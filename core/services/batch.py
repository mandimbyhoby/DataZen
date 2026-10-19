"""Nettoyage par lots : plusieurs jeux de données, mêmes options.

Le lot ne réimplémente rien : chaque fichier est confié au même
:func:`core.services.async_runner.start_cleaning` que le nettoyage unitaire.
Le verrou global de la file d'attente garantit qu'un seul traitement lourd
s'exécute à la fois, même si plusieurs threads sont lancés d'un coup.
"""
import logging

from .async_runner import start_cleaning

logger = logging.getLogger(__name__)

# Au-delà de cette taille, on refuse le lot : lancer des dizaines de
# traitements d'un seul clic donne l'impression que rien ne se passe.
MAX_BATCH_SIZE = 25


def start_batch(files, options, rules=None, session_key=None, language=None):
    """Lance le nettoyage d'une série de fichiers.

    Renvoie ``{"started": n, "skipped": [(nom, raison), ...]}``. Chaque échec
    de lancement est isolé : un fichier illisible ne doit pas empêcher les
    autres d'être traités. Le journal d'activité est écrit par l'appelant, qui
    seul connaît la langue de l'utilisateur.
    """
    files = list(files)
    started = 0
    skipped = []

    if len(files) > MAX_BATCH_SIZE:
        skipped = [
            (data_file.original_name, "lot trop volumineux")
            for data_file in files[MAX_BATCH_SIZE:]
        ]
        files = files[:MAX_BATCH_SIZE]

    for data_file in files:
        try:
            start_cleaning(
                data_file.pk,
                options,
                rules=rules or [],
                session_key=session_key,
                language=language,
            )
        except Exception as exc:  # noqa: BLE001 — un fichier en échec n'arrête pas le lot
            logger.exception("Lancement du lot impossible pour %s", data_file.pk)
            skipped.append((data_file.original_name, str(exc)))
            continue
        started += 1

    return {"started": started, "skipped": skipped}
