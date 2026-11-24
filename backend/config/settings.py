import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
REPOSITORY_ROOT = BASE_DIR.parent
load_dotenv(REPOSITORY_ROOT / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ImproperlyConfigured(f"{name} must be a boolean value")


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
DEBUG = env_bool("DEBUG", APP_ENV == "development")

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "joybuy-insecure-development-only")
if APP_ENV not in {"development", "test"} and (
    not SECRET_KEY or SECRET_KEY.startswith("CHANGE_ME") or "insecure" in SECRET_KEY
):
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set to a real secret")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    # 3000 商城端 / 5173 平台管理端 / 5174 商家端（三个前端都要能发写请求）
    # localhost 与 127.0.0.1 是不同的 Origin，两个变体都必须配置，
    # 否则用 localhost 访问时所有写请求都会被 CSRF 中间件 403。
    # m.localhost:5174 是商家端手机壳主机名（merchant-web 双壳方案），写请求同样要放行。
    "http://127.0.0.1:3000,http://127.0.0.1:5173,http://127.0.0.1:5174,"
    "http://localhost:3000,http://localhost:5173,http://localhost:5174,"
    "http://m.localhost:5174",
)

# 局域网访问（手机 / 同网段电脑）：浏览器直连 nuxt/vite 时 Origin 是本机局域网 IP，
# 例如 http://192.168.1.165:3000，不在上面的白名单里就会让所有写请求 403。
# DEBUG 下自动把本机全部 IPv4 的三个前端端口加进去，换网络/换 IP 都不用改配置。
# 生产不启用该逻辑（生产走真实域名，由 DJANGO_CSRF_TRUSTED_ORIGINS 显式配置）。
if DEBUG:
    import socket as _socket

    def _local_ipv4_addresses() -> set[str]:
        addresses: set[str] = set()
        # UDP connect 不真正发包，但能让系统给出默认出口网卡地址。
        try:
            probe = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
            try:
                probe.connect(("8.8.8.8", 80))
                addresses.add(probe.getsockname()[0])
            finally:
                probe.close()
        except OSError:
            pass
        try:
            for info in _socket.getaddrinfo(_socket.gethostname(), None, _socket.AF_INET):
                addresses.add(info[4][0])
        except OSError:
            pass
        return addresses

    for _ip in _local_ipv4_addresses():
        if _ip.startswith("127."):
            continue
        for _port in (3000, 5173, 5174):
            _origin = f"http://{_ip}:{_port}"
            if _origin not in CSRF_TRUSTED_ORIGINS:
                CSRF_TRUSTED_ORIGINS.append(_origin)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "common.apps.CommonConfig",
    "accounts_buyers.apps.AccountsBuyersConfig",
    "accounts_staff.apps.AccountsStaffConfig",
    "audit.apps.AuditConfig",
    "merchants.apps.MerchantsConfig",
    "merchant_ops.apps.MerchantOpsConfig",
    "catalog.apps.CatalogConfig",
    "offers.apps.OffersConfig",
    "media.apps.MediaConfig",
    "reviews.apps.ReviewsConfig",
    "crawler_control.apps.CrawlerControlConfig",
    "content.apps.ContentConfig",
    "cart.apps.CartConfig",
    "checkout.apps.CheckoutConfig",
    "orders.apps.OrdersConfig",
    "notifications.apps.NotificationsConfig",
]

MIDDLEWARE = [
    "common.middleware.RequestIdMiddleware",
    "common.client_timezone.ClientTimezoneMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "accounts_buyers.middleware.BuyerSessionMiddleware",
    "accounts_staff.middleware.StaffSessionMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

database_engine = os.getenv("DJANGO_DATABASE_ENGINE", "mysql").strip().lower()
if database_engine == "sqlite":
    sqlite_name = os.getenv("DJANGO_SQLITE_PATH", str(REPOSITORY_ROOT / "var" / "joybuy.sqlite3"))
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": sqlite_name,
        }
    }
elif database_engine == "mysql":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.mysql",
            "NAME": os.getenv("MYSQL_DATABASE", "joybuy"),
            "USER": os.getenv("MYSQL_USER", "joybuy"),
            "PASSWORD": os.getenv("MYSQL_PASSWORD", "joybuy_dev_only"),
            "HOST": os.getenv("MYSQL_HOST", "127.0.0.1"),
            "PORT": os.getenv("MYSQL_PORT", "33060"),
            "CONN_MAX_AGE": 60,
            "OPTIONS": {
                "charset": "utf8mb4",
                "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
            },
            "TEST": {"CHARSET": "utf8mb4"},
        }
    }
else:
    raise ImproperlyConfigured("DJANGO_DATABASE_ENGINE must be mysql or sqlite")

cache_backend = os.getenv("DJANGO_CACHE_BACKEND", "redis").strip().lower()
if cache_backend == "locmem":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "joybuy-local-test-cache",
        }
    }
elif cache_backend == "redis":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.getenv("REDIS_URL", "redis://127.0.0.1:63790/0"),
            "KEY_PREFIX": "joybuy",
            "OPTIONS": {
                "socket_connect_timeout": 2,
                "socket_timeout": 2,
            },
        }
    }
else:
    raise ImproperlyConfigured("DJANGO_CACHE_BACKEND must be redis or locmem")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = os.getenv("APP_TIME_ZONE", "Europe/London")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = REPOSITORY_ROOT / "var" / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = REPOSITORY_ROOT / "var" / "media"

# Media storage backend: "local" writes under MEDIA_ROOT (historical default),
# "s3" uploads media objects to MEDIA_S3_BUCKET under MEDIA_S3_PREFIX and keeps
# no local copy (crawler imports and uploads go straight to the bucket).
MEDIA_BACKEND = os.getenv("MEDIA_BACKEND", "local").strip().lower()
MEDIA_S3_BUCKET = os.getenv("MEDIA_S3_BUCKET", "joybuy-media-fra")
MEDIA_S3_PREFIX = os.getenv("MEDIA_S3_PREFIX", "media/")
MEDIA_S3_REGION = os.getenv("MEDIA_S3_REGION", "eu-central-1")
# S3-compatible endpoint (e.g. https://fra1.digitaloceanspaces.com for
# DigitalOcean Spaces). Empty = AWS virtual-host style URLs and the default
# boto3 endpoint; non-empty = path-style URLs against this endpoint.
MEDIA_S3_ENDPOINT = os.getenv("MEDIA_S3_ENDPOINT", "").strip().rstrip("/")
if MEDIA_BACKEND not in {"local", "s3"}:
    raise ImproperlyConfigured("MEDIA_BACKEND must be local or s3")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_NAME = "joybuy_django_session"
SESSION_COOKIE_HTTPONLY = True
# Secure 标志默认跟随环境（production/test 之外强制 Secure）。当前生产暂走纯 http
# （无 TLS），浏览器会拒存带 Secure 的 cookie 导致登录/CSRF 全部失效，允许用 env
# 显式关闭作临时降级；配置 TLS 当天删除 .env 里的覆盖行即回滚到默认强制。
SESSION_COOKIE_SECURE = env_bool(
    "DJANGO_SESSION_COOKIE_SECURE", APP_ENV not in {"development", "test"}
)
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = env_bool("DJANGO_CSRF_COOKIE_SECURE", APP_ENV not in {"development", "test"})
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# HMAC key for source reviewer fingerprints (WP-12); never store reversible ids.
SOURCE_FINGERPRINT_HMAC_KEY = os.getenv("SOURCE_FINGERPRINT_HMAC_KEY", SECRET_KEY)

# Crawler control (WP-13): encrypted account sessions and raw response retention.
CRAWL_SESSION_ENCRYPTION_KEY = os.getenv("CRAWL_SESSION_ENCRYPTION_KEY", SECRET_KEY)
CRAWL_RAW_RETENTION_DAYS = int(os.getenv("CRAWL_RAW_RETENTION_DAYS", "30"))
CRAWL_RAW_ROOT = Path(os.getenv("CRAWL_RAW_ROOT") or str(REPOSITORY_ROOT / "var" / "raw"))

BUYER_SESSION_COOKIE_NAME = os.getenv("BUYER_SESSION_COOKIE_NAME", "joybuy_buyer_session")
BUYER_SESSION_MAX_AGE_SECONDS = int(os.getenv("BUYER_SESSION_MAX_AGE_SECONDS", "1209600"))
BUYER_SESSION_HMAC_KEY = os.getenv("BUYER_SESSION_HMAC_KEY", SECRET_KEY)
VERIFICATION_CODE_HMAC_KEY = os.getenv("VERIFICATION_CODE_HMAC_KEY", SECRET_KEY)
VERIFICATION_CODE_TEST_MODE = env_bool(
    "VERIFICATION_CODE_TEST_MODE", APP_ENV in {"development", "test"}
)
VERIFICATION_CODE_TTL_SECONDS = int(os.getenv("VERIFICATION_CODE_TTL_SECONDS", "600"))
VERIFICATION_CODE_MAX_ATTEMPTS = int(os.getenv("VERIFICATION_CODE_MAX_ATTEMPTS", "5"))
VERIFICATION_CODE_SEND_LIMIT = int(os.getenv("VERIFICATION_CODE_SEND_LIMIT", "3"))
VERIFICATION_CODE_SEND_WINDOW_SECONDS = int(
    os.getenv("VERIFICATION_CODE_SEND_WINDOW_SECONDS", "3600")
)
BUYER_LOGIN_FAILURE_LIMIT = int(os.getenv("BUYER_LOGIN_FAILURE_LIMIT", "5"))
BUYER_LOGIN_FAILURE_WINDOW_SECONDS = int(os.getenv("BUYER_LOGIN_FAILURE_WINDOW_SECONDS", "900"))

STAFF_SESSION_COOKIE_NAME = os.getenv("STAFF_SESSION_COOKIE_NAME", "joybuy_staff_session")
# 员工会话要同时服务平台端（/api/v1/admin/*）与商家端（/api/v1/merchant/*），
# 所以作用域是整个 /api/v1/。历史值曾是 "/api/v1/admin/"，见 LEGACY 常量。
STAFF_SESSION_COOKIE_PATH = os.getenv("STAFF_SESSION_COOKIE_PATH", "/api/v1/")
STAFF_SESSION_COOKIE_LEGACY_PATHS = ("/api/v1/admin/",)
STAFF_SESSION_MAX_AGE_SECONDS = int(os.getenv("STAFF_SESSION_MAX_AGE_SECONDS", "28800"))
STAFF_SESSION_HMAC_KEY = os.getenv("STAFF_SESSION_HMAC_KEY", SECRET_KEY)
STAFF_TOTP_ENCRYPTION_KEY = os.getenv("STAFF_TOTP_ENCRYPTION_KEY", SECRET_KEY)
STAFF_TOTP_PERIOD_SECONDS = int(os.getenv("STAFF_TOTP_PERIOD_SECONDS", "30"))
STAFF_TOTP_ALLOWED_DRIFT_STEPS = int(os.getenv("STAFF_TOTP_ALLOWED_DRIFT_STEPS", "1"))
STAFF_LOGIN_FAILURE_LIMIT = int(os.getenv("STAFF_LOGIN_FAILURE_LIMIT", "5"))
STAFF_LOGIN_FAILURE_WINDOW_SECONDS = int(os.getenv("STAFF_LOGIN_FAILURE_WINDOW_SECONDS", "900"))

# 购物端「进入商家中心」的跳转地址（merchant-web 独立应用）。
# 空 = 用当前请求的 Origin 主机 + MERCHANT_WEB_PORT（开发默认 5174），
# 生产必须显式配置，避免把 localhost 地址带回给浏览器。
MERCHANT_WEB_URL = os.getenv("MERCHANT_WEB_URL", "").strip().rstrip("/")
MERCHANT_WEB_PORT = int(os.getenv("MERCHANT_WEB_PORT", "5174"))

# 购物端（storefront）地址：商家端「切换去商城」的 handoff 落地页由后端拼
# （/auth/merchant-handoff?token=...），前端不再自己拼 host。开发默认
# localhost:3000 —— storefront dev server 只绑 ::1/localhost，127.0.0.1 不通。
STOREFRONT_BASE_URL = (
    os.getenv("STOREFRONT_BASE_URL", "http://localhost:3000").strip().rstrip("/")
)

# Crisp 客服消息镜像（需求 18 / 批次 V）：商家端、管理端聊天消息旁路镜像到 Crisp Inbox。
# 凭据全部留空 = 镜像直接返回 skipped（只写 CrispMirrorLog，不发任何外部请求、不报错）。
# 优先级：workspace API token > plugin token > website token（同时配置时按此顺序取）。
# CRISP_API_TOKEN_ID/KEY 是「设定 → 工作区 → 进阶设定 → API 令牌」生成的 identifier + key，
# 授权头为 Basic base64(identifier:key)；CRISP_API_TIER 对应 X-Crisp-Tier（默认 website）。
# 注意：官网 token 每日 10,000 次、plugin token 每日 5,000 次，镜像按「一条消息一次 POST」计。
CRISP_WEBSITE_ID = os.getenv("CRISP_WEBSITE_ID", "").strip()
CRISP_WEBSITE_TOKEN = os.getenv("CRISP_WEBSITE_TOKEN", "").strip()
CRISP_PLUGIN_ID = os.getenv("CRISP_PLUGIN_ID", "").strip()
CRISP_PLUGIN_TOKEN = os.getenv("CRISP_PLUGIN_TOKEN", "").strip()
CRISP_API_TOKEN_ID = os.getenv("CRISP_API_TOKEN_ID", "").strip()
CRISP_API_TOKEN_KEY = os.getenv("CRISP_API_TOKEN_KEY", "").strip()
CRISP_API_TIER = os.getenv("CRISP_API_TIER", "website").strip() or "website"
# 平台客服（from=operator）消息在 Crisp 气泡上显示的昵称；留空用默认「Joybuy 客服」。
CRISP_PLATFORM_NICKNAME = os.getenv("CRISP_PLATFORM_NICKNAME", "").strip()

if APP_ENV not in {"development", "test"}:
    if VERIFICATION_CODE_TEST_MODE:
        raise ImproperlyConfigured("VERIFICATION_CODE_TEST_MODE cannot be enabled outside dev/test")
    for secret_name, secret_value in (
        ("BUYER_SESSION_HMAC_KEY", BUYER_SESSION_HMAC_KEY),
        ("VERIFICATION_CODE_HMAC_KEY", VERIFICATION_CODE_HMAC_KEY),
        ("STAFF_SESSION_HMAC_KEY", STAFF_SESSION_HMAC_KEY),
        ("STAFF_TOTP_ENCRYPTION_KEY", STAFF_TOTP_ENCRYPTION_KEY),
        ("SOURCE_FINGERPRINT_HMAC_KEY", SOURCE_FINGERPRINT_HMAC_KEY),
        ("CRAWL_SESSION_ENCRYPTION_KEY", CRAWL_SESSION_ENCRYPTION_KEY),
    ):
        if not secret_value or secret_value.startswith("CHANGE_ME") or secret_value == SECRET_KEY:
            raise ImproperlyConfigured(f"{secret_name} must be an independent production secret")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.getenv("MAIL_HOST", "127.0.0.1")
EMAIL_PORT = int(os.getenv("MAIL_PORT", "1025"))
EMAIL_USE_TLS = env_bool("MAIL_USE_TLS", False)
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "Joybuy Local <noreply@localhost>")

REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "common.exceptions.api_exception_handler",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "common.logging.JsonFormatter"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
    },
    "loggers": {
        "django.server": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        }
    },
}
