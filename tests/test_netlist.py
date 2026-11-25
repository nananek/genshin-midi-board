from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
NETLIST = yaml.safe_load((ROOT / "hardware" / "rp2040_midi_bridge" / "netlist.yaml").read_text(encoding="utf-8"))


class NetlistTests(unittest.TestCase):
    def test_component_and_net_counts(self) -> None:
        self.assertEqual(len(NETLIST["components"]), 72)
        self.assertEqual(len(NETLIST["nets"]), 49)

    def test_every_net_has_at_least_two_pins(self) -> None:
        for net, members in NETLIST["nets"].items():
            self.assertGreaterEqual(len(members), 2, net)

    def test_every_component_has_a_footprint(self) -> None:
        for ref, comp in NETLIST["components"].items():
            self.assertTrue(comp["footprint"], ref)

    def test_pins_are_not_reused_within_a_component(self) -> None:
        for ref, comp in NETLIST["components"].items():
            pins = list(comp["pins"])
            self.assertEqual(len(pins), len(set(pins)), ref)

    def test_usb_pairs_are_present(self) -> None:
        nets = NETLIST["nets"]
        for net in ("USB_A_DP", "USB_A_DM", "USB_PC_DP", "USB_PC_DM", "USB_MIDI_DP", "USB_MIDI_DM"):
            self.assertIn(net, nets)
            self.assertGreaterEqual(len(nets[net]), 2, net)

    def test_power_nets_have_sources_and_loads(self) -> None:
        nets = NETLIST["nets"]
        for net in ("+5V", "+3V3", "+1V1", "GND", "VBUS_PC", "VBUS_IPAD", "VBUS_USB_A"):
            self.assertIn(net, nets)
            self.assertGreaterEqual(len(nets[net]), 2, net)

    def test_switches_match_the_design(self) -> None:
        comps = NETLIST["components"]
        self.assertEqual(comps["SW1"]["pins"]["2"], "SW1_MUTE")
        self.assertEqual(comps["SW2"]["pins"]["2"], "SW2_LYRE")
        self.assertEqual(comps["SW3"]["pins"]["2"], "SW3_SUSTAIN")
        self.assertEqual(comps["SW4"]["pins"]["2"], "TPS_EN")
        self.assertEqual(comps["SW5"]["pins"]["3"], "SW5_RESET")
        self.assertEqual(comps["SW6"]["pins"]["2"], "BOOTSEL")
        self.assertEqual(comps["SW7"]["pins"]["2"], "RUN")

    def test_rp2040_usb_and_qspi_pins(self) -> None:
        pins = NETLIST["components"]["U1"]["pins"]
        self.assertEqual(pins["46"], "USB_PC_DM_MCU")
        self.assertEqual(pins["47"], "USB_PC_DP_MCU")
        self.assertEqual(pins["15"], "USB_A_DP_MCU")
        self.assertEqual(pins["16"], "USB_A_DM_MCU")
        self.assertEqual(pins["51"], "QSPI_SD3")
        self.assertEqual(pins["56"], "QSPI_SS")
        self.assertEqual(pins["57"], "GND")


if __name__ == "__main__":
    unittest.main()
