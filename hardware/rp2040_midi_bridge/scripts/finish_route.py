#!/usr/bin/env python3
"""Rip-up router for the last few unconnected nets.

The grid router in gen_pcb.py routes greedily: whichever net gets there first
keeps the corridor, and a handful of local nets are boxed in by then.  This
script loads the generated board, removes the copper of the nets that DRC
reports as unconnected, and routes them again with rip-up: when a net still
cannot connect, it asks a pad-only router where the net *would* go, rips up the
few nets sitting on that path, and retries.  Ripped nets are queued again.
"""

from __future__ import annotations

import math
import os
import re
import sys
from collections import deque
from pathlib import Path

import pcbnew

ROOT = Path(__file__).resolve().parent.parent
PCB = ROOT / "rp2040_midi_bridge.kicad_pcb"
RPT = ROOT / "drc.rpt"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pcb_router as R  # noqa: E402

W, H = 62.0, 35.0
OUTLINE = [(2, 0), (60, 0), (62, 2), (62, 33), (60, 35), (2, 35),
           (0, 33), (0, 2)]

POWER_WIDTH = {"+5V": 0.8, "VBUS_PC": 0.8, "VBUS_IPAD": 0.8,
               "VBUS_USB_A": 1.0}
PLANE_WIDTH = {"+3V3": 0.2, "+1V1": 0.2}
USB_NETS = {n for n in (
    "USB_PC_DP", "USB_PC_DM", "USB_PC_DP_MCU", "USB_PC_DM_MCU",
    "USB_A_DP", "USB_A_DM", "USB_A_DP_MCU", "USB_A_DM_MCU",
    "USB_MIDI_DP", "USB_MIDI_DM", "USB_MIDI_DP_MCU", "USB_MIDI_DM_MCU")}
PROTECTED = {"GND", "+3V3", "+1V1", "+5V", "VBUS_PC", "VBUS_IPAD",
             "VBUS_USB_A", "QSPI_SS", "QSPI_SCLK", "QSPI_SD0", "QSPI_SD1",
             "QSPI_SD2", "QSPI_SD3", "X1_XIN", "X1_XOUT", "X1_XOUT_MCU",
             "X2_XI", "X2_XO"}
PROTECTED |= {n.strip() for n in os.environ.get("PCB_PROTECT", "").split(",")
              if n.strip()}

TIGHT_VIA = {"SW6_RESET", "RUN", "SWCLK", "SWDIO", "SW3_SUSTAIN",
             "STATUS_LED", "UART0_RX", "TPS_FAULT", "USB_MIDI_DP",
             "USB_MIDI_DM", "CH345_RST", "CC1_PC", "CC1_IPAD", "CC2_IPAD",
             "+5V", "VBUS_PC", "VBUS_IPAD", "VBUS_USB_A", "+3V3"}


def rule_for(net):
    if net in POWER_WIDTH:
        return POWER_WIDTH[net], 0.1
    if net in PLANE_WIDTH:
        return PLANE_WIDTH[net], 0.1
    if net in USB_NETS:
        return 0.2, 0.1
    return 0.15, 0.1


def unconnected_nets(report: Path):
    nets = set()
    if not report.exists():
        return nets
    text = report.read_text(encoding="utf-8")
    for block in text.split("[unconnected_items]")[1:]:
        for m in re.finditer(r"\[([^\]]+)\] of", block):
            net = m.group(1)
            if net not in ("GND",):
                nets.add(net)
    return nets


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


class Finisher:
    def __init__(self):
        self.board = pcbnew.LoadBoard(str(PCB))
        self.pads = []
        self.by_net = {}
        self.geom = {}
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
                self.pads.append((net, pcbnew.ToMM(bb.GetLeft()),
                                  pcbnew.ToMM(bb.GetTop()),
                                  pcbnew.ToMM(bb.GetRight()),
                                  pcbnew.ToMM(bb.GetBottom()),
                                  layers or ["F"], clr))
                if pad.GetNumber() and pad.GetNetname():
                    self.by_net.setdefault(net, []).append(
                        (pcbnew.ToMM(bb.GetCenter().x),
                         pcbnew.ToMM(bb.GetCenter().y),
                         "FB" if len(layers) > 1 else "F"))
        for t in self.board.GetTracks():
            if isinstance(t, pcbnew.PCB_VIA):
                p = t.GetPosition()
                pos = (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))
                self.geom.setdefault(t.GetNetname(), []).append(
                    ("via", pos, pcbnew.ToMM(t.GetDrill()),
                     pcbnew.ToMM(t.GetWidth(pcbnew.F_Cu)) / 2))
            else:
                a, c = t.GetStart(), t.GetEnd()
                self.geom.setdefault(t.GetNetname(), []).append(
                    ("trk", "F" if t.GetLayer() == pcbnew.F_Cu else "B",
                     (pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)),
                     (pcbnew.ToMM(c.x), pcbnew.ToMM(c.y)),
                     pcbnew.ToMM(t.GetWidth())))
        self.active = set(self.geom)
        self.rip_count = {}
        self.log = []

    # ------------------------------------------------------------------
    def build(self, active):
        r = R.Router(W, H, cell=0.05)
        r.set_outline(OUTLINE)
        for (net, x0, y0, x1, y1, layers, clr) in self.pads:
            r.add_pad(net, x0, y0, x1, y1, layers, clr)
        for net in active:
            for item in self.geom.get(net, []):
                if item[0] == "trk":
                    r.commit_track(net, item[1], item[2], item[3], item[4])
                else:
                    r.commit_via(net, item[1], item[2], item[3])
        return r

    def route_net(self, r, net, attempts=1):
        pts = self.by_net.get(net, [])
        if len(pts) < 2:
            return True
        if net == "+3V3":
            ok = 0
            for (x, y, _l) in pts:
                _t, vias = r.connect_to_plane("+3V3", (x, y, "F"),
                                              0.2, 0.1, 0.225)
                if vias:
                    ok += 1
            return ok == len(pts)
        width, clearance = rule_for(net)
        vrad = 0.225 if net in TIGHT_VIA else 0.25
        widths = [width]
        if width > 0.2:
            widths += [0.6, 0.5, 0.35, 0.25, 0.2, 0.15]
        elif width > 0.15:
            widths += [0.15, 0.127]
        else:
            widths += [0.127]
        for w in widths:
            connected = [0]
            todo = list(range(1, len(pts)))
            for _ in range(len(pts)):
                if not todo:
                    break
                remaining = []
                for i in todo:
                    best = min(connected, key=lambda j: math.hypot(
                        pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]))
                    d = math.hypot(pts[i][0] - pts[best][0],
                                   pts[i][1] - pts[best][1])
                    ww = min(w, 0.2) if d < 2.0 else w
                    if r.connect(net, pts[i], pts[best], ww, clearance,
                                 via_cost=12, max_expand=180000,
                                 via_radius=vrad):
                        connected.append(i)
                    else:
                        remaining.append(i)
                todo = remaining
            if not todo:
                return True
        return False

    def desired_paths(self, net):
        """Straight-line nearest-neighbour corridor between the pads."""
        pts = self.by_net.get(net, [])
        width, _c = rule_for(net)
        if len(pts) < 2:
            return []
        connected = [0]
        todo = list(range(1, len(pts)))
        items = []
        while todo:
            remaining = []
            for i in todo:
                best = min(connected, key=lambda j: math.hypot(
                    pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]))
                items.append(("trk", "F", (pts[best][0], pts[best][1]),
                              (pts[i][0], pts[i][1]), width))
                connected.append(i)
            todo = remaining
        return items

    @staticmethod
    def item_points(item):
        if item[0] == "trk":
            return [item[2], item[3]]
        return [item[1]]

    def item_dist(self, item, pts):
        best = 1e9
        for p in self.item_points(item):
            for i in range(len(pts) - 1):
                best = min(best, seg_dist(p, pts[i], pts[i + 1]))
            if len(pts) == 1:
                best = min(best, math.hypot(p[0] - pts[0][0], p[1] - pts[0][1]))
        return best

    def route_points(self, items):
        route = []
        for item in items:
            if item[0] == "trk":
                if not route:
                    route.append(item[2])
                route.append(item[3])
            else:
                route.append(item[1])
        return route

    def blockers_for(self, net, free, active):
        route = self.route_points(free)
        if not route:
            return set()
        width, clearance = rule_for(net)
        need = width / 2 + clearance + 0.05
        found = set()
        for other in active:
            if other == net or other in PROTECTED:
                continue
            for item in self.geom.get(other, []):
                half = item[4] / 2 if item[0] == "trk" else item[3]
                if self.item_dist(item, route) < half + need:
                    found.add(other)
                    break
        return found

    # ------------------------------------------------------------------
    def run(self, targets):
        targets = set(targets) - {"GND"}
        print("free paths...", flush=True)
        desired = {}
        for net in sorted(targets):
            desired[net] = self.desired_paths(net)
            print(f"  {net}: {len(desired[net])} items", flush=True)
        # A target is routed from scratch; drop its old (partial) copper so it
        # cannot be written back on top of the new route.
        for net in targets:
            self.geom.pop(net, None)
        active = set(self.geom) - targets
        rip = set()
        for net in targets:
            rip |= self.blockers_for(net, desired[net], active)
        rip -= targets
        print("initial rip:", sorted(rip), flush=True)
        for n in rip:
            self.geom.pop(n, None)
        active -= rip
        failed = sorted(targets)
        for rounds in range(int(os.environ.get("PCB_ROUNDS", "2"))):
            r = self.build(active)
            failed_next = []
            order = sorted(failed) + sorted(n for n in rip if n not in failed)
            for net in order:
                if net in ("GND",):
                    continue
                ok = self.route_net(r, net)
                if ok:
                    self.geom[net] = list(r.net_geom.get(net, []))
                    active.add(net)
                    print(f"  ok {net}: {len(self.geom[net])} items", flush=True)
                else:
                    failed_next.append(net)
                    print(f"  FAIL {net}", flush=True)
            if not failed_next:
                print(f"all routed after round {rounds}", flush=True)
                return
            print(f"round {rounds}: failed {failed_next}", flush=True)
            # rip whatever sits on the free path of the failures
            extra = set()
            for net in failed_next:
                if net not in desired:
                    desired[net] = self.desired_paths(net)
                extra |= self.blockers_for(net, desired[net], active)
            extra -= targets
            extra = {n for n in extra if self.rip_count.get(n, 0) < 3}
            if not extra:
                print("no extra blockers; stopping", flush=True)
                failed = failed_next
                break
            print("rip:", sorted(extra), flush=True)
            for n in extra:
                self.rip_count[n] = self.rip_count.get(n, 0) + 1
                # ripped copper is removed from the board; it is only written
                # back if the net is routed again this round
                self.geom.pop(n, None)
            active -= extra
            rip = extra
            failed = failed_next

    def save(self):
        for t in list(self.board.GetTracks()):
            self.board.Remove(t)
        for net, items in self.geom.items():
            ni = self.board.FindNet(net)
            for item in items:
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
                    _, p, drill, radius = item
                    v = pcbnew.PCB_VIA(self.board)
                    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1])))
                    v.SetWidth(pcbnew.FromMM(2 * radius))
                    v.SetDrill(pcbnew.FromMM(drill))
                    v.SetViaType(pcbnew.VIATYPE_THROUGH)
                    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                    v.SetNet(ni)
                    self.board.Add(v)
        self.board.BuildConnectivity()
        pcbnew.ZONE_FILLER(self.board).Fill(self.board.Zones())
        pcbnew.SaveBoard(str(PCB), self.board)


def main():
    targets = unconnected_nets(RPT)
    targets |= {n.strip() for n in os.environ.get("PCB_EXTRA_TARGETS", "").split(",")
                if n.strip()}
    if not targets:
        print("no unconnected nets")
        return 0
    print("targets:", sorted(targets))
    f = Finisher()
    f.run(targets)
    f.save()
    print("steps", len(f.log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
