#!/usr/bin/env python3
"""Generate a 1:1 drilling template for the Muji PP small-case M."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DESIGN = yaml.safe_load(
    (ROOT / "hardware" / "rp2040_midi_bridge" / "design.yaml").read_text(encoding="utf-8")
)
OUT_SVG = ROOT / "docs" / "case_muji_m_template.svg"
OUT_PDF = ROOT / "docs" / "case_muji_m_template.pdf"

CASE_W = 60.0
CASE_H = 46.0
OFF = 1.0  # board offset inside the case
BOARD_W = float(DESIGN["board"]["width_mm"])
BOARD_H = float(DESIGN["board"]["height_mm"])
CHAMFER = float(DESIGN["board"]["chamfer_mm"])

parts: list[str] = []


def rect(x, y, w, h, stroke="#000", dash="", width=0.25, fill="none"):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(
        f'<rect x="{x:.3f}" y="{y:.3f}" width="{w:.3f}" height="{h:.3f}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{width}"{d}/>'
    )


def line(x1, y1, x2, y2, stroke="#000", width=0.2, dash=""):
    d = f' stroke-dasharray="{dash}"' if dash else ""
    parts.append(
        f'<line x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" '
        f'stroke="{stroke}" stroke-width="{width}"{d}/>'
    )


def text(x, y, s, size=1.8, anchor="middle", color="#000"):
    parts.append(
        f'<text x="{x:.3f}" y="{y:.3f}" font-family="sans-serif" font-size="{size}" '
        f'text-anchor="{anchor}" fill="{color}">{s}</text>'
    )


def circle(cx, cy, r, stroke="#c00", width=0.3):
    parts.append(
        f'<circle cx="{cx:.3f}" cy="{cy:.3f}" r="{r:.3f}" fill="none" '
        f'stroke="{stroke}" stroke-width="{width}"/>'
    )


# Board outline with 2 mm chamfers, offset by OFF.
x0, y0 = OFF, OFF
x1, y1 = OFF + BOARD_W, OFF + BOARD_H
c = CHAMFER
points = [
    (x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c),
    (x1 - c, y1), (x0 + c, y1), (x0, y1 - c), (x0, y0 + c),
]
parts.append(
    '<polygon points="' + " ".join(f"{x:.3f},{y:.3f}" for x, y in points)
    + '" fill="none" stroke="#000" stroke-width="0.35"/>'
)
rect(0, 0, CASE_W, CASE_H, stroke="#888", dash="1.2 0.8", width=0.25)
text(CASE_W / 2, 65.0, "MUJI PP small case M  inner 60 x 46 mm", size=2.0)
text(CASE_W / 2, 68.0, "board 58 x 44 mm, 1 mm margin", size=1.6)

# Board name / orientation marker.
text(CASE_W / 2, 36.0, "USB-A (J2) side", size=1.8)
text(CASE_W / 2, 10.5, "USB-C (J1/J3) side", size=1.8)

# Connectors and switches.
for c in DESIGN["connectors"]:
    x, y = c["x_mm"] + OFF, c["y_mm"] + OFF
    ref = c["ref"]
    if ref in ("J1", "J3"):
        # Top-wall opening: 10 x 4.5 mm, projected into the case.
        rect(x - 5.0, 0, 10.0, 4.5, stroke="#c00", dash="1.0 0.6")
        text(x, 3.4, ref, size=1.6, color="#c00")
    elif ref == "J2":
        rect(x - 8.25, CASE_H - 8.0, 16.5, 8.0, stroke="#c00", dash="1.0 0.6")
        text(x, CASE_H - 1.2, "J2", size=1.6, color="#c00")

for s in DESIGN["switches"]:
    ref = s["ref"]
    x, y = s["x_mm"] + OFF, s["y_mm"] + OFF
    if ref in ("SW1", "SW2"):
        rect(0, y - 3.5, 3.6, 7.0, stroke="#c00", dash="1.0 0.6")
        text(2.0, y + 0.6, ref, size=1.4, color="#c00", anchor="start")
    elif ref == "SW3":
        rect(CASE_W - 3.6, y - 3.5, 3.6, 7.0, stroke="#c00", dash="1.0 0.6")
        text(CASE_W - 2.0, y + 0.6, ref, size=1.4, color="#c00", anchor="end")
    elif ref == "SW4":
        rect(x - 3.5, CASE_H - 3.6, 7.0, 3.6, stroke="#c00", dash="1.0 0.6")
        text(x, CASE_H - 4.2, ref, size=1.4, color="#c00")
    elif ref in ("SW5", "SW6", "SW7"):
        r = 2.5 if ref == "SW5" else 1.5
        circle(x, y, r)
        text(x, y - r - 0.5, ref, size=1.4, color="#c00")

# LED1 is a placement, not a switch.
for p in DESIGN["placements"]:
    if p["ref"] == "LED1":
        circle(p["x_mm"] + OFF, p["y_mm"] + OFF, 1.5)
        text(p["x_mm"] + OFF, p["y_mm"] + OFF - 2.0, "LED1", size=1.4, color="#c00")

# Scale bar and notes.
line(2.0, CASE_H + 4.0, 52.0, CASE_H + 4.0, width=0.5)
line(2.0, CASE_H + 3.5, 2.0, CASE_H + 4.5, width=0.5)
line(52.0, CASE_H + 3.5, 52.0, CASE_H + 4.5, width=0.5)
text(27.0, CASE_H + 7.0, "50 mm", size=2.0)
text(2.0, CASE_H + 11.0,
     "Print at 1:1. Dashed red = cut/drill. Side-wall slots are shown in projection.",
     size=1.5, anchor="start")
text(2.0, CASE_H + 14.0,
     "Heights: USB-C 1.2-5.7 mm, USB-A 1.2-9.2 mm, slide switches 1.8-5.4 mm.",
     size=1.5, anchor="start")

svg = (
    f'<svg xmlns="http://www.w3.org/2000/svg" width="{CASE_W}mm" '
    f'height="{CASE_H + 26.0}mm" viewBox="0 0 {CASE_W} {CASE_H + 26.0}">'
    '<rect width="100%" height="100%" fill="white"/>'
    + "".join(parts)
    + "</svg>\n"
)
OUT_SVG.write_text(svg, encoding="utf-8")
print(f"wrote {OUT_SVG.relative_to(ROOT)}")
