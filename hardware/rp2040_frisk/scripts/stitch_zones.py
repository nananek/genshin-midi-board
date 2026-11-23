#!/usr/bin/env python3
"""Tie every filled ground-zone island to the In1 plane with one via.

Zone filling fragments the F.Cu/B.Cu ground pour into islands.  Islands that
still touch a ground pad survive island removal, but if they have no via they
are electrically floating and kicad-cli reports zone-to-zone unconnected
items.  This script scans each filled island and drops one 0.45/0.25 mm via on
a legal interior point, then refills.
"""

from __future__ import annotations

import math
import sys

import pcbnew

PCB = "/work/hardware/rp2040_frisk/rp2040_frisk.kicad_pcb"
VIA_D = 0.45
VIA_DRILL = 0.25
CLR = 0.35          # via radius + 0.1 copper clearance


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def rect_dist(p, r):
    x0, y0, x1, y1 = r
    dx = max(x0 - p[0], 0.0, p[0] - x1)
    dy = max(y0 - p[1], 0.0, p[1] - y1)
    return math.hypot(dx, dy)


def main() -> int:
    b = pcbnew.LoadBoard(PCB)
    pads = []
    for fp in b.GetFootprints():
        for p in fp.Pads():
            if p.GetNetname() == "GND":
                continue
            bb = p.GetBoundingBox()
            pads.append((pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                         pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())))
    segs = []
    gnd_vias = []
    for t in b.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            pos = t.GetPosition()
            p = (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))
            if t.GetNetname() == "GND":
                gnd_vias.append(p)
                continue
            segs.append(("p", p, pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2))
        else:
            if t.GetNetname() == "GND":
                continue
            a, c = t.GetStart(), t.GetEnd()
            segs.append(("s", ((pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)),
                              (pcbnew.ToMM(c.x), pcbnew.ToMM(c.y))),
                         pcbnew.ToMM(t.GetWidth()) / 2))

    added = skipped = 0
    for z in b.Zones():
        if z.GetNetname() != "GND":
            continue
        layer = z.GetLayer()
        poly = z.GetFilledPolysList(layer)
        for i in range(poly.OutlineCount()):
            isl = poly.Outline(i)
            pts = isl.CPoints()
            xs = [pcbnew.ToMM(p.x) for p in pts]
            ys = [pcbnew.ToMM(p.y) for p in pts]
            if not xs or not ys:
                continue
            spot = None
            y = min(ys) + 0.3
            while y < max(ys) - 0.3 and spot is None:
                x = min(xs) + 0.3
                while x < max(xs) - 0.3:
                    pos = pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))
                    if poly.Contains(pos) and isl.PointInside(pos):
                        ok = True
                        for kind, geo, half in segs:
                            d = (seg_dist((x, y), geo[0], geo[1])
                                 if kind == "s" else math.hypot(x - geo[0], y - geo[1]))
                            if d < half + CLR + 0.02:
                                ok = False
                                break
                        if ok:
                            for r in pads:
                                if rect_dist((x, y), r) < CLR + 0.02:
                                    ok = False
                                    break
                        if ok:
                            if any(math.hypot(x - vx, y - vy) < 0.65
                                   for vx, vy in gnd_vias):
                                ok = False
                        if ok:
                            spot = (x, y)
                            break
                    x += 0.25
                y += 0.25
            if spot is None:
                skipped += 1
                continue
            v = pcbnew.PCB_VIA(b)
            v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(spot[0]), pcbnew.FromMM(spot[1])))
            v.SetWidth(pcbnew.FromMM(VIA_D))
            v.SetDrill(pcbnew.FromMM(VIA_DRILL))
            v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            v.SetNet(b.FindNet("GND"))
            b.Add(v)
            gnd_vias.append(spot)
            added += 1
    b.BuildConnectivity()
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.SaveBoard(PCB, b)
    print(f"stitched {added} zone islands ({skipped} without room)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
