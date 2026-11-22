#!/usr/bin/env python3
"""Stitch isolated ground pour pockets.

After a DRC run the report lists GND pads that are not connected to the main
pour.  For each of them this script drops one 0.5/0.3 mm ground via next to
the pad (outside every pad, clear of other copper), which ties the pocket to
the B.Cu pour and to the In1 plane.  Zones are refilled afterwards.
"""

from __future__ import annotations

import re
import sys
from math import cos, hypot, pi, sin
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = ROOT / "rp2040_frisk.kicad_pcb"
RPT = ROOT / "drc.rpt"

CLEAR = 0.45        # via copper radius 0.25 + 0.2 clearance
VIA_GAP = 0.8


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
    return hypot(px - (ax + t * dx), py - (ay + t * dy))


def rect_dist(p, bb):
    x0, y0 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
    x1, y1 = pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())
    dx = max(x0 - p[0], 0.0, p[0] - x1)
    dy = max(y0 - p[1], 0.0, p[1] - y1)
    return hypot(dx, dy)


def gnd_pads(report):
    out = []
    for block in report.read_text(encoding="utf-8").split("\n\n"):
        if "[unconnected_items]" not in block:
            continue
        if "GND" not in block:
            continue
        for m in re.finditer(r"@\(([-\d.]+) mm, ([-\d.]+) mm\): Pad (\S+) \[GND\] "
                             r"of (\S+)", block):
            out.append((float(m.group(1)), float(m.group(2)), m.group(4), m.group(3)))
    return out


def main() -> int:
    board = pcbnew.LoadBoard(str(PCB))
    pads = gnd_pads(RPT)
    if not pads:
        print("no isolated GND pads")
        return 0
    tracks = []
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            pos = t.GetPosition()
            tracks.append(("via", (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y)),
                           t.GetNetname(), pcbnew.ToMM(t.GetWidth(
                               pcbnew.F_Cu)) / 2))
        else:
            tracks.append(("seg",
                           ((pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y)),
                            (pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y))),
                           t.GetNetname(), pcbnew.ToMM(t.GetWidth()) / 2))
    all_pads = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            all_pads.append((pad.GetBoundingBox(), pad.GetNetname()))
    vias = [t[1] for t in tracks if t[0] == "via"]

    added = 0
    for (x, y, ref, pin) in pads:
        placed = None
        for r in (0.85, 1.0, 1.15, 1.3, 1.5, 1.75, 2.0, 2.3, 2.6):
            for k in range(24):
                a = 2 * pi * k / 24
                cx, cy = x + r * cos(a), y + r * sin(a)
                if not (0.8 < cx < 56.8 and 0.8 < cy < 30.6):
                    continue
                ok = True
                for bb, net in all_pads:
                    if rect_dist((cx, cy), bb) < 0.45 + 0.05:
                        ok = False
                        break
                if not ok:
                    continue
                for kind, geo, net, half in tracks:
                    if net == "GND":
                        continue
                    d = (seg_dist((cx, cy), geo[0], geo[1]) if kind == "seg"
                         else hypot(cx - geo[0], cy - geo[1]))
                    if d < half + CLEAR:
                        ok = False
                        break
                if not ok:
                    continue
                if any(hypot(cx - vx, cy - vy) < VIA_GAP for vx, vy in vias):
                    continue
                placed = (cx, cy)
                break
            if placed:
                break
        if not placed:
            print(f"  no spot for {ref}.{pin} at {x:.2f},{y:.2f}")
            continue
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(placed[0]), pcbnew.FromMM(placed[1])))
        v.SetWidth(pcbnew.FromMM(0.5))
        v.SetDrill(pcbnew.FromMM(0.3))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(board.FindNet("GND"))
        board.Add(v)
        vias.append(placed)
        added += 1
        print(f"  via for {ref}.{pin} at {placed[0]:.2f},{placed[1]:.2f}")
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(PCB), board)
    print(f"added {added} stitching vias for {len(pads)} isolated GND pads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
