#!/usr/bin/env python3
"""Close the unconnected items that kicad-cli reports, one gap at a time.

For every [unconnected_items] block the DRC names two copper objects of the
same net.  This script loads the board, builds the grid router from the real
copper, and tries to add a track (with 0.45/0.25 or 0.5/0.3 vias if needed)
between those two objects.  It does not rip anything up: each repair only uses
free space, so a failure leaves the board as it was.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "rp2040_midi_bridge.kicad_pcb"
RPT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "drc.rpt"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pcb_router as R  # noqa: E402

W, H = 62.0, 35.0
OUTLINE = [(2, 0), (60, 0), (62, 2), (62, 33), (60, 35), (2, 35),
           (0, 33), (0, 2)]
POWER = {"+5V": 0.8, "VBUS_PC": 0.8, "VBUS_IPAD": 0.8, "VBUS_USB_A": 1.0}


def width_for(net):
    if net in POWER:
        return POWER[net]
    if net in ("+3V3", "+1V1"):
        return 0.2
    if net.startswith("USB_"):
        return 0.2
    return 0.15


def parse_items(report: Path):
    text = report.read_text(encoding="utf-8")
    out = []
    for block in text.split("[unconnected_items]")[1:]:
        items = []
        for m in re.finditer(
                r"@\(([-\d.]+) mm, ([-\d.]+) mm\): (.*)", block):
            x, y, desc = float(m.group(1)), float(m.group(2)), m.group(3)
            nm = re.search(r"\[([^\]]+)\]", desc)
            if not nm:
                continue
            net = nm.group(1)
            if net == "GND":
                continue
            layers = "FB" if "Via" in desc or "PTH" in desc else "F"
            if "on B.Cu" in desc:
                layers = "B"
            items.append((x, y, layers, desc, net))
            if len(items) == 2:
                break
        if len(items) == 2 and items[0][4] == items[1][4]:
            out.append((items[0], items[1]))
    return out


class Repairer:
    def __init__(self):
        self.board = pcbnew.LoadBoard(str(PCB))
        self.router = R.Router(W, H, cell=0.05)
        self.router.set_outline(OUTLINE)
        for fp in self.board.GetFootprints():
            for pad in fp.Pads():
                bb = pad.GetBoundingBox()
                net = pad.GetNetname() or "NC"
                layers = []
                if pad.GetLayerSet().Contains(pcbnew.F_Cu):
                    layers.append("F")
                if pad.GetLayerSet().Contains(pcbnew.B_Cu):
                    layers.append("B")
                clr = 0.1
                if pad.GetDrillSize().x > 0:
                    clr = max(clr, 0.35)
                self.router.add_pad(net, pcbnew.ToMM(bb.GetLeft()),
                                    pcbnew.ToMM(bb.GetTop()),
                                    pcbnew.ToMM(bb.GetRight()),
                                    pcbnew.ToMM(bb.GetBottom()),
                                    layers or ["F"], clr)
        for t in self.board.GetTracks():
            if isinstance(t, pcbnew.PCB_VIA):
                p = t.GetPosition()
                self.router.commit_via(t.GetNetname(),
                                       (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)),
                                       pcbnew.ToMM(t.GetDrill()),
                                       pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2)
            else:
                a, c = t.GetStart(), t.GetEnd()
                self.router.commit_track(
                    t.GetNetname(),
                    "F" if t.GetLayer() == pcbnew.F_Cu else "B",
                    (pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)),
                    (pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)),
                    pcbnew.ToMM(t.GetWidth()))

    def repair(self, a, b):
        net = a[4]
        w = width_for(net)
        src = (a[0], a[1], a[2])
        dst = (b[0], b[1], b[2])
        before = len(self.router.net_geom.get(net, []))
        width_tries = [w]
        if w > 0.3:
            width_tries += [0.6, 0.5, 0.35, 0.3, 0.25, 0.2]
        elif w > 0.18:
            width_tries += [0.15, 0.127]
        else:
            width_tries += [0.127]
        for ww in width_tries:
            for vc in (4, 12, 30):
                for force in (None, 0, 1):
                    if self.router.connect(net, src, dst, ww, 0.1,
                                           via_cost=vc, max_expand=2500000,
                                           via_radius=0.225,
                                           force_layer=force,
                                           via_gap=0.5):
                        self.emit(net, before)
                        return True
        # Fallback: a plain straight track if the corridor is clear.  This
        # handles adjacent connector pads where corner rules block the maze.
        if src[2] == dst[2] and src[2] in ("F", "B"):
            lay = 0 if src[2] == "F" else 1
            for ww in width_tries:
                blocked, _vm = self.router.masks(net, ww, 0.1, 0.225)
                if self.router._seg_clear(blocked[lay], (src[0], src[1]),
                                          (dst[0], dst[1])):
                    self.router.commit_track(net, src[2],
                                             (src[0], src[1]),
                                             (dst[0], dst[1]), ww)
                    self.emit(net, before)
                    return True
        return False

    def emit(self, net, before):
        ni = self.board.FindNet(net)
        for item in self.router.net_geom.get(net, [])[before:]:
            if item[0] == "trk":
                _, layer, p0, p1, width = item[:5]
                t = pcbnew.PCB_TRACK(self.board)
                t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(p0[0]), pcbnew.FromMM(p0[1])))
                t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(p1[0]), pcbnew.FromMM(p1[1])))
                t.SetLayer(pcbnew.F_Cu if layer == "F" else pcbnew.B_Cu)
                t.SetWidth(pcbnew.FromMM(width))
                t.SetNet(ni)
                self.board.Add(t)
            else:
                _, p, drill, radius = item[:4]
                v = pcbnew.PCB_VIA(self.board)
                v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1])))
                v.SetWidth(pcbnew.FromMM(2 * radius))
                v.SetDrill(pcbnew.FromMM(drill))
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetNet(ni)
                self.board.Add(v)

    def save(self):
        self.board.BuildConnectivity()
        pcbnew.ZONE_FILLER(self.board).Fill(self.board.Zones())
        pcbnew.SaveBoard(str(PCB), self.board)


def main():
    pairs = parse_items(RPT)
    if not pairs:
        print("no unconnected pairs")
        return 0
    print(f"{len(pairs)} gaps")
    rep = Repairer()
    ok = fail = 0
    for a, b in pairs:
        if rep.repair(a, b):
            ok += 1
            print(f"  ok   {a[4]:14s} {a[0]:6.2f},{a[1]:6.2f} -> {b[0]:6.2f},{b[1]:6.2f}")
        else:
            fail += 1
            print(f"  FAIL {a[4]:14s} {a[0]:6.2f},{a[1]:6.2f} -> {b[0]:6.2f},{b[1]:6.2f}")
    rep.save()
    print(f"repaired {ok}, failed {fail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
