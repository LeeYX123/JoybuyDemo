"""买家端三方登录（Google / Facebook）：OAuth 2.0 授权码 + PKCE。

设计约束见 ``docs/16-third-party-login.md``：

- 回调必须落在**商城同域**（买家会话 cookie 是 host-only），由
  ``settings.OAUTH_REDIRECT_BASE_URL`` 决定，注册到两家控制台的 URI 必须逐字一致；
- 账号唯一键是 ``(provider, subject)``。Facebook 可能不返回邮箱，这类账号
  ``email`` 为 NULL，只靠 identity 表认人（见 ``BuyerAccount.identity_bound``）；
- 日志、异常文案里**不出现** code / access_token / client_secret —— 出网 URL 的
  query 在报错前就被截断，profile 请求带 token 时也不会进 message；
- 出网用 stdlib ``urllib``，与 ``merchant_ops.crisp_mirror`` 的做法一致，不引第三方依赖。
"""

import base64
import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from accounts_buyers.models import BuyerAccount, BuyerIdentity
from accounts_buyers.services import ensure_display_name

logger = logging.getLogger(__name__)

STATE_CACHE_PREFIX = "buyer-oauth-state:"
DEFAULT_NEXT_PATH = "/account"


class OAuthError(Exception):
    """可预期的登录失败；``code`` 会以 ``?oauth_error=<code>`` 回给商城前端。

    不要把 provider 的原始错误体塞进 message：里面可能带 code / token。
    """

    def __init__(self, code: str, message: str = ""):
        self.code = code
        self.message = message or code
        super().__init__(self.message)


@dataclass(frozen=True)
class ProviderConfig:
    key: str
    auth_provider: str  # 落库值，与 BuyerAccount.AuthProvider 一致
    authorize_url: str
    token_url: str
    profile_url: str
    scope: str
    client_id: str
    client_secret: str
    # Google 支持 PKCE；Facebook 的 token 端点对未知参数容错差，只用 state + secret。
    use_pkce: bool = False
    prompt: str = ""


@dataclass(frozen=True)
class Profile:
    subject: str
    email: str | None
    email_verified: bool
    name: str = ""
    avatar_url: str = ""


def _google_config() -> ProviderConfig | None:
    client_id = settings.GOOGLE_OAUTH_CLIENT_ID
    client_secret = settings.GOOGLE_OAUTH_CLIENT_SECRET
    if not (client_id and client_secret):
        return None
    return ProviderConfig(
        key="google",
        auth_provider=BuyerAccount.AuthProvider.GOOGLE,
        authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
        token_url="https://oauth2.googleapis.com/token",
        profile_url="https://openidconnect.googleapis.com/v1/userinfo",
        scope="openid email profile",
        client_id=client_id,
        client_secret=client_secret,
        use_pkce=True,
        prompt="select_account",
    )


def _facebook_config() -> ProviderConfig | None:
    app_id = settings.FACEBOOK_OAUTH_APP_ID
    app_secret = settings.FACEBOOK_OAUTH_APP_SECRET
    if not (app_id and app_secret):
        return None
    version = settings.FACEBOOK_GRAPH_VERSION
    return ProviderConfig(
        key="facebook",
        auth_provider=BuyerAccount.AuthProvider.FACEBOOK,
        authorize_url=f"https://www.facebook.com/{version}/dialog/oauth",
        token_url=f"https://graph.facebook.com/{version}/oauth/access_token",
        profile_url=f"https://graph.facebook.com/{version}/me",
        # Facebook 的 scope 用逗号分隔（Google 用空格），别写反。
        scope="email,public_profile",
        client_id=app_id,
        client_secret=app_secret,
        use_pkce=False,
    )


PROVIDER_BUILDERS = {"google": _google_config, "facebook": _facebook_config}


def get_provider(provider_key: str) -> ProviderConfig:
    builder = PROVIDER_BUILDERS.get((provider_key or "").strip().lower())
    config = builder() if builder else None
    if config is None:
        # 渠道不存在 / 凭据未配置，一律按「该渠道不可用」处理，不泄露配置细节。
        raise OAuthError("provider_unavailable")
    return config


def providers_payload() -> list[dict]:
    """给前端渲染按钮用。

    返回**全部支持的渠道**并带 ``enabled`` 标记：登录页要把 Google / Facebook 并排
    摆出来（用户要求，不藏在「View more options」后面），凭据未配置的渠道由前端
    渲染成同款按钮、点击给「暂不可用」提示，而不是整块消失。
    """

    providers = []
    for key in PROVIDER_BUILDERS:
        providers.append(
            {
                "provider": key,
                "enabled": PROVIDER_BUILDERS[key]() is not None,
                "start_url": f"/api/v1/auth/buyer/oauth/{key}/start",
            }
        )
    return providers


def callback_url(provider_key: str) -> str:
    return f"{settings.OAUTH_REDIRECT_BASE_URL}/api/v1/auth/buyer/oauth/{provider_key}/callback"


def sanitize_next(value: str | None) -> str:
    """登录成功后回跳：只收站内相对路径（与 AuthForm 的 next 白名单同规则）。"""

    path = (value or "").strip()
    if not path.startswith("/") or path.startswith("//") or "\\" in path:
        return DEFAULT_NEXT_PATH
    if any(ch in path for ch in ("\r", "\n", "\t")):
        return DEFAULT_NEXT_PATH
    return path[:512]


# ---------------------------------------------------------------------------
# state + PKCE
# ---------------------------------------------------------------------------


def _code_verifier() -> str:
    return secrets.token_urlsafe(64)


def _code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def build_authorize_url(config: ProviderConfig, *, next_path: str | None) -> str:
    state = secrets.token_urlsafe(24)
    verifier = _code_verifier()
    cache.set(
        f"{STATE_CACHE_PREFIX}{state}",
        {
            "provider": config.key,
            "next": sanitize_next(next_path),
            "verifier": verifier,
        },
        timeout=settings.OAUTH_STATE_TTL_SECONDS,
    )

    params = {
        "client_id": config.client_id,
        "redirect_uri": callback_url(config.key),
        "response_type": "code",
        "scope": config.scope,
        "state": state,
    }
    if config.use_pkce:
        params["code_challenge"] = _code_challenge(verifier)
        params["code_challenge_method"] = "S256"
    if config.prompt:
        params["prompt"] = config.prompt
    # safe="," 让 Facebook 的 scope=email,public_profile 保持原样（%2C 也能被接受，
    # 但原样更贴近官方示例，排障时肉眼可读）。
    return f"{config.authorize_url}?{urllib.parse.urlencode(params, safe=',')}"


def consume_state(state: str | None, provider_key: str) -> dict:
    """取出并立即删除 state；不存在 / 过期 / 渠道不符都按无效处理。"""

    value = (state or "").strip()
    if not value:
        raise OAuthError("state_invalid")
    key = f"{STATE_CACHE_PREFIX}{value}"
    try:
        payload = cache.get(key)
    except Exception as exc:  # cache 不可用时降级为无效 state，不抛 500
        raise OAuthError("state_invalid") from exc
    if not isinstance(payload, dict):
        raise OAuthError("state_invalid")
    try:
        cache.delete(key)
    except Exception:
        logger.warning("buyer_oauth_state_delete_failed")
    if payload.get("provider") != provider_key:
        # 拿 A 渠道签发的 state 走 B 渠道回调：一次性凭证必须作废。
        raise OAuthError("state_invalid")
    return payload


# ---------------------------------------------------------------------------
# 出网（抽成单一函数便于测试 mock：测试绝不真连 Google / Facebook）
# ---------------------------------------------------------------------------


def _http_json(url: str, *, data: dict | None = None, headers: dict | None = None) -> dict:
    body = None if data is None else urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST" if body else "GET")
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    for name, value in (headers or {}).items():
        request.add_header(name, value)

    # 报错只带「方法 + 去 query 的 URL」：profile 请求的 query 里有 access_token。
    safe_target = f"{request.get_method()} {url.split('?', 1)[0]}"
    try:
        with urllib.request.urlopen(
            request, timeout=settings.OAUTH_HTTP_TIMEOUT_SECONDS
        ) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        raise OAuthError("provider_error", f"{safe_target} -> HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OAuthError("provider_unavailable", f"{safe_target} -> network error") from exc

    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise OAuthError("provider_error", f"{safe_target} -> invalid JSON") from exc
    return payload if isinstance(payload, dict) else {}


def exchange_code(config: ProviderConfig, *, code: str, verifier: str) -> str:
    data = {
        "client_id": config.client_id,
        "client_secret": config.client_secret,
        "code": code,
        "redirect_uri": callback_url(config.key),
        "grant_type": "authorization_code",
    }
    if config.use_pkce and verifier:
        data["code_verifier"] = verifier
    payload = _http_json(config.token_url, data=data)
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise OAuthError("provider_error", "token response missing access_token")
    return token


def fetch_profile(config: ProviderConfig, access_token: str) -> Profile:
    if config.key == "google":
        payload = _http_json(
            config.profile_url, headers={"Authorization": f"Bearer {access_token}"}
        )
        return Profile(
            subject=str(payload.get("sub") or ""),
            email=(payload.get("email") or "").strip().lower() or None,
            email_verified=bool(payload.get("email_verified")),
            name=(payload.get("name") or "").strip()[:120],
            avatar_url=(payload.get("picture") or "")[:512],
        )

    query = urllib.parse.urlencode(
        {"fields": "id,name,email,picture.type(large)", "access_token": access_token}
    )
    payload = _http_json(f"{config.profile_url}?{query}")
    picture = ((payload.get("picture") or {}).get("data") or {}).get("url") or ""
    return Profile(
        subject=str(payload.get("id") or ""),
        email=(payload.get("email") or "").strip().lower() or None,
        # Graph 不提供任何验证标记，且邮箱可被用户随意改 —— 一律视为未验证。
        email_verified=False,
        name=(payload.get("name") or "").strip()[:120],
        avatar_url=picture[:512],
    )


# ---------------------------------------------------------------------------
# 认人：查 identity → 按已验证邮箱合并（仅 Google）→ 否则建号
# ---------------------------------------------------------------------------


def resolve_account(config: ProviderConfig, profile: Profile) -> BuyerAccount:
    if not profile.subject:
        raise OAuthError("provider_error", "profile missing subject")

    identity = (
        BuyerIdentity.objects.select_related("account")
        .filter(provider=config.auth_provider, subject=profile.subject)
        .first()
    )
    if identity is not None:
        account = identity.account
        if account.status != BuyerAccount.Status.ACTIVE:
            raise OAuthError("disabled")
        now = timezone.now()
        BuyerAccount.objects.filter(pk=account.pk).update(last_login_at=now, updated_at=now)
        BuyerIdentity.objects.filter(pk=identity.pk).update(last_login_at=now)
        account.last_login_at = now
        return account

    existing = BuyerAccount.objects.filter(email=profile.email).first() if profile.email else None
    if existing is not None:
        if not (
            config.auth_provider == BuyerAccount.AuthProvider.GOOGLE and profile.email_verified
        ):
            # Facebook 邮箱不可信；Google 未验证邮箱同样不可信 → 既不合并，也不冒用该邮箱建号
            # （email 唯一，冒用必然 IntegrityError，还会把账号绑到别人的邮箱上）。
            raise OAuthError("email_exists")
        if existing.status != BuyerAccount.Status.ACTIVE:
            raise OAuthError("disabled")
        _link_identity(existing, config, profile)
        logger.info(
            "buyer_identity_linked provider=%s account=%s",
            config.auth_provider,
            existing.public_id,
        )
        return existing

    account = _create_account(config, profile)
    logger.info(
        "buyer_identity_created provider=%s account=%s email_bound=%s",
        config.auth_provider,
        account.public_id,
        bool(profile.email),
    )
    return account


def _link_identity(account: BuyerAccount, config: ProviderConfig, profile: Profile) -> None:
    now = timezone.now()
    try:
        with transaction.atomic():
            BuyerIdentity.objects.create(
                account=account,
                provider=config.auth_provider,
                subject=profile.subject,
                email_snapshot=profile.email,
                display_name=profile.name,
                avatar_url=profile.avatar_url,
                last_login_at=now,
            )
            BuyerAccount.objects.filter(pk=account.pk).update(last_login_at=now, updated_at=now)
    except IntegrityError:
        # 并发下另一个请求已绑定同一 subject：结果等价，不报错。
        logger.info("buyer_identity_link_race provider=%s", config.auth_provider)
    account.last_login_at = now


def _create_account(config: ProviderConfig, profile: Profile) -> BuyerAccount:
    now = timezone.now()
    try:
        with transaction.atomic():
            account = BuyerAccount(
                email=profile.email,
                phone_e164=None,
                # 无邮箱账号靠这条标记满足 buyer_account_has_identifier 约束。
                identity_bound=True,
                auth_provider=config.auth_provider,
                last_login_at=now,
                email_verified_at=(now if profile.email and profile.email_verified else None),
                # 批次 CA：三方登录首次建号同样默认不进购买白名单。
                purchase_whitelisted=False,
            )
            account.password = make_password(None)  # unusable：OAuth 账号不能走密码登录
            account.save()
            BuyerIdentity.objects.create(
                account=account,
                provider=config.auth_provider,
                subject=profile.subject,
                email_snapshot=profile.email,
                display_name=profile.name,
                avatar_url=profile.avatar_url,
                last_login_at=now,
            )
    except IntegrityError as exc:
        # 并发双击：另一个请求已建好 identity → 直接复用；否则是邮箱被占用。
        identity = (
            BuyerIdentity.objects.select_related("account")
            .filter(provider=config.auth_provider, subject=profile.subject)
            .first()
        )
        if identity is not None:
            return identity.account
        raise OAuthError("email_exists") from exc

    # 展示名走需求 13.5-6 的规则（user4323txlb）；无邮箱账号也只有这条路。
    ensure_display_name(account)
    return account


# ---------------------------------------------------------------------------
# 视图用的两步封装
# ---------------------------------------------------------------------------


def start_login(provider_key: str, next_path: str | None) -> str:
    return build_authorize_url(get_provider(provider_key), next_path=next_path)


def complete_login(
    provider_key: str, *, code: str | None, state: str | None
) -> tuple[BuyerAccount, str]:
    """校验 state → 换 token → 取 profile → 认人；返回 (账号, 回跳路径)。"""

    config = get_provider(provider_key)
    payload = consume_state(state, config.key)
    if not code:
        # 用户点了「取消」：state 已消费，按拒绝授权处理。
        raise OAuthError("denied")
    access_token = exchange_code(config, code=code, verifier=payload.get("verifier") or "")
    profile = fetch_profile(config, access_token)
    account = resolve_account(config, profile)
    return account, sanitize_next(payload.get("next"))
