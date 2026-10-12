"""Traductions DataZen.

Chaque langue dispose d'un module exposant ``TRANSLATIONS`` (dict
``msgid -> msgstr``) et ``CODE``. ``CATALOGS`` agrège le tout et
``LANGUAGE_NAMES`` fournit les libellés lisibles.

Pour ajouter une langue :
1. créer ``tools/translations/<code>.py`` avec ``CODE`` et ``TRANSLATIONS`` ;
2. l'enregistrer dans ``_MODULES`` ci-dessous ;
3. ajouter le code dans ``SITE_LANGUAGES`` (``datazen/settings.py``) ;
4. relancer ``python tools/i18n_build.py``.
"""

from __future__ import annotations

from importlib import import_module

from .validation_issues import ISSUE_UI_TRANSLATIONS
from .service_messages import SERVICE_MESSAGE_TRANSLATIONS
from .dataset_dashboard import DASHBOARD_TRANSLATIONS
from .cleaning_options import CLEANING_OPTIONS_TRANSLATIONS
from .cleaning_operations import CLEANING_OPERATION_TRANSLATIONS
from .dataset_messages import DATASET_MESSAGE_TRANSLATIONS
from .duplicate_review import DUPLICATE_REVIEW_TRANSLATIONS
from .chart_labels import CHART_LABEL_TRANSLATIONS
from .key_names import KEY_NAME_TRANSLATIONS
from .pro_features import PRO_FEATURE_TRANSLATIONS
from .rule_states import RULE_STATE_TRANSLATIONS
from .search_labels import SEARCH_LABEL_TRANSLATIONS
from .separators import SEPARATOR_TRANSLATIONS
from .ui_strings import UI_STRING_TRANSLATIONS

_MODULES = [
    "en",
    "es",
    "de",
    "it",
    "pt",
    "nl",
    "ar",
    "zh",
    "ru",
    "ja",
    "ko",
    "tr",
    "hi",
    "pl",
    "sv",
    "da",
    "fi",
    "cs",
    "ro",
    "vi",
    "th",
    "id",
]

LANGUAGE_NAMES = {
    "fr": "Français",
    "en": "English",
    "es": "Español",
    "de": "Deutsch",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "ar": "العربية",
    "zh-hans": "简体中文",
    "ru": "Русский",
    "ja": "日本語",
    "ko": "한국어",
    "tr": "Türkçe",
    "hi": "हिन्दी",
    "pl": "Polski",
    "sv": "Svenska",
    "da": "Dansk",
    "fi": "Suomi",
    "cs": "Čeština",
    "ro": "Română",
    "vi": "Tiếng Việt",
    "th": "ไทย",
    "id": "Bahasa Indonesia",
}

CATALOGS: dict[str, dict[str, str]] = {"fr": {}}

for _name in _MODULES:
    try:
        _module = import_module(f"tools.translations.{_name}")
    except ModuleNotFoundError:
        continue
    CATALOGS[_module.CODE] = _module.TRANSLATIONS

for _overrides in (
    ISSUE_UI_TRANSLATIONS,
    SERVICE_MESSAGE_TRANSLATIONS,
    DASHBOARD_TRANSLATIONS,
    CLEANING_OPTIONS_TRANSLATIONS,
    CLEANING_OPERATION_TRANSLATIONS,
    DATASET_MESSAGE_TRANSLATIONS,
    DUPLICATE_REVIEW_TRANSLATIONS,
    CHART_LABEL_TRANSLATIONS,
    KEY_NAME_TRANSLATIONS,
    PRO_FEATURE_TRANSLATIONS,
    RULE_STATE_TRANSLATIONS,
    SEARCH_LABEL_TRANSLATIONS,
    SEPARATOR_TRANSLATIONS,
    UI_STRING_TRANSLATIONS,
):
    for _code, _translations in _overrides.items():
        CATALOGS.setdefault(_code, {}).update(_translations)

__all__ = ["CATALOGS", "LANGUAGE_NAMES"]