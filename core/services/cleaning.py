"""
Module de nettoyage de données (DataClean Pro).

Ce module centralise les fonctions et classes responsables du
nettoyage des fichiers de données (CSV, Excel) à l'aide de Pandas.

Les fonctionnalités (suppression de doublons, normalisation,
gestion des valeurs manquantes, etc.) seront ajoutées ici au fil
des étapes du projet.
"""

import re
from datetime import datetime

import pandas as pd

from .operations import operation_entry

# Valeur spéciale « inconnu » : marqueur de donnée absente/indisponible.
# « Inconnu » n'est ni une erreur, ni une valeur manquante, ni un email invalide.
UNKNOWN_VALUE = "Inconnu"


def is_unknown(value):
    """Indique si une valeur est le marqueur « Inconnu » (insensible à la casse)."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() == UNKNOWN_VALUE.lower()
    return False


# Colonnes considérées comme des identifiants (clé primaire, numéro de ligne…).
# Elles ne servent pas à détecter les doublons : deux lignes peuvent porter un
# identifiant différent tout en représentant le même enregistrement (ex. Alice
# avec id=1 et id=4).
IDENTIFIER_COLUMNS = {
    "id",
    "index",
    "identifiant",
    "numero",
    "numéro",
    "no",
    "n°",
    "row",
    "row_id",
    "ligne",
    "ancien_id",  # colonne de traçabilité (jamais utilisée pour dédupliquer)
}


def _is_identifier(column):
    """Indique si une colonne est un identifiant (``id``, ``index``, …)."""
    name = str(column).strip().lower()
    if name in IDENTIFIER_COLUMNS:
        return True
    return name.endswith("_id") or name.endswith(".id")


# Noms de colonnes reconnus comme des numéros de téléphone ou des dates.
PHONE_COLUMN_TOKENS = (
    "telephone",
    "téléphone",
    "phone",
    "tel",
    "mobile",
    "portable",
    "gsm",
    "fax",
)

EMAIL_COLUMN_TOKENS = (
    "email",
    "e-mail",
    "mail",
    "courriel",
    "adresse_mail",
)

# Termes indiquant sans ambiguïté une colonne de date (un seul suffit).
STRONG_DATE_TOKENS = (
    "date",
    "naissance",
    "inscription",
    "creation",
    "création",
    "embauche",
)

# Termes ambigus : ils n'indiquent une date que si un terme fort est aussi
# présent (ex. « date_commande », « date_vente »). Une colonne
# « numero_commande » ou « numéro de commande » n'est PAS une date.
WEAK_DATE_TOKENS = (
    "commande",
    "vente",
)

CATEGORY_COLUMN_TOKENS = (
    "service",
    "categorie",
    "catégorie",
    "departement",
    "département",
    "type",
    "statut",
    "genre",
    "niveau",
    "role",
    "rôle",
    "fonction",
)

# Dictionnaire de normalisation des catégories (valeurs → libellé canonique).
DEFAULT_CATEGORY_MAP = {
    "rh": "Ressources Humaines",
    "ressources humaines": "Ressources Humaines",
    "ressourceshumaines": "Ressources Humaines",
    "informatique": "Informatique",
    "comptabilité": "Comptabilité",
    "comptabilite": "Comptabilité",
    "marketing": "Marketing",
    "finance": "Finance",
    "juridique": "Juridique",
    "logistique": "Logistique",
    "direction": "Direction",
}


def _is_phone_column(column):
    """Indique si une colonne contient des numéros de téléphone."""
    name = str(column).strip().lower()
    return any(token in name for token in PHONE_COLUMN_TOKENS)


def _is_email_column(column):
    """Indique si une colonne contient des adresses email."""
    name = str(column).strip().lower()
    return any(token in name for token in EMAIL_COLUMN_TOKENS)


def _is_date_column(column):
    """Indique si une colonne contient des dates.

    Un terme fort (« date », « naissance »…) suffit à classer la colonne comme
    date. Un terme ambigu (« commande », « vente ») ne suffit pas à lui seul :
    il faut aussi le mot « date » (ex. « date_commande »), sinon une colonne
    comme « numero_commande » (un code) serait à tort traitée comme une date.
    """
    name = str(column).strip().lower()
    if any(token in name for token in STRONG_DATE_TOKENS):
        return True
    if any(token in name for token in WEAK_DATE_TOKENS):
        return "date" in name
    return False


def _is_category_column(column):
    """Indique si une colonne est une catégorie (service, type, statut…)."""
    name = str(column).strip().lower()
    return any(token in name for token in CATEGORY_COLUMN_TOKENS)


# Noms de colonnes représentant des noms propres (personnes, lieux) : elles
# seules sont mises en casse « Capitales ». Les libellés libres (produits,
# descriptions…) n'en font PAS partie.
NAME_COLUMN_TOKENS = (
    "nom",
    "name",
    "surname",
    "prenom",
    "prénom",
    "first",
    "last",
    "ville",
    "city",
    "commune",
    "town",
    "pays",
    "country",
    "client",
    "adresse",
    "address",
    "rue",
)


def _is_name_column(column):
    """Indique si une colonne contient des noms propres (personne/lieu)."""
    name = str(column).strip().lower()
    return any(token in name for token in NAME_COLUMN_TOKENS)


# Noms de colonnes reconnus comme des montants numériques (salaires…).
SALARY_COLUMN_TOKENS = (
    "salaire",
    "salary",
    "remuneration",
    "rémunération",
    "remuneration_brute",
    "revenu",
    "montant",
    "prix",
)


def _is_salary_column(column):
    """Indique si une colonne contient des montants numériques (salaires…)."""
    name = str(column).strip().lower()
    return any(token in name for token in SALARY_COLUMN_TOKENS)


# Noms de colonnes représentant des compteurs/entiers (quantités, âges…).
INTEGER_COLUMN_TOKENS = (
    "quantite",
    "quantité",
    "quantity",
    "qte",
    "qty",
    "nombre",
    "count",
    "age",
    "annee",
    "année",
    "year",
    "stock",
    "nb",
    "nbre",
    "effectif",
)


def _is_integer_column(column):
    """Indique si une colonne est un compteur entier (quantité, âge…)."""
    name = str(column).strip().lower()
    return any(token in name for token in INTEGER_COLUMN_TOKENS)


# Noms de colonnes représentant des libellés libres (produits, articles…) :
# on les met en casse « Capitales » pour une présentation homogène.
LABEL_COLUMN_TOKENS = (
    "article",
    "produit",
    "product",
    "designation",
    "désignation",
    "libelle",
    "libellé",
    "description",
    "item",
    "intitule",
    "intitulé",
)


def _is_label_column(column):
    """Indique si une colonne est un libellé libre (produit, article…)."""
    name = str(column).strip().lower()
    return any(token in name for token in LABEL_COLUMN_TOKENS)


# Noms de colonnes représentant un choix binaire oui/non (newsletter, abonné…).
# Leurs valeurs sont uniformisées en minuscules (``OUI`` → ``oui``).
BOOLEAN_COLUMN_TOKENS = (
    "newsletter",
    "abonne",
    "abonné",
    "abonnement",
    "optin",
    "opt_in",
    "consentement",
    "consent",
    "actif",
    "active",
    "flag",
    "booleen",
    "booléen",
    "boolean",
)


def _is_boolean_column(column):
    """Indique si une colonne est un choix binaire oui/non (newsletter…)."""
    name = str(column).strip().lower()
    return any(token in name for token in BOOLEAN_COLUMN_TOKENS)


# Noms de colonnes représentant des codes/références (``CMD-001``…) : on les
# met en MAJUSCULES pour une présentation homogène. Les codes postaux en sont
# exclus (un code postal peut contenir un nom de ville en toutes lettres).
CODE_COLUMN_TOKENS = (
    "numero",
    "numéro",
    "code",
    "reference",
    "référence",
    "matricule",
    "sku",
    "cmd",
    "n°",
)
CODE_EXCLUDE_TOKENS = ("postal", "zip", "zipcode", "cp", "poste")


def _is_code_column(column):
    """Indique si une colonne est un code/référence (à mettre en majuscules)."""
    name = str(column).strip().lower()
    if any(token in name for token in CODE_EXCLUDE_TOKENS):
        return False
    return any(token in name for token in CODE_COLUMN_TOKENS)


def _is_placeholder_column(column):
    """Indique si une colonne peut recevoir le marqueur « Inconnu ».

    Seules les colonnes de texte libre peuvent recevoir « Inconnu ». On
    n'écrit jamais un texte dans une colonne numérique, ni dans un
    identifiant, un code ou une date : une valeur « Inconnu » y serait
    incohérente (elle corromprait le type de la colonne).
    """
    if _is_identifier(column):
        return False
    if _is_code_column(column):
        return False
    if _is_date_column(column):
        return False
    if _is_salary_column(column):
        return False
    return True


# Domaines d'email connus : permettent de corriger sans ambiguïté un « @ »
# manquant (ex. ``jean.dupontmail.com`` → ``jean.dupont@mail.com``).
KNOWN_EMAIL_DOMAINS = (
    "mail.com",
    "gmail.com",
    "hotmail.com",
    "hotmail.fr",
    "outlook.com",
    "outlook.fr",
    "yahoo.com",
    "yahoo.fr",
    "wanadoo.fr",
    "orange.fr",
    "free.fr",
    "live.fr",
    "live.com",
    "icloud.com",
    "protonmail.com",
)

EMAIL_RE_STRICT = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)

# Partie locale d'un email considérée comme un marqueur « inconnu » déguisé en
# adresse (``inconnu@mail.com``, ``unknown@…``). Une telle adresse n'est pas un
# email réel : c'est une donnée non disponible, traitée comme « Inconnu ».
PLACEHOLDER_EMAIL_LOCALS = frozenset(
    {"inconnu", "inconnue", "inconnus", "inconnues", "unknown"}
)


def is_placeholder_email(value):
    """Indique si une valeur est un email « placeholder » (inconnu@…, unknown@…)."""
    if value is None or pd.isna(value):
        return False
    if isinstance(value, (datetime, pd.Timestamp)):
        return False
    text = str(value).strip().lower()
    if "@" not in text:
        return False
    local = text.split("@", 1)[0].strip()
    return local in PLACEHOLDER_EMAIL_LOCALS


def fix_email(value):
    """Analyse une adresse email et renvoie ``(nettoyé, statut, action)``.

    Statuts : ``valide``, ``inconnu``, ``corrigé``, ``invalide``, ``placeholder``.

    - ``inconnu`` : marqueur « Inconnu » ou valeur absente/vide (non renseignée).
    - ``placeholder`` : adresse valide en forme mais qui est un marqueur d'inconnu
      (``inconnu@mail.com``, ``unknown@…``) → traitée comme « Inconnu ».
    - ``invalide`` : valeur renseignée mais de format incorrect (ex. ``marie.martin@``).

    Seule la correction *certaine* est appliquée : insertion d'un ``@``
    lorsqu'un domaine connu est présent en suffixe (``jean.dupontmail.com``).
    On n'invente jamais de domaine ni d'adresse complète.
    """
    if is_unknown(value):
        return str(value).strip(), "inconnu", "aucune"
    if pd.isna(value):
        return value, "inconnu", "aucune"
    text = str(value).strip().lower()
    if not text:
        return value, "inconnu", "aucune"

    # Email « placeholder » (``inconnu@mail.com``…) : pas une adresse réelle.
    if is_placeholder_email(text):
        return UNKNOWN_VALUE, "placeholder", "email placeholder « inconnu@… »"

    if EMAIL_RE_STRICT.match(text):
        return text, "valide", "aucune"

    # Domaine manquant (se termine par « @ ») : ne pas inventer.
    if text.endswith("@"):
        return text, "invalide", "signaler : domaine manquant"

    # « @ » absent : tente une insertion certaine via un domaine connu.
    if "@" not in text:
        for domain in sorted(KNOWN_EMAIL_DOMAINS, key=len, reverse=True):
            if text.endswith(domain) and len(text) > len(domain):
                local = text[: -len(domain)].rstrip(".")
                candidate = f"{local}@{domain}"
                if EMAIL_RE_STRICT.match(candidate):
                    return candidate, "corrigé", "« @ » manquant inséré"
        return text, "invalide", "signaler : « @ » manquant, correction incertaine"

    # Autre format invalide (caractères interdits, espaces…).
    return text, "invalide", "signaler : format invalide"


def _normalize_salary(value):
    """Convertit un montant en nombre flottant.

    Gère la virgule décimale française, le symbole monétaire et les espaces
    insécables. Ne renvoie jamais ``0`` pour une valeur inconnue : en cas
    d'échec, la valeur d'origine est conservée.
    """
    if value is None:
        return value
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return value
    # Retire symbole monétaire, espaces (dont insécable) et apostrophes.
    text = re.sub(r"[€$£\s\u00a0']", "", text)
    if "," in text and "." in text:
        # « 1.234,56 » : le point est un séparateur de milliers.
        text = text.replace(".", "").replace(",", ".")
    elif "," in text:
        # « 2800,50 » : la virgule est le séparateur décimal.
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return value  # non convertible : conserver la valeur d'origine.


def is_numeric_value(value):
    """Indique si une valeur est une donnée numérique.

    - int / float → True (sauf booléen).
    - chaîne convertible en nombre (``"1299.9"``, ``"29,99"``, ``"1 299,90 €"``)
      → True.
    - « Inconnu », chaîne vide, NaN, texte non numérique → False.

    Sert à valider les colonnes numériques sans jamais confondre « Inconnu »
    avec une valeur invalide.
    """
    if value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return True
    if is_unknown(value):
        return False
    text = str(value).strip()
    if not text:
        return False
    # Réutilise la normalisation des montants (virgule décimale, espaces,
    # symboles monétaires) pour décider si la chaîne représente un nombre.
    result = _normalize_salary(value)
    return isinstance(result, float) and not isinstance(result, bool)


def _to_int(value):
    """Convertit une valeur en entier si elle représente un entier exact.

    - ``1.0`` → ``1``, ``"2"`` → ``2``, ``"3,0"`` → ``3``.
    - Valeur non entière ou non convertible → conservée telle quelle.
    - Valeur manquante ou « Inconnu » → ``pd.NA``.
    """
    if value is None or isinstance(value, bool):
        return value
    if is_unknown(value):
        return pd.NA
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else value
    text = str(value).strip()
    if not text:
        return pd.NA
    try:
        number = float(text.replace(",", "."))
        if number.is_integer():
            return int(number)
    except ValueError:
        pass
    return value


def _is_ambiguous_date(value):
    """Indique si une date est ambiguë (jour et mois tous deux ≤ 12)."""
    if value is None or pd.isna(value):
        return False
    if isinstance(value, (datetime, pd.Timestamp)):
        return False
    text = str(value).strip()
    match = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", text)
    if not match:
        return False
    first, second = int(match.group(1)), int(match.group(2))
    return first <= 12 and second <= 12 and first != second


def _display(value):
    """Convertit une valeur en texte lisible pour le journal des modifications."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _normalize_phone(value):
    """Normalise un numéro de téléphone français en ``06XXXXXXXX``.

    ``+33 6 12 34 56 81`` → ``0612345681``
    ``06-12-34-56-80``     → ``0612345680``
    ``06.12.34.56.85``     → ``0612345685``
    """
    if pd.isna(value):
        return value
    text = str(value).strip()
    digits = re.sub(r"[^\d+]", "", text)
    # Préfixe international français (+33 / 0033) → 0.
    if digits.startswith("+33"):
        digits = "0" + digits[3:]
    elif digits.startswith("0033"):
        digits = "0" + digits[4:]
    digits = digits.replace("+", "")
    return digits if digits else value


# Formats de date acceptés, essayés dans l'ordre.
_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%Y/%m/%d",
    "%d/%m/%y",
)


def _normalize_date(value):
    """Normalise une date en ``AAAA-MM-JJ`` (ISO 8601).

    ``15/04/2024`` → ``2024-04-15``
    ``2024-01-15`` → ``2024-01-15`` (déjà conforme)
    """
    if pd.isna(value):
        return value
    # Déjà un objet date/datetime (pandas Timestamp, datetime.date…).
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.strftime("%Y-%m-%d")
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value  # introuvable : on laisse la valeur d'origine.


class DataCleaner:
    """Classe de base pour les opérations de nettoyage d'un DataFrame."""

    def __init__(self, dataframe):
        self.dataframe = dataframe
        # Compteurs des modifications effectuées (pour le rapport).
        self.changes = {}
        # Journal de traçabilité : liste de dictionnaires.
        self._change_log = []
        # Audit des emails (original / nettoyé / statut / action).
        self.email_audit = pd.DataFrame(
            columns=[
                "ligne",
                "colonne",
                "email_original",
                "email_nettoye",
                "statut_email",
                "action_email",
            ]
        )

    # --- Traçabilité -----------------------------------------------------
    def _record(self, index, column, old, new, correction_type, reason):
        """Ajoute une entrée au journal des modifications."""
        self._change_log.append(
            {
                "ligne": int(index) + 1,
                "colonne": column,
                "ancienne_valeur": _display(old),
                "nouvelle_valeur": _display(new),
                "type_correction": correction_type,
                "raison": reason,
            }
        )

    @property
    def change_log_df(self):
        """Renvoie le journal des modifications sous forme de DataFrame."""
        if not self._change_log:
            return pd.DataFrame(
                columns=[
                    "ligne",
                    "colonne",
                    "ancienne_valeur",
                    "nouvelle_valeur",
                    "type_correction",
                    "raison",
                ]
            )
        return pd.DataFrame(self._change_log)

    def remove_duplicates(self, subset=None, keep="first", ignore_case=False):
        """Supprime les doublons *exacts* (lignes identiques au contenu près).

        Quand ``subset`` vaut ``None`` (toutes les colonnes), les colonnes
        d'identifiant (``id``, ``index``…) sont ignorées afin de fusionner
        les lignes identiques qui ne diffèrent que par leur identifiant.

        Avec ``ignore_case=True``, la comparaison est faite en minuscules
        et sans espaces superflus, ce qui permet de détecter par exemple
        ``Alice`` et ``alice`` comme un même enregistrement.

        Ne supprime que les lignes 100 % identiques : les lignes proches mais
        incomplètes ou différentes sont conservées (voir « doublons potentiels »).
        """
        if subset is None:
            subset = [
                col
                for col in self.dataframe.columns
                if not _is_identifier(col)
            ]
        before = len(self.dataframe)
        if ignore_case:
            norm = self.dataframe.copy()
            text_cols = norm.select_dtypes(include=["object", "string"]).columns
            for col in text_cols:
                norm[col] = norm[col].str.lower().str.strip()
            mask = norm.duplicated(subset=subset, keep=keep)
        else:
            mask = self.dataframe.duplicated(subset=subset, keep=keep)

        # Journalise les lignes supprimées (traçabilité).
        for idx in self.dataframe.index[mask]:
            self._record(
                idx,
                "(ligne entière)",
                "doublon",
                "supprimée",
                "doublon",
                "doublon exact supprimé",
            )

        self.dataframe = self.dataframe[~mask].reset_index(drop=True)
        self.changes["duplicates_removed"] = before - len(self.dataframe)
        return self

    def merge_duplicates(self, subset=None, ignore_case=False):
        """Fusionne les doublons d'une même entité en une seule ligne.

        - Les lignes partageant la même clé (ex. ``email``) sont regroupées.
        - Les valeurs manquantes sont complétées par celles des lignes jumelles.
        - Seules les lignes *identiques* (à la casse et aux espaces près) sont
          fusionnées. Si deux lignes portent des valeurs différentes sur une
          même colonne (ex. deux dates d'inscription), elles représentent des
          enregistrements distincts et sont conservées séparément, afin de ne
          perdre aucune donnée.
        """
        df = self.dataframe.copy()

        if subset is None:
            subset = [
                col for col in df.columns if not _is_identifier(col)
            ]
        else:
            subset = list(subset)

        # Clé de regroupement normalisée (casse + espaces).
        key = df[subset].copy()
        for col in subset:
            series = key[col].astype(str)
            if ignore_case:
                series = series.str.lower()
            series = series.str.strip()
            # Une valeur manquante devient une clé unique pour ne jamais
            # fusionner à tort des lignes qui n'ont pas de clé.
            series = series.fillna(
                pd.Series(
                    [f"__missing__{i}__" for i in df.index], index=df.index
                )
            )
            key[col] = series

        group = key.apply(
            lambda row: "||".join(str(value) for value in row), axis=1
        )
        df["_group"] = group

        # Complète les valeurs manquantes à partir des lignes jumelles.
        for col in df.columns:
            if col in subset or col == "_group":
                continue
            df[col] = df.groupby("_group")[col].transform(
                lambda s: s.bfill().ffill() if s.notna().any() else s
            )

        # Compare les colonnes utiles (hors identifiants), normalisées, puis
        # supprime les lignes devenues identiques. Les lignes qui diffèrent
        # (ex. date différente) restent séparées.
        compared = [
            c
            for c in df.columns
            if c != "_group" and not _is_identifier(c)
        ]
        norm = df[compared].copy()
        for col in compared:
            series = norm[col].astype(str)
            if ignore_case:
                series = series.str.lower()
            series = series.str.strip()
            norm[col] = series.where(df[col].notna())

        mask = norm.duplicated(keep="first")
        self.dataframe = (
            df[~mask].drop(columns="_group").reset_index(drop=True)
        )
        return self

    def renumber_identifiers(self, start=1):
        """Réordonne les colonnes d'identifiant (``id``…) de façon continue.

        Après suppression des doublons, les identifiants peuvent présenter des
        trous (ex. ``1, 3, 5``). Cette méthode les réécrit séquentiellement en
        partant de ``start``, tout en conservant l'ancien identifiant dans une
        colonne ``ancien_id`` afin de tracer les modifications.
        """
        df = self.dataframe
        for col in df.columns:
            if not _is_identifier(col) or col == "ancien_id":
                continue
            old_values = df[col].astype(object)
            df[col] = range(start, start + len(df))
            # Rendre le type entier cohérent avec le reste (évite des floats).
            try:
                df[col] = df[col].astype("Int64")
            except (TypeError, ValueError):
                pass
            # Conserve l'ancien identifiant pour la traçabilité.
            if "ancien_id" not in df.columns:
                df.insert(
                    df.columns.get_loc(col) + 1, "ancien_id", old_values
                )
        self.dataframe = df
        return self

    def normalize_case(self, columns=None):
        """Convertit en minuscules les colonnes de texte (ou une sélection)."""
        cols = columns or self.dataframe.select_dtypes(
            include=["object", "string"]
        ).columns
        for col in cols:
            if col in self.dataframe.columns:
                self.dataframe[col] = self.dataframe[col].str.lower()
        return self

    def normalize_text(self):
        """Normalise la casse des noms propres et des libellés libres.

        - Les colonnes reconnues comme « nom » (:func:`_is_name_column`) et
          comme « libellé » (:func:`_is_label_column`, ex. ``produit``,
          ``article``) sont mises en casse « Capitales » (``DUPONT`` →
          ``Dupont``, ``ordinateur portable`` → ``Ordinateur Portable``),
          accents conservés. Cela garantit une présentation homogène : le
          même produit n'apparaît plus sous plusieurs casses différentes.
        - Les colonnes d'email, de catégorie et de code sont traitées par
          leurs méthodes dédiées (:meth:`normalize_emails`,
          :meth:`normalize_categories`, :meth:`normalize_codes`).
        """
        text_cols = list(
            self.dataframe.select_dtypes(include=["object", "string"]).columns
        )
        for col in text_cols:
            if not (_is_name_column(col) or _is_label_column(col)):
                continue
            series = self.dataframe[col]
            for idx, value in series.items():
                if pd.isna(value):
                    continue
                cleaned = str(value).strip().title()
                if cleaned != str(value):
                    self.dataframe.at[idx, col] = cleaned
                    self._record(
                        idx,
                        col,
                        value,
                        cleaned,
                        "casse",
                        "normalisation de la casse (nom/libellé)",
                    )
        return self

    def normalize_categories(self, mapping=None):
        """Normalise les catégories (services, types…) via un dictionnaire.

        Applique ``mapping`` (par défaut :attr:`DEFAULT_CATEGORY_MAP`) aux
        colonnes reconnues comme catégorie, en insensible à la casse et aux
        espaces. Les valeurs inconnues sont mises en casse « Capitales ».
        """
        mapping = mapping or DEFAULT_CATEGORY_MAP
        changed = 0
        for col in self.dataframe.columns:
            if not _is_category_column(col):
                continue
            series = self.dataframe[col]
            for idx, value in series.items():
                if pd.isna(value):
                    continue
                key = str(value).strip().lower()
                new = mapping.get(key, str(value).strip().title())
                if new != str(value):
                    self.dataframe.at[idx, col] = new
                    self._record(
                        idx,
                        col,
                        value,
                        new,
                        "catégorie",
                        f"normalisation de catégorie ({value} → {new})",
                    )
                    changed += 1
        self.changes["categories"] = changed
        return self

    def normalize_codes(self):
        """Uniformise la casse des codes/références en MAJUSCULES.

        ``cmd-006`` → ``CMD-006``. Les colonnes reconnues comme code
        (:func:`_is_code_column`, ex. ``numero_commande``) sont mises en
        majuscules pour une présentation homogène.
        """
        changed = 0
        for col in self.dataframe.columns:
            if not _is_code_column(col):
                continue
            series = self.dataframe[col]
            for idx, value in series.items():
                if pd.isna(value) or is_unknown(value):
                    continue
                text = str(value).strip()
                upper = text.upper()
                if upper != text:
                    self.dataframe.at[idx, col] = upper
                    self._record(
                        idx,
                        col,
                        value,
                        upper,
                        "casse",
                        "normalisation des codes en majuscules",
                    )
                    changed += 1
        self.changes["codes"] = changed
        return self

    def normalize_booleans(self):
        """Uniformise les choix binaires oui/non en minuscules.

        ``OUI`` → ``oui``, ``NON`` → ``non``, ``Non`` → ``non``. Les colonnes
        reconnues comme booléennes (:func:`_is_boolean_column`, ex.
        ``newsletter``) sont mises en minuscules pour une présentation
        homogène. Les valeurs « Inconnu » et les cellules vides sont laissées
        intactes.
        """
        changed = 0
        for col in self.dataframe.columns:
            if not _is_boolean_column(col):
                continue
            series = self.dataframe[col]
            for idx, value in series.items():
                if pd.isna(value) or is_unknown(value):
                    continue
                text = str(value).strip()
                lowered = text.lower()
                if lowered != text:
                    self.dataframe.at[idx, col] = lowered
                    self._record(
                        idx,
                        col,
                        value,
                        lowered,
                        "casse",
                        "normalisation des choix oui/non en minuscules",
                    )
                    changed += 1
        self.changes["booleans"] = changed
        return self

    def anonymize(self, columns=None):
        """Pseudonymise les colonnes sensibles (noms, emails, téléphones).

        Remplace les valeurs par des pseudonymes **déterministes** (même valeur
        → même pseudonyme), ce qui préserve les relations entre lignes tout en
        masquant les données personnelles. Les colonnes ciblées sont, par
        défaut, celles reconnues comme nom, email ou téléphone ; on peut en
        fournir une liste explicite via ``columns``.

        - Noms : ``Dupont`` → ``Personne_1``, ``Martin`` → ``Personne_2``…
        - Emails : ``alice@mail.com`` → ``email_1@anonyme.local``…
        - Téléphones : ``0612345678`` → ``telephone_1``…

        Les valeurs « Inconnu » et manquantes sont laissées intactes. Chaque
        remplacement est journalisé (type ``anonymisation``).
        """
        cols = columns or [
            c
            for c in self.dataframe.columns
            if _is_name_column(c) or _is_email_column(c) or _is_phone_column(c)
        ]

        # Compteurs par colonne pour des pseudonymes stables et lisibles.
        counters = {}
        changed = 0

        for col in cols:
            if col not in self.dataframe.columns:
                continue
            mapping = {}
            series = self.dataframe[col]
            for idx, value in series.items():
                if pd.isna(value) or is_unknown(value):
                    continue
                text = str(value).strip()
                if not text:
                    continue
                if text not in mapping:
                    counters[col] = counters.get(col, 0) + 1
                    n = counters[col]
                    if _is_email_column(col):
                        mapping[text] = f"email_{n}@anonyme.local"
                    elif _is_phone_column(col):
                        mapping[text] = f"telephone_{n}"
                    else:
                        mapping[text] = f"Personne_{n}"
                new = mapping[text]
                if new != text:
                    self.dataframe.at[idx, col] = new
                    self._record(
                        idx,
                        col,
                        value,
                        new,
                        "anonymisation",
                        "pseudonymisation de donnée sensible",
                    )
                    changed += 1

        self.changes["anonymized"] = changed
        return self

    def normalize_unknown(self):
        """Canonicalise les variantes du marqueur « Inconnu ».

        ``INCONNU``, ``inconnu``, ``Inconnue``… sont ramenés à la valeur
        standard ``Inconnu`` dans les colonnes de texte libre. Cela garantit
        un affichage et un comptage cohérents : le marqueur est reconnu quelle
        que soit la casse saisie à l'origine (ex. une ville notée ``INCONNU``
        devient ``Inconnu`` et est mise en évidence comme telle).
        """
        changed = 0
        for col in self.dataframe.columns:
            if not _is_placeholder_column(col):
                continue
            series = self.dataframe[col]
            for idx, value in series.items():
                if pd.isna(value):
                    continue
                if is_unknown(value) and str(value).strip() != UNKNOWN_VALUE:
                    self.dataframe.at[idx, col] = UNKNOWN_VALUE
                    self._record(
                        idx,
                        col,
                        value,
                        UNKNOWN_VALUE,
                        "inconnu",
                        "canonicalisation du marqueur « Inconnu »",
                    )
                    changed += 1
        self.changes["unknown"] = changed
        return self

    def trim_whitespace(self):
        """Supprime les espaces superflus dans les colonnes de texte.

        N'affecte que les vraies chaînes de caractères : les valeurs numériques
        (flottants issus de la conversion des salaires, etc.) sont laissées
        intactes, ce qui évite les erreurs ``.str`` sur des colonnes mixtes.
        """
        for col in self.dataframe.select_dtypes(include=["object", "string"]).columns:
            series = self.dataframe[col]
            self.dataframe[col] = series.map(
                lambda v: v.strip() if isinstance(v, str) else v
            )
        return self

    def normalize_phones(self):
        """Uniformise les numéros de téléphone (``06XXXXXXXX``).

        Supprime espaces, tirets et points, convertit ``+33`` / ``0033`` en
        ``0``. Un numéro n'est modifié que si le résultat est certain (10
        chiffres commençant par ``0``) ; sinon il est conservé et signalé.
        """
        changed = 0
        invalid = 0
        for col in self.dataframe.columns:
            if not _is_phone_column(col):
                continue
            series = self.dataframe[col]
            for idx, value in series.items():
                if pd.isna(value):
                    continue
                new = _normalize_phone(value)
                if new == value:
                    continue
                if re.fullmatch(r"0\d{9}", str(new)):
                    self.dataframe.at[idx, col] = new
                    self._record(
                        idx,
                        col,
                        value,
                        new,
                        "téléphone",
                        "normalisation du numéro",
                    )
                    changed += 1
                else:
                    self._record(
                        idx,
                        col,
                        value,
                        value,
                        "anomalie",
                        "numéro non normalisable (longueur/format incertain)",
                    )
                    invalid += 1
        self.changes["phones"] = changed
        self.changes["phones_invalid"] = invalid
        return self

    def normalize_dates(self):
        """Uniformise les dates au format ``AAAA-MM-JJ`` (ISO 8601).

        Convertit les formats mixtes (``15/04/2024``). Une date ambiguë
        (jour et mois tous deux ≤ 12) est signalée, jamais convertie
        silencieusement.
        """
        changed = 0
        for col in self.dataframe.columns:
            if not _is_date_column(col):
                continue
            series = self.dataframe[col]
            for idx, value in series.items():
                if pd.isna(value):
                    continue
                new = _normalize_date(value)
                ambiguous = _is_ambiguous_date(value)
                if new != value:
                    self.dataframe.at[idx, col] = new
                    reason = "conversion de format de date"
                    if ambiguous:
                        reason += " (date ambiguë JJ/MM, à vérifier)"
                    self._record(idx, col, value, new, "date", reason)
                    changed += 1
                elif ambiguous:
                    self._record(
                        idx,
                        col,
                        value,
                        value,
                        "anomalie",
                        "date ambiguë (jour/mois interchangeables), à vérifier",
                    )
        self.changes["dates"] = changed
        return self

    def normalize_emails(self):
        """Normalise et valide les adresses email.

        - Email valide → conservé.
        - Erreur évidente corrigeable sans inventer → corrigée
          (``jean.dupontmail.com`` → ``jean.dupont@mail.com``).
        - Email invalide mais NON corrigeable de façon fiable → remplacé par
          ``Inconnu`` (``marie.martin@`` → ``Inconnu``), tracé dans le journal.
        - Email vide/manquant → ``Inconnu``.
        - ``Inconnu`` → conservé tel quel.

        On n'invente jamais un domaine ni une adresse email. L'ancienne valeur
        reste traçable dans le journal de modification.

        Produit un audit ``email_audit`` (original / nettoyé / statut / action).
        """
        rows = []
        corrected = 0
        invalid = 0
        for col in self.dataframe.columns:
            if not _is_email_column(col):
                continue
            series = self.dataframe[col]
            for idx, value in series.items():
                original = value
                cleaned, status, action = fix_email(value)

                if status == "valide" and cleaned != _display(original):
                    # Email valide mais en casse mixte → mis en minuscules.
                    self.dataframe.at[idx, col] = cleaned
                    self._record(
                        idx,
                        col,
                        original,
                        cleaned,
                        "email",
                        "normalisation en minuscules",
                    )
                    corrected += 1
                elif status == "invalide":
                    # Non corrigeable de façon fiable → remplacé par « Inconnu ».
                    self.dataframe.at[idx, col] = UNKNOWN_VALUE
                    self._record(
                        idx,
                        col,
                        original,
                        UNKNOWN_VALUE,
                        "Email invalide",
                        "Adresse email incomplète et impossible à corriger "
                        "automatiquement sans inventer d'information.",
                    )
                    invalid += 1
                    cleaned = UNKNOWN_VALUE
                    status = "inconnu"
                    action = "remplacé par Inconnu"
                elif status == "corrigé" and cleaned != _display(original):
                    self.dataframe.at[idx, col] = cleaned
                    self._record(
                        idx,
                        col,
                        original,
                        cleaned,
                        "email",
                        action,
                    )
                    corrected += 1
                elif status == "placeholder":
                    # Adresse valide en forme mais marqueur d'inconnu
                    # (``inconnu@mail.com``) → remplacée par « Inconnu ».
                    self.dataframe.at[idx, col] = UNKNOWN_VALUE
                    self._record(
                        idx,
                        col,
                        original,
                        UNKNOWN_VALUE,
                        "Email placeholder",
                        "Adresse « inconnu@… » = donnée non disponible, "
                        "remplacée par « Inconnu ».",
                    )
                    cleaned = UNKNOWN_VALUE
                    status = "inconnu"
                    action = "remplacé par Inconnu (placeholder)"
                elif status == "inconnu" and not is_unknown(original):
                    # Valeur vide/manquante → « Inconnu ».
                    self.dataframe.at[idx, col] = UNKNOWN_VALUE
                    self._record(
                        idx,
                        col,
                        original,
                        UNKNOWN_VALUE,
                        "Email manquant",
                        "Adresse email absente, remplacée par « Inconnu ».",
                    )
                    cleaned = UNKNOWN_VALUE
                    action = "remplacé par Inconnu"

                rows.append(
                    {
                        "ligne": int(idx) + 1,
                        "colonne": col,
                        "email_original": _display(original),
                        "email_nettoye": _display(cleaned),
                        "statut_email": status,
                        "action_email": action,
                    }
                )
        if rows:
            self.email_audit = pd.DataFrame(rows)
        self.changes["emails_corriges"] = corrected
        self.changes["emails_invalides"] = invalid
        return self

    def normalize_salaries(self, log=True):
        """Normalise les montants au format ``X.XX`` (2 décimales fixes).

        Gère la virgule décimale française, les symboles monétaires et les
        espaces (``2800,50 €`` → ``2800.50``). Le résultat est **toujours**
        une chaîne à deux décimales pour garantir un affichage homogène
        (``1299.9``, ``29.99`` et ``449.0`` deviennent respectivement
        ``1299.90``, ``29.99`` et ``449.00``), sans jamais perdre les zéros
        de fin d'un montant monétaire. La conversion systématique en chaîne
        est essentielle : elle garantit que le type ne dépend pas de la façon
        dont le DataFrame a été lu (relecture CSV → float). Ne remplace
        jamais une valeur inconnue par ``0`` : en cas d'échec, la valeur
        d'origine est conservée.

        ``log=False`` applique la même normalisation sans journaliser : utile
        pour restituer les types après relecture d'un fichier déjà nettoyé.
        """
        changed = 0
        for col in self.dataframe.columns:
            if not _is_salary_column(col):
                continue
            # Convertit en object pour accepter un mélange flottants / chaînes
            # non convertibles (pandas 3.x refuse d'insérer un float dans un
            # dtype « str »).
            self.dataframe[col] = self.dataframe[col].astype(object)
            series = self.dataframe[col]
            for idx, value in series.items():
                if pd.isna(value) or is_unknown(value):
                    continue
                new = _normalize_salary(value)
                if isinstance(new, bool):
                    continue
                if isinstance(new, (int, float)):
                    formatted = f"{new:.2f}"
                    # Écrit toujours la chaîne normalisée (même si le texte
                    # d'origine est identique) pour fixer le type en chaîne.
                    self.dataframe.at[idx, col] = formatted
                    if log and formatted != str(value).strip():
                        self._record(
                            idx,
                            col,
                            value,
                            formatted,
                            "numérique",
                            "conversion en montant normalisé (2 décimales)",
                        )
                        changed += 1
                else:
                    if log:
                        self._record(
                            idx,
                            col,
                            value,
                            value,
                            "anomalie",
                            "montant non convertible, conservé tel quel",
                        )
        self.changes["salaries"] = changed
        return self

    def normalize_integers(self, log=True):
        """Convertit en entiers les colonnes de comptage (quantités…).

        Les colonnes reconnues comme entières (:func:`_is_integer_column`,
        ex. ``quantite``) sont converties en entiers (``1.0`` → ``1``,
        ``"2"`` → ``2``) avec le type nullable ``Int64`` : les valeurs
        manquantes restent manquantes (``<NA>``) et non ``0``. Une valeur
        non entière ou non convertible est conservée telle quelle.

        ``log=False`` applique la même conversion sans journaliser : utile
        pour restituer les types après relecture d'un fichier déjà nettoyé.
        """
        changed = 0
        for col in self.dataframe.columns:
            if not _is_integer_column(col):
                continue
            series = self.dataframe[col]
            new_values = []
            all_integer = True
            for idx, value in series.items():
                if pd.isna(value) or is_unknown(value):
                    new_values.append(pd.NA)
                    continue
                parsed = _to_int(value)
                if isinstance(parsed, int) and not isinstance(parsed, bool):
                    new_values.append(parsed)
                    if log and not isinstance(value, int):
                        self._record(
                            idx,
                            col,
                            value,
                            parsed,
                            "numérique",
                            "conversion en entier",
                        )
                        changed += 1
                else:
                    all_integer = False
                    new_values.append(value)
            if all_integer:
                self.dataframe[col] = pd.array(new_values, dtype="Int64")
            else:
                self.dataframe[col] = pd.Series(
                    new_values, index=series.index, dtype="object"
                )
        self.changes["integers"] = changed
        return self

    def fill_missing(self, value=""):
        """Remplace les valeurs manquantes en respectant le type des colonnes.

        - Colonnes numériques (int/float) : remplies par ``value`` uniquement
          si ``value`` est un nombre (ex. ``0``) ; sinon laissées manquantes
          (on n'écrit jamais un texte dans une colonne numérique).
        - Colonnes montant : remplies par ``value`` au format ``X.XX``
          uniquement si ``value`` est un nombre. Le marqueur « Inconnu » est
          toutefois accepté : une donnée absente peut être signalée comme
          telle, même dans une colonne montant.
        - Identifiants, codes et dates : jamais remplies par un placeholder
          texte (un code ou une date « Inconnu » serait incohérent).
        - Autres colonnes de texte : remplies par ``value``.
        """
        if value is None:
            return self
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return self

        value_is_numeric = is_numeric_value(value)

        for col in self.dataframe.columns:
            series = self.dataframe[col]
            # Colonne réellement numérique (int/float).
            if pd.api.types.is_numeric_dtype(series):
                if value_is_numeric:
                    fill = _normalize_salary(value)
                    if pd.api.types.is_integer_dtype(series):
                        fill = int(fill)
                    self.dataframe[col] = series.fillna(fill)
                continue
            # Colonne montant (sémantiquement numérique, lue en texte).
            if _is_salary_column(col):
                if value_is_numeric:
                    self.dataframe[col] = series.fillna(
                        f"{_normalize_salary(value):.2f}"
                    )
                elif is_unknown(value):
                    self.dataframe[col] = series.fillna(UNKNOWN_VALUE)
                continue
            # Identifiant / code / date : pas de placeholder texte.
            if not _is_placeholder_column(col):
                continue
            # Texte libre / email : remplit par la valeur.
            self.dataframe[col] = series.fillna(value)
        return self

    def apply_rules(self, rules):
        """Applique une liste de règles de nettoyage personnalisées.

        Chaque règle est un dictionnaire ``{"operation", "column", "value"}``.
        Les opérations reprennent les méthodes existantes du moteur : aucune
        logique de nettoyage n'est dupliquée. Renvoie la liste des
        descriptions d'opérations réellement appliquées (pour le rapport).
        """
        applied = []
        for rule in rules or []:
            operation = (rule.get("operation") or "").strip()
            column = (rule.get("column") or "").strip()
            value = rule.get("value") or ""
            columns = [column] if column else None

            if operation == "remove_duplicates":
                self.remove_duplicates(subset=columns, ignore_case=True)
                applied.append(
                    operation_entry(
                        "rule_remove_duplicates",
                        count=self.changes.get("duplicates_removed", 0),
                    )
                )
            elif operation == "trim_whitespace":
                self.trim_whitespace()
                applied.append(operation_entry("rule_trim_whitespace"))
            elif operation == "normalize_case":
                self.normalize_text()
                applied.append(operation_entry("rule_normalize_case"))
            elif operation == "normalize_emails":
                self.normalize_emails()
                applied.append(
                    operation_entry(
                        "rule_normalize_emails",
                        count=self.changes.get("emails_corriges", 0),
                    )
                )
            elif operation == "normalize_phones":
                self.normalize_phones()
                applied.append(
                    operation_entry(
                        "rule_normalize_phones", count=self.changes.get("phones", 0)
                    )
                )
            elif operation == "normalize_dates":
                self.normalize_dates()
                applied.append(
                    operation_entry(
                        "rule_normalize_dates", count=self.changes.get("dates", 0)
                    )
                )
            elif operation == "normalize_salaries":
                self.normalize_salaries()
                applied.append(
                    operation_entry(
                        "rule_normalize_salaries", count=self.changes.get("salaries", 0)
                    )
                )
            elif operation == "fill_missing":
                self.fill_missing(value)
                applied.append(operation_entry("rule_fill_missing", value=value))
            elif operation == "anonymize":
                self.anonymize(columns=columns)
                applied.append(
                    operation_entry(
                        "rule_anonymize", count=self.changes.get("anonymized", 0)
                    )
                )
        return applied

    @property
    def result(self):
        """Renvoie le DataFrame nettoyé."""
        return self.dataframe


def restore_semantic_types(df):
    """Restitue les types sémantiques après relecture d'un fichier nettoyé.

    La relecture d'un CSV ré-infère des types flottants qui perdent de
    l'information : un montant ``1299.90`` devient le flottant ``1299.9``
    (zéro de fin perdu) et un compteur ``1`` devient le flottant ``1.0``.
    Cette fonction ré-applique la normalisation finale (montants en chaînes
    à 2 décimales, compteurs en entiers ``Int64``) **sans journaliser**, afin
    que l'affichage, la revue manuelle et tout traitement ultérieur
    reflètent exactement le fichier nettoyé exporté.
    """
    cleaner = DataCleaner(df.copy())
    cleaner.normalize_salaries(log=False)
    cleaner.normalize_integers(log=False)
    return cleaner.result
