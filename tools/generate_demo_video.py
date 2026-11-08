"""Génère la vidéo de démonstration animée de la page d'accueil.

Une boucle de 12 secondes, dans la palette lime du site, raconte le
nettoyage d'un fichier :

1. un tableau de données apparaît ligne à ligne ;
2. le curseur clique sur le bouton de nettoyage ;
3. un faisceau parcourt le tableau, les cellules en erreur passent au rouge ;
4. chaque erreur est corrigée (vert + coche), le doublon s'efface ;
5. le score de qualité grimpe et l'histogramme se remplit ;
6. tout s'estompe puis la boucle reprend sans saut.

La vidéo ne contient **aucun texte** (barres, icônes et chiffres seulement) :
elle reste valable dans les 23 langues de l'interface.

Usage :
    python tools/generate_demo_video.py              # mp4 + webm + poster
    python tools/generate_demo_video.py --preview 6  # images PNG de contrôle
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from video_kit import MP4_CODEC, WEBM_CODEC, encode_frames, report

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "static" / "video"
POSTER = ROOT / "static" / "img" / "demo-poster.jpg"
PREVIEW_DIR = ROOT / "files" / "_demo_preview"

W, H = 1280, 720
SS = 2  # sur-échantillonnage : dessin en 2x puis réduction (anticrénelage)
FPS = 30
SECONDS = 12
FRAME_COUNT = FPS * SECONDS

# Palette du site (section 22 de style.css).
BG = (246, 247, 243)
CARD = (255, 255, 255)
BORDER = (226, 229, 220)
INK = (17, 20, 14)
MUTED = (178, 184, 170)
BAR = (214, 219, 207)
LIME = (140, 198, 63)
LIME_LIGHT = (198, 230, 107)
LIME_DARK = (77, 124, 15)
LIME_SOFT = (232, 245, 205)
CHARCOAL = (71, 85, 105)
RED = (239, 68, 68)
RED_SOFT = (254, 226, 226)
ORANGE = (245, 158, 11)
ORANGE_SOFT = (254, 243, 199)

# --- Données du tableau ---------------------------------------------------
# Largeur relative de la « valeur » de chaque cellule (barre grise) ; une
# cellule en erreur a une valeur aberrante, corrigée vers ``fixed``.
COLUMNS = (0.17, 0.33, 0.27, 0.23)  # proportions des colonnes
ROWS = (
    (0.55, 0.80, 0.70, 0.45),
    (0.70, 0.62, 0.92, 0.50),
    (0.48, 0.86, 0.66, 0.40),
    (0.62, 0.74, 0.70, 0.55),  # doublon de la ligne 1 (supprimé)
    (0.58, 0.70, 0.60, 0.48),
    (0.66, 0.90, 0.74, 0.42),
    (0.52, 0.66, 0.68, 0.52),
)
DUPLICATE_ROW = 3
# (ligne, colonne, valeur corrigée) : ordre de correction.
ERRORS = ((0, 1, 0.70), (1, 2, 0.70), (2, 0, 0.60), (4, 3, 0.50), (5, 1, 0.74), (6, 2, 0.70))

# --- Chronologie (fractions de la boucle) ---------------------------------
T_TABLE = (0.00, 0.12)
T_CURSOR = (0.10, 0.20)
T_CLICK = 0.20
T_SCAN = (0.22, 0.36)
T_FIX = (0.38, 0.66)
T_DUP = (0.62, 0.70)
T_SCORE = (0.58, 0.86)
T_FADE_OUT = (0.93, 1.00)
SCORE_FROM, SCORE_TO = 58, 96


# --- Outils ---------------------------------------------------------------
def clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def phase(t: float, span: tuple[float, float]) -> float:
    start, end = span
    return clamp((t - start) / (end - start))


def ease(x: float) -> float:
    """Ease-in-out cubique."""
    return 4 * x * x * x if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out(x: float) -> float:
    return 1 - (1 - x) ** 3


def back_out(x: float) -> float:
    """Léger dépassement (effet « pop »)."""
    c1, c3 = 1.70158, 2.70158
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2


def mix(a, b, k: float):
    return tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(3))


def s(value: float) -> int:
    """Coordonnée à l'échelle du sur-échantillonnage."""
    return int(round(value * SS))


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in (
        "/usr/share/fonts/opentype/inter/InterDisplay-Bold.otf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(path).exists():
            return ImageFont.truetype(path, size * SS)
    return ImageFont.load_default()


FONT_SCORE = load_font(64)
FONT_SMALL = load_font(20)


def rrect(draw: ImageDraw.ImageDraw, box, radius, **kwargs) -> None:
    x0, y0, x1, y1 = box
    if x1 - x0 < 1 or y1 - y0 < 1:
        return  # forme écrasée (ligne en train de disparaître)
    radius = min(radius, (x1 - x0) / 2, (y1 - y0) / 2)
    draw.rounded_rectangle((s(x0), s(y0), s(x1), s(y1)), radius=s(radius), **kwargs)


def check_mark(draw, cx, cy, size, color, progress=1.0, width=3.2) -> None:
    """Coche tracée progressivement (``progress`` dans [0, 1])."""
    points = [(cx - size * 0.45, cy), (cx - size * 0.1, cy + size * 0.35), (cx + size * 0.5, cy - size * 0.35)]
    first = math.dist(points[0], points[1])
    second = math.dist(points[1], points[2])
    length = (first + second) * progress
    path = [points[0]]
    if length <= first:
        k = length / first
        path.append((points[0][0] + (points[1][0] - points[0][0]) * k, points[0][1] + (points[1][1] - points[0][1]) * k))
    else:
        path.append(points[1])
        k = (length - first) / second
        path.append((points[1][0] + (points[2][0] - points[1][0]) * k, points[1][1] + (points[2][1] - points[1][1]) * k))
    draw.line([(s(x), s(y)) for x, y in path], fill=color, width=s(width), joint="curve")


def cross_mark(draw, cx, cy, size, color, width=3.0) -> None:
    d = size * 0.35
    draw.line((s(cx - d), s(cy - d), s(cx + d), s(cy + d)), fill=color, width=s(width))
    draw.line((s(cx - d), s(cy + d), s(cx + d), s(cy - d)), fill=color, width=s(width))


# --- Scène ------------------------------------------------------------------
TABLE_X, TABLE_Y, TABLE_W = 70, 96, 690
HEADER_H, ROW_H = 46, 64
PANEL_X, PANEL_Y, PANEL_W, PANEL_H = 800, 96, 410, 528
BUTTON = (PANEL_X + 40, 560, PANEL_X + PANEL_W - 40, 604)


def fix_progress(t: float, index: int) -> float:
    """Avancement de la correction de la n-ième erreur."""
    start, end = T_FIX
    slot = (end - start) / len(ERRORS)
    return clamp((t - (start + index * slot)) / (slot * 0.9))


def detected(t: float, row: int) -> float:
    """1 quand le faisceau du scan a dépassé la ligne ``row``."""
    scan = ease(phase(t, T_SCAN))
    return clamp((scan * (len(ROWS) + 1) - row) * 2.0)


def draw_background(draw: ImageDraw.ImageDraw) -> None:
    draw.rectangle((0, 0, s(W), s(H)), fill=BG)
    for x in range(20, W, 28):
        for y in range(16, 200, 28):
            alpha = 1 - y / 200
            draw.ellipse((s(x - 1.3), s(y - 1.3), s(x + 1.3), s(y + 1.3)), fill=mix(BG, (196, 201, 188), alpha))
    # Arcs verts décoratifs (rappel des en-têtes de page).
    draw.arc((s(W - 260), s(-300), s(W + 260), s(220)), 90, 200, fill=LIME, width=s(10))
    draw.arc((s(W - 300), s(-340), s(W + 300), s(260)), 95, 190, fill=mix(BG, LIME, 0.35), width=s(3))
    draw.arc((s(-180), s(H - 160), s(180), s(H + 200)), 280, 30, fill=mix(BG, LIME, 0.7), width=s(8))


def draw_table(draw: ImageDraw.ImageDraw, t: float) -> None:
    appear = phase(t, T_TABLE)
    dup = ease(phase(t, T_DUP))

    # Carte du tableau (hauteur qui se resserre quand le doublon disparaît).
    rows_h = ROW_H * (len(ROWS) - dup)
    card = (TABLE_X - 18, TABLE_Y - 18, TABLE_X + TABLE_W + 18, TABLE_Y + HEADER_H + rows_h + 18)
    rrect(draw, (card[0], card[1] + 6, card[2], card[3] + 10), 22, fill=(232, 234, 227))
    rrect(draw, card, 22, fill=CARD, outline=BORDER, width=s(1.5))

    # En-tête vert lime.
    rrect(draw, (TABLE_X, TABLE_Y, TABLE_X + TABLE_W, TABLE_Y + HEADER_H), 12, fill=LIME)
    x = TABLE_X
    for width in COLUMNS:
        col_w = width * TABLE_W
        rrect(draw, (x + 16, TABLE_Y + 18, x + 16 + col_w * 0.42, TABLE_Y + 28), 5, fill=(36, 60, 10))
        x += col_w

    y = TABLE_Y + HEADER_H
    for row_index, row in enumerate(ROWS):
        # Apparition décalée de chaque ligne.
        row_appear = ease_out(clamp(appear * (len(ROWS) + 2) - row_index))
        if row_appear <= 0:
            continue
        height = ROW_H
        fade = row_appear
        if row_index == DUPLICATE_ROW:
            height = ROW_H * (1 - dup)
            fade *= 1 - dup
            if height < 1:
                continue
        offset = (1 - row_appear) * 24
        top = y + offset
        is_dup = row_index == DUPLICATE_ROW
        hit = detected(t, row_index)

        # Fond de ligne : doublon détecté en orange.
        if is_dup and hit > 0:
            rrect(draw, (TABLE_X, top + 4, TABLE_X + TABLE_W, top + height - 4), 10,
                  fill=mix(CARD, ORANGE_SOFT, hit * fade))
        elif row_index % 2 == 1:
            rrect(draw, (TABLE_X, top + 4, TABLE_X + TABLE_W, top + height - 4), 10,
                  fill=mix(CARD, (247, 248, 245), fade))

        x = TABLE_X
        for col_index, width in enumerate(COLUMNS):
            col_w = width * TABLE_W
            value = row[col_index]
            color = mix(CARD, BAR, fade)
            error = next(((i, fixed) for i, (r, c, fixed) in enumerate(ERRORS) if r == row_index and c == col_index), None)
            if error is not None and height >= ROW_H * 0.5:
                order, fixed = error
                fixed_k = ease(fix_progress(t, order))
                red_k = hit * (1 - fixed_k)
                cell = (x + 8, top + 12, x + col_w - 8, top + height - 12)
                if red_k > 0.01:
                    rrect(draw, cell, 9, fill=mix(CARD, RED_SOFT, red_k * fade))
                if fixed_k > 0.01:
                    rrect(draw, cell, 9, fill=mix(CARD, LIME_SOFT, fixed_k * fade))
                value = value + (fixed - value) * fixed_k
                color = mix(mix(CARD, BAR, fade), RED, red_k * 0.85)
                color = mix(color, LIME_DARK, fixed_k * 0.55)
                if fixed_k > 0.05:
                    pop = back_out(clamp(fixed_k * 1.4))
                    cx, cy, r = x + col_w - 26, top + height / 2, 11 * pop
                    draw.ellipse((s(cx - r), s(cy - r), s(cx + r), s(cy + r)), fill=LIME)
                    check_mark(draw, cx, cy, 13 * pop, CARD, progress=clamp(fixed_k * 1.6), width=2.6)
                elif red_k > 0.4:
                    cx, cy = x + col_w - 26, top + height / 2
                    draw.ellipse((s(cx - 10), s(cy - 10), s(cx + 10), s(cy + 10)), fill=mix(CARD, RED, red_k))
                    cross_mark(draw, cx, cy, 14, CARD, width=2.4)
            bar_w = (col_w - 64) * value
            if height > 30:
                bar_h = 10
                cy = top + height / 2
                rrect(draw, (x + 18, cy - bar_h / 2, x + 18 + bar_w, cy + bar_h / 2), 5, fill=color)
            x += col_w
        y += height

    # Faisceau du scan.
    scan_k = phase(t, T_SCAN)
    if 0 < scan_k < 1:
        beam_y = TABLE_Y + HEADER_H + ease(scan_k) * ROW_H * len(ROWS)
        for i in range(14):
            k = 1 - i / 14
            draw.line((s(TABLE_X), s(beam_y - i * 2), s(TABLE_X + TABLE_W), s(beam_y - i * 2)),
                      fill=mix(CARD, LIME_LIGHT, 0.55 * k), width=s(2))
        draw.line((s(TABLE_X - 6), s(beam_y), s(TABLE_X + TABLE_W + 6), s(beam_y)), fill=LIME, width=s(3))


def draw_panel(draw: ImageDraw.ImageDraw, image: Image.Image, t: float) -> None:
    appear = ease_out(phase(t, (0.04, 0.16)))
    if appear <= 0:
        return
    dy = (1 - appear) * 30
    x0, y0 = PANEL_X, PANEL_Y + dy
    rrect(draw, (x0, y0 + 6, x0 + PANEL_W, y0 + PANEL_H + 10), 24, fill=(232, 234, 227))
    rrect(draw, (x0, y0, x0 + PANEL_W, y0 + PANEL_H), 24, fill=CARD, outline=BORDER, width=s(1.5))
    # Liseré lime à gauche, comme les bandeaux de page.
    rrect(draw, (x0, y0 + 24, x0 + 5, y0 + PANEL_H - 24), 3, fill=LIME)

    # --- Jauge de score.
    score_k = ease(phase(t, T_SCORE))
    score = SCORE_FROM + (SCORE_TO - SCORE_FROM) * score_k
    cx, cy, radius = x0 + PANEL_W / 2, y0 + 150, 96
    box = (s(cx - radius), s(cy - radius), s(cx + radius), s(cy + radius))
    draw.arc(box, 0, 360, fill=(236, 239, 231), width=s(18))
    end_angle = -90 + 360 * score / 100
    # Dégradé de l'arc : segments successifs du vert foncé au lime clair.
    steps = 90
    for i in range(steps):
        a0 = -90 + (end_angle + 90) * i / steps
        a1 = -90 + (end_angle + 90) * (i + 1) / steps + 0.6
        draw.arc(box, a0, a1, fill=mix((79, 157, 42), LIME_LIGHT, i / steps), width=s(18))
    label = f"{int(round(score))}"
    color = mix(mix(INK, RED, 0.75), INK, score_k)
    bbox = draw.textbbox((0, 0), label, font=FONT_SCORE)
    draw.text((s(cx) - (bbox[2] - bbox[0]) / 2 - bbox[0], s(cy) - (bbox[3] - bbox[1]) / 2 - bbox[1] - s(6)),
              label, font=FONT_SCORE, fill=color)
    small = "/100"
    bbox = draw.textbbox((0, 0), small, font=FONT_SMALL)
    draw.text((s(cx) - (bbox[2] - bbox[0]) / 2, s(cy + 30)), small, font=FONT_SMALL, fill=MUTED)

    # --- Mini-histogramme : barres anthracite (avant) puis lime (après).
    base_y = y0 + 400
    heights_before = (0.55, 0.35, 0.70, 0.45, 0.60)
    heights_after = (0.92, 0.85, 0.97, 0.88, 0.95)
    chart_x = x0 + 60
    bar_w = 44
    for i in range(5):
        k = ease_out(clamp(score_k * 1.3 - i * 0.08))
        h_before = 70 * heights_before[i] * appear
        h_after = 70 * heights_after[i] * k
        x = chart_x + i * 62
        rrect(draw, (x, base_y - h_before, x + bar_w * 0.42, base_y), 4, fill=CHARCOAL)
        if h_after > 1:
            rrect(draw, (x + bar_w * 0.5, base_y - h_after, x + bar_w * 0.92, base_y), 4, fill=LIME)
    draw.line((s(chart_x - 10), s(base_y + 1), s(chart_x + 4 * 62 + bar_w + 4), s(base_y + 1)), fill=BORDER, width=s(2))

    # --- Bouton « nettoyer » (icône de balai étincelant, sans texte).
    click = t - T_CLICK
    pressed = 0.0 if click < 0 else max(0.0, 1 - click / 0.04)
    done = ease(phase(t, (T_FIX[1], T_FIX[1] + 0.05)))
    bx0, by0, bx1, by1 = BUTTON
    by0 += dy
    by1 += dy
    inset = 3 * pressed
    fill = mix(LIME, (163, 214, 83), 0.5 + 0.5 * done)
    rrect(draw, (bx0 + inset, by0 + inset, bx1 - inset, by1 - inset), 14, fill=fill, outline=(110, 165, 43), width=s(1.5))
    mid_x, mid_y = (bx0 + bx1) / 2, (by0 + by1) / 2
    if done > 0.05:
        check_mark(draw, mid_x, mid_y, 22, (18, 32, 10), progress=done, width=3.4)
    else:
        # Triangle « lancer », qui pulse pendant le traitement.
        busy = 0 <= click < (T_FIX[1] - T_CLICK)
        size = 10 * (1 + (0.12 * math.sin(click * 60) if busy else 0))
        draw.polygon(
            [(s(mid_x - size * 0.7), s(mid_y - size)), (s(mid_x - size * 0.7), s(mid_y + size)),
             (s(mid_x + size), s(mid_y))],
            fill=(18, 32, 10),
        )
    # Onde du clic.
    if 0 <= click < 0.06:
        k = click / 0.06
        r = 20 + 70 * k
        draw.ellipse((s(mid_x - r), s(mid_y - r), s(mid_x + r), s(mid_y + r)),
                     outline=mix(CARD, LIME, 1 - k), width=s(3))


def draw_cursor(draw: ImageDraw.ImageDraw, t: float) -> None:
    """Pointeur de souris : entre, clique sur le bouton, puis repart."""
    move_in = ease(phase(t, T_CURSOR))
    move_out = ease(phase(t, (0.26, 0.36)))
    if move_in <= 0 or move_out >= 1:
        return
    target = ((BUTTON[0] + BUTTON[2]) / 2 + 30, (BUTTON[1] + BUTTON[3]) / 2 + 6)
    start = (W - 120, H + 40)
    leave = (W + 60, H - 80)
    x = start[0] + (target[0] - start[0]) * move_in + (leave[0] - target[0]) * move_out
    y = start[1] + (target[1] - start[1]) * move_in + (leave[1] - target[1]) * move_out
    press = 0.9 if abs(t - T_CLICK) < 0.015 else 1.0
    pts = [(0, 0), (0, 26), (7, 20), (12, 31), (17, 29), (12, 18), (21, 18)]
    poly = [(s(x + px * press), s(y + py * press)) for px, py in pts]
    draw.polygon([(px + s(2), py + s(3)) for px, py in poly], fill=(200, 204, 194))
    draw.polygon(poly, fill=INK, outline=CARD)
    draw.line(poly + [poly[0]], fill=CARD, width=s(2))


def frame_image(t: float) -> Image.Image:
    image = Image.new("RGB", (W * SS, H * SS), BG)
    draw = ImageDraw.Draw(image)
    draw_background(draw)
    draw_table(draw, t)
    draw_panel(draw, image, t)
    draw_cursor(draw, t)
    image = image.resize((W, H), Image.LANCZOS)

    # Boucle sans couture : fondu vers l'état initial (fond seul) en fin de
    # boucle, symétrique de l'apparition du début.
    fade = phase(t, T_FADE_OUT)
    if fade > 0:
        start = frame_image.base if hasattr(frame_image, "base") else None
        if start is None:
            base = Image.new("RGB", (W * SS, H * SS), BG)
            draw_background(ImageDraw.Draw(base))
            start = frame_image.base = base.resize((W, H), Image.LANCZOS)
        image = Image.blend(image, start, ease(fade))
    return image


def render_frame(t: float) -> bytes:
    return frame_image(t).tobytes()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preview", type=int, default=0, help="nombre d'images PNG de contrôle")
    args = parser.parse_args()

    if args.preview:
        PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
        for index in range(args.preview):
            t = index / args.preview
            frame_image(t).save(PREVIEW_DIR / f"demo_{index:02d}.png")
        print(f"{args.preview} images dans {PREVIEW_DIR.relative_to(ROOT)}")
        return

    for name, codec in (("demo.webm", WEBM_CODEC), ("demo.mp4", MP4_CODEC)):
        path = encode_frames(OUT_DIR / name, codec, render_frame, FRAME_COUNT, (W, H), FPS)
        report(name.split(".")[1], path, ROOT)
    POSTER.parent.mkdir(parents=True, exist_ok=True)
    # Affiche : l'état final (tableau propre, score élevé) résume la démo.
    frame_image(0.88).save(POSTER, "JPEG", quality=84, optimize=True, progressive=True)
    report("poster", POSTER, ROOT)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    main()
