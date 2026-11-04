from django.conf import settings

from accounts_buyers.services import resolve_buyer_session


class BuyerSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.buyer_account = None
        request.buyer_session = None

        token = request.COOKIES.get(settings.BUYER_SESSION_COOKIE_NAME)
        if token:
            session = resolve_buyer_session(token)
            if session:
                request.buyer_session = session
                request.buyer_account = session.account

        return self.get_response(request)
