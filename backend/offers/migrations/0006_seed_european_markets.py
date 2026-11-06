from django.db import migrations

LOCALES = {
    "en-GB": ("en", "GB", "English (United Kingdom)", "English"),
    "zh-CN": ("zh", "CN", "Chinese (Simplified)", "中文（简体）"),
    "de-DE": ("de", "DE", "German (Germany)", "Deutsch"),
    "fr-FR": ("fr", "FR", "French (France)", "Français"),
    "nl-NL": ("nl", "NL", "Dutch (Netherlands)", "Nederlands"),
    "nl-BE": ("nl", "BE", "Dutch (Belgium)", "Nederlands"),
    "fr-BE": ("fr", "BE", "French (Belgium)", "Français"),
    "de-BE": ("de", "BE", "German (Belgium)", "Deutsch"),
    "lb-LU": ("lb", "LU", "Luxembourgish", "Lëtzebuergesch"),
    "fr-LU": ("fr", "LU", "French (Luxembourg)", "Français"),
    "de-LU": ("de", "LU", "German (Luxembourg)", "Deutsch"),
}

MARKETS = {
    "GB": ("United Kingdom", "en-GB", "Europe/London", "GBP", None),
    "BE": ("Belgium", "nl-BE", "Europe/Brussels", "EUR", "GB"),
    "DE": ("Germany", "de-DE", "Europe/Berlin", "EUR", "GB"),
    "FR": ("France", "fr-FR", "Europe/Paris", "EUR", "GB"),
    "NL": ("Netherlands", "nl-NL", "Europe/Amsterdam", "EUR", "GB"),
    "LU": ("Luxembourg", "lb-LU", "Europe/Luxembourg", "EUR", "GB"),
}

MARKET_LOCALES = {
    "GB": ["en-GB", "zh-CN"],
    "BE": ["nl-BE", "fr-BE", "de-BE"],
    "DE": ["de-DE"],
    "FR": ["fr-FR"],
    "NL": ["nl-NL"],
    "LU": ["lb-LU", "fr-LU", "de-LU"],
}


def seed_european_markets(apps, schema_editor):
    currency_model = apps.get_model("offers", "Currency")
    locale_model = apps.get_model("offers", "Locale")
    market_model = apps.get_model("offers", "Market")
    market_locale_model = apps.get_model("offers", "MarketLocale")

    gbp, _ = currency_model.objects.update_or_create(
        code="GBP",
        defaults={
            "name": "Pound sterling",
            "symbol": "£",
            "exponent": 2,
            "is_active": True,
        },
    )
    eur, _ = currency_model.objects.update_or_create(
        code="EUR",
        defaults={
            "name": "Euro",
            "symbol": "€",
            "exponent": 2,
            "is_active": True,
        },
    )
    currencies = {"GBP": gbp, "EUR": eur}

    locales = {}
    for code, (language_code, region_code, name, native_name) in LOCALES.items():
        locale, _ = locale_model.objects.update_or_create(
            code=code,
            defaults={
                "language_code": language_code,
                "region_code": region_code,
                "name": name,
                "native_name": native_name,
                "is_active": True,
            },
        )
        locales[code] = locale

    markets = {}
    for code, (name, default_locale, time_zone, currency_code, _fallback) in MARKETS.items():
        market, _ = market_model.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "default_locale": default_locale,
                "time_zone": time_zone,
                "default_currency": currencies[currency_code],
                "display_currency_symbol": "$",
                "is_active": True,
            },
        )
        markets[code] = market

    for code, (*_values, fallback_code) in MARKETS.items():
        fallback = markets.get(fallback_code)
        market_model.objects.filter(pk=markets[code].pk).update(offer_fallback_market=fallback)

    for market_code, locale_codes in MARKET_LOCALES.items():
        market = markets[market_code]
        market_locale_model.objects.filter(market=market).update(is_default=False)
        for sort_order, locale_code in enumerate(locale_codes):
            market_locale_model.objects.update_or_create(
                market=market,
                locale=locales[locale_code],
                defaults={"is_default": sort_order == 0, "sort_order": sort_order},
            )


def unseed_european_markets(apps, schema_editor):
    market_model = apps.get_model("offers", "Market")
    locale_model = apps.get_model("offers", "Locale")
    market_model.objects.filter(code__in=["BE", "DE", "FR", "NL", "LU"]).delete()
    locale_model.objects.filter(code__in=LOCALES).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("offers", "0005_locale_market_display_currency_symbol_and_more"),
    ]

    operations = [migrations.RunPython(seed_european_markets, unseed_european_markets)]
