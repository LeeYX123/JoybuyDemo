from django.urls import path

from accounts_staff import views

urlpatterns = [
    path(
        "api/v1/admin/auth/session",
        views.StaffSessionView.as_view(),
        name="staff-session",
    ),
    path(
        "api/v1/admin/auth/login",
        views.StaffLoginView.as_view(),
        name="staff-login",
    ),
    path(
        "api/v1/admin/auth/logout",
        views.StaffLogoutView.as_view(),
        name="staff-logout",
    ),
    path("api/v1/admin/rbac/me", views.StaffMeView.as_view(), name="staff-rbac-me"),
    path(
        "api/v1/admin/staff/<uuid:public_id>/roles",
        views.StaffRoleAssignmentView.as_view(),
        name="staff-role-assignment",
    ),
]
