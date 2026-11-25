from django.urls import path

from accounts_buyers import views

urlpatterns = [
    path(
        "api/v1/auth/buyer/verification-codes",
        views.VerificationCodeView.as_view(),
        name="buyer-verification-code",
    ),
    path("api/v1/auth/buyer/register", views.BuyerRegisterView.as_view(), name="buyer-register"),
    path(
        "api/v1/auth/buyer/register/email",
        views.BuyerEmailRegisterView.as_view(),
        name="buyer-register-email",
    ),
    path("api/v1/auth/buyer/login", views.BuyerLoginView.as_view(), name="buyer-login"),
    path("api/v1/auth/buyer/logout", views.BuyerLogoutView.as_view(), name="buyer-logout"),
    path(
        "api/v1/auth/buyer/merchant-handoff",
        views.BuyerMerchantHandoffView.as_view(),
        name="buyer-merchant-handoff",
    ),
    path("api/v1/auth/buyer/session", views.BuyerSessionView.as_view(), name="buyer-session"),
    # 三方登录（docs/16）：providers 给前端渲染按钮，start/callback 是 OAuth 跳转链。
    path(
        "api/v1/auth/buyer/oauth/providers",
        views.OAuthProvidersView.as_view(),
        name="buyer-oauth-providers",
    ),
    # 登录页 email-first 第一步：只回答「这个邮箱/手机号是否已注册」（docs/17 §4）。
    path(
        "api/v1/auth/buyer/identifier/lookup",
        views.BuyerIdentifierLookupView.as_view(),
        name="buyer-identifier-lookup",
    ),
    path(
        "api/v1/auth/buyer/oauth/<str:provider>/start",
        views.OAuthStartView.as_view(),
        name="buyer-oauth-start",
    ),
    path(
        "api/v1/auth/buyer/oauth/<str:provider>/callback",
        views.OAuthCallbackView.as_view(),
        name="buyer-oauth-callback",
    ),
]
