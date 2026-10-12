"""Messages d'erreur présentables à l'utilisateur.

Les exceptions brutes ne doivent jamais remonter telles quelles dans l'interface
ni dans l'API : elles exposent les chemins absolus du serveur, les versions des
bibliothèques, les noms de fonctions internes, voire des extraits de données.
:func:`user_error` journalise la pile d'appels complète côté serveur et ne
renvoie qu'un message court, sans chemin de fichier.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# « /home/app/datazen/core/services/pipeline.py » → « pipeline.py »
_ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/)[\w.\-\\/]*[\\/]([\w.\-]+)")
# Limite de longueur pour ne pas noyer l'utilisateur dans un message technique.
_MAX_LENGTH = 180


def user_error(exc, context=""):
    """Renvoie un message court et désinfecté, et journalise ``exc``.

    ``context`` sert à identifier l'endroit du code dans le journal serveur.
    """
    logger.exception("%s : %s", context or "Erreur applicative", exc)
    text = str(exc).strip().splitlines()
    message = text[0] if text else exc.__class__.__name__
    message = _ABSOLUTE_PATH.sub(r"\1", message)
    message = message.replace("\\", "/")
    if len(message) > _MAX_LENGTH:
        message = message[: _MAX_LENGTH - 1].rstrip() + "…"
    return message
