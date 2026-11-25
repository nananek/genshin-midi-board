#!/usr/bin/env python3
"""Route the last MIDI_UART_RX gap on the 0.025 mm grid.

local_repair.py closes the remaining pad connections on the 0.05 mm grid.
MIDI_UART_RX is the one net that needs the 0.025 mm grid and a 0.1 mm track to
thread between the QSPI fan-out and U2.  The first pass keeps 0.086 mm to the
QSPI_SS track, so the run is shifted 0.05 mm away from it afterwards.

Run inside the KiCad container:

    ./scripts/kicad.sh python3 hardware/rp2040_midi_bridge/scripts/finish_midi_rx.py \
        hardware/rp2040_midi_bridge/rp2040_midi_bridge.kicad_pcb \
        hardware/rp2040_midi_bridge/drc.rpt
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

PCB = Path(sys.argv[1]) if len(sys.argv) > 1 else None
RPT = Path(sys.argv[2]) if len(sys.argv) > 2 else None

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
ROOT = HERE.parent
PCB = PCB or ROOT / "rp2040_midi_bridge.kicad_pcb"
RPT = RPT or ROOT / "drc.rpt"

os.environ.setdefault("PCB_CELL", "0.025")
sys.argv = ["finish_midi_rx", str(PCB), str(RPT)]
import local_repair as LR  # noqa: E402
import pcbnew  # noqa: E402

NET = "MIDI_UART_RX"


def gap():
    if not RPT.exists():
        return None
    for block in RPT.read_text(encoding="utf-8").split("[unconnected_items]")[1:]:
        pts = []
        for m in re.finditer(r"@\(([-\d.]+) mm, ([-\d.]+) mm\): (.*)", block):
            desc = m.group(3)
            if f"[{NET}]" not in desc:
                continue
            layers = "FB" if ("Via" in desc or "PTH" in desc) else "F"
            if "on B.Cu" in desc:
                layers = "B"
            pts.append((float(m.group(1)), float(m.group(2)), layers))
            if len(pts) == 2:
                return pts
    return None


def main():
    pair = gap()
    if pair is None:
        print(f"{NET} is already connected")
        return 0

    b = LR.Board(PCB)
    b.geom.pop(NET, None)
    r = b.build()
    if not r.connect(NET, pair[0], pair[1], 0.1, 0.1, via_cost=5,
                     max_expand=20000000, via_radius=0.225,
                     relax_corner=True):
        print(f"{NET}: no path on the {LR.CELL if hasattr(LR, 'CELL') else 0.025} mm grid")
        return 1
    b.geom[NET] = list(r.net_geom.get(NET, []))
    b.save(PCB)

    # Keep 0.1 mm to the QSPI_SS run.  The first shift clears three marginal
    # spots, the second clears the via at (29.05, 11.55).
    board = pcbnew.LoadBoard(str(PCB))
    for (x0, x1, y0, y1, dx, dy) in ((26.5, 30.5, 11.3, 13.4, 0.0, -0.05),
                                     (29.1, 29.7, 11.45, 12.05, 0.05, -0.05)):
        for t in board.GetTracks():
            if t.GetNetname() != NET or isinstance(t, pcbnew.PCB_VIA):
                continue
            for get, set_ in ((t.GetStart, t.SetStart), (t.GetEnd, t.SetEnd)):
                p = get()
                x, y = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
                if x0 <= x <= x1 and y0 <= y <= y1:
                    set_(pcbnew.VECTOR2I(pcbnew.FromMM(x + dx),
                                         pcbnew.FromMM(y + dy)))
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(PCB), board)
    print(f"{NET}: routed on the 0.025 mm grid")
    return 0


if __name__ == "__main__":
    sys.exit(main())
