from dataclasses import dataclass

from offers.models import Locale, Market, MarketLocale

LOCALE_ALIASES = {
    "en": "en-GB",
    "zh": "zh-CN",
    "de": "de-DE",
    "fr": "fr-FR",
    "nl": "nl-NL",
    "lb": "lb-LU",
}


@dataclass(frozen=True)
class MarketContext:
    market: Market
    locale: Locale


def normalize_locale_code(value: str) -> str:
    cleaned = (value or "").strip()
    return LOCALE_ALIASES.get(cleaned, cleaned)


def resolve_market_context(request) -> MarketContext | None:
    market_code = (
        (request.GET.get("market") or request.COOKIES.get("joybuy-market") or "GB").strip().upper()
    )
    market = (
        Market.objects.select_related("default_currency", "offer_fallback_market")
        .filter(code=market_code, is_active=True)
        .first()
    )
    if market is None:
        return None

    requested_locale = normalize_locale_code(
        request.GET.get("locale") or request.COOKIES.get("joybuy-locale") or market.default_locale
    )
    option = (
        MarketLocale.objects.select_related("locale")
        .filter(market=market, locale__code=requested_locale, locale__is_active=True)
        .first()
    )
    if option is None:
        option = (
            MarketLocale.objects.select_related("locale")
            .filter(market=market, is_default=True, locale__is_active=True)
            .order_by("sort_order", "pk")
            .first()
        )
    if option is None:
        locale = Locale.objects.filter(code=market.default_locale, is_active=True).first()
        if locale is None:
            return None
    else:
        locale = option.locale
    return MarketContext(market=market, locale=locale)


def offer_market_chain(market: Market) -> list[Market]:
    result = [market]
    seen = {market.pk}
    current = market
    while current.offer_fallback_market_id and current.offer_fallback_market_id not in seen:
        current = current.offer_fallback_market
        result.append(current)
        seen.add(current.pk)
    return result


def serialize_market(market: Market) -> dict:
    options = market.locale_options.select_related("locale").filter(locale__is_active=True)
    return {
        "code": market.code,
        "name": market.name,
        "default_locale": market.default_locale,
        "time_zone": market.time_zone,
        "display_currency_symbol": market.display_currency_symbol,
        "stored_currency": market.default_currency.code,
        "offer_fallback_market": (
            market.offer_fallback_market.code if market.offer_fallback_market_id else None
        ),
        "locales": [
            {
                "code": option.locale.code,
                "name": option.locale.name,
                "native_name": option.locale.native_name,
                "is_default": option.is_default,
            }
            for option in options.order_by("sort_order", "locale__code")
        ],
    }
