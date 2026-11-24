#!/usr/bin/env python3
"""Add missing F.CrtYd outlines to the copied third-party footprints."""
from __future__ import annotations

import re
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "lib" / "rp2040_midi_bridge.pretty"

COURTYARDS = {
    "USB_A_Neltron_5075AR-04-WH.kicad_mod": (-8.22, -6.08, 8.22, 3.42),
    "SW_SPDT_NKK_115643_Slide.kicad_mod": (-5.30, -3.45, 5.30, 3.45),
    "SW_TACT_Akizuki_DTS63.kicad_mod": (-4.50, -3.60, 4.50, 3.60),
}


def add_rect(path: Path, box: tuple[float, float, float, float]) -> bool:
    text = path.read_text(encoding="utf-8")
    if "F.CrtYd" in text:
        return False
    x0, y0, x1, y1 = box
    rect = (
        f'\t(fp_rect\n'
        f'\t\t(start {x0} {y0})\n'
        f'\t\t(end {x1} {y1})\n'
        f'\t\t(stroke\n\t\t\t(width 0.05)\n\t\t\t(type solid)\n\t\t)\n'
        f'\t\t(fill none)\n'
        f'\t\t(layer "F.CrtYd")\n'
        f'\t)\n'
    )
    idx = text.rstrip().rfind("\n)")
    text = text[:idx + 1] + rect + text[idx + 1:]
    path.write_text(text, encoding="utf-8")
    return True


def main() -> None:
    for name, box in COURTYARDS.items():
        p = LIB / name
        print(name, "added" if add_rect(p, box) else "already has courtyard")


if __name__ == "__main__":
    main()
