"""Exécution des nettoyages planifiés.

Une planification ne contient pas de copie du pipeline : elle mémorise les
options choisies et délègue au :func:`core.services.async_runner.start_cleaning`
habituel. Un traitement planifié et un traitement lancé à la main produisent
donc rigoureusement le même résultat.

``run_due_schedules`` est appelée par la commande de gestion
``run_schedules``, prévue pour un ordonnanceur système (cron, Planificateur de
tâches Windows) : l'application n'embarque volontairement pas de démon.
"""
import logging

from django.utils import timezone

from ..models import ActivityLog, CleaningSchedule, CleaningRule
from . import activity as activity_service
from .async_runner import start_cleaning

logger = logging.getLogger(__name__)


def due_schedules(now=None):
    """Planifications actives dont l'échéance est atteinte."""
    return CleaningSchedule.objects.filter(
        is_active=True, next_run_at__lte=now or timezone.now()
    ).select_related("data_file", "owner")


def rules_payload(schedule):
    """Reconstruit les règles personnalisées attachées à une planification.

    Les règles peuvent avoir été supprimées entre-temps : celles qui manquent
    sont simplement ignorées, plutôt que de faire échouer le nettoyage.
    """
    ids = list(schedule.rule_ids or [])
    if not ids:
        return []
    rules = CleaningRule.objects.filter(pk__in=ids, is_active=True)
    return [
        {
            "operation": rule.operation,
            "column": rule.column,
            "value": rule.value,
        }
        for rule in rules
    ]


def run_schedule(schedule, session_key=None):
    """Lance le nettoyage d'une planification et renvoie un compte rendu.

    Le résultat est un dictionnaire ``{"ok": bool, "error": str}`` : l'appelant
    décide comment le présenter (message d'interface ou journal du serveur).
    """
    data_file = schedule.data_file
    try:
        start_cleaning(
            data_file.pk,
            schedule.options or {},
            rules=rules_payload(schedule),
            session_key=session_key,
            language=None,
        )
    except Exception as exc:  # noqa: BLE001 — une planification ne doit pas bloquer la file
        logger.exception("Planification %s : lancement impossible", schedule.pk)
        schedule.last_status = "error"
        schedule.run_count += 1
        schedule.last_run_at = timezone.now()
        schedule.next_run_at = schedule.compute_next_run()
        schedule.save(
            update_fields=["last_status", "run_count", "last_run_at", "next_run_at"]
        )
        return {"ok": False, "error": str(exc)}

    schedule.last_status = "started"
    schedule.run_count += 1
    schedule.last_run_at = timezone.now()
    schedule.next_run_at = schedule.compute_next_run()
    schedule.save(
        update_fields=["last_status", "run_count", "last_run_at", "next_run_at"]
    )
    return {"ok": True, "error": ""}


def run_due_schedules(now=None, session_key=None):
    """Exécute toutes les planifications dues et renvoie leur nombre.

    Chaque planification est traitée indépendamment : une erreur sur l'une
    n'empêche pas les suivantes de partir.
    """
    schedules = list(due_schedules(now))
    for schedule in schedules:
        result = run_schedule(schedule, session_key)
        activity_service.record(
            schedule.owner,
            ActivityLog.Action.CLEAN,
            (
                f"Nettoyage planifié lancé pour « {schedule.data_file.original_name} »"
                if result["ok"]
                else f"Échec du nettoyage planifié pour « {schedule.data_file.original_name} »"
            ),
            data_file=schedule.data_file,
            level=ActivityLog.Level.INFO if result["ok"] else ActivityLog.Level.DANGER,
        )
    return len(schedules)
