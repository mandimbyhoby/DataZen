"""Dashboard Data Quality (DataZen).

Construit un tableau de bord lisible à partir du DataFrame nettoyé et des
résultats déjà produits par le moteur de nettoyage. Aucun calcul n'est
dupliqué : ce module **réutilise** les fonctions existantes
(:func:`validation.build_detection`, :func:`validation.compute_quality_score`,
:func:`validation.is_missing`, :func:`cleaning.is_unknown`, etc.).

Il est conçu pour être robuste : il fonctionne avec n'importe quel dataset,
quel que soit le nombre/nom de colonnes, et ne plante jamais si une colonne
(email, téléphone, date, prix…) est absente.
"""

from collections import Counter

import pandas as pd

from .cleaning import (
    DEFAULT_CATEGORY_MAP,
    _is_category_column,
    _is_date_column,
    _is_email_column,
    _is_identifier,
    _is_phone_column,
    _is_salary_column,
    is_numeric_value,
    is_unknown,
)
from django.utils.translation import gettext as _

from .validation import (
    build_detection,
    compute_quality_score,
    is_missing,
    profile_dataframe,
    structural_anomaly_label,
)


def _score_category(total):
    """Étiquette qualitative du score (explicative, sans modifier le calcul)."""
    if total >= 90:
        return _("excellente qualité"), "success"
    if total >= 75:
        return _("bonne qualité"), "success"
    if total >= 50:
        return _("qualité moyenne"), "warning"
    return _("qualité faible"), "danger"


def _column_type(col, df):
    """Type d'une colonne, détecté via les helpers + inférence du dtype.

    L'inférence numérique ignore « Inconnu » et les valeurs manquantes : une
    colonne comme ``quantite`` (``1.0, 2.0, "Inconnu"``) est donc bien
    détectée comme « numérique ».
    """
    if _is_identifier(col):
        return "identifiant"
    if _is_email_column(col):
        return "email"
    if _is_phone_column(col):
        return "téléphone"
    if _is_date_column(col):
        return "date"
    if _is_salary_column(col):
        return "numérique"
    if _is_category_column(col):
        return "catégorie"

    try:
        if pd.api.types.is_numeric_dtype(df[col]):
            return "numérique"
    except (TypeError, ValueError):
        pass

    # Inférence : si toutes les valeurs renseignées (hors « Inconnu » et
    # NaN) sont numériques, la colonne est numérique (ex. quantite après
    # relecture CSV en chaînes).
    remaining = [
        v
        for v in df[col]
        if (not pd.isna(v)) and (not is_unknown(v))
    ]
    if remaining and all(is_numeric_value(v) for v in remaining):
        return "numérique"

    return "texte"


def _translated_column_type(column_type):
    labels = {
        "identifiant": _("identifiant"),
        "email": _("email"),
        "téléphone": _("téléphone"),
        "date": _("date"),
        "numérique": _("numérique"),
        "catégorie": _("catégorie"),
        "texte": _("texte"),
    }
    return labels.get(column_type, column_type)


def _translated_dimension_name(name):
    labels = {
        "complétude": _("complétude"),
        "validité": _("validité"),
        "unicité": _("unicité"),
        "cohérence": _("cohérence"),
        "conformité": _("conformité"),
    }
    return labels.get(name, name)


def _column_invalid(col, df, detection):
    """Nombre de valeurs invalides pour une colonne donnée.

    Réutilise les règles exactes du module de validation afin de ne jamais
    produire de statistique contradictoire.
    """
    if _is_email_column(col):
        return sum(1 for _, c, _ in detection["emails"]["issues"] if c == col)
    if _is_phone_column(col):
        return detection["phones"].get(col, {}).get("invalid", 0)
    if _is_date_column(col):
        return detection["dates"].get(col, {}).get("invalid", 0)
    if _is_salary_column(col) or _column_type(col, df) == "numérique":
        # Valide = valeur numérique (ou convertible). « Inconnu » / NaN exclus.
        return sum(
            1
            for v in df[col]
            if (not pd.isna(v)) and (not is_unknown(v)) and (not is_numeric_value(v))
        )
    if _is_category_column(col):
        return sum(
            1
            for v in df[col]
            if (not pd.isna(v))
            and (not is_unknown(v))
            and str(v).strip().lower() in DEFAULT_CATEGORY_MAP
            and DEFAULT_CATEGORY_MAP[str(v).strip().lower()] != str(v).strip()
        )
    return 0


def _column_quality(df, detection):
    """Statistiques par colonne : type, complétude, validité, inconnus, statut."""
    rows = []
    total = len(df)
    for col in df.columns:
        series = df[col]
        unknown = int(series.map(is_unknown).sum())
        missing = int(series.map(is_missing).sum())
        filled = total - unknown - missing
        invalid = _column_invalid(col, df, detection)

        completeness = round(100 * filled / total, 1) if total else 100.0
        validity = round(100 * (1 - invalid / filled), 1) if filled else 100.0

        if invalid > 0:
            status = "❌"
        elif unknown > 0 or missing > 0:
            status = "⚠️"
        else:
            status = "✅"

        rows.append(
            {
                "colonne": str(col),
                "type": _translated_column_type(_column_type(col, df)),
                "completude": completeness,
                "validite": validity,
                "inconnu": unknown,
                "manquant": missing,
                "invalide": invalid,
                "statut": status,
            }
        )
    return rows


def _column_stats(df):
    """Statistiques descriptives par colonne (min, max, moyenne, uniques…).

    Les valeurs « Inconnu » et manquantes sont exclues des calculs : elles ne
    sont pas des observations réelles. Les colonnes numériques reçoivent
    min/max/moyenne ; les autres reçoivent la valeur la plus fréquente.
    """
    rows = []
    for col in df.columns:
        series = df[col]
        values = [
            v for v in series if (not pd.isna(v)) and (not is_unknown(v))
        ]
        n_filled = len(values)
        ctype = _column_type(col, df)

        stat = {
            "colonne": str(col),
            "type": ctype,
            "renseigne": n_filled,
            "n_unique": len({str(v) for v in values}),
            "min": "—",
            "max": "—",
            "moyenne": "—",
            "top": "—",
        }

        if ctype == "numérique":
            nums = []
            for v in values:
                try:
                    nums.append(float(str(v).replace(",", ".")))
                except (TypeError, ValueError):
                    continue
            if nums:
                stat["min"] = f"{min(nums):g}"
                stat["max"] = f"{max(nums):g}"
                stat["moyenne"] = f"{sum(nums) / len(nums):.2f}"
        elif values:
            top, freq = Counter(str(v) for v in values).most_common(1)[0]
            stat["top"] = f"{top} ({freq})"

        rows.append(stat)
    return rows


def _row_values(df, idx):
    """Convertit une ligne du DataFrame en liste de chaînes, alignée sur les colonnes."""
    out = []
    for col in df.columns:
        value = df.iloc[idx][col]
        if value is None or (isinstance(value, float) and pd.isna(value)):
            out.append("")
        else:
            out.append(str(value))
    return out


def build_dashboard(df, detection=None, score=None, change_log_df=None, operations=None):
    """Construit le dictionnaire complet du dashboard Data Quality.

    Paramètres
    ----------
    - ``df`` : DataFrame nettoyé (final).
    - ``detection`` : résultat de ``build_detection(df)`` (sinon recalculé).
    - ``score`` : résultat de ``compute_quality_score(df)`` (sinon recalculé).
    - ``change_log_df`` : DataFrame du journal de modification.
    - ``operations`` : liste de chaînes décrivant les opérations appliquées.

    Retourne un dictionnaire prêt à être consommé par le template.
    """
    detection = detection or build_detection(df)
    score = score or compute_quality_score(df, detection)
    n = len(df)

    # --- Score global + catégorie qualitative ---
    total = score["total"]
    category_label, category_class = _score_category(total)

    # --- Indicateurs principaux ---
    unknown_by_col = detection["unknown"]
    unknown_total = sum(unknown_by_col.values())

    exact_duplicates = detection["duplicates"]
    potential_duplicates = detection["potential_duplicates"]
    potential_count = len(potential_duplicates)

    email_invalid = detection["emails"]["invalid"]
    phone_invalid = sum(v["invalid"] for v in detection["phones"].values())
    date_invalid = sum(v["invalid"] for v in detection["dates"].values())
    salary_invalid = detection["salaries"]["invalid"]
    errors_total = email_invalid + phone_invalid + date_invalid + salary_invalid

    outliers = detection.get("outliers", [])
    outlier_count = len(outliers)

    structural_anomalies = detection.get("structural", [])
    structural_count = len(structural_anomalies)

    indicators = [
        {"label": _("Lignes après nettoyage"), "value": n, "icon": "📄", "class": "primary"},
        {"label": _("Doublons exacts"), "value": exact_duplicates, "icon": "🔴", "class": "danger" if exact_duplicates else "success"},
        {"label": _("Doublons potentiels"), "value": potential_count, "icon": "🟠", "class": "warning" if potential_count else "success"},
        {"label": _("Valeurs « Inconnu »"), "value": unknown_total, "icon": "⚪", "class": "secondary" if unknown_total else "success"},
        {"label": _("Valeurs aberrantes"), "value": outlier_count, "icon": "📈", "class": "warning" if outlier_count else "success"},
        {"label": _("Anomalies structurelles"), "value": structural_count, "icon": "🧩", "class": "warning" if structural_count else "success"},
        {"label": _("Erreurs restantes"), "value": errors_total, "icon": "❌", "class": "danger" if errors_total else "success"},
    ]

    # --- Dimensions de qualité (réutilise le score existant) ---
    dimensions = [
        {**dimension, "name": _translated_dimension_name(dimension["name"])}
        for dimension in score.get("breakdown", [])
    ]

    # --- Valeurs « Inconnu » par colonne ---
    unknown_by_column = [
        {"colonne": col, "count": count}
        for col, count in sorted(unknown_by_col.items(), key=lambda x: -x[1])
    ]
    # Largeur relative des barres (bornée, pour ne jamais déborder).
    max_unknown = max((count for count in unknown_by_col.values()), default=0)
    for item in unknown_by_column:
        item["width"] = round(100 * item["count"] / max_unknown) if max_unknown else 0

    # --- Analyse des doublons (potentiels : jamais supprimés) ---
    duplicate_groups = []
    for i, p in enumerate(potential_duplicates):
        rows = [_row_values(df, r) for r in p["rows"]]
        duplicate_groups.append(
            {
                "n": i + 1,
                "lignes": [r + 1 for r in p["rows"]],
                "nb_lignes": len(p["rows"]),
                "score": p.get("score", 0.0),
                "raison": p.get("reason", ""),
                "colonnes_differentes": ", ".join(p.get("similar_columns", [])) or "—",
                "columns": [str(c) for c in df.columns],
                "rows": rows,
            }
        )

    # --- Qualité par colonne ---
    columns_quality = _column_quality(df, detection)

    # --- Statistiques descriptives par colonne ---
    column_stats = _column_stats(df)

    # --- Profilage avancé (statistiques enrichies) ---
    profile = profile_dataframe(df)

    # --- Journal des modifications ---
    # Les lignes sont converties en listes alignées sur les colonnes, afin
    # d'être rendues simplement par le template (sans filtre de dict).
    change_log_rows = []
    change_log_columns = []
    if change_log_df is not None and not change_log_df.empty:
        change_log_columns = [str(c) for c in change_log_df.columns]
        for _index, row in change_log_df.head(50).iterrows():
            change_log_rows.append(
                ["" if pd.isna(v) else str(v) for v in row.tolist()]
            )
    change_log_total = len(change_log_df) if change_log_df is not None else 0

    # --- Points nécessitant une vérification humaine ---
    to_verify = []
    if potential_count:
        to_verify.append(
            {
                "type": "warn",
                "text": _("%(count)s doublon(s) potentiel(s) nécessitent une vérification.")
                % {"count": potential_count},
            }
        )
    if unknown_total:
        to_verify.append(
            {
                "type": "warn",
                "text": _("%(count)s valeur(s) sont actuellement « Inconnu ».")
                % {"count": unknown_total},
            }
        )
    invalid_items = []
    for category in ("emails", "dates", "phones", "salaries"):
        details = detection.get(category, {})
        if category == "emails":
            invalid_items.extend(
                (row, column, value, _("Email invalide"))
                for row, column, value in details.get("issues", [])
            )
        elif category == "salaries":
            invalid_items.extend(
                (row, column, value, _("Valeur numérique invalide"))
                for row, column, value in details.get("issues", [])
            )
        else:
            for column, info in details.items():
                invalid_items.extend(
                    (
                        issue_row,
                        issue_column,
                        issue_value,
                        _("Date invalide")
                        if category == "dates"
                        else _("Téléphone non standard"),
                    )
                    for issue_row, issue_column, issue_value in info.get("issues", [])
                )
    invalid_items.sort(key=lambda issue: (issue[0], str(issue[1])))

    if errors_total:
        to_verify.append(
            {
                "type": "warn",
                "text": _("%(count)s erreur(s) n'ont pas pu être corrigée(s) automatiquement.") % {"count": errors_total},
                "issues": [
                    {
                        "row": row + 1,
                        "column": column,
                        "value": value,
                        "reason": reason,
                    }
                    for row, column, value, reason in invalid_items
                ],
            }
        )
    if outlier_count:
        to_verify.append(
            {
                "type": "warn",
                "text": _("%(count)s valeur(s) aberrante(s) détectée(s) sur les colonnes numériques.")
                % {"count": outlier_count},
            }
        )
    if structural_count:
        to_verify.append(
            {
                "type": "warn",
                "text": _("%(count)s anomalie(s) structurelle(s) détectée(s) sur les colonnes.")
                % {"count": structural_count},
                "items": [
                    {
                        "column": anomaly["colonne"],
                        "type": anomaly["type"],
                        "severity": anomaly["severite"],
                        "detail": anomaly["detail"],
                    }
                    for anomaly in structural_anomalies
                ],
            }
        )

    # --- Anomalies structurelles (libellés traduits, prêts pour le template) ---
    anomaly_classes = {
        "haute": "danger",
        "moyenne": "warning",
        "faible": "secondary",
    }
    structural_rows = [
        {
            "colonne": anomaly["colonne"],
            "type_code": anomaly["type"],
            "type": str(structural_anomaly_label(anomaly["type"])),
            "severite_code": anomaly["severite"],
            "severite": _("haute") if anomaly["severite"] == "haute" else (
                _("moyenne") if anomaly["severite"] == "moyenne" else _("faible")
            ),
            "classe": anomaly_classes.get(anomaly["severite"], "secondary"),
            "detail": anomaly["detail"],
        }
        for anomaly in structural_anomalies
    ]

    # --- Répartition des problèmes (pour mini-graphique) ---
    problems = [
        {"label": _("Doublons potentiels"), "value": potential_count, "class": "warning"},
        {"label": _("Valeurs « Inconnu »"), "value": unknown_total, "class": "secondary"},
        {"label": _("Valeurs aberrantes"), "value": outlier_count, "class": "info"},
        {"label": _("Anomalies structurelles"), "value": structural_count, "class": "warning"},
        {"label": _("Erreurs restantes"), "value": errors_total, "class": "danger"},
    ]
    max_problem = max((p["value"] for p in problems), default=0)
    for p in problems:
        p["width"] = round(100 * p["value"] / max_problem) if max_problem else 0

    return {
        "score": total,
        "category_label": category_label,
        "category_class": category_class,
        "indicators": indicators,
        "dimensions": dimensions,
        "unknown_by_column": unknown_by_column,
        "unknown_total": unknown_total,
        "duplicate_groups": duplicate_groups,
        "exact_duplicates": exact_duplicates,
        "potential_count": potential_count,
        "columns_quality": columns_quality,
        "column_stats": column_stats,
        "profile": profile,
        "outliers": outliers,
        "outlier_count": outlier_count,
        "structural_anomalies": structural_rows,
        "structural_count": structural_count,
        "operations": operations or [],
        "change_log_rows": change_log_rows,
        "change_log_columns": change_log_columns,
        "change_log_total": change_log_total,
        "to_verify": to_verify,
        "problems": problems,
    }
