"""Politique de rétention : archivage puis purge automatique des fichiers.

La rétention est configurable par utilisateur (``Profile.retention_days``) :
un fichier nettoyé plus ancien que cette durée est archivé, puis supprimé si
l'utilisateur a activé la purge automatique (``Profile.auto_purge``).

``retention_days = 0`` désactive toute purge : les données sont conservées
indéfiniment, ce qui laisse le choix à l'utilisateur.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone

from ..models import DataFile

# Nombre de jours après lequel un fichier nettoyé est archivé automatiquement
# (comportement historique de l'application).
DEFAULT_ARCHIVE_DAYS = 30


def retention_days(user):
    """Durée de conservation de l'utilisateur (0 = illimitée)."""
    profile = getattr(user, "profile", None)
    if profile is None:
        return 0
    return int(profile.retention_days or 0)


def auto_purge_enabled(user):
    """Vrai si l'utilisateur a activé la purge automatique."""
    profile = getattr(user, "profile", None)
    return bool(profile and profile.auto_purge)


def expired_files(user):
    """Fichiers nettoyés ayant dépassé la durée de conservation (hors exemptés)."""
    days = retention_days(user)
    if days <= 0:
        return DataFile.objects.none()
    cutoff = timezone.now() - timedelta(days=days)
    queryset = DataFile.objects.filter(
        status=DataFile.Status.CLEANED,
        archive_exempt_from_auto=False,
    )
    if not user.is_superuser:
        queryset = queryset.filter(owner=user)
    # Un fichier nettoyé avant l'ajout de ``cleaned_at`` n'a pas de date : on
    # se rabat alors sur sa dernière mise à jour.
    return queryset.filter(
        Q(cleaned_at__lte=cutoff)
        | Q(cleaned_at__isnull=True, updated_at__lte=cutoff)
    ).distinct()


def apply_retention(user, purge=None):
    """Applique la rétention : archive les fichiers anciens, puis les purge.

    ``purge`` force (``True``) ou interdit (``False``) la suppression ; par
    défaut c'est la préférence de l'utilisateur qui décide. Renvoie un
    dictionnaire ``{"archived": n, "purged": n, "freed_files": [...]}``.
    """
    days = retention_days(user)
    if days <= 0:
        return {"archived": 0, "purged": 0, "mode": "disabled"}

    if purge is None:
        purge = auto_purge_enabled(user)

    archive_cutoff = timezone.now() - timedelta(days=min(days, DEFAULT_ARCHIVE_DAYS))
    candidates = list(expired_files(user))
    archived = 0
    purged = 0

    for data_file in candidates:
        if data_file.archived_at is None:
            reference = data_file.cleaned_at or data_file.updated_at
            if reference and reference <= archive_cutoff:
                data_file.archived_at = reference
                data_file.save(update_fields=["archived_at"])
                archived += 1
        if purge:
            for field in (
                data_file.file,
                data_file.cleaned_file,
                data_file.report_file,
                data_file.change_log_file,
            ):
                if field:
                    field.delete(save=False)
            data_file.delete()
            purged += 1

    return {"archived": archived, "purged": purged, "mode": "purge" if purge else "archive"}
