"""Graphiques statistiques (matplotlib + seaborn) pour DataZen.

Ce module produit des images PNG générées côté serveur à partir du DataFrame
nettoyé et des résultats **déjà calculés** par :mod:`core.services.dashboard`
et :mod:`core.services.validation`. Aucun calcul de qualité n'est dupliqué :
les graphiques ne font que représenter des données existantes.

Le backend ``Agg`` de matplotlib est forcé : indispensable en environnement
serveur, où aucun affichage graphique n'est disponible.

Chaque fonction est défensive : si une colonne est absente, vide ou non
numérique, le graphique correspondant est simplement ignoré (``None``) au lieu
de faire échouer la page.
"""

import base64
import io
import math
from collections import Counter

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402 — après matplotlib.use("Agg")
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from django.utils import translation  # noqa: E402
from django.utils.formats import number_format  # noqa: E402
from django.utils.translation import gettext as _  # noqa: E402
from django.utils.translation import gettext_lazy as _lazy  # noqa: E402

from . import dashboard as dashboard_service  # noqa: E402
from .cleaning import is_unknown  # noqa: E402
from .validation import (  # noqa: E402
    profile_dataframe,
    structural_anomaly_label,
)

# Palette alignée sur la charte graphique DataZen (dégradé de marque).
BRAND = [
    "#4f46e5",
    "#7c3aed",
    "#06b6d4",
    "#f59e0b",
    "#ef4444",
    "#10b981",
    "#8b5cf6",
    "#ec4899",
]

# Couleurs sémantiques (score, complétude).
COLOR_OK = "#10b981"
COLOR_WARN = "#f59e0b"
COLOR_BAD = "#ef4444"

# Rendu « full HD » : les figures sont dimensionnées en pouces puis
# multipliées par la résolution. 9,6 in × 200 ppp ≈ 1920 px de large, ce qui
# reste net une fois l'image réduite dans une carte ou un rapport.
DPI = 200
FULL_WIDTH = 9.6
HALF_WIDTH = 4.8

_THEMES = {
    "light": {
        "bg": "#ffffff",
        "text": "#1f2937",
        "muted": "#6b7280",
        "grid": "#e5e7eb",
    },
    "dark": {
        "bg": "#111827",
        "text": "#e5e7eb",
        "muted": "#9ca3af",
        "grid": "#374151",
    },
    # Thème « auto » : fond transparent et texte gris neutre, lisible aussi
    # bien sur fond clair que sombre. Utilisé pour les graphiques affichés
    # dans l'interface (le thème y est géré côté navigateur).
    "auto": {
        "bg": "none",
        "text": "#6b7280",
        "muted": "#9ca3af",
        "grid": "#9ca3af",
    },
}

# Catalogue des graphiques : (slug, titre, description).
# Les libellés sont *paresseux* : ils sont résolus au rendu (donc dans la
# langue active de la requête), pas à l'import du module.
CHART_SPECS = [
    ("score", _lazy("Score global"), _lazy("Jauge du score de qualité global (sur 100).")),
    (
        "dimensions",
        _lazy("Dimensions de qualité"),
        _lazy("Contribution des cinq dimensions pondérées du score."),
    ),
    (
        "missing",
        _lazy("Complétude par colonne"),
        _lazy("Taux de remplissage de chaque colonne (les plus incomplètes d'abord)."),
    ),
    (
        "problems",
        _lazy("Répartition des problèmes"),
        _lazy("Volume des anomalies restantes par catégorie."),
    ),
    (
        "histograms",
        _lazy("Distributions numériques"),
        _lazy("Histogrammes des colonnes numériques détectées."),
    ),
    (
        "boxplots",
        _lazy("Boîtes à moustaches"),
        _lazy("Dispersion et valeurs extrêmes des colonnes numériques."),
    ),
    (
        "correlation",
        _lazy("Matrice de corrélation"),
        _lazy("Corrélations de Pearson entre les colonnes numériques."),
    ),
    (
        "categories",
        _lazy("Top des catégories"),
        _lazy("Valeurs les plus fréquentes des colonnes catégorielles."),
    ),
    (
        "outliers",
        _lazy("Valeurs aberrantes"),
        _lazy("Nombre de valeurs aberrantes (méthode IQR) par colonne."),
    ),
    (
        "moments",
        _lazy("Forme des distributions"),
        _lazy("Asymétrie et aplatissement (moments centrés) des colonnes numériques."),
    ),
    (
        "structural",
        _lazy("Anomalies structurelles"),
        _lazy("Colonnes vides, constantes, quasi constantes ou à type hétérogène."),
    ),
]


# --------------------------------------------------------------------------
# Utilitaires internes
# --------------------------------------------------------------------------
# Polices de repli : matplotlib n'embarque pas les glyphes CJK, thaï ou
# devanagari. On construit une chaîne de repli à partir des polices
# réellement installées sur la machine (``font.family`` accepte une liste).
_FONT_CANDIDATES = (
    "DejaVu Sans",
    "Segoe UI",
    "Arial",
    "Tahoma",
    "Microsoft YaHei",
    "Malgun Gothic",
    "Yu Gothic",
    "MS Gothic",
    "Leelawadee UI",
    "Nirmala UI",
)

# Langues s'écrivant de droite à gauche (façonnage + réordonnancement requis).
_RTL_LANGUAGES = {"ar", "he", "fa", "ur"}


def _available_fonts():
    """Polices de repli réellement installées, dans l'ordre de préférence."""
    from matplotlib import font_manager

    installed = {font.name for font in font_manager.fontManager.ttflist}
    fonts = [name for name in _FONT_CANDIDATES if name in installed]
    return fonts or ["DejaVu Sans"]


def _is_rtl():
    """Indique si la langue active s'écrit de droite à gauche."""
    language = translation.get_language() or ""
    return language.split("-")[0].split("_")[0] in _RTL_LANGUAGES


def _label(text):
    """Prépare un libellé pour matplotlib (façonnage arabe si nécessaire).

    matplotlib ne gère ni la liaison des lettres arabes ni le sens de lecture
    droite-à-gauche : sans ce traitement, les libellés arabes apparaissent
    sous forme de lettres isolées et inversées.
    """
    text = str(text)
    if not _is_rtl():
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
    except ImportError:  # pragma: no cover - dépend de l'environnement
        return text
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:  # noqa: BLE001 — un libellé ne doit jamais casser un graphique
        return text


def _num(value, decimals=None):
    """Nombre localisé : séparateur décimal de la langue active.

    ``decimals=None`` reproduit le formatage ``%g`` (zéros superflus retirés),
    ``decimals=n`` fixe le nombre de décimales.
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{number:g}" if decimals is None else f"{number:.{decimals}f}"
    separator = number_format(1.5, decimal_pos=1, use_l10n=True)[1]
    return text.replace(".", separator)


def _to_float(value):
    """Convertit une valeur formatée (``"1,23"``) en flottant, sinon ``None``."""
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _style(theme):
    """Applique le thème (clair/sombre) et la palette DataZen à matplotlib."""
    t = _THEMES.get(theme, _THEMES["light"])
    plt.rcParams.update(
        {
            "figure.facecolor": t["bg"],
            "axes.facecolor": t["bg"],
            "savefig.facecolor": t["bg"],
            "text.color": t["text"],
            "axes.labelcolor": t["text"],
            "axes.edgecolor": t["grid"],
            "xtick.color": t["muted"],
            "ytick.color": t["muted"],
            "grid.color": t["grid"],
            "font.family": _available_fonts(),
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.titleweight": "bold",
            "axes.titlepad": 14,
            "axes.labelsize": 11,
            "axes.labelpad": 8,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
            "figure.dpi": DPI,
            "savefig.dpi": DPI,
            # Habillage épuré : cadres superflus retirés, grilles tracées
            # explicitement par chaque graphique (donc sous les données).
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": False,
            "grid.linewidth": 0.8,
            "grid.alpha": 0.5,
            "lines.linewidth": 2.0,
        }
    )
    sns.set_palette(BRAND)
    return t


def _figure_to_png(fig):
    """Sérialise une figure en PNG haute résolution puis libère la mémoire."""
    buffer = io.BytesIO()
    fig.savefig(
        buffer,
        format="png",
        dpi=DPI,
        bbox_inches="tight",
        pad_inches=0.25,
        facecolor=fig.get_facecolor(),
    )
    plt.close(fig)
    return buffer.getvalue()


def _data_uri(png):
    """Encode un PNG en URI ``data:`` (pour un rapport HTML autonome)."""
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def _is_blank(value):
    """Indique si une valeur est absente (``None``, NaN ou chaîne vide)."""
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return not str(value).strip()


def _numeric_values(series):
    """Extrait les valeurs numériques exploitables d'une colonne.

    « Inconnu », valeurs manquantes, booléens et textes non convertibles sont
    ignorés. Les formats français (``1 299,90 €``) sont acceptés.
    """
    out = []
    for value in series:
        if _is_blank(value) or is_unknown(value) or isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            out.append(float(value))
            continue
        text = str(value).strip().replace(" ", "").replace("\u00a0", "")
        if "," in text and "." in text:
            text = text.replace(".", "").replace(",", ".")
        elif "," in text:
            text = text.replace(",", ".")
        for symbol in ("€", "$", "%"):
            text = text.replace(symbol, "")
        try:
            out.append(float(text))
        except ValueError:
            continue
    return out


def numeric_columns(df, limit=6):
    """Colonnes numériques exploitables (au moins deux valeurs), plafonnées."""
    cols = []
    for col in df.columns:
        try:
            if dashboard_service._column_type(col, df) != "numérique":
                continue
        except Exception:  # noqa: BLE001 — colonne exotique : on l'ignore
            continue
        if len(_numeric_values(df[col])) >= 2:
            cols.append(col)
    return cols[:limit]


def categorical_columns(df, limit=6):
    """Colonnes catégorielles pertinentes (2 à 25 modalités distinctes)."""
    cols = []
    for col in df.columns:
        try:
            ctype = dashboard_service._column_type(col, df)
        except Exception:  # noqa: BLE001
            continue
        if ctype not in ("catégorie", "texte", "email", "téléphone", "date"):
            continue
        values = [
            str(v) for v in df[col] if not _is_blank(v) and not is_unknown(v)
        ]
        if len(values) < 2:
            continue
        if 1 < len(set(values)) <= 25:
            cols.append(col)
    return cols[:limit]


def _score_color(total):
    """Couleur sémantique associée à un score de qualité."""
    if total >= 90:
        return COLOR_OK
    if total >= 75:
        return "#06b6d4"
    if total >= 50:
        return COLOR_WARN
    return COLOR_BAD


def _completeness_color(value):
    """Couleur sémantique associée à un taux de complétude."""
    if value >= 95:
        return COLOR_OK
    if value >= 80:
        return COLOR_WARN
    return COLOR_BAD


def _grid(n_items, ncols):
    """Nombre de lignes nécessaires pour une grille de ``n_items`` graphiques."""
    return max(1, math.ceil(n_items / ncols))


def _soft_grid(ax, axis="y"):
    """Grille discrète tracée sous les données, sans graduations saillantes."""
    ax.set_axisbelow(True)
    ax.grid(axis=axis, linewidth=0.8, alpha=0.5)
    ax.tick_params(length=0)


def _hbar_track(ax, labels, values, colors, track_color, total, height=0.62):
    """Barres horizontales posées sur une piste claire (style « jauge »).

    Renvoie les barres de données (la piste n'est qu'un repère visuel).
    """
    ax.barh(
        labels,
        [total] * len(labels),
        color=track_color,
        alpha=0.3,
        height=height,
        zorder=1,
    )
    return ax.barh(labels, values, color=colors, height=height, zorder=2)


def _value_label(ax, x, y, text, color, ha="left", va="center", size=10):
    """Étiquette de valeur, tracée au-dessus des barres."""
    ax.text(x, y, text, ha=ha, va=va, fontsize=size, color=color, zorder=4)


# --------------------------------------------------------------------------
# Graphiques
# --------------------------------------------------------------------------
def chart_score(score, theme="light"):
    """Jauge en anneau du score global de qualité."""
    t = _style(theme)
    total = float(score or 0)
    total = max(0.0, min(100.0, total))
    color = _score_color(total)

    fig, ax = plt.subplots(figsize=(5.6, 5.6))
    ax.pie(
        [total, max(0.0, 100.0 - total)],
        colors=[color, t["grid"]],
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.30, "edgecolor": t["bg"], "linewidth": 2},
    )
    ax.text(
        0,
        0.12,
        _num(total),
        ha="center",
        va="center",
        fontsize=40,
        fontweight="bold",
        color=color,
    )
    ax.text(
        0, -0.22, "/ 100", ha="center", va="center", fontsize=13, color=t["muted"]
    )
    ax.text(
        0,
        -0.46,
        _label(_("Score global de qualité")),
        ha="center",
        va="center",
        fontsize=12,
        color=t["text"],
    )
    ax.set_aspect("equal")
    return _figure_to_png(fig)


def chart_dimensions(dimensions, theme="light"):
    """Barres horizontales des dimensions pondérées du score."""
    if not dimensions:
        return None
    t = _style(theme)
    labels = [_label(str(d["name"]).capitalize()) for d in dimensions][::-1]
    values = [float(d["value"]) for d in dimensions][::-1]
    weights = [d.get("weight", 0) for d in dimensions][::-1]

    fig, ax = plt.subplots(figsize=(FULL_WIDTH, 0.62 * len(labels) + 2.4))
    bars = _hbar_track(
        ax, labels, values, BRAND[: len(labels)], t["grid"], 100, height=0.58
    )
    for bar, value, weight in zip(bars, values, weights):
        _value_label(
            ax,
            min(value + 2.5, 101),
            bar.get_y() + bar.get_height() / 2,
            _label(
                _("%(score)s / 100  (%(weight)s %(percent)s)")
                % {"score": _num(value), "weight": _num(weight), "percent": "%"}
            ),
            t["muted"],
        )
    ax.set_xlim(0, 122)
    ax.set_xlabel(_("Score de la dimension"))
    ax.set_title(_("Dimensions de qualité"), color=t["text"], loc="left")
    _soft_grid(ax, axis="x")
    fig.tight_layout()
    return _figure_to_png(fig)


def chart_missing(columns_quality, theme="light"):
    """Complétude par colonne (les colonnes les plus incomplètes en premier)."""
    if not columns_quality:
        return None
    t = _style(theme)
    rows = sorted(columns_quality, key=lambda r: r.get("completude", 0))[:15]
    labels = [_label(str(r["colonne"])[:26]) for r in rows][::-1]
    values = [float(r.get("completude", 0)) for r in rows][::-1]
    colors = [_completeness_color(v) for v in values]

    fig, ax = plt.subplots(figsize=(FULL_WIDTH, 0.46 * len(labels) + 2.4))
    bars = _hbar_track(ax, labels, values, colors, t["grid"], 100, height=0.6)
    for bar, value in zip(bars, values):
        _value_label(
            ax,
            min(value + 2, 101),
            bar.get_y() + bar.get_height() / 2,
            _("%(value)s %(percent)s") % {"value": _num(value), "percent": "%"},
            t["muted"],
        )
    ax.set_xlim(0, 114)
    ax.set_xlabel(_("Taux de complétude (%)"))
    ax.set_title(_("Complétude par colonne"), color=t["text"], loc="left")
    _soft_grid(ax, axis="x")
    fig.tight_layout()
    return _figure_to_png(fig)


def chart_problems(problems, theme="light"):
    """Volume des anomalies restantes par catégorie."""
    items = [p for p in (problems or []) if p.get("value")]
    if not items:
        return None
    t = _style(theme)
    labels = [_label(str(p["label"])) for p in items]
    values = [float(p["value"]) for p in items]

    fig, ax = plt.subplots(figsize=(FULL_WIDTH, 4.6))
    bars = ax.bar(
        labels,
        values,
        color=BRAND[: len(labels)],
        width=0.58,
        zorder=2,
    )
    for bar, value in zip(bars, values):
        _value_label(
            ax,
            bar.get_x() + bar.get_width() / 2,
            value,
            _num(value),
            t["text"],
            ha="center",
            va="bottom",
        )
    ax.set_ylabel(_("Nombre d'occurrences"))
    ax.set_title(_("Répartition des problèmes restants"), color=t["text"], loc="left")
    ax.margins(y=0.14)
    _soft_grid(ax, axis="y")
    plt.setp(ax.get_xticklabels(), rotation=18, ha="right")
    fig.tight_layout()
    return _figure_to_png(fig)


def chart_histograms(df, theme="light"):
    """Grille d'histogrammes pour les colonnes numériques."""
    cols = numeric_columns(df)
    if not cols:
        return None
    t = _style(theme)
    ncols = 2 if len(cols) > 1 else 1
    nrows = _grid(len(cols), ncols)

    fig, axes = plt.subplots(
        nrows, ncols, figsize=(HALF_WIDTH * ncols, 3.1 * nrows), squeeze=False
    )
    for i, col in enumerate(cols):
        ax = axes[i // ncols][i % ncols]
        values = _numeric_values(df[col])
        bins = max(5, min(20, len(values) // 3 or 5))
        color = BRAND[i % len(BRAND)]
        sns.histplot(
            values,
            bins=bins,
            ax=ax,
            color=color,
            edgecolor=t["bg"],
            linewidth=0.6,
            alpha=0.9,
            zorder=2,
        )
        # Courbe de densité : donne du relief à la distribution.
        if len(values) >= 5 and len(set(values)) > 1:
            sns.kdeplot(
                values,
                ax=ax,
                color=color,
                linewidth=2.0,
                zorder=3,
                warn_singular=False,
            )
        ax.set_title(_label(str(col)), color=t["text"], loc="left")
        ax.set_xlabel("")
        ax.set_ylabel(_("Effectif"))
        _soft_grid(ax, axis="y")

    for j in range(len(cols), nrows * ncols):
        axes[j // ncols][j % ncols].axis("off")

    fig.suptitle(
        _("Distributions des colonnes numériques"),
        color=t["text"],
        fontsize=15,
        fontweight="bold",
        x=0.02,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return _figure_to_png(fig)


def chart_boxplots(df, theme="light"):
    """Boîtes à moustaches (seaborn) des colonnes numériques."""
    cols = numeric_columns(df)
    if not cols:
        return None
    t = _style(theme)

    records = []
    for col in cols:
        for value in _numeric_values(df[col]):
            records.append({"colonne": _label(str(col)), "valeur": value})
    if not records:
        return None
    long_df = pd.DataFrame(records)

    fig, ax = plt.subplots(figsize=(max(FULL_WIDTH, 1.3 * len(cols) + 3.4), 5.0))
    sns.boxplot(
        data=long_df,
        x="colonne",
        y="valeur",
        hue="colonne",
        legend=False,
        palette=BRAND[: len(cols)],
        width=0.5,
        linewidth=1.4,
        fliersize=5,
        flierprops={"marker": "o", "alpha": 0.6},
        ax=ax,
    )
    ax.set_title(
        _("Boîtes à moustaches des colonnes numériques"), color=t["text"], loc="left"
    )
    ax.set_xlabel("")
    ax.set_ylabel(_("Valeur"))
    _soft_grid(ax, axis="y")
    plt.setp(ax.get_xticklabels(), rotation=18, ha="right")
    fig.tight_layout()
    return _figure_to_png(fig)


def chart_correlation(df, theme="light"):
    """Matrice de corrélation de Pearson entre colonnes numériques."""
    cols = numeric_columns(df, limit=10)
    if len(cols) < 2:
        return None
    t = _style(theme)

    data = pd.DataFrame({str(c): pd.Series(_numeric_values(df[c])) for c in cols})
    if len(data) < 3:
        return None
    corr = data.corr(numeric_only=True)
    if corr.empty or corr.isna().all().all():
        return None

    # Matrice carrée : on part de 80 % de la largeur pleine (≈ 1536 px) pour
    # rester net sans produire une figure démesurément haute.
    size = max(FULL_WIDTH * 0.8, 0.86 * len(cols) + 3.0)
    fig, ax = plt.subplots(figsize=(size, size * 0.86))
    sns.heatmap(
        corr,
        annot=len(cols) <= 8,
        fmt=".2f",
        cmap="coolwarm",
        center=0,
        vmin=-1,
        vmax=1,
        square=True,
        linewidths=1.0,
        linecolor=t["bg"],
        cbar_kws={"shrink": 0.75, "label": _("Coefficient de Pearson")},
        annot_kws={"size": 9, "weight": "bold"},
        ax=ax,
    )
    ax.set_title(_("Matrice de corrélation (Pearson)"), color=t["text"], loc="left")
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    plt.setp(ax.get_yticklabels(), rotation=0)
    fig.tight_layout()
    return _figure_to_png(fig)


def chart_categories(df, theme="light"):
    """Top 8 des modalités les plus fréquentes par colonne catégorielle."""
    cols = categorical_columns(df)
    if not cols:
        return None
    t = _style(theme)
    ncols = 2 if len(cols) > 1 else 1
    nrows = _grid(len(cols), ncols)

    fig, axes = plt.subplots(
        nrows, ncols, figsize=(HALF_WIDTH * ncols, 3.0 * nrows), squeeze=False
    )
    for i, col in enumerate(cols):
        ax = axes[i // ncols][i % ncols]
        values = [
            str(v) for v in df[col] if not _is_blank(v) and not is_unknown(v)
        ]
        counts = Counter(values).most_common(8)
        if not counts:
            ax.axis("off")
            continue
        labels = [_label(c[0][:24]) for c in counts][::-1]
        sizes = [c[1] for c in counts][::-1]
        color = BRAND[i % len(BRAND)]
        bars = ax.barh(labels, sizes, color=color, height=0.6, zorder=2)
        for bar, size in zip(bars, sizes):
            _value_label(
                ax,
                size,
                bar.get_y() + bar.get_height() / 2,
                f" {_num(size)}",
                t["muted"],
                size=9,
            )
        ax.set_title(_label(str(col)), color=t["text"], loc="left")
        ax.set_xlabel(_("Effectif"))
        ax.margins(x=0.12)
        _soft_grid(ax, axis="x")

    for j in range(len(cols), nrows * ncols):
        axes[j // ncols][j % ncols].axis("off")

    fig.suptitle(
        _("Valeurs les plus fréquentes"),
        color=t["text"],
        fontsize=15,
        fontweight="bold",
        x=0.02,
        ha="left",
    )
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    return _figure_to_png(fig)


def chart_outliers(df, outliers, theme="light"):
    """Nombre de valeurs aberrantes (IQR) par colonne."""
    if not outliers:
        return None
    t = _style(theme)
    counts = Counter(str(o.get("colonne", "—")) for o in outliers)
    items = counts.most_common(12)
    labels = [_label(c[0][:26]) for c in items][::-1]
    values = [c[1] for c in items][::-1]

    fig, ax = plt.subplots(figsize=(FULL_WIDTH, 0.46 * len(labels) + 2.4))
    bars = ax.barh(labels, values, color=COLOR_WARN, height=0.6, zorder=2)
    for bar, value in zip(bars, values):
        _value_label(
            ax,
            value,
            bar.get_y() + bar.get_height() / 2,
            f" {_num(value)}",
            t["muted"],
        )
    ax.set_xlabel(_("Nombre de valeurs aberrantes"))
    ax.set_title(
        _("Valeurs aberrantes par colonne (méthode IQR)"), color=t["text"], loc="left"
    )
    ax.margins(x=0.12)
    _soft_grid(ax, axis="x")
    fig.tight_layout()
    return _figure_to_png(fig)


def _moments_items(df):
    """Asymétrie et aplatissement par colonne numérique (moments centrés).

    Réutilise :func:`validation.profile_dataframe` : aucune statistique n'est
    recalculée ici, le graphique ne fait que représenter des valeurs déjà
    produites par le profilage.
    """
    items = []
    for row in profile_dataframe(df):
        if row.get("type") != "numérique":
            continue
        skewness = _to_float(row.get("asymetrie"))
        kurtosis = _to_float(row.get("aplatissement"))
        if skewness is None or kurtosis is None:
            continue
        items.append(
            {
                "label": str(row["colonne"]),
                "skewness": skewness,
                "kurtosis": kurtosis,
            }
        )
    return items


def chart_moments(df, theme="light"):
    """Forme des distributions : asymétrie et aplatissement par colonne."""
    items = _moments_items(df)
    if not items:
        return None
    t = _style(theme)

    labels = [_label(item["label"][:26]) for item in items][::-1]
    skewness = [item["skewness"] for item in items][::-1]
    kurtosis = [item["kurtosis"] for item in items][::-1]
    positions = range(len(labels))
    height = 0.36

    fig, ax = plt.subplots(figsize=(FULL_WIDTH, 0.62 * len(labels) + 2.6))
    ax.barh(
        [p + height / 2 for p in positions],
        skewness,
        height=height,
        color=BRAND[0],
        label=_("Asymétrie"),
        zorder=2,
    )
    ax.barh(
        [p - height / 2 for p in positions],
        kurtosis,
        height=height,
        color=BRAND[2],
        label=_("Aplatissement"),
        zorder=2,
    )
    ax.axvline(0, color=t["muted"], linewidth=1.0, zorder=1)
    ax.set_yticks(list(positions))
    ax.set_yticklabels(labels)
    ax.set_xlabel(_("Valeur du moment centré"))
    ax.set_title(
        _("Forme des distributions (asymétrie et aplatissement)"),
        color=t["text"],
        loc="left",
    )
    legend = ax.legend(loc="lower right", frameon=False)
    for text in legend.get_texts():
        text.set_color(t["text"])
    ax.margins(x=0.14)
    _soft_grid(ax, axis="x")
    fig.tight_layout()
    return _figure_to_png(fig)


def chart_structural(df, anomalies, theme="light"):
    """Anomalies structurelles détectées, regroupées par type."""
    if not anomalies:
        return None
    t = _style(theme)
    counts = Counter(str(a.get("type", "—")) for a in anomalies)
    items = counts.most_common()
    labels = [_label(structural_anomaly_label(code)[:30]) for code, _n in items][::-1]
    values = [n for _code, n in items][::-1]

    fig, ax = plt.subplots(figsize=(FULL_WIDTH, 0.5 * len(labels) + 2.4))
    bars = ax.barh(labels, values, color=COLOR_WARN, height=0.6, zorder=2)
    for bar, value in zip(bars, values):
        _value_label(
            ax,
            value,
            bar.get_y() + bar.get_height() / 2,
            f" {_num(value)}",
            t["muted"],
        )
    ax.set_xlabel(_("Nombre de colonnes concernées"))
    ax.set_title(_("Anomalies structurelles par type"), color=t["text"], loc="left")
    ax.margins(x=0.12)
    _soft_grid(ax, axis="x")
    fig.tight_layout()
    return _figure_to_png(fig)


# --------------------------------------------------------------------------
# Données JSON (rendu interactif React + Chart.js)
# --------------------------------------------------------------------------
# Les PNG restent la référence (rapport HTML autonome, repli sans JavaScript).
# Ce payload alimente la version interactive : mêmes données, mêmes libellés
# traduits, mais dessinés par le navigateur — donc nets à n'importe quelle
# résolution et adaptés automatiquement au thème clair/sombre.
#
# Le façonnage droite-à-gauche n'est **pas** appliqué ici : le navigateur gère
# nativement le bidi, contrairement à matplotlib.

# Couleurs associées aux classes Bootstrap produites par le dashboard.
_CLASS_COLORS = {
    "primary": BRAND[0],
    "secondary": "#94a3b8",
    "success": COLOR_OK,
    "info": "#06b6d4",
    "warning": COLOR_WARN,
    "danger": COLOR_BAD,
}


def _json_number(value):
    """Nombre sérialisable en JSON (``None`` pour NaN et l'infini)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _separators():
    """Séparateurs décimal et de milliers de la langue active."""
    sample = number_format(1234.5, decimal_pos=1, use_l10n=True, force_grouping=True)
    decimal = number_format(1.5, decimal_pos=1, use_l10n=True)[1]
    integer = sample.split(decimal)[0]
    # « 1 234 » → «  » (espace fine insécable) ; « 1,234 » → « , ».
    thousand = integer[1:-3] if len(integer) > 4 else ""
    return {"decimal": decimal, "thousand": thousand}


def _histogram(values, bins):
    """Histogramme (bords + effectifs) calculé sans dépendance externe."""
    if not values:
        return [], []
    low, high = min(values), max(values)
    if low == high:
        return [low - 0.5, high + 0.5], [len(values)]
    width = (high - low) / bins
    edges = [low + index * width for index in range(bins + 1)]
    counts = [0] * bins
    for value in values:
        index = int((value - low) / width)
        counts[min(index, bins - 1)] += 1
    return edges, counts


def _density(values, edges, points=48, sample=400):
    """Courbe de densité (noyau gaussien) échantillonnée sur les bords.

    Donne du relief à la distribution, comme la courbe KDE des PNG. Le nombre
    de valeurs utilisées est plafonné : le coût est quadratique.
    """
    if len(values) < 5 or len(set(values)) < 2 or len(edges) < 2:
        return []
    if len(values) > sample:
        step = len(values) / sample
        values = [values[int(index * step)] for index in range(sample)]

    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    std = variance ** 0.5
    if std <= 0:
        return []
    # Règle de Silverman pour la largeur de bande.
    bandwidth = 1.06 * std * len(values) ** (-0.2)
    if bandwidth <= 0:
        return []

    low, high = edges[0], edges[-1]
    step = (high - low) / (points - 1)
    normalizer = len(values) * bandwidth * math.sqrt(2 * math.pi)
    curve = []
    for index in range(points):
        x = low + index * step
        total = 0.0
        for value in values:
            z = (x - value) / bandwidth
            total += math.exp(-0.5 * z * z)
        curve.append({"x": x, "y": total / normalizer})
    return curve


def _box_stats(values):
    """Statistiques d'une boîte à moustaches (méthode IQR) pour une colonne."""
    if len(values) < 2:
        return None
    ordered = sorted(values)
    n = len(ordered)

    def quantile(position):
        """Quantile par interpolation linéaire (méthode des rangs)."""
        rank = position * (n - 1)
        low = int(math.floor(rank))
        high = int(math.ceil(rank))
        if low == high:
            return ordered[low]
        return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)

    q1 = quantile(0.25)
    median = quantile(0.5)
    q3 = quantile(0.75)
    iqr = q3 - q1
    low_fence = q1 - 1.5 * iqr
    high_fence = q3 + 1.5 * iqr
    inside = [value for value in ordered if low_fence <= value <= high_fence]
    if not inside:
        return None
    return {
        "min": inside[0],
        "q1": q1,
        "median": median,
        "q3": q3,
        "max": inside[-1],
        "outliers": [value for value in ordered if value < low_fence or value > high_fence][:40],
    }


def _correlation_payload(df):
    """Matrice de corrélation de Pearson, prête pour un rendu en grille."""
    cols = numeric_columns(df, limit=10)
    if len(cols) < 2:
        return None
    data = pd.DataFrame({str(c): pd.Series(_numeric_values(df[c])) for c in cols})
    if len(data) < 3:
        return None
    corr = data.corr(numeric_only=True)
    if corr.empty or corr.isna().all().all():
        return None
    labels = [str(c) for c in corr.columns]
    matrix = [
        [_json_number(corr.iloc[row, col]) for col in range(len(labels))]
        for row in range(len(labels))
    ]
    return {"labels": labels, "matrix": matrix}


def chart_data(df, dashboard=None):
    """Payload JSON de tous les graphiques disponibles (React + Chart.js).

    Renvoie un dictionnaire sérialisable en JSON décrivant chaque graphique
    par son ``slug``, son ``kind`` (type de rendu côté navigateur) et ses
    données brutes. Les libellés sont traduits dans la langue active ; les
    nombres restent des flottants, le navigateur appliquant les séparateurs
    transmis à part.
    """
    dashboard = dashboard or {}
    available = set(available_charts(df, dashboard))
    payloads = {}

    if "score" in available:
        total = max(0.0, min(100.0, float(dashboard.get("score") or 0)))
        payloads["score"] = {
            "kind": "gauge",
            "data": {"value": total, "label": _("Score global de qualité")},
        }

    dimensions = dashboard.get("dimensions") or []
    if "dimensions" in available and dimensions:
        payloads["dimensions"] = {
            "kind": "hbar",
            "data": {
                "total": 100,
                "items": [
                    {
                        "label": str(d["name"]).capitalize(),
                        "value": _json_number(d["value"]),
                        # Réutilise la chaîne déjà traduite dans les catalogues.
                        "note": _("%(score)s / 100  (%(weight)s %(percent)s)")
                        % {
                            "score": _num(d["value"]),
                            "weight": _num(d.get("weight", 0)),
                            "percent": "%",
                        },
                    }
                    for d in dimensions
                ],
            },
        }

    if "missing" in available:
        rows = sorted(
            dashboard.get("columns_quality") or [],
            key=lambda row: row.get("completude", 0),
        )[:15]
        payloads["missing"] = {
            "kind": "hbar",
            "data": {
                "total": 100,
                "items": [
                    {
                        "label": str(row["colonne"]),
                        "value": _json_number(row.get("completude", 0)),
                        "color": _completeness_color(float(row.get("completude", 0))),
                    }
                    for row in rows
                ],
            },
        }

    if "problems" in available:
        payloads["problems"] = {
            "kind": "vbar",
            "data": {
                "items": [
                    {
                        "label": str(problem["label"]),
                        "value": _json_number(problem["value"]),
                        "color": _CLASS_COLORS.get(
                            problem.get("class"), BRAND[index % len(BRAND)]
                        ),
                    }
                    for index, problem in enumerate(dashboard.get("problems") or [])
                    if problem.get("value")
                ]
            },
        }

    if "histograms" in available:
        panels = []
        for index, col in enumerate(numeric_columns(df)):
            values = _numeric_values(df[col])
            if len(values) < 2:
                continue
            bins = max(5, min(20, len(values) // 3 or 5))
            edges, counts = _histogram(values, bins)
            panels.append(
                {
                    "label": str(col),
                    "color": BRAND[index % len(BRAND)],
                    "edges": edges,
                    "counts": counts,
                    "density": _density(values, edges),
                }
            )
        if panels:
            payloads["histograms"] = {"kind": "histograms", "data": {"panels": panels}}

    if "boxplots" in available:
        items = []
        for index, col in enumerate(numeric_columns(df)):
            stats = _box_stats(_numeric_values(df[col]))
            if stats is None:
                continue
            items.append(
                {"label": str(col), "color": BRAND[index % len(BRAND)], **stats}
            )
        if items:
            payloads["boxplots"] = {
                "kind": "boxplots",
                "data": {
                    "items": items,
                    # Libellés des statistiques affichées dans les infobulles.
                    # « Min », « Médiane » et « Max » réutilisent les entrées
                    # déjà présentes dans les catalogues du site.
                    "labels": {
                        "min": _("Min"),
                        "q1": _("Premier quartile"),
                        "median": _("Médiane"),
                        "q3": _("Troisième quartile"),
                        "max": _("Max"),
                        "outliers": _("valeur(s) extrême(s)"),
                    },
                },
            }

    if "correlation" in available:
        correlation = _correlation_payload(df)
        if correlation:
            payloads["correlation"] = {"kind": "heatmap", "data": correlation}

    if "categories" in available:
        panels = []
        for index, col in enumerate(categorical_columns(df)):
            values = [
                str(value)
                for value in df[col]
                if not _is_blank(value) and not is_unknown(value)
            ]
            counts = Counter(values).most_common(8)
            if not counts:
                continue
            panels.append(
                {
                    "label": str(col),
                    "color": BRAND[index % len(BRAND)],
                    "items": [
                        {"label": label, "value": count} for label, count in counts
                    ],
                }
            )
        if panels:
            payloads["categories"] = {"kind": "categories", "data": {"panels": panels}}

    if "outliers" in available:
        counts = Counter(
            str(outlier.get("colonne", "—"))
            for outlier in dashboard.get("outliers") or []
        )
        items = [
            {"label": label, "value": count, "color": COLOR_WARN}
            for label, count in counts.most_common(12)
        ]
        if items:
            payloads["outliers"] = {"kind": "hbar", "data": {"items": items}}

    if "moments" in available:
        items = [
            {
                "label": item["label"],
                "skewness": _json_number(item["skewness"]),
                "kurtosis": _json_number(item["kurtosis"]),
            }
            for item in _moments_items(df)
        ]
        if items:
            payloads["moments"] = {
                "kind": "moments",
                "data": {
                    "items": items,
                    "labels": {
                        "skewness": _("Asymétrie"),
                        "kurtosis": _("Aplatissement"),
                    },
                },
            }

    if "structural" in available:
        counts = Counter(
            str(anomaly.get("type_code", "—"))
            for anomaly in dashboard.get("structural_anomalies") or []
        )
        items = [
            {
                "label": str(structural_anomaly_label(code)),
                "value": count,
                "color": COLOR_WARN,
            }
            for code, count in counts.most_common(12)
        ]
        if items:
            payloads["structural"] = {"kind": "hbar", "data": {"items": items}}

    charts = []
    for slug, title, description in CHART_SPECS:
        payload = payloads.get(slug)
        if payload is None:
            continue
        charts.append(
            {
                "slug": slug,
                "title": str(title),
                "description": str(description),
                "kind": payload["kind"],
                "data": payload["data"],
            }
        )

    return {
        "language": translation.get_language() or "fr",
        "direction": "rtl" if _is_rtl() else "ltr",
        "separators": _separators(),
        "charts": charts,
    }


# --------------------------------------------------------------------------
# API publique
# --------------------------------------------------------------------------
def _builders(df, dashboard, theme):
    """Table slug → fabrique de graphique (évaluation paresseuse)."""
    dashboard = dashboard or {}
    return {
        "score": lambda: chart_score(dashboard.get("score", 0), theme),
        "dimensions": lambda: chart_dimensions(dashboard.get("dimensions"), theme),
        "missing": lambda: chart_missing(dashboard.get("columns_quality"), theme),
        "problems": lambda: chart_problems(dashboard.get("problems"), theme),
        "histograms": lambda: chart_histograms(df, theme),
        "boxplots": lambda: chart_boxplots(df, theme),
        "correlation": lambda: chart_correlation(df, theme),
        "categories": lambda: chart_categories(df, theme),
        "outliers": lambda: chart_outliers(df, dashboard.get("outliers"), theme),
        "moments": lambda: chart_moments(df, theme),
        "structural": lambda: chart_structural(
            df, dashboard.get("structural_anomalies"), theme
        ),
    }


def chart_png(df, dashboard, slug, theme="light"):
    """PNG d'un graphique identifié par son slug, ou ``None`` si indisponible."""
    builder = _builders(df, dashboard, theme).get(slug)
    if builder is None:
        return None
    try:
        return builder()
    except Exception:  # noqa: BLE001 — un graphique ne doit jamais casser la page
        return None


def available_charts(df, dashboard=None):
    """Slugs des graphiques réellement productibles, **sans les dessiner**.

    Permet à la page de n'afficher que les graphiques pertinents (et donc de
    ne déclencher le rendu PNG qu'à la demande, via l'endpoint dédié).
    """
    dashboard = dashboard or {}
    slugs = ["score"]
    if dashboard.get("dimensions"):
        slugs.append("dimensions")
    if dashboard.get("columns_quality"):
        slugs.append("missing")
    if any(p.get("value") for p in dashboard.get("problems") or []):
        slugs.append("problems")
    if numeric_columns(df):
        slugs.extend(["histograms", "boxplots"])
    if len(numeric_columns(df, limit=10)) >= 2:
        slugs.append("correlation")
    if categorical_columns(df):
        slugs.append("categories")
    if dashboard.get("outliers"):
        slugs.append("outliers")
    if _moments_items(df):
        slugs.append("moments")
    if dashboard.get("structural_anomalies"):
        slugs.append("structural")
    return slugs


def chart_catalog(df, dashboard=None):
    """Catalogue ordonné des graphiques disponibles.

    Renvoie une liste de dictionnaires ``{slug, title, description}``, prête à
    être consommée par les templates.
    """
    available = set(available_charts(df, dashboard))
    return [
        {"slug": slug, "title": title, "description": description}
        for slug, title, description in CHART_SPECS
        if slug in available
    ]


def build_charts(df, dashboard=None, theme="light"):
    """Construit tous les graphiques disponibles pour un DataFrame.

    Renvoie une liste de dictionnaires
    ``{slug, title, description, png}`` — les graphiques impossibles à
    produire (aucune colonne numérique, données insuffisantes…) sont omis.
    """
    builders = _builders(df, dashboard, theme)
    charts = []
    for slug, title, description in CHART_SPECS:
        try:
            png = builders[slug]()
        except Exception:  # noqa: BLE001
            png = None
        if png:
            charts.append(
                {
                    "slug": slug,
                    "title": title,
                    "description": description,
                    "png": png,
                }
            )
    return charts


def charts_as_data_uris(df, dashboard=None, theme="light"):
    """Comme :func:`build_charts`, mais avec les images en URI ``data:``.

    Utilisé pour produire un rapport HTML **autonome** (images embarquées,
    aucun fichier externe requis).
    """
    charts = build_charts(df, dashboard, theme)
    for chart in charts:
        chart["data_uri"] = _data_uri(chart["png"])
    return charts
