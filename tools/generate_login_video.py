"""Génère les vidéos de fond décoratives de la page de connexion.

Deux variantes sont produites, une par thème de l'application :

* ``login-bg.mp4`` + ``login-poster.jpg`` — thème sombre ;
* ``login-bg-light.mp4`` + ``login-poster-light.jpg`` — thème clair.

Le sujet est un tableau de bord animé : graphique en courbes multi-séries avec
aire remplie, histogramme dont les barres respirent, anneau de répartition qui
tourne, nuage de points qui dérive et grille de fond. Toutes les fréquences
sont entières, donc la dernière image se raccorde exactement à la première :
la boucle est invisible.

Usage :
    python tools/generate_login_video.py              # les deux thèmes
    python tools/generate_login_video.py --theme light
    python tools/generate_login_video.py --preview 3  # images PNG de contrôle
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from functools import partial
from pathlib import Path

import numpy as np
from PIL import Image

from video_kit import MP4_CODEC, blur, blur_rgb, encode_frames, report

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "static" / "video"
POSTER_DIR = ROOT / "static" / "img"
PREVIEW_DIR = ROOT / "files" / "_login_preview"

# Noms de fichiers attendus par templates/core/login.html et static/css/style.css.
VIDEO_NAMES = {"dark": "login-bg.mp4", "light": "login-bg-light.mp4"}
POSTER_NAMES = {"dark": "login-poster.jpg", "light": "login-poster-light.jpg"}

W, H = 1280, 720
FPS = 24
SECONDS = 10
FRAME_COUNT = FPS * SECONDS


def _rgb(*values: float) -> np.ndarray:
    return np.array(values, dtype=np.float32)


@dataclass(frozen=True)
class Theme:
    """Palette et réglages de composition d'une variante de la vidéo.

    ``additive`` distingue les deux façons de poser une couleur sur le fond :
    sur fond nuit on *ajoute* de la lumière, sur fond clair on *fond* la
    couleur (mélange alpha), sinon les accents délavent l'image vers le blanc.
    """

    name: str
    bg_top: np.ndarray
    bg_bottom: np.ndarray
    grid: np.ndarray
    cyan: np.ndarray
    indigo: np.ndarray
    violet: np.ndarray
    emerald: np.ndarray
    amber: np.ndarray
    highlight: np.ndarray
    additive: bool
    strength: float
    focus: float
    vignette: float


THEMES = {
    "dark": Theme(
        name="dark",
        bg_top=_rgb(8, 11, 24),
        bg_bottom=_rgb(13, 18, 38),
        grid=_rgb(86, 108, 168),
        cyan=_rgb(34, 211, 238),
        indigo=_rgb(99, 102, 241),
        violet=_rgb(168, 85, 247),
        emerald=_rgb(16, 185, 129),
        amber=_rgb(245, 158, 11),
        highlight=_rgb(226, 236, 255),
        additive=True,
        strength=1.0,
        focus=-0.58,
        vignette=-0.38,
    ),
    "light": Theme(
        name="light",
        bg_top=_rgb(247, 248, 252),
        bg_bottom=_rgb(222, 230, 246),
        grid=_rgb(148, 163, 200),
        cyan=_rgb(8, 145, 178),
        indigo=_rgb(79, 70, 229),
        violet=_rgb(147, 51, 234),
        emerald=_rgb(5, 150, 105),
        amber=_rgb(217, 119, 6),
        highlight=_rgb(30, 41, 59),
        additive=False,
        strength=1.30,
        focus=0.30,
        vignette=0.16,
    ),
}

# Grilles 2D (H, W) et vecteurs 1D pour le broadcasting.
YS = np.arange(H, dtype=np.float32)[:, None]
XS = np.arange(W, dtype=np.float32)[None, :]
YN = YS / H
XN = XS / W

# --- Histogramme (coin gauche) ------------------------------------------------
BAR_COUNT = 7
BAR_LEFT = 0.055 * W
BAR_PITCH = 0.285 * W / BAR_COUNT
BAR_WIDTH = 34.0
BAR_BASE = 0.545 * H
BAR_MAX = 0.30 * H
BAR_COLOURS = ("cyan", "indigo", "violet", "emerald", "cyan", "amber", "indigo")
# (fréquence temporelle, phase) — fréquences entières ⇒ boucle parfaite.
BAR_MOTION = ((1, 0.00), (2, 0.18), (1, 0.36), (2, 0.54), (1, 0.72), (2, 0.88), (1, 0.44))

# --- Anneau de répartition (coin droit) ---------------------------------------
DONUT_CX, DONUT_CY, DONUT_R = 0.805 * W, 0.295 * H, 106.0
DONUT_THICK = 13.0

# --- Graphique en courbes (bas de l'image) ------------------------------------
CHART_X0, CHART_X1 = 0.045 * W, 0.955 * W
CHART_BASE = 0.735 * H
# (base, amplitude, fréq. X, fréq. T, phase, couleur, poids)
SERIES = (
    (0.640, 0.105, 1, 1, 0.00, "cyan", 1.00),
    (0.520, 0.085, 2, 1, 0.30, "indigo", 0.80),
    (0.415, 0.065, 3, 2, 0.62, "violet", 0.62),
)

# --- Nuage de points ----------------------------------------------------------
POINT_COUNT = 90
_rng = np.random.default_rng(20261012)
POINT_X = _rng.random(POINT_COUNT, dtype=np.float32)
POINT_Y = _rng.random(POINT_COUNT, dtype=np.float32)
POINT_R = _rng.uniform(1.4, 3.0, POINT_COUNT).astype(np.float32)
POINT_F = _rng.integers(1, 3, POINT_COUNT).astype(np.float32)
POINT_P = _rng.random(POINT_COUNT, dtype=np.float32)
POINT_S = _rng.uniform(0.35, 1.0, POINT_COUNT).astype(np.float32)
POINT_C = _rng.integers(0, 4, POINT_COUNT)
POINT_PALETTE = ("cyan", "indigo", "violet", "emerald")


def base_gradient(theme: Theme) -> np.ndarray:
    """Dégradé vertical, légèrement incliné pour éviter l'effet « plat »."""
    ramp = np.clip(YN * 0.85 + XN * 0.15, 0.0, 1.0)
    return theme.bg_top + (theme.bg_bottom - theme.bg_top) * ramp[..., None]


_BASE_CACHE: dict[str, np.ndarray] = {}


def base_cache(theme: Theme) -> np.ndarray:
    if theme.name not in _BASE_CACHE:
        _BASE_CACHE[theme.name] = base_gradient(theme)
    return _BASE_CACHE[theme.name]


def paint(img: np.ndarray, mask: np.ndarray, colour: np.ndarray, amount: float, theme: Theme) -> None:
    """Compose une couleur sur l'image selon le mode du thème."""
    if theme.additive:
        img += mask[..., None] * colour * amount
        return
    alpha = np.clip(mask * amount * theme.strength, 0.0, 1.0)[..., None]
    img *= 1.0 - alpha
    img += alpha * colour


def paint_rgb(img: np.ndarray, field: np.ndarray, amount: float, theme: Theme) -> None:
    """Compose un halo coloré (H, W, 3) sur l'image selon le mode du thème."""
    if theme.additive:
        img += field * amount
        return
    peak = np.clip(field.max(axis=-1, keepdims=True) / 255.0, 0.0, 1.0)
    alpha = np.clip(peak * amount * theme.strength, 0.0, 1.0)
    img *= 1.0 - alpha
    img += field * alpha


def shade(img: np.ndarray, mask: np.ndarray, amount: float) -> None:
    """Éclaircit (``amount`` > 0) ou assombrit (< 0) l'image selon un masque."""
    if amount < 0:
        img *= (1.0 + amount * mask)[..., None]
    else:
        img += (255.0 - img) * (amount * mask)[..., None]


def add_point(field: np.ndarray, cx: float, cy: float, radius: float, strength: float) -> None:
    """Ajoute une petite tache gaussienne, sans calculer toute l'image."""
    reach = radius * 3.0
    x0, x1 = int(cx - reach), int(cx + reach) + 1
    y0, y1 = int(cy - reach), int(cy + reach) + 1
    if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
        return
    x0, x1 = max(x0, 0), min(x1, W)
    y0, y1 = max(y0, 0), min(y1, H)
    gx = np.exp(-((np.arange(x0, x1, dtype=np.float32) - cx) ** 2) / (2 * radius**2))
    gy = np.exp(-((np.arange(y0, y1, dtype=np.float32) - cy) ** 2) / (2 * radius**2))
    field[y0:y1, x0:x1] += strength * gy[:, None] * gx[None, :]


def draw_bars(img: np.ndarray, t: float, theme: Theme) -> None:
    """Histogramme dont les barres montent et descendent en respirant."""
    for index in range(BAR_COUNT):
        freq, phase = BAR_MOTION[index]
        colour = getattr(theme, BAR_COLOURS[index])
        x0 = BAR_LEFT + index * BAR_PITCH
        x1 = x0 + BAR_WIDTH
        wave = 0.5 + 0.5 * np.sin(2 * np.pi * (freq * t + phase))
        height = BAR_MAX * (0.30 + 0.70 * wave)
        top = BAR_BASE - height

        columns = (XS >= x0) & (XS < x1)
        body = (columns & (YS >= top) & (YS <= BAR_BASE)).astype(np.float32)
        paint(img, body, colour, 0.42, theme)

        cap = np.exp(-((YS - top) ** 2) / (2 * 2.6**2)) * columns
        paint(img, cap, colour, 0.95, theme)

    axis = np.exp(-((YS - BAR_BASE) ** 2) / (2 * 1.4**2)) * (XS >= BAR_LEFT - 12) * (XS <= BAR_LEFT + BAR_COUNT * BAR_PITCH + 12)
    paint(img, axis, theme.grid, 0.55, theme)


def draw_donut(img: np.ndarray, t: float, theme: Theme) -> None:
    """Anneau de répartition : deux arcs qui tournent en sens opposés."""
    dx = XS - DONUT_CX
    dy = YS - DONUT_CY
    distance = np.sqrt(dx**2 + dy**2)
    angle = np.arctan2(dy, dx)

    ring = np.exp(-((distance - DONUT_R) ** 2) / (2 * DONUT_THICK**2))
    paint(img, ring, theme.grid, 0.30, theme)

    for span, speed, phase, colour, weight in (
        (0.42, 1.0, 0.00, theme.cyan, 1.00),
        (0.26, -1.0, 0.35, theme.violet, 0.85),
    ):
        start = 2 * np.pi * (speed * t + phase)
        offset = (angle - start) % (2 * np.pi)
        arc = np.clip((span * 2 * np.pi - offset) * 5.0, 0.0, 1.0)
        paint(img, ring * arc, colour, weight, theme)

    inner = np.exp(-((distance - (DONUT_R - 34.0)) ** 2) / (2 * 3.0**2))
    start = 2 * np.pi * (-2 * t + 0.15)
    offset = (angle - start) % (2 * np.pi)
    arc = np.clip((0.30 * 2 * np.pi - offset) * 5.0, 0.0, 1.0)
    paint(img, inner * arc, theme.emerald, 0.75, theme)

    hub = np.exp(-(distance**2) / (2 * 26.0**2))
    paint(img, hub, theme.indigo, 0.22, theme)


def draw_chart(img: np.ndarray, t: float, theme: Theme) -> None:
    """Graphique en courbes multi-séries, avec aire remplie sous la première."""
    inside = (XS >= CHART_X0) & (XS <= CHART_X1)

    glow = np.zeros((H, W, 3), dtype=np.float32)
    first = None
    for base, amplitude, fx, ft, phase, colour_key, weight in SERIES:
        colour = getattr(theme, colour_key)
        curve = H * (base + amplitude * np.sin(2 * np.pi * (fx * XN + ft * t + phase)))
        if first is None:
            first = curve
        core = np.exp(-((YS - curve) ** 2) / (2 * 2.0**2)) * inside
        paint(img, core, colour, weight, theme)
        glow += (np.exp(-((YS - curve) ** 2) / (2 * 9.0**2)) * inside)[..., None] * colour * weight

    paint_rgb(img, blur_rgb(glow, 6.0), 0.55, theme)

    # Aire remplie sous la première série : donne du volume au graphique.
    area = np.clip((first - YS) / (0.26 * H), 0.0, 1.0) * inside
    paint(img, area**1.6, theme.cyan, 0.16, theme)

    # Axe horizontal + graduations verticales.
    axis = np.exp(-((YS - CHART_BASE) ** 2) / (2 * 1.4**2)) * inside
    paint(img, axis, theme.grid, 0.60, theme)
    for step in range(1, 8):
        x = CHART_X0 + (CHART_X1 - CHART_X0) * step / 8.0
        tick = np.exp(-((XS - x) ** 2) / (2 * 1.2**2)) * (YS >= CHART_BASE) * (YS <= CHART_BASE + 9)
        paint(img, tick, theme.grid, 0.45, theme)

    # Curseur : un point lumineux qui balaie la courbe, avec sa ligne de rappel.
    frac = 0.5 + 0.5 * np.sin(2 * np.pi * t)
    px = CHART_X0 + (CHART_X1 - CHART_X0) * frac
    py = H * (SERIES[0][0] + SERIES[0][1] * np.sin(2 * np.pi * (SERIES[0][2] * (px / W) + SERIES[0][3] * t + SERIES[0][4])))
    guide = np.exp(-((XS - px) ** 2) / (2 * 1.3**2)) * (YS >= py) * (YS <= CHART_BASE)
    paint(img, guide, theme.highlight, 0.20, theme)
    marker = np.exp(-((XS - px) ** 2 + (YS - py) ** 2) / (2 * 7.0**2))
    paint(img, marker, theme.highlight, 0.95, theme)
    halo = np.exp(-((XS - px) ** 2 + (YS - py) ** 2) / (2 * 22.0**2))
    paint(img, halo, theme.cyan, 0.45, theme)


def draw_points(img: np.ndarray, t: float, theme: Theme) -> None:
    """Nuage de points qui dérive : mouvement circulaire, donc raccord parfait."""
    field = np.zeros((H, W), dtype=np.float32)
    colour = np.zeros((H, W, 3), dtype=np.float32)
    for index in range(POINT_COUNT):
        angle = 2 * np.pi * (POINT_F[index] * t + POINT_P[index])
        px = ((POINT_X[index] + 0.022 * np.cos(angle)) % 1.0) * W
        py = ((POINT_Y[index] + 0.018 * np.sin(angle)) % 1.0) * H
        twinkle = 0.55 + 0.45 * np.sin(2 * np.pi * (2 * t + POINT_P[index]))
        strength = POINT_S[index] * twinkle
        add_point(field, px, py, POINT_R[index], strength)
        tint = getattr(theme, POINT_PALETTE[POINT_C[index]])
        for channel in range(3):
            add_point(colour[..., channel], px, py, POINT_R[index], strength * tint[channel] / 255.0)
    paint(img, blur(field, 1.1), theme.highlight, 0.55, theme)
    paint_rgb(img, blur_rgb(colour * 255.0, 1.6), 0.55, theme)


def render_frame(theme: Theme, t: float) -> bytes:
    """Rend une image de la boucle pour la position temporelle ``t`` dans [0, 1)."""
    img = base_cache(theme).copy()

    # --- Visualisations. ------------------------------------------------------
    draw_bars(img, t, theme)
    draw_donut(img, t, theme)
    draw_chart(img, t, theme)
    draw_points(img, t, theme)

    # --- Balayage diagonal : donne du relief à l'ensemble. --------------------
    diagonal = XN * 0.75 + YN * 0.25
    sweep = np.exp(-((diagonal - (0.5 + 0.5 * np.sin(2 * np.pi * t))) ** 2) / (2 * 0.16**2))
    paint(img, sweep, theme.indigo, 0.16, theme)

    # --- Recentrage : la carte de connexion reste lisible. --------------------
    focus = np.exp(-((XS - W * 0.5) ** 2 + (YS - H * 0.5) ** 2) / (2 * 420.0**2))
    shade(img, focus, theme.focus)

    # --- Vignette douce sur les bords. ---------------------------------------
    edge = np.clip(((XN - 0.5) ** 2 + (YN - 0.5) ** 2) / 0.5, 0.0, 1.0)
    shade(img, edge, theme.vignette)

    img = np.clip(img, 0.0, 255.0)
    # Léger dithering : évite le banding dans les dégradés.
    img += np.random.default_rng(int(t * 100000)).random((H, W, 1), dtype=np.float32) * 2.5
    return np.clip(img, 0.0, 255.0).astype(np.uint8).tobytes()


def frame_image(theme: Theme, t: float) -> Image.Image:
    return Image.frombytes("RGB", (W, H), render_frame(theme, t))


def encode(theme: Theme, name: str, codec: tuple[str, ...]) -> Path:
    """Encode la boucle complète en poussant les images brutes sur l'entrée ffmpeg."""
    return encode_frames(
        OUT_DIR / name,
        codec,
        partial(render_frame, theme),
        FRAME_COUNT,
        (W, H),
        FPS,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", type=int, default=0, help="nombre d'images PNG de contrôle")
    parser.add_argument(
        "--theme",
        choices=("dark", "light", "both"),
        default="both",
        help="variante(s) à produire (défaut : les deux)",
    )
    args = parser.parse_args()

    names = ("dark", "light") if args.theme == "both" else (args.theme,)

    if args.preview:
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        for name in names:
            theme = THEMES[name]
            for index in range(args.preview):
                image = frame_image(theme, index / max(1, FRAME_COUNT))
                path = PREVIEW_DIR / f"preview_{name}_{index:03d}.png"
                image.save(path)
                print(path)
        return

    POSTER_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        theme = THEMES[name]
        poster = POSTER_DIR / POSTER_NAMES[name]
        frame_image(theme, 0.0).save(poster, "JPEG", quality=82, optimize=True, progressive=True)
        report(f"{name} aff.", poster, ROOT)
        report(f"{name} mp4", encode(theme, VIDEO_NAMES[name], MP4_CODEC), ROOT)


if __name__ == "__main__":
    main()
