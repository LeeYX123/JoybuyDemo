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
    "http://127.0.0.1:3000,http://127.0.0.1:5173",
)

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

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SESSION_COOKIE_NAME = "joybuy_django_session"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = APP_ENV not in {"development", "test"}
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True
CSRF_COOKIE_SECURE = APP_ENV not in {"development", "test"}
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
STAFF_SESSION_MAX_AGE_SECONDS = int(os.getenv("STAFF_SESSION_MAX_AGE_SECONDS", "28800"))
STAFF_SESSION_HMAC_KEY = os.getenv("STAFF_SESSION_HMAC_KEY", SECRET_KEY)
STAFF_TOTP_ENCRYPTION_KEY = os.getenv("STAFF_TOTP_ENCRYPTION_KEY", SECRET_KEY)
STAFF_TOTP_PERIOD_SECONDS = int(os.getenv("STAFF_TOTP_PERIOD_SECONDS", "30"))
STAFF_TOTP_ALLOWED_DRIFT_STEPS = int(os.getenv("STAFF_TOTP_ALLOWED_DRIFT_STEPS", "1"))
# Set false ONLY in local development to sign in with password alone
# (TOTP codes not required); production keeps the default enforcement.
STAFF_TOTP_LOGIN_ENFORCED = env_bool("STAFF_TOTP_LOGIN_ENFORCED", True)
STAFF_LOGIN_FAILURE_LIMIT = int(os.getenv("STAFF_LOGIN_FAILURE_LIMIT", "5"))
STAFF_LOGIN_FAILURE_WINDOW_SECONDS = int(os.getenv("STAFF_LOGIN_FAILURE_WINDOW_SECONDS", "900"))

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
