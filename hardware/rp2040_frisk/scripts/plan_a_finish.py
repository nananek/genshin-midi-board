#!/usr/bin/env python3
"""Plan A finishing pass for the 62 x 35 mm RP2040 frisk board.

Committed record of the QSPI_SD0 / SW3_SUSTAIN closure.  It works on the
existing routed board (it does not regenerate it):

  * moves U2 +1.5 mm in x so SD0 gets a legal U1-side via/channel,
  * moves U8 up 1.2 mm so the U2/U8 courtyards stay apart (U8 cannot move
    right: U3's courtyard starts 0.96 mm away and the +5V bus is at x=41.3),
  * moves TP11 +0.5 mm in x clear of U2's new courtyard,
  * moves SW3 to y = 12.5 mm and lifts C16/R16 into the free space above it,
  * reroutes all six QSPI nets plus the QSPI_SS pull-up stubs,
  * reroutes MIDI_UART_TX around U2.8,
  * routes SW3_SUSTAIN out of the U1.39 pocket on B.Cu,
  * reroutes TPS_FAULT, whose old via occupied the only SW3 via site,
  * drags the local stubs of the small moves and reconnects the two lifted
    passives.

pcbnew's Python Tracks() iterator cannot be used after BOARD.Remove(), so the
copper is read into plain data first.  Removed proxies are kept alive in TRASH
because destroying them in the SWIG bindings double-frees.  The script exits
with os._exit() for the same reason.

Run inside the KiCad container:

    ./scripts/kicad.sh python3 hardware/rp2040_frisk/scripts/plan_a_finish.py \
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
DEFAULT_BOARD = ROOT / "rp2040_frisk.kicad_pcb"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pcb_router as R  # noqa: E402

W, H = 62.0, 35.0
OUTLINE = [(2, 0), (60, 0), (62, 2), (62, 33), (60, 35), (2, 35),
           (0, 33), (0, 2)]
CLEARANCE = 0.1
TRASH = []          # removed board items, kept alive until os._exit()

# reference -> (dx, dy) in mm, board coordinates (y grows down)
MOVES = {
    "U2": (1.5, 0.0),
    "U8": (0.9, 0.0),
    "TP11": (0.5, 0.0),
    "SW3": (0.0, 3.5),         # y 9.0 -> 12.5
    "C16": (0.0, -10.2),       # (57.4, 16.2) -> (57.4, 6.0)
    "R16": (0.0, -11.4),       # (54.2, 16.4) -> (54.2, 5.0)
}
DRAG_REFS = ("U8", "TP11")    # small moves: pull the local stubs along

QSPI = ["QSPI_SS", "QSPI_SCLK", "QSPI_SD0",
        "QSPI_SD1", "QSPI_SD2", "QSPI_SD3"]
QSPI_ORDERS = [
    ["QSPI_SD3", "QSPI_SCLK", "QSPI_SD0", "QSPI_SD1", "QSPI_SD2", "QSPI_SS"],
    ["QSPI_SD2", "QSPI_SD3", "QSPI_SCLK", "QSPI_SD0", "QSPI_SD1", "QSPI_SS"],
    ["QSPI_SD3", "QSPI_SD2", "QSPI_SCLK", "QSPI_SD0", "QSPI_SD1", "QSPI_SS"],
    ["QSPI_SD0", "QSPI_SD2", "QSPI_SD3", "QSPI_SCLK", "QSPI_SD1", "QSPI_SS"],
    ["QSPI_SD2", "QSPI_SD0", "QSPI_SD3", "QSPI_SCLK", "QSPI_SD1", "QSPI_SS"],
    ["QSPI_SD3", "QSPI_SCLK", "QSPI_SD1", "QSPI_SD0", "QSPI_SD2", "QSPI_SS"],
]
PRE_STRIP = QSPI + ["TPS_FAULT"]

QSPI_PINS = {"QSPI_SS": ("56", "1"), "QSPI_SCLK": ("52", "6"),
             "QSPI_SD0": ("53", "5"), "QSPI_SD1": ("55", "2"),
             "QSPI_SD2": ("54", "3"), "QSPI_SD3": ("51", "7")}

# lifted passives: local stubs are dropped, then reconnected to the net
LIFTED = {
    "C16": ("1", "2"),         # +3V3 / GND
    "R16": ("1", "2"),         # CH345_RST / +5V
}
PLANE_PADS = [("U2", "4", "GND"), ("U2", "8", "+3V3"),
              ("C16", "1", "+3V3"), ("C16", "2", "GND")]


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


def drop_net(board, copper, net):
    keep = []
    for data, item in copper:
        if data[1] == net:
            board.Remove(item)
            TRASH.append(item)
        else:
            keep.append((data, item))
    return keep


def remove_board_local_stub(board, copper, net, centre, radius=0.75):
    """Remove a local stub from the board only; the router keeps its copy."""
    cx, cy = centre
    for data, item in copper:
        if data[1] != net or item is None:
            continue
        pts = [data[2]] if data[0] == "via" else [data[3], data[4]]
        if any(math.hypot(p[0] - cx, p[1] - cy) <= radius for p in pts):
            board.Remove(item)
            TRASH.append(item)


def remove_board_net(board, copper, net):
    """Remove a net's copper from the board, leaving the router data intact."""
    for data, item in copper:
        if data[1] == net and item is not None:
            board.Remove(item)
            TRASH.append(item)


def drop_local_stub(board, copper, net, centre, radius=0.75):
    cx, cy = centre
    keep = []
    for data, item in copper:
        if data[1] != net:
            keep.append((data, item))
            continue
        pts = [data[2]] if data[0] == "via" else [data[3], data[4]]
        if any(math.hypot(p[0] - cx, p[1] - cy) <= radius for p in pts):
            board.Remove(item)
            TRASH.append(item)
        else:
            keep.append((data, item))
    return keep


def drag_local(board, copper, ref, old, new):
    """Translate track endpoints that sit on a moved pad to its new centre."""
    moved = 0
    keep = []
    for data, item in copper:
        if data[0] != "trk":
            keep.append((data, item))
            continue
        pts = [list(data[3]), list(data[4])]
        hit = False
        for pin, centre in old.items():
            target = new[ref].get(pin)
            if target is None:
                continue
            net = new[ref + "_net"].get(pin)
            if data[1] != net:
                continue
            for k in (0, 1):
                if math.hypot(pts[k][0] - centre[0],
                              pts[k][1] - centre[1]) <= 0.35:
                    pts[k] = list(target)
                    hit = True
        if not hit:
            keep.append((data, item))
            continue
        board.Remove(item)
        TRASH.append(item)
        newdata = ("trk", data[1], data[2], tuple(pts[0]), tuple(pts[1]),
                   data[5])
        if math.hypot(pts[0][0] - pts[1][0], pts[0][1] - pts[1][1]) > 0.001:
            keep.append((newdata, None))
            moved += 1
    print(f"dragged {moved} stubs for {ref}", flush=True)
    return keep


def drag_cluster(board, copper, ref, centre, delta, nets, radius):
    """Translate a whole local copper cluster with the footprint.

    Moving only the pad endpoints stretches the fanout across the neighbouring
    pads, so every track endpoint and via of the footprint's nets inside
    `radius` of the old centre moves by the same delta.
    """
    dx, dy = delta
    cx, cy = centre
    moved = 0
    keep = []
    for data, item in copper:
        if data[1] not in nets:
            keep.append((data, item))
            continue
        hit = False
        if data[0] == "via":
            ox, oy = data[2]
            if math.hypot(ox - cx, oy - cy) <= radius:
                data = ("via", data[1], (ox + dx, oy + dy), data[3], data[4])
                hit = True
        else:
            pts = [list(data[3]), list(data[4])]
            for k in (0, 1):
                if math.hypot(pts[k][0] - cx, pts[k][1] - cy) <= radius:
                    pts[k] = [pts[k][0] + dx, pts[k][1] + dy]
                    hit = True
            if hit:
                data = ("trk", data[1], data[2], tuple(pts[0]),
                        tuple(pts[1]), data[5])
        if not hit:
            keep.append((data, item))
            continue
        if item is not None:
            board.Remove(item)
            TRASH.append(item)
        keep.append((data, None))
        moved += 1
    print(f"dragged {moved} cluster items for {ref}", flush=True)
    return keep


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


def router_endpoints(router, net):
    pts = []
    for item in router.net_geom.get(net, []):
        if item[0] == "via":
            pts.append((*item[1], "FB"))
        else:
            pts.append((*item[2], item[1]))
            pts.append((*item[3], item[1]))
    return pts


def width_for(net):
    if net in ("+5V", "VBUS_PC", "VBUS_IPAD"):
        return 0.8
    if net == "VBUS_USB_A":
        return 1.0
    if net in ("+3V3", "+1V1"):
        return 0.2
    if net.startswith("USB_"):
        return 0.2
    return 0.15


def pad_map(board, ref):
    fp = board.FindFootprintByReference(ref)
    if fp is None:
        raise SystemExit(f"footprint {ref} not found")
    return fp, {p.GetNumber(): p for p in fp.Pads()}


def pad_centres(board, ref):
    _fp, pads = pad_map(board, ref)
    return {pin: T(p.GetPosition()) for pin, p in pads.items()}, \
           {pin: p.GetNetname() for pin, p in pads.items()}


class RouterBuilder:
    def __init__(self, board, copper, dragged):
        self.board = board
        self.copper = [d for d, _i in copper]
        self.dragged = dragged
        self.router = R.Router(W, H, cell=0.05)
        self.router.set_outline(OUTLINE)
        self.base = {}

    def build(self):
        r = self.router
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
                r.add_pad(net, pcbnew.ToMM(bb.GetLeft()),
                          pcbnew.ToMM(bb.GetTop()),
                          pcbnew.ToMM(bb.GetRight()),
                          pcbnew.ToMM(bb.GetBottom()),
                          layers or ["F"], clr)
        for c in self.copper + self.dragged:
            if c[0] == "via":
                r.commit_via(c[1], c[2], c[3], c[4])
            else:
                r.commit_track(c[1], c[2], c[3], c[4], c[5])

    def mark(self, net):
        self.base.setdefault(net, len(self.router.net_geom.get(net, [])))

    def connect(self, net, src, dst, widths, forces=(None,), vcs=(30,),
                max_expand=3000000):
        self.mark(net)
        for w in widths:
            for force in forces:
                for vc in vcs:
                    if self.router.connect(net, src, dst, w, CLEARANCE,
                                           via_cost=vc, max_expand=max_expand,
                                           via_radius=0.225, force_layer=force):
                        return True
        return False

    def plane(self, net, pos):
        self.mark(net)
        _tracks, vias = self.router.connect_to_plane(
            net, (pos[0], pos[1], "F"), 0.2, CLEARANCE, 0.225)
        return bool(vias)

    def add_track(self, net, layer, p0, p1, width=0.15):
        self.mark(net)
        self.router.commit_track(net, layer, p0, p1, width)

    def add_via(self, net, pos, drill=0.25, radius=0.225):
        self.mark(net)
        self.router.commit_via(net, pos, drill, radius)

    def write(self):
        board = self.board
        for net in set(self.base) | {d[1] for d in self.dragged}:
            ni = board.FindNet(net)
            if ni is None:
                raise SystemExit(f"unknown net {net}")
            drag = []
            for d in self.dragged:
                if d[1] != net:
                    continue
                if d[0] == "trk":
                    drag.append(("trk", d[2], d[3], d[4], d[5], 0.0))
                else:
                    drag.append(("via", d[2], d[3], d[4]))
            if net in self.base:
                items = list(self.router.net_geom.get(net, [])[self.base[net]:])
                items += drag
            else:
                # nothing rerouted on this net: only the dragged stubs are new
                items = drag
            for item in items:
                if item[0] == "trk":
                    _, layer, p0, p1, width, _extra = item
                    t = pcbnew.PCB_TRACK(board)
                    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(p0[0]),
                                               pcbnew.FromMM(p0[1])))
                    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(p1[0]),
                                             pcbnew.FromMM(p1[1])))
                    t.SetLayer(pcbnew.F_Cu if layer == "F" else pcbnew.B_Cu)
                    t.SetWidth(pcbnew.FromMM(width))
                    t.SetNet(ni)
                    board.Add(t)
                else:
                    _, p, drill, radius = item
                    v = pcbnew.PCB_VIA(board)
                    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(p[0]),
                                                  pcbnew.FromMM(p[1])))
                    v.SetWidth(pcbnew.FromMM(2 * radius))
                    v.SetDrill(pcbnew.FromMM(drill))
                    v.SetViaType(pcbnew.VIATYPE_THROUGH)
                    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    v.SetNet(ni)
                    board.Add(v)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=str(DEFAULT_BOARD))
    args = ap.parse_args(argv)
    path = Path(args.board)
    board = pcbnew.LoadBoard(str(path))

    old = {}
    old_pos = {}
    for ref, (dx, dy) in MOVES.items():
        fp, pads = pad_map(board, ref)
        old[ref] = {pin: T(p.GetPosition()) for pin, p in pads.items()}
        pos = T(fp.GetPosition())
        old_pos[ref] = pos
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(pos[0] + dx),
                                       pcbnew.FromMM(pos[1] + dy)))
        print(f"move {ref}: {pos[0]:.2f},{pos[1]:.2f} -> "
              f"{pos[0] + dx:.2f},{pos[1] + dy:.2f}", flush=True)

    copper = read_copper(board)
    for net in PRE_STRIP:
        copper = drop_net(board, copper, net)
    for ref, pins in LIFTED.items():
        for pin in pins:
            net = pad_centres(board, ref)[1][pin]
            copper = drop_local_stub(board, copper, net, old[ref][pin])

    dragged = []
    for ref, radius in (("U8", 2.6), ("TP11", 1.0)):
        nets = set(pad_centres(board, ref)[1].values())
        copper = drag_cluster(board, copper, ref, old_pos[ref],
                              MOVES[ref], nets, radius)
        # collect the dragged data that is now in copper with item None
    for data, item in copper:
        if item is None:
            dragged.append(data)
    copper = [(d, i) for d, i in copper if i is not None]

    _, u1pads = pad_map(board, "U1")
    _, u2pads = pad_map(board, "U2")
    b = None
    for attempt, order in enumerate(QSPI_ORDERS, 1):
        print(f"QSPI attempt {attempt}: {','.join(order)}", flush=True)
        cand = RouterBuilder(board, copper, dragged)
        cand.build()
        good = True
        for net in order:
            p1, p2 = QSPI_PINS[net]
            src = (*T(u1pads[p1].GetPosition()), "F")
            dst = (*T(u2pads[p2].GetPosition()), "F")
            one = cand.connect(net, src, dst, [0.15, 0.127],
                               forces=(None, 0), vcs=(45, 12, 4),
                               max_expand=6000000)
            print(f"  {net}: {'ok' if one else 'FAIL'}", flush=True)
            good &= one
            if not good:
                break
        if good:
            b = cand
            break
    ok = b is not None
    if not ok:
        print("no QSPI order closed all six", flush=True)
        sys.stdout.flush()
        os._exit(1)

    # QSPI_SS pull-ups R15.1 / R12.1 onto the new trunk
    for ref in ("R15", "R12"):
        _, pads = pad_map(board, ref)
        src = (*T(pads["1"].GetPosition()), "F")
        ends = router_endpoints(b.router, "QSPI_SS")
        ends.sort(key=lambda p: math.hypot(p[0] - src[0], p[1] - src[1]))
        good = False
        for end in ends[:12]:
            if b.connect("QSPI_SS", src, end, [0.15, 0.127],
                         forces=(None, 0), vcs=(30, 8)):
                good = True
                break
        print(f"QSPI_SS {ref}.1: {'ok' if good else 'FAIL'}", flush=True)
        ok &= good

    # MIDI_UART_TX around U2.8: drop the old trunk now (it stays in the
    # router as a stale obstacle, but the net ignores its own copper)
    remove_board_net(board, copper, "MIDI_UART_TX")
    remove_board_net(board, copper, "MIDI_UART_RX")
    _, u3pads = pad_map(board, "U3")
    for net, upin, pq in (("MIDI_UART_TX", "6", "4"),
                          ("MIDI_UART_RX", "7", "3")):
        src = (*T(u1pads[upin].GetPosition()), "F")
        dst = (*T(u3pads[pq].GetPosition()), "F")
        good = b.connect(net, src, dst, [0.15, 0.127],
                         forces=(None, 0), vcs=(30, 8))
        print(f"{net}: {'ok' if good else 'FAIL'}", flush=True)
        ok &= good

    # CH345_RST: the TP11 stub was dragged; only the lifted R16.1 is new
    _, r16pads = pad_map(board, "R16")
    src = (*T(r16pads["1"].GetPosition()), "F")
    ends = router_endpoints(b.router, "CH345_RST")
    ends.sort(key=lambda p: math.hypot(p[0] - src[0], p[1] - src[1]))
    good = False
    for end in ends[:12]:
        if b.connect("CH345_RST", src, end, [0.15, 0.127],
                     forces=(None, 0), vcs=(30, 8)):
            good = True
            break
    print(f"CH345_RST R16.1: {'ok' if good else 'FAIL'}", flush=True)
    ok &= good

    # U2's old GND/+3V3 stubs stayed as QSPI obstacles; drop them now
    for pin, net in (("4", "GND"), ("8", "+3V3")):
        remove_board_local_stub(board, copper, net, old["U2"][pin])

    # +3V3 / GND plane stubs of the lifted U2 and C16
    for ref, pin, net in PLANE_PADS:
        _, pads = pad_map(board, ref)
        good = b.plane(net, T(pads[pin].GetPosition()))
        print(f"{net} {ref}.{pin}: {'ok' if good else 'FAIL'}", flush=True)
        ok &= good
    src = (*T(r16pads["2"].GetPosition()), "F")
    ends = endpoints(copper, "+5V")
    ends.sort(key=lambda p: math.hypot(p[0] - src[0], p[1] - src[1]))
    good = False
    for end in ends[:12]:
        if b.connect("+5V", src, end, [0.8, 0.5, 0.35, 0.25, 0.15],
                     forces=(None, 0), vcs=(30, 8)):
            good = True
            break
    print(f"+5V R16.2: {'ok' if good else 'FAIL'}", flush=True)
    ok &= good

    # SW3_SUSTAIN: forced B.Cu escape from the U1.39 pocket
    b.add_track("SW3_SUSTAIN", "F", (25.4, 20.4375), (25.4, 21.1))
    b.add_track("SW3_SUSTAIN", "F", (25.4, 21.1), (25.0, 21.1))
    b.add_track("SW3_SUSTAIN", "F", (25.0, 21.1), (25.0, 22.4))
    b.add_via("SW3_SUSTAIN", (25.0, 22.4), 0.25, 0.225)
    _, sw3pads = pad_map(board, "SW3")
    pin2 = T(sw3pads["2"].GetPosition())
    good = b.connect("SW3_SUSTAIN", (25.0, 22.4, "B"), (*pin2, "FB"),
                     [0.15, 0.127], forces=(1,), vcs=(30, 8))
    print(f"SW3_SUSTAIN: {'ok' if good else 'FAIL'}", flush=True)
    ok &= good

    _, u5 = pad_map(board, "U5")
    _, r11 = pad_map(board, "R11")
    good = b.connect("TPS_FAULT", (*T(u5["6"].GetPosition()), "F"),
                     (*T(r11["1"].GetPosition()), "F"),
                     [0.15, 0.127], forces=(None, 0), vcs=(30, 8))
    print(f"TPS_FAULT: {'ok' if good else 'FAIL'}", flush=True)
    ok &= good

    if not ok:
        print("plan A did not close every net; board left unsaved", flush=True)
        sys.stdout.flush()
        os._exit(1)

    b.write()
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(path), board)
    print(f"saved {path}", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
