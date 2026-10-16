"""Vues de l'application DataZen."""
import html
import io
import json
import logging
from datetime import timedelta
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.db.models import Q
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_not_required, login_required
from django.contrib.auth.models import User
from django.http import FileResponse, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext, gettext as _
from django.views.decorators.http import require_POST

from .errors import user_error
from .forms import (
    ApiTokenForm,
    CleaningOptionsForm,
    CleaningRuleForm,
    DataFileUploadForm,
    ProfileForm,
    SignUpForm,
    StyledPasswordChangeForm,
    WebhookForm,
)
from .models import ActivityLog, ApiToken, CleaningRule, DataFile, Profile, Webhook
from .services import activity as activity_service
from .services import api as api_service
from .services import overview as overview_service
from .services import permissions as permissions_service
from .services import retention as retention_service
from .services.async_runner import start_cleaning
from .services.charts import (
    build_charts,
    chart_catalog,
    chart_data,
    chart_png,
    charts_as_data_uris,
    numeric_columns,
)
from .services.cleaning import restore_semantic_types
from .services.comparison import load_comparison
from .services.markdown import markdown_to_html
from .services.operations import render_operations
from .services.pdf import build_pdf
from .services.pipeline import (
    append_change_log,
    build_cleaned_context,
    overwrite_cleaned_file,
    preview_cleaning,
    read_change_log,
    run_cleaning,
    stats as _stats,
)
from .services.dashboard import build_dashboard
from .services.reader import dataframe_to_rows, read_dataframe
from .services.review import apply_decision
from .services.validation import build_detection, compute_quality_score

PREVIEW_LIMIT = 10

logger = logging.getLogger(__name__)

# Types MIME explicites : sur Windows, `mimetypes` ne connaît pas `.xlsx`,
# sinon le fichier est servi en `application/octet-stream` et devient
# illisible pour les lecteurs Excel en ligne.
CONTENT_TYPES = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
}


def index(request):
    """Page d'accueil : téléversement et liste des fichiers (avec recherche)."""
    if request.method == "POST":
        form = DataFileUploadForm(request.POST, request.FILES)
        if form.is_valid():
            data_file = form.save(commit=False)
            data_file.owner = request.user
            data_file.save()
            activity_service.record(
                request.user,
                ActivityLog.Action.UPLOAD,
                _("Téléversement de « %(name)s »") % {"name": data_file.original_name},
                data_file=data_file,
                level=ActivityLog.Level.SUCCESS,
            )
            api_service.trigger(
                request.user, Webhook.Event.UPLOAD, data_file=data_file
            )
            messages.success(request, _("Fichier téléversé avec succès."))
            return redirect("core:dataset_detail", pk=data_file.pk)
    else:
        form = DataFileUploadForm()

    # Politique de rétention : purge des fichiers expirés (si activée), puis
    # archivage automatique des fichiers nettoyés les plus anciens.
    apply_retention(request.user)
    _auto_archive(request.user)

    archive = request.GET.get("archive") == "1"
    query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    valid_statuses = {choice.value for choice in DataFile.Status}

    visible_files = _visible_files(request.user)
    files_qs = visible_files.filter(archived_at__isnull=not archive)
    if query:
        files_qs = files_qs.filter(original_name__icontains=query)
    if status in valid_statuses:
        files_qs = files_qs.filter(status=status)

    total_files = files_qs.count()
    recent_files = list(files_qs[:50])

    # Les statistiques courantes excluent les fichiers déjà archivés.
    all_files = visible_files.filter(archived_at__isnull=True)
    global_stats = {
        "total": all_files.count(),
        "cleaned": all_files.filter(status=DataFile.Status.CLEANED).count(),
        "pending": all_files.filter(status=DataFile.Status.UPLOADED).count(),
        "errors": all_files.filter(status=DataFile.Status.ERROR).count(),
    }

    context = {
        "form": form,
        "recent_files": recent_files,
        "query": query,
        "status": status,
        "status_choices": DataFile.Status.choices,
        "total_files": total_files,
        "global_stats": global_stats,
        "archive": archive,
        "archived_count": visible_files.filter(archived_at__isnull=False).count(),
    }
    return render(request, "core/index.html", context)


def _auto_archive(user):
    """Archive automatiquement les fichiers nettoyés depuis plus de 30 jours."""
    cutoff = timezone.now() - timedelta(days=30)
    eligible = _visible_files(user).filter(
        status=DataFile.Status.CLEANED,
        archived_at__isnull=True,
        archive_exempt_from_auto=False,
    ).filter(
        Q(cleaned_at__lte=cutoff) | Q(cleaned_at__isnull=True, updated_at__lte=cutoff)
    )
    for data_file in eligible.only("pk", "cleaned_at", "updated_at"):
        data_file.archived_at = data_file.cleaned_at or data_file.updated_at
        data_file.save(update_fields=["archived_at"])


def apply_retention(user):
    """Applique la politique de rétention de l'utilisateur (best effort).

    Une erreur de purge (fichier verrouillé, stockage distant…) ne doit jamais
    empêcher l'affichage de la page d'accueil.
    """
    if not getattr(user, "is_authenticated", False):
        return None
    try:
        result = retention_service.apply_retention(user)
    except Exception:  # noqa: BLE001 — la rétention ne bloque jamais l'accueil
        logger.exception("Échec de l'application de la rétention")
        return None
    if result and result.get("purged"):
        activity_service.record(
            user,
            ActivityLog.Action.DELETE,
            _("Purge automatique de %(count)s fichier(s) expiré(s)")
            % {"count": result["purged"]},
            level=ActivityLog.Level.WARNING,
        )
    return result


def _visible_files(user):
    """Renvoie les fichiers visibles par l'utilisateur connecté.

    Trois sources se cumulent : la propriété, le partage nominatif et, pour
    un administrateur, l'ensemble du catalogue. L'application exige un
    compte : aucun fichier n'est accessible sans être connecté.
    """
    if user.is_superuser or permissions_service.is_admin(user):
        return DataFile.objects.all()
    shared_ids = permissions_service.shared_dataset_ids(user)
    return DataFile.objects.filter(Q(owner=user) | Q(pk__in=shared_ids)).distinct()


def _get_visible_file(request, pk):
    """Récupère un fichier en vérifiant les droits d'accès de l'utilisateur."""
    data_file = get_object_or_404(DataFile, pk=pk)
    if not _can_access(request.user, data_file):
        messages.error(request, _("Vous n'avez pas accès à ce fichier."))
        return None
    return data_file


def _can_access(user, data_file):
    """Indique si l'utilisateur connecté peut consulter le fichier."""
    return permissions_service.can_view(user, data_file)


def _require_edit(request, data_file=None):
    """Vérifie que le compte peut transformer les données.

    Un lecteur consulte et télécharge ; il ne nettoie ni ne supprime. Le
    contrôle est repris ici plutôt que dans le gabarit seul, car une page HTML
    ne protège rien : la requête doit être refusée côté serveur.
    """
    if permissions_service.can_edit(request.user):
        return True
    messages.error(
        request,
        _("Votre rôle ne permet pas de modifier les données. Contactez un administrateur."),
    )
    return False


def _require_download(request, data_file):
    """Vérifie que le compte peut exporter les fichiers du jeu de données.

    Un partage en consultation seule autorise l'affichage mais pas l'export :
    le contrôle est repris ici plutôt que dans le gabarit, qui ne protège rien.
    """
    if permissions_service.can_download(request.user, data_file):
        return True
    messages.error(request, _("Ce partage ne permet pas le téléchargement."))
    return False


def dataset_detail(request, pk):
    """Prévisualisation et nettoyage d'un fichier téléversé."""
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    try:
            df = read_dataframe(data_file.file.path)
    except Exception as exc:  # noqa: BLE001 — message utilisateur clair
        messages.error(
            request,
            _("Impossible de lire ce fichier : %(error)s")
            % {"error": user_error(exc, "lecture du fichier téléversé")},
        )
        return redirect("core:index")

    form = CleaningOptionsForm(request.POST or None, columns=list(df.columns))

    # Détection : analyse des problèmes avant nettoyage.
    issues = build_detection(df)
    quality_before = compute_quality_score(df, issues)

    context = {
        "data_file": data_file,
        "columns": list(df.columns),
        "stats": _stats(df),
        "preview_rows": dataframe_to_rows(df, limit=PREVIEW_LIMIT),
        "form": form,
        "issues": issues,
        "quality_before": quality_before,
        "rules": _visible_rules(request.user),
    }

    # Si un nettoyage a déjà eu lieu, on reconstruit tout le contexte
    # « après nettoyage » (score, dashboard, revue, validation, cohérence,
    # journal) directement depuis le fichier nettoyé, afin que la page reste
    # cohérente lors d'un simple rechargement (GET).
    if request.method == "GET" and data_file.cleaned_file:
        try:
            context.update(_cleaned_context(data_file, request))
        except Exception:
            # Un fichier nettoyé illisible ne doit pas casser l'affichage.
            pass

    if request.method == "POST" and form.is_valid():
        if not _require_edit(request, data_file):
            return redirect("core:dataset_detail", pk=data_file.pk)
        options = dict(form.cleaned_data)
        rules = _selected_rules(request)

        # Aperçu avant/après : on calcule exactement le même nettoyage que
        # ci-dessous, mais sans rien écrire. L'utilisateur décide ensuite de
        # confirmer (« action=clean », le cas par défaut) ou de réajuster ses
        # options.
        if request.POST.get("action") == "preview":
            context["preview"] = _build_preview(data_file, options, rules)
            if context["preview"] is None:
                messages.error(
                    request,
                    _("Impossible de simuler le nettoyage : le fichier est illisible."),
                )
            else:
                activity_service.record(
                    request.user,
                    ActivityLog.Action.CLEAN,
                    _("Aperçu de nettoyage sur « %(name)s »")
                    % {"name": data_file.original_name},
                    data_file=data_file,
                )
                messages.info(
                    request,
                    _(
                        "Aperçu calculé : aucune modification n'a été enregistrée. "
                        "Confirmez pour appliquer le nettoyage."
                    ),
                )
            return render(request, "core/dataset_detail.html", context)

        # Traitement asynchrone : le nettoyage s'exécute en arrière-plan et la
        # page affiche une barre de progression (polling JSON).
        start_cleaning(
            data_file.pk,
            options,
            rules=rules,
            session_key=request.session.session_key,
            language=request.LANGUAGE_CODE,
        )
        activity_service.record(
            request.user,
            ActivityLog.Action.CLEAN,
            _("Nettoyage lancé sur « %(name)s »") % {"name": data_file.original_name},
            data_file=data_file,
        )
        messages.info(
            request,
            _(
                "Nettoyage lancé en arrière-plan. La page se met à jour "
                "automatiquement."
            ),
        )
        return redirect("core:dataset_detail", pk=data_file.pk)

    return render(request, "core/dataset_detail.html", context)


def _build_preview(data_file, options, rules):
    """Prépare l'aperçu avant/après affiché sur la page de détail.

    Le service renvoie déjà la comparaison complète ; on ne fait ici que
    traduire les libellés des opérations **au moment de l'affichage** (jamais au
    moment du calcul), pour que l'aperçu suive la langue active comme le reste
    de la page et ne reproduise pas le bug des libellés figés.
    """
    preview = preview_cleaning(data_file, options, rules)
    if preview is None:
        return None
    preview["rendered_operations"] = render_operations(preview["operations"])
    # Repère « score » désigné par son unité (le seul indicateur en %) plutôt
    # que par son libellé traduit, qui serait cassant d'une langue à l'autre.
    preview["score_indicator"] = next(
        (row for row in preview["indicators"] if row.get("unit") == "%"), None
    )
    return preview


def _cleaned_context(data_file, request):
    """Contexte « après nettoyage » avec les opérations mémorisées en session."""
    return build_cleaned_context(
        data_file,
        operations=request.session.get(f"operations_{data_file.pk}", []),
        regex_rules=request.session.get(f"regex_rules_{data_file.pk}", []),
        theme=_theme(request),
    )


def _theme(request):
    """Thème des graphiques : ``auto`` (transparent), ``light`` ou ``dark``.

    Le thème de l'interface est mémorisé côté navigateur (``localStorage``),
    donc invisible pour le serveur : par défaut les graphiques sont rendus
    avec un fond transparent, lisible dans les deux thèmes.
    """
    theme = request.GET.get("theme", "auto")
    return theme if theme in ("light", "dark") else "auto"


def _cleaned_dataframe(data_file):
    """DataFrame nettoyé d'un dataset, ou ``None`` s'il n'existe pas/est illisible."""
    if not data_file.cleaned_file:
        return None
    try:
        return restore_semantic_types(read_dataframe(data_file.cleaned_file.path))
    except Exception:  # noqa: BLE001 — fichier illisible : pas de graphique
        return None


def dataset_chart(request, pk, slug):
    """Renvoie un graphique PNG (matplotlib/seaborn) pour un dataset nettoyé.

    Les images sont générées à la demande puis mises en cache par le
    navigateur : la page reste légère même avec de nombreux graphiques.
    """
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    df = _cleaned_dataframe(data_file)
    if df is None:
        messages.error(request, _("Aucune donnée nettoyée disponible."))
        return redirect("core:dataset_detail", pk=pk)

    dashboard = build_dashboard(df)
    png = chart_png(df, dashboard, slug, theme=_theme(request))
    if png is None:
        messages.error(request, _("Ce graphique n'est pas disponible pour ce jeu de données."))
        return redirect("core:dataset_detail", pk=pk)

    response = HttpResponse(png, content_type="image/png")
    response["Cache-Control"] = "private, max-age=3600"
    # Le rendu dépend de la langue active : sans ``Vary``, un changement de
    # langue pourrait servir une image mise en cache dans l'ancienne langue.
    response["Vary"] = "Cookie"
    return response


def dataset_chart_data(request, pk):
    """Données JSON des graphiques, pour le rendu interactif (React + Chart.js).

    Renvoie le même contenu que les PNG, mais sous forme de données brutes :
    le navigateur dessine alors les graphiques en pleine résolution, adaptés au
    thème clair/sombre et redimensionnables. Les PNG restent utilisés comme
    repli (JavaScript désactivé, rapport HTML autonome).
    """
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return JsonResponse({"error": "not_found"}, status=404)

    df = _cleaned_dataframe(data_file)
    if df is None:
        return JsonResponse({"error": "no_cleaned_data"}, status=409)

    payload = chart_data(df, build_dashboard(df))
    response = JsonResponse(payload)
    response["Cache-Control"] = "private, max-age=3600"
    # Les libellés dépendent de la langue active : sans ``Vary``, un changement
    # de langue pourrait servir un JSON mis en cache dans l'ancienne langue.
    response["Vary"] = "Cookie"
    return response


def dataset_analysis(request, pk):
    """Page « Analyse exploratoire » : tous les graphiques statistiques.

    Les graphiques sont produits côté serveur avec matplotlib et seaborn à
    partir du DataFrame nettoyé, puis affichés en PNG.
    """
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    df = _cleaned_dataframe(data_file)
    if df is None:
        messages.error(
            request,
            _("Lancez d'abord un nettoyage pour accéder à l'analyse exploratoire."),
        )
        return redirect("core:dataset_detail", pk=pk)

    dashboard = build_dashboard(df)
    context = {
        "data_file": data_file,
        "dashboard": dashboard,
        "charts": chart_catalog(df, dashboard),
        "theme": _theme(request),
        "numeric_columns": [str(c) for c in numeric_columns(df, limit=len(df.columns) or 1)],
        "row_count": len(df),
        "column_count": len(df.columns),
    }
    return render(request, "core/dataset_analysis.html", context)


def _visible_rules(user):
    """Règles de nettoyage visibles par l'utilisateur connecté."""
    if user.is_superuser:
        return CleaningRule.objects.all()
    return CleaningRule.objects.filter(owner=user)


def _selected_rules(request):
    """Règles cochées dans le formulaire de nettoyage (liste de dicts)."""
    ids = request.POST.getlist("rules")
    if not ids:
        return []
    rules = _visible_rules(request.user).filter(pk__in=ids, is_active=True)
    return [
        {
            "operation": rule.operation,
            "column": rule.column,
            "value": rule.value,
        }
        for rule in rules
    ]


def cleaning_status(request, pk):
    """Renvoie l'état d'avancement du nettoyage (JSON, pour le polling)."""
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return JsonResponse({"error": "not_found"}, status=404)
    return JsonResponse(
        {
            "status": data_file.status,
            "progress": data_file.progress,
            "error": data_file.error_message,
            "cleaned": bool(data_file.cleaned_file),
        }
    )


def download_cleaned(request, pk):
    """Télécharge le fichier nettoyé, au format CSV ou Excel (au choix).

    Le paramètre ``format`` (``csv`` / ``xlsx``) permet de convertir à la
    volée : un fichier d'origine Excel peut être téléchargé en CSV et
    inversement, sans modifier le fichier nettoyé stocké.
    """
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    if not _require_download(request, data_file):
        return redirect("core:dataset_detail", pk=pk)

    if not data_file.cleaned_file:
        messages.error(request, _("Aucun fichier nettoyé n'est disponible."))
        return redirect("core:dataset_detail", pk=pk)

    filename = Path(data_file.cleaned_file.name).name
    current_ext = Path(filename).suffix.lower().lstrip(".")

    activity_service.record(
        request.user,
        ActivityLog.Action.DOWNLOAD,
        _("Téléchargement de « %(name)s »") % {"name": data_file.original_name},
        data_file=data_file,
    )

    # Conversion à la volée vers un autre format si demandé.
    fmt = request.GET.get("format", "").strip().lower()
    if fmt in {"csv", "xlsx", "xls"} and fmt != current_ext:
        try:
            df = restore_semantic_types(
                read_dataframe(data_file.cleaned_file.path)
            )
            if fmt == "csv":
                buffer = io.BytesIO()
                df.to_csv(
                    buffer, index=False, sep=";", encoding="utf-8-sig"
                )
                buffer.seek(0)
                return FileResponse(
                    buffer,
                    as_attachment=True,
                    filename=f"{Path(filename).stem}.csv",
                    content_type=CONTENT_TYPES[".csv"],
                )
            buffer = io.BytesIO()
            df.to_excel(buffer, index=False)
            buffer.seek(0)
            return FileResponse(
                buffer,
                as_attachment=True,
                filename=f"{Path(filename).stem}.xlsx",
                content_type=CONTENT_TYPES[".xlsx"],
            )
        except Exception as exc:  # noqa: BLE001 — message utilisateur clair
            messages.error(
                request,
                _("Impossible de convertir le fichier : %(error)s")
                % {"error": user_error(exc, "conversion du fichier")},
            )
            return redirect("core:dataset_detail", pk=pk)

    content_type = CONTENT_TYPES.get(
        Path(filename).suffix.lower(), "application/octet-stream"
    )
    return FileResponse(
        data_file.cleaned_file.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type=content_type,
    )


def download_original(request, pk):
    """Télécharge le fichier d'origine (avant nettoyage)."""
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    if not _require_download(request, data_file):
        return redirect("core:dataset_detail", pk=pk)

    if not data_file.file:
        messages.error(request, _("Aucun fichier d'origine n'est disponible."))
        return redirect("core:dataset_detail", pk=pk)

    filename = Path(data_file.file.name).name
    content_type = CONTENT_TYPES.get(
        Path(filename).suffix.lower(), "application/octet-stream"
    )
    return FileResponse(
        data_file.file.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type=content_type,
    )


def archive_dataset(request, pk):
    return _set_dataset_archived(request, pk, archived=True)


def restore_dataset(request, pk):
    return _set_dataset_archived(request, pk, archived=False)


def _set_dataset_archived(request, pk, archived):
    """Archive ou restaure un fichier sans modifier ses données."""
    if request.method != "POST":
        return redirect("core:index")

    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    name = data_file.original_name
    data_file.archived_at = timezone.now() if archived else None
    data_file.archive_exempt_from_auto = not archived
    data_file.save(update_fields=["archived_at", "archive_exempt_from_auto"])
    activity_service.record(
        request.user,
        ActivityLog.Action.ARCHIVE if archived else ActivityLog.Action.RESTORE,
        (
            _("Archivage de « %(name)s »")
            if archived
            else _("Restauration de « %(name)s »")
        )
        % {"name": name},
        data_file=data_file,
    )
    if archived:
        messages.success(request, _("Fichier « %(name)s » archivé.") % {"name": name})
        return redirect(f"{reverse('core:index')}?archive=1")

    messages.success(request, _("Fichier « %(name)s » restauré.") % {"name": name})
    return redirect("core:index")


def delete_dataset(request, pk):
    """Supprime un fichier de données et tous ses fichiers associés.

    Suppression explicite (POST avec confirmation) : l'utilisateur garde
    toujours la main. Les fichiers physiques (original, nettoyé, rapport,
    journal) sont également supprimés du stockage.
    """
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    if request.method != "POST":
        return redirect("core:dataset_detail", pk=pk)
    if not _require_edit(request, data_file):
        return redirect("core:dataset_detail", pk=pk)

    name = data_file.original_name
    for field in (
        data_file.file,
        data_file.cleaned_file,
        data_file.report_file,
        data_file.change_log_file,
    ):
        if field:
            field.delete(save=False)
    api_service.trigger(
        request.user, Webhook.Event.DELETE, data_file=data_file
    )
    activity_service.record(
        request.user,
        ActivityLog.Action.DELETE,
        _("Suppression de « %(name)s »") % {"name": name},
        level=ActivityLog.Level.WARNING,
    )
    data_file.delete()

    messages.success(request, _("Fichier « %(name)s » supprimé.") % {"name": name})
    return redirect("core:index")


def download_report(request, pk):
    """Télécharge le rapport de nettoyage."""
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    if not _require_download(request, data_file):
        return redirect("core:dataset_detail", pk=pk)

    if not data_file.report_file:
        messages.error(request, _("Aucun rapport de nettoyage n'est disponible."))
        return redirect("core:dataset_detail", pk=pk)

    filename = Path(data_file.report_file.name).name
    return FileResponse(
        data_file.report_file.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type="text/markdown; charset=utf-8",
    )


def view_report(request, pk):
    """Affiche le rapport de nettoyage directement dans le navigateur.

    Le rapport est stocké en Markdown ; il est converti en HTML via
    :func:`core.services.markdown.markdown_to_html` pour une lecture
    confortable, sans téléchargement.
    """
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    if not data_file.report_file:
        messages.error(request, _("Aucun rapport de nettoyage n'est disponible."))
        return redirect("core:dataset_detail", pk=pk)

    try:
        markdown_text = Path(data_file.report_file.path).read_text(
            encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001 — message utilisateur clair
        messages.error(
            request,
            _("Impossible de lire le rapport : %(error)s")
            % {"error": user_error(exc, "lecture du rapport")},
        )
        return redirect("core:dataset_detail", pk=pk)

    context = {
        "data_file": data_file,
        "report_html": markdown_to_html(markdown_text),
    }
    return render(request, "core/report_view.html", context)


def download_report_html(request, pk):
    """Télécharge le rapport converti en HTML autonome (stylé).

    Les graphiques statistiques (matplotlib/seaborn) sont embarqués en URI
    ``data:`` : le document reste autonome, sans fichier externe.
    """
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    if not _require_download(request, data_file):
        return redirect("core:dataset_detail", pk=pk)

    if not data_file.report_file:
        messages.error(request, _("Aucun rapport de nettoyage n'est disponible."))
        return redirect("core:dataset_detail", pk=pk)

    try:
        markdown_text = Path(data_file.report_file.path).read_text(
            encoding="utf-8"
        )
    except Exception as exc:  # noqa: BLE001 — message utilisateur clair
        messages.error(
            request,
            _("Impossible de lire le rapport : %(error)s")
            % {"error": user_error(exc, "lecture du rapport")},
        )
        return redirect("core:dataset_detail", pk=pk)

    body = markdown_to_html(markdown_text)
    body += _charts_html(data_file)
    title = html.escape(data_file.original_name)
    document = _wrap_html_document(title, body)

    buffer = io.BytesIO(document.encode("utf-8"))
    stem = Path(data_file.report_file.name).stem
    return FileResponse(
        buffer,
        as_attachment=True,
        filename=f"{stem}.html",
        content_type="text/html; charset=utf-8",
    )


def _charts_html(data_file):
    """Section HTML des graphiques, images embarquées en URI ``data:``."""
    df = _cleaned_dataframe(data_file)
    if df is None:
        return ""

    try:
        dashboard = build_dashboard(df)
        charts = charts_as_data_uris(df, dashboard, theme="light")
    except Exception:  # noqa: BLE001 — le rapport reste valable sans graphiques
        return ""

    if not charts:
        return ""

    parts = [
        f"<h2>{html.escape(_('Visualisations statistiques'))}</h2>",
        "<p>"
        + html.escape(
            _(
                "Graphiques générés avec matplotlib et seaborn à partir des "
                "données nettoyées."
            )
        )
        + "</p>",
    ]
    for chart in charts:
        parts.append(
            f'<figure class="chart">'
            f'<img src="{chart["data_uri"]}" alt="{html.escape(chart["title"])}">'
            f"<figcaption>{html.escape(chart['title'])} — "
            f"{html.escape(chart['description'])}</figcaption>"
            f"</figure>"
        )
    return "\n".join(parts)


def _wrap_html_document(title, body):
    """Enveloppe un fragment HTML dans un document autonome et stylé."""
    language = (translation.get_language() or "fr").replace("_", "-")
    return f"""<!DOCTYPE html>
<html lang="{html.escape(language)}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{html.escape(_("Rapport"))} — {title}</title>
<style>
  body {{ font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
         max-width: 960px; margin: 2rem auto; padding: 0 1rem; color: #212529; }}
  h1, h2, h3 {{ color: #0d6efd; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #dee2e6; padding: 0.5rem 0.75rem; text-align: left; }}
  th {{ background: #f8f9fa; }}
  code {{ background: #f1f3f5; padding: 0.1rem 0.3rem; border-radius: 0.25rem; }}
  hr {{ border: none; border-top: 1px solid #dee2e6; margin: 1.5rem 0; }}
  figure.chart {{ margin: 2rem 0; text-align: center; }}
  figure.chart img {{ max-width: 100%; height: auto;
                      border: 1px solid #dee2e6; border-radius: 0.75rem;
                      box-shadow: 0 8px 24px -14px rgba(15, 23, 42, 0.35); }}
  figure.chart figcaption {{ margin-top: 0.6rem; font-size: 0.85rem;
                             color: #6c757d; }}
  @media print {{ figure.chart {{ break-inside: avoid; }}
                  figure.chart img {{ box-shadow: none; }} }}
</style>
</head>
<body>
{body}
</body>
</html>"""


def download_change_log(request, pk):
    """Télécharge le journal des modifications (change_log)."""
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    if not _require_download(request, data_file):
        return redirect("core:dataset_detail", pk=pk)

    if not data_file.change_log_file:
        messages.error(
            request, _("Aucun journal des modifications n'est disponible.")
        )
        return redirect("core:dataset_detail", pk=pk)

    filename = Path(data_file.change_log_file.name).name
    return FileResponse(
        data_file.change_log_file.open("rb"),
        as_attachment=True,
        filename=filename,
        content_type="text/csv; charset=utf-8",
    )


def download_json(request, pk):
    """Télécharge le fichier nettoyé au format JSON.

    Le JSON est un tableau d'objets (une clé par colonne), encodé en UTF-8.
    Les valeurs non sérialisables (NaN, timestamps…) sont converties en
    ``None`` afin de produire un JSON strictement valide.
    """
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    if not _require_download(request, data_file):
        return redirect("core:dataset_detail", pk=pk)

    if not data_file.cleaned_file:
        messages.error(request, _("Aucun fichier nettoyé n'est disponible."))
        return redirect("core:dataset_detail", pk=pk)

    try:
        df = restore_semantic_types(
            read_dataframe(data_file.cleaned_file.path)
        )
    except Exception as exc:  # noqa: BLE001 — message utilisateur clair
        messages.error(
            request,
            _("Impossible de lire le fichier : %(error)s")
            % {"error": user_error(exc, "relecture du fichier nettoyé")},
        )
        return redirect("core:dataset_detail", pk=pk)

    records = df.to_dict(orient="records")
    # Sérialisation robuste : remplace les valeurs non JSON (NaN, NaT…)
    # par ``None``, sans quoi ``json.dumps`` produirait un JSON invalide.
    cleaned_records = json.loads(
        json.dumps(records, default=_json_default, ensure_ascii=False)
    )
    payload = json.dumps(
        cleaned_records, ensure_ascii=False, indent=2
    ).encode("utf-8")

    stem = Path(data_file.original_name or "donnees").stem
    return FileResponse(
        io.BytesIO(payload),
        as_attachment=True,
        filename=f"{stem}_nettoye.json",
        content_type="application/json; charset=utf-8",
    )


def _json_default(value):
    """Convertit une valeur non sérialisable en JSON en ``None``."""
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return None


def review_duplicate(request, pk):
    """Applique une décision manuelle sur un doublon potentiel.

    L'action n'est jamais appliquée sans interaction explicite de
    l'utilisateur (POST avec ``action`` + confirmation dans l'interface).
    Après application, le DataFrame final est mis à jour, les ``id``
    renumérotés (``ancien_id`` conservé), le journal complété, puis on
    redirige vers la page de détail qui recalcule score/dashboard/validation.
    """
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    if request.method != "POST":
        return redirect("core:dataset_detail", pk=pk)

    if not data_file.cleaned_file:
        messages.error(request, _("Aucun fichier nettoyé n'est disponible."))
        return redirect("core:dataset_detail", pk=pk)

    action = request.POST.get("action", "")
    ancien_ids = [
        x for x in request.POST.get("ancien_ids", "").split(",") if x.strip()
    ]

    valid_actions = {"keep_a", "keep_b", "merge", "keep_both", "ignore"}
    if action not in valid_actions or not ancien_ids:
        messages.error(request, _("Action invalide."))
        return redirect("core:dataset_detail", pk=pk)

    try:
        cleaned_df = restore_semantic_types(
            read_dataframe(data_file.cleaned_file.path)
        )
        new_df, entries = apply_decision(cleaned_df, ancien_ids, action)

        # Renumérotation des id (ancien_id conservé) via le moteur existant.
        if action in {"keep_a", "keep_b", "merge"}:
            renumbered = DataCleaner(new_df)
            renumbered.renumber_identifiers()
            new_df = renumbered.result

        # Écrit le DataFrame final dans le fichier nettoyé (même chemin).
        overwrite_cleaned_file(data_file, new_df)

        # Ajoute les entrées manuelles au journal (schéma strict conservé).
        append_change_log(data_file, entries)
    except Exception as exc:  # noqa: BLE001 — message utilisateur clair
        messages.error(
            request,
            _("Impossible d'appliquer la décision : %(error)s")
            % {"error": user_error(exc, "application de la décision")},
        )
        return redirect("core:dataset_detail", pk=pk)

    messages.success(request, _("Décision appliquée avec succès."))
    return redirect("core:dataset_detail", pk=pk)


# --- Langue de l'interface ------------------------------------------------


@login_not_required
@require_POST
def set_language(request):
    """Mémorise la langue choisie puis revient à la page d'origine.

    Le choix est stocké dans la session (``django_language``) et appliqué
    immédiatement ; il est aussi persisté dans le profil pour être restauré
    lors des connexions suivantes.
    """
    code = request.POST.get("language", "").strip().lower().replace("_", "-")
    allowed = {lang["code"].lower() for lang in settings.SITE_LANGUAGES}

    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER", "")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = "/"

    if code not in allowed:
        return redirect(next_url)

    translation.activate(code)
    request.session["django_language"] = code

    if request.user.is_authenticated:
        profile_obj, _created = Profile.objects.get_or_create(user=request.user)
        if profile_obj.language != code:
            profile_obj.language = code
            profile_obj.save(update_fields=["language"])

    # Le cookie prend le relais quand la session expire (visiteur anonyme).
    response = redirect(next_url)
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        code,
        max_age=settings.LANGUAGE_COOKIE_AGE,
        path=settings.LANGUAGE_COOKIE_PATH,
        domain=settings.LANGUAGE_COOKIE_DOMAIN,
        secure=settings.LANGUAGE_COOKIE_SECURE,
        httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
    )
    return response


# --- Authentification -----------------------------------------------------


@login_not_required
def signup(request):
    """Création de compte utilisateur."""
    if request.user.is_authenticated:
        return redirect("core:index")

    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, _("Bienvenue %(username)s !") % {"username": user.username})
            return redirect("core:index")
    else:
        form = SignUpForm()

    return render(request, "core/signup.html", {"form": form})


# --- Profil utilisateur ----------------------------------------------------


@login_required
def profile(request):
    """Consultation et modification du profil de l'utilisateur connecté."""
    profile_obj, _created = Profile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile_obj)
        if form.is_valid():
            form.save()
            messages.success(request, gettext("Votre profil a été mis à jour."))
            return redirect("core:profile")
    else:
        form = ProfileForm(instance=profile_obj)

    data_files = DataFile.objects.filter(owner=request.user)
    cleaned = data_files.filter(status=DataFile.Status.CLEANED)
    context = {
        "form": form,
        "profile": profile_obj,
        "completion": profile_obj.completion,
        "stats": {
            "files": data_files.count(),
            "cleaned": cleaned.count(),
            "rules": CleaningRule.objects.filter(owner=request.user).count(),
        },
        "recent_files": data_files[:5],
        "recent_rules": CleaningRule.objects.filter(owner=request.user)[:5],
    }
    return render(request, "core/profile.html", context)


@login_required
@require_POST
def profile_avatar_delete(request):
    """Supprime la photo de profil et revient à la page de profil."""
    profile_obj, _created = Profile.objects.get_or_create(user=request.user)
    if profile_obj.avatar:
        profile_obj.avatar.delete(save=True)
        messages.success(request, _("Votre photo de profil a été supprimée."))
    return redirect("core:profile")


@login_required
def profile_password(request):
    """Changement de mot de passe depuis la page de profil."""
    if request.method == "POST":
        form = StyledPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            messages.success(
                request, _("Votre mot de passe a été modifié. Vos autres sessions restent actives.")
            )
            return redirect("core:profile")
    else:
        form = StyledPasswordChangeForm(request.user)

    return render(request, "core/profile_password.html", {"form": form})


@login_required
def profile_export(request):
    """Exporte les données du compte au format JSON (portabilité)."""
    profile_obj, _created = Profile.objects.get_or_create(user=request.user)
    data_files = DataFile.objects.filter(owner=request.user)
    rules = CleaningRule.objects.filter(owner=request.user)

    def dimensions(data_file):
        """Dimensions du fichier (nettoyé si disponible), sans planter si illisible."""
        source = data_file.cleaned_file or data_file.file
        if not source:
            return None, None
        try:
            df = read_dataframe(source.path)
        except Exception:
            return None, None
        return len(df), df.shape[1]

    fichiers = []
    for data_file in data_files:
        lignes, colonnes = dimensions(data_file)
        fichiers.append(
            {
                "nom": data_file.original_name,
                "statut": data_file.get_status_display(),
                "lignes": lignes,
                "colonnes": colonnes,
                "televerse_le": data_file.created_at.isoformat(),
            }
        )

    payload = {
        "exporte_le": timezone.now().isoformat(),
        "compte": {
            "nom_utilisateur": request.user.username,
            "prenom": request.user.first_name,
            "nom": request.user.last_name,
            "email": request.user.email,
            "date_inscription": request.user.date_joined.isoformat(),
            "derniere_connexion": (
                request.user.last_login.isoformat() if request.user.last_login else None
            ),
            "administrateur": request.user.is_staff,
        },
        "profil": {
            "presentation": profile_obj.bio,
            "fonction": profile_obj.job_title,
            "organisation": profile_obj.organisation,
            "localisation": profile_obj.location,
            "site_web": profile_obj.website,
            "theme": profile_obj.theme_preference,
            "format_date": profile_obj.date_format,
            "notifications_email": profile_obj.email_notifications,
            "profil_public": profile_obj.public_profile,
            "photo": profile_obj.avatar.url if profile_obj.avatar else None,
        },
        "fichiers": fichiers,
        "regles": [
            {
                "nom": r.name,
                "operation": r.get_operation_display(),
                "colonne": r.column,
                "active": r.is_active,
            }
            for r in rules
        ],
    }

    response = JsonResponse(payload, json_dumps_params={"ensure_ascii": False, "indent": 2})
    response["Content-Disposition"] = (
        f'attachment; filename="datazen-{request.user.username}-profil.json"'
    )
    return response


@login_required
@require_POST
def profile_delete(request):
    """Supprime définitivement le compte et toutes ses données."""
    user = request.user
    if user.is_superuser:
        messages.error(
            request,
            _("Un compte administrateur ne peut pas être supprimé depuis cette page."),
        )
        return redirect("core:profile")

    if request.POST.get("confirmation", "").strip() != user.username:
        messages.error(
            request,
            _("La confirmation ne correspond pas à votre nom d'utilisateur : suppression annulée."),
        )
        return redirect("core:profile")

    username = user.username
    logout(request)
    user.delete()
    messages.success(request, _("Le compte « %(username)s » a été supprimé.") % {"username": username})
    return redirect("core:index")


def profile_public(request, username):
    """Profil public d'un utilisateur, si celui-ci l'a autorisé."""
    user = get_object_or_404(User, username=username)
    profile_obj, _created = Profile.objects.get_or_create(user=user)

    if not profile_obj.public_profile and request.user != user:
        messages.error(request, _("Ce profil n'est pas public."))
        return redirect("core:index")

    data_files = DataFile.objects.filter(owner=user)
    context = {
        "profile_user": user,
        "profile": profile_obj,
        "stats": {
            "files": data_files.count(),
            "cleaned": data_files.filter(status=DataFile.Status.CLEANED).count(),
            "rules": CleaningRule.objects.filter(owner=user).count(),
        },
    }
    return render(request, "core/profile_public.html", context)


# --- Règles de nettoyage personnalisées -----------------------------------


@login_required
def rules_list(request):
    """Liste et création des règles de nettoyage personnalisées."""
    if request.method == "POST":
        if not _require_edit(request):
            return redirect("core:rules_list")
        form = CleaningRuleForm(request.POST)
        if form.is_valid():
            rule = form.save(commit=False)
            rule.owner = request.user
            rule.save()
            activity_service.record(
                request.user,
                ActivityLog.Action.RULE_CREATE,
                _("Création de la règle « %(name)s »") % {"name": rule.name},
                level=ActivityLog.Level.SUCCESS,
            )
            messages.success(request, _("Règle « %(name)s » créée.") % {"name": rule.name})
            return redirect("core:rules_list")
    else:
        form = CleaningRuleForm()

    context = {
        "form": form,
        "rules": _visible_rules(request.user),
        "operations": CleaningRule.Operation.choices,
    }
    return render(request, "core/rules.html", context)


@login_required
@require_POST
def rule_delete(request, pk):
    """Supprime une règle de nettoyage."""
    rule = get_object_or_404(CleaningRule, pk=pk)
    if not (
        request.user.is_superuser or rule.owner_id == request.user.pk
    ):
        messages.error(request, _("Vous n'avez pas accès à cette règle."))
        return redirect("core:rules_list")

    name = rule.name
    rule.delete()
    activity_service.record(
        request.user,
        ActivityLog.Action.RULE_DELETE,
        _("Suppression de la règle « %(name)s »") % {"name": name},
        level=ActivityLog.Level.WARNING,
    )
    messages.success(request, _("Règle « %(name)s » supprimée.") % {"name": name})
    return redirect("core:rules_list")


@login_required
@require_POST
def rule_toggle(request, pk):
    """Active ou désactive une règle de nettoyage."""
    rule = get_object_or_404(CleaningRule, pk=pk)
    if not (
        request.user.is_superuser or rule.owner_id == request.user.pk
    ):
        messages.error(request, _("Vous n'avez pas accès à cette règle."))
        return redirect("core:rules_list")

    rule.is_active = not rule.is_active
    rule.save(update_fields=["is_active", "updated_at"])
    state = _("activée") if rule.is_active else _("désactivée")
    messages.success(request, _("Règle « %(name)s » %(state)s.") % {"name": rule.name, "state": state})
    return redirect("core:rules_list")
