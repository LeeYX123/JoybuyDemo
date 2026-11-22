"""商家端「切换去商城」：把商家员工身份映射成同邮箱的买家账号。

手机版商家端头部按钮的落地接口。商家端登录态是 StaffAccount
（``joybuy_staff_session``），购物端登录态是 BuyerAccount
（``joybuy_buyer_session``），两套会话互相独立；这里只做「同邮箱同密码」
的一次性衔接，不引入新的账号体系。

2026-11-22 起不再直接写 buyer session cookie：商家端可能在 m.localhost:5174，
Chromium 拒绝从该 host 写入 ``Domain=.localhost`` 的 cookie（localhost 是
public-suffix 特例），所以改为签发 60 秒一次性 handoff token，由购物端
``/auth/merchant-handoff`` 页用自己的同源域名兑换 session。
"""

from urllib.parse import quote

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.response import Response

from accounts_buyers.models import BuyerAccount
from accounts_buyers.services import issue_merchant_handoff_token
from accounts_staff.api_exceptions import StaffApiError
from merchant_ops.merchant_context import MerchantAPIView


class MerchantSwitchToMallView(MerchantAPIView):
    """POST /api/v1/merchant/switch-to-mall（不要求店铺上下文）。"""

    skip_context = True

    def post(self, request):
        staff = getattr(request, "staff_account", None)
        if staff is None:
            raise StaffApiError(
                business_code="MERCHANT_AUTH_REQUIRED",
                message="请先登录商家账号。",
                status_code=401,
            )

        email = (staff.email or "").strip()
        if not email:
            raise StaffApiError(
                business_code="STAFF_EMAIL_REQUIRED",
                message="当前账号未绑定邮箱，无法切换到购物端",
                status_code=400,
            )

        buyer = BuyerAccount.objects.filter(email__iexact=email).first()
        if buyer is None:
            try:
                # 首次切换：直接复制商家密码的 Django 哈希串，与「申请店铺」
                # 流程「同邮箱同密码」口径一致（不接触明文密码）。
                with transaction.atomic():
                    buyer = BuyerAccount.objects.create(
                        email=email,
                        password=staff.password,
                        status=BuyerAccount.Status.ACTIVE,
                        auth_provider=BuyerAccount.AuthProvider.EMAIL,
                    )
            except IntegrityError:
                # 并发首次切换：另一个请求已建号，复用（不改密码）。
                buyer = BuyerAccount.objects.filter(email__iexact=email).first()
                if buyer is None:
                    raise

        token = issue_merchant_handoff_token(buyer_id=buyer.public_id)
        redirect_url = (
            f"{settings.STOREFRONT_BASE_URL}/auth/merchant-handoff"
            f"?token={quote(token, safe='')}"
        )
        return Response({"handoff_token": token, "redirect_url": redirect_url})
