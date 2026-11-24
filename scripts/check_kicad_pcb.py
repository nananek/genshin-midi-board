#!/usr/bin/env python3
"""Check the KiCad PCB against the JLCPCB constraints from the design PR.

This is a text-level audit, not a replacement for kicad-cli DRC.  It catches
the mistakes that cost money at JLCPCB: 0.15 mm drills, via-in-pad, plugged
vias, blind/buried vias, and a board that is not 62.0 x 35.0 mm.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PCB = ROOT / "hardware" / "rp2040_frisk" / "rp2040_frisk.kicad_pcb"


def blocks(text: str, keyword: str) -> list[str]:
    """Return balanced S-expression blocks starting with (keyword ...)."""
    result = []
    start = 0
    needle = f"({keyword}"
    while True:
        i = text.find(needle, start)
        if i < 0:
            return result
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    result.append(text[i:j + 1])
                    start = j + 1
                    break
        else:
            return result


def fnum(pattern: str, block: str) -> float | None:
    m = re.search(pattern, block)
    return float(m.group(1)) if m else None


def main() -> int:
    if not PCB.exists():
        print(f"SKIP {PCB.relative_to(ROOT)} does not exist yet")
        return 0

    text = PCB.read_text(encoding="utf-8")
    failures: list[str] = []
    checks = 0

    # Board size from the Edge.Cuts bounding box.
    xs: list[float] = []
    ys: list[float] = []
    for block in blocks(text, "gr_line"):
        if 'Edge.Cuts' not in block:
            continue
        for m in re.finditer(r"\(start ([-\d.]+) ([-\d.]+)\)", block):
            xs.append(float(m.group(1)))
            ys.append(float(m.group(2)))
        for m in re.finditer(r"\(end ([-\d.]+) ([-\d.]+)\)", block):
            xs.append(float(m.group(1)))
            ys.append(float(m.group(2)))
    for block in blocks(text, "gr_rect"):
        if 'Edge.Cuts' not in block:
            continue
        for m in re.finditer(r"\((start|end) ([-\d.]+) ([-\d.]+)\)", block):
            xs.append(float(m.group(2)))
            ys.append(float(m.group(3)))
    if xs and ys:
        checks += 1
        w, h = max(xs) - min(xs), max(ys) - min(ys)
        if abs(w - 62.0) > 0.05 or abs(h - 35.0) > 0.05:
            failures.append(f"board outline is {w:.2f} x {h:.2f} mm, expected 62.0 x 35.0")
    else:
        failures.append("no Edge.Cuts outline found")

    # Copper layer count.
    copper = re.findall(r'\((?:\d+) "(F\.Cu|In\d+\.Cu|B\.Cu)"', text)
    checks += 1
    if len(copper) != 4 or "In1.Cu" not in copper or "In2.Cu" not in copper:
        failures.append(f"expected F.Cu + In1.Cu + In2.Cu + B.Cu, found {copper}")

    # Vias.
    via_blocks = blocks(text, "via")
    for i, block in enumerate(via_blocks):
        checks += 1
        size = fnum(r"\(size ([-\d.]+)\)", block)
        drill = fnum(r"\(drill ([-\d.]+)\)", block)
        if (size, drill) not in ((0.5, 0.3), (0.45, 0.25)):
            failures.append(f"via {i}: size={size}, drill={drill}; "
                            "only 0.5/0.3 and 0.45/0.25 are allowed")
        if re.search(r"\((blind|micro|buried)\b", block):
            failures.append(f"via {i}: blind/buried/micro via is not allowed")
    if not via_blocks:
        failures.append("no vias found; the board is not routed yet")

    # Fabrication options.
    for word in ("plugging", "capping", "filling"):
        if re.search(rf"\({word}\s+yes\)", text):
            failures.append(f"{word} is enabled; keep the via process standard")
        checks += 1

    # Via-in-pad: any via centre inside an SMD pad bounding box.
    pad_boxes: list[tuple[float, float, float, float, str]] = []
    for block in blocks(text, "pad"):
        if '"smd"' not in block:
            continue
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)", block)
        size = re.search(r"\(size ([-\d.]+) ([-\d.]+)\)", block)
        if not at or not size:
            continue
        x, y = float(at.group(1)), float(at.group(2))
        w, h = float(size.group(1)), float(size.group(2))
        pad_boxes.append((x - w / 2, y - h / 2, w, h, block[:40]))
    for i, block in enumerate(via_blocks):
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)", block)
        if not at:
            continue
        vx, vy = float(at.group(1)), float(at.group(2))
        for px, py, pw, ph, label in pad_boxes:
            if px + 0.01 < vx < px + pw - 0.01 and py + 0.01 < vy < py + ph - 0.01:
                failures.append(f"via {i} at ({vx}, {vy}) is inside SMD pad {label}")
                break

    print(f"{checks} KiCad PCB checks, {len(failures)} failed")
    for failure in failures:
        print(f"FAIL {failure}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
