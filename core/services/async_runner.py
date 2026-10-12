"""Traitement asynchrone du nettoyage (file d'attente légère par threads).

Les gros fichiers peuvent prendre plusieurs secondes à nettoyer. Pour ne pas
bloquer la requête HTTP, le nettoyage est exécuté dans un thread d'arrière-plan
tandis que la page de détail interroge la progression (polling JSON).

Ce module reste volontairement simple (``threading``) : il ne nécessite aucun
service externe (Redis, Celery) et suffit pour un déploiement mono-processus.
"""
import logging
import threading
import uuid
from importlib import import_module

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from ..models import ActivityLog, DataFile, Webhook
from . import activity as activity_service
from . import api as api_service
from .pipeline import run_cleaning

# Verrou global : un seul nettoyage lourd à la fois, pour éviter de saturer
# le process (les fichiers sont en général petits, mais restons prudents).
_QUEUE_LOCK = threading.Lock()

logger = logging.getLogger(__name__)


def _session_store(session_key):
    """Instancie le moteur de session Django pour un ``session_key`` donné."""
    engine = import_module(settings.SESSION_ENGINE)
    return engine.SessionStore(session_key=session_key)


def start_cleaning(data_file_id, options, rules=None, session_key=None, language=None):
    """Lance le nettoyage en arrière-plan et renvoie immédiatement.

    Le statut du :class:`~core.models.DataFile` passe à ``processing`` puis
    ``cleaned`` (ou ``error``). La progression est écrite dans le champ
    ``progress`` pour être interrogée par le client.
    """
    thread = threading.Thread(
        target=_run,
        args=(data_file_id, options, rules or [], session_key, language),
        daemon=True,
        name=f"datazen-clean-{data_file_id}",
    )
    thread.start()
    return thread


def _run(data_file_id, options, rules, session_key, language=None):
    """Corps du thread : exécute le pipeline et met à jour l'état."""
    close_old_connections()
    try:
        with _QUEUE_LOCK:
            data_file = DataFile.objects.get(pk=data_file_id)
            data_file.status = DataFile.Status.PROCESSING
            data_file.progress = 0
            data_file.error_message = ""
            data_file.save(
                update_fields=["status", "progress", "error_message", "updated_at"]
            )

            last_saved = {"value": -1}

            def progress(percent, message=""):
                # N'écrit en base que si la valeur a réellement changé, pour
                # limiter les accès SQL pendant le traitement.
                if percent == last_saved["value"]:
                    return
                last_saved["value"] = percent
                DataFile.objects.filter(pk=data_file_id).update(progress=percent)

            with translation.override(language):
                operations, regex_rules = run_cleaning(
                    data_file, options, rules=rules, progress=progress
                )

            if session_key:
                try:
                    store = _session_store(session_key)
                    store[f"operations_{data_file_id}"] = operations
                    store[f"regex_rules_{data_file_id}"] = regex_rules
                    store.save()
                except Exception:
                    # La session est un confort d'affichage : son échec ne
                    # doit pas invalider un nettoyage réussi.
                    pass

            DataFile.objects.filter(pk=data_file_id).update(
                status=DataFile.Status.CLEANED,
                progress=100,
                cleaned_at=timezone.now(),
            )
            with translation.override(language):
                _notify(data_file_id, Webhook.Event.CLEANING_DONE)
    except Exception as exc:  # noqa: BLE001 — l'erreur est montrée à l'utilisateur
        # La pile d'appels complète est journalisée côté serveur uniquement :
        # la rendre à l'utilisateur divulguerait les chemins du disque, les
        # versions des bibliothèques et l'organisation interne du code. On ne
        # conserve qu'un message court, rattaché à une référence loggable.
        reference = uuid.uuid4().hex[:8]
        logger.exception(
            "Nettoyage %s en échec (référence %s)", data_file_id, reference
        )
        summary = str(exc).strip().splitlines()
        detail = summary[0] if summary else exc.__class__.__name__
        # Le bloc ``except`` s'exécute après la sortie de ``translation.override`` :
        # sans cette réactivation, le message serait rendu dans la langue du
        # thread et non dans celle de l'utilisateur qui a lancé le nettoyage.
        with translation.override(language):
            error_message = (
                f"{_('Échec du nettoyage')} — {detail[:180]} "
                f"({_('référence')} {reference})"
            )
        DataFile.objects.filter(pk=data_file_id).update(
            status=DataFile.Status.ERROR,
            progress=0,
            error_message=error_message,
        )
        with translation.override(language):
            _notify(data_file_id, Webhook.Event.CLEANING_ERROR, detail=str(exc))
    finally:
        close_old_connections()


def _notify(data_file_id, event, detail=""):
    """Journalise la fin du nettoyage et déclenche les webhooks associés.

    Appelé depuis le thread d'arrière-plan : toute erreur ici est ignorée
    pour ne jamais transformer un nettoyage réussi en échec.
    """
    try:
        data_file = DataFile.objects.select_related("owner").get(pk=data_file_id)
    except DataFile.DoesNotExist:
        return

    owner = data_file.owner
    if owner is not None:
        success = event == Webhook.Event.CLEANING_DONE
        score = data_file.quality_after if success else data_file.quality_before
        message = (
            _("Nettoyage terminé : « %(name)s »") % {"name": data_file.original_name}
            if success
            else _("Échec du nettoyage de « %(name)s »") % {"name": data_file.original_name}
        )
        if success and score is not None:
            message = f"{message} — {_('score')} {score:.0f}%"
        activity_service.record(
            owner,
            ActivityLog.Action.CLEAN,
            message,
            detail=detail,
            data_file=data_file,
            level=ActivityLog.Level.SUCCESS if success else ActivityLog.Level.DANGER,
        )
        api_service.trigger(owner, event, data_file=data_file)
