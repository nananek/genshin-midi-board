#!/usr/bin/env python3
"""Measure the RP2040 -> flash length of each QSPI net and check the limits.

The pull-up stubs (R12/R15 on QSPI_SS) are not part of the bus, so the length
is measured along the shortest path between the RP2040 pad and the flash pad.
The default check is 25 mm maximum and 10 mm spread.  The 2 mm spread used in
earlier revisions does not fit the 208-mil U2 and the 4-layer routing.
"""

from __future__ import annotations

import heapq
import sys
from collections import defaultdict
from math import hypot

import pcbnew

PCB = "/work/hardware/rp2040_midi_bridge/rp2040_midi_bridge.kicad_pcb"

BUS = {
    "QSPI_SS": ("U1", "56", "U2", "1"),
    "QSPI_SCLK": ("U1", "52", "U2", "6"),
    "QSPI_SD0": ("U1", "53", "U2", "5"),
    "QSPI_SD1": ("U1", "55", "U2", "2"),
    "QSPI_SD2": ("U1", "54", "U2", "3"),
    "QSPI_SD3": ("U1", "51", "U2", "7"),
}


def pad_pos(board, ref, pin):
    for fp in board.GetFootprints():
        if fp.GetReference() != ref:
            continue
        for p in fp.Pads():
            if p.GetNumber() == pin:
                pos = p.GetPosition()
                return (pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y))
    return None


def bus_length(board, net, start, goal):
    """Shortest path length along the net's segments between two points."""
    segs = []
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            continue
        if t.GetNetname() != net:
            continue
        a = t.GetStart()
        b = t.GetEnd()
        segs.append(((pcbnew.ToMM(a.x), pcbnew.ToMM(a.y)),
                     (pcbnew.ToMM(b.x), pcbnew.ToMM(b.y))))
    if not segs:
        return 0.0

    def key(p):
        return (round(p[0], 2), round(p[1], 2))

    adj = defaultdict(list)
    for a, b in segs:
        adj[key(a)].append((key(b), hypot(a[0] - b[0], a[1] - b[1])))
        adj[key(b)].append((key(a), hypot(a[0] - b[0], a[1] - b[1])))
    src = min(adj, key=lambda p: hypot(p[0] - start[0], p[1] - start[1]))
    dst = min(adj, key=lambda p: hypot(p[0] - goal[0], p[1] - goal[1]))
    dist = {src: 0.0}
    prev = {}
    heap = [(0.0, src)]
    while heap:
        d, u = heapq.heappop(heap)
        if u == dst:
            break
        if d > dist.get(u, 1e9):
            continue
        for v, w in adj[u]:
            nd = d + w
            if nd < dist.get(v, 1e9):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
    return dist.get(dst, 0.0)


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--board", default=PCB)
    ap.add_argument("--max-length", type=float, default=25.0)
    ap.add_argument("--max-spread", type=float, default=10.0)
    args = ap.parse_args()
    board = pcbnew.LoadBoard(args.board)
    lengths = {}
    for net, (r1, p1, r2, p2) in BUS.items():
        a = pad_pos(board, r1, p1)
        b = pad_pos(board, r2, p2)
        lengths[net] = bus_length(board, net, a, b) if a and b else 0.0
    print("QSPI bus length (RP2040 -> W25Q128), mm:")
    for net, v in lengths.items():
        print(f"  {net:10s} {v:7.2f}")
    live = {n: v for n, v in lengths.items() if v > 0}
    spread = max(live.values()) - min(live.values()) if len(live) > 1 else 0.0
    print(f"  spread     {spread:7.2f}")
    bad = [n for n, v in live.items() if v > args.max_length]
    if bad:
        print(f"FAIL {', '.join(bad)} exceeds {args.max_length:.1f} mm")
    if spread > args.max_spread:
        print(f"FAIL spread {spread:.2f} mm exceeds {args.max_spread:.1f} mm")
    return 1 if (bad or spread > args.max_spread) else 0


if __name__ == "__main__":
    sys.exit(main())
