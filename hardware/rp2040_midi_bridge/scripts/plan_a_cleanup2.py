#!/usr/bin/env python3
"""Third finishing pass for plan A: remove the last dangling stubs and route
the +5V / USB_MIDI_DP islands created by the U8 relocation.

    ./scripts/kicad.sh python3 hardware/rp2040_midi_bridge/scripts/plan_a_cleanup2.py
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

TRASH = []


def T(p):
    return (pcbnew.ToMM(p.x), pcbnew.ToMM(p.y))


def seg_dist(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def remove_via_near(board, pos, tol=0.05):
    n = 0
    for t in list(board.GetTracks()):
        if isinstance(t, pcbnew.PCB_VIA):
            p = T(t.GetPosition())
            if math.hypot(p[0] - pos[0], p[1] - pos[1]) <= tol:
                board.Remove(t)
                TRASH.append(t)
                n += 1
    return n


def remove_tracks_near(board, net, pos, tol=0.05):
    n = 0
    for t in list(board.GetTracks()):
        if isinstance(t, pcbnew.PCB_VIA) or t.GetNetname() != net:
            continue
        a, c = T(t.GetStart()), T(t.GetEnd())
        if math.hypot(a[0] - pos[0], a[1] - pos[1]) <= tol or \
                math.hypot(c[0] - pos[0], c[1] - pos[1]) <= tol:
            board.Remove(t)
            TRASH.append(t)
            n += 1
    return n


def remove_seg(board, net, p0, p1, tol=0.03):
    for t in list(board.GetTracks()):
        if isinstance(t, pcbnew.PCB_VIA) or t.GetNetname() != net:
            continue
        a, c = T(t.GetStart()), T(t.GetEnd())
        if ((math.hypot(a[0] - p0[0], a[1] - p0[1]) < tol and
             math.hypot(c[0] - p1[0], c[1] - p1[1]) < tol) or
                (math.hypot(a[0] - p1[0], a[1] - p1[1]) < tol and
                 math.hypot(c[0] - p0[0], c[1] - p0[1]) < tol)):
            board.Remove(t)
            TRASH.append(t)
            return True
    return False


def track(board, net, layer, p0, p1, width):
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

    # stray stitching / orphan vias
    for pos in ((40.9, 8.0), (58.4468, 17.2142)):
        print("remove via", pos, remove_via_near(board, pos), flush=True)
    # orphan stubs left by removed vias
    print("CH345 stub", remove_tracks_near(board, "CH345_RST", (52.5, 16.1)),
          flush=True)
    print("CH345 tail", remove_tracks_near(board, "CH345_RST", (52.45, 16.05)),
          flush=True)
    print("CH345 tail2", remove_tracks_near(board, "CH345_RST", (50.9, 16.05)),
          flush=True)
    print("VBUS stub", remove_tracks_near(board, "VBUS_IPAD", (42.85, 8.15)),
          flush=True)

    # +5V: reroute the branch that crossed SW3 pin 2
    remove_seg(board, "+5V", (54.6, 13.4), (52.9, 11.7))
    remove_seg(board, "+5V", (54.6, 13.4), (54.1, 13.9))
    remove_seg(board, "+5V", (54.1, 13.9), (54.1, 17.25))
    track(board, "+5V", "F", (52.9, 11.7), (54.1, 12.9), 0.25)
    track(board, "+5V", "F", (54.1, 12.9), (54.1, 17.25), 0.25)

    # USB_MIDI_DP: bridge the B.Cu island to the F.Cu fanout at 45.3/45.4
    track(board, "USB_MIDI_DP", "B", (42.35, 11.25), (45.3, 9.15), 0.2)
    track(board, "USB_MIDI_DP", "F", (45.3, 9.15), (45.4, 9.05), 0.2)

    # MIDI_UART_TX sits in the 0.365 mm gap between USB_MIDI_DM (y=12.7)
    # and U2 pad 7 (y=13.065); thin it to 0.127 and centre it.
    for t in list(board.GetTracks()):
        if isinstance(t, pcbnew.PCB_VIA) or t.GetNetname() != "MIDI_UART_TX":
            continue
        a, c = T(t.GetStart()), T(t.GetEnd())
        if abs(a[1] - 12.85) < 0.001 and abs(c[1] - 12.85) < 0.001:
            board.Remove(t)
            TRASH.append(t)
            track(board, "MIDI_UART_TX", "F", (a[0], 12.8825),
                  (c[0], 12.8825), 0.127)
            print("nudged MIDI_UART_TX", a, c, flush=True)

    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.SaveBoard(str(path), board)
    print(f"saved {path}", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
