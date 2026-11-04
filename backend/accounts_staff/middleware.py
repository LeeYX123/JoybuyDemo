from django.conf import settings

from accounts_staff.services import resolve_staff_session


class StaffSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.staff_account = None
        request.staff_session = None

        token = request.COOKIES.get(settings.STAFF_SESSION_COOKIE_NAME)
        if token:
            session = resolve_staff_session(token)
            if session:
                request.staff_session = session
                request.staff_account = session.staff

        return self.get_response(request)
