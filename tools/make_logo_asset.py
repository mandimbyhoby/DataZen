"""Derive optimised, transparent-background logo assets from the source PNG.

Source: design/logo-source.png (1536x1024, white bg)
Outputs:
  static/img/logo-datazen.png       mark + wordmark, alpha, light theme
  static/img/logo-datazen-dark.png  same artwork, lifted for dark backgrounds
"""
import numpy as np
from PIL import Image

SRC = "design/logo-source.png"
OUT = "static/img/logo-datazen.png"
OUT_DARK = "static/img/logo-datazen-dark.png"

# Content bbox of the mark + wordmark. The tagline sits under the wordmark
# (source x >= 540, y >= 530) and is illegible at navbar size, so it is masked
# out. TAGLINE is expressed in crop coordinates.
BOX = (110, 286, 1422, 678)
TAGLINE = (540 - BOX[0], 530 - BOX[1])

im = Image.open(SRC).convert("RGB").crop(BOX)
a = np.asarray(im).astype(np.float64)

# The artwork sits on a flat white background: recover alpha + un-premultiply.
alpha = 1.0 - a.min(axis=2) / 255.0
safe = np.maximum(alpha, 1e-6)[..., None]
ink = np.clip((a - 255.0 * (1.0 - safe)) / safe, 0, 255)

yy, xx = np.mgrid[0:alpha.shape[0], 0:alpha.shape[1]]
alpha[(xx >= TAGLINE[0]) & (yy >= TAGLINE[1])] = 0.0

rgba = np.dstack([ink, alpha * 255.0]).round().astype(np.uint8)
out = Image.fromarray(rgba, "RGBA")

# Downscale to ~2x the largest on-screen size (footer) to keep the file light.
target_w = 600
out = out.resize((target_w, round(out.height * target_w / out.width)), Image.LANCZOS)
out.save(OUT, optimize=True)

# Dark theme: the wordmark is a very dark navy that disappears on the dark
# navbar. Lift the value channel while keeping hue and saturation, so the navy
# becomes a bright blue and the teal accent stays recognisable.
hsv = out.convert("RGB").convert("HSV")
h, s, v = hsv.split()
v = v.point(lambda p: round(255 - 0.55 * p))
dark = Image.merge("HSV", (h, s, v)).convert("RGB")
dark = dark.convert("RGBA")
dark.putalpha(out.getchannel("A"))
dark.save(OUT_DARK, optimize=True)

print("source", SRC)
print("crop", BOX, "->", im.size)
print("saved", OUT, out.size)
print("saved", OUT_DARK, dark.size)

