"""Rapport PDF de qualité des données (ReportLab).

Le PDF est produit à la volée depuis le contexte déjà calculé pour la page
d'analyse : aucun fichier de données n'est relu deux fois. Les graphiques
matplotlib « full HD » sont embarqués dans le document comme images PNG.

Le module est volontairement autonome : il n'importe ni vues ni modèles, et
ne touche pas au système de fichiers.
"""

from __future__ import annotations

import io

from django.utils import timezone
from django.utils.translation import gettext as _

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Charte graphique DataZen — en hexadécimal textuel pour le balisage
# <font color> des paragraphes ReportLab.
BRAND = "#4f46e5"
BRAND_SOFT = "#eef2ff"
INK = "#1f2937"
MUTED = "#6b7280"
SUCCESS = "#10b981"
WARNING = "#f59e0b"
DANGER = "#ef4444"

_BRAND = colors.HexColor(BRAND)
_BRAND_SOFT = colors.HexColor(BRAND_SOFT)
_LINE = colors.HexColor("#e5e7eb")

# Graphiques embarqués dans le rapport, dans cet ordre.
FEATURED_CHARTS = ("score", "problems", "missing", "correlation")

_PAGE_WIDTH = A4[0] - 40 * mm


def _styles():
    """Feuille de styles du rapport."""
    sheet = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "DzTitle",
            parent=sheet["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=26,
            textColor=_BRAND,
            spaceAfter=2,
        ),
        "subtitle": ParagraphStyle(
            "DzSubtitle",
            parent=sheet["Normal"],
            fontSize=10.5,
            leading=15,
            textColor=colors.HexColor(MUTED),
            alignment=TA_CENTER,
            spaceAfter=14,
        ),
        "h2": ParagraphStyle(
            "DzH2",
            parent=sheet["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.HexColor(INK),
            spaceBefore=12,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "DzBody",
            parent=sheet["Normal"],
            fontSize=9.5,
            leading=14,
            textColor=colors.HexColor(INK),
        ),
        "cell": ParagraphStyle(
            "DzCell",
            parent=sheet["Normal"],
            fontSize=9,
            leading=12.5,
            textColor=colors.HexColor(INK),
        ),
        "small": ParagraphStyle(
            "DzSmall",
            parent=sheet["Normal"],
            fontSize=8,
            leading=11,
            textColor=colors.HexColor(MUTED),
        ),
    }


def _as_float(value):
    """Conversion tolérante d'une valeur en flottant (``None`` si impossible)."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _score_color(value):
    """Couleur textuelle d'un score sur 100."""
    if value is None:
        return MUTED
    if value >= 75:
        return SUCCESS
    if value >= 50:
        return WARNING
    return DANGER


def _score_label(value):
    """Appréciation qualitative d'un score, alignée sur l'interface."""
    if value is None:
        return _("non évalué")
    if value >= 90:
        return _("excellente qualité")
    if value >= 75:
        return _("bonne qualité")
    if value >= 50:
        return _("qualité moyenne")
    return _("qualité faible")


def _table(rows, styles, header=True):
    """Tableau homogène, en-tête soulignée à la couleur de la marque."""
    data = [
        [
            Paragraph(str(cell), styles["body"] if index == 0 else styles["cell"])
            for cell in row
        ]
        for index, row in enumerate(rows)
    ]
    table = Table(data, hAlign="LEFT")
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, _LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]
    if header:
        commands += [
            ("BACKGROUND", (0, 0), (-1, 0), _BRAND_SOFT),
            ("TEXTCOLOR", (0, 0), (-1, 0), _BRAND),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, _BRAND),
        ]
    table.setStyle(TableStyle(commands))
    return table


def _score_block(quality, styles):
    """Bandeau de synthèse : score final et appréciation."""
    total = _as_float((quality or {}).get("total")) if isinstance(quality, dict) else None
    value = f"{total:.1f} / 100" if total is not None else "—"
    paragraph = Paragraph(
        f"<font size='20' color='{_score_color(total)}'><b>{value}</b></font>"
        f"<br/><font size='9' color='{MUTED}'>{_score_label(total)}</font>",
        styles["body"],
    )
    table = Table([[paragraph]], colWidths=[_PAGE_WIDTH], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), _BRAND_SOFT),
                ("BOX", (0, 0), (-1, -1), 0.5, _BRAND),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
            ]
        )
    )
    return table


def _summary_rows(data_file, quality):
    """Lignes du tableau de synthèse (page de titre)."""
    before = _as_float(data_file.quality_before)
    after = _as_float(data_file.quality_after)
    if after is None and isinstance(quality, dict):
        after = _as_float(quality.get("total"))
    progression = (
        f"{after - before:+.1f} " + _("points")
        if before is not None and after is not None
        else "—"
    )
    return [
        (_("Indicateur"), _("Valeur")),
        (_("Lignes"), f"{data_file.rows_count or 0}"),
        (_("Colonnes"), data_file.columns_count or 0),
        (_("Score avant nettoyage"), f"{before:.1f}" if before is not None else "—"),
        (_("Score après nettoyage"), f"{after:.1f}" if after is not None else "—"),
        (_("Progression"), progression),
        (_("Problèmes restants"), data_file.issues_count or 0),
        (_("Corrections appliquées"), data_file.changes_count or 0),
    ]


def _dimension_rows(quality):
    """Lignes du tableau des dimensions pondérées du score."""
    rows = [(_("Dimension"), _("Score"), _("Poids"))]
    if not isinstance(quality, dict):
        return rows + [(_("Aucune donnée"), "—", "—")]
    weights = quality.get("weights", {})
    for name, value in quality.get("components", {}).items():
        score = _as_float(value)
        rows.append(
            (
                name,
                f"{score:.1f} %" if score is not None else "—",
                f"{weights.get(name, '—')} %",
            )
        )
    if len(rows) == 1:
        rows.append((_("Aucune donnée"), "—", "—"))
    return rows


def _problem_rows(dashboard):
    """Lignes du tableau des problèmes détectés."""
    rows = [(_("Problème"), _("Volume"))]
    for problem in (dashboard or {}).get("problems") or []:
        rows.append((problem.get("label", "—"), problem.get("value", 0)))
    if len(rows) == 1:
        rows.append((_("Aucun problème détecté"), 0))
    return rows


def _correction_rows(dashboard, operations):
    """Lignes du tableau des corrections appliquées."""
    rows = [(_("Type de correction"), _("Détail"))]
    for operation in operations or []:
        rows.append((operation, ""))
    total = (dashboard or {}).get("change_log_total")
    if total:
        rows.append((_("Lignes du journal des modifications"), total))
    if len(rows) == 1:
        rows.append((_("Aucune correction"), 0))
    return rows


def _quality_rows(dashboard):
    """Lignes du tableau « qualité par colonne » (plus incomplètes d'abord)."""
    rows = [(_("Colonne"), _("Type"), _("Complétude"), _("Statut"))]
    columns = (dashboard or {}).get("columns_quality") or []
    for column in sorted(columns, key=lambda c: c.get("completude", 100))[:20]:
        completeness = _as_float(column.get("completude"))
        rows.append(
            (
                column.get("colonne", "—"),
                column.get("type", "—"),
                f"{completeness:.1f} %" if completeness is not None else "—",
                column.get("statut", "—"),
            )
        )
    if len(rows) == 1:
        rows.append((_("Aucune colonne"), "—", "—", "—"))
    return rows


def build_pdf(
    data_file,
    dashboard=None,
    quality=None,
    validation=None,
    charts=None,
    operations=None,
    theme="light",
):
    """Construit le rapport PDF et renvoie son contenu binaire (``bytes``).

    ``charts`` est la liste produite par ``charts.build_charts`` : les entrées
    dont le slug figure dans :data:`FEATURED_CHARTS` sont embarquées, dans
    l'ordre de ce tuple. ``theme`` et ``validation`` sont acceptés pour rester
    interchangeables avec les autres constructeurs de rendu.
    """
    buffer = io.BytesIO()
    styles = _styles()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"DataZen — {data_file.original_name}",
        author="DataZen",
        subject=_("Rapport de qualité des données"),
    )

    story = []
    generated = timezone.localtime().strftime("%d/%m/%Y %H:%M")

    # --- Page de titre ---------------------------------------------------
    story.append(Paragraph(_("Rapport de qualité des données"), styles["title"]))
    story.append(
        Paragraph(
            f"{data_file.original_name} — {_('généré le')} {generated}",
            styles["subtitle"],
        )
    )
    story.append(_score_block(quality, styles))
    story.append(Spacer(1, 30))

    story.append(Paragraph(_("Synthèse"), styles["h2"]))
    story.append(_table(_summary_rows(data_file, quality), styles))

    if operations:
        story.append(Paragraph(_("Opérations de nettoyage"), styles["h2"]))
        story.append(
            _table(
                [(_("Opération"),)] + [(operation,) for operation in operations[:24]],
                styles,
            )
        )

    # --- Indicateurs -----------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph(_("Dimensions de qualité"), styles["h2"]))
    story.append(_table(_dimension_rows(quality), styles))

    story.append(Paragraph(_("Problèmes détectés"), styles["h2"]))
    story.append(_table(_problem_rows(dashboard), styles))

    story.append(Paragraph(_("Corrections appliquées"), styles["h2"]))
    story.append(_table(_correction_rows(dashboard, operations), styles))

    # --- Graphiques embarqués -------------------------------------------
    by_slug = {
        chart.get("slug"): chart for chart in (charts or []) if chart.get("png")
    }
    featured = [by_slug[slug] for slug in FEATURED_CHARTS if slug in by_slug]
    if featured:
        story.append(PageBreak())
        story.append(Paragraph(_("Graphiques"), styles["h2"]))
        for chart in featured:
            try:
                image = Image(io.BytesIO(chart["png"]))
            except Exception:  # noqa: BLE001 — une image illisible est ignorée
                continue
            ratio = image.imageHeight / float(image.imageWidth or 1)
            image.drawWidth = _PAGE_WIDTH
            image.drawHeight = _PAGE_WIDTH * ratio
            story.append(
                KeepTogether(
                    [
                        Paragraph(
                            str(chart.get("title") or chart.get("slug", "")),
                            styles["body"],
                        ),
                        Spacer(1, 4),
                        image,
                        Spacer(1, 10),
                    ]
                )
            )

    # --- Qualité par colonne --------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph(_("Qualité par colonne"), styles["h2"]))
    story.append(_table(_quality_rows(dashboard), styles))

    story.append(Spacer(1, 14))
    story.append(
        Paragraph(
            _(
                "Rapport généré automatiquement par DataZen. Les scores sont "
                "calculés selon cinq dimensions pondérées : complétude, validité, "
                "unicité, cohérence et conformité."
            ),
            styles["small"],
        )
    )

    document.build(story)
    return buffer.getvalue()
