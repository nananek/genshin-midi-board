from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIB = ROOT / "hardware" / "rp2040_midi_bridge" / "lib" / "rp2040_midi_bridge.pretty" / "USB_A_Neltron_5075AR-04-WH.kicad_mod"
PCB = ROOT / "hardware" / "rp2040_midi_bridge" / "rp2040_midi_bridge.kicad_pcb"

PAD_RE = re.compile(r'\(pad "([56])" thru_hole circle\s*\(at ([-0-9.]+) ([-0-9.]+)', re.S)


def shell_pads(text: str) -> dict[str, float]:
    return {number: float(y) for number, _, y in PAD_RE.findall(text)}


class J2FootprintTests(unittest.TestCase):
    def test_shell_pegs_are_on_the_opening_side(self) -> None:
        pads = shell_pads(LIB.read_text(encoding="utf-8"))
        self.assertEqual(set(pads), {"5", "6"})
        for y in pads.values():
            self.assertAlmostEqual(y, -2.7, places=3,
                                   msg="J2 shell pegs must sit 2.7 mm on the opening side")

    def test_board_uses_the_same_shell_peg_side(self) -> None:
        board = PCB.read_text(encoding="utf-8")
        start = board.index('footprint "rp2040_midi_bridge:USB_A_Neltron_5075AR-04-WH"')
        end = board.index("(footprint ", start + 10)
        pads = shell_pads(board[start:end])
        self.assertEqual(set(pads), {"5", "6"})
        for y in pads.values():
            self.assertAlmostEqual(y, -2.7, places=3)

    def test_boot_and_run_are_labelled_on_the_front_silk(self) -> None:
        board = PCB.read_text(encoding="utf-8")
        for label in ("BOOT", "RUN"):
            pattern = rf'\(gr_text "{label}"\s*\(at [-0-9.]+ [-0-9.]+ [-0-9.]+\)\s*\(layer "F.SilkS"\)'
            self.assertRegex(board, pattern, msg=f"{label} label missing from F.SilkS")


if __name__ == "__main__":
    unittest.main()
