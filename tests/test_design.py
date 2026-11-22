from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DESIGN = yaml.safe_load((ROOT / "hardware" / "rp2040_frisk" / "design.yaml").read_text(encoding="utf-8"))


class BoardTests(unittest.TestCase):
    def test_board_is_frisk_sized_four_layer(self) -> None:
        board = DESIGN["board"]
        self.assertAlmostEqual(board["width_mm"], 57.6, places=3)
        self.assertAlmostEqual(board["height_mm"], 31.4, places=3)
        self.assertEqual(board["layers"], 4)
        self.assertAlmostEqual(board["chamfer_mm"], 2.0, places=3)

    def test_three_ports_have_independent_roles(self) -> None:
        ports = {p["id"]: p for p in DESIGN["ports"]}
        self.assertEqual(set(ports), {"keyboard", "pc", "ipad"})
        self.assertEqual(ports["keyboard"]["type"], "USB-A host")
        self.assertEqual(ports["pc"]["type"], "USB-C device")
        self.assertEqual(ports["ipad"]["type"], "USB-C device")
        self.assertIn("NKRO", ports["pc"]["role"])
        self.assertIn("MIDI", ports["ipad"]["role"])

    def test_type_c_ports_are_not_crowded(self) -> None:
        connectors = {c["ref"]: c for c in DESIGN["connectors"]}
        pitch = abs(connectors["J3"]["x_mm"] - connectors["J1"]["x_mm"])
        gap = pitch - connectors["J1"]["courtyard"][2]
        self.assertGreaterEqual(pitch, 25.0)
        self.assertGreaterEqual(gap, 15.0)
        self.assertAlmostEqual(pitch, 29.0, places=3)

    def test_all_connectors_are_on_long_edges(self) -> None:
        for connector in DESIGN["connectors"]:
            self.assertIn(connector["edge"], {"top", "bottom"}, connector["ref"])

    def test_no_advanced_via_process(self) -> None:
        fab = DESIGN["fabrication"]
        self.assertEqual(fab["via_diameter_mm"], 0.5)
        self.assertEqual(fab["via_drill_mm"], 0.3)
        self.assertFalse(fab["via_in_pad"])
        self.assertFalse(fab["plugged_vias"])
        self.assertFalse(fab["advanced_via_process"])
        self.assertNotIn(0.15, fab["allowed_via_drills_mm"])
        self.assertNotIn(0.15, fab["allowed_via_diameters_mm"])

    def test_pinmap_has_no_conflicts(self) -> None:
        pins = []
        gpios = []
        for entry in DESIGN["pinmap"]:
            if isinstance(entry["rp2040_pin"], int):
                pins.append(entry["rp2040_pin"])
            if isinstance(entry["gpio"], int):
                gpios.append(entry["gpio"])
        self.assertEqual(len(pins), len(set(pins)))
        self.assertEqual(len(gpios), len(set(gpios)))

    def test_six_switches_match_the_original_implementation(self) -> None:
        switches = {s["ref"]: s for s in DESIGN["switches"]}
        self.assertEqual(set(switches), {"SW1", "SW2", "SW3", "SW4", "SW5", "SW6"})
        self.assertEqual(sum(1 for s in switches.values() if s["type"] == "slide"), 5)
        self.assertEqual(sum(1 for s in switches.values() if s["type"] == "tact"), 1)
        self.assertIsNone(switches["SW4"]["gpio"])
        self.assertEqual(switches["SW1"]["gpio"], 28)
        self.assertEqual(switches["SW2"]["gpio"], 29)
        self.assertEqual(switches["SW3"]["gpio"], 27)
        self.assertEqual(switches["SW5"]["gpio"], 26)
        self.assertEqual(switches["SW6"]["gpio"], 14)

    def test_smt_bom_has_lcsc_parts(self) -> None:
        for line in DESIGN["bom"]:
            if line["assembly"] == "SMT":
                self.assertTrue(line.get("lcsc"), line["ref"])

    def test_design_check_script_passes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "check_design.py")],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
