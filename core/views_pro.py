"""Vues des fonctionnalités « pro » : pilotage, confiance, productivité, API.

Ce module est importé par :mod:`core.urls` et complète :mod:`core.views` sans
alourdir le fichier principal :

- **pilotage** : tableau de bord global multi-fichiers ;
- **confiance** : comparaison avant / après et rapport PDF ;
- **productivité** : recherche globale (Ctrl+K) et journal d'activité ;
- **intégration** : API REST en lecture, jetons et webhooks ;
- **rétention** : purge manuelle des fichiers expirés.

Aucune vue de ce module n'est accessible sans compte : toutes exigent une
authentification (``@login_required``) ou un jeton d'API valide.
"""
from __future__ import annotations

import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required, login_required
from django.db.models import Q
from django.http import FileResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .errors import user_error
from .forms import ApiTokenForm, WebhookForm
from .models import ActivityLog, ApiToken, DataFile, Webhook
from .services import activity as activity_service
from .services import api as api_service
from .services import overview as overview_service
from .services import retention as retention_service
from .services import search as search_service
from .services.charts import build_charts
from .services.comparison import load_comparison
from .services.dashboard import build_dashboard
from .services.operations import render_correction_types
from .services.pdf import build_pdf
from .services.pipeline import read_change_log
from .services.reader import read_dataframe
from .services.validation import build_detection, compute_quality_score
from .views import (
    _cleaned_dataframe,
    _get_visible_file,
    _theme,
    _visible_files,
    _visible_rules,
)


# --- Pilotage : tableau de bord global -----------------------------------


@login_required
def dashboard(request):
    """Tableau de bord global : synthèse de tous les fichiers de l'utilisateur.

    Aucun fichier n'est relu : les indicateurs figés lors du nettoyage
    (``DataFile.metrics``) suffisent, la page s'affiche donc instantanément.
    """
    queryset = _visible_files(request.user)
    data = overview_service.build_overview(queryset)
    data["sparkline"] = overview_service.score_sparkline(data["timeline"])
    data["aggregate"] = overview_service.aggregate_stats(
        queryset.filter(archived_at__isnull=True)
    )
    data["activities"] = activity_service.recent_activities(request.user, limit=8)
    # Progression avant/après attachée aux fichiers listés (attribut transitoire).
    for data_file in data["worst_files"] + data["best_files"]:
        delta = overview_service.format_delta(data_file)
        data_file.delta_css = delta["css"]
        data_file.delta_text = delta["text"]
    data["timeline_json"] = json.dumps(
        data["timeline"], ensure_ascii=False, default=str
    )
    return render(request, "core/dashboard.html", data)


# --- Confiance : comparaison avant / après et rapport PDF ----------------


@login_required
def dataset_comparison(request, pk):
    """Comparaison « avant / après » entre le fichier d'origine et le nettoyé."""
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    comparison = load_comparison(data_file)
    if comparison is None:
        messages.error(
            request,
            _(
                "La comparaison n'est pas disponible : lancez d'abord un "
                "nettoyage sur ce fichier."
            ),
        )
        return redirect("core:dataset_detail", pk=pk)

    context = {
        "data_file": data_file,
        "comparison": comparison,
        "delta": overview_service.format_delta(data_file),
    }
    return render(request, "core/dataset_comparison.html", context)


@login_required
def download_pdf_report(request, pk):
    """Génère et renvoie le rapport de qualité au format PDF.

    Les graphiques matplotlib sont embarqués dans le document : le rapport est
    autonome et exploitable hors ligne (comité qualité, audit, client).
    """
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    df = _cleaned_dataframe(data_file)
    if df is None:
        messages.error(
            request,
            _("Lancez d'abord un nettoyage pour générer un rapport PDF."),
        )
        return redirect("core:dataset_detail", pk=pk)

    dashboard = build_dashboard(df)
    quality = compute_quality_score(df, build_detection(df))
    charts = build_charts(df, dashboard, theme="light")
    operations = []
    try:
        change_log = read_change_log(data_file)
        if change_log is not None and not change_log.empty:
            column = "type_correction"
            if column in change_log.columns:
                operations = render_correction_types(
                    change_log[column].dropna().unique().tolist()
                )
    except Exception:  # noqa: BLE001 — le journal est un bonus, pas un prérequis
        operations = []

    try:
        payload = build_pdf(
            data_file,
            dashboard=dashboard,
            quality=quality,
            validation=build_detection(df),
            charts=charts,
            operations=operations,
        )
    except Exception as exc:  # noqa: BLE001 — message utilisateur clair
        messages.error(
            request,
            _("Impossible de générer le PDF : %(error)s")
            % {"error": user_error(exc, "génération du PDF")},
        )
        return redirect("core:dataset_detail", pk=pk)

    activity_service.record(
        request.user,
        ActivityLog.Action.REPORT,
        _("Rapport PDF de « %(name)s »") % {"name": data_file.original_name},
        data_file=data_file,
    )

    import io

    from pathlib import Path

    stem = Path(data_file.original_name or "donnees").stem
    return FileResponse(
        io.BytesIO(payload),
        as_attachment=True,
        filename=f"{stem}_rapport.pdf",
        content_type="application/pdf",
    )


# --- Productivité : recherche globale et journal d'activité --------------


@login_required
def global_search(request):
    """Recherche globale (palette Ctrl+K) : fichiers, règles, pages, activité.

    Renvoie un JSON léger, limité aux éléments visibles par l'utilisateur. Le
    classement par pertinence et l'agrégation des sources sont délégués à
    :mod:`core.services.search`.
    """
    return JsonResponse(search_service.search(request.user, request.GET.get("q")))


@login_required
def activity(request):
    """Journal d'activité : historique horodaté des actions de l'utilisateur."""
    action = request.GET.get("action", "").strip()
    valid_actions = {choice.value for choice in ActivityLog.Action}

    queryset = activity_service.visible_activities(request.user)
    if action in valid_actions:
        queryset = queryset.filter(action=action)

    activities = list(queryset[:300])
    context = {
        "activities": activities,
        "selected_action": action,
        "action_choices": ActivityLog.Action.choices,
        "stats": activity_service.activity_stats(request.user),
        "summary": activity_service.summarize_deletions(activities),
    }
    return render(request, "core/activity.html", context)


# --- Intégration : API REST, jetons et webhooks --------------------------


def _json_error(message, status):
    """Réponse d'erreur JSON homogène pour l'API."""
    return JsonResponse({"error": message}, status=status)


def _bearer_token(request):
    """Résout le jeton porteur de la requête (en-tête Authorization).

    Le paramètre d'URL ``?token=`` a été retiré : un jeton placé dans une URL
    fuite dans les journaux d'accès, l'historique du navigateur et l'en-tête
    ``Referer``. Seul l'en-tête est donc accepté.
    """
    header = request.META.get("HTTP_AUTHORIZATION", "")
    if header.lower().startswith("bearer "):
        return api_service.resolve_token(header[7:].strip())
    return None


def api_required(view):
    """Protège une vue d'API par jeton porteur.

    Le jeton est lu dans l'en-tête ``Authorization: Bearer …`` ou, à défaut,
    dans le paramètre d'URL — retiré, car un jeton dans une URL fuite dans les
    journaux d'accès, l'historique du navigateur et l'en-tête ``Referer``.
    Chaque appel valide est journalisé et incrémente le compteur du jeton.

    La vue est marquée ``login_not_required`` : l'authentification est assurée
    par le jeton, pas par la session (un client automatisé n'a pas de session).
    """

    @login_not_required
    def wrapper(request, *args, **kwargs):
        token = _bearer_token(request)
        if token is None:
            response = _json_error("invalid_token", 401)
            response["WWW-Authenticate"] = "Bearer"
            return response
        api_service.touch_token(token)
        activity_service.record(
            token.owner,
            ActivityLog.Action.API,
            _("Appel API : %(path)s") % {"path": request.path},
        )
        request.api_token = token
        request.api_user = token.owner
        return view(request, *args, **kwargs)

    wrapper.__name__ = view.__name__
    wrapper.__doc__ = view.__doc__
    return wrapper


def _api_dataset_payload(data_file):
    """Représentation JSON d'un dataset (sans chemin de fichier)."""
    return {
        "id": data_file.pk,
        "name": data_file.original_name,
        "status": data_file.status,
        "status_label": data_file.get_status_display(),
        "created_at": data_file.created_at.isoformat(),
        "cleaned_at": data_file.cleaned_at.isoformat() if data_file.cleaned_at else None,
        "archived": data_file.archived_at is not None,
        "rows": data_file.rows_count,
        "columns": data_file.columns_count,
        "score_before": data_file.quality_before,
        "score_after": data_file.quality_after,
        "issues": data_file.issues_count,
        "changes": data_file.changes_count,
        "metrics": data_file.metrics or {},
        "urls": {
            "detail": reverse("core:api_dataset_detail", args=[data_file.pk]),
            "changelog": reverse("core:api_dataset_changelog", args=[data_file.pk]),
            "download": reverse("core:api_dataset_download", args=[data_file.pk]),
        },
    }


@api_required
def api_index(request):
    """Point d'entrée de l'API : décrit les routes disponibles."""
    return JsonResponse(
        {
            "application": "DataZen",
            "version": 1,
            "user": request.api_user.username,
            "endpoints": {
                "datasets": reverse("core:api_datasets"),
                "dataset": reverse("core:api_dataset_detail", args=[0]).replace("/0/", "/<id>/"),
                "stats": reverse("core:api_stats"),
                "changelog": reverse("core:api_dataset_changelog", args=[0]).replace("/0/", "/<id>/"),
                "download": reverse("core:api_dataset_download", args=[0]).replace("/0/", "/<id>/"),
            },
        }
    )


@api_required
def api_datasets(request):
    """Liste les datasets de l'utilisateur du jeton (filtres ``status``/``q``)."""
    queryset = _visible_files(request.api_user)
    status = request.GET.get("status", "").strip()
    query = request.GET.get("q", "").strip()
    if status in {choice.value for choice in DataFile.Status}:
        queryset = queryset.filter(status=status)
    if query:
        queryset = queryset.filter(original_name__icontains=query)

    limit = min(int(request.GET.get("limit", 50) or 50), 200)
    items = [_api_dataset_payload(f) for f in queryset[:limit]]
    return JsonResponse({"count": len(items), "results": items})


@api_required
def api_dataset_detail(request, pk):
    """Détail d'un dataset (indicateurs + journal des modifications)."""
    data_file = DataFile.objects.filter(pk=pk).first()
    if data_file is None or not (
        request.api_user.is_superuser or data_file.owner_id == request.api_user.pk
    ):
        return _json_error("not_found", 404)

    payload = _api_dataset_payload(data_file)
    try:
        change_log = read_change_log(data_file)
        payload["change_log"] = (
            change_log.head(200).to_dict(orient="records")
            if change_log is not None and not change_log.empty
            else []
        )
    except Exception:  # noqa: BLE001 — journal optionnel
        payload["change_log"] = []
    return JsonResponse(payload)


@api_required
def api_dataset_changelog(request, pk):
    """Journal des modifications d'un dataset, au format JSON."""
    data_file = DataFile.objects.filter(pk=pk).first()
    if data_file is None or not (
        request.api_user.is_superuser or data_file.owner_id == request.api_user.pk
    ):
        return _json_error("not_found", 404)

    try:
        change_log = read_change_log(data_file)
    except Exception:  # noqa: BLE001
        change_log = None
    rows = (
        change_log.to_dict(orient="records")
        if change_log is not None and not change_log.empty
        else []
    )
    return JsonResponse({"dataset": data_file.original_name, "count": len(rows), "results": rows})


@api_required
def api_dataset_download(request, pk):
    """Renvoie le fichier nettoyé en flux JSON (portabilité vers un autre outil)."""
    data_file = DataFile.objects.filter(pk=pk).first()
    if data_file is None or not (
        request.api_user.is_superuser or data_file.owner_id == request.api_user.pk
    ):
        return _json_error("not_found", 404)
    if not data_file.cleaned_file:
        return _json_error("no_cleaned_data", 409)

    try:
        df = read_dataframe(data_file.cleaned_file.path)
    except Exception:  # noqa: BLE001
        return _json_error("unreadable_file", 500)

    records = json.loads(
        json.dumps(
            df.to_dict(orient="records"),
            default=lambda value: None,
            ensure_ascii=False,
        )
    )
    return JsonResponse(
        {"dataset": data_file.original_name, "count": len(records), "results": records}
    )


@api_required
def api_stats(request):
    """Statistiques agrégées du compte (mêmes indicateurs que le tableau de bord)."""
    queryset = _visible_files(request.api_user)
    aggregate = overview_service.aggregate_stats(queryset.filter(archived_at__isnull=True))
    return JsonResponse(
        {
            "files": aggregate.get("files") or 0,
            "rows": aggregate.get("rows") or 0,
            "columns": aggregate.get("columns") or 0,
            "issues": aggregate.get("issues") or 0,
            "changes": aggregate.get("changes") or 0,
            "average_score": (
                round(aggregate["average"], 1)
                if aggregate.get("average") is not None
                else None
            ),
        }
    )


@login_required
def api_tokens(request):
    """Gestion des jetons d'API : création, révocation, statistiques d'usage."""
    new_token = None
    if request.method == "POST":
        form = ApiTokenForm(request.POST)
        if form.is_valid():
            token, clear = api_service.create_token(
                request.user,
                form.cleaned_data["name"],
                form.cleaned_data.get("expires_at"),
            )
            activity_service.record(
                request.user,
                ActivityLog.Action.TOKEN_CREATE,
                _("Création du jeton « %(name)s »") % {"name": token.name},
                level=ActivityLog.Level.SUCCESS,
            )
            new_token = {"instance": token, "clear": clear}
            messages.success(
                request,
                _(
                    "Jeton créé. Copiez-le maintenant : il ne sera plus affiché."
                ),
            )
            form = ApiTokenForm()
    else:
        form = ApiTokenForm()

    context = {
        "form": form,
        "tokens": api_service.visible_tokens(request.user),
        "stats": api_service.token_stats(request.user),
        "new_token": new_token,
        "sample_curl": _sample_curl(request),
    }
    return render(request, "core/api_tokens.html", context)


def _sample_curl(request):
    """Exemple d'appel prêt à copier (adapté au domaine courant)."""
    base = request.build_absolute_uri(reverse("core:api_datasets"))
    return (
        f'curl -H "Authorization: Bearer dz_VOTRE_JETON"\n'
        f'     "{base}"'
    )


@login_required
@require_POST
def api_token_revoke(request, pk):
    """Révoque un jeton d'API (l'historique du journal est conservé)."""
    token = get_object_or_404(ApiToken, pk=pk)
    if not (request.user.is_superuser or token.owner_id == request.user.pk):
        messages.error(request, _("Vous n'avez pas accès à ce jeton."))
        return redirect("core:api_tokens")

    api_service.revoke_token(token)
    activity_service.record(
        request.user,
        ActivityLog.Action.TOKEN_REVOKE,
        _("Révocation du jeton « %(name)s »") % {"name": token.name},
        level=ActivityLog.Level.WARNING,
    )
    messages.success(request, _("Jeton « %(name)s » révoqué.") % {"name": token.name})
    return redirect("core:api_tokens")


@login_required
def webhooks(request):
    """Gestion des webhooks : abonnements sortants vers un service externe."""
    if request.method == "POST":
        form = WebhookForm(request.POST)
        if form.is_valid():
            hook = form.save(commit=False)
            hook.owner = request.user
            hook.secret = hook.secret or api_service.generate_secret()
            hook.save()
            messages.success(
                request, _("Webhook « %(name)s » créé.") % {"name": hook.name}
            )
            return redirect("core:webhooks")
    else:
        form = WebhookForm()

    context = {
        "form": form,
        "hooks": api_service.visible_webhooks(request.user),
        "stats": api_service.webhook_stats(request.user),
    }
    return render(request, "core/webhooks.html", context)


@login_required
@require_POST
def webhook_delete(request, pk):
    """Supprime un webhook."""
    hook = get_object_or_404(Webhook, pk=pk)
    if not (request.user.is_superuser or hook.owner_id == request.user.pk):
        messages.error(request, _("Vous n'avez pas accès à ce webhook."))
        return redirect("core:webhooks")

    name = hook.name
    hook.delete()
    messages.success(request, _("Webhook « %(name)s » supprimé.") % {"name": name})
    return redirect("core:webhooks")


@login_required
@require_POST
def webhook_toggle(request, pk):
    """Active ou désactive un webhook."""
    hook = get_object_or_404(Webhook, pk=pk)
    if not (request.user.is_superuser or hook.owner_id == request.user.pk):
        messages.error(request, _("Vous n'avez pas accès à ce webhook."))
        return redirect("core:webhooks")

    hook.is_active = not hook.is_active
    hook.save(update_fields=["is_active"])
    messages.success(
        request,
        _("Webhook « %(name)s » %(state)s.")
        % {
            "name": hook.name,
            "state": _("activé") if hook.is_active else _("désactivé"),
        },
    )
    return redirect("core:webhooks")


@login_required
@require_POST
def webhook_test(request, pk):
    """Envoie un événement de test (appel HTTP synchrone, code retour affiché)."""
    hook = get_object_or_404(Webhook, pk=pk)
    if not (request.user.is_superuser or hook.owner_id == request.user.pk):
        messages.error(request, _("Vous n'avez pas accès à ce webhook."))
        return redirect("core:webhooks")

    status = api_service.send_test(hook)
    if status and status < 400:
        messages.success(
            request,
            _("Webhook « %(name)s » : test réussi (HTTP %(status)s).")
            % {"name": hook.name, "status": status},
        )
    else:
        messages.error(
            request,
            _(
                "Webhook « %(name)s » : test échoué (HTTP %(status)s). "
                "Vérifiez l'URL et que le service accepte les appels entrants."
            )
            % {"name": hook.name, "status": status or 0},
        )
    return redirect("core:webhooks")


# --- Rétention : purge manuelle ------------------------------------------


@login_required
def retention(request):
    """Politique de rétention : fichiers expirés et purge manuelle.

    La purge automatique est optionnelle et pilotée depuis le profil ; cette
    page montre exactement ce qui serait supprimé et permet de le faire à la
    demande, sans surprise.
    """
    expired = list(retention_service.expired_files(request.user))
    days = retention_service.retention_days(request.user)
    cutoff = timezone.now() - timedelta(days=days)

    context = {
        "expired": expired,
        "expired_count": len(expired),
        "days": days,
        "cutoff": cutoff,
        "auto_purge": retention_service.auto_purge_enabled(request.user),
        "archived_count": _visible_files(request.user)
        .filter(archived_at__isnull=False)
        .count(),
        "activities": activity_service.recent_activities(request.user, limit=6),
    }
    return render(request, "core/retention.html", context)


@login_required
@require_POST
def retention_purge(request):
    """Purge immédiate des fichiers expirés (action explicite de l'utilisateur)."""
    result = retention_service.apply_retention(request.user, purge=True)
    purged = (result or {}).get("purged", 0)
    archived = (result or {}).get("archived", 0)
    activity_service.record(
        request.user,
        ActivityLog.Action.DELETE,
        _("Purge de %(count)s fichier(s) expiré(s)") % {"count": purged},
        level=ActivityLog.Level.WARNING,
    )
    if purged:
        messages.success(
            request,
            _("%(purged)s fichier(s) supprimé(s), %(archived)s archivé(s).")
            % {"purged": purged, "archived": archived},
        )
    else:
        messages.info(request, _("Aucun fichier expiré à purger."))
    return redirect("core:retention")


@login_required
@require_POST
def retention_cleanup_activity(request):
    """Purge les entrées du journal d'activité antérieures à la rétention."""
    days = retention_service.retention_days(request.user)
    deleted = activity_service.cleanup_activities(user=request.user, days=days)
    messages.success(
        request,
        _("%(count)s entrée(s) d'activité supprimée(s).") % {"count": deleted},
    )
    return redirect("core:activity")


# --- Aide contextuelle ----------------------------------------------------


@login_required
def shortcuts(request):
    """Aide-mémoire des raccourcis clavier et des nouveautés de l'interface."""
    context = {
        "rules_count": _visible_rules(request.user).count(),
        "files_count": _visible_files(request.user).count(),
        "tokens_count": api_service.token_stats(request.user)["total"],
        "hooks_count": api_service.webhook_stats(request.user)["total"],
    }
    return render(request, "core/shortcuts.html", context)
