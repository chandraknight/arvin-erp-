from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.user_dashboard, name='user_dashboard'),
    path('users/', views.user_list_view, name='user_list'),
    path('user/create/', views.UserCreateView.as_view(), name='user_create'),
    path('user/update/<uuid:id>/', views.UserUpdateView.as_view(), name='user_update'),
    path('user/delete/<uuid:id>/', views.user_delete, name='user_delete'),
    path('user/<uuid:id>/access/', views.user_module_access, name='user_access'),

    path('rbacs/', views.rbac_list_view, name='rbac_list'),
    path('rbac/update/<uuid:id>/', views.update_rbac, name='update_rbac'),

    # ── Password change (logged-in users) ─────────────────────────────────────
    path('password/change/', auth_views.PasswordChangeView.as_view(
        template_name='accounts/password_change.html',
        success_url='/accounts/password/change/done/',
    ), name='password_change'),
    path('password/change/done/', auth_views.PasswordChangeDoneView.as_view(
        template_name='accounts/password_change_done.html',
    ), name='password_change_done'),

    # ── Password reset (forgot password — unauthenticated) ────────────────────
    path('password/reset/', auth_views.PasswordResetView.as_view(
        template_name='accounts/password_reset.html',
        email_template_name='accounts/emails/password_reset_email.txt',
        html_email_template_name='accounts/emails/password_reset_email.html',
        subject_template_name='accounts/emails/password_reset_subject.txt',
        success_url='/accounts/password/reset/sent/',
    ), name='password_reset'),
    path('password/reset/sent/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_sent.html',
    ), name='password_reset_done'),
    path('password/reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/password_reset_confirm.html',
        success_url='/accounts/password/reset/complete/',
    ), name='password_reset_confirm'),
    path('password/reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/password_reset_complete.html',
    ), name='password_reset_complete'),

    # ── User invitation: set initial password ────────────────────────────────
    path('invitation/<uidb64>/<token>/', views.accept_invitation, name='accept_invitation'),
]
