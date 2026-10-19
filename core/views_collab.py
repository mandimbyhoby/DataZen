"""Vues des fonctionnalités collaboratives et d'automatisation.

Ce module complète :mod:`core.views` et :mod:`core.views_pro` :

- **rôles** : gestion des droits des comptes par un administrateur ;
- **partage** : partage nominatif ou par lien public, en lecture seule ;
- **versions** : historique des nettoyages, comparaison et restauration ;
- **planification** : nettoyages récurrents d'un jeu de données ;
- **lots** : nettoyage de plusieurs jeux de données en une fois.

Toutes les vues exigent un compte et vérifient les droits côté serveur : un
gabarit qui masque un bouton ne protège rien.
"""
from __future__ import annotations

from pathlib import Path

from django.contrib import messages
from django.contrib.auth.decorators import login_not_required, login_required
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from .errors import user_error
from .forms import BatchCleaningForm, ScheduleForm, ShareForm
from .models import (
    ActivityLog,
    CleaningSchedule,
    DataFile,
    DatasetShare,
    DatasetVersion,
    Profile,
)
from .services import activity as activity_service
from .services import batch as batch_service
from .services import permissions as permissions_service
from .services import schedules as schedule_service
from .services import versions as version_service
from .services.operations import render_operations
from .services.reader import dataframe_to_rows, read_dataframe
from .views import (
    _get_visible_file,
    _require_edit,
    _selected_rules,
    _theme,
    _visible_files,
    _visible_rules,
)


# --- Rôles ----------------------------------------------------------------


@login_required
def roles(request):
    """Gestion des rôles : réservée aux administrateurs."""
    if not permissions_service.is_admin(request.user):
        messages.error(request, _("Cette page est réservée aux administrateurs."))
        return redirect("core:index")

    if request.method == "POST":
        target = get_object_or_404(User, pk=request.POST.get("user_id"))
        role = request.POST.get("role", "")
        if role not in Profile.Role.values:
            messages.error(request, _("Rôle inconnu."))
            return redirect("core:roles")
        if target == request.user:
            # Se retirer soi-même ses droits couperait l'accès à cette page.
            messages.error(request, _("Vous ne pouvez pas modifier votre propre rôle."))
            return redirect("core:roles")

        profile, _created = Profile.objects.get_or_create(user=target)
        previous = profile.role
        profile.role = role
        profile.save(update_fields=["role", "updated_at"])
        activity_service.record(
            request.user,
            ActivityLog.Action.RULE_CREATE,
            _("Rôle de « %(name)s » : %(before)s → %(after)s")
            % {
                "name": target.username,
                "before": Profile.Role(previous).label,
                "after": Profile.Role(role).label,
            },
            level=ActivityLog.Level.SUCCESS,
        )
        messages.success(
            request,
            _("Rôle de « %(name)s » mis à jour.") % {"name": target.username},
        )
        return redirect("core:roles")

    query = request.GET.get("q", "").strip()
    users = User.objects.select_related("profile").order_by("username")
    if query:
        users = users.filter(
            Q(username__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(email__icontains=query)
        )

    counts = {
        row["owner_id"]: row["total"]
        for row in DataFile.objects.values("owner_id").annotate(total=Count("id"))
    }
    user_rows = [
        {"user": user, "files_count": counts.get(user.pk, 0)} for user in users
    ]

    return render(
        request,
        "core/roles.html",
        {
            "users": user_rows,
            "role_choices": Profile.Role.choices,
            "query": query,
            "theme": _theme(request),
        },
    )


# --- Partage --------------------------------------------------------------

SHARED_PREVIEW_LIMIT = 20


def _owned_or_admin(request, pk):
    """Récupère un fichier que l'utilisateur peut partager.

    Seul le propriétaire (ou un administrateur) décide des partages : un
    destinataire ne peut pas re-partager ce qu'il consulte.
    """
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return None
    if (
        data_file.owner_id != request.user.pk
        and not permissions_service.is_admin(request.user)
        and not request.user.is_superuser
    ):
        messages.error(request, _("Seul le propriétaire peut gérer les partages."))
        return None
    return data_file


@login_required
def share_dataset(request, pk):
    """Liste et création des partages d'un jeu de données."""
    data_file = _owned_or_admin(request, pk)
    if data_file is None:
        return redirect("core:index")

    if request.method == "POST":
        if not _require_edit(request, data_file):
            return redirect("core:share_dataset", pk=pk)
        form = ShareForm(request.POST, data_file=data_file)
        if form.is_valid():
            share = DatasetShare.objects.create(
                data_file=data_file,
                shared_with=form.cleaned_data["shared_with"],
                permission=form.cleaned_data["permission"],
                expires_at=form.cleaned_data["expires_at"],
                token=permissions_service.new_share_token(),
                created_by=request.user,
            )
            target = share.shared_with.username if share.shared_with_id else _("lien public")
            activity_service.record(
                request.user,
                ActivityLog.Action.UPLOAD,
                _("Partage de « %(name)s » avec %(target)s")
                % {"name": data_file.original_name, "target": target},
                data_file=data_file,
                level=ActivityLog.Level.SUCCESS,
            )
            messages.success(request, _("Partage créé."))
            return redirect("core:share_dataset", pk=pk)
    else:
        form = ShareForm(data_file=data_file)

    share_url = ""
    new_share = DatasetShare.objects.filter(data_file=data_file).order_by("-id").first()
    if new_share is not None and new_share.is_public_link:
        share_url = request.build_absolute_uri(
            reverse("core:shared_dataset", args=[new_share.token])
        )

    return render(
        request,
        "core/share.html",
        {
            "data_file": data_file,
            "form": form,
            "shares": data_file.shares.select_related("shared_with").all(),
            "share_url": share_url,
            "theme": _theme(request),
        },
    )


@login_required
@require_POST
def share_revoke(request, pk, share_id):
    """Révoque un partage : le destinataire perd immédiatement l'accès."""
    data_file = _owned_or_admin(request, pk)
    if data_file is None:
        return redirect("core:index")
    share = get_object_or_404(DatasetShare, pk=share_id, data_file=data_file)
    share.delete()
    messages.success(request, _("Partage révoqué."))
    return redirect("core:share_dataset", pk=pk)


@login_not_required
def shared_dataset(request, token):
    """Accès à un jeu de données via un lien de partage public.

    Le jeton est le seul secret : il est opaque, révocable et peut expirer. Le
    lien ouvre la page de détail en lecture seule, sans authentification. La vue
    est marquée ``login_not_required`` car l'accès est prouvé par le jeton, pas
    par une session : ``LoginRequiredMiddleware`` redirigerait sinon tout
    visiteur anonyme vers la page de connexion.
    """
    share = permissions_service.share_for_token(token)
    if share is None:
        messages.error(request, _("Ce lien de partage est invalide ou a expiré."))
        return redirect("core:login")

    data_file = share.data_file
    context = {
        "data_file": data_file,
        "share": share,
        "shared_view": True,
        "theme": _theme(request),
    }
    # Un lien public sans session : on n'expose ni les options de nettoyage ni
    # les actions, uniquement la prévisualisation et le téléchargement.
    source = data_file.cleaned_file or data_file.file
    try:
        df = read_dataframe(source.path)
        context["preview_rows"] = dataframe_to_rows(df, limit=SHARED_PREVIEW_LIMIT)
        context["columns"] = list(df.columns)
        context["row_count"] = len(df)
    except Exception as exc:  # noqa: BLE001 — message utilisateur clair
        messages.error(
            request,
            _("Impossible de lire ce fichier : %(error)s")
            % {"error": user_error(exc, "lecture du fichier partagé")},
        )
        return redirect("core:login")
    return render(request, "core/shared_dataset.html", context)


@login_not_required
def shared_dataset_download(request, token):
    """Télécharge le fichier d'un partage public, si le droit le permet."""
    share = permissions_service.share_for_token(token)
    if share is None:
        messages.error(request, _("Ce lien de partage est invalide ou a expiré."))
        return redirect("core:login")
    if share.permission != DatasetShare.Permission.DOWNLOAD:
        messages.error(request, _("Ce lien ne permet pas le téléchargement."))
        return redirect("core:shared_dataset", token=token)

    data_file = share.data_file
    if not data_file.cleaned_file:
        messages.error(request, _("Aucun fichier nettoyé n'est disponible."))
        return redirect("core:shared_dataset", token=token)
    return _file_response(data_file, data_file.cleaned_file)


def _file_response(data_file, field):
    """Sert un fichier stocké en pièce jointe (téléchargement direct)."""
    path = Path(field.path)
    response = HttpResponse(path.read_bytes(), content_type="application/octet-stream")
    response["Content-Disposition"] = f'attachment; filename="{path.name}"'
    return response


# --- Versions -------------------------------------------------------------


@login_required
def dataset_versions(request, pk):
    """Historique des versions d'un jeu de données."""
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    entries = [
        {
            "version": version,
            # Les codes d'opération sont traduits ici : l'historique suit la
            # langue active même si le nettoyage date d'une autre.
            "operations": render_operations(version.operations),
        }
        for version in data_file.versions.select_related("created_by").all()
    ]

    return render(
        request,
        "core/versions.html",
        {
            "data_file": data_file,
            "entries": entries,
            "can_edit": permissions_service.can_edit(request.user),
            "theme": _theme(request),
        },
    )


@login_required
def version_download(request, pk, number):
    """Télécharge le fichier nettoyé d'une version donnée."""
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")
    if not permissions_service.can_download(request.user, data_file):
        messages.error(request, _("Ce partage ne permet pas le téléchargement."))
        return redirect("core:dataset_versions", pk=pk)

    version = get_object_or_404(DatasetVersion, data_file=data_file, number=number)
    if not version.cleaned_file:
        messages.error(request, _("Le fichier de cette version n'est plus disponible."))
        return redirect("core:dataset_versions", pk=pk)
    return _file_response(data_file, version.cleaned_file)


@login_required
def version_compare(request, pk):
    """Compare deux versions (ou la version courante) d'un jeu de données."""
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")

    versions = list(data_file.versions.all())
    if len(versions) < 1:
        messages.error(
            request,
            _("Aucune version enregistrée : lancez un nettoyage pour en créer une."),
        )
        return redirect("core:dataset_versions", pk=pk)

    def _pick(value, default):
        try:
            return next(v for v in versions if v.number == int(value))
        except (TypeError, ValueError, StopIteration):
            return default

    after = _pick(request.GET.get("after"), versions[0])
    before = _pick(request.GET.get("before"), versions[-1])

    comparison = None
    if before.pk != after.pk:
        try:
            comparison = version_service.compare_versions(before, after)
        except Exception as exc:  # noqa: BLE001 — message utilisateur clair
            messages.error(
                request,
                _("Impossible de comparer ces versions : %(error)s")
                % {"error": user_error(exc, "comparaison des versions")},
            )
            return redirect("core:dataset_versions", pk=pk)

    return render(
        request,
        "core/version_compare.html",
        {
            "data_file": data_file,
            "versions": versions,
            "before": before,
            "after": after,
            # Les codes sont rendus ici : l'historique suit la langue active.
            "before_operations": render_operations(before.operations),
            "after_operations": render_operations(after.operations),
            "comparison": comparison,
            "theme": _theme(request),
        },
    )


@login_required
@require_POST
def version_restore(request, pk, number):
    """Restaure une version antérieure comme version courante du dataset."""
    data_file = _get_visible_file(request, pk)
    if data_file is None:
        return redirect("core:index")
    if not _require_edit(request, data_file):
        return redirect("core:dataset_versions", pk=pk)

    version = get_object_or_404(DatasetVersion, data_file=data_file, number=number)
    try:
        version_service.restore_version(version)
    except Exception as exc:  # noqa: BLE001 — message utilisateur clair
        messages.error(
            request,
            _("Restauration impossible : %(error)s")
            % {"error": user_error(exc, "restauration de version")},
        )
        return redirect("core:dataset_versions", pk=pk)

    activity_service.record(
        request.user,
        ActivityLog.Action.RESTORE,
        _("Restauration de la version %(number)s de « %(name)s »")
        % {"number": version.number, "name": data_file.original_name},
        data_file=data_file,
        level=ActivityLog.Level.WARNING,
    )
    messages.success(
        request,
        _("Version %(number)s restaurée.") % {"number": version.number},
    )
    return redirect("core:dataset_detail", pk=pk)


# --- Planification --------------------------------------------------------


@login_required
def schedules(request):
    """Liste des nettoyages planifiés et création d'une planification."""
    if request.method == "POST":
        if not _require_edit(request):
            return redirect("core:schedules")
        form = ScheduleForm(request.POST, user=request.user)
        if form.is_valid():
            first_run = form.cleaned_data["first_run_at"] or timezone.now()
            schedule = CleaningSchedule.objects.create(
                data_file=form.cleaned_data["data_file"],
                owner=request.user,
                frequency=form.cleaned_data["frequency"],
                options=form.cleaned_options(),
                rule_ids=form.cleaned_rule_ids(),
                # La première exécution est celle choisie ; les suivantes sont
                # calculées à partir d'elle par compute_next_run().
                next_run_at=first_run,
            )
            activity_service.record(
                request.user,
                ActivityLog.Action.CLEAN,
                _("Planification créée pour « %(name)s »")
                % {"name": schedule.data_file.original_name},
                data_file=schedule.data_file,
                level=ActivityLog.Level.SUCCESS,
            )
            messages.success(request, _("Planification créée."))
            return redirect("core:schedules")
    else:
        form = ScheduleForm(user=request.user)

    return render(
        request,
        "core/schedules.html",
        {
            "form": form,
            "schedules": CleaningSchedule.objects.filter(
                owner=request.user
            ).select_related("data_file"),
            "rules": _visible_rules(request.user).filter(is_active=True),
            "can_edit": permissions_service.can_edit(request.user),
            "theme": _theme(request),
        },
    )


@login_required
@require_POST
def schedule_toggle(request, pk):
    """Active ou suspend une planification."""
    schedule = get_object_or_404(CleaningSchedule, pk=pk, owner=request.user)
    schedule.is_active = not schedule.is_active
    if schedule.is_active:
        # Réactiver une planification ne doit pas déclencher aussitôt une
        # exécution si l'échéance est passée : on repart de maintenant.
        now = timezone.now()
        if schedule.next_run_at <= now:
            schedule.next_run_at = schedule.compute_next_run(now)
    schedule.save(update_fields=["is_active", "next_run_at"])
    state = _("activée") if schedule.is_active else _("suspendue")
    messages.success(request, _("Planification %(state)s.") % {"state": state})
    return redirect("core:schedules")


@login_required
@require_POST
def schedule_delete(request, pk):
    """Supprime une planification."""
    schedule = get_object_or_404(CleaningSchedule, pk=pk, owner=request.user)
    schedule.delete()
    messages.success(request, _("Planification supprimée."))
    return redirect("core:schedules")


@login_required
@require_POST
def schedule_run_now(request, pk):
    """Exécute immédiatement une planification, sans attendre l'échéance."""
    schedule = get_object_or_404(
        CleaningSchedule.objects.select_related("data_file"),
        pk=pk,
        owner=request.user,
    )
    if not _require_edit(request, schedule.data_file):
        return redirect("core:schedules")
    result = schedule_service.run_schedule(schedule, request.session.session_key)
    if result["ok"]:
        messages.success(
            request,
            _("Nettoyage planifié de « %(name)s » lancé.")
            % {"name": schedule.data_file.original_name},
        )
    else:
        messages.error(
            request,
            _("Échec du nettoyage planifié : %(error)s")
            % {"error": result["error"]},
        )
    return redirect("core:schedules")


# --- Traitement par lots --------------------------------------------------


@login_required
def batch_cleaning(request):
    """Nettoie plusieurs jeux de données avec les mêmes options.

    La page d'accueil coche les fichiers ; cette vue les traite en série via
    le pipeline habituel. Le traitement est séquentiel à dessein : un seul
    nettoyage lourd à la fois évite de saturer le processus.
    """
    candidates = _visible_files(request.user).order_by("-created_at")

    if request.method == "POST":
        if not _require_edit(request):
            return redirect("core:batch_cleaning")
        form = BatchCleaningForm(request.POST, files=candidates)
        if form.is_valid():
            selected = list(form.cleaned_data["files"])
            options = form.cleaned_options()
            rules = _selected_rules(request)
            result = batch_service.start_batch(
                selected,
                options,
                rules=rules,
                session_key=request.session.session_key,
                language=request.LANGUAGE_CODE,
            )
            activity_service.record(
                request.user,
                ActivityLog.Action.CLEAN,
                _("Nettoyage par lots : %(count)s fichier(s) lancé(s)")
                % {"count": result["started"]},
                level=ActivityLog.Level.INFO,
            )
            messages.success(
                request,
                _("%(count)s nettoyage(s) lancé(s) en arrière-plan.")
                % {"count": result["started"]},
            )
            if result["skipped"]:
                messages.warning(
                    request,
                    _("%(count)s fichier(s) ignoré(s) : lot limité à %(limit)s.")
                    % {"count": len(result["skipped"]), "limit": batch_service.MAX_BATCH_SIZE},
                )
            return redirect("core:index")
    else:
        form = BatchCleaningForm(files=candidates)

    return render(
        request,
        "core/batch.html",
        {
            "form": form,
            "files": candidates,
            "rules": _visible_rules(request.user).filter(is_active=True),
            "can_edit": permissions_service.can_edit(request.user),
            "theme": _theme(request),
        },
    )
