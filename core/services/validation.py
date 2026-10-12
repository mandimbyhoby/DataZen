"""Détection, validation et score de qualité des données (DataZen).

Ce module analyse un DataFrame et renvoie un rapport structuré des
problèmes détectés (doublons exacts, doublons potentiels, doublons par
similarité, valeurs manquantes, emails, dates, téléphones, catégories,
salaires), puis calcule un score de qualité global sur 100 décomposé en
critères objectifs.

Le module n'utilise que la bibliothèque standard (``re``, ``datetime``,
``difflib``) et pandas : aucune dépendance externe.
"""

import re
from collections import Counter
from datetime import datetime
from difflib import SequenceMatcher

import pandas as pd
from django.utils.translation import gettext as _

from .cleaning import (
    _DATE_FORMATS,
    _is_category_column,
    _is_date_column,
    _is_email_column,
    _is_identifier,
    _is_integer_column,
    _is_phone_column,
    _is_salary_column,
    DEFAULT_CATEGORY_MAP,
    UNKNOWN_VALUE,
    is_numeric_value,
    is_placeholder_email,
    is_unknown,
)

# Format d'adresse email raisonnable (local@domaine.ext).
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")

# Étiquettes lisibles alignées sur les formats reconnus dans ``cleaning.py``.
_DATE_LABELS = (
    "AAAA-MM-JJ",
    "JJ/MM/AAAA",
    "JJ-MM-AAAA",
    "JJ.MM.AAAA",
    "AAAA/MM/JJ",
    "JJ/MM/AA",
)
DATE_FORMAT_LABELS = tuple(zip(_DATE_FORMATS, _DATE_LABELS))


def is_valid_email(value):
    """Indique si une valeur est une adresse email syntaxiquement valide."""
    if pd.isna(value):
        return False
    return bool(EMAIL_RE.match(str(value).strip()))


def is_missing(value):
    """Indique si une valeur est manquante (NaN/None ou chaîne vide).

    Définition unique utilisée partout pour un comptage cohérent : une chaîne
    vide ou composée d'espaces compte comme manquante au même titre que
    NaN/None (cas typique après ``fillna("")``).
    """
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(value, str) and value.strip() == ""


def count_missing_cells(df):
    """Nombre total de cellules manquantes (NaN ou chaîne vide)."""
    return int(df.map(is_missing).sum().sum())


def text_similarity(a, b):
    """Similarité textuelle entre deux valeurs (0.0 à 1.0), via ``difflib``."""
    if a is None or b is None or pd.isna(a) or pd.isna(b):
        return 0.0
    sa, sb = str(a).strip().lower(), str(b).strip().lower()
    if not sa or not sb:
        return 0.0
    return SequenceMatcher(None, sa, sb).ratio()


def detect_duplicates(df, subset=None):
    """Compte les doublons exacts (casse/espaces ignorés), hors identifiants."""
    if subset is None:
        subset = [c for c in df.columns if not _is_identifier(c)]
    norm = df[subset].copy()
    for col in norm.columns:
        if str(norm[col].dtype) in ("object", "string", "str"):
            norm[col] = norm[col].astype("string").str.lower().str.strip()
    return int(norm.duplicated().sum())


def detect_missing(df):
    """Renvoie ``{colonne: {"count": n, "percent": p}}`` par colonne.

    Une valeur est manquante si elle est NaN/None ou une chaîne vide, en
    cohérence avec :func:`detect_email_report` : un email vide est donc compté
    à la fois dans « emails manquants » et dans le total des valeurs manquantes
    de sa colonne.
    """
    result = {}
    n = len(df)
    for col in df.columns:
        count = int(df[col].map(is_missing).sum())
        if count:
            result[col] = {
                "count": count,
                "percent": round(100 * count / n, 1) if n else 0.0,
            }
    return result


def detect_email_report(df):
    """Analyse les colonnes email en 3 catégories : valide, invalide, inconnu.

    - ``valide`` : format conforme (ex. ``jean.dupont@mail.com``).
    - ``invalide`` : valeur renseignée mais format incorrect (ex. ``marie.martin@``).
    - ``inconnu`` : marqueur « Inconnu » ou valeur absente/vide (non renseignée).

    « Inconnu » n'est jamais compté comme email invalide.
    """
    valid = 0
    invalid = 0
    unknown = 0
    issues = []
    unknown_rows = []
    for col in df.columns:
        if not _is_email_column(col):
            continue
        for idx, value in df[col].items():
            if is_unknown(value) or is_missing(value):
                unknown += 1
                unknown_rows.append((int(idx), col, str(value).strip()))
                continue
            # Email « placeholder » (``inconnu@mail.com``) : donnée non
            # disponible, comptée comme « inconnu », jamais comme valide.
            if is_placeholder_email(value):
                unknown += 1
                unknown_rows.append((int(idx), col, str(value).strip()))
                continue
            text = str(value).strip()
            if EMAIL_RE.match(text):
                valid += 1
            else:
                invalid += 1
                issues.append((int(idx), col, text))
    return {
        "valid": valid,
        "invalid": invalid,
        "unknown": unknown,
        "issues": issues,
        "unknown_rows": unknown_rows,
    }


def detect_unknown(df):
    """Renvoie ``{colonne: count}`` du nombre de valeurs « Inconnu ».

    « Inconnu » est une valeur spéciale (donnée absente/indisponible), distincte
    des valeurs manquantes (NaN/chaîne vide) et des valeurs invalides.
    """
    result = {}
    for col in df.columns:
        count = int(df[col].map(is_unknown).sum())
        if count:
            result[col] = count
    return result


def _potential_key_columns(df):
    """Colonnes servant de clé « naturelle » pour repérer les doublons.

    Priorité : ``nom + prénom`` → ``nom`` seul → ``email``.
    """
    lowered = {str(c).lower(): c for c in df.columns}
    name_tokens = ("nom", "name", "last_name", "lastname")
    first_tokens = ("prenom", "prénom", "first_name", "firstname")

    nom = next((lowered[t] for t in name_tokens if t in lowered), None)
    prenom = next((lowered[t] for t in first_tokens if t in lowered), None)
    if nom and prenom:
        return [nom, prenom]
    if nom:
        return [nom]

    email = next((c for c in df.columns if _is_email_column(c)), None)
    return [email] if email else []


def _normalized(df, cols):
    """Copie normalisée (minuscules + espaces) d'une sélection de colonnes."""
    out = df[cols].copy()
    for col in cols:
        s = out[col].astype(str).str.lower().str.strip()
        out[col] = s.where(df[col].notna())
    return out


def detect_potential_duplicates(df):
    """Repère les doublons potentiels (même clé naturelle, contenu différent).

    Deux lignes partageant la même clé (nom + prénom, ou email) mais dont le
    contenu n'est pas strictement identique sont signalées, sans suppression.

    Renvoie une liste de dictionnaires :
    ``{key, rows, score, similar_columns, reason, recommendation}``.
    """
    key_cols = _potential_key_columns(df)
    if not key_cols:
        return []

    key = _normalized(df, key_cols)
    # Une clé absente (« Inconnu » ou manquante) n'identifie aucun
    # enregistrement : elle ne doit jamais regrouper deux lignes distinctes.
    # On la rend unique pour chaque ligne afin d'éviter les faux doublons
    # (ex. deux clients différents dont l'email est « Inconnu »).
    for col in key.columns:
        absent = key[col].map(lambda v: is_missing(v) or is_unknown(v))
        key[col] = key[col].mask(
            absent,
            pd.Series([f"__absent_{i}__" for i in df.index], index=df.index),
        )
    group = key.apply(lambda row: "||".join(str(v) for v in row), axis=1)

    compared = [
        c for c in df.columns if c not in key_cols and not _is_identifier(c)
    ]
    norm = _normalized(df, compared) if compared else pd.DataFrame(index=df.index)

    potential = []
    for g, idxs in df.groupby(group).groups.items():
        if len(idxs) < 2:
            continue
        sub = norm.loc[idxs] if not norm.empty else pd.DataFrame(index=idxs)
        # Lignes identiques = doublons exacts (gérés ailleurs), pas potentiels.
        if not sub.empty and sub.nunique(dropna=False).le(1).all():
            continue

        differing = []
        best_score = 0.0
        for c in compared:
            values = df.loc[idxs, c].tolist()
            sims = [
                text_similarity(values[i], values[j])
                for i in range(len(values))
                for j in range(i + 1, len(values))
            ]
            if sims:
                best_score = max(best_score, max(sims))
                if any(s < 1.0 for s in sims):
                    differing.append(c)

        potential.append(
            {
                "key": g,
                "rows": [int(i) for i in idxs],
                "score": round(best_score, 3),
                "similar_columns": differing,
                "reason": "même clé naturelle mais valeurs différentes ou incomplètes",
                "recommendation": "à vérifier manuellement",
            }
        )
    return potential


def detect_fuzzy_duplicates(df, threshold=0.8, max_rows=500):
    """Détecte les doublons par similarité textuelle (fuzzy matching).

    Compare les lignes deux à deux sur les colonnes identifiantes (nom,
    prénom, email). Renvoie une liste de dictionnaires
    ``{row_a, row_b, score, similar_columns, reason, recommendation}``.

    Limité à ``max_rows`` lignes pour rester performant.
    """
    if len(df) > max_rows:
        return []

    lowered = {str(c).lower(): c for c in df.columns}
    preferred = []
    for token in ("nom", "name", "prenom", "prénom", "first", "last"):
        if token in lowered and lowered[token] not in preferred:
            preferred.append(lowered[token])
    email = next((c for c in df.columns if _is_email_column(c)), None)
    if email:
        preferred.append(email)
    if not preferred:
        text_cols = list(df.select_dtypes(include=["object", "string"]).columns)
        preferred = [c for c in text_cols if not _is_identifier(c)][:3]
    if not preferred:
        return []

    results = []
    n = len(df)
    for i in range(n):
        for j in range(i + 1, n):
            best = 0.0
            sim_cols = []
            for c in preferred:
                s = text_similarity(df.iloc[i][c], df.iloc[j][c])
                best = max(best, s)
                if s >= 0.7:
                    sim_cols.append(c)
            # Ignore les paires strictement identiques (doublons exacts déjà
            # traités) : on ne signale que les similarités imparfaites (typos).
            if best >= threshold and best < 0.999:
                results.append(
                    {
                        "row_a": int(i),
                        "row_b": int(j),
                        "score": round(best, 3),
                        "similar_columns": sim_cols,
                        "reason": "similarité textuelle élevée (fuzzy matching)",
                        "recommendation": "à vérifier manuellement",
                    }
                )
    return results


def _date_label(value):
    """Renvoie le format reconnu ou ``None`` si la date est invalide/absente."""
    if pd.isna(value):
        return None
    if isinstance(value, (datetime, pd.Timestamp)):
        return "YYYY-MM-DD"
    text = str(value).strip()
    for fmt, label in DATE_FORMAT_LABELS:
        try:
            datetime.strptime(text, fmt)
            return label
        except ValueError:
            continue
    return None


def _date_format_display_label(label):
    if label == "YYYY-MM-DD":
        return _("YYYY-MM-DD")
    if label is None:
        return _("Unknown")
    return label


def detect_date_issues(df):
    """Par colonne de date : comptage des formats et des dates invalides.

    La valeur « Inconnu » est une donnée non disponible : elle n'est ni une
    date invalide ni un format non standard, elle est ignorée ici (elle est
    comptée séparément dans :func:`detect_unknown`).
    """
    result = {}
    for col in df.columns:
        if not _is_date_column(col):
            continue
        counts = {}
        invalid = 0
        for value in df[col]:
            if pd.isna(value) or is_unknown(value):
                continue
            label = _date_label(value)
            if label is None:
                invalid += 1
            display_label = _date_format_display_label(label)
            counts[display_label] = counts.get(display_label, 0) + 1
        result[col] = {
            "counts": counts,
            "non_standard": sum(
                n
                for lbl, n in counts.items()
                if lbl not in (_("YYYY-MM-DD"), _("Unknown"))
            ),
            "invalid": invalid,
        }
    return result


def detect_phone_issues(df):
    """Par colonne de téléphone : total, standard, invalides.

    La valeur « Inconnu » est une donnée non disponible : elle n'est pas un
    numéro invalide, elle est ignorée ici (comptée dans :func:`detect_unknown`).
    """
    result = {}
    for col in df.columns:
        if not _is_phone_column(col):
            continue
        total = 0
        standard = 0
        for value in df[col]:
            if pd.isna(value) or is_unknown(value):
                continue
            total += 1
            if re.fullmatch(r"0\d{9}", str(value).strip()):
                standard += 1
        result[col] = {
            "total": total,
            "standard": standard,
            "invalid": total - standard,
            "non_standard": total - standard,
        }
    return result


def detect_category_issues(df):
    """Évalue la cohérence des colonnes catégorielles."""
    total = 0
    inconsistent = 0
    for col in df.columns:
        if not _is_category_column(col):
            continue
        for value in df[col]:
            if pd.isna(value):
                continue
            total += 1
            key = str(value).strip().lower()
            if key in DEFAULT_CATEGORY_MAP and DEFAULT_CATEGORY_MAP[key] != str(value).strip():
                inconsistent += 1
    return {"total": total, "inconsistent": inconsistent}


def detect_salary_issues(df):
    """Compte les montants non numériques (invalides).

    - Une valeur numérique (int/float, ou chaîne convertible) → valide.
    - « Inconnu » / NaN → ignoré ici (donnée non disponible, comptée dans
      :func:`detect_unknown`), jamais invalide.
    - Toute autre valeur non numérique → invalide.
    """
    total = 0
    invalid = 0
    for col in df.columns:
        if not _is_salary_column(col):
            continue
        for value in df[col]:
            if pd.isna(value) or is_unknown(value):
                continue
            total += 1
            if not is_numeric_value(value):
                invalid += 1
    return {"total": total, "invalid": invalid}


def _numeric_values(series):
    """Extrait les valeurs numériques exploitables d'une colonne.

    Ignore « Inconnu », les valeurs manquantes et les chaînes non
    convertibles : seules les observations réellement numériques servent au
    calcul des statistiques (moyenne, écart-type, quartiles).
    """
    numbers = []
    for value in series:
        if pd.isna(value) or is_unknown(value):
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            numbers.append(float(value))
            continue
        text = str(value).strip()
        if not text:
            continue
        try:
            numbers.append(float(text.replace(",", ".")))
        except (TypeError, ValueError):
            continue
    return numbers


def detect_outliers(df, method="iqr", threshold=1.5):
    """Détecte les valeurs aberrantes (outliers) sur les colonnes numériques.

    Deux méthodes, toutes deux **non destructives** (simple signalement) :

    - ``iqr`` (défaut) : méthode de l'écart interquartile. Une valeur est
      aberrante si elle est inférieure à ``Q1 − k·IQR`` ou supérieure à
      ``Q3 + k·IQR``, avec ``k = threshold`` (1,5 par défaut, convention de
      Tukey). Robuste aux valeurs extrêmes.
    - ``zscore`` : méthode de l'écart réduit. Une valeur est aberrante si
      ``|z| > threshold`` (3 par défaut). Sensible aux valeurs extrêmes, donc
      réservée aux distributions proches de la normale.

    Les colonnes analysées sont celles reconnues comme numériques
    (``_is_salary_column`` ou ``_is_integer_column``) ou dont toutes les
    valeurs renseignées sont numériques. « Inconnu » et les valeurs
    manquantes sont ignorées.

    Renvoie une liste de dictionnaires :
    ``{colonne, ligne, valeur, borne_basse, borne_haute, methode}``.
    """
    if method not in ("iqr", "zscore"):
        method = "iqr"

    outliers = []
    for col in df.columns:
        # Colonne numérique : reconnue par nom, ou toutes valeurs numériques.
        if not (
            _is_salary_column(col)
            or _is_integer_column(col)
            or (
                df[col].map(
                    lambda v: pd.isna(v) or is_unknown(v) or is_numeric_value(v)
                ).all()
            )
        ):
            continue

        numbers = _numeric_values(df[col])
        if len(numbers) < 4:
            # Trop peu d'observations pour un calcul fiable de dispersion.
            continue

        if method == "zscore":
            mean = sum(numbers) / len(numbers)
            variance = sum((x - mean) ** 2 for x in numbers) / len(numbers)
            std = variance ** 0.5
            if std == 0:
                continue
            low = mean - threshold * std
            high = mean + threshold * std
        else:
            ordered = sorted(numbers)
            n = len(ordered)
            q1 = ordered[int(n * 0.25)]
            q3 = ordered[int(n * 0.75)]
            iqr = q3 - q1
            if iqr == 0:
                continue
            low = q1 - threshold * iqr
            high = q3 + threshold * iqr

        for idx, value in df[col].items():
            if pd.isna(value) or is_unknown(value) or isinstance(value, bool):
                continue
            try:
                num = float(str(value).replace(",", "."))
            except (TypeError, ValueError):
                continue
            if num < low or num > high:
                outliers.append(
                    {
                        "colonne": str(col),
                        "ligne": int(idx) + 1,
                        "valeur": num,
                        "borne_basse": round(low, 2),
                        "borne_haute": round(high, 2),
                        "methode": method,
                    }
                )

    return outliers


def parse_regex_rules(text):
    """Parse une chaîne de règles regex « colonne:motif » en liste de dicts.

    Une règle par ligne, séparée par le premier « : ». Les lignes vides ou
    sans « : » sont ignorées. Renvoie une liste de dictionnaires
    ``{"colonne", "pattern", "label"}``.
    """
    rules = []
    if not text:
        return rules
    for line in str(text).splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        col, pattern = line.split(":", 1)
        col = col.strip()
        pattern = pattern.strip()
        if not col or not pattern:
            continue
        rules.append({"colonne": col, "pattern": pattern, "label": pattern})
    return rules


def detect_regex_violations(df, rules):
        """Détecte les valeurs qui ne respectent pas des règles regex personnalisées.

        ``rules`` est une liste de dictionnaires ``{"colonne": ..., "pattern": ...,
        "label": ...}``. Pour chaque règle, on signale les lignes dont la valeur
        (renseignée, hors « Inconnu »/manquant) ne correspond pas au motif.

        Renvoie une liste de dictionnaires :
        ``{colonne, ligne, valeur, pattern, label}``.
        """
        violations = []
        for rule in rules:
            col = rule.get("colonne")
            pattern = rule.get("pattern")
            label = rule.get("label") or pattern
            if not col or not pattern or col not in df.columns:
                continue
            try:
                regex = re.compile(pattern)
            except re.error:
                continue
            for idx, value in df[col].items():
                if pd.isna(value) or is_unknown(value):
                    continue
                text = str(value).strip()
                if not text:
                    continue
                if not regex.search(text):
                    violations.append(
                        {
                            "colonne": str(col),
                            "ligne": int(idx) + 1,
                            "valeur": text,
                            "pattern": pattern,
                            "label": label,
                        }
                    )
        return violations


def profile_dataframe(df):
        """Profilage avancé des données (statistiques descriptives enrichies).

        Complète les statistiques de base du dashboard avec des indicateurs
        utiles à un data analyst : pour chaque colonne, renvoie le type détecté,
        le nombre de valeurs renseignées, le taux de complétude, le nombre de
        valeurs uniques, la valeur la plus fréquente (mode), et — pour les
        colonnes numériques — min, max, moyenne, médiane, écart-type, quartiles
        (Q1/Q3) et nombre de valeurs aberrantes (méthode IQR).

        Les valeurs « Inconnu » et manquantes sont exclues des calculs. La
        fonction est **non destructive** : elle ne modifie jamais le DataFrame.

        Renvoie une liste de dictionnaires, un par colonne.
        """
        outliers_by_col = {}
        for o in detect_outliers(df):
            outliers_by_col.setdefault(o["colonne"], 0)
            outliers_by_col[o["colonne"]] += 1

        profile = []
        for col in df.columns:
            series = df[col]
            values = [
                v for v in series if (not pd.isna(v)) and (not is_unknown(v))
            ]
            n_filled = len(values)
            n_total = len(df)

            # Type détecté (réutilise la logique de détection de colonne).
            if _is_salary_column(col) or _is_integer_column(col):
                ctype = "numérique"
            elif _is_email_column(col):
                ctype = "email"
            elif _is_phone_column(col):
                ctype = "téléphone"
            elif _is_date_column(col):
                ctype = "date"
            elif _is_category_column(col):
                ctype = "catégorie"
            elif _is_identifier(col):
                ctype = "identifiant"
            else:
                remaining = [
                    v for v in values if is_numeric_value(v)
                ]
                ctype = "numérique" if remaining and len(remaining) == len(values) else "texte"

            entry = {
                "colonne": str(col),
                "type": ctype,
                "renseigne": n_filled,
                "completude": round(100 * n_filled / n_total, 1) if n_total else 100.0,
                "n_unique": len({str(v) for v in values}),
                "mode": "—",
                "min": "—",
                "max": "—",
                "moyenne": "—",
                "mediane": "—",
                "ecart_type": "—",
                "q1": "—",
                "q3": "—",
                "outliers": outliers_by_col.get(str(col), 0),
            }

            if values:
                mode, freq = Counter(str(v) for v in values).most_common(1)[0]
                entry["mode"] = f"{mode} ({freq})"

            if ctype == "numérique":
                nums = []
                for v in values:
                    try:
                        nums.append(float(str(v).replace(",", ".")))
                    except (TypeError, ValueError):
                        continue
                if nums:
                    nums_sorted = sorted(nums)
                    n = len(nums_sorted)
                    mean = sum(nums_sorted) / n
                    variance = sum((x - mean) ** 2 for x in nums_sorted) / n
                    entry["min"] = f"{nums_sorted[0]:g}"
                    entry["max"] = f"{nums_sorted[-1]:g}"
                    entry["moyenne"] = f"{mean:.2f}"
                    entry["mediane"] = f"{nums_sorted[n // 2]:g}" if n % 2 else f"{(nums_sorted[n // 2 - 1] + nums_sorted[n // 2]) / 2:g}"
                    entry["ecart_type"] = f"{variance ** 0.5:.2f}"
                    entry["q1"] = f"{nums_sorted[int(n * 0.25)]:g}"
                    entry["q3"] = f"{nums_sorted[int(n * 0.75)]:g}"

            profile.append(entry)

        return profile


def build_detection(df):
    """Analyse complète d'un DataFrame (détection ou validation).

    Renvoie les comptes et les coordonnées des problèmes détectés.
    """
    emails = detect_email_report(df)
    dates = detect_date_issues(df)
    phones = detect_phone_issues(df)
    salaries = detect_salary_issues(df)

    for name, detector in (("dates", dates), ("phones", phones)):
        for col in detector:
            detector[col]["issues"] = []
    salaries["issues"] = []

    for row_index, row in df.iterrows():
        for col, value in row.items():
            if is_missing(value) or is_unknown(value):
                continue
            if col in dates and _date_label(value) is None:
                dates[col]["issues"].append((int(row_index), col, str(value)))
            if col in phones and not re.fullmatch(r"0\d{9}", str(value).strip()):
                phones[col]["issues"].append((int(row_index), col, str(value)))
            if _is_salary_column(col) and not is_numeric_value(value):
                salaries["issues"].append((int(row_index), col, str(value)))

    return {
        "duplicates": detect_duplicates(df),
        "potential_duplicates": detect_potential_duplicates(df),
        "fuzzy_duplicates": detect_fuzzy_duplicates(df),
        "missing": detect_missing(df),
        "unknown": detect_unknown(df),
        "emails": emails,
        "dates": dates,
        "phones": phones,
        "categories": detect_category_issues(df),
        "salaries": salaries,
        "outliers": detect_outliers(df),
    }


# Pondérations du score de qualité (somme = 1.0, donc 100 %).
#
# Ces poids sont volontairement configurables : modifiez-les ici pour
# ajuster l'importance relative de chaque dimension dans le score final.
QUALITY_WEIGHTS = {
    "complétude": 0.30,   # part de données réellement renseignées
    "validité": 0.30,     # part de valeurs conformes aux règles attendues
    "unicité": 0.20,      # absence de doublons (exacts et potentiels)
    "cohérence": 0.15,    # valeurs dans un état « valide ou Inconnu »
    "conformité": 0.05,   # formats standardisés après normalisation
}


def _build_explanations(detection, metrics):
    """Build translated explanations for the quality score."""
    explanations = []

    missing = metrics["missing_cells"]
    unknown = metrics["unknown_cells"]
    if unknown > 0:
        explanations.append({"type": "warn", "text": _("%(count)s unknown value(s) (data unavailable)") % {"count": unknown}})
    if missing > 0:
        explanations.append({"type": "warn", "text": _("%(count)s missing value(s)") % {"count": missing}})
    if missing == 0 and unknown == 0:
        explanations.append({"type": "ok", "text": _("No missing or unknown values")})

    invalid = metrics["invalid_cells"]
    if invalid > 0:
        explanations.append({"type": "warn", "text": _("%(count)s invalid value(s) among filled data") % {"count": invalid}})
    else:
        explanations.append({"type": "ok", "text": _("All filled values are valid")})

    exact = metrics["exact_duplicates"]
    potential = metrics["potential_duplicates"]
    if exact > 0:
        explanations.append({"type": "warn", "text": _("%(count)s exact duplicate(s) remaining") % {"count": exact}})
    else:
        explanations.append({"type": "ok", "text": _("No exact duplicates")})
    if potential > 0:
        explanations.append({"type": "warn", "text": _("%(count)s potential duplicate(s) need manual review (reduced penalty)") % {"count": potential}})
    else:
        explanations.append({"type": "ok", "text": _("No potential duplicates")})

    if invalid > 0:
        explanations.append({"type": "warn", "text": _("%(count)s inconsistent value(s) remaining (neither valid nor unknown)") % {"count": invalid}})
    else:
        explanations.append({"type": "ok", "text": _("Data is consistent: each value is valid or unknown")})

    nonstd = metrics["non_standard_cells"]
    if nonstd > 0:
        explanations.append({"type": "warn", "text": _("%(count)s non-standard value(s)") % {"count": nonstd}})
    else:
        explanations.append({"type": "ok", "text": _("Formats standardized (phones, dates)")})

    return explanations


def compute_quality_score(df, detection=None):
    """Calcule un score de qualité **explicable** sur 100, reflétant la qualité
    du DataFrame **final après nettoyage**.

    Cinq dimensions indépendantes, chacune sur 100, pondérées :

    1. **Complétude** (30 %) — proportion de cellules réellement renseignées.
       Une cellule « Inconnu » **ou** manquante n'est pas renseignée :
       ``complétude = cellules_renseignées / cellules_totales × 100``.

    2. **Validité** (30 %) — proportion de valeurs valides parmi les cellules
       renseignées (hors manquantes et hors « Inconnu ») :
       ``validité = 1 − invalides / renseignées × 100``.
       « Inconnu » n'est **pas** invalide : il est exclu du dénominateur.

    3. **Unicité** (20 %) — absence de doublons. Un doublon exact retire une
       pénalité forte (1/n), un doublon potentiel une pénalité réduite (0,5/n),
       car il nécessite une simple vérification humaine (jamais supprimé).

    4. **Cohérence** (15 %) — proportion de cellules dans un état acceptable
       (valide ou « Inconnu ») : une cellule renseignée mais invalide est une
       incohérence restante.

    5. **Conformité** (5 %) — proportion de formats standardisés (téléphones
       et dates au format canonique) après normalisation.

    Le score final est la somme pondérée, bornée à [0, 100].

    Retourne un dictionnaire riche :
    ``{total, components, weights, details, explanations}``.
    """
    detection = detection or build_detection(df)
    n = len(df)
    n_cols = df.shape[1]
    total_cells = n * n_cols

    # --- Métriques intermédiaires (partagées) ---------------------------
    missing_cells = sum(v["count"] for v in detection["missing"].values())
    unknown_cells = sum(detection["unknown"].values())
    complete_cells = total_cells - missing_cells - unknown_cells

    email_invalid = detection["emails"]["invalid"]
    phone_invalid = sum(v["invalid"] for v in detection["phones"].values())
    phone_total = sum(v["total"] for v in detection["phones"].values())
    date_invalid = sum(v["invalid"] for v in detection["dates"].values())
    date_total = sum(sum(v["counts"].values()) for v in detection["dates"].values())
    salary_invalid = detection["salaries"]["invalid"]
    salary_total = detection["salaries"]["total"]

    # Cellules « invalides » = renseignées mais au mauvais format.
    invalid_cells = email_invalid + phone_invalid + date_invalid + salary_invalid
    # Cellules renseignées = total − manquantes − inconnues.
    renseignees = complete_cells

    exact_duplicates = detection["duplicates"]
    potential_duplicates = len(detection["potential_duplicates"])

    phone_nonstd = sum(v["non_standard"] for v in detection["phones"].values())
    date_nonstd = sum(v["non_standard"] for v in detection["dates"].values())
    non_standard_cells = phone_nonstd + date_nonstd

    # --- 1. Complétude (30 %) ------------------------------------------
    completeness = (
        100 * (complete_cells / total_cells) if total_cells else 100.0
    )

    # --- 2. Validité (30 %) --------------------------------------------
    # Sur les cellules renseignées uniquement : « Inconnu » et manquantes
    # sont exclues, donc jamais comptées comme invalides.
    validity = (
        100 * (1 - invalid_cells / renseignees) if renseignees else 100.0
    )

    # --- 3. Unicité (20 %) ---------------------------------------------
    # Doublon exact : pénalité forte (1/n par doublon).
    # Doublon potentiel : pénalité réduite (0,5/n par groupe), vérification
    # humaine requise mais non supprimé automatiquement.
    exact_penalty = exact_duplicates / n if n else 0.0
    potential_penalty = 0.5 * potential_duplicates / n if n else 0.0
    uniqueness = 100 * (1 - exact_penalty - potential_penalty)
    uniqueness = max(0.0, min(100.0, uniqueness))

    # --- 4. Cohérence (15 %) -------------------------------------------
    # Une cellule renseignée mais invalide est une incohérence (ni valide,
    # ni « Inconnu »). Rapportée au total de cellules.
    coherence = (
        100 * (1 - invalid_cells / total_cells) if total_cells else 100.0
    )

    # --- 5. Conformité / normalisation (5 %) ---------------------------
    # Formats standard parmi les cellules applicables (téléphones + dates).
    fmt_phone = 100 * (1 - phone_nonstd / phone_total) if phone_total else 100.0
    fmt_date = 100 * (1 - date_nonstd / date_total) if date_total else 100.0
    conformity = (fmt_phone + fmt_date) / 2

    # --- Assemblage -----------------------------------------------------
    components = {
        "complétude": round(completeness, 1),
        "validité": round(validity, 1),
        "unicité": round(uniqueness, 1),
        "cohérence": round(coherence, 1),
        "conformité": round(conformity, 1),
    }
    # Somme pondérée, bornée à [0, 100].
    total = round(sum(components[k] * QUALITY_WEIGHTS[k] for k in components), 1)
    total = max(0.0, min(100.0, total))

    metrics = {
        "missing_cells": missing_cells,
        "unknown_cells": unknown_cells,
        "invalid_cells": invalid_cells,
        "exact_duplicates": exact_duplicates,
        "potential_duplicates": potential_duplicates,
        "non_standard_cells": non_standard_cells,
    }

    return {
        "total": total,
        "components": components,
        "weights": {k: int(v * 100) for k, v in QUALITY_WEIGHTS.items()},
        # Liste ordonnée pour l'affichage (nom, valeur, pondération).
        "breakdown": [
            {
                "name": name,
                "value": components[name],
                "weight": int(QUALITY_WEIGHTS[name] * 100),
            }
            for name in components
        ],
        "details": {
            "score_final": total,
            "score_completude": components["complétude"],
            "score_validite": components["validité"],
            "score_unicite": components["unicité"],
            "score_coherence": components["cohérence"],
            "score_conformite": components["conformité"],
        },
        "explanations": _build_explanations(detection, metrics),
    }


def calculate_quality_score(df, detection=None):
    """Fonction de transparence : renvoie les scores de chaque dimension.

    Retourne un dictionnaire plat, lisible et documenté :
    ``{score_final, score_completude, score_validite, score_unicite,
    score_coherence, score_conformite, weights, explanations}``.

    Pratique pour un affichage externe (Streamlit, logs, API).
    """
    rich = compute_quality_score(df, detection)
    return {
        "score_final": rich["total"],
        "score_completude": rich["components"]["complétude"],
        "score_validite": rich["components"]["validité"],
        "score_unicite": rich["components"]["unicité"],
        "score_coherence": rich["components"]["cohérence"],
        "score_conformite": rich["components"]["conformité"],
        "weights": rich["weights"],
        "explanations": rich["explanations"],
    }


def verify_consistency(df, detection=None, change_log_df=None, changes=None):
    """Vérifie la cohérence entre les statistiques annoncées et les données.

    Recalcule indépendamment chaque indicateur **directement depuis le
    DataFrame final** et le compare aux valeurs du dictionnaire ``detection``
    (produit par :func:`build_detection`). Toute divergence est signalée.

    Contrôles effectués :
    1. Le total des valeurs manquantes est cohérent avec le détail par colonne.
    2. Le détail par colonne correspond au recomptage réel du DataFrame.
    3. Les valeurs « Inconnu » sont cohérentes avec le détail par colonne.
    4. ``valides + invalides + inconnus ==`` total des cellules email.
    5. Les emails « inconnus » sont comptés dans la statistique « Inconnu ».
    6. Les emails invalides ne sont **pas** comptés comme inconnus/manquants.
    7. Le nombre d'emails corrigés dans le journal correspond au compteur.

    Renvoie ``{"ok": bool, "checks": [...], "inconsistencies": [...]}``.
    """
    detection = detection or build_detection(df)
    checks = []
    inconsistencies = []

    def _check(label, ok, detail):
        checks.append({"label": label, "ok": bool(ok), "detail": detail})
        if not ok:
            inconsistencies.append(f"{label} ? {detail}")

    recomputed = {
        col: int(df[col].map(is_missing).sum())
        for col in df.columns
        if int(df[col].map(is_missing).sum())
    }
    announced = detection.get("missing", {})
    total_announced = sum(v["count"] for v in announced.values())
    total_recomputed = sum(recomputed.values())
    _check(
        _("Total missing values"),
        total_announced == total_recomputed,
        _("Reported %(reported)s vs recalculated %(actual)s") % {"reported": total_announced, "actual": total_recomputed},
    )
    announced_cols = {k: v["count"] for k, v in announced.items()}
    _check(
        _("Missing values by column"),
        announced_cols == recomputed,
        _("Reported %(reported)s vs recalculated %(actual)s") % {"reported": announced_cols, "actual": recomputed},
    )

    recomputed_unknown = {
        col: int(df[col].map(is_unknown).sum())
        for col in df.columns
        if int(df[col].map(is_unknown).sum())
    }
    announced_unknown = detection.get("unknown", {})
    _check(
        _("Unknown values by column"),
        announced_unknown == recomputed_unknown,
        _("Reported %(reported)s vs recalculated %(actual)s") % {"reported": announced_unknown, "actual": recomputed_unknown},
    )

    email_cols = [c for c in df.columns if _is_email_column(c)]
    if email_cols:
        em = detection.get("emails", {})
        total_email_cells = len(df) * len(email_cols)
        em_sum = em.get("valid", 0) + em.get("invalid", 0) + em.get("unknown", 0)
        _check(
            _("Emails: valid + invalid + unknown = total"),
            em_sum == total_email_cells,
            _("%(valid)s + %(invalid)s + %(unknown)s = %(actual)s vs %(expected)s expected") % {
                "valid": em.get("valid", 0), "invalid": em.get("invalid", 0),
                "unknown": em.get("unknown", 0), "actual": em_sum, "expected": total_email_cells,
            },
        )
        unknown_in_cols = sum(announced_unknown.get(c, 0) for c in email_cols)
        _check(
            _("Unknown emails included in the unknown-value statistic"),
            unknown_in_cols == em.get("unknown", 0),
            _("%(actual)s unknown value(s) in email column(s) vs %(reported)s reported") % {
                "actual": unknown_in_cols, "reported": em.get("unknown", 0),
            },
        )
        invalid_ok = all(
            (not is_missing(value)) and (not is_unknown(value))
            for _, _, value in em.get("issues", [])
        )
        _check(
            _("Invalid emails are not counted as unknown or missing"),
            invalid_ok,
            _("%(count)s invalid email(s) present (non-empty and not unknown)") % {"count": len(em.get("issues", []))},
        )

    if change_log_df is not None and not change_log_df.empty:
        if "type_correction" in change_log_df.columns:
            log_corrected = int((change_log_df["type_correction"] == "email").sum())
            announced_corrected = (changes or {}).get("emails_corriges", 0)
            _check(
                _("Emails corrected (change log vs counter)"),
                log_corrected == announced_corrected,
                _("%(actual)s correction(s) in the log vs %(reported)s reported") % {
                    "actual": log_corrected, "reported": announced_corrected,
                },
            )

    return {
        "ok": len(inconsistencies) == 0,
        "checks": checks,
        "inconsistencies": inconsistencies,
    }
