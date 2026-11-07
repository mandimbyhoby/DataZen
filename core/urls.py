"""Routage URL de l'application core."""
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views, views_auth

app_name = "core"

urlpatterns = [
    path("accounts/login/", views_auth.ThrottledLoginView.as_view(), name="login"),
    path("accounts/signup/", views_auth.signup, name="signup"),
    path(
        "accounts/password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="core/password_reset.html",
            email_template_name="core/password_reset_email.html",
            subject_template_name="core/password_reset_subject.txt",
            success_url=reverse_lazy("core:password_reset_done"),
        ),
        name="password_reset",
    ),
    path(
        "accounts/password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="core/password_reset_done.html"
        ),
        name="password_reset_done",
    ),
    path(
        "accounts/reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="core/password_reset_confirm.html",
            success_url=reverse_lazy("core:password_reset_complete"),
        ),
        name="password_reset_confirm",
    ),
    path(
        "accounts/reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="core/password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
    path("", views.index, name="index"),
    path("datasets/<int:pk>/", views.dataset_detail, name="dataset_detail"),
    path("datasets/<int:pk>/download/", views.download_cleaned, name="download_cleaned"),
    path("datasets/<int:pk>/download_original/", views.download_original, name="download_original"),
    path("datasets/<int:pk>/report/", views.download_report, name="download_report"),
    path("datasets/<int:pk>/report/view/", views.view_report, name="view_report"),
    path("datasets/<int:pk>/report/html/", views.download_report_html, name="download_report_html"),
    path("datasets/<int:pk>/changelog/", views.download_change_log, name="download_changelog"),
    path("datasets/<int:pk>/review/", views.review_duplicate, name="review_duplicate"),
    path("datasets/<int:pk>/delete/", views.delete_dataset, name="delete_dataset"),
]
