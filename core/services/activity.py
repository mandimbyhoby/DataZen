"""Journal d'activité : enregistrement et lecture des actions utilisateur.

Le journal est volontairement « best effort » : une erreur d'écriture ne doit
jamais faire échouer l'action métier en cours (nettoyage, export, suppression).
Toutes les entrées sont donc créées dans un bloc protégé.
"""

from __future__ import annotations

import logging

from django.utils.translation import gettext

from ..models import ActivityLog, DataFile

logger = logging.getLogger(__name__)


def record(
    user,
    action,
    message="",
    data_file=None,
    level=ActivityLog.Level.INFO,
    detail="",
):
    """Enregistre une activité et renvoie l'entrée créée (ou ``None``).

    ``message`` est un libellé **déjà traduit** : le journal reste lisible tel
    qu'il a été vu par l'utilisateur, même si les traductions évoluent.
    """
    try:
        return ActivityLog.objects.create(
            owner=user if getattr(user, "is_authenticated", False) else None,
            data_file=data_file if isinstance(data_file, DataFile) else None,
            action=action,
            level=level,
            message=str(message)[:255],
            detail=str(detail),
        )
    except Exception:  # noqa: BLE001 — le journal ne doit jamais bloquer l'action
        logger.exception("Impossible d'enregistrer l'activité %s", action)
        return None


def recent_activities(user, limit=12):
    """Dernières activités visibles par l'utilisateur (jamais ``None``)."""
    return list(visible_activities(user)[:limit])


def visible_activities(user):
    """Requête des activités visibles : tout pour un superutilisateur, sinon les siennes."""
    queryset = ActivityLog.objects.select_related("data_file")
    if user.is_superuser:
        return queryset
    return queryset.filter(owner=user)


def activity_stats(user):
    """Compteurs par action, pour les puces de filtre de la page d'activité."""
    from django.db.models import Count

    rows = (
        visible_activities(user)
        .values("action")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    labels = dict(ActivityLog.Action.choices)
    items = [
        {
            "action": row["action"],
            "label": labels.get(row["action"], row["action"]),
            "count": row["total"],
        }
        for row in rows
    ]
    return {"total": visible_activities(user).count(), "by_action": items}


def summarize_deletions(activities):
    """Résumé lisible d'une liste d'activités (compteurs par action)."""
    counts = {}
    for activity in activities:
        counts[activity.action] = counts.get(activity.action, 0) + 1
    labels = dict(ActivityLog.Action.choices)
    return [
        {"label": labels.get(action, action), "count": count}
        for action, count in sorted(counts.items(), key=lambda item: -item[1])
    ]


def cleanup_activities(user=None, days=180):
    """Purge les activités plus anciennes que ``days`` jours.

    Utilisé par la commande de gestion ``purge_activities`` ; renvoie le nombre
    d'entrées supprimées.
    """
    from datetime import timedelta

    from django.utils import timezone

    cutoff = timezone.now() - timedelta(days=days)
    queryset = ActivityLog.objects.filter(created_at__lt=cutoff)
    if user is not None:
        queryset = queryset.filter(owner=user)
    deleted, _details = queryset.delete()
    return deleted


def describe_cleaning(data_file, quality_before=None, quality_after=None):
    """Message d'activité décrivant un nettoyage terminé."""
    parts = [gettext("Nettoyage du fichier « %(name)s »") % {"name": data_file.original_name}]
    if quality_before is not None and quality_after is not None:
        parts.append(
            gettext("score %(before)s → %(after)s")
            % {"before": quality_before, "after": quality_after}
        )
    return " · ".join(parts)
