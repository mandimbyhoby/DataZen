"""Opérations de nettoyage : codes stables et rendu traduit à l'affichage.

Le pipeline ne mémorise plus de texte déjà traduit mais un couple
``(code, paramètres)``. La traduction est résolue au moment de l'affichage
(:func:`render_operations`), ce qui permet à la liste des opérations de suivre
la langue active de l'interface même si le nettoyage a été lancé dans une
autre langue.

Les messages sont déclarés en ``gettext_lazy`` : les littéraux restent
visibles pour l'extracteur i18n (``tools/i18n_extract.py``) tout en étant
résolus dynamiquement.
"""

import re
from functools import lru_cache

from django.conf import settings
from django.utils import translation
from django.utils.translation import gettext_lazy

# Opérations du pipeline (options de nettoyage).
OPERATION_MESSAGES = {
    "remove_duplicates_column": gettext_lazy(
        "Suppression des doublons sur « %(column)s » (%(count)s supprimé(s))"
    ),
    "remove_duplicates_exact": gettext_lazy(
        "Suppression des doublons exacts (%(count)s supprimé(s))"
    ),
    "normalize_case": gettext_lazy(
        "Normalisation de la casse (noms, libellés, villes)"
    ),
    "normalize_categories": gettext_lazy(
        "Normalisation des catégories (%(count)s corrigée(s))"
    ),
    "normalize_codes": gettext_lazy(
        "Normalisation des codes/références (%(count)s corrigé(s))"
    ),
    "normalize_booleans": gettext_lazy(
        "Normalisation des choix oui/non (%(count)s corrigé(s))"
    ),
    "normalize_emails": gettext_lazy(
        "Validation et correction des emails (%(corrected)s corrigé(s), %(invalid)s invalide(s))"
    ),
    "normalize_phones": gettext_lazy(
        "Normalisation des téléphones (%(count)s corrigé(s))"
    ),
    "normalize_dates": gettext_lazy(
        "Normalisation des dates (%(count)s corrigée(s))"
    ),
    "normalize_salaries": gettext_lazy(
        "Conversion des montants (%(count)s converti(s))"
    ),
    "trim_whitespace": gettext_lazy("Suppression des espaces superflus"),
    "normalize_unknown": gettext_lazy(
        "Canonicalisation du marqueur « Inconnu » (%(count)s corrigé(s))"
    ),
    "normalize_integers": gettext_lazy(
        "Conversion des compteurs en entiers (%(count)s converti(s))"
    ),
    "anonymize": gettext_lazy(
        "Anonymisation des données sensibles (%(count)s valeur(s) pseudonymisée(s))"
    ),
    "renumber_identifiers": gettext_lazy(
        "Renumérotation des identifiants (ancien id conservé)"
    ),
    "fill_missing": gettext_lazy(
        "Remplissage des valeurs manquantes par « %(value)s » "
        "(les montants, codes et dates ne reçoivent jamais un texte)"
    ),
}

# Règles de nettoyage personnalisées (préfixe « [Règle] »).
RULE_OPERATION_MESSAGES = {
    "rule_remove_duplicates": gettext_lazy(
        "[Règle] Suppression des doublons (%(count)s supprimé(s))"
    ),
    "rule_trim_whitespace": gettext_lazy(
        "[Règle] Suppression des espaces superflus"
    ),
    "rule_normalize_case": gettext_lazy("[Règle] Normalisation de la casse"),
    "rule_normalize_emails": gettext_lazy(
        "[Règle] Normalisation des emails (%(count)s corrigé(s))"
    ),
    "rule_normalize_phones": gettext_lazy(
        "[Règle] Normalisation des téléphones (%(count)s corrigé(s))"
    ),
    "rule_normalize_dates": gettext_lazy(
        "[Règle] Normalisation des dates (%(count)s corrigée(s))"
    ),
    "rule_normalize_salaries": gettext_lazy(
        "[Règle] Conversion des montants (%(count)s converti(s))"
    ),
    "rule_fill_missing": gettext_lazy(
        "[Règle] Remplissage des valeurs manquantes par « %(value)s »"
    ),
    "rule_anonymize": gettext_lazy(
        "[Règle] Anonymisation (%(count)s valeur(s))"
    ),
}

MESSAGES = {**OPERATION_MESSAGES, **RULE_OPERATION_MESSAGES}

# Types de correction du journal des modifications (colonne
# ``type_correction``). Ce sont des codes internes : ils ne doivent jamais
# être affichés bruts à l'utilisateur.
CORRECTION_TYPE_MESSAGES = {
    "doublon": gettext_lazy("Doublon"),
    "casse": gettext_lazy("Casse"),
    "catégorie": gettext_lazy("Catégorie"),
    "anonymisation": gettext_lazy("Anonymisation"),
    "inconnu": gettext_lazy("Valeur inconnue"),
    "téléphone": gettext_lazy("Téléphone"),
    "anomalie": gettext_lazy("Anomalie"),
    "date": gettext_lazy("Date"),
    "email": gettext_lazy("Email"),
    "Email invalide": gettext_lazy("Email invalide"),
    "Email placeholder": gettext_lazy("Email fictif"),
    "Email manquant": gettext_lazy("Email manquant"),
    "numérique": gettext_lazy("Numérique"),
}


# Explications du score de qualité. Comme les opérations, elles sont
# mémorisées sous forme de code : le texte est résolu à l'affichage pour
# suivre la langue active de l'interface.
SCORE_EXPLANATION_MESSAGES = {
    "unknown_values": gettext_lazy(
        "%(count)s valeur(s) inconnue(s) (donnée indisponible)"
    ),
    "missing_values": gettext_lazy("%(count)s valeur(s) manquante(s)"),
    "no_missing_or_unknown": gettext_lazy(
        "Aucune valeur manquante ou inconnue"
    ),
    "invalid_values": gettext_lazy(
        "%(count)s valeur(s) invalide(s) parmi les données renseignées"
    ),
    "all_valid": gettext_lazy("Toutes les valeurs renseignées sont valides"),
    "exact_duplicates": gettext_lazy(
        "%(count)s doublon(s) exact(s) restant(s)"
    ),
    "no_exact_duplicates": gettext_lazy("Aucun doublon exact"),
    "potential_duplicates": gettext_lazy(
        "%(count)s doublon(s) potentiel(s) à vérifier (pénalité réduite)"
    ),
    "no_potential_duplicates": gettext_lazy("Aucun doublon potentiel"),
    "inconsistent_values": gettext_lazy(
        "%(count)s valeur(s) incohérente(s) restante(s) "
        "(ni valide ni inconnue)"
    ),
    "consistent": gettext_lazy(
        "Données cohérentes : chaque valeur est valide ou inconnue"
    ),
    "non_standard_values": gettext_lazy("%(count)s valeur(s) non standard"),
    "formats_standardized": gettext_lazy(
        "Formats standardisés (téléphones, dates)"
    ),
}


# Catalogues de messages disponibles à la reconnaissance des libellés figés.
CATALOGS = {
    "operation": MESSAGES,
    "score": SCORE_EXPLANATION_MESSAGES,
}


def operation_entry(code, **params):
    """Décrit une opération appliquée : ``(code, paramètres)``."""
    return (code, params)


def score_explanation_entry(kind, code, **params):
    """Décrit une explication du score : ``{"type", "code", "params"}``."""
    return {"type": kind, "code": code, "params": params}


def render_score_explanations(explanations):
    """Traduit les explications du score dans la langue active.

    Les entrées déjà rendues (``{"type", "text"}``) sont reconverties en code
    lorsque leur libellé figé est reconnu, afin de suivre elles aussi la langue
    active ; sinon elles sont conservées telles quelles, ce qui préserve les
    scores calculés avant l'introduction des codes.
    """
    rendered = []
    for item in explanations or []:
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        params = item.get("params") or {}
        if code is None:
            if "text" not in item:
                continue
            recovered = _recover_legacy_entry(
                str(item["text"]), catalog_name="score"
            )
            if recovered is None:
                rendered.append(item)
                continue
            code, params = recovered
        message = SCORE_EXPLANATION_MESSAGES.get(code)
        if message is None:
            continue
        try:
            text = str(message) % (params or {})
        except (KeyError, TypeError, ValueError):
            text = str(message)
        rendered.append({"type": item.get("type", "ok"), "text": text})
    return rendered


def correction_type_label(code):
    """Libellé traduit d'un type de correction du journal.

    Un code inconnu est renvoyé tel quel plutôt que perdu.
    """
    message = CORRECTION_TYPE_MESSAGES.get(code)
    return str(message) if message is not None else str(code)


def render_correction_types(codes):
    """Traduit une liste de codes ``type_correction`` dans la langue active."""
    return [correction_type_label(code) for code in codes or []]


def render_operations(operations):
    """Traduit une liste d'opérations dans la langue active.

    Les entrées ``(code, paramètres)`` sont rendues via :data:`MESSAGES`. Une
    chaîne simple (session enregistrée avant l'introduction des codes) est
    reconvertie en ``(code, paramètres)`` puis rendue, afin qu'elle suive elle
    aussi la langue active ; si elle est vraiment inconnue, elle est conservée
    telle quelle. Un code inconnu est affiché brut plutôt que silencieusement
    perdu.
    """
    rendered = []
    for entry in operations or []:
        if isinstance(entry, str):
            recovered = _recover_legacy_entry(entry)
            if recovered is None:
                rendered.append(entry)
                continue
            entry = recovered
        try:
            code, params = entry
        except (TypeError, ValueError):
            rendered.append(str(entry))
            continue
        message = MESSAGES.get(code)
        if message is None:
            rendered.append(str(code))
            continue
        try:
            rendered.append(str(message) % (params or {}))
        except (KeyError, TypeError, ValueError):
            rendered.append(str(message))
    return rendered


# Un libellé figé se présente sous la forme « texte (détail) » ; les valeurs
# dynamiques (colonnes, montants) y sont encadrées par des guillemets.
_PATTERN_PLACEHOLDER = re.compile(
    "[«\u201c\u201e\u2018\"]\\s*(?P<value>.+?)\\s*[»\u201d\u201c\u2019\"]"
)
_PATTERN_FIELD = re.compile(r"%\((?P<name>\w+)\)s")
_PATTERN_NUMBER = re.compile(r"-?\d+")
_COUNT_KEYS = ("count", "corrected", "invalid")


def _normalize_legacy_text(text):
    """Remplace valeurs dynamiques, champs et nombres par un marqueur.

    Deux libellés qui ne diffèrent que par leurs valeurs produisent ainsi le
    même motif, ce qui permet de les reconnaître quelle que soit la langue.
    """
    text = _PATTERN_PLACEHOLDER.sub("\x00", text)
    text = _PATTERN_FIELD.sub("\x00", text)
    return _PATTERN_NUMBER.sub("\x00", text)


@lru_cache(maxsize=None)
def _legacy_forms(catalog_name):
    """Table ``motif figé -> [(code, noms de paramètres)]``, toutes langues.

    Les libellés sont résolus dans chaque langue de l'interface : une session
    enregistrée en chinois comme en français peut donc être reconnue.
    """
    messages = CATALOGS[catalog_name]
    forms = {}
    languages = [code for code, _name in getattr(settings, "LANGUAGES", [])] or ["fr"]
    for language in languages:
        with translation.override(language):
            for code, message in messages.items():
                text = str(message)
                names = tuple(dict.fromkeys(_PATTERN_FIELD.findall(text)))
                forms.setdefault(_normalize_legacy_text(text), set()).add((code, names))
    return {pattern: sorted(variants) for pattern, variants in forms.items()}


def _extract_params(text, param_names):
    """Extrait les valeurs dynamiques d'un libellé hérité, ou ``None``."""
    if len(param_names) == 1 and param_names[0] not in _COUNT_KEYS:
        match = _PATTERN_PLACEHOLDER.search(text)
        if match is None:
            return None
        params = {param_names[0]: match.group("value")}
    else:
        values = _PATTERN_PLACEHOLDER.findall(text)
        plain = [name for name in param_names if name not in _COUNT_KEYS]
        if plain:
            if len(values) != len(plain):
                return None
            params = dict(zip(plain, values))
        else:
            params = {}

    # Les nombres sont cherchés hors des valeurs dynamiques, pour ne pas
    # confondre un montant ou un nom de colonne avec un compteur.
    masked = _PATTERN_PLACEHOLDER.sub(" ", text)
    numbers = _PATTERN_NUMBER.findall(masked)
    count_names = [name for name in _COUNT_KEYS if name in param_names]
    if count_names:
        if len(numbers) < len(count_names):
            return None
        for name, value in zip(count_names, numbers):
            params[name] = value
    return params


def _recover_legacy_entry(text, catalog_name="operation"):
    """Reconvertit un libellé figé en ``(code, paramètres)``, sinon ``None``."""
    pattern = _normalize_legacy_text(text)
    for code, param_names in _legacy_forms(catalog_name).get(pattern, ()):
        params = _extract_params(text, param_names)
        if params is not None:
            return (code, params)
    return None
