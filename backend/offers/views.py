from django.http import JsonResponse

from offers.market_services import serialize_market
from offers.models import Market


def storefront_markets(request):
    markets = (
        Market.objects.filter(is_active=True)
        .select_related("default_currency", "offer_fallback_market")
        .prefetch_related("locale_options__locale")
        .order_by("code")
    )
    return JsonResponse({"markets": [serialize_market(market) for market in markets]})
