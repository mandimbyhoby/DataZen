"""Tableau de bord global : agrégation multi-fichiers des indicateurs qualité.

Ce module ne relit **aucun** fichier de données : il s'appuie sur les
indicateurs figés sur :class:`~core.models.DataFile` lors du nettoyage
(score, dimensions, compteurs de problèmes). L'affichage du tableau de bord
reste donc instantané, quel que soit le nombre de fichiers.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from django.db.models import Avg, Count, Sum
from django.utils import timezone
from django.utils.translation import gettext

from ..models import DataFile

# Libellés des problèmes agrégés, dans l'ordre d'affichage.
PROBLEM_LABELS = (
    ("duplicates", "Doublons exacts", "danger", "🔴"),
    ("potential_duplicates", "Doublons potentiels", "warning", "🟠"),
    ("unknown", "Valeurs « Inconnu »", "secondary", "⚪"),
    ("outliers", "Valeurs aberrantes", "warning", "📈"),
    ("errors", "Erreurs restantes", "danger", "❌"),
    ("missing", "Cellules manquantes", "info", "▫️"),
)


def _score_category(total):
    """Étiquette qualitative d'un score, cohérente avec le dashboard par fichier."""
    if total is None:
        return gettext("non évalué"), "secondary"
    if total >= 90:
        return gettext("excellente qualité"), "success"
    if total >= 75:
        return gettext("bonne qualité"), "success"
    if total >= 50:
        return gettext("qualité moyenne"), "warning"
    return gettext("qualité faible"), "danger"


def _metrics_of(data_file):
    """Instantané d'indicateurs d'un fichier, avec repli sur les colonnes dédiées."""
    metrics = data_file.metrics or {}
    return {
        "duplicates": int(metrics.get("duplicates", 0) or 0),
        "potential_duplicates": int(metrics.get("potential_duplicates", 0) or 0),
        "unknown": int(metrics.get("unknown", 0) or 0),
        "outliers": int(metrics.get("outliers", 0) or 0),
        "errors": int(metrics.get("errors", 0) or 0),
        "missing": int(metrics.get("missing", 0) or 0),
    }


def build_overview(queryset):
    """Construit le tableau de bord global à partir d'un queryset de fichiers.

    ``queryset`` doit déjà être filtré sur les droits de l'utilisateur (voir
    ``core.views._visible_files``). Les fichiers archivés sont exclus par
    défaut afin que les moyennes reflètent l'activité courante.
    """
    active = list(queryset.filter(archived_at__isnull=True))
    cleaned = [f for f in active if f.status == DataFile.Status.CLEANED]

    scores = [f.quality_after for f in cleaned if f.quality_after is not None]
    average = round(sum(scores) / len(scores), 1) if scores else None
    category_label, category_class = _score_category(average)

    # Répartition par tranche de qualité (histogramme du tableau de bord).
    buckets = [
        (90, 101, "success"),
        (75, 90, "info"),
        (50, 75, "warning"),
        (-1, 50, "danger"),
    ]
    distribution = []
    for low, high, css in buckets:
        count = sum(1 for score in scores if low <= score < high)
        distribution.append(
            {
                "label": _score_category((low + high) / 2 if low >= 0 else 25)[0],
                "count": count,
                "css": css,
                "width": round(100 * count / len(scores)) if scores else 0,
            }
        )

    # Agrégation des problèmes restants, tous fichiers confondus.
    totals = defaultdict(int)
    for data_file in cleaned:
        for key, value in _metrics_of(data_file).items():
            totals[key] += value

    problems = []
    for key, label, css, icon in PROBLEM_LABELS:
        problems.append(
            {
                "key": key,
                "label": gettext(label),
                "icon": icon,
                "css": css,
                "value": totals.get(key, 0),
            }
        )
    max_problem = max((p["value"] for p in problems), default=0)
    for problem in problems:
        problem["width"] = (
            round(100 * problem["value"] / max_problem) if max_problem else 0
        )

    # Compétences qualité les plus faibles : moyennes par dimension.
    dimension_totals = defaultdict(list)
    for data_file in cleaned:
        for name, value in (data_file.metrics or {}).get("dimensions", {}).items():
            dimension_totals[name].append(value)
    dimensions = [
        {
            "name": name,
            "score": round(sum(values) / len(values), 1),
            "count": len(values),
            "width": round(sum(values) / len(values)),
        }
        for name, values in dimension_totals.items()
    ]
    dimensions.sort(key=lambda item: item["score"])

    # Activité dans le temps, 12 dernières semaines.
    timeline = timeline_heights(_timeline(cleaned))

    # Classement des fichiers : les scores les plus bas d'abord (à traiter).
    ranked = sorted(
        cleaned,
        key=lambda f: (f.quality_after if f.quality_after is not None else 101),
    )

    return {
        "totals": {
            "files": len(active),
            "cleaned": len(cleaned),
            "pending": sum(1 for f in active if f.status == DataFile.Status.UPLOADED),
            "processing": sum(
                1 for f in active if f.status == DataFile.Status.PROCESSING
            ),
            "errors": sum(1 for f in active if f.status == DataFile.Status.ERROR),
            "archived": queryset.filter(archived_at__isnull=False).count(),
        },
        "average_score": average,
        "category_label": category_label,
        "category_class": category_class,
        "best_score": round(max(scores), 1) if scores else None,
        "worst_score": round(min(scores), 1) if scores else None,
        "rows_total": sum(f.rows_count or 0 for f in cleaned),
        "columns_total": sum(f.columns_count or 0 for f in cleaned),
        "issues_total": sum(totals.get(key, 0) for key, *_ in PROBLEM_LABELS),
        "changes_total": sum(f.changes_count or 0 for f in cleaned),
        "distribution": distribution,
        "problems": problems,
        "dimensions": dimensions,
        "timeline": timeline,
        "best_files": ranked[-5:][::-1],
        "worst_files": ranked[:5],
        "recent_files": sorted(
            cleaned, key=lambda f: f.cleaned_at or f.updated_at, reverse=True
        )[:5],
    }


def _timeline(cleaned, weeks=12):
    """Évolution hebdomadaire : nombre de nettoyages et score moyen."""
    now = timezone.now()
    buckets = []
    for offset in range(weeks - 1, -1, -1):
        end = now - timedelta(days=7 * offset)
        start = end - timedelta(days=7)
        window = [
            f
            for f in cleaned
            if (f.cleaned_at or f.updated_at) and start <= (f.cleaned_at or f.updated_at) < end
        ]
        scores = [f.quality_after for f in window if f.quality_after is not None]
        buckets.append(
            {
                "label": end.strftime("%d/%m"),
                "count": len(window),
                "score": round(sum(scores) / len(scores), 1) if scores else None,
            }
        )
    return buckets


def timeline_heights(timeline):
    """Ajoute à chaque tranche la hauteur relative (%) de sa barre d'activité."""
    peak = max((bucket["count"] for bucket in timeline), default=0)
    for bucket in timeline:
        bucket["height"] = round(100 * bucket["count"] / peak) if peak else 0
    return timeline


def score_sparkline(timeline):
    """Points normalisés (0-100) pour tracer une courbe légère en SVG."""
    points = []
    width = 100
    step = width / max(len(timeline) - 1, 1)
    for index, bucket in enumerate(timeline):
        score = bucket["score"]
        if score is None:
            continue
        points.append(
            {
                "x": round(index * step, 2),
                "y": round(100 - max(0.0, min(100.0, score)), 2),
                "score": score,
                "label": bucket["label"],
            }
        )
    return points


def aggregate_stats(queryset):
    """Statistiques brutes (une requête SQL) pour les en-têtes du tableau de bord."""
    return queryset.aggregate(
        files=Count("id"),
        rows=Sum("rows_count"),
        columns=Sum("columns_count"),
        issues=Sum("issues_count"),
        changes=Sum("changes_count"),
        average=Avg("quality_after"),
    )


def cleaning_delta(data_file):
    """Écart de score avant/après nettoyage d'un fichier (``None`` si inconnu)."""
    if data_file.quality_before is None or data_file.quality_after is None:
        return None
    return round(data_file.quality_after - data_file.quality_before, 1)


def format_delta(data_file):
    """Représentation textuelle de la progression d'un fichier."""
    delta = cleaning_delta(data_file)
    if delta is None:
        return {"value": None, "css": "secondary", "text": gettext("—")}
    if delta > 0:
        return {
            "value": delta,
            "css": "success",
            "text": f"+{delta} " + gettext("points"),
        }
    if delta < 0:
        return {"value": delta, "css": "danger", "text": f"{delta} " + gettext("points")}
    return {"value": 0.0, "css": "secondary", "text": gettext("stable")}
