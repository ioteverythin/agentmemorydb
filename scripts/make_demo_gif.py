#!/usr/bin/env python3
"""Render examples/demo.py output into an animated terminal GIF.

Runs the demo, parses its ANSI colours, and draws a scrolling terminal
window frame-by-frame. Regenerate with::

    python scripts/make_demo_gif.py

Output: docs/images/demo.gif
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "images", "demo.gif")

# GitHub-dark terminal palette.
BG = (13, 17, 23)
BAR = (22, 27, 34)
DEFAULT = (201, 209, 217)
PALETTE = {
    "dim": (110, 118, 129),
    "31": (248, 81, 73),
    "32": (86, 211, 100),
    "33": (242, 204, 96),
    "34": (88, 166, 255),
    "35": (188, 140, 255),
    "36": (86, 212, 221),
    "37": (255, 255, 255),
}

FONT_SIZE = 15
PAD = 16
ROWS = 22  # visible terminal rows (viewport scrolls beyond this)

_SGR = re.compile(r"\033\[([0-9;]*)m")


def parse_ansi(line: str) -> list[tuple[str, tuple[int, int, int]]]:
    """Split a line into (text, rgb) runs from its ANSI SGR codes."""
    runs: list[tuple[str, tuple[int, int, int]]] = []
    pos = 0
    bold = dim = False
    color: str | None = None
    for m in _SGR.finditer(line):
        if m.start() > pos:
            runs.append((line[pos : m.start()], _rgb(bold, dim, color)))
        for code in (m.group(1) or "0").split(";"):
            if code in ("", "0"):
                bold = dim = False
                color = None
            elif code == "1":
                bold = True
            elif code == "2":
                dim = True
            elif code in PALETTE:
                color = code
        pos = m.end()
    if pos < len(line):
        runs.append((line[pos:], _rgb(bold, dim, color)))
    return runs


def _rgb(bold: bool, dim: bool, color: str | None) -> tuple[int, int, int]:
    if dim:
        return PALETTE["dim"]
    if color is None:
        return (255, 255, 255) if bold else DEFAULT
    return PALETTE[color]


def _clean(text: str) -> str:
    # Drop emoji / astral chars the mono font can't render (avoids tofu).
    return "".join(c for c in text if ord(c) < 0x1F000)


def main() -> None:
    raw = subprocess.run(
        [sys.executable, os.path.join(ROOT, "examples", "demo.py"), "0"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    ).stdout
    lines = [parse_ansi(_clean(ln)) for ln in raw.split("\n")]

    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", FONT_SIZE)
    cw = font.getbbox("M")[2]
    lh = FONT_SIZE + 6
    plain = [("".join(t for t, _ in run)) for run in lines]
    cols = max((len(p) for p in plain), default=40)
    width = PAD * 2 + cw * min(cols, 96)
    barh = 30
    height = barh + PAD * 2 + lh * ROWS

    def render(upto: int) -> Image.Image:
        img = Image.new("RGB", (width, height), BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, width, barh], fill=BAR)
        for i, c in enumerate(((246, 89, 84), (245, 191, 79), (98, 197, 84))):
            d.ellipse([PAD + i * 20, 10, PAD + i * 20 + 11, 21], fill=c)
        d.text((width // 2 - 60, 8), "engramdb — demo", font=font, fill=PALETTE["dim"])
        visible = lines[:upto][-ROWS:]
        y = barh + PAD
        for run in visible:
            x = PAD
            for text, rgb in run:
                d.text((x, y), text, font=font, fill=rgb)
                x += cw * len(text)
            y += lh
        # blinking cursor on the last visible line
        if visible:
            cx = PAD + cw * len(plain[min(upto, len(plain)) - 1])
            d.rectangle([cx, y - lh, cx + cw - 2, y - lh + FONT_SIZE], fill=(88, 166, 255))
        return img

    frames = [render(i) for i in range(1, len(lines) + 1)]
    frames += [frames[-1]] * 12  # hold the final frame

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    frames[0].save(
        OUT,
        save_all=True,
        append_images=frames[1:],
        duration=[110] * (len(frames) - 12) + [130] * 12,
        loop=0,
        optimize=True,
        disposal=2,
    )
    kb = os.path.getsize(OUT) // 1024
    print(f"wrote {OUT}  ({len(frames)} frames, {width}x{height}, {kb} KB)")


if __name__ == "__main__":
    main()
