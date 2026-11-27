"""购物端「申请店铺」：买家提交/查看开店申请 + 管理端入驻申请审核。

买家侧挂在 ``/api/v1/account/merchant-application``（买家会话，不进
商家端员工会话与店铺上下文链）；管理侧挂在
``/api/v1/admin/merchant-applications*``（员工会话 + merchants 权限，
风格同 AdminMerchantsView）。

approve 是关键新逻辑：create_merchant 开店后，按买家邮箱打通商家端
账号——StaffAccount 不存在则创建并**直接复制买家密码哈希**（两表同套
Django hasher，买家密码即可登录商家端）；已存在则只加 membership、
不动其密码。之后走既有 review_admission 状态机（免保证金→ACTIVE、
需保证金→PENDING_DEPOSIT）并回填申请单。
"""

import re
from urllib.parse import urlparse

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.response import Response

from accounts_buyers.api_exceptions import BuyerApiError
from accounts_buyers.models import BuyerAccount
from accounts_buyers.views import BuyerCsrfAPIView
from accounts_staff.api_exceptions import StaffApiError
from accounts_staff.models import StaffAccount
from accounts_staff.permissions import StaffRbacPermission
from accounts_staff.services import create_staff_session, set_staff_session_cookie
from audit.services import record_audit
from media.models import MediaAsset
from media.uploads import UploadError, store_upload
from merchant_ops.api_utils import OpsAPIView, iso, paginate, parse_amount, parse_positive_int
from merchants.models import MerchantApplication, MerchantMembership, MerchantRole
from merchants.services import create_merchant, review_admission

MAX_SHOP_NAME_LENGTH = 60
MAX_USER_NAME_LENGTH = 60
MAX_ADDRESS_LENGTH = 255

# 手机号宽松校验：去掉空格 / 横线 / 括号后，必须是「可选 + 国家码 + 6~20 位数字」
# （覆盖 +447700900123 与 07700900123 两种写法，正则口径在测试里固化）。
PHONE_PATTERN = re.compile(r"^\+?\d{6,20}$")
PHONE_SEPARATORS = re.compile(r"[\s\-()]")


def _clean_phone(raw: str) -> str:
    return PHONE_SEPARATORS.sub("", raw or "")


def _validated_media_url(raw: str, *, field: str) -> str:
    """申请图片只接受本站 ``/media/`` 前缀且必须对应真实 MediaAsset。

    买家不能凭空填一个外链或编造路径；路径必须由买家侧上传接口
    落盘后返回。``..`` 之类的穿越片段在 relative_path 匹配中天然不存在。
    """

    url = str(raw or "").strip()
    prefix = f"{settings.MEDIA_URL.rstrip('/')}/"
    if not url.startswith(prefix):
        raise BuyerApiError(
            business_code=f"{field}_INVALID",
            message="图片地址无效，请通过本页上传获取。",
            status_code=400,
        )
    relative = url[len(prefix) :]
    if not relative or relative.startswith("/") or ".." in relative:
        raise BuyerApiError(
            business_code=f"{field}_INVALID",
            message="图片地址无效，请通过本页上传获取。",
            status_code=400,
        )
    if not MediaAsset.objects.filter(relative_path=relative).exists():
        raise BuyerApiError(
            business_code=f"{field}_NOT_FOUND",
            message="图片不存在或已失效，请重新上传。",
            status_code=400,
        )
    return url


def _application_payload(application: MerchantApplication) -> dict:
    merchant = application.merchant
    return {
        "id": str(application.pk),
        "status": application.status,
        "user_name": application.user_name,
        "shop_name": application.shop_name,
        "phone": application.phone,
        "legal_name": application.legal_name,
        "referrer_code": application.referrer_code,
        "id_document_type": application.id_document_type,
        "residential_address": application.residential_address,
        "logo_image_url": application.logo_image_url,
        "id_document_image_url": application.id_document_image_url,
        "reject_reason": application.reject_reason,
        "submitted_at": iso(application.submitted_at),
        "reviewed_at": iso(application.reviewed_at),
        "merchant": {
            "id": str(merchant.public_id),
            "public_id": str(merchant.public_id),
            "display_name": merchant.display_name,
            "onboarding_status": merchant.onboarding_status,
        }
        if merchant is not None
        else None,
    }


def _require_buyer(request) -> BuyerAccount:
    buyer = getattr(request, "buyer_account", None)
    if buyer is None:
        raise BuyerApiError(
            business_code="BUYER_AUTH_REQUIRED",
            message="请先登录后再操作。",
            status_code=401,
        )
    return buyer


class BuyerMerchantApplicationView(BuyerCsrfAPIView):
    """GET 当前申请 / POST 提交（或驳回后重新提交）。"""

    def get(self, request):
        buyer = _require_buyer(request)
        application = MerchantApplication.objects.filter(buyer=buyer).first()
        return Response(
            {"application": _application_payload(application) if application is not None else None}
        )

    def post(self, request):
        buyer = _require_buyer(request)
        payload = request.data or {}

        # ---- 必填文本：用户名字 / 店铺名 / 手机号码 / 居住地址 ----
        user_name = str(payload.get("user_name") or "").strip()
        if not user_name:
            raise BuyerApiError(
                business_code="USER_NAME_REQUIRED",
                message="请填写用户名字。",
                status_code=400,
            )
        if len(user_name) > MAX_USER_NAME_LENGTH:
            raise BuyerApiError(
                business_code="USER_NAME_TOO_LONG",
                message=f"用户名字不能超过 {MAX_USER_NAME_LENGTH} 个字符。",
                status_code=400,
            )

        shop_name = str(payload.get("shop_name") or "").strip()
        if not shop_name:
            raise BuyerApiError(
                business_code="SHOP_NAME_REQUIRED",
                message="请填写店铺名称。",
                status_code=400,
            )
        if len(shop_name) > MAX_SHOP_NAME_LENGTH:
            raise BuyerApiError(
                business_code="SHOP_NAME_TOO_LONG",
                message=f"店铺名称不能超过 {MAX_SHOP_NAME_LENGTH} 个字符。",
                status_code=400,
            )

        phone = _clean_phone(str(payload.get("phone") or "").strip())
        if not phone:
            raise BuyerApiError(
                business_code="PHONE_REQUIRED",
                message="请填写手机号码。",
                status_code=400,
            )
        if len(phone) > 32 or not PHONE_PATTERN.match(phone):
            raise BuyerApiError(
                business_code="PHONE_INVALID",
                message="手机号码格式不正确。",
                status_code=400,
            )

        residential_address = str(payload.get("residential_address") or "").strip()
        if not residential_address:
            raise BuyerApiError(
                business_code="RESIDENTIAL_ADDRESS_REQUIRED",
                message="请填写个人居住地址。",
                status_code=400,
            )
        if len(residential_address) > MAX_ADDRESS_LENGTH:
            raise BuyerApiError(
                business_code="RESIDENTIAL_ADDRESS_TOO_LONG",
                message=f"个人居住地址不能超过 {MAX_ADDRESS_LENGTH} 个字符。",
                status_code=400,
            )

        # ---- 个人证件：类型三选一 + 证件照片 ----
        id_document_type = str(payload.get("id_document_type") or "").strip().upper()
        if id_document_type not in MerchantApplication.IdDocumentType.values:
            raise BuyerApiError(
                business_code="ID_DOCUMENT_TYPE_INVALID",
                message="证件类型必须是身份证、护照或驾照。",
                status_code=400,
            )

        logo_image_url = _validated_media_url(
            payload.get("logo_image_url"), field="LOGO_IMAGE"
        )
        id_document_image_url = _validated_media_url(
            payload.get("id_document_image_url"), field="ID_DOCUMENT_IMAGE"
        )

        # ---- 选填：邀请码（不在提交时校验有效性；approve 才尝试绑定，
        # 无效忽略——与 create_merchant/WP-42 的口径一致）。 ----
        referrer_code = str(payload.get("referrer_code") or "").strip()
        if len(referrer_code) > 32:
            raise BuyerApiError(
                business_code="REFERRER_CODE_TOO_LONG",
                message="邀请码不能超过 32 个字符。",
                status_code=400,
            )
        # legal_name 为旧表单遗留（历史行），新表单不再收集，保留原值不覆盖。

        if not (buyer.email or "").strip():
            raise BuyerApiError(
                business_code="BUYER_EMAIL_REQUIRED",
                message="当前账号未绑定邮箱，无法申请店铺。",
                status_code=400,
            )

        existing = MerchantApplication.objects.filter(buyer=buyer).first()
        if existing is not None:
            if existing.status == MerchantApplication.Status.PENDING:
                raise BuyerApiError(
                    business_code="APPLICATION_ALREADY_PENDING",
                    message="您已提交申请，正在审核中。",
                    status_code=409,
                )
            if existing.status == MerchantApplication.Status.APPROVED:
                raise BuyerApiError(
                    business_code="SHOP_ALREADY_APPROVED",
                    message="您已开通店铺。",
                    status_code=409,
                )

        # 一账号一店（2026-11-22）：该买家邮箱已打通商家端账号且已绑店时，
        # 填表前就拒绝，避免提交后才在审批环节被拒。
        bound_staff = StaffAccount.objects.filter(email__iexact=(buyer.email or "").strip()).first()
        if (
            bound_staff is not None
            and MerchantMembership.objects.filter(staff=bound_staff).exists()
        ):
            raise BuyerApiError(
                business_code="ACCOUNT_ALREADY_BOUND_SHOP",
                message="该邮箱已绑定其他店铺，一个账号只能绑定一家店铺。",
                status_code=409,
            )

        now = timezone.now()
        with transaction.atomic():
            if existing is not None:
                # REJECTED 重新申请：原行重置为 PENDING，清空驳回原因与上一轮
                # 审核痕迹、刷新提交时间。
                existing.user_name = user_name
                existing.shop_name = shop_name
                existing.phone = phone
                existing.referrer_code = referrer_code
                existing.id_document_type = id_document_type
                existing.residential_address = residential_address
                existing.logo_image_url = logo_image_url
                existing.id_document_image_url = id_document_image_url
                existing.reject_reason = ""
                existing.status = MerchantApplication.Status.PENDING
                existing.submitted_at = now
                existing.reviewed_by = None
                existing.reviewed_at = None
                existing.save(
                    update_fields=[
                        "user_name",
                        "shop_name",
                        "phone",
                        "referrer_code",
                        "id_document_type",
                        "residential_address",
                        "logo_image_url",
                        "id_document_image_url",
                        "reject_reason",
                        "status",
                        "submitted_at",
                        "reviewed_by",
                        "reviewed_at",
                        "updated_at",
                    ]
                )
                application = existing
            else:
                application = MerchantApplication.objects.create(
                    buyer=buyer,
                    user_name=user_name,
                    shop_name=shop_name,
                    phone=phone,
                    referrer_code=referrer_code,
                    id_document_type=id_document_type,
                    residential_address=residential_address,
                    logo_image_url=logo_image_url,
                    id_document_image_url=id_document_image_url,
                )
        return Response({"application": _application_payload(application)}, status=201)


class BuyerMerchantApplicationMediaView(BuyerCsrfAPIView):
    """买家侧「申请开店」图片上传（店铺 logo / 个人证件照）。

    与管理端 ``/admin/media`` 共用 ``media.uploads.store_upload``（Pillow
    验真、2MB 上限、sha256 内容寻址、MERCHANT 桶）；区别在于：
    * 鉴权是**买家会话**（不是员工会话）；
    * purpose 固定为 ``shop_application``，其它用途一律拒绝；
    * 证件照属敏感信息：仅 dev 演示用途，接口只允许本人提交、
      平台审核读取，不做额外加密（代码口径与需求一致）。
    """

    ALLOWED_PURPOSES = {"shop_application"}

    def post(self, request):
        _require_buyer(request)
        purpose = str((request.data or {}).get("purpose") or "").strip().lower()
        if purpose not in self.ALLOWED_PURPOSES:
            raise BuyerApiError(
                business_code="UPLOAD_PURPOSE_INVALID",
                message="上传用途不正确，该接口仅用于开店申请图片。",
                status_code=400,
            )
        file = request.FILES.get("file")
        if file is None:
            raise BuyerApiError(
                business_code="FILE_REQUIRED",
                message="请选择要上传的图片。",
                status_code=400,
            )
        try:
            result = store_upload(file, purpose=purpose)
        except UploadError as exc:
            raise BuyerApiError(
                business_code=exc.code, message=exc.message, status_code=exc.status_code
            ) from exc
        return Response({"media": result}, status=201)


def _merchant_web_url(request) -> str:
    """商家端跳转地址：配置优先，否则当前请求主机 + MERCHANT_WEB_PORT。

    浏览器直连时 ``Origin`` 是用户实际访问的 host（例如 localhost:3000），
    比 ``request.get_host()`` 更可靠：Nuxt 的 devProxy 会把 Host 改写成
    127.0.0.1:8000，照抄会让 cookie 落在错误的主机上（cookie 按 host
    共享、不按端口）。生产环境必须配置 ``MERCHANT_WEB_URL``。
    """

    configured = (getattr(settings, "MERCHANT_WEB_URL", "") or "").strip().rstrip("/")
    if configured:
        return f"{configured}/"

    host = ""
    origin = (request.META.get("HTTP_ORIGIN") or "").strip()
    if origin:
        host = urlparse(origin).hostname or ""
    if not host:
        host = urlparse(f"//{request.get_host()}").hostname or ""
    if not host:
        host = "localhost"

    scheme = "https" if request.is_secure() else "http"
    host_for_url = f"[{host}]" if ":" in host else host
    port = int(getattr(settings, "MERCHANT_WEB_PORT", 5174))
    return f"{scheme}://{host_for_url}:{port}/"


class BuyerMerchantConsoleSessionView(BuyerCsrfAPIView):
    """POST：为当前买家自己的 APPROVED 店铺签发商家端员工会话。

    与商家端登录后拿到的 cookie 完全一致（同一个 staff 账号、同一个会话
    字段），所以浏览器随后打开 merchant-web 时已是登录态。

    安全约束（不得放宽）：
    * 身份只来自买家会话 ``request.buyer_account``；接口**不接受任何
      staff / merchant 参数**，否则买家可以指定别人的 staff id 冒用店铺；
    * 只查该买家自己的 MerchantApplication（OneToOne），且必须 APPROVED；
    * StaffAccount 只按 approve 时落库的买家邮箱定位；membership 必须属于
      该申请回填的 merchant 且 ACTIVE。
    """

    def post(self, request):
        buyer = _require_buyer(request)
        application = (
            MerchantApplication.objects.select_related("merchant").filter(buyer=buyer).first()
        )
        if application is None or application.status != MerchantApplication.Status.APPROVED:
            raise BuyerApiError(
                business_code="APPLICATION_NOT_APPROVED",
                message="您还没有审核通过的店铺申请，暂时无法进入商家中心。",
                status_code=400,
            )

        merchant = application.merchant
        email = (buyer.email or "").strip()
        staff = StaffAccount.objects.filter(email__iexact=email).first() if email else None
        if merchant is None or staff is None:
            raise BuyerApiError(
                business_code="MERCHANT_ACCOUNT_MISSING",
                message="商家端账号尚未开通，请联系平台客服处理。",
                status_code=409,
            )
        if staff.status != StaffAccount.Status.ACTIVE:
            raise BuyerApiError(
                business_code="MERCHANT_ACCOUNT_DISABLED",
                message="商家端账号已被停用，请联系平台客服处理。",
                status_code=409,
            )

        membership = (
            MerchantMembership.objects.select_related("role")
            .filter(
                merchant=merchant,
                staff=staff,
                status=MerchantMembership.Status.ACTIVE,
            )
            .first()
        )
        if membership is None:
            raise BuyerApiError(
                business_code="MERCHANT_MEMBERSHIP_MISSING",
                message="商家端账号未绑定当前店铺，请联系平台客服处理。",
                status_code=409,
            )

        token, _session = create_staff_session(
            staff=staff,
            ip_address=request.META.get("REMOTE_ADDR"),
            user_agent=request.headers.get("User-Agent", ""),
            totp_verified=True,
        )
        response = Response(
            {
                "url": _merchant_web_url(request),
                "staff": {
                    "id": str(staff.public_id),
                    "email": staff.email,
                    "display_name": staff.display_name,
                },
                "merchant": {
                    "id": str(merchant.public_id),
                    "display_name": merchant.display_name,
                    "onboarding_status": merchant.onboarding_status,
                },
                "expires_in": int(settings.STAFF_SESSION_MAX_AGE_SECONDS),
            }
        )
        # 商家端在独立子域（merchant.joyfumi.com）：正式域名下把 cookie 域放宽到
        # .joyfumi.com，子域才能收到；本地（127.0.0.1/localhost）保持 host-only。
        # 管理端用的是另一个 cookie 键（STAFF_ADMIN_SESSION_COOKIE_NAME），
        # 所以这里写 cookie 不会再覆盖管理端登录态。
        host = request.get_host().split(":")[0].lower()
        cookie_domain = ".joyfumi.com" if host.endswith("joyfumi.com") else None
        set_staff_session_cookie(response, token, domain=cookie_domain)
        return response


APPLICATION_STATUS_FILTERS = {"PENDING", "APPROVED", "REJECTED"}

def _filtered_applications(request):
    queryset = MerchantApplication.objects.select_related(
        "buyer", "merchant", "reviewed_by"
    ).order_by("-submitted_at", "-pk")
    status = (request.query_params.get("status") or "").strip().upper()
    if status and status != "ALL" and status in APPLICATION_STATUS_FILTERS:
        queryset = queryset.filter(status=status)
    return queryset


class AdminMerchantApplicationsView(OpsAPIView):
    """入驻申请列表（按提交时间倒序），meta 里带待审计数。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["merchants.manage"]
    view_permissions = ["merchants.view"]

    def get(self, request):
        rows, meta = paginate(_filtered_applications(request), request)
        meta["pending_count"] = MerchantApplication.objects.filter(
            status=MerchantApplication.Status.PENDING
        ).count()
        items = []
        for application in rows:
            payload = _application_payload(application)
            payload["buyer_email"] = application.buyer.email
            payload["reviewed_by"] = (
                application.reviewed_by.display_name if application.reviewed_by else ""
            )
            items.append(payload)
        return Response({"items": items, **meta})


class AdminMerchantApplicationActionsView(OpsAPIView):
    """approve（开店 + 打通商家端账号）与 reject（记录原因）。"""

    permission_classes = [StaffRbacPermission]
    required_permissions = ["merchants.manage"]
    view_permissions = ["merchants.view"]

    def _get_locked_application(self, application_id: str) -> MerchantApplication:
        try:
            application = (
                MerchantApplication.objects.select_for_update()
                .select_related("buyer")
                .get(pk=application_id)
            )
        except (MerchantApplication.DoesNotExist, ValueError, TypeError) as exc:
            raise StaffApiError(
                business_code="APPLICATION_NOT_FOUND",
                message="入驻申请不存在。",
                status_code=404,
            ) from exc
        return application

    def post(self, request):
        payload = request.data or {}
        action = (str(payload.get("action") or "")).strip().lower()
        if action not in {"approve", "reject"}:
            raise StaffApiError(
                business_code="ACTION_UNSUPPORTED",
                message="不支持的操作。",
                status_code=400,
            )

        application_id = payload.get("application_id")
        with transaction.atomic():
            application = self._get_locked_application(application_id)
            if application.status == MerchantApplication.Status.APPROVED:
                raise StaffApiError(
                    business_code="APPLICATION_ALREADY_REVIEWED",
                    message="该申请已审核通过，不能重复操作。",
                    status_code=409,
                )

            if action == "approve":
                result = self._approve(request, application, payload)
            else:
                reason = str(payload.get("reason") or "").strip()
                if not reason:
                    raise StaffApiError(
                        business_code="FIELD_REQUIRED",
                        message="请填写驳回原因。",
                        status_code=400,
                    )
                application.status = MerchantApplication.Status.REJECTED
                application.reject_reason = reason
                application.reviewed_by = request.staff_account
                application.reviewed_at = timezone.now()
                application.save(
                    update_fields=[
                        "status",
                        "reject_reason",
                        "reviewed_by",
                        "reviewed_at",
                        "updated_at",
                    ]
                )
                record_audit(
                    request=request,
                    actor=request.staff_account,
                    action="MERCHANT_APPLICATION_REJECTED",
                    target_type="merchant_application",
                    target_id=str(application.pk),
                    reason=reason,
                    before_state={"status": MerchantApplication.Status.PENDING},
                    after_state={"status": MerchantApplication.Status.REJECTED},
                )
                result = {"application": _application_payload(application)}

        return Response(result)

    def _approve(self, request, application: MerchantApplication, payload: dict) -> dict:
        buyer = application.buyer
        email = (buyer.email or "").strip()
        if not email:
            raise StaffApiError(
                business_code="BUYER_EMAIL_REQUIRED",
                message="该买家未绑定邮箱，无法打通商家端账号。",
                status_code=400,
            )

        require_deposit = bool(payload.get("require_deposit"))
        deposit_amount = None
        if require_deposit:
            raw_amount = payload.get("deposit_amount")
            if raw_amount in (None, ""):
                raise StaffApiError(
                    business_code="DEPOSIT_AMOUNT_REQUIRED",
                    message="启用保证金时必须填写大于 0 的应缴金额。",
                    status_code=400,
                )
            deposit_amount = parse_amount(raw_amount, field="应缴保证金")
        ban_after_days = parse_positive_int(
            payload.get("ban_after_days", 4), field="未发货封店天数"
        )

        # ① 开店（含推荐返佣绑定 + 申请店铺logo 回填 Merchant.avatar_url）；
        # ②打通商家端账号；③店主 membership；④既有入驻状态机；
        # ⑤回填申请单——全部在一个事务里。
        merchant = create_merchant(
            display_name=application.shop_name,
            legal_name=application.legal_name,
            avatar_url=application.logo_image_url,
            referrer_code=application.referrer_code,
            ban_after_days=ban_after_days,
        )

        staff = StaffAccount.objects.filter(email__iexact=email).first()
        staff_created = staff is None
        if staff is None:
            # 两表同套 Django hasher：直接复制哈希串，买家密码即可登录商家端。
            staff = StaffAccount(
                email=email,
                display_name=application.shop_name,
                status=StaffAccount.Status.ACTIVE,
                password=buyer.password,
            )
            staff.save()
        # 已存在则不改其密码，只补 membership。

        # 一账号一店（2026-11-22）：同一 staff 已有任意 membership 时拒绝开通第二家店。
        # 放在 get_or_create 之前是为了给出业务 409，而不是撞唯一约束变成 500。
        if MerchantMembership.objects.filter(staff=staff).exists():
            raise StaffApiError(
                business_code="ACCOUNT_ALREADY_BOUND_SHOP",
                message="该邮箱已绑定其他店铺，一个账号只能绑定一家店铺。",
                status_code=409,
            )

        owner_role = MerchantRole.objects.get(code="merchant_owner")
        try:
            # 保存点：并发下唯一约束仍可能被撞到，转成同一个业务 409 而不是 500。
            with transaction.atomic():
                MerchantMembership.objects.get_or_create(
                    merchant=merchant,
                    staff=staff,
                    defaults={
                        "role": owner_role,
                        "status": MerchantMembership.Status.ACTIVE,
                        "joined_at": timezone.now(),
                    },
                )
        except IntegrityError as exc:
            raise StaffApiError(
                business_code="ACCOUNT_ALREADY_BOUND_SHOP",
                message="该邮箱已绑定其他店铺，一个账号只能绑定一家店铺。",
                status_code=409,
            ) from exc

        merchant = review_admission(
            merchant,
            approved=True,
            require_deposit=require_deposit,
            deposit_required=deposit_amount,
            ban_after_days=ban_after_days,
        )

        application.status = MerchantApplication.Status.APPROVED
        application.reject_reason = ""
        application.reviewed_by = request.staff_account
        application.reviewed_at = timezone.now()
        application.merchant = merchant
        application.save(
            update_fields=[
                "status",
                "reject_reason",
                "reviewed_by",
                "reviewed_at",
                "merchant",
                "updated_at",
            ]
        )

        record_audit(
            request=request,
            actor=request.staff_account,
            action="MERCHANT_APPLICATION_APPROVED",
            target_type="merchant_application",
            target_id=str(application.pk),
            reason="",
            before_state={"status": MerchantApplication.Status.PENDING},
            after_state={
                "status": MerchantApplication.Status.APPROVED,
                "merchant_id": str(merchant.public_id),
                "staff_account_created": staff_created,
            },
        )
        return {
            "application": _application_payload(application),
            "staff_account_created": staff_created,
        }
