"""Traductions françaises des messages dont la source est anglaise.

Le français est la langue source de DataZen : son catalogue reste donc vide
par défaut, et ``gettext`` renvoie le msgid tel quel. C'est correct tant que
le msgid est écrit en français — mais une partie du code (contrôle de
cohérence, tableau de bord, exports) déclare ses messages directement en
anglais. Sans ce module, ces libellés s'affichent en anglais alors que
l'interface est en français.

Ce catalogue ne contient donc **que** les msgids à source anglaise. Les
chaînes qui s'écrivent identiquement dans les deux langues (« API », « URL »,
« email », « Score », « Q1 »…) sont volontairement absentes : les lister
n'apporterait rien et alourdirait le fichier.
"""

from __future__ import annotations

FRENCH_SOURCE_TRANSLATIONS: dict[str, dict[str, str]] = {
    "fr": {
        # Contrôle de cohérence (core/services/validation.py).
        "%(actual)s correction(s) in the log vs %(reported)s reported": (
            "%(actual)s correction(s) dans le journal vs %(reported)s annoncée(s)"
        ),
        "%(actual)s unknown value(s) in email column(s) vs %(reported)s reported": (
            "%(actual)s valeur(s) inconnue(s) dans les colonnes email "
            "vs %(reported)s annoncée(s)"
        ),
        "%(count)s invalid email(s) present (non-empty and not unknown)": (
            "%(count)s email(s) invalide(s) présent(s) (non vide et non inconnu)"
        ),
        "%(valid)s + %(invalid)s + %(unknown)s = %(actual)s vs %(expected)s expected": (
            "%(valid)s + %(invalid)s + %(unknown)s = %(actual)s "
            "vs %(expected)s attendu(s)"
        ),
        "Emails corrected (change log vs counter)": (
            "Emails corrigés (journal vs compteur)"
        ),
        "Emails: valid + invalid + unknown = total": (
            "Emails : valides + invalides + inconnus = total"
        ),
        "Invalid emails are not counted as unknown or missing": (
            "Les emails invalides ne sont comptés ni comme inconnus "
            "ni comme manquants"
        ),
        "Missing values by column": "Valeurs manquantes par colonne",
        "Reported %(reported)s vs recalculated %(actual)s": (
            "Annoncé %(reported)s vs recalculé %(actual)s"
        ),
        "Total missing values": "Total des valeurs manquantes",
        "Unknown emails included in the unknown-value statistic": (
            "Les emails inconnus sont inclus dans la statistique "
            "des valeurs inconnues"
        ),
        "Unknown values by column": "Valeurs inconnues par colonne",
        # Tableau de bord et exports.
        "(score ≥ 0.8)": "(score ≥ 0,8)",
        "Active": "Actif",
        "Inactive": "Inactif",
        "Outliers": "Valeurs aberrantes",
        "Unknown": "Inconnu",
        "API & webhooks": "API et webhooks",
    }
}
