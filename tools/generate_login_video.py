"""Génère la vidéo de fond décorative de la page de connexion.

Le thème est celui de l'application : un tableau de bord animé. On y voit un
graphique en courbes multi-séries avec aire remplie, un histogramme dont les
barres respirent, un anneau de répartition qui tourne, un nuage de points qui
dérive et une grille de fond. Toutes les fréquences sont entières, donc la
dernière image se raccorde exactement à la première : la boucle est invisible.

Usage :
    python tools/generate_login_video.py              # mp4 + webm + poster
    python tools/generate_login_video.py --preview 3  # images PNG de contrôle
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from video_kit import MP4_CODEC, WEBM_CODEC, blur, blur_rgb, encode_frames, report

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "static" / "video"
POSTER = ROOT / "static" / "img" / "login-poster.jpg"
PREVIEW_DIR = ROOT / "files" / "_login_preview"

W, H = 1280, 720
FPS = 24
SECONDS = 10
FRAME_COUNT = FPS * SECONDS

# Palette « tableau de bord » : nuit profonde + accents de visualisation.
BG_TOP = np.array([8.0, 11.0, 24.0], dtype=np.float32)
BG_BOTTOM = np.array([13.0, 18.0, 38.0], dtype=np.float32)
GRID_COLOR = np.array([86.0, 108.0, 168.0], dtype=np.float32)
CYAN = np.array([34.0, 211.0, 238.0], dtype=np.float32)
INDIGO = np.array([99.0, 102.0, 241.0], dtype=np.float32)
VIOLET = np.array([168.0, 85.0, 247.0], dtype=np.float32)
EMERALD = np.array([16.0, 185.0, 129.0], dtype=np.float32)
AMBER = np.array([245.0, 158.0, 11.0], dtype=np.float32)
WHITE = np.array([226.0, 236.0, 255.0], dtype=np.float32)

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
BAR_COLORS = (CYAN, INDIGO, VIOLET, EMERALD, CYAN, AMBER, INDIGO)
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
    (0.640, 0.105, 1, 1, 0.00, CYAN, 1.00),
    (0.520, 0.085, 2, 1, 0.30, INDIGO, 0.80),
    (0.415, 0.065, 3, 2, 0.62, VIOLET, 0.62),
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
POINT_PALETTE = (CYAN, INDIGO, VIOLET, EMERALD)


def base_gradient() -> np.ndarray:
    """Dégradé nuit vertical, légèrement incliné pour éviter l'effet « plat »."""
    ramp = np.clip(YN * 0.85 + XN * 0.15, 0.0, 1.0)
    return BG_TOP + (BG_BOTTOM - BG_TOP) * ramp[..., None]


BASE_CACHE = base_gradient()


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


def draw_bars(img: np.ndarray, t: float) -> None:
    """Histogramme dont les barres montent et descendent en respirant."""
    for index in range(BAR_COUNT):
        freq, phase = BAR_MOTION[index]
        colour = BAR_COLORS[index]
        x0 = BAR_LEFT + index * BAR_PITCH
        x1 = x0 + BAR_WIDTH
        wave = 0.5 + 0.5 * np.sin(2 * np.pi * (freq * t + phase))
        height = BAR_MAX * (0.30 + 0.70 * wave)
        top = BAR_BASE - height

        columns = (XS >= x0) & (XS < x1)
        body = columns & (YS >= top) & (YS <= BAR_BASE)
        img += body[..., None] * colour * 0.42

        cap = np.exp(-((YS - top) ** 2) / (2 * 2.6**2)) * columns
        img += cap[..., None] * colour * 0.95

    axis = np.exp(-((YS - BAR_BASE) ** 2) / (2 * 1.4**2)) * (XS >= BAR_LEFT - 12) * (XS <= BAR_LEFT + BAR_COUNT * BAR_PITCH + 12)
    img += axis[..., None] * GRID_COLOR * 0.55


def draw_donut(img: np.ndarray, t: float) -> None:
    """Anneau de répartition : deux arcs qui tournent en sens opposés."""
    dx = XS - DONUT_CX
    dy = YS - DONUT_CY
    distance = np.sqrt(dx**2 + dy**2)
    angle = np.arctan2(dy, dx)

    ring = np.exp(-((distance - DONUT_R) ** 2) / (2 * DONUT_THICK**2))
    img += ring[..., None] * GRID_COLOR * 0.30

    for span, speed, phase, colour, weight in (
        (0.42, 1.0, 0.00, CYAN, 1.00),
        (0.26, -1.0, 0.35, VIOLET, 0.85),
    ):
        start = 2 * np.pi * (speed * t + phase)
        offset = (angle - start) % (2 * np.pi)
        arc = np.clip((span * 2 * np.pi - offset) * 5.0, 0.0, 1.0)
        img += (ring * arc)[..., None] * colour * weight

    inner = np.exp(-((distance - (DONUT_R - 34.0)) ** 2) / (2 * 3.0**2))
    start = 2 * np.pi * (-2 * t + 0.15)
    offset = (angle - start) % (2 * np.pi)
    arc = np.clip((0.30 * 2 * np.pi - offset) * 5.0, 0.0, 1.0)
    img += (inner * arc)[..., None] * EMERALD * 0.75

    hub = np.exp(-(distance**2) / (2 * 26.0**2))
    img += hub[..., None] * INDIGO * 0.22


def draw_chart(img: np.ndarray, t: float) -> None:
    """Graphique en courbes multi-séries, avec aire remplie sous la première."""
    inside = (XS >= CHART_X0) & (XS <= CHART_X1)

    glow = np.zeros((H, W, 3), dtype=np.float32)
    first = None
    for base, amplitude, fx, ft, phase, colour, weight in SERIES:
        curve = H * (base + amplitude * np.sin(2 * np.pi * (fx * XN + ft * t + phase)))
        if first is None:
            first = curve
        core = np.exp(-((YS - curve) ** 2) / (2 * 2.0**2)) * inside
        img += core[..., None] * colour * weight
        glow += (np.exp(-((YS - curve) ** 2) / (2 * 9.0**2)) * inside)[..., None] * colour * weight

    img += blur_rgb(glow, 6.0) * 0.55

    # Aire remplie sous la première série : donne du volume au graphique.
    area = np.clip((first - YS) / (0.26 * H), 0.0, 1.0) * inside
    img += (area**1.6)[..., None] * CYAN * 0.16

    # Axe horizontal + graduations verticales.
    axis = np.exp(-((YS - CHART_BASE) ** 2) / (2 * 1.4**2)) * inside
    img += axis[..., None] * GRID_COLOR * 0.60
    for step in range(1, 8):
        x = CHART_X0 + (CHART_X1 - CHART_X0) * step / 8.0
        tick = np.exp(-((XS - x) ** 2) / (2 * 1.2**2)) * (YS >= CHART_BASE) * (YS <= CHART_BASE + 9)
        img += tick[..., None] * GRID_COLOR * 0.45

    # Curseur : un point lumineux qui balaie la courbe, avec sa ligne de rappel.
    frac = 0.5 + 0.5 * np.sin(2 * np.pi * t)
    px = CHART_X0 + (CHART_X1 - CHART_X0) * frac
    py = H * (SERIES[0][0] + SERIES[0][1] * np.sin(2 * np.pi * (SERIES[0][2] * (px / W) + SERIES[0][3] * t + SERIES[0][4])))
    guide = np.exp(-((XS - px) ** 2) / (2 * 1.3**2)) * (YS >= py) * (YS <= CHART_BASE)
    img += guide[..., None] * WHITE * 0.20
    marker = np.exp(-((XS - px) ** 2 + (YS - py) ** 2) / (2 * 7.0**2))
    img += marker[..., None] * WHITE * 0.95
    halo = np.exp(-((XS - px) ** 2 + (YS - py) ** 2) / (2 * 22.0**2))
    img += halo[..., None] * CYAN * 0.45


def draw_points(img: np.ndarray, t: float) -> None:
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
        add_point(colour[..., 0], px, py, POINT_R[index], strength * POINT_PALETTE[POINT_C[index]][0] / 255.0)
        add_point(colour[..., 1], px, py, POINT_R[index], strength * POINT_PALETTE[POINT_C[index]][1] / 255.0)
        add_point(colour[..., 2], px, py, POINT_R[index], strength * POINT_PALETTE[POINT_C[index]][2] / 255.0)
    img += blur(field, 1.1)[..., None] * WHITE * 0.55
    img += blur_rgb(colour * 255.0, 1.6) * 0.55


def render_frame(t: float) -> bytes:
    """Rend une image de la boucle pour la position temporelle ``t`` dans [0, 1)."""
    img = BASE_CACHE.copy()

    # --- Visualisations. ------------------------------------------------------
    draw_bars(img, t)
    draw_donut(img, t)
    draw_chart(img, t)
    draw_points(img, t)

    # --- Balayage diagonal : donne du relief à l'ensemble. --------------------
    diagonal = XN * 0.75 + YN * 0.25
    sweep = np.exp(-((diagonal - (0.5 + 0.5 * np.sin(2 * np.pi * t))) ** 2) / (2 * 0.16**2))
    img += sweep[..., None] * INDIGO * 0.16

    # --- Assombrissement central : la carte de connexion reste lisible. -------
    focus = np.exp(-((XS - W * 0.5) ** 2 + (YS - H * 0.5) ** 2) / (2 * 420.0**2))
    img *= (1.0 - 0.58 * focus)[..., None]

    # --- Vignette douce sur les bords. ---------------------------------------
    edge = ((XN - 0.5) ** 2 + (YN - 0.5) ** 2) / 0.5
    img *= (1.0 - 0.38 * np.clip(edge, 0.0, 1.0))[..., None]

    img = np.clip(img, 0.0, 255.0)
    # Léger dithering : évite le banding dans les dégradés sombres.
    img += np.random.default_rng(int(t * 100000)).random((H, W, 1), dtype=np.float32) * 2.5
    return np.clip(img, 0.0, 255.0).astype(np.uint8).tobytes()


def frame_image(t: float) -> Image.Image:
    return Image.frombytes("RGB", (W, H), render_frame(t))


def encode(name: str, codec: tuple[str, ...]) -> Path:
    """Encode la boucle complète en poussant les images brutes sur l'entrée ffmpeg."""
    return encode_frames(OUT_DIR / name, codec, render_frame, FRAME_COUNT, (W, H), FPS)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", type=int, default=0, help="nombre d'images PNG de contrôle")
    args = parser.parse_args()

    if args.preview:
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        for index in range(args.preview):
            image = frame_image(index / max(1, FRAME_COUNT))
            path = PREVIEW_DIR / f"preview_{index:03d}.png"
            image.save(path)
            print(path)
        return

    POSTER.parent.mkdir(parents=True, exist_ok=True)
    frame_image(0.0).save(POSTER, "JPEG", quality=82, optimize=True, progressive=True)
    report("poster", POSTER, ROOT)

    report("mp4", encode("login.mp4", MP4_CODEC), ROOT)

    try:
        webm = encode("login.webm", WEBM_CODEC)
    except SystemExit:
        print("webm   : codec VP9 indisponible, ignoré", file=sys.stderr)
    else:
        report("webm", webm, ROOT)


if __name__ == "__main__":
    main()
