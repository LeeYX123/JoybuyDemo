from decimal import Decimal, InvalidOperation

from accounts_staff.models import StaffAccount
from catalog.models import Sku
from django.db import IntegrityError, transaction
from django.utils import timezone
from merchants.models import Merchant

from offers.domain import (
    InventoryAdjustmentInvalid,
    InventoryIdempotencyConflict,
    MoneyValueInvalid,
    OfferSourceIdentityInvalid,
)
from offers.models import (
    Currency,
    InventoryLedger,
    Market,
    Offer,
    OfferSourceIdentity,
    PriceSnapshot,
)


def parse_money(value, currency: Currency) -> Decimal:
    if isinstance(value, float):
        raise MoneyValueInvalid("Money values cannot be provided as floating-point numbers.")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise MoneyValueInvalid("Money value is invalid.") from exc
    if not amount.is_finite() or amount < 0:
        raise MoneyValueInvalid("Money value must be finite and non-negative.")
    quantum = Decimal(1).scaleb(-currency.exponent)
    quantized = amount.quantize(quantum)
    if amount != quantized:
        raise MoneyValueInvalid(
            f"Money value has more than {currency.exponent} decimal places for {currency.code}."
        )
    return quantized


def _normalize_source_identity(source_system: str, source_id: str) -> tuple[str, str]:
    normalized_system = source_system.strip().casefold()
    normalized_id = source_id.strip()
    if not normalized_system or not normalized_id:
        raise OfferSourceIdentityInvalid("source_system and source_id are required.")
    return normalized_system, normalized_id


def _validate_offer_identity(
    offer: Offer,
    *,
    sku: Sku,
    merchant: Merchant,
    market: Market,
    currency: Currency,
) -> None:
    if (
        offer.sku_id != sku.pk
        or offer.merchant_id != merchant.pk
        or offer.market_id != market.pk
        or offer.currency_id != currency.pk
    ):
        raise OfferSourceIdentityInvalid(
            "The source offer identity is already assigned to a different offer."
        )


def import_offer_from_source(
    *,
    sku: Sku,
    merchant: Merchant,
    market: Market,
    currency: Currency,
    source_system: str,
    source_id: str,
    current_price,
    list_price=None,
    source_availability: str = Offer.SourceAvailability.UNKNOWN,
    source_url: str = "",
    promotion_label: str = "",
    observed_at=None,
) -> tuple[Offer, bool]:
    normalized_system, normalized_id = _normalize_source_identity(source_system, source_id)
    if source_availability not in Offer.SourceAvailability.values:
        raise OfferSourceIdentityInvalid("Unknown source availability.")
    parsed_current_price = parse_money(current_price, currency)
    parsed_list_price = parse_money(list_price, currency) if list_price is not None else None
    if parsed_list_price is not None and parsed_list_price < parsed_current_price:
        raise MoneyValueInvalid("List price cannot be lower than the current price.")
    observed_at = observed_at or timezone.now()

    with transaction.atomic():
        identity = (
            OfferSourceIdentity.objects.select_for_update()
            .select_related("offer")
            .filter(source_system=normalized_system, source_id=normalized_id)
            .first()
        )
        if identity:
            offer = identity.offer
            _validate_offer_identity(
                offer,
                sku=sku,
                merchant=merchant,
                market=market,
                currency=currency,
            )
            created = False
            identity.source_url = source_url.strip()
            identity.last_seen_at = observed_at
            identity.save(update_fields=["source_url", "last_seen_at", "updated_at"])
        else:
            offer, created = Offer.objects.get_or_create(
                sku=sku,
                merchant=merchant,
                market=market,
                currency=currency,
                defaults={
                    "current_price": parsed_current_price,
                    "list_price": parsed_list_price,
                    "promotion_label": promotion_label.strip(),
                    "source_availability": source_availability,
                },
            )
            OfferSourceIdentity.objects.create(
                offer=offer,
                source_system=normalized_system,
                source_id=normalized_id,
                source_url=source_url.strip(),
                first_seen_at=observed_at,
                last_seen_at=observed_at,
            )
            if created:
                InventoryLedger.objects.create(
                    offer=offer,
                    quantity_delta=offer.local_inventory,
                    balance_after=offer.local_inventory,
                    reason=InventoryLedger.Reason.INITIAL_IMPORT,
                    idempotency_key=f"offer-initial:{offer.public_id}",
                    reference_type="offer",
                    reference_id=str(offer.public_id),
                )

        offer.current_price = parsed_current_price
        offer.list_price = parsed_list_price
        offer.promotion_label = promotion_label.strip()
        offer.source_availability = source_availability
        offer.save(
            update_fields=[
                "current_price",
                "list_price",
                "promotion_label",
                "source_availability",
                "updated_at",
            ]
        )
        snapshot, snapshot_created = PriceSnapshot.objects.get_or_create(
            offer=offer,
            observed_at=observed_at,
            defaults={
                "currency": currency,
                "current_price": parsed_current_price,
                "list_price": parsed_list_price,
                "promotion_label": promotion_label.strip(),
                "source_url": source_url.strip(),
            },
        )
        if not snapshot_created and (
            snapshot.currency_id != currency.pk
            or snapshot.current_price != parsed_current_price
            or snapshot.list_price != parsed_list_price
        ):
            raise OfferSourceIdentityInvalid(
                "The observation timestamp already exists with different price data."
            )
        return offer, created


def adjust_offer_inventory(
    *,
    offer: Offer,
    quantity_delta: int,
    reason: str,
    idempotency_key: str,
    actor: StaffAccount | None = None,
    request_id=None,
    reference_type: str = "",
    reference_id: str = "",
    note: str = "",
) -> InventoryLedger:
    if (
        not isinstance(quantity_delta, int)
        or isinstance(quantity_delta, bool)
        or quantity_delta == 0
    ):
        raise InventoryAdjustmentInvalid("Inventory delta must be a non-zero integer.")
    normalized_key = idempotency_key.strip()
    if not normalized_key:
        raise InventoryAdjustmentInvalid("An inventory idempotency key is required.")
    if reason not in InventoryLedger.Reason.values:
        raise InventoryAdjustmentInvalid("Unknown inventory adjustment reason.")

    existing = InventoryLedger.objects.filter(idempotency_key=normalized_key).first()
    if existing:
        if (
            existing.offer_id != offer.pk
            or existing.quantity_delta != quantity_delta
            or existing.reason != reason
        ):
            raise InventoryIdempotencyConflict(
                "The inventory idempotency key was already used for another adjustment."
            )
        return existing

    try:
        with transaction.atomic():
            locked_offer = Offer.objects.select_for_update().get(pk=offer.pk)
            balance_after = locked_offer.local_inventory + quantity_delta
            if balance_after < 0:
                raise InventoryAdjustmentInvalid("Inventory cannot become negative.")
            locked_offer.local_inventory = balance_after
            locked_offer.save(update_fields=["local_inventory", "updated_at"])
            return InventoryLedger.objects.create(
                offer=locked_offer,
                quantity_delta=quantity_delta,
                balance_after=balance_after,
                reason=reason,
                idempotency_key=normalized_key,
                actor=actor,
                request_id=request_id,
                reference_type=reference_type,
                reference_id=reference_id,
                note=note,
            )
    except IntegrityError:
        existing = InventoryLedger.objects.get(idempotency_key=normalized_key)
        if (
            existing.offer_id != offer.pk
            or existing.quantity_delta != quantity_delta
            or existing.reason != reason
        ):
            raise InventoryIdempotencyConflict(
                "The inventory idempotency key was already used for another adjustment."
            )
        return existing
