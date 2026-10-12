"""Comparaison avant / après nettoyage d'un fichier.

Le module relit le fichier d'origine **et** le fichier nettoyé, puis calcule
les écarts utiles : qualité globale, qualité par colonne, complétude, doublons,
erreurs de format, valeurs « Inconnu ». Aucune logique de détection n'est
réécrite : tout passe par :func:`validation.build_detection` et
:func:`validation.compute_quality_score`.
"""

from __future__ import annotations

from django.utils.translation import gettext

from .cleaning import restore_semantic_types
from .reader import read_dataframe
from .validation import build_detection, compute_quality_score

# Statuts possibles d'une colonne entre l'état initial et l'état final.
STATUS_IMPROVED = "improved"
STATUS_REGRESSED = "regressed"
STATUS_STABLE = "stable"
STATUS_ADDED = "added"
STATUS_REMOVED = "removed"


def _column_metrics(df, detection):
    """Indicateurs par colonne, calculés à partir d'une détection donnée."""
    metrics = {}
    for column in df.columns:
        missing = detection.get("missing", {}).get(column, {}).get("count", 0)
        unknown = detection.get("unknown", {}).get(column, 0)
        total = len(df) or 1
        metrics[column] = {
            "missing": int(missing),
            "unknown": int(unknown),
            "issues": 0,
            "completeness": round(100 * (total - missing - unknown) / total, 1),
        }

    for column, info in detection.get("phones", {}).items():
        if column in metrics:
            metrics[column]["issues"] += int(info.get("invalid", 0))
    for column, info in detection.get("dates", {}).items():
        if column in metrics:
            metrics[column]["issues"] += int(info.get("invalid", 0))
    emails = detection.get("emails", {})
    for _index, column, _value in emails.get("issues", []):
        if column in metrics:
            metrics[column]["issues"] += 1
    if "salaries" in detection and detection["salaries"].get("column") in metrics:
        metrics[detection["salaries"]["column"]]["issues"] += int(
            detection["salaries"].get("invalid", 0)
        )
    return metrics


def _status(before, after):
    """Compare deux métriques d'issues et renvoie un statut lisible."""
    if after < before:
        return STATUS_IMPROVED
    if after > before:
        return STATUS_REGRESSED
    return STATUS_STABLE


def _total_errors(detection):
    """Somme des erreurs de format détectées (emails, téléphones, dates, montants)."""
    return (
        int(detection.get("emails", {}).get("invalid", 0))
        + sum(int(v.get("invalid", 0)) for v in detection.get("phones", {}).values())
        + sum(int(v.get("invalid", 0)) for v in detection.get("dates", {}).values())
        + int(detection.get("salaries", {}).get("invalid", 0))
    )


def _totals(df, detection, score):
    """Indicateurs globaux d'un état (avant ou après)."""
    missing = sum(int(v.get("count", 0)) for v in detection.get("missing", {}).values())
    unknown = sum(int(v) for v in detection.get("unknown", {}).values())
    return {
        "rows": len(df),
        "columns": df.shape[1],
        "score": score.get("total") if score else None,
        "components": score.get("components", {}) if score else {},
        "duplicates": int(detection.get("duplicates", 0)),
        "potential_duplicates": len(detection.get("potential_duplicates", [])),
        "missing": missing,
        "unknown": unknown,
        "errors": _total_errors(detection),
        "outliers": len(detection.get("outliers", [])),
    }


def build_comparison(original_df, cleaned_df):
    """Compare deux DataFrame et renvoie un rapport de comparaison complet.

    ``original_df`` est le fichier tel que téléversé, ``cleaned_df`` le résultat
    du nettoyage. Le dictionnaire retourné est directement consommable par le
    template : tableaux *avant / après*, deltas et liste des colonnes modifiées.
    """
    before_detection = build_detection(original_df)
    after_detection = build_detection(cleaned_df)
    before_score = compute_quality_score(original_df, before_detection)
    after_score = compute_quality_score(cleaned_df, after_detection)

    before_totals = _totals(original_df, before_detection, before_score)
    after_totals = _totals(cleaned_df, after_detection, after_score)

    before_columns = _column_metrics(original_df, before_detection)
    after_columns = _column_metrics(cleaned_df, after_detection)

    columns = []
    for name in dict.fromkeys(list(before_columns) + list(after_columns)):
        before = before_columns.get(name)
        after = after_columns.get(name)
        if before is None:
            status = STATUS_ADDED
        elif after is None:
            status = STATUS_REMOVED
        else:
            status = _status(before["issues"], after["issues"])
        columns.append(
            {
                "name": name,
                "before": before,
                "after": after,
                "status": status,
                "status_label": _status_label(status),
                "status_css": _status_css(status),
                "delta_issues": (after["issues"] - before["issues"])
                if before and after
                else 0,
                "delta_completeness": round(
                    (after["completeness"] - before["completeness"]), 1
                )
                if before and after
                else 0,
            }
        )

    # Indicateurs globaux comparés (libellé, avant, après, meilleur sens).
    indicators = [
        _indicator(gettext("Score de qualité"), before_totals["score"], after_totals["score"], "up", "%"),
        _indicator(gettext("Lignes"), before_totals["rows"], after_totals["rows"], "down"),
        _indicator(gettext("Colonnes"), before_totals["columns"], after_totals["columns"], "none"),
        _indicator(gettext("Doublons exacts"), before_totals["duplicates"], after_totals["duplicates"], "down"),
        _indicator(
            gettext("Doublons potentiels"),
            before_totals["potential_duplicates"],
            after_totals["potential_duplicates"],
            "down",
        ),
        _indicator(gettext("Cellules manquantes"), before_totals["missing"], after_totals["missing"], "down"),
        _indicator(gettext("Valeurs « Inconnu »"), before_totals["unknown"], after_totals["unknown"], "down"),
        _indicator(gettext("Erreurs de format"), before_totals["errors"], after_totals["errors"], "down"),
        _indicator(gettext("Valeurs aberrantes"), before_totals["outliers"], after_totals["outliers"], "down"),
    ]

    dimensions = []
    for name, value in after_score.get("components", {}).items():
        previous = before_score.get("components", {}).get(name)
        dimensions.append(
            {
                "name": name,
                "before": previous,
                "after": value,
                "delta": round(value - previous, 1) if previous is not None else None,
            }
        )

    improved = sum(1 for c in columns if c["status"] == STATUS_IMPROVED)
    regressed = sum(1 for c in columns if c["status"] == STATUS_REGRESSED)
    changed_keys = ("rows", "columns", "score", "duplicates", "unknown", "errors", "missing")

    return {
        "before": before_totals,
        "after": after_totals,
        "delta": round(
            (after_totals["score"] or 0) - (before_totals["score"] or 0), 1
        ),
        "indicators": indicators,
        "dimensions": dimensions,
        "columns": columns,
        "improved_columns": improved,
        "regressed_columns": regressed,
        "stable_columns": len(columns) - improved - regressed,
        "has_changes": any(
            before_totals.get(key) != after_totals.get(key) for key in changed_keys
        ),
    }


def _indicator(label, before, after, better, unit=""):
    """Construit une ligne de comparaison avec son sens d'amélioration."""
    delta = None
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        delta = round(after - before, 1)
    return {
        "label": label,
        "before": before,
        "after": after,
        "delta": delta,
        "unit": unit,
        "better": better,
        "css": _delta_css(delta, better),
        "text": _delta_text(delta, unit),
    }


def _delta_css(delta, better):
    """Classe CSS d'un écart, selon le sens attendu."""
    if not delta:
        return "secondary"
    if better == "none":
        return "info"
    improvement = delta > 0 if better == "up" else delta < 0
    return "success" if improvement else "danger"


def _delta_text(delta, unit=""):
    """Texte signé d'un écart, avec son unité."""
    if delta is None:
        return "—"
    if delta == 0:
        return gettext("inchangé")
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta}{unit}"


def _status_label(status):
    """Libellé traduit d'un statut de colonne."""
    return {
        STATUS_IMPROVED: gettext("améliorée"),
        STATUS_REGRESSED: gettext("à vérifier"),
        STATUS_STABLE: gettext("stable"),
        STATUS_ADDED: gettext("ajoutée"),
        STATUS_REMOVED: gettext("supprimée"),
    }.get(status, status)


def _status_css(status):
    """Classe Bootstrap d'un statut de colonne."""
    return {
        STATUS_IMPROVED: "success",
        STATUS_REGRESSED: "warning",
        STATUS_STABLE: "secondary",
        STATUS_ADDED: "info",
        STATUS_REMOVED: "dark",
    }.get(status, "secondary")


def load_comparison(data_file):
    """Charge les deux versions d'un fichier et renvoie leur comparaison.

    Renvoie ``None`` si le fichier d'origine ou le fichier nettoyé est absent
    ou illisible : l'appelant affiche alors un message d'information.
    """
    if not data_file.file or not data_file.cleaned_file:
        return None
    try:
        original_df = read_dataframe(data_file.file.path)
        cleaned_df = restore_semantic_types(read_dataframe(data_file.cleaned_file.path))
    except Exception:  # noqa: BLE001 — un fichier illisible ne doit pas planter la page
        return None
    return build_comparison(original_df, cleaned_df)
