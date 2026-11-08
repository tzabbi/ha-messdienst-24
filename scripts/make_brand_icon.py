#!/usr/bin/env python3
"""Erzeugt die Brand-Icons unter custom_components/messdienst24/brand/ (benötigt Pillow).

Motiv: Zählerskala mit drei Segmenten (Kaltwasser blau, Warmwasser orange,
Heizung rot), Zeiger und ein halb blauer/halb roter Wassertropfen.
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "custom_components" / "messdienst24" / "brand"
S = 2048  # supersampled canvas, downscaled for anti-aliasing

BLUE = (30, 136, 229, 255)
ORANGE = (251, 140, 0, 255)
RED = (229, 57, 53, 255)


def polar(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def draw_icon(needle_color):
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = S / 2
    outer, width = 0.47 * S, 0.12 * S
    mid = outer - width / 2

    # Gauge: 270° sweep, opening at the bottom. PIL angles: 0° = 3 o'clock, clockwise.
    gap = 16
    for start, end, color in ((135, 225, BLUE), (225, 315, ORANGE), (315, 405, RED)):
        s, e = start + gap / 2, end - gap / 2
        d.arc(
            (cx - outer, cy - outer, cx + outer, cy + outer),
            s,
            e,
            fill=color,
            width=int(width),
        )
        for ang in (s, e):  # round caps
            x, y = polar(cx, cy, mid, ang)
            d.ellipse(
                (x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=color
            )

    # Needle pointing into the red (heat) segment.
    ang = -40
    tip = polar(cx, cy, 0.33 * S, ang)
    base_w = 0.045 * S
    left = polar(cx, cy, base_w, ang - 90)
    right = polar(cx, cy, base_w, ang + 90)
    d.polygon([tip, left, right], fill=needle_color)
    hub = 0.075 * S
    d.ellipse((cx - hub, cy - hub, cx + hub, cy + hub), fill=needle_color)

    # Water drop below the hub, left half cold (blue), right half warm (red).
    dcx, dcy, r = cx, 0.80 * S, 0.095 * S
    dist = 2.0 * r
    theta = math.acos(r / dist)
    drop_mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(drop_mask)
    md.ellipse((dcx - r, dcy - r, dcx + r, dcy + r), fill=255)
    md.polygon(
        [
            (dcx, dcy - dist),
            (dcx - r * math.sin(theta), dcy - r * math.cos(theta)),
            (dcx + r * math.sin(theta), dcy - r * math.cos(theta)),
        ],
        fill=255,
    )
    halves = Image.new("RGBA", (S, S), BLUE)
    ImageDraw.Draw(halves).rectangle((dcx, 0, S, S), fill=RED)
    img.paste(halves, (0, 0), drop_mask)
    return img


def square_trimmed(img):
    l, t, r, b = img.getbbox()
    side = max(r - l, b - t)
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    out.paste(img.crop((l, t, r, b)), ((side - (r - l)) // 2, (side - (b - t)) // 2))
    return out


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for prefix, needle in (("", (55, 71, 79, 255)), ("dark_", (236, 239, 241, 255))):
        icon = square_trimmed(draw_icon(needle))
        for name, size in ((f"{prefix}icon.png", 256), (f"{prefix}icon@2x.png", 512)):
            icon.resize((size, size), Image.LANCZOS).save(OUT / name, optimize=True)
            print("geschrieben:", OUT / name)


if __name__ == "__main__":
    main()
