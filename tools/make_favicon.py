"""Derive the favicon assets from the brand mark.

Source: static/img/logo-datazen.png (600x179, mark + wordmark, transparent)
Outputs:
  static/img/favicon.ico        multi-size 16/32/48/64, transparent
  static/img/favicon-180.png    apple-touch-icon, opaque white background

The mark is the leftmost glyph of the logo, isolated by scanning the alpha
channel for the first column run. It is padded to a square canvas so the
browser does not squash it.
"""
import numpy as np
from PIL import Image

SRC = "static/img/logo-datazen.png"
OUT_ICO = "static/img/favicon.ico"
OUT_APPLE = "static/img/favicon-180.png"

ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64)]
APPLE_SIZE = 180
APPLE_MARK_RATIO = 0.72
ALPHA_FLOOR = 12


def _first_column_run(alpha):
    """Return the (start, end) column range of the leftmost opaque glyph."""
    occupied = (alpha > ALPHA_FLOOR).sum(axis=0) > 0
    start = None
    for index, filled in enumerate(occupied):
        if filled and start is None:
            start = index
        elif not filled and start is not None:
            return start, index - 1
    if start is not None:
        return start, len(occupied) - 1
    raise ValueError("aucun pixel opaque trouvé dans le logo source")


def _square(image):
    """Centre the artwork on a transparent square canvas."""
    side = max(image.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
    return canvas


logo = Image.open(SRC).convert("RGBA")
alpha = np.asarray(logo)[..., 3]

left, right = _first_column_run(alpha)
band = alpha[:, left:right + 1]
rows = np.where((band > ALPHA_FLOOR).sum(axis=1) > 0)[0]
mark = logo.crop((left, int(rows[0]), right + 1, int(rows[-1]) + 1))
print("mark", mark.size, "at columns", (left, right))

square = _square(mark)
square.resize((256, 256), Image.LANCZOS).save(OUT_ICO, format="ICO", sizes=ICO_SIZES)
print("saved", OUT_ICO, ICO_SIZES)

# iOS composites transparency on black, so the touch icon gets a white plate.
plate = Image.new("RGBA", (APPLE_SIZE, APPLE_SIZE), (255, 255, 255, 255))
inner = round(APPLE_SIZE * APPLE_MARK_RATIO)
scaled = square.resize((inner, inner), Image.LANCZOS)
offset = (APPLE_SIZE - inner) // 2
plate.paste(scaled, (offset, offset), scaled)
plate.convert("RGB").save(OUT_APPLE, optimize=True)
print("saved", OUT_APPLE, plate.size)
