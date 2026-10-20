"""Point d'entrée du conteneur DataZen.

Exécute les migrations puis délègue au serveur WSGI passé en ``CMD``.

Ce script est écrit en Python plutôt qu'en shell pour deux raisons :
  * un script ``.sh`` versionné depuis un poste Windows (``core.autocrlf=true``)
    arrive avec des fins de ligne CRLF et échoue sous Linux avec
    ``bad interpreter: /bin/sh^M`` ;
  * l'attente de la base de données et la remontée des erreurs sont plus
    lisibles qu'une boucle ``until pg_isready``.
"""

from __future__ import annotations

import os
import sys
import time

import django
from django.core.management import call_command
from django.db import connections
from django.db.utils import OperationalError

# Secondes d'attente avant d'abandonner la connexion à PostgreSQL. Le service
# `db` de docker-compose expose un healthcheck, mais un conteneur lancé hors
# compose (ou un redémarrage de PostgreSQL) peut n'être prêt qu'après coup.
DB_WAIT_SECONDS = int(os.environ.get("DATAZEN_DB_WAIT_SECONDS", "60"))
DB_WAIT_INTERVAL = 2


def wait_for_database() -> None:
    """Attend que la base de données accepte les connexions."""
    deadline = time.monotonic() + DB_WAIT_SECONDS
    attempt = 0
    while True:
        attempt += 1
        try:
            connections["default"].ensure_connection()
            return
        except OperationalError as exc:
            if time.monotonic() >= deadline:
                print(
                    f"[entrypoint] base de données injoignable après "
                    f"{DB_WAIT_SECONDS}s : {exc}",
                    file=sys.stderr,
                )
                raise
            print(
                f"[entrypoint] base de données indisponible "
                f"(tentative {attempt}), nouvelle tentative dans "
                f"{DB_WAIT_INTERVAL}s…",
                file=sys.stderr,
            )
            time.sleep(DB_WAIT_INTERVAL)


def main() -> None:
    django.setup()

    wait_for_database()

    print("[entrypoint] application des migrations…", flush=True)
    call_command("migrate", interactive=False, verbosity=1)

    # `execvp` remplace le processus courant : le serveur WSGI devient PID 1 et
    # reçoit directement SIGTERM de Docker, ce qui permet un arrêt propre.
    os.execvp(sys.argv[1], sys.argv[1:])


if __name__ == "__main__":
    main()
