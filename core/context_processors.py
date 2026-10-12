"""Context processors partagés par tous les templates."""
from django.conf import settings
from django.utils import translation


def _matches(language_code, current):
    """Vrai si ``language_code`` désigne la langue active.

    Gère l'écart entre ``LANGUAGE_CODE`` ("fr-fr") et le code du sélecteur
    ("fr", "zh-hans") : on compare le code exact, puis le préfixe.
    """
    if language_code == current:
        return True
    return language_code.split("-")[0] == current.split("-")[0]


def site_languages(request):
    """Expose les langues du sélecteur et la langue active.

    Permet au template de base de construire le menu des drapeaux sans
    connaître la configuration : ``SITE_LANGUAGES`` reste la seule source.
    """
    current = translation.get_language() or settings.LANGUAGE_CODE
    current = current.lower().replace("_", "-")

    languages = []
    active = None
    for lang in settings.SITE_LANGUAGES:
        entry = dict(lang)
        entry["is_active"] = _matches(lang["code"].lower(), current)
        if entry["is_active"] and active is None:
            active = entry
        languages.append(entry)

    if active is None:
        active = languages[0]

    return {
        "site_languages": languages,
        "active_language": active,
    }
