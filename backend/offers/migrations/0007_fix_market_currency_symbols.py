"""修正市场货币符号（2026-11-27）。

0006 种子把所有市场的 ``display_currency_symbol`` 写成了 ``$``，导致购物端
列表/详情价格显示成美元符号。按各市场 ``default_currency`` 修正：
GBP → £，EUR → €。
"""

from django.db import migrations

SYMBOLS = {"GBP": "£", "EUR": "€"}


def fix_symbols(apps, schema_editor):
    market_model = apps.get_model("offers", "Market")
    for market in market_model.objects.select_related("default_currency"):
        code = market.default_currency.code if market.default_currency_id else ""
        symbol = SYMBOLS.get(code)
        if symbol and market.display_currency_symbol != symbol:
            market.display_currency_symbol = symbol
            market.save(update_fields=["display_currency_symbol", "updated_at"])


def revert(apps, schema_editor):
    market_model = apps.get_model("offers", "Market")
    market_model.objects.update(display_currency_symbol="$")


class Migration(migrations.Migration):

    dependencies = [
        ("offers", "0006_seed_european_markets"),
    ]

    operations = [
        migrations.RunPython(fix_symbols, revert),
    ]
