"""Dessine les icônes d'onglet à partir du symbole du logo animé.

Le symbole est le même que celui de `templates/core/_logo.html` (écrin lime
arrondi, trois barres de données, étoile), dessiné ici avec Pillow en grand
format puis réduit, sans dépendre d'une image source.

Sorties :
  static/img/favicon.svg        icône vectorielle (navigateurs récents)
  static/img/favicon.ico        multi-tailles 16/32/48/64, fond transparent
  static/img/favicon-180.png    apple-touch-icon, fond blanc opaque

Usage :
    python tools/make_favicon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT_SVG = ROOT / "static/img/favicon.svg"
OUT_ICO = ROOT / "static/img/favicon.ico"
OUT_APPLE = ROOT / "static/img/favicon-180.png"

ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64)]
APPLE_SIZE = 180
APPLE_MARK_RATIO = 0.74
CANVAS = 1024  # dessin en grand format, puis réduction (anticrénelage)

LIME_LIGHT = (212, 239, 122)
LIME = (140, 198, 63)
LIME_DARK = (63, 138, 31)

SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#d4ef7a"/>
      <stop offset="0.5" stop-color="#8cc63f"/>
      <stop offset="1" stop-color="#3f8a1f"/>
    </linearGradient>
  </defs>
  <rect x="2" y="2" width="44" height="44" rx="13" fill="url(#g)"/>
  <rect x="2" y="2" width="44" height="20" rx="13" fill="#fff" opacity="0.16"/>
  <rect x="10.5" y="27" width="7" height="12" rx="3.5" fill="#fff"/>
  <rect x="20.5" y="21" width="7" height="18" rx="3.5" fill="#fff"/>
  <rect x="30.5" y="15" width="7" height="24" rx="3.5" fill="#fff"/>
  <path d="M14 6.5 Q15 11 19.5 12 Q15 13 14 17.5 Q13 13 8.5 12 Q13 11 14 6.5Z" fill="#fff"/>
</svg>
"""


def _lerp(a, b, k):
    return tuple(int(round(a[i] + (b[i] - a[i]) * k)) for i in range(3))


def draw_mark(size=CANVAS):
    """Symbole carré sur fond transparent (coordonnées du viewBox 48×48)."""
    unit = size / 48

    def box(x, y, w, h):
        return (x * unit, y * unit, (x + w) * unit, (y + h) * unit)

    # Dégradé diagonal lime clair → lime → vert foncé.
    gradient = Image.new("RGB", (size, size))
    pixels = gradient.load()
    for y in range(size):
        for x in range(size):
            k = (x + y) / (2 * (size - 1))
            pixels[x, y] = _lerp(LIME_LIGHT, LIME, k / 0.5) if k < 0.5 else _lerp(LIME, LIME_DARK, (k - 0.5) / 0.5)

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box(2, 2, 44, 44), radius=13 * unit, fill=255)
    mark = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    mark.paste(gradient, (0, 0), mask)

    # Reflet sur la moitié haute.
    gloss = Image.new("L", (size, size), 0)
    ImageDraw.Draw(gloss).rounded_rectangle(box(2, 2, 44, 20), radius=13 * unit, fill=41)
    white = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    mark = Image.composite(white, mark, Image.composite(gloss, Image.new("L", (size, size), 0), mask))
    mark.putalpha(mask)

    draw = ImageDraw.Draw(mark)
    for x, y, h in ((10.5, 27, 12), (20.5, 21, 18), (30.5, 15, 24)):
        draw.rounded_rectangle(box(x, y, 7, h), radius=3.5 * unit, fill=(255, 255, 255, 255))
    # Étoile à quatre branches (approximation polygonale des courbes du SVG).
    cx, cy, r, waist = 14 * unit, 12 * unit, 5.5 * unit, 1.3 * unit
    star = [(cx, cy - r), (cx + waist, cy - waist), (cx + r, cy), (cx + waist, cy + waist),
            (cx, cy + r), (cx - waist, cy + waist), (cx - r, cy), (cx - waist, cy - waist)]
    draw.polygon(star, fill=(255, 255, 255, 255))
    return mark


def main():
    OUT_SVG.write_text(SVG, encoding="utf-8")

    mark = draw_mark()
    icons = [mark.resize(size, Image.LANCZOS) for size in ICO_SIZES]
    icons[-1].save(OUT_ICO, format="ICO", sizes=ICO_SIZES, append_images=icons[:-1])

    apple = Image.new("RGBA", (APPLE_SIZE, APPLE_SIZE), (255, 255, 255, 255))
    inner = int(APPLE_SIZE * APPLE_MARK_RATIO)
    offset = (APPLE_SIZE - inner) // 2
    apple.alpha_composite(mark.resize((inner, inner), Image.LANCZOS), (offset, offset))
    apple.convert("RGB").save(OUT_APPLE, format="PNG", optimize=True)

    for path in (OUT_SVG, OUT_ICO, OUT_APPLE):
        print(f"{path.relative_to(ROOT)} ({path.stat().st_size / 1024:.1f} Ko)")


if __name__ == "__main__":
    main()
