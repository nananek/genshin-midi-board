#!/usr/bin/env python3
"""Close the unconnected items of a DRC report with local rip-up.

Each [unconnected_items] pair is routed with the pcb_router grid router,
rebuilt from the real copper of the board, the way close_gaps.py does it.  If
the pair has no free corridor, the copper of one unprotected net crossing the
straight line between the two items is ripped up, the pair is connected and
that net is routed again from its own pads.  A change is kept only when the
board's own unconnected count drops, so a repair never makes connectivity worse
and a second run on the output changes nothing.  Planes, VBUS, QSPI and clock
nets are never ripped, and new copper keeps CLEAR (0.13 mm, above the 0.1 mm
board minimum) to every other net, so no clearance violation is added.

Usage: local_repair.py [board.kicad_pcb] [drc.rpt]
Writes <board stem>.repaired.kicad_pcb next to the input.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pcb_router as R  # noqa: E402

TOMM = pcbnew.ToMM
ROOT = Path(__file__).resolve().parent.parent
PCB = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "rp2040_midi_bridge.kicad_pcb"
RPT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "drc.rpt"

W, H = 58.0, 44.0
OUTLINE = [(2, 0), (56, 0), (58, 2), (58, 42), (56, 44), (2, 44), (0, 42), (0, 2)]
POWER = {"+5V": 0.5, "VBUS_PC": 0.5, "VBUS_IPAD": 0.5, "VBUS_USB_A": 0.8}
CLEAR = 0.13          # above the 0.1 mm board minimum, same as close_gaps.py
VIA_R = 0.225         # 0.45 / 0.25 via
CORRIDOR = 0.5        # extra radius when looking for rip-up candidates
PROTECTED = {"GND", "+5V", "+3V3", "+1V1"}
PROTECTED_PREFIX = ("QSPI_", "X1_", "X2_", "VBUS_")


def protected(net):
    return net in PROTECTED or net.startswith(PROTECTED_PREFIX)


def width_for(net):
    if net in POWER:
        return POWER[net]
    return 0.2 if net in ("+3V3", "+1V1") or net.startswith("USB_") else 0.15


def widths_for(net):
    width = width_for(net)
    return [width] + [w for w in (0.5, 0.35, 0.25, 0.2, 0.15, 0.127) if w < width]


def parse_pairs(report: Path):
    """[(src, dst)] with src/dst = (x, y, layers, description, net)."""
    out = []
    for block in report.read_text(encoding="utf-8").split("[unconnected_items]")[1:]:
        items = []
        for m in re.finditer(r"@\(([-\d.]+) mm, ([-\d.]+) mm\): (.*)", block):
            x, y, desc = float(m.group(1)), float(m.group(2)), m.group(3)
            name = re.search(r"\[([^\]]+)\]", desc)
            if not name:
                continue
            layers = "FB" if ("Via" in desc or "PTH" in desc) else "F"
            layers = "B" if "on B.Cu" in desc else layers
            items.append((x, y, layers, desc, name.group(1)))
            if len(items) == 2:
                break
        if len(items) == 2 and items[0][4] == items[1][4]:
            out.append((items[0], items[1]))
    return out


def seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / ll))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def track_item(t):
    """A board track or via as a router item."""
    if isinstance(t, pcbnew.PCB_VIA):
        p = t.GetPosition()
        return ("via", (TOMM(p.x), TOMM(p.y)), TOMM(t.GetDrill()),
                TOMM(t.GetWidth(pcbnew.F_Cu)) / 2)
    a, b = t.GetStart(), t.GetEnd()
    return ("trk", "F" if t.GetLayer() == pcbnew.F_Cu else "B", (TOMM(a.x), TOMM(a.y)),
            (TOMM(b.x), TOMM(b.y)), TOMM(t.GetWidth()))


def make_item(board, net, item):
    """A router item as a board track or via."""
    if item[0] == "trk":
        _, layer, p0, p1, width = item[:5]
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(p0[0]), pcbnew.FromMM(p0[1])))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(p1[0]), pcbnew.FromMM(p1[1])))
        t.SetLayer(pcbnew.F_Cu if layer == "F" else pcbnew.B_Cu)
        t.SetWidth(pcbnew.FromMM(width))
        t.SetNet(net)
        return t
    _, p, drill, radius = item[:4]
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(p[0]), pcbnew.FromMM(p[1])))
    v.SetWidth(pcbnew.FromMM(2 * radius))
    v.SetDrill(pcbnew.FromMM(drill))
    v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(net)
    return v


class Board:
    """Copper of the board as router items, in plain python state.

    The BOARD object is never mutated: each measurement and the final save load
    a fresh copy of the input and lay the items on it, which keeps swig object
    lifetimes out of the way.
    """

    def __init__(self, path: Path):
        self.pcb = path
        board = pcbnew.LoadBoard(str(path))
        self.pads, self.pts, self.geom = [], {}, {}
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                bb = pad.GetBoundingBox()
                net = pad.GetNetname() or "NC"
                layers = [lg for lg, cu in (("F", pcbnew.F_Cu), ("B", pcbnew.B_Cu))
                          if pad.GetLayerSet().Contains(cu)] or ["F"]
                clr = 0.35 if pad.GetDrillSize().x > 0 else 0.1
                self.pads.append((net, TOMM(bb.GetLeft()), TOMM(bb.GetTop()),
                                  TOMM(bb.GetRight()), TOMM(bb.GetBottom()), layers, clr))
                if pad.GetNumber() and pad.GetNetname():
                    c = bb.GetCenter()
                    self.pts.setdefault(net, []).append(
                        (TOMM(c.x), TOMM(c.y), "FB" if len(layers) > 1 else layers[0]))
        for t in board.GetTracks():
            self.geom.setdefault(t.GetNetname(), []).append(track_item(t))
        board.BuildConnectivity()
        self.before = board.GetConnectivity().GetUnconnectedCount(False)

    def lay(self, board):
        for net in sorted(self.geom):
            info = board.FindNet(net)
            for item in self.geom[net]:
                board.Add(make_item(board, info, item))

    def measure(self):
        board = pcbnew.LoadBoard(str(self.pcb))
        conn = board.GetConnectivity()   # keep the wrapper alive across the edit
        for t in list(board.GetTracks()):
            board.RemoveNative(t)        # Remove() gives the item to python and
        self.lay(board)                  # the stale wrappers corrupt swig state
        board.BuildConnectivity()
        return conn.GetUnconnectedCount(False)

    def save(self, out: Path):
        board = pcbnew.LoadBoard(str(self.pcb))
        for t in list(board.GetTracks()):
            board.RemoveNative(t)
        self.lay(board)
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.SaveBoard(str(out), board)
        pro = self.pcb.with_suffix(".kicad_pro")
        if pro.exists():
            out.with_suffix(".kicad_pro").write_bytes(pro.read_bytes())

    def build(self):
        r = R.Router(W, H, cell=0.05)
        r.set_outline(OUTLINE)
        for pad in self.pads:
            r.add_pad(*pad)
        for net in sorted(self.geom):
            for item in self.geom[net]:
                if item[0] == "trk":
                    r.commit_track(net, item[1], item[2], item[3], item[4])
                elif not r.commit_via(net, item[1], item[2], item[3]):
                    # A via the board already has may fail the hole-to-hole
                    # guard; its copper still has to block other nets.
                    for lay in (0, 1):
                        r.stamp_disc(r.copper[lay], item[1][0], item[1][1], item[3])
                    r.net_geom.setdefault(net, []).append(item)
        return r


def connected(r, net, p0, p1):
    """True when the copper of `net` already links the two points."""
    own = r._own_map(net)
    switch = bytearray(r.n)
    for item in r.net_geom.get(net, []):
        if item[0] == "via":
            r.stamp_disc(switch, item[1][0], item[1][1], item[3])
    nx, n = r.nx, r.n
    start, goal = set(), set()
    for lay in (0, 1):
        for point, bucket in ((p0, start), (p1, goal)):
            i = r.idx(r.cx(point[0]), r.cy(point[1]))
            if own[lay][i]:
                bucket.add(lay * n + i)
    queue, seen = sorted(start), set(start)
    while queue:
        cur = queue.pop()
        if cur in goal:
            return True
        lay, cell = divmod(cur, n)
        iy, ix = divmod(cell, nx)
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            jx, jy = ix + dx, iy + dy
            if 0 <= jx < nx and 0 <= jy < r.ny:
                ni = jy * nx + jx
                if own[lay][ni] and lay * n + ni not in seen:
                    seen.add(lay * n + ni)
                    queue.append(lay * n + ni)
        other = (1 - lay) * n + cell
        if switch[cell] and own[1 - lay][cell] and other not in seen:
            seen.add(other)
            queue.append(other)
    return False


def try_connect(r, net, src, dst, widths, deep=False):
    """A* over a few widths and layer choices, then a straight fallback.

    Only the primary width gets the deep budget: a long net needs it, while the
    narrower retries only have to fit through local gaps.
    """
    plans = [(widths[0], 4, None, 3000000 if deep else 600000)]
    plans += [(w, 4, None, 600000) for w in widths[1:]]
    plans += [(w, vc, force, 300000) for w in widths
              for vc, force in ((12, None), (4, 0), (4, 1))]
    for width, via_cost, force, budget in plans:
        if r.connect(net, src, dst, width, CLEAR, via_cost=via_cost,
                     max_expand=budget, via_radius=VIA_R, force_layer=force,
                     via_gap=0.55):
            return True
    if src[2] == dst[2] and src[2] in ("F", "B"):   # straight segment fallback
        lay = 0 if src[2] == "F" else 1
        for width in widths:
            blocked, _vm = r.masks(net, width, CLEAR, VIA_R)
            if r._seg_clear(blocked[lay], src[:2], dst[:2]):
                r.commit_track(net, src[2], src[:2], dst[:2], width)
                return True
    return False


def route_net(r, net, pts):
    """Route a ripped net again from its own pads."""
    if len(pts) < 2:
        return True
    width = width_for(net)
    for w in [width] + [w for w in (0.2, 0.15, 0.127) if w < width]:
        done, todo = [0], list(range(1, len(pts)))
        for _ in range(len(pts)):
            left = []
            for i in todo:
                best = min(done, key=lambda j: math.hypot(
                    pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]))
                d = math.hypot(pts[i][0] - pts[best][0], pts[i][1] - pts[best][1])
                if r.connect(net, pts[i], pts[best], min(w, 0.2) if d < 2.0 else w,
                             CLEAR, via_cost=12, max_expand=800000, via_radius=VIA_R):
                    done.append(i)
                else:
                    left.append(i)
            todo = left
        if not todo:
            return True
    return False


class Repair:
    def __init__(self, path: Path):
        self.b = Board(path)
        self.best = self.b.before
        self.fixed, self.ripped = [], set()

    def snapshot(self):
        return {net: list(items) for net, items in self.b.geom.items()}

    def accept(self, snapshot):
        """Keep the current geom only if the unconnected count drops."""
        now = self.b.measure()
        if now < self.best:
            self.best = now
            return True
        self.b.geom = snapshot
        return False

    def blockers(self, net, src, dst, active):
        """Other nets across the straight corridor, worst first."""
        need = width_for(net) / 2 + CLEAR + CORRIDOR
        steps = int(math.hypot(dst[0] - src[0], dst[1] - src[1]) / 0.2) + 1
        samples = [(src[0] + (dst[0] - src[0]) * s / steps,
                    src[1] + (dst[1] - src[1]) * s / steps) for s in range(steps + 1)]
        score = {}
        for other in active:
            if other == net:
                continue
            for item in self.b.geom.get(other, []):
                if item[0] == "trk":
                    half, ends = item[4] / 2, (item[2], item[3])
                else:
                    half, ends = item[3], (item[1], item[1])
                hit = sum(1 for p in samples
                          if seg_dist(p, ends[0], ends[1]) < need + half)
                if hit:
                    score[other] = score.get(other, 0) + hit
        return [n for n in sorted(score, key=lambda n: (-score[n], n))
                if not protected(n)]

    def repair_pair(self, a, b):
        """'linked' (already joined), True (repaired) or False (gave up)."""
        net = a[4]
        src, dst = (a[0], a[1], a[2]), (b[0], b[1], b[2])
        widths = widths_for(net)
        snapshot, active = self.snapshot(), set(self.b.geom)
        r = self.b.build()
        if connected(r, net, src, dst):
            return "linked"
        before = len(r.net_geom.get(net, []))
        if try_connect(r, net, src, dst, widths, deep=True):
            self.b.geom.setdefault(net, []).extend(r.net_geom[net][before:])
            if self.accept(snapshot):
                return True
        for cand in self.blockers(net, src, dst, active)[:2]:
            snapshot = self.snapshot()
            self.b.geom.pop(cand, None)
            r = self.b.build()
            t_before = len(r.net_geom.get(net, []))
            if not try_connect(r, net, src, dst, widths):
                self.b.geom = snapshot
                continue
            c_before = len(r.net_geom.get(cand, []))
            if route_net(r, cand, self.b.pts.get(cand, [])):
                self.b.geom[net] = self.b.geom.get(net, []) + r.net_geom[net][t_before:]
                self.b.geom[cand] = r.net_geom[cand][c_before:]
                if self.accept(snapshot):
                    self.ripped.add(cand)
                    print(f"    ripped {cand} and routed it again", flush=True)
                    return True
            self.b.geom = snapshot
        return False

    def run(self, pairs):
        todo = [p for p in pairs if p[0][4] != "GND"]
        print(f"{PCB.name}: {self.b.before} unconnected, {len(todo)} pairs", flush=True)
        failed = []
        for rnd in range(3):
            failed = []
            for a, b in todo:
                res = self.repair_pair(a, b)
                where = f"{a[4]:16s} {a[0]:6.2f},{a[1]:6.2f} -> {b[0]:6.2f},{b[1]:6.2f}"
                if res is True:
                    self.fixed.append(a[4])
                    print(f"  ok   {where}  ({self.best} left)", flush=True)
                elif res == "linked":
                    print(f"  --   {where}  already connected", flush=True)
                else:
                    failed.append((a, b))
                    print(f"  FAIL {where}", flush=True)
            if not failed or len(failed) == len(todo):
                break
            print(f"round {rnd + 1}: {len(failed)} pairs left, retrying", flush=True)
            todo = failed
        print(f"unconnected: {self.b.before} -> {self.best}")
        print("repaired nets:   ", sorted(set(self.fixed)) or "-")
        print("ripped nets:     ", sorted(self.ripped) or "-")
        print("still unconnected:", sorted({a[4] for a, _b in failed}) or "-")
        return self.best < self.b.before


def main():
    if not RPT.exists():
        print(f"no report: {RPT}")
        return 1
    rep = Repair(PCB)
    if not rep.run(parse_pairs(RPT)):
        print("nothing repaired; board left untouched")
        return 0
    out = PCB.with_name(PCB.stem + ".repaired.kicad_pcb")
    rep.b.save(out)
    print("saved", out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
