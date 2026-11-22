#!/usr/bin/env python3
"""Build the machine-readable netlist for the RP2040 frisk board.

The design intent lives in design.yaml and docs/design.md.  This file turns
that intent into an explicit pin-to-net map so that the schematic and PCB
generators cannot drift from each other.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "hardware" / "rp2040_frisk" / "netlist.yaml"

C: dict[str, dict[str, Any]] = {}


def add(ref: str, value: str, footprint: str, pins: dict[str, str | None]) -> None:
    C[ref] = {"value": value, "footprint": footprint, "pins": pins}


# --- MCU and memory -------------------------------------------------------
add("U1", "RP2040", "QFN-56_7x7mm_P0.4mm", {
    "1": "+3V3", "2": "UART0_TX", "3": "UART0_RX", "4": None, "5": None,
    "6": "MIDI_UART_TX", "7": "MIDI_UART_RX", "8": None, "9": None,
    "10": "+3V3", "11": None, "12": None, "13": None, "14": None,
    "15": "USB_A_DP_MCU", "16": "USB_A_DM_MCU", "17": "SW6_RESET",
    "18": None, "19": "GND", "20": "X1_XIN", "21": "X1_XOUT_MCU",
    "22": "+3V3", "23": "+1V1", "24": "SWCLK", "25": "SWDIO", "26": "RUN",
    "27": None, "28": None, "29": None, "30": None, "31": None, "32": None,
    "33": "+3V3", "34": None, "35": None, "36": None, "37": "STATUS_LED",
    "38": None, "39": "SW3_SUSTAIN", "40": "SW1_MUTE", "41": "SW2_LYRE",
    "42": "+3V3", "43": "+3V3", "44": "+3V3", "45": "+1V1",
    "46": "USB_PC_DM_MCU", "47": "USB_PC_DP_MCU", "48": "+3V3", "49": "+3V3",
    "50": "+1V1", "51": "QSPI_SD3", "52": "QSPI_SCLK", "53": "QSPI_SD0",
    "54": "QSPI_SD2", "55": "QSPI_SD1", "56": "QSPI_SS", "57": "GND",
})

add("U2", "W25Q128JVSIQ", "SOIC-8_3.9x4.9mm_P1.27mm", {
    "1": "QSPI_SS", "2": "QSPI_SD1", "3": "QSPI_SD2", "4": "GND",
    "5": "QSPI_SD0", "6": "QSPI_SCLK", "7": "QSPI_SD3", "8": "+3V3",
})

# --- USB MIDI bridge ------------------------------------------------------
add("U3", "CH345T", "SSOP-20_5.3x7.2mm_P0.65mm", {
    "1": "CH345_RST", "2": None, "3": "MIDI_UART_RX", "4": "MIDI_UART_TX",
    "5": "CH345_V3", "6": "USB_MIDI_DP_MCU", "7": "USB_MIDI_DM_MCU", "8": "GND",
    "9": "X2_XI", "10": "X2_XO", "11": None, "12": None, "13": None,
    "14": None, "15": None, "16": None, "17": "GND", "18": None,
    "19": "+5V", "20": None,
})

# --- power ----------------------------------------------------------------
add("U4", "AP2112K-3.3TRG1", "SOT-23-5", {
    "1": "+5V", "2": "GND", "3": "+5V", "4": None, "5": "+3V3",
})
add("U5", "TPS2553DBVR", "SOT-23-6", {
    "1": "+5V", "2": "GND", "3": "TPS_EN", "4": "TPS_ILIM",
    "5": "VBUS_USB_A", "6": "TPS_FAULT",
})

# --- ESD ------------------------------------------------------------------
for ref, dp, dm, vbus in (
    ("U6", "USB_A_DP", "USB_A_DM", "VBUS_USB_A"),
    ("U7", "USB_PC_DP", "USB_PC_DM", "VBUS_PC"),
    ("U8", "USB_MIDI_DP", "USB_MIDI_DM", "VBUS_IPAD"),
):
    add(ref, "USBLC6-2SC6", "SOT-23-6", {
        "1": dp, "2": "GND", "3": dm, "4": dm, "5": vbus, "6": dp,
    })

# --- connectors -----------------------------------------------------------
usb_c_common = {
    "A1": "GND", "A12": "GND", "B1": "GND", "B12": "GND", "SH": "GND",
    "A8": None, "B8": None,
}
add("J1", "TYPE-C-31-M-12", "USB_C_Receptacle_HRO_TYPE-C-31-M-12", {
    **usb_c_common,
    "A4": "VBUS_PC", "A9": "VBUS_PC", "B4": "VBUS_PC", "B9": "VBUS_PC",
    "A5": "CC1_PC", "B5": "CC2_PC",
    "A6": "USB_PC_DP", "B6": "USB_PC_DP",
    "A7": "USB_PC_DM", "B7": "USB_PC_DM",
})
add("J3", "TYPE-C-31-M-12", "USB_C_Receptacle_HRO_TYPE-C-31-M-12", {
    **usb_c_common,
    "A4": "VBUS_IPAD", "A9": "VBUS_IPAD", "B4": "VBUS_IPAD", "B9": "VBUS_IPAD",
    "A5": "CC1_IPAD", "B5": "CC2_IPAD",
    "A6": "USB_MIDI_DP", "B6": "USB_MIDI_DP",
    "A7": "USB_MIDI_DM", "B7": "USB_MIDI_DM",
})
add("J2", "USB-A_5075AR-04-WH", "USB_A_Neltron_5075AR-04-WH", {
    "1": "VBUS_USB_A", "2": "USB_A_DM", "3": "USB_A_DP", "4": "GND",
    "5": "GND", "6": "GND",
})

# --- crystals, diodes, LED ------------------------------------------------
add("X1", "12MHz", "Crystal_SMD_3225-4Pin_3.2x2.5mm", {
    "1": "X1_XIN", "2": "GND", "3": "X1_XOUT", "4": "GND",
})
add("X2", "12MHz", "Crystal_SMD_3225-4Pin_3.2x2.5mm", {
    "1": "X2_XI", "2": "GND", "3": "X2_XO", "4": "GND",
})
add("D1", "BAT54WS", "D_SOD-323", {"1": "+5V", "2": "VBUS_PC"})
add("D2", "BAT54WS", "D_SOD-323", {"1": "+5V", "2": "VBUS_IPAD"})
add("LED1", "KT-0603R", "LED_0603_1608Metric", {"1": "GND", "2": "LED_A"})

# --- switches -------------------------------------------------------------
for ref, net in (("SW1", "SW1_MUTE"), ("SW2", "SW2_LYRE"), ("SW3", "SW3_SUSTAIN")):
    add(ref, "NKK_115643", "SW_SPDT_NKK_115643_Slide", {"1": None, "2": net, "3": "GND"})
add("SW4", "NKK_115643", "SW_SPDT_NKK_115643_Slide", {"1": None, "2": "TPS_EN", "3": "+3V3"})
add("SW6", "DTS-63-N-V-BLK", "SW_TACT_Akizuki_DTS63", {"1": "GND", "2": "GND", "3": "SW6_RESET", "4": "SW6_RESET"})

# --- resistors ------------------------------------------------------------
add("R1", "27R", "R_0603_1608Metric", {"1": "USB_PC_DP_MCU", "2": "USB_PC_DP"})
add("R2", "27R", "R_0603_1608Metric", {"1": "USB_PC_DM_MCU", "2": "USB_PC_DM"})
add("R3", "22R", "R_0603_1608Metric", {"1": "USB_A_DP_MCU", "2": "USB_A_DP"})
add("R4", "22R", "R_0603_1608Metric", {"1": "USB_A_DM_MCU", "2": "USB_A_DM"})
add("R5", "5.1k", "R_0603_1608Metric", {"1": "CC1_PC", "2": "GND"})
add("R6", "5.1k", "R_0603_1608Metric", {"1": "CC2_PC", "2": "GND"})
add("R7", "5.1k", "R_0603_1608Metric", {"1": "CC1_IPAD", "2": "GND"})
add("R8", "5.1k", "R_0603_1608Metric", {"1": "CC2_IPAD", "2": "GND"})
add("R9", "52.3k", "R_0603_1608Metric", {"1": "TPS_ILIM", "2": "GND"})
add("R10", "100k", "R_0603_1608Metric", {"1": "TPS_EN", "2": "GND"})
add("R11", "100k", "R_0603_1608Metric", {"1": "TPS_FAULT", "2": "+3V3"})
add("R12", "10k", "R_0603_1608Metric", {"1": "QSPI_SS", "2": "+3V3"})
add("R13", "1k", "R_0603_1608Metric", {"1": "STATUS_LED", "2": "LED_A"})
add("R14", "1k", "R_0603_1608Metric", {"1": "X1_XOUT_MCU", "2": "X1_XOUT"})
add("R15", "1k", "R_0603_1608Metric", {"1": "QSPI_SS", "2": "BOOTSEL"})
add("R16", "100k", "R_0603_1608Metric", {"1": "CH345_RST", "2": "+5V"})
add("R17", "22R", "R_0603_1608Metric", {"1": "USB_MIDI_DP_MCU", "2": "USB_MIDI_DP"})
add("R18", "22R", "R_0603_1608Metric", {"1": "USB_MIDI_DM_MCU", "2": "USB_MIDI_DM"})
add("R19", "10k", "R_0603_1608Metric", {"1": "RUN", "2": "+3V3"})

# --- capacitors -----------------------------------------------------------
caps = {
    "C1": ("1uF", "+3V3"), "C2": ("1uF", "+1V1"), "C3": ("100nF", "+1V1"),
    "C4": ("1uF", "+3V3"), "C5": ("10uF", "+3V3"),
    "C6": ("100nF", "+3V3"), "C7": ("100nF", "+3V3"), "C8": ("100nF", "+3V3"),
    "C9": ("100nF", "+3V3"), "C10": ("100nF", "+3V3"), "C11": ("100nF", "+3V3"),
    "C12": ("100nF", "+3V3"), "C13": ("100nF", "+3V3"), "C14": ("100nF", "+1V1"),
    "C15": ("100nF", "+1V1"), "C16": ("100nF", "+3V3"),
    "C19": ("100nF", "CH345_V3"), "C20": ("100nF", "+5V"), "C21": ("10uF", "+5V"),
    "C24": ("100nF", "VBUS_PC"), "C25": ("100nF", "VBUS_IPAD"),
    "C26": ("100nF", "VBUS_USB_A"), "C27": ("100uF", "VBUS_USB_A"),
    "C28": ("10uF", "+5V"), "C29": ("100nF", "+5V"), "C30": ("100nF", "+5V"),
}
for ref, (value, net) in caps.items():
    add(ref, value, "C_0603_1608Metric" if value != "10uF" else "C_0805_2012Metric", {
        "1": net, "2": "GND",
    })
add("C17", "15pF", "C_0603_1608Metric", {"1": "X1_XIN", "2": "GND"})
add("C18", "15pF", "C_0603_1608Metric", {"1": "X1_XOUT", "2": "GND"})
add("C22", "22pF", "C_0603_1608Metric", {"1": "X2_XI", "2": "GND"})
add("C23", "22pF", "C_0603_1608Metric", {"1": "X2_XO", "2": "GND"})
C["C27"]["footprint"] = "C_1210_3225Metric"

# --- test pads ------------------------------------------------------------
for ref, net in (
    ("TP1", "UART0_TX"), ("TP2", "UART0_RX"), ("TP3", "GND"),
    ("TP4", "SWCLK"), ("TP5", "SWDIO"), ("TP6", "RUN"),
    ("TP7", "BOOTSEL"), ("TP8", "+3V3"), ("TP9", "+5V"),
    ("TP10", "GND"), ("TP11", "CH345_RST"), ("TP12", "VBUS_USB_A"),
):
    add(ref, net, "TestPoint_1P", {"1": net})

# --- derive nets ----------------------------------------------------------
nets: dict[str, list[str]] = {}
for ref, comp in C.items():
    for pin, net in comp["pins"].items():
        if net:
            nets.setdefault(net, []).append(f"{ref}.{pin}")

errors: list[str] = []
for net, members in sorted(nets.items()):
    if len(members) < 2:
        errors.append(f"net {net} has only {members}")
for ref, comp in C.items():
    if not comp["pins"]:
        errors.append(f"{ref} has no pins")
if errors:
    raise SystemExit("\n".join(errors))

data = {
    "project": "rp2040_frisk",
    "components": C,
    "nets": dict(sorted(nets.items())),
}
OUT.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
print(f"wrote {OUT.relative_to(ROOT)}: {len(C)} components, {len(nets)} nets")
