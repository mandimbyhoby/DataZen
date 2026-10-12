"""Routage URL de l'application core."""
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views, views_pro

app_name = "core"

urlpatterns = [
    path("", views.index, name="index"),
    path("datasets/<int:pk>/", views.dataset_detail, name="dataset_detail"),
    path("datasets/<int:pk>/status/", views.cleaning_status, name="cleaning_status"),
    path("datasets/<int:pk>/download/", views.download_cleaned, name="download_cleaned"),
    path("datasets/<int:pk>/download_original/", views.download_original, name="download_original"),
    path("datasets/<int:pk>/report/", views.download_report, name="download_report"),
    path("datasets/<int:pk>/report/view/", views.view_report, name="view_report"),
    path("datasets/<int:pk>/report/html/", views.download_report_html, name="download_report_html"),
    path("datasets/<int:pk>/changelog/", views.download_change_log, name="download_changelog"),
    path("datasets/<int:pk>/json/", views.download_json, name="download_json"),
    path("datasets/<int:pk>/review/", views.review_duplicate, name="review_duplicate"),
    path("datasets/<int:pk>/analysis/", views.dataset_analysis, name="dataset_analysis"),
    path("datasets/<int:pk>/chart/<slug:slug>.png", views.dataset_chart, name="dataset_chart"),
    path("datasets/<int:pk>/chart-data/", views.dataset_chart_data, name="dataset_chart_data"),
    path("datasets/<int:pk>/delete/", views.delete_dataset, name="delete_dataset"),
    path("datasets/<int:pk>/archive/", views.archive_dataset, name="archive_dataset"),
    path("datasets/<int:pk>/restore/", views.restore_dataset, name="restore_dataset"),
    # Pilotage : tableau de bord global
    path("dashboard/", views_pro.dashboard, name="dashboard"),
    # Confiance : comparaison avant/après et rapport PDF
    path(
        "datasets/<int:pk>/comparison/",
        views_pro.dataset_comparison,
        name="dataset_comparison",
    ),
    path(
        "datasets/<int:pk>/report/pdf/",
        views_pro.download_pdf_report,
        name="download_pdf_report",
    ),
    # Productivité : recherche globale (Ctrl+K) et journal d'activité
    path("search/", views_pro.global_search, name="global_search"),
    path("activity/", views_pro.activity, name="activity"),
    path("shortcuts/", views_pro.shortcuts, name="shortcuts"),
    # Intégration : API REST en lecture
    path("api/", views_pro.api_index, name="api_index"),
    path("api/datasets/", views_pro.api_datasets, name="api_datasets"),
    path("api/datasets/<int:pk>/", views_pro.api_dataset_detail, name="api_dataset_detail"),
    path(
        "api/datasets/<int:pk>/changelog/",
        views_pro.api_dataset_changelog,
        name="api_dataset_changelog",
    ),
    path(
        "api/datasets/<int:pk>/download/",
        views_pro.api_dataset_download,
        name="api_dataset_download",
    ),
    path("api/stats/", views_pro.api_stats, name="api_stats"),
    # Intégration : jetons et webhooks
    path("api/tokens/", views_pro.api_tokens, name="api_tokens"),
    path(
        "api/tokens/<int:pk>/revoke/",
        views_pro.api_token_revoke,
        name="api_token_revoke",
    ),
    path("api/webhooks/", views_pro.webhooks, name="webhooks"),
    path("api/webhooks/<int:pk>/", views_pro.webhook_delete, name="webhook_delete"),
    path(
        "api/webhooks/<int:pk>/toggle/",
        views_pro.webhook_toggle,
        name="webhook_toggle",
    ),
    path("api/webhooks/<int:pk>/test/", views_pro.webhook_test, name="webhook_test"),
    # Rétention des données
    path("retention/", views_pro.retention, name="retention"),
    path("retention/purge/", views_pro.retention_purge, name="retention_purge"),
    path(
        "retention/activity/",
        views_pro.retention_cleanup_activity,
        name="retention_cleanup_activity",
    ),
    # Langue de l'interface
    path("i18n/setlang/", views.set_language, name="set_language"),
    # Authentification
    path("accounts/signup/", views.signup, name="signup"),
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="core/login.html"),
        name="login",
    ),
    path("accounts/logout/", auth_views.LogoutView.as_view(), name="logout"),
    # Réinitialisation du mot de passe
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
    # Règles de nettoyage personnalisées
    path("rules/", views.rules_list, name="rules_list"),
    path("rules/<int:pk>/delete/", views.rule_delete, name="rule_delete"),
    path("rules/<int:pk>/toggle/", views.rule_toggle, name="rule_toggle"),
    # Profil utilisateur
    path("profile/", views.profile, name="profile"),
    path("profile/avatar/delete/", views.profile_avatar_delete, name="profile_avatar_delete"),
    path("profile/password/", views.profile_password, name="profile_password"),
    path("profile/export/", views.profile_export, name="profile_export"),
    path("profile/delete/", views.profile_delete, name="profile_delete"),
    path("u/<str:username>/", views.profile_public, name="profile_public"),
]
