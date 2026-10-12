"""Outils partagés par les générateurs de vidéos décoratives de DataZen.

Aucun ffmpeg système n'est requis : le binaire est fourni par le paquet
`imageio-ffmpeg`. Les images sont produites en Python puis poussées sur
l'entrée standard de ffmpeg, ce qui évite d'écrire 240 PNG intermédiaires.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageFilter

FrameRenderer = Callable[[float], bytes]

# Réglages d'encodage communs : légers, sans audio, prêts pour le web.
MP4_CODEC = (
    "-c:v",
    "libx264",
    "-preset",
    "slow",
    "-crf",
    "27",
    "-pix_fmt",
    "yuv420p",
    "-profile:v",
    "high",
    "-level",
    "4.0",
)
WEBM_CODEC = (
    "-c:v",
    "libvpx-vp9",
    "-crf",
    "36",
    "-b:v",
    "0",
    "-row-mt",
    "1",
    "-pix_fmt",
    "yuv420p",
)


def blur(array: np.ndarray, radius: float) -> np.ndarray:
    """Flou gaussien rapide sur une nappe mono-canal normalisée dans [0, 1]."""
    image = Image.fromarray((np.clip(array, 0.0, 1.0) * 255.0).astype(np.uint8), mode="L")
    image = image.filter(ImageFilter.GaussianBlur(radius))
    return np.asarray(image, dtype=np.float32) / 255.0


def blur_rgb(array: np.ndarray, radius: float) -> np.ndarray:
    """Flou gaussien sur une nappe RGB (H, W, 3) de valeurs 0-255."""
    channels = [blur(array[..., index] / 255.0, radius) for index in range(array.shape[-1])]
    return np.stack(channels, axis=-1) * 255.0


def encode_frames(
    target: Path,
    codec: tuple[str, ...],
    render: FrameRenderer,
    frame_count: int,
    size: tuple[int, int],
    fps: int,
) -> Path:
    """Encode ``frame_count`` images RGB24 produites par ``render``.

    ``render`` reçoit une position temporelle dans [0, 1) et renvoie les octets
    bruts d'une image RGB.
    """
    import imageio_ffmpeg

    width, height = size
    target.parent.mkdir(parents=True, exist_ok=True)
    command = [
        imageio_ffmpeg.get_ffmpeg_exe(),
        "-y",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        *codec,
        "-movflags",
        "+faststart",
        "-an",
        str(target),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    for index in range(frame_count):
        process.stdin.write(render(index / frame_count))
    process.stdin.close()
    if process.wait() != 0:
        raise SystemExit(f"échec de l'encodage {target.name}")
    return target


def report(label: str, path: Path, root: Path) -> None:
    """Affiche la taille du fichier produit, en kilo-octets."""
    print(f"{label:7s}: {path.relative_to(root)} ({path.stat().st_size / 1024:.0f} Ko)")
