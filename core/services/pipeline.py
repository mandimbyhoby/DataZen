"""Pipeline de nettoyage réutilisable (synchrone et asynchrone).

Ce module centralise la logique de nettoyage d'un :class:`~core.models.DataFile`
afin qu'elle puisse être exécutée :

- soit de façon synchrone (requête HTTP classique) ;
- soit en arrière-plan dans un thread (traitement asynchrone des gros
  fichiers), avec mise à jour de la progression.

Aucune logique de nettoyage n'est dupliquée : le pipeline s'appuie
exclusivement sur :class:`~core.services.cleaning.DataCleaner` et sur les
services existants (validation, rapport, export).
"""
import logging
import uuid
from pathlib import Path


import pandas as pd
from django.conf import settings
from django.utils import timezone

from ..models import DataFile
from .cleaning import DataCleaner, restore_semantic_types
from .comparison import build_comparison
from .exporter import export_dataframe
from .operations import operation_entry, render_operations, render_score_explanations
from .reader import read_dataframe
from .report import build_report
from .validation import (
    build_detection,
    compute_quality_score,
    count_missing_cells,
    detect_regex_violations,
    parse_regex_rules,
    profile_dataframe,
    verify_consistency,
)

logger = logging.getLogger(__name__)

# Colonnes strictes du journal de modification (ne jamais en ajouter).
CHANGE_LOG_COLUMNS = [
    "ligne",
    "colonne",
    "ancienne_valeur",
    "nouvelle_valeur",
    "type_correction",
    "raison",
]


def stats(df):
    """Calcule des statistiques simples sur un DataFrame.

    ``duplicates`` = doublons **exacts** (casse/espaces ignorés, colonnes
    d'identifiant exclues), calculés par :func:`validation.detect_duplicates`
    afin d'être cohérents avec le reste de l'application.
    """
    return {
        "rows": len(df),
        "columns": df.shape[1],
        "duplicates": build_detection(df)["duplicates"],
        "missing": count_missing_cells(df),
    }


def empty_change_log():
    """Journal vide avec le schéma strict du journal."""
    return pd.DataFrame(columns=CHANGE_LOG_COLUMNS)


def read_change_log(data_file):
    """Relit le journal de modification existant (ou un journal vide)."""
    if not data_file.change_log_file:
        return empty_change_log()
    path = Path(settings.MEDIA_ROOT) / data_file.change_log_file.name
    if not path.exists():
        return empty_change_log()
    try:
        return read_dataframe(str(path))
    except Exception:
        return empty_change_log()


def changes_from_log(change_log_df):
    """Reconstruit les compteurs ``changes`` depuis le journal."""
    changes = {}
    if change_log_df is not None and not change_log_df.empty:
        if "type_correction" in change_log_df.columns:
            vc = change_log_df["type_correction"].value_counts()
            changes["emails_corriges"] = int(vc.get("email", 0))
            changes["phones"] = int(vc.get("téléphone", 0))
            changes["dates"] = int(vc.get("date", 0))
            changes["categories"] = int(vc.get("catégorie", 0))
            changes["salaries"] = int(vc.get("numérique", 0))
            changes["duplicates_removed"] = int(vc.get("doublon", 0))
    return changes


def save_cleaned_file(data_file, df):
    """Exporte le DataFrame nettoyé et renvoie son chemin relatif."""
    original = Path(data_file.original_name or "donnees.csv")
    ext = original.suffix.lower() or ".csv"
    if ext not in {".csv", ".xlsx", ".xls"}:
        ext = ".csv"

    filename = f"{original.stem}_nettoye_{uuid.uuid4().hex[:6]}{ext}"
    rel_dir = Path("cleaned")
    abs_dir = Path(settings.MEDIA_ROOT) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    export_dataframe(df, abs_dir / filename)
    return (rel_dir / filename).as_posix()


def save_report_file(data_file, report_text):
    """Écrit le rapport de nettoyage et renvoie son chemin relatif."""
    original = Path(data_file.original_name or "donnees.csv")
    filename = f"{original.stem}_rapport_{uuid.uuid4().hex[:6]}.md"
    rel_dir = Path("reports")
    abs_dir = Path(settings.MEDIA_ROOT) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    (abs_dir / filename).write_text(report_text, encoding="utf-8")
    return (rel_dir / filename).as_posix()


def save_change_log_file(data_file, change_log_df):
    """Écrit le journal des modifications (CSV) et renvoie son chemin relatif."""
    original = Path(data_file.original_name or "donnees.csv")
    filename = f"{original.stem}_change_log_{uuid.uuid4().hex[:6]}.csv"
    rel_dir = Path("logs")
    abs_dir = Path(settings.MEDIA_ROOT) / rel_dir
    abs_dir.mkdir(parents=True, exist_ok=True)

    export_dataframe(change_log_df, abs_dir / filename)
    return (rel_dir / filename).as_posix()


def overwrite_cleaned_file(data_file, df):
    """Réécrit le fichier nettoyé existant (même chemin)."""
    path = Path(settings.MEDIA_ROOT) / data_file.cleaned_file.name
    path.parent.mkdir(parents=True, exist_ok=True)
    export_dataframe(df, path)


def append_change_log(data_file, entries):
    """Ajoute des entrées au journal de modification (même schéma strict)."""
    if not entries:
        return
    existing = read_change_log(data_file)
    new = pd.DataFrame(entries, columns=CHANGE_LOG_COLUMNS)
    combined = pd.concat([existing, new], ignore_index=True)

    if not data_file.change_log_file:
        data_file.change_log_file.name = save_change_log_file(data_file, combined)
    else:
        path = Path(settings.MEDIA_ROOT) / data_file.change_log_file.name
        export_dataframe(combined, path)
    data_file.save(update_fields=["change_log_file", "updated_at"])


def _store_metrics(data_file, cleaned_df, change_log_df, detection, quality_before, quality_after):
    """Fige les indicateurs de qualité sur le fichier (tableau de bord global).

    Ces valeurs évitent de relire les fichiers à chaque affichage du tableau de
    bord multi-datasets : elles sont calculées une fois, au moment du nettoyage.
    """
    total_errors = (
        int(detection.get("emails", {}).get("invalid", 0))
        + sum(int(v.get("invalid", 0)) for v in detection.get("phones", {}).values())
        + sum(int(v.get("invalid", 0)) for v in detection.get("dates", {}).values())
        + int(detection.get("salaries", {}).get("invalid", 0))
    )
    total_changes = 0 if change_log_df is None or change_log_df.empty else int(len(change_log_df))
    data_file.rows_count = len(cleaned_df)
    data_file.columns_count = cleaned_df.shape[1]
    data_file.quality_before = (quality_before or {}).get("total")
    data_file.quality_after = (quality_after or {}).get("total")
    data_file.issues_count = total_errors + len(detection.get("potential_duplicates", []))
    data_file.changes_count = total_changes
    data_file.metrics = {
        # Noms de colonnes figés : ils rendent les fichiers trouvables par
        # leur contenu structurel dans la recherche globale (Ctrl+K).
        "columns": [str(column) for column in cleaned_df.columns],
        "duplicates": int(detection.get("duplicates", 0)),
        "potential_duplicates": len(detection.get("potential_duplicates", [])),
        "unknown": sum(int(v) for v in detection.get("unknown", {}).values()),
        "outliers": len(detection.get("outliers", [])),
        "errors": total_errors,
        "missing": sum(
            int(v.get("count", 0)) for v in detection.get("missing", {}).values()
        ),
        "dimensions": {
            name: round(float(value), 1)
            for name, value in (quality_after or {}).get("components", {}).items()
        },
    }


def run_cleaning(data_file, options, rules=None, progress=None):
    """Exécute le nettoyage complet d'un fichier et persiste les résultats.

    ``options`` est un dictionnaire d'options (issu de
    :class:`~core.forms.CleaningOptionsForm`), ``rules`` une liste de règles
    personnalisées, ``progress`` un callback ``progress(percent, message)``
    optionnel utilisé par le traitement asynchrone.

    Renvoie ``(operations, regex_rules)`` pour la session.
    """
    outcome = _execute_cleaning(data_file, options, rules, progress, persist=True)
    return outcome["operations"], outcome["regex_rules"]


def preview_cleaning(data_file, options, rules=None):
    """Simule le nettoyage **sans rien écrire** et renvoie le résultat complet.

    Sert à l'aperçu avant/après : l'utilisateur voit le score, les colonnes
    touchées et les lignes qui seraient modifiées avant de valider. Le fichier
    d'origine, le fichier nettoyé, le journal, le rapport et les indicateurs du
    dataset restent intacts.

    Renvoie ``None`` si le fichier source est illisible, sinon un dictionnaire
    ``{"comparison", "operations", "changes", "change_log", "email_audit",
    "quality_before", "quality_after", "rows_before", "rows_after"}``.
    """
    try:
        outcome = _execute_cleaning(data_file, options, rules, None, persist=False)
    except Exception:
        logger.exception("Aperçu de nettoyage impossible pour %s", data_file.pk)
        return None

    comparison = build_comparison(outcome["original_df"], outcome["cleaned_df"])
    comparison["change_log"] = _sample_change_log(outcome["change_log_df"])
    comparison["operations"] = outcome["operations"]
    comparison["changes"] = outcome["changes"]
    comparison["email_audit"] = outcome["email_audit"]
    comparison["quality_before"] = outcome["quality_before"]
    comparison["quality_after"] = outcome["quality_after"]
    comparison["rows_before"] = int(len(outcome["original_df"]))
    comparison["rows_after"] = int(len(outcome["cleaned_df"]))
    if not comparison.get("has_changes") and not comparison["change_log"]:
        comparison["has_changes"] = False
    return comparison


PREVIEW_CHANGE_LIMIT = 50


def _sample_change_log(change_log_df, limit=PREVIEW_CHANGE_LIMIT):
    """Extrait un échantillon lisible du journal des corrections.

    Le journal fournit de vrais couples « ancienne valeur → nouvelle valeur »
    avec leur ligne, contrairement à une comparaison positionnelle qui serait
    fausse dès que la déduplication réindexe le tableau.
    """
    if change_log_df is None or change_log_df.empty:
        return {"rows": [], "total": 0, "truncated": False}

    total = int(len(change_log_df))
    sample = change_log_df.head(limit)
    rows = [
        {
            "line": _as_text(row.get("ligne")),
            "column": _as_text(row.get("colonne")),
            "before": _as_text(row.get("ancienne_valeur")),
            "after": _as_text(row.get("nouvelle_valeur")),
            "kind": _as_text(row.get("type_correction")),
            "reason": _as_text(row.get("raison")),
        }
        for row in sample.to_dict("records")
    ]
    return {"rows": rows, "total": total, "truncated": total > limit}


def _as_text(value):
    """Rend une cellule de journal affichable (les NaN deviennent vides)."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _execute_cleaning(data_file, options, rules, progress, persist):
    """Cœur du pipeline, partagé par le nettoyage réel et par l'aperçu.

    ``persist=True`` écrit le fichier nettoyé, le journal, le rapport et les
    indicateurs sur le :class:`~core.models.DataFile`. ``persist=False`` renvoie
    le résultat juste avant ces écritures : l'aperçu et le nettoyage réel
    traversent donc exactement le même code, dans le même ordre.
    """
    def report_progress(percent, message=""):
        if progress:
            progress(percent, message)

    report_progress(5, "Lecture du fichier…")
    df = read_dataframe(data_file.file.path)

    report_progress(15, "Analyse des problèmes…")
    issues = build_detection(df)
    quality_before = compute_quality_score(df, issues)
    before = stats(df)

    operations = []
    cleaner = DataCleaner(df)

    if options.get("remove_duplicates"):
        ignore_case = options.get("dedupe_ignore_case", False)
        subset = options.get("dedupe_column") or None
        cleaner.remove_duplicates(subset=subset, ignore_case=ignore_case)
        removed = cleaner.changes.get("duplicates_removed", 0)
        if subset:
            operations.append(
                operation_entry("remove_duplicates_column", column=subset, count=removed)
            )
        else:
            operations.append(operation_entry("remove_duplicates_exact", count=removed))
    if options.get("normalize_case"):
        cleaner.normalize_text()
        operations.append(operation_entry("normalize_case"))
        cleaner.normalize_categories()
        operations.append(
            operation_entry("normalize_categories", count=cleaner.changes.get("categories", 0))
        )
        cleaner.normalize_codes()
        operations.append(
            operation_entry("normalize_codes", count=cleaner.changes.get("codes", 0))
        )
        cleaner.normalize_booleans()
        operations.append(
            operation_entry("normalize_booleans", count=cleaner.changes.get("booleans", 0))
        )
    if options.get("normalize_emails"):
        cleaner.normalize_emails()
        operations.append(
            operation_entry(
                "normalize_emails",
                corrected=cleaner.changes.get("emails_corriges", 0),
                invalid=cleaner.changes.get("emails_invalides", 0),
            )
        )
    if options.get("normalize_phones"):
        cleaner.normalize_phones()
        operations.append(
            operation_entry("normalize_phones", count=cleaner.changes.get("phones", 0))
        )
    if options.get("normalize_dates"):
        cleaner.normalize_dates()
        operations.append(
            operation_entry("normalize_dates", count=cleaner.changes.get("dates", 0))
        )
    if options.get("normalize_salaries"):
        cleaner.normalize_salaries()
        operations.append(
            operation_entry("normalize_salaries", count=cleaner.changes.get("salaries", 0))
        )
    if options.get("trim_whitespace"):
        cleaner.trim_whitespace()
        operations.append(operation_entry("trim_whitespace"))

    cleaner.normalize_unknown()
    operations.append(
        operation_entry("normalize_unknown", count=cleaner.changes.get("unknown", 0))
    )
    cleaner.normalize_integers()
    operations.append(
        operation_entry("normalize_integers", count=cleaner.changes.get("integers", 0))
    )
    if options.get("anonymize"):
        cleaner.anonymize()
        operations.append(
            operation_entry("anonymize", count=cleaner.changes.get("anonymized", 0))
        )
    cleaner.renumber_identifiers()
    operations.append(operation_entry("renumber_identifiers"))
    if options.get("fill_missing"):
        value = options.get("fill_missing_value", "")
        cleaner.fill_missing(value)
        operations.append(operation_entry("fill_missing", value=value))

    # Règles de nettoyage personnalisées (réutilisables).
    operations.extend(cleaner.apply_rules(rules))

    report_progress(60, "Validation du résultat…")
    cleaned_df = cleaner.result
    after = stats(cleaned_df)

    validation = build_detection(cleaned_df)
    quality_after = compute_quality_score(cleaned_df, validation)

    regex_rules = parse_regex_rules(options.get("regex_rules", ""))
    regex_violations = detect_regex_violations(cleaned_df, regex_rules)

    change_log_df = cleaner.change_log_df

    if not persist:
        # Aperçu : on s'arrête juste avant la première écriture disque ou base.
        return {
            "original_df": df,
            "cleaned_df": cleaned_df,
            "operations": operations,
            "regex_rules": regex_rules,
            "changes": cleaner.changes,
            "change_log_df": change_log_df,
            "email_audit": cleaner.email_audit,
            "quality_before": quality_before,
            "quality_after": quality_after,
            "before": before,
            "after": after,
        }

    consistency = verify_consistency(
        cleaned_df,
        detection=validation,
        change_log_df=change_log_df,
        changes=cleaner.changes,
    )

    report_progress(75, "Enregistrement du fichier nettoyé…")
    rel_path = save_cleaned_file(data_file, cleaned_df)
    data_file.cleaned_file.name = rel_path
    data_file.status = DataFile.Status.CLEANED
    data_file.cleaned_at = timezone.now()
    _store_metrics(
        data_file, cleaned_df, change_log_df, validation, quality_before, quality_after
    )
    data_file.save()

    if not change_log_df.empty:
        change_log_rel = save_change_log_file(data_file, change_log_df)
        data_file.change_log_file.name = change_log_rel

    report_progress(90, "Génération du rapport…")
    report_text = build_report(
        data_file.original_name,
        operations,
        before,
        after,
        detected=issues,
        validation=validation,
        changes=cleaner.changes,
        quality_before=quality_before,
        quality_after=quality_after,
        change_log=change_log_df,
        email_audit=cleaner.email_audit,
        consistency=consistency,
        profile=profile_dataframe(cleaned_df),
    )
    report_rel = save_report_file(data_file, report_text)
    data_file.report_file.name = report_rel
    data_file.save(update_fields=["report_file", "change_log_file", "updated_at"])

    # Historique : chaque nettoyage réussi fige une version restaurable.
    # L'import est local pour éviter une dépendance circulaire au chargement.
    from .versions import record_version

    record_version(
        data_file,
        cleaned_df,
        change_log_df=change_log_df,
        operations=operations,
        created_by=data_file.owner,
    )

    report_progress(100, "Terminé")
    return {
        "original_df": df,
        "cleaned_df": cleaned_df,
        "operations": operations,
        "regex_rules": regex_rules,
        "changes": cleaner.changes,
        "change_log_df": change_log_df,
        "email_audit": cleaner.email_audit,
        "quality_before": quality_before,
        "quality_after": quality_after,
        "before": before,
        "after": after,
    }


def build_cleaned_context(data_file, operations=None, regex_rules=None, theme="light"):
    """Reconstruit tout le contexte « après nettoyage » depuis le fichier nettoyé.

    Réutilise uniquement les fonctions existantes : aucun calcul dupliqué.
    """
    from .charts import chart_catalog
    from .dashboard import build_dashboard
    from .review import build_review_groups

    cleaned_df = restore_semantic_types(read_dataframe(data_file.cleaned_file.path))
    change_log_df = read_change_log(data_file)

    validation = build_detection(cleaned_df)
    quality_after = compute_quality_score(cleaned_df, validation)
    # Les explications sont mémorisées sous forme de codes : on les traduit ici,
    # à l'affichage, pour qu'elles suivent la langue active de l'interface.
    quality_after["explanations"] = render_score_explanations(
        quality_after.get("explanations")
    )

    # Rétro-remplissage des indicateurs figés pour les fichiers nettoyés avant
    # l'introduction du tableau de bord global (une seule écriture, puis le
    # marqueur `quality_after` évite tout recalcul).
    if data_file.quality_after is None:
        _store_metrics(
            data_file,
            cleaned_df,
            change_log_df,
            validation,
            None,
            quality_after,
        )
        data_file.quality_before = None
        data_file.save(
            update_fields=[
                "quality_before",
                "quality_after",
                "rows_count",
                "columns_count",
                "issues_count",
                "changes_count",
                "metrics",
                "updated_at",
            ]
        )
    consistency = verify_consistency(
        cleaned_df,
        detection=validation,
        change_log_df=change_log_df,
        changes=changes_from_log(change_log_df),
    )
    operations = render_operations(operations)
    regex_rules = regex_rules or []
    regex_violations = detect_regex_violations(cleaned_df, regex_rules)
    dashboard = build_dashboard(
        cleaned_df,
        detection=validation,
        score=quality_after,
        change_log_df=change_log_df,
        operations=operations,
    )
    review_groups = build_review_groups(cleaned_df)

    return {
        "cleaned": True,
        "cleaned_stats": stats(cleaned_df),
        "cleaned_columns": list(cleaned_df.columns),
        "cleaned_preview_rows": _rows(cleaned_df),
        "report": data_file.report_file,
        "operations": operations,
        "validation": validation,
        "quality_after": quality_after,
        "change_log": data_file.change_log_file,
        "consistency": consistency,
        "dashboard": dashboard,
        "charts": chart_catalog(cleaned_df, dashboard),
        "review_groups": review_groups,
        "regex_rules": regex_rules,
        "regex_violations": regex_violations,
    }


def _rows(df):
    """Convertit toutes les lignes d'un DataFrame en liste de listes."""
    from .reader import dataframe_to_rows

    return dataframe_to_rows(df, limit=None)
