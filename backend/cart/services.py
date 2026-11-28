from dataclasses import dataclass

from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone

from cart.models import MAX_QTY_PER_ITEM, Cart, CartItem, generate_anonymous_token
from merchants.services import IMPORT_FALLBACK_SLUG
from offers.models import Offer

ANONYMOUS_COOKIE_NAME = "joybuy_cart_token"
CART_MAX_AGE_SECONDS = 60 * 60 * 24 * 30  # 30 days
# 需求文档03 12.3：平台自营口径的对外店名（自营导入商家的商品在购物车/下单
# 快照里统一按 Joybuy 官营呈现，与真站「Sold and fulfilled by Joybuy」一致）。
JOYBUY_OFFICIAL_MERCHANT_NAME = "Joybuy"


class CartError(Exception):
    """Domain error with a stable business code for the API layer."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class CartItemInvalid(CartError):
    def __init__(self, code="CART_ITEM_INVALID", message="The cart item is not available."):
        super().__init__(code, message)


@dataclass
class CartRequestContext:
    """Resolved cart identity for one request."""

    account = None  # BuyerAccount or None
    anonymous_token: str = ""
    new_anonymous_token: str = ""


def resolve_cart_context(request) -> CartRequestContext:
    context = CartRequestContext()
    context.account = getattr(request, "buyer_account", None)
    context.anonymous_token = request.COOKIES.get(ANONYMOUS_COOKIE_NAME, "")
    if not context.account and not context.anonymous_token:
        context.new_anonymous_token = generate_anonymous_token()
    return context


def _apply_anonymous_cookie(response, context) -> None:
    if context.new_anonymous_token:
        response.set_cookie(
            ANONYMOUS_COOKIE_NAME,
            context.new_anonymous_token,
            max_age=CART_MAX_AGE_SECONDS,
            httponly=True,
            samesite="Lax",
            secure=False,
        )


def get_or_create_cart(context) -> Cart:
    if context.account:
        cart, _ = Cart.objects.get_or_create(account=context.account, status=Cart.Status.OPEN)
        return cart
    token = context.anonymous_token or context.new_anonymous_token
    if not token:
        token = context.new_anonymous_token = generate_anonymous_token()
    cart, _ = Cart.objects.get_or_create(anonymous_token=token, status=Cart.Status.OPEN)
    return cart


def _validate_offer(offer) -> None:
    if (
        offer is None
        or offer.status != Offer.Status.ACTIVE
        or offer.local_inventory < 1
        or offer.source_availability == Offer.SourceAvailability.UNAVAILABLE
    ):
        raise CartItemInvalid("SKU_NOT_AVAILABLE", "This SKU is not available to buy.")


def _offer_for_spu(spu_public_id: str, market, *, lock: bool = False) -> Offer:
    """按卡片 ``price_min`` 口径挑 SPU 的可购买 Offer（2026-11-28）。

    搜索接口的 item 不带 offer id，卡片【+】只能传 ``spu_public_id``。这里沿
    请求市场的 offer 市场链（``market`` → 回退市场，与搜索索引 ``min_price``
    同源）取「最低价 + ACTIVE + 有库存」的 Offer；链上没有可购买 Offer 时
    抛既有的 ``SKU_NOT_AVAILABLE``。最低价那一行若缺货会顺延到下一条，避免
    卡片有价却加不进车。
    """

    from catalog.models import Spu
    from offers.market_services import offer_market_chain

    if market is None:
        raise CartItemInvalid("SKU_NOT_AVAILABLE", "This SKU is not available to buy.")
    spu = Spu.objects.filter(public_id=spu_public_id).first() if spu_public_id else None
    if spu is None:
        raise CartItemInvalid("SKU_NOT_AVAILABLE", "This SKU is not available to buy.")

    for candidate_market in offer_market_chain(market):
        queryset = Offer.objects.select_related("currency").filter(
            sku__spu=spu,
            market=candidate_market,
            status=Offer.Status.ACTIVE,
            local_inventory__gte=1,
        )
        if lock:
            queryset = queryset.select_for_update()
        offer = (
            queryset.exclude(source_availability=Offer.SourceAvailability.UNAVAILABLE)
            .order_by("current_price", "pk")
            .first()
        )
        if offer is not None:
            return offer
    raise CartItemInvalid("SKU_NOT_AVAILABLE", "This SKU is not available to buy.")


def add_item(
    context,
    *,
    offer_public_id: str = "",
    quantity: int,
    spu_public_id: str = "",
    market=None,
) -> Cart:
    """加购：``offer_public_id``（原路径）或 ``spu_public_id``（卡片【+】）二选一。

    SPU 路径先解析成当前市场的最低价可购买 Offer，之后与 offer 路径走完全
    同一条逻辑（白名单、匿名购物车、库存、重复行合并数量）。
    """

    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise CartItemInvalid(message="Quantity must be a positive integer.")
    if quantity > MAX_QTY_PER_ITEM:
        raise CartItemInvalid("QUANTITY_LIMIT", "Quantity cannot exceed 99 per item.")

    # 白名单后端打通（WP-42 文档购物端）：只有白名单账户能加购，
    # 以后端返回的白名单标识为准，未拿到标识按不可购买处理。
    if context.account is not None and not context.account.purchase_whitelisted:
        raise CartItemInvalid("NOT_WHITELISTED", "当前账号不在购买白名单内，无法加购。")

    with transaction.atomic():
        if offer_public_id:
            offer = (
                Offer.objects.select_for_update()
                .select_related("currency")
                .filter(public_id=offer_public_id)
                .first()
            )
        elif spu_public_id:
            offer = _offer_for_spu(spu_public_id, market, lock=True)
        else:
            raise CartItemInvalid("SKU_NOT_AVAILABLE", "This SKU is not available to buy.")
        _validate_offer(offer)
        if quantity > offer.local_inventory:
            raise CartItemInvalid("INSUFFICIENT_STOCK", "Not enough stock for this quantity.")

        cart = get_or_create_cart(context)
        item, created = CartItem.objects.get_or_create(
            cart=cart,
            offer=offer,
            defaults={"quantity": quantity},
        )
        if not created:
            new_quantity = item.quantity + quantity
            if new_quantity > 99:
                raise CartItemInvalid("QUANTITY_LIMIT", "Quantity cannot exceed 99 per item.")
            if new_quantity > offer.local_inventory:
                raise CartItemInvalid("INSUFFICIENT_STOCK", "Not enough stock for this quantity.")
            item.quantity = new_quantity
            item.updated_at = timezone.now()
            item.save(update_fields=["quantity", "updated_at"])
    return cart


def update_item(context, *, item_public_id: str, quantity: int) -> Cart:
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise CartItemInvalid(message="Quantity must be a positive integer.")
    if quantity > 99:
        raise CartItemInvalid("QUANTITY_LIMIT", "Quantity cannot exceed 99 per item.")
    with transaction.atomic():
        cart = get_or_create_cart(context)
        item = (
            CartItem.objects.select_for_update()
            .select_related("offer")
            .filter(cart=cart, public_id=item_public_id)
            .first()
        )
        if item is None:
            raise CartItemInvalid(message="This cart item no longer exists.")
        if quantity > item.offer.local_inventory:
            raise CartItemInvalid("INSUFFICIENT_STOCK", "Not enough stock for this quantity.")
        item.quantity = quantity
        item.updated_at = timezone.now()
        item.save(update_fields=["quantity", "updated_at"])
    return cart


def remove_item(context, *, item_public_id: str) -> Cart:
    cart = get_or_create_cart(context)
    deleted, _ = CartItem.objects.filter(cart=cart, public_id=item_public_id).delete()
    if not deleted:
        raise CartItemInvalid(message="This cart item no longer exists.")
    return cart


def merchant_entry(offer) -> dict:
    """Per-item merchant payload (需求文档03 12.3，增量字段不破坏既有契约)。

    来源 offer→merchant 链；None 安全：无商家（防御分支）回退 Joybuy 官营口径；
    平台自营导入商家（IMPORT_FALLBACK）对外也统一为 Joybuy 官营店名。
    """

    merchant = getattr(offer, "merchant", None)
    if merchant is None:
        return {
            "merchant_id": "",
            "merchant_name": JOYBUY_OFFICIAL_MERCHANT_NAME,
            "merchant_avatar_url": "",
        }
    merchant_name = (
        JOYBUY_OFFICIAL_MERCHANT_NAME
        if merchant.slug == IMPORT_FALLBACK_SLUG
        else merchant.display_name
    )
    return {
        "merchant_id": str(merchant.public_id),
        "merchant_name": merchant_name,
        "merchant_avatar_url": merchant.avatar_url or "",
    }


def resolve_item_title(spu, market, locale) -> str:
    """购物车/直购行标题：与 PDP 同源的本地化口径（2026-11-28）。

    ``market``/``locale`` 缺失（订单快照等老调用方）时保持旧行为：按 pk
    取第一条 ``SpuTranslation``（历史快照逐字节不变）。给了请求上下文就走
    :func:`catalog.localization_services.resolve_product_content`
    —— ``SpuMarketContent`` CURRENT+locale 优先，其次 ``SpuTranslation``，
    请求 locale 没有译文时显式回退 en-GB（绝不落到 de/fr 等其它语言）。
    """

    if market is None or locale is None:
        translation = spu.translations.order_by("pk").first()
        return translation.title if translation else ""

    from catalog.localization_services import resolve_product_content

    return resolve_product_content(spu, market, locale).title


def serialize_cart(cart: Cart, *, market=None, locale=None) -> dict:
    """Live re-validation: prices come from the current offer, invalid rows
    are flagged instead of silently dropped so the buyer can act on them.

    ``market``/``locale`` 是请求上下文（购物车 API / checkout_quote 传入），
    用于行标题的本地化；不传时保持旧的「第一条译文」快照口径。
    """

    items = []
    subtotal = None
    changed = False
    currency_code = ""
    rows = cart.items.select_related(
        "offer", "offer__currency", "offer__sku__spu", "offer__merchant"
    )
    if market is not None and locale is not None:
        # 固定 +2 条查询（与行数无关）：resolve_product_content 只读
        # spu.market_contents / spu.translations，过滤到请求 locale 就够。
        from catalog.models import SpuMarketContent, SpuTranslation

        rows = rows.prefetch_related(
            Prefetch(
                "offer__sku__spu__market_contents",
                queryset=SpuMarketContent.objects.select_related("locale").filter(
                    locale=locale
                ),
            ),
            Prefetch("offer__sku__spu__translations", queryset=SpuTranslation.objects.all()),
        )
    for item in rows:
        offer = item.offer
        entry = {
            "public_id": str(item.public_id),
            "offer_public_id": str(offer.public_id),
            "spu_public_id": str(offer.sku.spu.public_id),
            "title": resolve_item_title(offer.sku.spu, market, locale),
            "quantity": item.quantity,
            "price": str(offer.current_price),
            "currency": offer.currency.code,
            "inventory_display": offer.display_inventory,
            "merchant": merchant_entry(offer),
            "is_valid": offer.status == Offer.Status.ACTIVE
            and offer.local_inventory > 0
            and offer.source_availability != Offer.SourceAvailability.UNAVAILABLE,
            "issue": None,
        }
        if not entry["is_valid"]:
            entry["issue"] = "SKU_NOT_AVAILABLE"
            changed = True
        elif item.quantity > offer.local_inventory:
            entry["issue"] = "INSUFFICIENT_STOCK"
            entry["quantity"] = offer.local_inventory
            changed = True
        if entry["is_valid"]:
            line_total = offer.current_price * entry["quantity"]
            subtotal = line_total if subtotal is None else subtotal + line_total
            currency_code = offer.currency.code
        items.append(entry)
    return {
        "public_id": str(cart.public_id),
        "items": items,
        "subtotal": str(subtotal) if subtotal is not None else None,
        "currency": currency_code,
        "needs_attention": changed,
    }


def merge_anonymous_cart(context) -> dict:
    """Fold the anonymous cart into the buyer's open cart on sign-in."""

    if not context.account:
        raise CartError("AUTH_REQUIRED", "Sign in required to merge carts.")
    token = context.anonymous_token
    if not token:
        return {"merged_items": 0}

    with transaction.atomic():
        anonymous = Cart.objects.filter(anonymous_token=token, status=Cart.Status.OPEN).first()
        if anonymous is None:
            return {"merged_items": 0}
        buyer_cart, _ = Cart.objects.get_or_create(account=context.account, status=Cart.Status.OPEN)
        merged = 0
        for item in anonymous.items.select_for_update().select_related("offer"):
            if item.offer.status != Offer.Status.ACTIVE or item.offer.local_inventory < 1:
                continue
            target, created = CartItem.objects.get_or_create(
                cart=buyer_cart,
                offer=item.offer,
                defaults={"quantity": item.quantity},
            )
            if created:
                merged += 1
            else:
                target.quantity = min(99, target.quantity + item.quantity)
                target.save(update_fields=["quantity", "updated_at"])
                merged += 1
        anonymous.status = Cart.Status.MERGED
        anonymous.save(update_fields=["status", "updated_at"])
        return {"merged_items": merged}
