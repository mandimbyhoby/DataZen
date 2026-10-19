"""Historique des versions d'un jeu de données.

Chaque nettoyage réussi fige une version : copie du fichier nettoyé, journal
des modifications et indicateurs du moment. L'historique permet de consulter
l'évolution, de comparer deux versions entre elles et de restaurer une version
antérieure si un nettoyage s'avère inopportun.

Les opérations sont conservées sous forme de codes ``(code, paramètres)`` et
traduites à l'affichage : l'historique reste lisible dans toutes les langues,
même si le nettoyage a été lancé dans une autre.
"""
import logging
import uuid
from pathlib import Path

import pandas as pd
from django.conf import settings
from django.utils import timezone

from ..models import DatasetVersion, DataFile
from .comparison import build_comparison
from .exporter import export_dataframe
from .reader import read_dataframe

logger = logging.getLogger(__name__)


def next_number(data_file):
    """Numéro de la prochaine version d'un jeu de données (1 s'il n'y en a pas)."""
    last = data_file.versions.order_by("-number").values_list("number", flat=True).first()
    return (last or 0) + 1


def _version_path(data_file, number, suffix):
    """Chemin de stockage d'une pièce de version (fichier nettoyé ou journal)."""
    stamp = timezone.now().strftime("%Y/%m/%d")
    stem = Path(data_file.original_name or "donnees.csv").stem
    token = uuid.uuid4().hex[:6]
    return f"versions/{stamp}/{stem}_v{number}_{token}{suffix}"


def record_version(
    data_file,
    cleaned_df,
    change_log_df=None,
    operations=None,
    created_by=None,
):
    """Fige une version après un nettoyage réussi.

    Renvoie la :class:`~core.models.DatasetVersion` créée, ou ``None`` si
    l'écriture a échoué. Un échec de versionnage ne doit jamais faire échouer
    un nettoyage déjà réussi : l'erreur est journalisée et avalée.
    """
    try:
        number = next_number(data_file)

        abs_dir = Path(settings.MEDIA_ROOT)
        suffix = Path(data_file.original_name or "donnees.csv").suffix.lower()
        if suffix not in {".csv", ".xlsx", ".xls"}:
            suffix = ".csv"
        cleaned_rel = _version_path(data_file, number, suffix)
        cleaned_abs = abs_dir / cleaned_rel
        cleaned_abs.parent.mkdir(parents=True, exist_ok=True)
        export_dataframe(cleaned_df, cleaned_abs)

        change_log_rel = ""
        if change_log_df is not None and not change_log_df.empty:
            change_log_rel = _version_path(data_file, number, ".csv")
            export_dataframe(change_log_df, abs_dir / change_log_rel)

        return DatasetVersion.objects.create(
            data_file=data_file,
            number=number,
            cleaned_file=cleaned_rel,
            change_log_file=change_log_rel or None,
            quality_before=data_file.quality_before,
            quality_after=data_file.quality_after,
            rows_count=data_file.rows_count,
            columns_count=data_file.columns_count,
            changes_count=data_file.changes_count,
            metrics=data_file.metrics or {},
            operations=list(operations or []),
            created_by=created_by if getattr(created_by, "pk", None) else None,
        )
    except Exception:  # noqa: BLE001 — le versionnage reste un confort
        logger.exception("Versionnage impossible pour le fichier %s", data_file.pk)
        return None


def version_dataframe(version):
    """Charge le DataFrame d'une version depuis son fichier nettoyé."""
    return read_dataframe(version.cleaned_file.path)


def compare_versions(before, after):
    """Compare deux versions et renvoie l'écart d'indicateurs.

    Réutilise :func:`comparison.build_comparison` : la comparaison de versions
    et la comparaison avant/après nettoyage partagent donc exactement la même
    logique d'analyse.
    """
    comparison = build_comparison(version_dataframe(before), version_dataframe(after))
    comparison["before_version"] = before
    comparison["after_version"] = after
    return comparison


def restore_version(version):
    """Réapplique une version : le fichier nettoyé du dataset devient le sien.

    Les indicateurs figés sur le dataset sont mis à jour en conséquence afin
    que le tableau de bord reste cohérent avec le contenu restauré.
    """
    data_file = version.data_file
    source = Path(version.cleaned_file.path)
    if not source.exists():
        raise FileNotFoundError(source)

    target_dir = Path(settings.MEDIA_ROOT) / "cleaned"
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(data_file.original_name or "donnees.csv").stem
    suffix = source.suffix or ".csv"
    target_rel = f"cleaned/{stem}_v{version.number}_{uuid.uuid4().hex[:6]}{suffix}"
    target_abs = Path(settings.MEDIA_ROOT) / target_rel

    target_abs.write_bytes(source.read_bytes())

    data_file.cleaned_file.name = target_rel
    if version.change_log_file:
        data_file.change_log_file.name = version.change_log_file.name
    data_file.quality_before = version.quality_before
    data_file.quality_after = version.quality_after
    data_file.rows_count = version.rows_count
    data_file.columns_count = version.columns_count
    data_file.changes_count = version.changes_count
    data_file.metrics = version.metrics or {}
    data_file.status = DataFile.Status.CLEANED
    data_file.cleaned_at = timezone.now()
    data_file.save()
    return data_file
