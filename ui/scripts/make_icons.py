"""Draw the app icons (home screen, install prompt, favicon) as PNGs in ui/public.

The navbar's trend mark: an orange arrow in a tinted rounded square on the app background, kept
inside the central 70% so Android's "maskable" crop never cuts it. Pure numpy + zlib, no
image library needed; run it again only if the design changes:

    python ui/scripts/make_icons.py
"""

import struct
import zlib
from pathlib import Path

import numpy as np

BG = np.array([0x0b, 0x0f, 0x1a], float)
ORANGE = np.array([0xff, 0x99, 0x33], float)
OUT = Path(__file__).resolve().parents[1] / "public"
SS = 4                                          # supersampling for smooth edges


def _segment_distance(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy), 0, 1)
    return np.hypot(px - (ax + t * dx), py - (ay + t * dy))


def draw(size: int) -> np.ndarray:
    n = size * SS
    y, x = np.mgrid[0:n, 0:n].astype(float) + 0.5
    x, y = x / SS, y / SS                       # back to icon pixels
    img = np.tile(BG, (n, n, 1))

    box = size * 0.70
    x0 = y0 = (size - box) / 2
    r = box * 0.24
    cx, cy = np.clip(x, x0 + r, x0 + box - r), np.clip(y, y0 + r, y0 + box - r)
    d_box = np.hypot(x - cx, y - cy) - r        # < 0 inside the rounded square
    border = max(2.0, size / 64)
    inside = d_box < 0
    img[inside] = BG * 0.85 + ORANGE * 0.15     # tinted fill, like the navbar badge
    ring = (d_box < 0) & (d_box > -border)
    img[ring] = BG * 0.55 + ORANGE * 0.45

    # lucide TrendingUp on a 24-unit grid, scaled into the box
    scale = box * 0.6 / 24
    ox, oy = size / 2 - 12 * scale, size / 2 - 12 * scale
    pts = lambda seq: [(ox + a * scale, oy + b * scale) for a, b in seq]
    lines = [pts([(22, 7), (13.5, 15.5), (8.5, 10.5), (2, 17)]), pts([(16, 7), (22, 7), (22, 13)])]
    half = 2.4 * scale / 2
    d = np.full(x.shape, np.inf)
    for line in lines:
        for (ax, ay), (bx, by) in zip(line, line[1:]):
            d = np.minimum(d, _segment_distance(x, y, ax, ay, bx, by))
    img[d <= half] = ORANGE
    return img.reshape(size, SS, size, SS, 3).mean(axis=(1, 3)).round().clip(0, 255).astype(np.uint8)


def write_png(path: Path, rgb: np.ndarray) -> None:
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(h))
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) \
        + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    path.write_bytes(png)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in [("icon-512.png", 512), ("icon-192.png", 192), ("apple-touch-icon.png", 180), ("favicon-32.png", 32)]:
        write_png(OUT / name, draw(size))
        print("wrote", name)
