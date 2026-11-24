#!/usr/bin/env python3
"""Refresh the board-name, USB-A labels and QR code on the routed PCB.

Run inside the KiCad container:

    make silk
"""

from __future__ import annotations

from pathlib import Path

import pcbnew

import silk_art

ROOT = Path(__file__).resolve().parent.parent
PCB = ROOT / "rp2040_midi_bridge.kicad_pcb"


def main() -> None:
    board = pcbnew.LoadBoard(str(PCB))
    silk_art.add_art(board)
    pcbnew.SaveBoard(str(PCB), board)
    print(f"updated silkscreen art in {PCB}")


if __name__ == "__main__":
    main()
