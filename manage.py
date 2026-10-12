#!/usr/bin/env python
"""Utilitaire de ligne de commande Django pour les tâches administratives."""
import os
import sys


def main():
    """Exécute les tâches administratives."""
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "datazen.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Impossible d'importer Django. Assurez-vous qu'il est installé et "
            "disponible dans votre variable d'environnement PYTHONPATH, que vous "
            "avez bien activé votre environnement virtuel, ou que vous l'avez "
            "installé avec `pip install -r requirements.txt`."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
