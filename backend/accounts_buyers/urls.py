from django.urls import path

from accounts_buyers import views

urlpatterns = [
    path(
        "api/v1/auth/buyer/verification-codes",
        views.VerificationCodeView.as_view(),
        name="buyer-verification-code",
    ),
    path("api/v1/auth/buyer/register", views.BuyerRegisterView.as_view(), name="buyer-register"),
    path("api/v1/auth/buyer/login", views.BuyerLoginView.as_view(), name="buyer-login"),
    path("api/v1/auth/buyer/logout", views.BuyerLogoutView.as_view(), name="buyer-logout"),
    path("api/v1/auth/buyer/session", views.BuyerSessionView.as_view(), name="buyer-session"),
]
