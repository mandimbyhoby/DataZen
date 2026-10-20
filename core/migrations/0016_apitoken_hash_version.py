"""Ajoute la version du condensé aux jetons d'API.

Le repli sur l'ancien condensé à sel statique (``sha256("datazen:" + jeton)``)
est supprimé : il restait vérifiable hors ligne à partir d'un simple vidage de
la base, sans la clé du serveur.

Les lignes existantes sont marquées « keyé » : le hachage keyé est le seul
format de création depuis le premier commit du dépôt, donc aucune ligne ne peut
porter un condensé hérité. Si une installation dérivée en possédait malgré
tout, elles se retrouveraient marquées « keyé » et cesseraient de se résoudre —
le comportement voulu est de refuser (fail closed) plutôt que d'accepter un
condensé faible. Les jetons concernés doivent être régénérés.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_profile_role_cleaningschedule_datasetshare_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="apitoken",
            name="hash_version",
            field=models.PositiveSmallIntegerField(
                default=2,
                verbose_name="Version du condensé",
            ),
        ),
    ]
