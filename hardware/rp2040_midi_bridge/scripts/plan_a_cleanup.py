#!/usr/bin/env python3
"""Second finishing pass for plan A: clean up the moved U8 fanout and the
+5V branch that now runs through SW3 pin 3.

Run after plan_a_finish.py, inside the KiCad container:

    ./scripts/kicad.sh python3 hardware/rp2040_midi_bridge/scripts/plan_a_cleanup.py \
        [--board path/to/board.kicad_pcb]
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BOARD = ROOT / "rp2040_midi_bridge.kicad_pcb"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pcb_router as R  # noqa: E402

W, H = 58.0, 44.0
OUTLINE = [(2, 0), (56, 0), (58, 2), (58, 42), (56, 44), (2, 44),
           (0, 42), (0, 2)]
CLEARANCE = 0.1
TRASH = []

U8_OLD = (39.5, 10.5)
U8_NEW = (40.4, 10.5)


def T(p):
    return (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))


def read_copper(board):
    copper = []
    for t in board.GetTracks():
        net = t.GetNetname()
        if isinstance(t, pcbnew.PCB_VIA):
            data = ("via", net, T(t.GetPosition()),
                    pcbnew.ToMM(t.GetDrill()),
                    pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2)
        else:
            data = ("trk", net,
                    "F" if t.GetLayer() == pcbnew.F_Cu else "B",
                    T(t.GetStart()), T(t.GetEnd()),
                    pcbnew.ToMM(t.GetWidth()))
        copper.append((data, t))
    return copper


def drop_item(board, copper, data, item):
    board.Remove(item)
    TRASH.append(item)
    copper.remove((data, item))


def remove_near(board, copper, net, centre, radius):
    cx, cy = centre
    for data, item in list(copper):
        if data[1] != net:
            continue
        pts = [data[2]] if data[0] == "via" else [data[3], data[4]]
        if any(math.hypot(p[0] - cx, p[1] - cy) <= radius for p in pts):
            drop_item(board, copper, data, item)


def remove_seg(board, copper, net, p0, p1, tol=0.02):
    for data, item in list(copper):
        if data[1] != net or data[0] != "trk":
            continue
        a, c = data[3], data[4]
        if ((math.hypot(a[0] - p0[0], a[1] - p0[1]) < tol and
             math.hypot(c[0] - p1[0], c[1] - p1[1]) < tol) or
                (math.hypot(a[0] - p1[0], a[1] - p1[1]) < tol and
                 math.hypot(c[0] - p0[0], c[1] - p0[1]) < tol)):
            drop_item(board, copper, data, item)
            return True
    return False


def remove_via_at(board, copper, pos, tol=0.01):
    for data, item in list(copper):
        if data[0] == "via" and math.hypot(data[2][0] - pos[0],
                                           data[2][1] - pos[1]) < tol:
            drop_item(board, copper, data, item)
            return True
    return False


def endpoints(copper, net):
    pts = []
    for c, _item in copper:
        if c[1] != net:
            continue
        if c[0] == "via":
            pts.append((*c[2], "FB"))
        else:
            pts.append((*c[3], c[2]))
            pts.append((*c[4], c[2]))
    return pts


class Router:
    def __init__(self, board, copper):
        self.board = board
        self.copper = [d for d, _i in copper]
        self.r = R.Router(W, H, cell=0.05)
        self.r.set_outline(OUTLINE)

    def build(self):
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
                self.r.add_pad(net, pcbnew.ToMM(bb.GetLeft()),
                               pcbnew.ToMM(bb.GetTop()),
                               pcbnew.ToMM(bb.GetRight()),
                               pcbnew.ToMM(bb.GetBottom()),
                               layers or ["F"], clr)
        for c in self.copper:
            if c[0] == "via":
                self.r.commit_via(c[1], c[2], c[3], c[4])
            else:
                self.r.commit_track(c[1], c[2], c[3], c[4], c[5])

    def connect(self, net, src, dst, widths):
        for w in widths:
            for force in (None, 0):
                for vc in (30, 8):
                    if self.r.connect(net, src, dst, w, CLEARANCE,
                                      via_cost=vc, max_expand=3000000,
                                      via_radius=0.225, force_layer=force):
                        return True
        return False

    def emit(self, net, base):
        ni = self.board.FindNet(net)
        for item in self.r.net_geom.get(net, [])[base:]:
            if item[0] == "trk":
                _, layer, p0, p1, width, _e = item
                t = pcbnew.PCB_TRACK(self.board)
                t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(p0[0]),
                                           pcbnew.FromMM(p0[1])))
                t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(p1[0]),
                                         pcbnew.FromMM(p1[1])))
                t.SetLayer(pcbnew.F_Cu if layer == "F" else pcbnew.B_Cu)
                t.SetWidth(pcbnew.FromMM(width))
                t.SetNet(ni)
                self.board.Add(t)
            else:
                _, p, drill, radius = item
                v = pcbnew.PCB_VIA(self.board)
                v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(p[0]),
                                              pcbnew.FromMM(p[1])))
                v.SetWidth(pcbnew.FromMM(2 * radius))
                v.SetDrill(pcbnew.FromMM(drill))
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetNet(ni)
                self.board.Add(v)


def add_track(board, net, layer, p0, p1, width=0.25):
    ni = board.FindNet(net)
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(p0[0]),
                               pcbnew.FromMM(p0[1])))
    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(p1[0]),
                             pcbnew.FromMM(p1[1])))
    t.SetLayer(pcbnew.F_Cu if layer == "F" else pcbnew.B_Cu)
    t.SetWidth(pcbnew.FromMM(width))
    t.SetNet(ni)
    board.Add(t)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=str(DEFAULT_BOARD))
    args = ap.parse_args(argv)
    path = Path(args.board)
    board = pcbnew.LoadBoard(str(path))
    copper = read_copper(board)

    # ---- U8 fanout: drop the local 0.9 mm-shifted pieces -----------------
    fp = board.FindFootprintByReference("U8")
    pads = {p.GetNumber(): p for p in fp.Pads()}
    for pin in ("1", "3", "4", "5", "6"):
        net = pads[pin].GetNetname()
        c = T(pads[pin].GetPosition())
        remove_near(board, copper, net, c, 1.7)
        remove_near(board, copper, net,
                    (c[0] - (U8_NEW[0] - U8_OLD[0]), c[1]), 1.0)
    g = T(pads["2"].GetPosition())
    remove_near(board, copper, "GND", g, 1.2)
    remove_near(board, copper, "GND",
                (g[0] - (U8_NEW[0] - U8_OLD[0]), g[1]), 1.0)

    # ---- +5V branch that crosses SW3 pin 3 -------------------------------
    for a, b in (((59.0, 15.3), (55.75, 15.3)),
                 ((59.3, 15.6), (59.0, 15.3)),
                 ((59.4, 15.6), (59.3, 15.6)),
                 ((60.0, 16.2), (59.4, 15.6))):
        remove_seg(board, copper, "+5V", a, b)

    # ---- dangling vias and the edge-clearance stitching via --------------
    for pos in ((35.1256, 10.7910), (56.8968, 17.2142),
                (52.5, 16.1), (61.35, 19.4)):
        remove_via_at(board, copper, pos)

    # ---- route the U8 pads back onto their nets --------------------------
    rb = Router(board, copper)
    rb.build()
    for pin in ("1", "3", "4", "5", "6"):
        net = pads[pin].GetNetname()
        src = (*T(pads[pin].GetPosition()), "F")
        base = len(rb.r.net_geom.get(net, []))
        ends = endpoints(copper, net)
        ends.sort(key=lambda p: math.hypot(p[0] - src[0], p[1] - src[1]))
        good = False
        for end in ends[:12]:
            if rb.connect(net, src, end, [0.2, 0.15, 0.127]):
                good = True
                break
        if not good:
            print(f"FAIL U8.{pin} {net}", flush=True)
            sys.stdout.flush()
            os._exit(1)
        rb.emit(net, base)
        print(f"U8.{pin} {net}: ok", flush=True)
    base = len(rb.r.net_geom.get("GND", []))
    _tracks, vias = rb.r.connect_to_plane("GND", (*g, "F"), 0.2, 0.1, 0.225)
    if not vias:
        print("FAIL U8.2 GND", flush=True)
        sys.stdout.flush()
        os._exit(1)
    rb.emit("GND", base)
    print("U8.2 GND: ok", flush=True)

    # ---- clean +5V path to TP9 around SW3 --------------------------------
    add_track(board, "+5V", "F", (54.6, 13.4), (54.1, 13.9))
    add_track(board, "+5V", "F", (54.1, 13.9), (54.1, 17.25))
    add_track(board, "+5V", "F", (54.05, 17.25), (54.1, 17.25))
    add_track(board, "+5V", "F", (54.1, 17.25), (54.1, 17.4))
    add_track(board, "+5V", "F", (54.1, 17.4), (59.6, 17.4))
    add_track(board, "+5V", "F", (59.6, 17.4), (59.6, 16.2))
    add_track(board, "+5V", "F", (59.6, 16.2), (60.0, 16.2))
    print("+5V TP9 branch rerouted", flush=True)

    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(path), board)
    print(f"saved {path}", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
