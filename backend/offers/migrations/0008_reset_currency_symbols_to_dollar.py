"""全站价格符号统一为 $（2026-11-27 用户拍板）。

0007 曾按各市场 ``default_currency`` 把符号改成 £/€，但站点规则是
所有价格一律显示 ``$``。本迁移把所有市场的 ``display_currency_symbol``
重置为 ``$``。
"""

from django.db import migrations


def reset_symbols(apps, schema_editor):
    market_model = apps.get_model("offers", "Market")
    market_model.objects.update(display_currency_symbol="$")


def revert(apps, schema_editor):
    market_model = apps.get_model("offers", "Market")
    for market in market_model.objects.select_related("default_currency"):
        code = market.default_currency.code if market.default_currency_id else ""
        symbol = {"GBP": "£", "EUR": "€"}.get(code, "$")
        if market.display_currency_symbol != symbol:
            market.display_currency_symbol = symbol
            market.save(update_fields=["display_currency_symbol", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("offers", "0007_fix_market_currency_symbols"),
    ]

    operations = [
        migrations.RunPython(reset_symbols, revert),
    ]
