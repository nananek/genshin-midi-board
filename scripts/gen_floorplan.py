#!/usr/bin/env python3
"""Generate a placement / keep-out study SVG from design.yaml.

The drawing is deliberately not a fabrication drawing.  It exists so that the
connector spacing, the switch locations, and the large keep-outs can be checked
before schematic capture.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "hardware" / "rp2040_frisk" / "design.yaml"
OUT = ROOT / "hardware" / "rp2040_frisk" / "floorplan.svg"

SCALE = 12.0
MARGIN = 70.0


def main() -> None:
    data = yaml.safe_load(DESIGN.read_text(encoding="utf-8"))
    board = data["board"]
    W, H = float(board["width_mm"]), float(board["height_mm"])
    chamfer = float(board["chamfer_mm"])

    width = W * SCALE + 2 * MARGIN
    height = H * SCALE + 2 * MARGIN

    def X(x: float) -> float:
        return MARGIN + x * SCALE

    def Y(y: float) -> float:
        return MARGIN + y * SCALE

    parts: list[str] = []

    parts.append('<?xml version="1.0" encoding="UTF-8"?>')
    parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">')
    parts.append('<rect width="100%" height="100%" fill="#ffffff"/>')
    parts.append('<style>text{font-family:\'Noto Sans JP\',\'DejaVu Sans\',sans-serif;fill:#1a1a1a} .small{font-size:9px} .label{font-size:10px} .title{font-size:16px;font-weight:600} .dim{font-size:9px;fill:#b3261e}</style>')

    # board
    points = [
        (chamfer, 0), (W - chamfer, 0),
        (W, chamfer), (W, H - chamfer),
        (W - chamfer, H), (chamfer, H),
        (0, H - chamfer), (0, chamfer),
    ]
    path = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in points)
    parts.append(f'<polygon points="{path}" fill="#f7f5ef" stroke="#1a1a1a" stroke-width="1.4"/>')

    # 5 mm grid
    for x in range(5, int(W), 5):
        parts.append(f'<line x1="{X(x):.1f}" y1="{Y(0):.1f}" x2="{X(x):.1f}" y2="{Y(H):.1f}" stroke="#d9d4c7" stroke-width="0.4"/>')
    for y in range(5, int(H), 5):
        parts.append(f'<line x1="{X(0):.1f}" y1="{Y(y):.1f}" x2="{X(W):.1f}" y2="{Y(y):.1f}" stroke="#d9d4c7" stroke-width="0.4"/>')

    def draw_rect(x: float, y: float, w: float, h: float, fill: str, stroke: str, label: str, sub: str = "") -> None:
        parts.append(f'<rect x="{X(x):.1f}" y="{Y(y):.1f}" width="{w * SCALE:.1f}" height="{h * SCALE:.1f}" rx="1" fill="{fill}" stroke="{stroke}" stroke-width="0.8"/>')
        cx, cy = X(x + w / 2), Y(y + h / 2)
        parts.append(f'<text x="{cx:.1f}" y="{cy - 2:.1f}" text-anchor="middle" class="label">{label}</text>')
        if sub:
            parts.append(f'<text x="{cx:.1f}" y="{cy + 10:.1f}" text-anchor="middle" class="small">{sub}</text>')

    # connectors
    conn_labels = {
        "J1": ("J1 USB-C", "PC / NKRO HID"),
        "J3": ("J3 USB-C", "iPad / USB-MIDI"),
        "J2": ("J2 USB-A", "microKEY2"),
    }
    for entry in data["connectors"]:
        x, y, w, h = (float(v) for v in entry["courtyard"])
        label, sub = conn_labels[entry["ref"]]
        draw_rect(x, y, w, h, "#dbe7f5", "#235789", label, sub)
        # mouth arrow
        if entry["mouth"] == "up":
            parts.append(f'<path d="M {X(x + w / 2 - 1):.1f} {Y(1.0):.1f} L {X(x + w / 2):.1f} {Y(-1.0):.1f} L {X(x + w / 2 + 1):.1f} {Y(1.0):.1f}" fill="none" stroke="#235789" stroke-width="1.2"/>')
        else:
            parts.append(f'<path d="M {X(x + w / 2 - 1):.1f} {Y(H - 1.0):.1f} L {X(x + w / 2):.1f} {Y(H + 1.0):.1f} L {X(x + w / 2 + 1):.1f} {Y(H - 1.0):.1f}" fill="none" stroke="#235789" stroke-width="1.2"/>')

    # placements (centres)
    short_values = {
        "RP2040": "RP2040",
        "W25Q128JVSIQ": "W25Q128",
        "CH345T": "CH345T",
        "AP2112K-3.3": "AP2112",
        "TPS2553DBVR": "TPS2553",
        "USBLC6-2SC6": "USBLC6",
        "12MHz": "12MHz",
        "BAT54WS": "BAT54",
        "status LED": "LED",
    }
    for entry in data["placements"]:
        x = float(entry["x_mm"]) - float(entry["w_mm"]) / 2
        y = float(entry["y_mm"]) - float(entry["h_mm"]) / 2
        draw_rect(x, y, float(entry["w_mm"]), float(entry["h_mm"]), "#e2efdf", "#3f6b3a",
                  entry["ref"], short_values.get(entry["value"], entry["value"]))

    # switches
    short_switches = {
        "SW1": "mute",
        "SW2": "lyre",
        "SW3": "spare",
        "SW4": "USB-A PWR",
        "SW6": "MIDI RESET",
    }
    for entry in data["switches"]:
        x, y, w, h = (float(v) for v in entry["body"])
        draw_rect(x, y, w, h, "#f7e3cd", "#9a5b13", entry["ref"], short_switches.get(entry["ref"], entry["function"]))
        # actuator hint
        if entry["type"] == "slide":
            if entry["rotation_deg"] == 90:
                x1, y1 = X(x), Y(y + h / 2)
                x2, y2 = X(x - 2.0), Y(y + h / 2)
            elif entry["rotation_deg"] == 270:
                x1, y1 = X(x + w), Y(y + h / 2)
                x2, y2 = X(x + w + 2.0), Y(y + h / 2)
            else:
                x1, y1 = X(x + w / 2), Y(y + h)
                x2, y2 = X(x + w / 2), Y(y + h + 2.0)
            parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#9a5b13" stroke-width="1.6"/>')
            parts.append(f'<circle cx="{x2:.1f}" cy="{y2:.1f}" r="1.5" fill="#9a5b13"/>')

    # connector pitch dimension
    j1 = next(e for e in data["connectors"] if e["ref"] == "J1")
    j3 = next(e for e in data["connectors"] if e["ref"] == "J3")
    x1 = X(float(j1["x_mm"]))
    x2 = X(float(j3["x_mm"]))
    ydim = Y(10.5)
    parts.append(f'<line x1="{x1:.1f}" y1="{ydim:.1f}" x2="{x2:.1f}" y2="{ydim:.1f}" stroke="#b3261e" stroke-width="0.8"/>')
    parts.append(f'<line x1="{x1:.1f}" y1="{ydim - 4:.1f}" x2="{x1:.1f}" y2="{ydim + 4:.1f}" stroke="#b3261e" stroke-width="0.8"/>')
    parts.append(f'<line x1="{x2:.1f}" y1="{ydim - 4:.1f}" x2="{x2:.1f}" y2="{ydim + 4:.1f}" stroke="#b3261e" stroke-width="0.8"/>')
    parts.append(f'<text x="{(x1 + x2) / 2:.1f}" y="{ydim - 6:.1f}" text-anchor="middle" class="dim">USB-C pitch 29.0 mm</text>')

    # overall dimensions
    parts.append(f'<line x1="{X(0):.1f}" y1="{Y(H) + 22:.1f}" x2="{X(W):.1f}" y2="{Y(H) + 22:.1f}" stroke="#b3261e" stroke-width="0.8"/>')
    parts.append(f'<line x1="{X(0):.1f}" y1="{Y(H) + 17:.1f}" x2="{X(0):.1f}" y2="{Y(H) + 27:.1f}" stroke="#b3261e" stroke-width="0.8"/>')
    parts.append(f'<line x1="{X(W):.1f}" y1="{Y(H) + 17:.1f}" x2="{X(W):.1f}" y2="{Y(H) + 27:.1f}" stroke="#b3261e" stroke-width="0.8"/>')
    parts.append(f'<text x="{X(W / 2):.1f}" y="{Y(H) + 36:.1f}" text-anchor="middle" class="dim">57.6 mm</text>')
    parts.append(f'<line x1="{X(W) + 22:.1f}" y1="{Y(0):.1f}" x2="{X(W) + 22:.1f}" y2="{Y(H):.1f}" stroke="#b3261e" stroke-width="0.8"/>')
    parts.append(f'<line x1="{X(W) + 17:.1f}" y1="{Y(0):.1f}" x2="{X(W) + 27:.1f}" y2="{Y(0):.1f}" stroke="#b3261e" stroke-width="0.8"/>')
    parts.append(f'<line x1="{X(W) + 17:.1f}" y1="{Y(H):.1f}" x2="{X(W) + 27:.1f}" y2="{Y(H):.1f}" stroke="#b3261e" stroke-width="0.8"/>')
    parts.append(f'<text x="{X(W) + 36:.1f}" y="{Y(H / 2):.1f}" text-anchor="middle" class="dim" transform="rotate(90 {X(W) + 36:.1f} {Y(H / 2):.1f})">31.4 mm</text>')

    # title and notes
    parts.append(f'<text x="{MARGIN}" y="28" class="title">RP2040 Frisk MIDI bridge — placement / keep-out study</text>')
    parts.append(f'<text x="{MARGIN}" y="44" class="small">57.6 × 31.4 mm, 4 layers, 2 mm punch cuts. Not a fabrication drawing.</text>')
    parts.append(f'<text x="{MARGIN}" y="{height - 26:.1f}" class="small">Blue: connector keep-out. Green: IC. Orange: switch. Red: dimension. Top edge: J1/J3 USB-C (29.0 mm pitch). Bottom edge: J2 USB-A.</text>')
    parts.append('</svg>')

    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
