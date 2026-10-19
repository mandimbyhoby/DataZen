"""Exécute les nettoyages planifiés dont l'échéance est atteinte.

L'application n'embarque aucun démon : cette commande est prévue pour être
appelée par un ordonnanceur système (cron, Planificateur de tâches Windows),
par exemple toutes les cinq minutes :

    python manage.py run_schedules

``--dry-run`` liste les planifications dues sans rien lancer, ce qui permet de
vérifier la configuration de l'ordonnanceur sans effet de bord.
"""
from django.core.management.base import BaseCommand

from core.services import schedules as schedule_service


class Command(BaseCommand):
    help = "Lance les nettoyages planifiés arrivés à échéance."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Affiche les planifications dues sans lancer de nettoyage.",
        )

    def handle(self, *args, **options):
        if options["dry_run"]:
            due = list(schedule_service.due_schedules())
            if not due:
                self.stdout.write("Aucune planification à échéance.")
                return
            for schedule in due:
                self.stdout.write(
                    f"[à faire] {schedule.data_file.original_name} "
                    f"({schedule.get_frequency_display()}) — "
                    f"échéance {schedule.next_run_at:%Y-%m-%d %H:%M}"
                )
            self.stdout.write(f"{len(due)} planification(s) à échéance.")
            return

        count = schedule_service.run_due_schedules()
        if count:
            self.stdout.write(self.style.SUCCESS(f"{count} nettoyage(s) lancé(s)."))
        else:
            self.stdout.write("Aucune planification à échéance.")
