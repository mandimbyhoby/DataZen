"""Traductions contextuelles (``msgctxt``).

Contrairement aux autres modules, les clés de ``SEPARATOR_TRANSLATIONS``
portent un contexte : elles sont écrites sous la forme ``contexte\\x04msgid``
(le séparateur ``\\x04`` est celui qu'utilise ``gettext`` pour
``pgettext`` / ``{% translate … context "…" %}``).

Le contexte « séparateur » sert au « ou » des séparateurs d'authentification
(``login.html``, ``signup.html``, ``password_reset.html``).
"""

CONTEXT = "séparateur"
MSGID = "ou"

_TRANSLATIONS = {
    "en": "or",
    "es": "o",
    "de": "oder",
    "it": "o",
    "pt": "ou",
    "nl": "of",
    "ar": "أو",
    "zh-hans": "或",
    "ru": "или",
    "ja": "または",
    "ko": "또는",
    "tr": "veya",
    "hi": "या",
    "pl": "lub",
    "sv": "eller",
    "da": "eller",
    "fi": "tai",
    "cs": "nebo",
    "ro": "sau",
    "vi": "hoặc",
    "th": "หรือ",
    "id": "atau",
}

SEPARATOR_TRANSLATIONS = {
    code: {f"{CONTEXT}\x04{MSGID}": value} for code, value in _TRANSLATIONS.items()
}
