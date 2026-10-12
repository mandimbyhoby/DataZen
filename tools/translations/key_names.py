"""Noms des touches clavier affichés dans les raccourcis et la palette.

Ces libellés apparaissent dans des balises ``<kbd>`` (« Entrée », « Échap »).
Ils doivent suivre la langue de l'interface : un utilisateur germanophone
lit « Eingabe », un utilisateur russophone « Ввод ».

Les clés sont réparties en deux tranches alignées : chaque langue fournit un
couple de tuples de même longueur, vérifié à l'import. Le français est absent
volontairement : c'est la langue source, ses catalogues restent vides.
"""

from __future__ import annotations

KEYS_A: tuple[str, ...] = (
    "Entrée",
    "Échap",
)

_VALUES: dict[str, tuple[str, ...]] = {
    "en": ("Enter", "Esc"),
    "es": ("Intro", "Esc"),
    "de": ("Eingabe", "Esc"),
    "it": ("Invio", "Esc"),
    "pt": ("Enter", "Esc"),
    "nl": ("Enter", "Esc"),
    "ar": ("إدخال", "إلغاء"),
    "zh-hans": ("回车", "退出"),
    "ru": ("Ввод", "Выход"),
    "ja": ("Enter", "Esc"),
    "ko": ("Enter", "Esc"),
    "tr": ("Enter", "Esc"),
    "hi": ("एंटर", "एस्केप"),
    "pl": ("Enter", "Esc"),
    "sv": ("Enter", "Esc"),
    "da": ("Enter", "Esc"),
    "fi": ("Enter", "Esc"),
    "cs": ("Enter", "Esc"),
    "ro": ("Enter", "Esc"),
    "vi": ("Enter", "Esc"),
    "th": ("Enter", "Esc"),
    "id": ("Enter", "Esc"),
}

for _code, _values in _VALUES.items():
    if len(_values) != len(KEYS_A):
        raise ValueError(f"traductions désalignées pour {_code}")

KEY_NAME_TRANSLATIONS: dict[str, dict[str, str]] = {
    code: dict(zip(KEYS_A, values)) for code, values in _VALUES.items()
}
