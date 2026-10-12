"""Génère la vidéo de fond (boucle sans couture) du hero de la page d'accueil.

Le rendu est entièrement procédural : dégradé nuit, halos indigo / violet / cyan,
trame de points dérivante, histogramme animé et balayage lumineux. Tous les
mouvements sont périodiques sur la durée de la boucle, donc la dernière image se
raccorde exactement à la première.

Usage :
    python tools/generate_hero_video.py              # mp4 + webm + poster
    python tools/generate_hero_video.py --preview 3  # images PNG de contrôle
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from video_kit import MP4_CODEC, WEBM_CODEC, blur, encode_frames, report

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "static" / "video"
POSTER = ROOT / "static" / "img" / "hero-poster.jpg"
PREVIEW_DIR = ROOT / "files" / "_hero_preview"

W, H = 1280, 720
FPS = 24
SECONDS = 10
FRAME_COUNT = FPS * SECONDS

NAVY_TOP = np.array([9.0, 12.0, 26.0], dtype=np.float32)
NAVY_BOTTOM = np.array([16.0, 21.0, 46.0], dtype=np.float32)
INDIGO = np.array([79.0, 70.0, 229.0], dtype=np.float32)
VIOLET = np.array([124.0, 58.0, 237.0], dtype=np.float32)
CYAN = np.array([6.0, 182.0, 212.0], dtype=np.float32)

YY = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None, None]
XX = np.linspace(0.0, 1.0, W, dtype=np.float32)[None, :, None]
YS = np.arange(H, dtype=np.float32)[:, None]
XS = np.arange(W, dtype=np.float32)[None, :]

DOT_STEP = 40
BAR_COUNT = 72
BAR_GAP = 4
BAR_MIN = 10
BAR_MAX = int(H * 0.30)
BEAM_SIGMA = 150.0

# Coordonnées des halos : (amplitude X, amplitude Y, fréquence, phase, couleur,
# intensité). Les fréquences sont entières pour garantir la boucle.
ORBS = (
    (0.15, 0.17, 1, 0.00, INDIGO, 0.55),
    (0.13, 0.14, 1, 0.55, VIOLET, 0.42),
    (0.18, 0.10, 2, 0.30, CYAN, 0.34),
    (0.10, 0.12, 2, 0.80, INDIGO, 0.26),
)


def base_gradient() -> np.ndarray:
    """Dégradé nuit diagonal servant de fond à chaque image."""
    grad = NAVY_TOP * (1.0 - YY) + NAVY_BOTTOM * YY
    grad = np.broadcast_to(grad, (H, W, 3)).copy()
    grad += (XX * 0.35 + YY * 0.65) * np.array([5.0, 3.0, 14.0], dtype=np.float32)
    return grad


def dot_mask() -> np.ndarray:
    """Trame de points régulière, périodique sur les deux axes."""
    dx = XS % DOT_STEP - DOT_STEP / 2.0
    dy = YS % DOT_STEP - DOT_STEP / 2.0
    d2 = dx**2 + dy**2
    return np.exp(-d2 / (2.0 * 1.5**2)).astype(np.float32)


def gaussian(cx: float, cy: float, sigma: float) -> np.ndarray:
    """Nappe gaussienne normalisée, utilisée pour les halos et le balayage."""
    d2 = (XS - cx) ** 2 + (YS - cy) ** 2
    return np.exp(-d2 / (2.0 * sigma**2)).astype(np.float32)


# Caractéristiques aléatoires mais figées des barres de l'histogramme.
_rng = np.random.default_rng(20261011)
BAR_PHASE = _rng.random(BAR_COUNT).astype(np.float32)
BAR_FREQ = _rng.integers(1, 4, BAR_COUNT).astype(np.float32)
BAR_AMP = (0.45 + 0.55 * _rng.random(BAR_COUNT)).astype(np.float32)
BAR_TINT = _rng.random(BAR_COUNT).astype(np.float32)
BAR_T = np.linspace(0.0, 1.0, BAR_COUNT, dtype=np.float32)

DOT_CACHE = dot_mask()
BASE_CACHE = base_gradient()
_SIGMA = 26.0
GLOW_ROWS = np.exp(-((np.arange(H, dtype=np.float32) - (H - BAR_MAX * 0.5)) ** 2) / (2 * _SIGMA**2))


def render_frame(t: float) -> bytes:
    """Rend une image de la boucle pour la position temporelle ``t`` dans [0, 1)."""
    img = BASE_CACHE.copy()

    # Halos colorés : deux orbites décalées par halo, sans dérive sur la boucle.
    for amp_x, amp_y, step, phase, color, strength in ORBS:
        cx = W * (0.5 + amp_x * np.cos(2 * np.pi * step * t + 2 * np.pi * phase))
        cy = H * (0.5 + amp_y * np.sin(2 * np.pi * step * t + 2 * np.pi * phase))
        img += gaussian(cx, cy, 250.0)[..., None] * color * strength

    # Trame de points : dérive circulaire, donc raccord parfait.
    offset_x = int(round(DOT_STEP * 2 * t)) % DOT_STEP
    offset_y = int(round(DOT_STEP * t)) % DOT_STEP
    drift = np.roll(np.roll(DOT_CACHE, offset_y, axis=0), offset_x, axis=1)
    img += drift[..., None] * np.array([120.0, 150.0, 240.0], dtype=np.float32) * 0.20

    # Histogramme animé : chaque barre oscille à une fréquence entière.
    wave = 0.5 + 0.5 * np.sin(
        2 * np.pi * (BAR_FREQ * t + BAR_PHASE) + 2 * np.pi * 2 * t - BAR_T * 6.0
    )
    heights = BAR_MIN + BAR_MAX * BAR_AMP * wave

    step_w = W / BAR_COUNT + 0.0
    beam_x = t * (W + 4 * BEAM_SIGMA) - 2 * BEAM_SIGMA
    sweep = np.exp(
        -((np.arange(W, dtype=np.float32) - beam_x) ** 2) / (2 * (BEAM_SIGMA * 0.45) ** 2)
    ).astype(np.float32)

    bars = np.zeros((H, W), dtype=np.float32)
    color_map = np.zeros((H, W, 3), dtype=np.float32)
    for i in range(BAR_COUNT):
        x0 = int(round(i * step_w))
        x1 = max(x0 + 1, int(round((i + 1) * step_w)) - BAR_GAP)
        top = int(round(H - heights[i]))
        bars[top:H, x0:x1] = 1.0
        tint = BAR_TINT[i]
        color = INDIGO * (1.0 - tint) + CYAN * tint
        color_map[top:H, x0:x1] = color

    # Le balayage « nettoie » les barres traversées : elles s'illuminent et
    # virent au cyan avant de retomber.
    boosted = bars * (0.55 + 1.45 * sweep)[None, :]
    img += boosted[..., None] * color_map * 0.85
    img += boosted[..., None] * (INDIGO * 0.5 + CYAN * sweep[None, :, None] * 0.6) * 0.35

    # Halo diffus sous les barres, pour lier l'histogramme au fond.
    glow = blur(bars, 22.0) * GLOW_ROWS[:, None]
    img += glow[..., None] * np.array([80.0, 90.0, 210.0], dtype=np.float32) * 0.55

    # Faisceau lumineux vertical, visible même sans barre.
    img += (sweep * (0.35 + 0.65 * (1.0 - YY[:, :, 0])))[..., None] * (
        np.array([120.0, 160.0, 255.0], dtype=np.float32) * 0.28
    )

    # Assombrissement du centre : garantit le contraste du texte blanc du hero.
    focus = gaussian(W * 0.5, H * 0.34, 340.0) * 0.42
    img *= (1.0 - focus)[..., None]

    # Vignette douce sur les bords.
    edge = ((XS / W - 0.5) ** 2 + (YS / H - 0.5) ** 2) / 0.5
    img *= (1.0 - 0.35 * np.clip(edge, 0.0, 1.0))[..., None]

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

    report("mp4", encode("hero.mp4", MP4_CODEC), ROOT)

    try:
        webm = encode("hero.webm", WEBM_CODEC)
    except SystemExit:
        print("webm   : codec VP9 indisponible, ignoré", file=sys.stderr)
    else:
        report("webm", webm, ROOT)


if __name__ == "__main__":
    main()
