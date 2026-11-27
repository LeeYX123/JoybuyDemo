from django.conf import settings

from accounts_staff.services import resolve_staff_session


class StaffSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.staff_account = None
        request.staff_session = None

        # 管理端专用 cookie 优先，没有才回退到员工/商家通用 cookie。
        # 2026-11-27：商家端 handoff 会写 STAFF cookie，若不优先读管理端 cookie，
        # 同浏览器里的管理端登录态会被商家账号会话遮蔽。
        token = request.COOKIES.get(
            settings.STAFF_ADMIN_SESSION_COOKIE_NAME
        ) or request.COOKIES.get(settings.STAFF_SESSION_COOKIE_NAME)
        if token:
            session = resolve_staff_session(token)
            if session:
                request.staff_session = session
                request.staff_account = session.staff

        return self.get_response(request)
