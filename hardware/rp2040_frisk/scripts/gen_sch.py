#!/usr/bin/env python3
"""Generate the KiCad 10 schematic for the RP2040 frisk MIDI bridge.

The machine-readable netlist (../netlist.yaml) is the single source of truth:
every component, every pin number and every net name is taken from it.  This
script only adds what a schematic needs beyond the netlist: symbol choice,
sheet layout, power/PWR_FLAG symbols, no-connect markers and a title block.

Official KiCad symbols are copied into the project library so that the project
opens without the global library tables.  Three things cannot be taken
verbatim from the official libraries and are built here:

  * CH345T and TPS2553DBVR have no official KiCad symbols.
  * Connector:USB_A and Switch:SW_Push do not have the pin numbers that the
    Neltron USB-A footprint and the 4-pin DTS-63 tact switch need.

Run inside the KiCad container:

    docker run --rm -u "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:/work" \
        -w /work kicad/kicad:10.0 \
        python3 hardware/rp2040_frisk/scripts/gen_sch.py
"""

from __future__ import annotations

import copy
import csv
import math
import os
import uuid
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # hardware/rp2040_frisk
PROJECT = "rp2040_frisk"
LIB_NAME = PROJECT
SYM_DIR = Path(os.environ.get("KICAD_SYMBOL_DIR", "/usr/share/kicad/symbols"))
ROOT_UUID = "0d4a1f52-6a52-4d0e-9c3b-7a1e6f0d2b11"
STUB = 3.81
GRID = 1.27
POWER_EXTENT = 7.62  # room for a power symbol instead of a label
CAPTION_FONT = 2.0
CHAR_W = 1.12  # advance of the KiCad stroke font at 1.27 mm
MARGIN = 12.0
COL_GAP = 16.0
SHELF_GAP = 6.0
SHELF_H_GAP = 7.0

PAPER = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0),
         "A1": (841.0, 594.0), "A0": (1189.0, 841.0)}
PAPER_ORDER = ["A4", "A3", "A2", "A1", "A0"]


# ---------------------------------------------------------------------------
# S-expressions
# ---------------------------------------------------------------------------
class Q(str):
    """Atom that must be written as a quoted string."""


def tokenize(text):
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c in "()":
            yield c
            i += 1
        elif c.isspace():
            i += 1
        elif c == '"':
            i += 1
            buf = []
            while True:
                c = text[i]
                if c == "\\":
                    esc = text[i + 1]
                    buf.append({"n": "\n", "t": "\t", "r": "\r"}.get(esc, esc))
                    i += 2
                elif c == '"':
                    i += 1
                    break
                else:
                    buf.append(c)
                    i += 1
            yield Q("".join(buf))
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in '()"':
                j += 1
            yield text[i:j]
            i = j


def parse(text):
    stack = [[]]
    for tok in tokenize(text):
        if tok == "(":
            stack.append([])
        elif tok == ")":
            node = stack.pop()
            stack[-1].append(node)
        else:
            stack[-1].append(tok)
    return stack[0][0]


def esc(s):
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def dump(node, indent=0):
    pad = "\t" * indent
    if not isinstance(node, list):
        return f'"{esc(node)}"' if isinstance(node, Q) else str(node)
    if all(not isinstance(x, list) for x in node):
        return pad + "(" + " ".join(dump(x) for x in node) + ")"
    out = [pad + "(" + dump(node[0])]
    for item in node[1:]:
        if isinstance(item, list):
            out.append(dump(item, indent + 1))
        else:
            out[-1] += " " + dump(item)
    out.append(pad + ")")
    return "\n".join(out)


def child(node, head):
    for item in node:
        if isinstance(item, list) and item and item[0] == head:
            return item
    return None


def children(node, head):
    return [i for i in node if isinstance(i, list) and i and i[0] == head]


def prop(node, name):
    for item in children(node, "property"):
        if str(item[1]) == name:
            return item
    return None


# ---------------------------------------------------------------------------
# library symbols
# ---------------------------------------------------------------------------
_LIB_CACHE: dict[str, list] = {}


def lib_tree(filename):
    if filename not in _LIB_CACHE:
        _LIB_CACHE[filename] = parse((SYM_DIR / filename).read_text(encoding="utf-8"))
    return _LIB_CACHE[filename]


def raw_symbol(libtree, name):
    for node in libtree:
        if (isinstance(node, list) and node and node[0] == "symbol"
                and isinstance(node[1], Q) and str(node[1]) == name):
            return node
    raise KeyError(name)


def flatten_symbol(libtree, name):
    """Return a standalone (no ``extends``) copy of ``name``."""
    node = copy.deepcopy(raw_symbol(libtree, name))
    ext = child(node, "extends")
    if ext is None:
        return node
    base = flatten_symbol(libtree, str(ext[1]))
    base_name = str(base[1])
    for item in node[1:]:
        if not isinstance(item, list) or not item:
            continue
        head = item[0]
        if head in ("extends", "symbol"):
            continue
        if head == "property":
            for idx, other in enumerate(base):
                if (isinstance(other, list) and other and other[0] == "property"
                        and str(other[1]) == str(item[1])):
                    base[idx] = item
                    break
            else:
                base.append(item)
        else:
            for idx, other in enumerate(base):
                if isinstance(other, list) and other and other[0] == head:
                    base[idx] = item
                    break
            else:
                base.append(item)
    base[1] = Q(name)
    for item in base:
        if (isinstance(item, list) and item and item[0] == "symbol"
                and isinstance(item[1], Q) and str(item[1]).startswith(base_name + "_")):
            item[1] = Q(name + str(item[1])[len(base_name):])
    return base


PIN_TYPES = {"input", "output", "bidirectional", "tri_state", "passive", "free",
             "unspecified", "power_in", "power_out", "open_collector",
             "open_emitter", "no_connect"}
PIN_SHAPES = {"line", "inverted", "clock", "inverted_clock", "input_low",
              "clock_low", "output_low", "edge_clock_high", "non_logic"}


def symbol_pins(libsym):
    """number -> dict(x, y, angle, length, etype, name) from a flat symbol."""
    pins = {}
    for unit in children(libsym, "symbol"):
        for pin in unit[1:]:
            if (not isinstance(pin, list) or len(pin) < 4 or pin[0] != "pin"
                    or pin[1] not in PIN_TYPES or pin[2] not in PIN_SHAPES):
                continue
            at = child(pin, "at")
            length = child(pin, "length")
            number = child(pin, "number")
            name = child(pin, "name")
            pins[str(number[1])] = {
                "x": float(at[1]), "y": float(at[2]), "angle": float(at[3]),
                "length": float(length[1]), "etype": pin[1],
                "name": str(name[1]),
            }
    return pins


def graphic_points(libsym):
    pts = []
    for unit in children(libsym, "symbol"):
        for item in unit[1:]:
            if not isinstance(item, list) or not item:
                continue
            if item[0] == "rectangle":
                start, end = child(item, "start"), child(item, "end")
                pts += [(float(start[1]), float(start[2])), (float(end[1]), float(end[2]))]
            elif item[0] == "circle":
                center, radius = child(item, "center"), child(item, "radius")
                cx, cy, r = float(center[1]), float(center[2]), float(radius[1])
                pts += [(cx - r, cy - r), (cx + r, cy + r)]
            elif item[0] == "polyline":
                for xy in child(item, "pts")[1:]:
                    pts.append((float(xy[1]), float(xy[2])))
            elif item[0] == "arc":
                for key in ("start", "mid", "end"):
                    xy = child(item, key)
                    if xy:
                        pts.append((float(xy[1]), float(xy[2])))
    return pts


# ---------------------------------------------------------------------------
# custom symbols
# ---------------------------------------------------------------------------
def _effects():
    return ["effects", ["font", ["size", "1.27", "1.27"]]]


def _pin(number, name, etype, x, y, angle, length=3.81):
    return ["pin", etype, "line", ["at", fnum(x), fnum(y), fnum(angle)],
            ["length", fnum(length)],
            ["name", Q(name), _effects()],
            ["number", Q(number), _effects()]]


def _property(name, value, x, y, hide=False, angle=0):
    node = ["property", Q(name), Q(value), ["at", fnum(x), fnum(y), fnum(angle)],
            ["show_name", "no"], ["do_not_autoplace", "no"]]
    if hide:
        node.append(["hide", "yes"])
    node.append(_effects())
    return node


def make_symbol(name, ref_prefix, side_pins, width, height, value=None,
                description="", datasheet=""):
    """Build a rectangular box symbol.

    side_pins: list of (number, pin_name, etype, side, y) with side in "LR".
    """
    value = value or name
    top, bottom = height / 2.0, -height / 2.0
    body = ["rectangle", ["start", fnum(-width / 2), fnum(top)],
            ["end", fnum(width / 2), fnum(bottom)],
            ["stroke", ["width", "0.254"], ["type", "default"]],
            ["fill", ["type", "background"]]]
    sym = ["symbol", Q(name),
           ["pin_names", ["offset", "1.016"]],
           ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
           ["in_pos_files", "yes"], ["duplicate_pin_numbers_are_jumpers", "no"],
           _property("Reference", ref_prefix, 0, top + 2.54),
           _property("Value", value, 0, bottom - 2.54),
           _property("Footprint", "", 0, 0, hide=True),
           _property("Datasheet", datasheet, 0, 0, hide=True),
           _property("Description", description, 0, 0, hide=True),
           ["symbol", Q(f"{name}_0_1"), body]]
    unit = ["symbol", Q(f"{name}_1_1")]
    for number, pin_name, etype, side, y in side_pins:
        if side == "L":
            unit.append(_pin(number, pin_name, etype, -(width / 2 + 3.81), y, 0))
        else:
            unit.append(_pin(number, pin_name, etype, width / 2 + 3.81, y, 180))
    sym.append(unit)
    sym.append(["embedded_fonts", "no"])
    return sym


def power_symbol(rail):
    return ["symbol", Q(rail), ["power", "global"],
            ["pin_numbers", ["hide", "yes"]],
            ["pin_names", ["offset", "0"], ["hide", "yes"]],
            ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
            ["in_pos_files", "yes"], ["duplicate_pin_numbers_are_jumpers", "no"],
            _property("Reference", "#PWR", 0, 3.81, hide=True),
            _property("Value", rail, 0, 3.556),
            _property("Footprint", "", 0, 0, hide=True),
            _property("Datasheet", "", 0, 0, hide=True),
            _property("Description", f'Power symbol creates a global label with name "{rail}"',
                      0, 0, hide=True),
            ["symbol", Q(f"{rail}_0_1"),
             ["polyline", ["pts", ["xy", "-0.762", "1.27"], ["xy", "0", "2.54"]],
              ["stroke", ["width", "0"], ["type", "default"]], ["fill", ["type", "none"]]],
             ["polyline", ["pts", ["xy", "0", "2.54"], ["xy", "0.762", "1.27"]],
              ["stroke", ["width", "0"], ["type", "default"]], ["fill", ["type", "none"]]],
             ["polyline", ["pts", ["xy", "0", "0"], ["xy", "0", "2.54"]],
              ["stroke", ["width", "0"], ["type", "default"]], ["fill", ["type", "none"]]]],
            ["symbol", Q(f"{rail}_1_1"),
             ["pin", "power_in", "line", ["at", "0", "0", "90"], ["length", "0"],
              ["name", Q(""), _effects()], ["number", Q("1"), _effects()]]],
            ["embedded_fonts", "no"]]


def custom_symbols():
    syms = {}

    # CH345T -- USB MIDI <-> UART bridge, SSOP-20
    ch = [
        ("1", "RST", "input", "L", 11.43),
        ("2", "NC", "no_connect", "L", 8.89),
        ("3", "MOUT", "output", "L", 6.35),
        ("4", "MIN", "input", "L", 3.81),
        ("5", "V3", "passive", "L", 1.27),
        ("6", "UD+", "bidirectional", "L", -1.27),
        ("7", "UD-", "bidirectional", "L", -3.81),
        ("8", "GND", "power_in", "L", -6.35),
        ("9", "XI", "input", "L", -8.89),
        ("10", "XO", "output", "L", -11.43),
        ("20", "NC", "no_connect", "R", 11.43),
        ("19", "VCC", "power_in", "R", 8.89),
        ("18", "NC", "no_connect", "R", 6.35),
        ("17", "GND", "power_in", "R", 3.81),
        ("16", "NC", "no_connect", "R", 1.27),
        ("15", "NC", "no_connect", "R", -1.27),
        ("14", "NC", "no_connect", "R", -3.81),
        ("13", "NC", "no_connect", "R", -6.35),
        ("12", "NC", "no_connect", "R", -8.89),
        ("11", "NC", "no_connect", "R", -11.43),
    ]
    syms["CH345T"] = make_symbol(
        "CH345T", "U", ch, 17.78, 27.94,
        description="USB MIDI to UART bridge, SSOP-20",
        datasheet="http://wch.cn/downloads/CH345DS1_PDF.html")

    # TPS2553DBVR -- current limited 5 V switch, SOT-23-6
    tps = [
        ("1", "IN", "power_in", "L", 2.54),
        ("2", "GND", "power_in", "L", 0.0),
        ("3", "EN", "input", "L", -2.54),
        ("6", "FAULT", "open_collector", "R", 2.54),
        ("5", "OUT", "power_out", "R", 0.0),
        ("4", "ILIM", "passive", "R", -2.54),
    ]
    syms["TPS2553DBVR"] = make_symbol(
        "TPS2553DBVR", "U", tps, 12.7, 7.62,
        description="Adjustable current-limited power switch, SOT-23-6",
        datasheet="https://www.ti.com/lit/ds/symlink/tps2553.pdf")

    # USB-A receptacle with two shell tabs (Neltron 5075AR-04-WH)
    usba = [
        ("1", "VBUS", "passive", "L", 5.08),
        ("2", "D-", "passive", "L", 2.54),
        ("3", "D+", "passive", "L", 0.0),
        ("4", "GND", "passive", "L", -2.54),
        ("5", "SHIELD", "passive", "L", -5.08),
        ("6", "SHIELD", "passive", "L", -7.62),
    ]
    syms["USB_A_6P"] = make_symbol(
        "USB_A_6P", "J", usba, 7.62, 15.24,
        description="USB 2.0 type A receptacle with two shell tabs")

    # 4-pin tact switch (Akizuki DTS-63-N-V-BLK)
    tact = [
        ("1", "1", "passive", "L", 1.27),
        ("2", "2", "passive", "L", -1.27),
        ("4", "4", "passive", "R", 1.27),
        ("3", "3", "passive", "R", -1.27),
    ]
    syms["SW_TACT_4P"] = make_symbol(
        "SW_TACT_4P", "SW", tact, 10.16, 6.35,
        description="Push button, 4 pins (1-2 and 3-4 internally paired)")

    # supply rails the official power library does not carry
    for rail in ("+1V1", "VBUS_PC", "VBUS_IPAD", "VBUS_USB_A"):
        syms[rail] = power_symbol(rail)
    return syms


# ---------------------------------------------------------------------------
# numbers and transforms
# ---------------------------------------------------------------------------
def fnum(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def snap(v):
    """Round a sheet coordinate to the connection grid."""
    return round(v / GRID) * GRID


def snap_up(v):
    return math.ceil(v / GRID) * GRID


def tf(x, y, rot):
    """Library coordinates (Y up) to sheet offsets (Y down) for ``rot``."""
    if rot == 0:
        return (x, -y)
    if rot == 90:
        return (-y, -x)
    if rot == 180:
        return (-x, y)
    if rot == 270:
        return (y, x)
    raise ValueError(rot)


def tf_dir(angle, rot):
    """Sheet direction pointing away from the symbol body for a pin."""
    a = math.radians(angle + 180.0)
    dx = round(math.cos(a), 6)
    dy = round(math.sin(a), 6)
    return tf(dx, dy, rot)


# ---------------------------------------------------------------------------
# design data
# ---------------------------------------------------------------------------
LIB_FILES = {
    "RP2040": ("MCU_RaspberryPi.kicad_sym", "RP2040"),
    "W25Q128JVS": ("Memory_Flash.kicad_sym", "W25Q128JVS"),
    "AP2112K-3.3": ("Regulator_Linear.kicad_sym", "AP2112K-3.3"),
    "USBLC6-2SC6": ("Power_Protection.kicad_sym", "USBLC6-2SC6"),
    "USB_C_Receptacle_USB2.0_16P": ("Connector.kicad_sym", "USB_C_Receptacle_USB2.0_16P"),
    "TestPoint": ("Connector.kicad_sym", "TestPoint"),
    "Crystal_GND24": ("Device.kicad_sym", "Crystal_GND24"),
    "R": ("Device.kicad_sym", "R"),
    "C": ("Device.kicad_sym", "C"),
    "C_Polarized": ("Device.kicad_sym", "C_Polarized"),
    "D_Schottky": ("Device.kicad_sym", "D_Schottky"),
    "LED": ("Device.kicad_sym", "LED"),
    "SW_SPDT": ("Switch.kicad_sym", "SW_SPDT"),
    "PWR_FLAG": ("power.kicad_sym", "PWR_FLAG"),
    "GND": ("power.kicad_sym", "GND"),
    "+5V": ("power.kicad_sym", "+5V"),
    "+3V3": ("power.kicad_sym", "+3V3"),
}

SYMBOL_OF = {
    "U1": "RP2040", "U2": "W25Q128JVS", "U3": "CH345T", "U4": "AP2112K-3.3",
    "U5": "TPS2553DBVR", "U6": "USBLC6-2SC6", "U7": "USBLC6-2SC6",
    "U8": "USBLC6-2SC6", "J1": "USB_C_Receptacle_USB2.0_16P",
    "J2": "USB_A_6P", "J3": "USB_C_Receptacle_USB2.0_16P",
    "X1": "Crystal_GND24", "X2": "Crystal_GND24",
    "D1": "D_Schottky", "D2": "D_Schottky", "LED1": "LED",
    "SW1": "SW_SPDT", "SW2": "SW_SPDT", "SW3": "SW_SPDT", "SW4": "SW_SPDT",
    "SW6": "SW_TACT_4P", "C27": "C_Polarized",
}
for _i in range(1, 20):
    SYMBOL_OF[f"R{_i}"] = "R"
for _i in range(1, 31):
    SYMBOL_OF[f"C{_i}"] = "C"
for _i in range(1, 13):
    SYMBOL_OF[f"TP{_i}"] = "TestPoint"

ROTATION = {
    ref: (90 if sym in ("R", "C", "C_Polarized", "D_Schottky", "LED") else 0)
    for ref, sym in SYMBOL_OF.items()
}

# netlist footprint -> KiCad footprint field (names without ":" live in lib/)
FOOTPRINT = {
    "QFN-56_7x7mm_P0.4mm": "Package_DFN_QFN:QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm",
    "SOIC-8_3.9x4.9mm_P1.27mm": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
    "SSOP-20_5.3x7.2mm_P0.65mm": f"{LIB_NAME}:SSOP-20_5.3x7.2mm_P0.65mm",
    "SOT-23-5": "Package_TO_SOT_SMD:SOT-23-5",
    "SOT-23-6": "Package_TO_SOT_SMD:SOT-23-6",
    "USB_C_Receptacle_HRO_TYPE-C-31-M-12":
        f"{LIB_NAME}:USB_C_Receptacle_HRO_TYPE-C-31-M-12",
    "USB_A_Neltron_5075AR-04-WH": f"{LIB_NAME}:USB_A_Neltron_5075AR-04-WH",
    "Crystal_SMD_3225-4Pin_3.2x2.5mm": "Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm",
    "D_SOD-323": "Diode_SMD:D_SOD-323",
    "LED_0603_1608Metric": "LED_SMD:LED_0603_1608Metric",
    "SW_SPDT_NKK_115643_Slide": f"{LIB_NAME}:SW_SPDT_NKK_115643_Slide",
    "SW_TACT_Akizuki_DTS63": f"{LIB_NAME}:SW_TACT_Akizuki_DTS63",
    "R_0603_1608Metric": "Resistor_SMD:R_0603_1608Metric",
    "C_0603_1608Metric": "Capacitor_SMD:C_0603_1608Metric",
    "C_0805_2012Metric": "Capacitor_SMD:C_0805_2012Metric",
    "C_1210_3225Metric": "Capacitor_SMD:C_1210_3225Metric",
    "CP_Radial_D6.3mm_P2.5mm": "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm",
    "TestPoint_1P": f"{LIB_NAME}:TestPoint_1P",
}

OFFICIAL_FP_LIBS = ["Capacitor_SMD", "Capacitor_THT", "Crystal", "Diode_SMD",
                    "LED_SMD", "Package_DFN_QFN", "Package_SO",
                    "Package_TO_SOT_SMD", "Resistor_SMD"]

BLOCKS = [
    ("column1", "RP2040 core and decoupling", [
        "U1",
        "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8",
        "C9", "C10", "C11", "C12", "C13", "C14", "C15", "C16",
    ]),
    ("column1", "Switches", ["SW1", "SW2", "SW3", "SW6"]),
    ("column1", "USB-MIDI device (iPad) - CH345T", [
        "J3", "U3", "U8", "X2", "R7", "R8", "R16", "R17", "R18",
        "C19", "C22", "C23", "C25", "TP11",
    ]),
    ("column2", "USB-A host (KORG microKEY2) - PIO-USB", [
        "J2", "U6", "U5", "SW4", "R3", "R4", "R9", "R10", "R11",
        "C26", "C27", "TP12",
    ]),
    ("column2", "USB-C device (PC) - native USB / NKRO HID", [
        "J1", "U7", "R1", "R2", "R5", "R6", "C24",
    ]),
    ("column2", "Power: VBUS OR-ing and 3V3 LDO", [
        "D1", "D2", "U4", "C20", "C21", "C28", "C29", "C30",
    ]),
    ("column2", "QSPI flash, crystal, debug and status", [
        "U2", "X1", "R12", "R13", "R14", "R15", "R19",
        "C17", "C18", "LED1",
        "TP1", "TP2", "TP3", "TP4", "TP5", "TP6", "TP7", "TP8", "TP9", "TP10",
    ]),
]

POWER_NETS = ["+5V", "+3V3", "+1V1", "GND", "VBUS_PC", "VBUS_IPAD", "VBUS_USB_A"]
# nets that contain no power-output pin and therefore need a PWR_FLAG
POWER_NET_SET = set(POWER_NETS)
FLAGGED_NETS = ["+5V", "GND", "VBUS_PC", "VBUS_IPAD"]


def power_rotation(direction):
    """Orient a power symbol so that its graphic points away from the pin."""
    dx, dy = direction
    if dx > 0:
        return 90
    if dx < 0:
        return 270
    return 0 if dy < 0 else 180


# ---------------------------------------------------------------------------
# component layout
# ---------------------------------------------------------------------------
def label_extent(text):
    return len(text) * CHAR_W


def item_box(item):
    """Bounding box of a placed component relative to its origin."""
    pins, rot = item["pins"], item["rot"]
    xs, ys, groups = [], [], {}
    for num, pin in pins.items():
        p = tf(pin["x"], pin["y"], rot)
        groups.setdefault((round(p[0], 3), round(p[1], 3)), []).append(num)
        xs.append(p[0])
        ys.append(p[1])
    for gx, gy in groups:
        net = item["nets"][groups[(gx, gy)][0]]
        if net is None:
            continue
        dx, dy = tf_dir(pins[groups[(gx, gy)][0]]["angle"], rot)
        ex, ey = gx + dx * STUB, gy + dy * STUB
        if net in POWER_NET_SET:
            ext = POWER_EXTENT
            side = 4.0
        else:
            ext = label_extent(net)
            side = 1.0
        if dx != 0:
            xs += [ex, ex + dx * ext]
            ys += [ey - side, ey + side]
        else:
            ys += [ey, ey + dy * ext]
            xs += [ex - side, ex + side]
    for gx, gy in graphic_points(item["libsym"]):
        p = tf(gx, gy, rot)
        xs.append(p[0])
        ys.append(p[1])
    body_top, body_bottom = min(ys), max(ys)
    half_text = max(label_extent(item["value"]), label_extent(item["ref"])) / 2.0
    xs += [-half_text - 1.0, half_text + 1.0]
    ys += [body_top - 4.5, body_bottom + 4.5]
    item.update(minx=min(xs), miny=min(ys), maxx=max(xs), maxy=max(ys),
                body_top=body_top, body_bottom=body_bottom, groups=groups)
    item["w"] = item["maxx"] - item["minx"]
    item["h"] = item["maxy"] - item["miny"]


def build_items(components, libsyms):
    items = []
    for ref, comp in components.items():
        name = SYMBOL_OF[ref]
        libsym = libsyms[name]
        pins = symbol_pins(libsym)
        if set(pins) != set(comp["pins"]):
            raise SystemExit(f"{ref}: symbol {name} pins {sorted(pins)} "
                             f"!= netlist pins {sorted(comp['pins'])}")
        item = {"ref": ref, "value": comp["value"], "comp": comp, "symbol": name,
                "libsym": libsym, "pins": pins, "rot": ROTATION[ref],
                "nets": comp["pins"]}
        item_box(item)
        items.append(item)
    return items


def pack(items, x0, y0, width):
    pos = {}
    x, y = snap(x0), snap(y0)
    shelf_h = 0.0
    for item in items:
        if x > snap(x0) and x + item["w"] > x0 + width:
            y = snap(y + shelf_h + SHELF_H_GAP)
            x = snap(x0)
            shelf_h = 0.0
        pos[item["ref"]] = (snap(x - item["minx"]), snap(y - item["miny"]))
        x = snap(x + snap_up(item["w"]) + SHELF_GAP)
        shelf_h = max(shelf_h, snap_up(item["h"]))
    return pos, y + shelf_h - snap(y0)


def layout(items, col_width, top):
    positions, blocks = {}, []
    by_ref = {i["ref"]: i for i in items}
    col = {"column1": 0, "column2": 1}
    y = {"column1": top, "column2": top}
    for column, caption, refs in BLOCKS:
        x0 = MARGIN + col[column] * (col_width + COL_GAP)
        y[column] += CAPTION_FONT + 3.0
        pos, height = pack([by_ref[r] for r in refs], x0, y[column], col_width)
        positions.update(pos)
        blocks.append({"caption": caption, "x": x0,
                       "y": y[column] - CAPTION_FONT - 2.5})
        y[column] += height + 9.0
    return positions, blocks, y


# ---------------------------------------------------------------------------
# schematic emission
# ---------------------------------------------------------------------------
_UUID_COUNTER = [0]


def u():
    """Deterministic UUIDs keep regenerated schematics diff-friendly."""
    _UUID_COUNTER[0] += 1
    return str(uuid.uuid5(uuid.NAMESPACE_URL,
                          f"{PROJECT}/{_UUID_COUNTER[0]}"))


def mklabel(net, x, y, direction):
    dx, dy = direction
    if dx > 0:
        angle, just = 0, "left"
    elif dx < 0:
        angle, just = 0, "right"
    elif dy < 0:
        angle, just = 90, "left"
    else:
        angle, just = 90, "right"
    return ["label", Q(net), ["at", fnum(x), fnum(y), str(angle)],
            ["effects", ["font", ["size", "1.27", "1.27"]],
             ["justify", just, "bottom"]],
            ["uuid", Q(u())]]


def emit_symbol(item, x, y, footprint, lcsc, datasheet):
    ref, rot = item["ref"], item["rot"]
    out = ["symbol",
           ["lib_id", Q(f"{LIB_NAME}:{item['symbol']}")],
           ["at", fnum(x), fnum(y), str(rot)],
           ["unit", "1"],
           ["exclude_from_sim", "no"], ["in_bom", "yes"], ["on_board", "yes"],
           ["dnp", "no"], ["fields_autoplaced", "yes"], ["uuid", Q(u())],
           ["property", Q("Reference"), Q(ref),
            ["at", fnum(x), fnum(y + item["body_top"] - 2.2), "0"], _effects()],
           ["property", Q("Value"), Q(item["value"]),
            ["at", fnum(x), fnum(y + item["body_bottom"] + 3.2), "0"], _effects()],
           ["property", Q("Footprint"), Q(footprint),
            ["at", fnum(x), fnum(y), "0"], ["hide", "yes"], _effects()],
           ["property", Q("Datasheet"), Q(datasheet),
            ["at", fnum(x), fnum(y), "0"], ["hide", "yes"], _effects()]]
    if lcsc:
        out.append(["property", Q("LCSC"), Q(lcsc), ["at", fnum(x), fnum(y), "0"],
                    ["hide", "yes"], _effects()])
    for num in item["pins"]:
        out.append(["pin", Q(num), ["uuid", Q(u())]])
    out.append(["instances", ["project", Q(PROJECT),
                              ["path", Q("/" + ROOT_UUID),
                               ["reference", Q(ref)], ["unit", "1"]]]])
    return out


def emit_power(symbol, ref, x, y, rot=0):
    return ["symbol", ["lib_id", Q(f"{LIB_NAME}:{symbol}")],
            ["at", fnum(x), fnum(y), str(rot)], ["unit", "1"],
            ["exclude_from_sim", "no"], ["in_bom", "no"], ["on_board", "no"],
            ["dnp", "no"], ["fields_autoplaced", "yes"], ["uuid", Q(u())],
            ["property", Q("Reference"), Q(ref),
             ["at", fnum(x), fnum(y + 6.35), "0"], ["hide", "yes"], _effects()],
            ["property", Q("Value"), Q(symbol),
             ["at", fnum(x), fnum(y - 2.5), "0"], _effects()],
            ["property", Q("Footprint"), Q(""), ["at", fnum(x), fnum(y), "0"],
             ["hide", "yes"], _effects()],
            ["property", Q("Datasheet"), Q(""), ["at", fnum(x), fnum(y), "0"],
             ["hide", "yes"], _effects()],
            ["pin", Q("1"), ["uuid", Q(u())]],
            ["instances", ["project", Q(PROJECT),
                           ["path", Q("/" + ROOT_UUID),
                            ["reference", Q(ref)], ["unit", "1"]]]]]


def emit_rails(x0, y0, first_ref):
    """Power symbol + PWR_FLAG for every net that has no power output pin."""
    out, wires = [], []
    pitch, down = 48.26, 7.62
    for i, net in enumerate(FLAGGED_NETS):
        x = snap(x0 + (i % 2) * pitch)
        y = snap(y0 + (i // 2) * 24.13)
        out.append(emit_power(net, f"#PWR{first_ref + i + 1:03d}", x, y))
        out.append(emit_power("PWR_FLAG", f"#FLG{i + 1:02d}", x, y + down, rot=180))
        wires.append(["wire", ["pts", ["xy", fnum(x), fnum(y)],
                               ["xy", fnum(x), fnum(y + down)]],
                      ["stroke", ["width", "0"], ["type", "default"]],
                      ["uuid", Q(u())]])
    return out + wires


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    netlist = yaml.safe_load((ROOT / "netlist.yaml").read_text(encoding="utf-8"))
    components = netlist["components"]

    lcsc = {}
    bom = ROOT / "bom.csv"
    if bom.exists():
        with bom.open(encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                for ref in row["ref"].replace('"', "").split(","):
                    if row.get("lcsc"):
                        lcsc[ref.strip()] = row["lcsc"]

    libsyms = {}
    for name, (filename, symbol) in LIB_FILES.items():
        libsyms[name] = flatten_symbol(lib_tree(filename), symbol)
    libsyms.update(custom_symbols())

    unknown = sorted(set(SYMBOL_OF) - set(components))
    if unknown:
        raise SystemExit(f"symbol map knows parts that are not in the netlist: {unknown}")
    unmapped = sorted(set(components) - set(SYMBOL_OF))
    if unmapped:
        raise SystemExit(f"no symbol for {unmapped}")

    blocked = [ref for _, _, refs in BLOCKS for ref in refs]
    if sorted(blocked) != sorted(components):
        raise SystemExit(f"block list mismatch: missing {sorted(set(components) - set(blocked))}, "
                         f"extra {sorted(set(blocked) - set(components))}, "
                         f"duplicates {sorted({r for r in blocked if blocked.count(r) > 1})}")

    items = build_items(components, libsyms)

    chosen = None
    for paper in PAPER_ORDER:
        width, height = PAPER[paper]
        col_width = (width - 2 * MARGIN - COL_GAP) / 2.0
        positions, blocks, col_y = layout(items, col_width, MARGIN + 16.51)
        short = min(col_y, key=col_y.get)
        rail_y = col_y[short] + 8.0
        if rail_y + 48.0 <= height - MARGIN:
            chosen = (paper, width, height, col_width, positions, blocks, col_y, short, rail_y)
            break
    if chosen is None:
        raise SystemExit("schematic does not fit on A0")
    (paper, width, height, col_width, positions, blocks,
     col_y, rail_col, rail_y) = chosen
    print(f"paper {paper} ({width:.0f} x {height:.0f} mm), columns end at "
          f"{col_y['column1']:.1f}/{col_y['column2']:.1f} mm")

    boxes = []
    for item in items:
        x, y = positions[item["ref"]]
        boxes.append((item["ref"], x + item["minx"], y + item["miny"],
                      x + item["maxx"], y + item["maxy"]))
    for i, (ra, ax0, ay0, ax1, ay1) in enumerate(boxes):
        if ax0 < 2.0 or ay0 < 2.0 or ax1 > width - 2.0 or ay1 > height - 2.0:
            raise SystemExit(f"{ra} leaves the sheet: {ax0:.1f},{ay0:.1f} -> "
                             f"{ax1:.1f},{ay1:.1f}")
        for rb, bx0, by0, bx1, by1 in boxes[i + 1:]:
            if ax0 < bx1 - 0.2 and bx0 < ax1 - 0.2 and ay0 < by1 - 0.2 and by0 < ay1 - 0.2:
                raise SystemExit(f"{ra} and {rb} overlap")

    used = sorted({item["symbol"] for item in items} | set(POWER_NETS) | {"PWR_FLAG"})
    embedded = []
    for name in used:
        node = copy.deepcopy(libsyms[name])
        node[1] = Q(f"{LIB_NAME}:{name}")
        embedded.append(node)

    out = ["kicad_sch",
           ["version", "20250610"],
           ["generator", Q("eeschema")],
           ["generator_version", Q("10.0")],
           ["uuid", Q(ROOT_UUID)],
           ["paper", Q(paper)],
           ["title_block",
            ["title", Q("RP2040 Frisk MIDI bridge")],
            ["date", Q("2026-11-23")],
            ["rev", Q("A")],
            ["comment", "1", Q("Board 62.0 x 35.0 mm, 4 layers, 1.6 mm")],
            ["comment", "2", Q("RP2040 PIO-USB host + native USB HID + CH345T USB-MIDI")],
            ["comment", "3", Q("Generated from hardware/rp2040_frisk/netlist.yaml")]],
           ["lib_symbols"] + embedded]

    wires, labels, noconnects = [], [], []
    pwr_count = 0

    for item in items:
        x, y = positions[item["ref"]]
        footprint = FOOTPRINT[item["comp"]["footprint"]]
        datasheet = ""
        dsym = prop(item["libsym"], "Datasheet")
        if dsym is not None and str(dsym[2]) not in ("", "~"):
            datasheet = str(dsym[2])
        out.append(emit_symbol(item, x, y, footprint,
                               lcsc.get(item["ref"], ""), datasheet))

        for (gx, gy), nums in item["groups"].items():
            nets = {item["nets"][n] for n in nums}
            if len(nets) != 1:
                raise SystemExit(f"{item['ref']}: pins {nums} share a point "
                                 f"but have nets {sorted(map(str, nets))}")
            net = nets.pop()
            px, py = x + gx, y + gy
            if net is None:
                noconnects.append(["no_connect", ["at", fnum(px), fnum(py)],
                                   ["uuid", Q(u())]])
                continue
            dx, dy = tf_dir(item["pins"][nums[0]]["angle"], item["rot"])
            ex, ey = px + dx * STUB, py + dy * STUB
            wires.append(["wire", ["pts", ["xy", fnum(px), fnum(py)],
                                   ["xy", fnum(ex), fnum(ey)]],
                          ["stroke", ["width", "0"], ["type", "default"]],
                          ["uuid", Q(u())]])
            if net in POWER_NET_SET:
                pwr_count += 1
                out.append(emit_power(net, f"#PWR{pwr_count:03d}", ex, ey,
                                      rot=power_rotation((dx, dy))))
            else:
                labels.append(mklabel(net, ex, ey, (dx, dy)))

    rail_x = MARGIN + (0 if rail_col == "column1" else 1) * (col_width + COL_GAP)
    rail_y = snap(rail_y)
    blocks.append({"caption": "Power rails with PWR_FLAG", "x": rail_x,
                   "y": rail_y - 3.0})
    rails = emit_rails(rail_x, rail_y + 6.0, pwr_count)
    out += rails

    for block in blocks:
        out.append(["text", Q(block["caption"]),
                    ["exclude_from_sim", "no"],
                    ["at", fnum(block["x"]), fnum(block["y"]), "0"],
                    ["effects", ["font", ["size", fnum(CAPTION_FONT),
                                          fnum(CAPTION_FONT)]],
                     ["justify", "left", "bottom"]],
                    ["uuid", Q(u())]])

    out += wires + labels + noconnects
    out.append(["embedded_fonts", "no"])

    (ROOT / f"{PROJECT}.kicad_sch").write_text(dump(out) + "\n", encoding="utf-8")

    lib = ["kicad_symbol_lib", ["version", "20251024"],
           ["generator", Q("kicad_symbol_editor")], ["generator_version", Q("10.0")]]
    lib += [copy.deepcopy(libsyms[n]) for n in used]
    (ROOT / "lib").mkdir(exist_ok=True)
    (ROOT / "lib" / f"{LIB_NAME}.kicad_sym").write_text(dump(lib) + "\n",
                                                        encoding="utf-8")

    (ROOT / "sym-lib-table").write_text(
        "(sym_lib_table\n\t(version 7)\n"
        f'\t(lib (name "{LIB_NAME}")(type "KiCad")'
        f'(uri "${{KIPRJMOD}}/lib/{LIB_NAME}.kicad_sym")(options "")'
        '(descr "RP2040 frisk project symbols"))\n)\n', encoding="utf-8")

    fp_entries = [f'\t(lib (name "{LIB_NAME}")(type "KiCad")'
                  f'(uri "${{KIPRJMOD}}/lib/{LIB_NAME}.pretty")(options "")'
                  '(descr "RP2040 frisk project footprints"))']
    for libname in OFFICIAL_FP_LIBS:
        fp_entries.append(f'\t(lib (name "{libname}")(type "KiCad")'
                          f'(uri "${{KICAD10_FOOTPRINT_DIR}}/{libname}.pretty")'
                          '(options "")(descr "official KiCad footprints"))')
    (ROOT / "fp-lib-table").write_text(
        "(fp_lib_table\n\t(version 7)\n" + "\n".join(fp_entries) + "\n)\n",
        encoding="utf-8")

    (ROOT / f"{PROJECT}.kicad_pro").write_text(PROJECT_FILE, encoding="utf-8")

    n_nets = len({n for c in components.values() for n in c["pins"].values() if n})
    print(f"wrote {PROJECT}.kicad_sch: {len(items)} symbols, {len(labels)} labels, "
          f"{len(noconnects)} no-connects, {n_nets} nets")


PROJECT_FILE = """{
  "board": {
    "design_settings": {
      "defaults": {},
      "rules": {
        "min_clearance": 0.127,
        "min_track_width": 0.127,
        "min_via_diameter": 0.5,
        "min_through_hole_diameter": 0.3
      }
    }
  },
  "boards": [],
  "libraries": {
    "pinned_footprint_libs": [],
    "pinned_symbol_libs": []
  },
  "meta": {
    "filename": "rp2040_frisk.kicad_pro",
    "version": 1
  },
  "net_settings": {
    "classes": [
      {
        "name": "Default",
        "clearance": 0.127,
        "track_width": 0.15,
        "via_diameter": 0.5,
        "via_drill": 0.3,
        "diff_pair_width": 0.2,
        "diff_pair_gap": 0.2,
        "wire_width": 6.0,
        "bus_width": 12.0,
        "line_style": 0,
        "microvia_diameter": 0.3,
        "microvia_drill": 0.1,
        "pcb_color": "rgba(0, 0, 0, 0.000)",
        "schematic_color": "rgba(0, 0, 0, 0.000)"
      }
    ],
    "meta": {
      "version": 1
    },
    "net_colors": null
  },
  "pcbnew": {
    "page_layout_descr_file": ""
  },
  "sheets": [],
  "text_variables": {}
}
"""


if __name__ == "__main__":
    main()
