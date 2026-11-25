#!/usr/bin/env python3
"""Generate hardware/rp2040_midi_bridge/rp2040_midi_bridge.kicad_pcb from netlist.yaml.

Run inside the KiCad container, e.g.

    ./scripts/kicad.sh python3 hardware/rp2040_midi_bridge/scripts/gen_pcb.py
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path

import pcbnew
import yaml

import silk_art

ROOT = Path(__file__).resolve().parent.parent          # hardware/rp2040_midi_bridge
PROJ_LIB = ROOT / "lib" / "rp2040_midi_bridge.pretty"
KICAD_LIB = Path("/usr/share/kicad/footprints")
PCB_PATH = ROOT / "rp2040_midi_bridge.kicad_pcb"

MM = pcbnew.FromMM
TOMM = pcbnew.ToMM

BOARD_W = 58.0
BOARD_H = 44.0
CHAMFER = 2.0
EDGE_CLEARANCE = 0.3

LAYER_F = pcbnew.F_Cu
LAYER_IN1 = pcbnew.In1_Cu
LAYER_IN2 = pcbnew.In2_Cu
LAYER_B = pcbnew.B_Cu

# ---------------------------------------------------------------------------
# footprints: netlist name -> (directory, footprint file stem)
# ---------------------------------------------------------------------------
FOOTPRINTS = {
    "QFN-56_7x7mm_P0.4mm": (KICAD_LIB / "Package_DFN_QFN.pretty",
                            "QFN-56-1EP_7x7mm_P0.4mm_EP3.2x3.2mm", "Package_DFN_QFN"),
    "SOIC-8_3.9x4.9mm_P1.27mm": (KICAD_LIB / "Package_SO.pretty",
                                 "SOIC-8_3.9x4.9mm_P1.27mm", "Package_SO"),
    "SSOP-20_5.3x7.2mm_P0.65mm": (PROJ_LIB, "SSOP-20_5.3x7.2mm_P0.65mm", "rp2040_midi_bridge"),
    "SOT-23-5": (KICAD_LIB / "Package_TO_SOT_SMD.pretty", "SOT-23-5", "Package_TO_SOT_SMD"),
    "SOT-23-6": (KICAD_LIB / "Package_TO_SOT_SMD.pretty", "SOT-23-6", "Package_TO_SOT_SMD"),
    "USB_C_Receptacle_HRO_TYPE-C-31-M-12": (PROJ_LIB,
                                            "USB_C_Receptacle_HRO_TYPE-C-31-M-12",
                                            "rp2040_midi_bridge"),
    "USB_A_Neltron_5075AR-04-WH": (PROJ_LIB, "USB_A_Neltron_5075AR-04-WH", "rp2040_midi_bridge"),
    "Crystal_SMD_3225-4Pin_3.2x2.5mm": (KICAD_LIB / "Crystal.pretty",
                                        "Crystal_SMD_3225-4Pin_3.2x2.5mm", "Crystal"),
    "D_SOD-323": (KICAD_LIB / "Diode_SMD.pretty", "D_SOD-323", "Diode_SMD"),
    "LED_0603_1608Metric": (KICAD_LIB / "LED_SMD.pretty", "LED_0603_1608Metric", "LED_SMD"),
    "R_0603_1608Metric": (KICAD_LIB / "Resistor_SMD.pretty", "R_0603_1608Metric",
                          "Resistor_SMD"),
    "C_0603_1608Metric": (KICAD_LIB / "Capacitor_SMD.pretty", "C_0603_1608Metric",
                          "Capacitor_SMD"),
    "C_0805_2012Metric": (KICAD_LIB / "Capacitor_SMD.pretty", "C_0805_2012Metric",
                          "Capacitor_SMD"),
    "C_1210_3225Metric": (KICAD_LIB / "Capacitor_SMD.pretty",
                                "C_1210_3225Metric", "Capacitor_SMD"),
    "SW_SPDT_NKK_115643_Slide": (PROJ_LIB, "SW_SPDT_NKK_115643_Slide", "rp2040_midi_bridge"),
    "SW_TACT_Akizuki_DTS63": (PROJ_LIB, "SW_TACT_Akizuki_DTS63", "rp2040_midi_bridge"),
    "SW_Push_1P1T-SH_NO_CK_KMR2xxG": (KICAD_LIB / "Button_Switch_SMD.pretty",
                                      "SW_Push_1P1T-SH_NO_CK_KMR2xxG",
                                      "Button_Switch_SMD"),
    "TestPoint_1P": (PROJ_LIB, "TestPoint_1P", "rp2040_midi_bridge"),
}

# ---------------------------------------------------------------------------
# placement (mm, board origin top-left, y down) and rotation
# ---------------------------------------------------------------------------
PLACEMENT = {
    # connectors and the fixed placements from design.yaml (old 62 x 35 layout)
    "J1": (16.5, 2.4, 180),
    "J3": (45.5, 2.4, 180),
    "J2": (31.0, 31.6, 180),
    # U1 in the middle: QSPI faces right toward U2, USB-A faces down toward J2
    "U1": (24.0, 17.0, 270),
    "U2": (34.5, 14.0, 0),
    "U3": (47.3, 12.5, 0),
    "U4": (11.0, 21.8, 0),
    "U5": (15.5, 24.0, 0),
    "U6": (29.5, 23.3, 0),
    "U7": (12.0, 10.3, 0),
    "U8": (40.4, 10.5, 0),
    "X1": (15.5, 17.2, 0),
    "X2": (47.5, 19.5, 0),
    "D1": (9.5, 2.5, 90),
    "D2": (37.6, 4.3, 0),
    "LED1": (21.8, 24.7, 0),
    "SW1": (5.2, 9.0, 90),
    "SW2": (5.2, 24.5, 90),
    "SW3": (55.5, 12.5, 270),
    "SW4": (15.0, 31.5, 0),
    "SW5": (31.0, 4.2, 0),
    # USB-C series resistors in the free pocket between J1 and SW5
    "R1": (24.0, 9.0, 90),
    "R2": (25.7, 8.8, 90),
    # USB-A series resistors beside U1/USBLC6
    "R3": (18.3, 20.5, 0),
    "R4": (19.5, 23.0, 0),
    # CC pulldowns next to their connector
    "R5": (21.0, 8.9, 0),
    "R6": (21.0, 10.6, 0),
    "R7": (53.5, 2.0, 0),
    "R8": (56.7, 2.0, 0),
    # TPS2553 support
    "R9": (16.0, 26.8, 0),
    "R10": (12.0, 26.6, 0),
    "R11": (50.5, 24.2, 0),
    "R12": (46.5, 24.0, 0),
    "R13": (24.6, 23.5, 270),
    "R14": (18.7, 15.5, 270),
    "R15": (38.1, 24.0, 0),
    "R16": (54.2, 5.0, 0),
    "R17": (41.5, 14.2, 90),
    "R18": (41.5, 17.5, 90),
    "R19": (30.0, 19.5, 0),
    # 1uF / +1V1 rail next to U1 and U4
    "C1": (35.0, 24.7, 0),
    "C2": (34.0, 19.5, 0),
    "C3": (35.0, 22.3, 0),
    "C14": (37.1, 19.5, 0),
    "C15": (38.1, 22.3, 0),
    # +3V3 decoupling in a two-column grid on the right edge
    "C4": (57.4, 29.0, 0),
    "C5": (53.6, 29.0, 0),
    "C6": (53.6, 19.4, 0),
    "C7": (57.4, 19.4, 0),
    "C8": (53.6, 22.6, 0),
    "C9": (57.4, 22.6, 0),
    "C10": (53.6, 25.8, 0),
    "C11": (57.4, 25.8, 0),
    "C12": (53.6, 32.2, 0),
    "C13": (57.4, 32.2, 0),
    "C16": (57.4, 6.0, 0),
    # crystal load caps and R14/R19
    "C17": (10.5, 18.2, 90),
    "C18": (10.8, 14.8, 90),
    "C19": (43.8, 18.8, 0),
    # +5V / VBUS bulk in the free lower-right area
    "C20": (41.0, 26.0, 0),
    "C21": (45.0, 26.0, 0),
    "C22": (43.0, 20.5, 0),
    "C23": (50.0, 22.3, 0),
    "C24": (23.5, 5.0, 0),
    "C25": (37.6, 6.5, 0),
    "C26": (49.0, 29.5, 0),
    "C27": (41.6, 33.0, 0),
    "C28": (49.0, 26.0, 0),
    "C29": (41.0, 29.5, 0),
    "C30": (45.0, 29.5, 0),
    # test points: debug TPs around U1, power/GND TPs at the free right edge
}

# Revision B: 58 x 44 mm board for the Muji PP small-case M.  Keep the old
# relative layout, shift the bottom group down, and add the BOOT/RUN buttons.
_X_SHIFT = -1.5
_Y_SHIFT_BOTTOM = 7.8
_SPECIAL_PLACEMENT = {
    "J1": (15.0, 2.4, 180),
    "J3": (44.0, 2.4, 180),
    "J2": (29.0, 39.4, 180),
    "SW4": (13.5, 40.0, 0),
    "SW5": (29.0, 4.2, 0),
    "SW6": (4.0, 33.5, 0),
    "SW7": (4.0, 38.0, 0),
    "R1": (22.0, 9.4, 90),
    "R2": (23.6, 9.4, 90),
    # Rotate the USBLC6 so pins 1 and 6 sit on the same side and the DP pair
    # can bridge under the package.
    "U8": (38.9, 10.5, 90),
    # Keep the USB-A series resistors out of the SW2 corridor along the bottom
    "R3": (29.0, 30.0, 0),
    "R4": (30.0, 31.8, 0),
}

def _rebase_placement(ref, x, y, rot):
    if ref in _SPECIAL_PLACEMENT:
        return _SPECIAL_PLACEMENT[ref]
    return (x + _X_SHIFT, y + (_Y_SHIFT_BOTTOM if y > 27.0 else 0.0), rot)

PLACEMENT = {ref: _rebase_placement(ref, *pos)
             for ref, pos in PLACEMENT.items()}
PLACEMENT.update(_SPECIAL_PLACEMENT)

# ---------------------------------------------------------------------------
# net rules
# ---------------------------------------------------------------------------
USB_NETS = {n for n in (
    "USB_PC_DP", "USB_PC_DM", "USB_PC_DP_MCU", "USB_PC_DM_MCU",
    "USB_A_DP", "USB_A_DM", "USB_A_DP_MCU", "USB_A_DM_MCU",
    "USB_MIDI_DP", "USB_MIDI_DM", "USB_MIDI_DP_MCU", "USB_MIDI_DM_MCU")}
POWER_WIDTH = {"+5V": 0.5, "VBUS_PC": 0.5, "VBUS_IPAD": 0.5, "VBUS_USB_A": 0.8}
PLANE_WIDTH = {"+3V3": 0.2, "+1V1": 0.2}
USB_ROUTE_ORDER = [
    "VBUS_PC", "VBUS_IPAD", "+5V", "VBUS_USB_A", "+1V1",
    "USB_PC_DP_MCU", "USB_PC_DM_MCU", "USB_PC_DP", "USB_PC_DM",
    "USB_A_DP_MCU", "USB_A_DM_MCU", "USB_A_DP", "USB_A_DM",
    "USB_MIDI_DP_MCU", "USB_MIDI_DM_MCU", "USB_MIDI_DP", "USB_MIDI_DM",
    "QSPI_SS", "QSPI_SCLK", "QSPI_SD0", "QSPI_SD1", "QSPI_SD2", "QSPI_SD3",
    "MIDI_UART_TX", "MIDI_UART_RX",
    "X1_XIN", "X1_XOUT_MCU", "X1_XOUT", "X2_XI", "X2_XO",
    "CH345_RST", "CH345_V3", "TPS_EN", "TPS_ILIM", "TPS_FAULT",
    "SW1_MUTE", "SW2_LYRE", "SW3_SUSTAIN", "SW5_RESET",
    "STATUS_LED", "LED_A", "RUN", "BOOTSEL",
    "CC1_PC", "CC2_PC", "CC1_IPAD", "CC2_IPAD",
]


TIGHT_VIA = {"SW5_RESET", "RUN", "SW3_SUSTAIN",
             "STATUS_LED", "TPS_FAULT", "USB_MIDI_DP",
             "USB_MIDI_DM", "CH345_RST", "CC1_PC", "CC1_IPAD", "CC2_IPAD",
             "+5V", "VBUS_PC", "VBUS_IPAD", "VBUS_USB_A", "+3V3"}


def rule_for(net):
    if net in POWER_WIDTH:
        return POWER_WIDTH[net], 0.2
    if net in PLANE_WIDTH:
        return PLANE_WIDTH[net], 0.127
    if net in USB_NETS:
        return 0.2, 0.127
    return 0.15, 0.127


# ---------------------------------------------------------------------------

PROJECT_TEMPLATE = {
    "board": {
        "design_settings": {
            "defaults": {},
            "diff_pair_dimensions": [],
            "drc_exclusions": [],
            "meta": {"version": 2},
            "rule_severities": {
                "silk_over_copper": "ignore",
                "silk_overlap": "ignore",
                "silk_edge_clearance": "ignore",
                "courtyards_overlap": "error",
                "starved_thermal": "error",
                "copper_edge_clearance": "error",
                "lib_footprint_issues": "warning",
            },
            "rules": {
                "allow_blind_buried_vias": False,
                "allow_microvias": False,
                "max_error": 0.005,
                "min_clearance": 0.127,
                "min_copper_edge_clearance": 0.3,
                "min_hole_clearance": 0.25,
                "min_hole_to_hole": 0.25,
                "min_microvia_diameter": 0.2,
                "min_microvia_drill": 0.1,
                "min_silk_clearance": 0.0,
                "min_silk_text_height": 0.5,
                "min_silk_text_thickness": 0.08,
                "min_through_hole_diameter": 0.3,
                "min_track_width": 0.127,
                "min_via_annular_width": 0.1,
                "min_via_diameter": 0.5,
                "use_height_for_length_calcs": True,
            },
            "track_widths": [0.0, 0.127, 0.15, 0.2, 0.4, 0.8, 1.0],
            "via_dimensions": [{"diameter": 0.5, "drill": 0.3}],
            "zones_allow_external_fillets": False,
        },
        "layer_pairs": [],
        "layer_presets": [],
        "viewports": [],
    },
    "boards": [],
    "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
    "meta": {"filename": "rp2040_midi_bridge.kicad_pro", "project": "rp2040_midi_bridge",
             "version": 3},
    "net_settings": {
        "classes": [{
            "bus_width": 12.0,
            "clearance": 0.127,
            "diff_pair_gap": 0.25,
            "diff_pair_via_gap": 0.25,
            "diff_pair_width": 0.2,
            "line_style": 0,
            "microvia_diameter": 0.3,
            "microvia_drill": 0.1,
            "name": "Default",
            "pcb_color": "rgba(0, 0, 0, 0.000)",
            "schematic_color": "rgba(0, 0, 0, 0.000)",
            "track_width": 0.15,
            "via_diameter": 0.5,
            "via_drill": 0.3,
            "wire_width": 6.0,
        }],
        "meta": {"version": 4},
        "net_colors": None,
        "netclass_assignments": None,
        "netclass_patterns": [],
    },
    "pcbnew": {
        "last_paths": {"gencad": "", "idf": "", "netlist": "", "plot": "",
                       "pos_files": "", "specctra_dsn": "", "step": "", "svg": "",
                       "vrml": ""},
        "page_layout_descr_file": "",
    },
    "text_variables": {},
}


def write_project(path):
    import json
    Path(path).write_text(json.dumps(PROJECT_TEMPLATE, indent=2) + "\n",
                          encoding="utf-8")


def outline_points():
    c = CHAMFER
    return [(c, 0.0), (BOARD_W - c, 0.0), (BOARD_W, c), (BOARD_W, BOARD_H - c),
            (BOARD_W - c, BOARD_H), (c, BOARD_H), (0.0, BOARD_H - c), (0.0, c)]


def new_board():
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetBoardThickness(MM(1.6))
    # Put the drill/place origin at the bottom-left corner so the Gerbers,
    # drill files and JLCPCB CPL share one coordinate system.
    ds.SetAuxOrigin(pcbnew.VECTOR2I(0, MM(BOARD_H)))
    ds.m_MinClearance = MM(0.1)
    ds.m_TrackMinWidth = MM(0.127)
    ds.m_ViasMinSize = MM(0.5)
    ds.m_MinThroughDrill = MM(0.3)
    ds.m_ViasMinAnnularWidth = MM(0.1)
    ds.m_CopperEdgeClearance = MM(EDGE_CLEARANCE)
    ds.m_HoleClearance = MM(0.2)
    ds.m_HoleToHoleMin = MM(0.25)
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(MM(0.1))
    nc.SetTrackWidth(MM(0.15))
    nc.SetViaDiameter(MM(0.5))
    nc.SetViaDrill(MM(0.3))
    board.SetLayerType(LAYER_IN1, pcbnew.LT_POWER)
    board.SetLayerType(LAYER_IN2, pcbnew.LT_POWER)
    board.SetLayerName(LAYER_IN1, "In1.Cu")
    board.SetLayerName(LAYER_IN2, "In2.Cu")
    return board


def add_outline(board):
    pts = outline_points()
    for a, b in zip(pts, pts[1:] + pts[:1]):
        seg = pcbnew.PCB_SHAPE(board)
        seg.SetShape(pcbnew.SHAPE_T_SEGMENT)
        seg.SetStart(pcbnew.VECTOR2I(MM(a[0]), MM(a[1])))
        seg.SetEnd(pcbnew.VECTOR2I(MM(b[0]), MM(b[1])))
        seg.SetLayer(pcbnew.Edge_Cuts)
        seg.SetWidth(MM(0.1))
        board.Add(seg)


def add_nets(board, netlist):
    for name in netlist["nets"]:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)


def load_footprint(netlist, ref):
    fp_name = netlist["components"][ref]["footprint"]
    directory, stem, nickname = FOOTPRINTS[fp_name]
    fp = pcbnew.FootprintLoad(str(directory), stem)
    if fp is None:
        raise SystemExit(f"cannot load {fp_name} for {ref}")
    fp.SetFPID(pcbnew.LIB_ID(nickname, stem))
    return fp


def place_footprints(board, netlist):
    missing = set(netlist["components"]) - set(PLACEMENT)
    if missing:
        raise SystemExit(f"no placement for {sorted(missing)}")
    fps = {}
    for ref, comp in netlist["components"].items():
        x, y, rot = PLACEMENT[ref]
        fp = load_footprint(netlist, ref)
        fp.SetPosition(pcbnew.VECTOR2I(MM(x), MM(y)))
        fp.SetOrientationDegrees(rot)
        fp.SetReference(ref)
        fp.SetValue(comp["value"])
        for txt in (fp.Reference(), fp.Value()):
            if TOMM(txt.GetTextHeight()) < 0.8:
                txt.SetTextSize(pcbnew.VECTOR2I(MM(0.8), MM(0.8)))
                txt.SetTextThickness(MM(0.12))
        board.Add(fp)
        for pad in fp.Pads():
            pin = pad.GetNumber()
            if not pin:
                continue
            net = comp["pins"].get(pin)
            if net:
                ni = board.FindNet(net)
                if ni is None:
                    raise SystemExit(f"unknown net {net} on {ref}.{pin}")
                pad.SetNet(ni)
        if ref in ("J1", "J3"):
            for pad in fp.Pads():
                pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
        # small SMD GND pads cannot host two thermal spokes
        if len(fp.Pads()) <= 2:
            for pad in fp.Pads():
                if (pad.GetNetname() == "GND" and
                        not pad.GetLayerSet().Contains(pcbnew.B_Cu)):
                    pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
        else:
            for pad in fp.Pads():
                if (pad.GetNetname() == "GND" and
                        not pad.GetLayerSet().Contains(pcbnew.B_Cu)):
                    pad.SetLocalZoneConnection(pcbnew.ZONE_CONNECTION_FULL)
        fps[ref] = fp
    return fps


def add_zones(board):
    poly = outline_points()
    for layer, net in ((LAYER_IN1, "GND"), (LAYER_IN2, "+3V3"),
                       (LAYER_F, "GND"), (LAYER_B, "GND")):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(board.FindNet(net))
        z.SetLocalClearance(MM(0.2))
        z.SetMinThickness(MM(0.25))
        z.SetThermalReliefGap(MM(0.2))
        z.SetThermalReliefSpokeWidth(MM(0.3))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
        o = z.Outline()
        o.NewOutline()
        for (x, y) in poly:
            o.Append(MM(x), MM(y))
        board.Add(z)


def add_silk(board):
    silk_art.add_art(board)


# ---------------------------------------------------------------------------
def check_placement(board, fps):
    boxes = {}
    for ref, fp in fps.items():
        poly = fp.GetCourtyard(pcbnew.F_CrtYd)
        bb = poly.BBox()
        boxes[ref] = (TOMM(bb.GetLeft()), TOMM(bb.GetTop()),
                      TOMM(bb.GetRight()), TOMM(bb.GetBottom()))
    bad = 0
    refs = sorted(boxes)
    for i, a in enumerate(refs):
        ax0, ay0, ax1, ay1 = boxes[a]
        if a not in ("J1", "J2", "J3") and (
                ax0 < -0.01 or ay0 < -0.01 or ax1 > BOARD_W + 0.01 or ay1 > BOARD_H + 0.01):
            print(f"OUTSIDE {a}: {ax0:.2f},{ay0:.2f} - {ax1:.2f},{ay1:.2f}")
        for b in refs[i + 1:]:
            bx0, by0, bx1, by1 = boxes[b]
            ox = min(ax1, bx1) - max(ax0, bx0)
            oy = min(ay1, by1) - max(ay0, by0)
            if ox > 0.001 and oy > 0.001:
                print(f"OVERLAP {a} / {b}: {ox:.2f} x {oy:.2f} mm")
                bad += 1
    print(f"{len(boxes)} footprints, {bad} courtyard overlaps")
    return bad


def report_nets(board, netlist):
    counts = {"pads": 0, "pads_with_net": 0}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            counts["pads"] += 1
            if pad.GetNetCode() > 0:
                counts["pads_with_net"] += 1
    print(f"{counts['pads']} pads, {counts['pads_with_net']} with a net, "
          f"{len(netlist['components'])} components, {len(netlist['nets'])} nets")



# ---------------------------------------------------------------------------
# routing
# ---------------------------------------------------------------------------
def pad_endpoints(fps, netlist):
    """net -> [(x, y, layers)] plus a pad lookup for the router."""
    by_net = {}
    for ref, comp in netlist["components"].items():
        fp = fps[ref]
        for pad in fp.Pads():
            pin = pad.GetNumber()
            if not pin:
                continue
            net = comp["pins"].get(pin)
            if not net:
                continue
            by_net.setdefault(net, []).append((ref, pin, pad))
    return by_net


def pad_center(fps, ref, pin):
    for pad in fps[ref].Pads():
        if pad.GetNumber() == pin:
            c = pad.GetBoundingBox().GetCenter()
            return TOMM(c.x), TOMM(c.y)
    raise SystemExit(f"no pad {ref}.{pin}")


def route(board, netlist, fps):
    import pcb_router as R

    router = R.Router(BOARD_W, BOARD_H, cell=0.05)
    router.set_outline(outline_points())
    by_net = pad_endpoints(fps, netlist)

    # every pad is an obstacle, including unconnected ones
    for ref, comp in netlist["components"].items():
        fp = fps[ref]
        for pad in fp.Pads():
            pin = pad.GetNumber()
            net = comp["pins"].get(pin) if pin else None
            if net is None:
                net = f"__nc_{ref}_{pin or 'npth'}"
            clr = rule_for(net)[1] if not net.startswith("__nc") else 0.127
            if pad.GetDrillSize().x > 0:
                clr = max(clr, 0.35)
            bb = pad.GetBoundingBox()
            layers = []
            if pad.GetLayerSet().Contains(pcbnew.F_Cu):
                layers.append("F")
            if pad.GetLayerSet().Contains(pcbnew.B_Cu):
                layers.append("B")
            router.add_pad(net, TOMM(bb.GetLeft()), TOMM(bb.GetTop()),
                           TOMM(bb.GetRight()), TOMM(bb.GetBottom()),
                           layers or ["F"], clr)

    # Type-C A6/B6 (DP) and A7/B7 (DM) are interleaved at 0.5 mm pitch, so a
    # pad-to-pad track through the pad row is impossible.  Fan the pairs out
    # above and below the pad field before anything else claims that copper.
    for ref in ("J1", "J3"):
        pins = {}
        for pad in fps[ref].Pads():
            if pad.GetNumber() in ("A6", "B6", "A7", "B7"):
                bb = pad.GetBoundingBox()
                pins[pad.GetNumber()] = (
                    TOMM(bb.GetCenter().x), TOMM(bb.GetCenter().y),
                    TOMM(bb.GetTop()), TOMM(bb.GetBottom()),
                    pad.GetNetname())
        for pair, above in ((("A6", "B6"), True), (("A7", "B7"), False)):
            p0, p1 = pins[pair[0]], pins[pair[1]]
            net = p0[4]
            y = (min(p0[2], p1[2]) - 0.33 if above
                 else max(p0[3], p1[3]) + 0.33)
            for a, b in (((p0[0], p0[1]), (p0[0], y)),
                         ((p0[0], y), (p1[0], y)),
                         ((p1[0], y), (p1[0], p1[1]))):
                router.commit_track(net, "F", a, b, 0.2, 0.0)

        # The four wide VBUS pads sit on two x positions.  Bridge them below
        # the USB data dogbones so the power net does not have to thread the
        # 0.5 mm pad field.
        vbus = {}
        for pad in fps[ref].Pads():
            if pad.GetNumber() in ("A4", "A9", "B4", "B9"):
                bb = pad.GetBoundingBox()
                x = round(TOMM(bb.GetCenter().x), 4)
                vbus[x] = (TOMM(bb.GetCenter().y), TOMM(bb.GetBottom()),
                           pad.GetNetname())
        xs = sorted(vbus)
        if len(xs) >= 2:
            net = vbus[xs[0]][2]
            yb = max(vbus[x][1] for x in xs) + 1.18
            for x in xs:
                router.commit_track(net, "F", (x, vbus[x][0]), (x, yb), 0.8, 0.0)
            router.commit_track(net, "F", (xs[0], yb), (xs[-1], yb), 0.8, 0.0)


    def endpoints(net):
        out = []
        for ref, pin, pad in by_net.get(net, []):
            bb = pad.GetBoundingBox()
            layers = "FB" if (pad.GetLayerSet().Contains(pcbnew.F_Cu) and
                              pad.GetLayerSet().Contains(pcbnew.B_Cu)) else "F"
            out.append((TOMM(bb.GetCenter().x), TOMM(bb.GetCenter().y), layers))
        return out

    def do_net(net, widths=None, via_cost=None):
        vrad = 0.225 if net in TIGHT_VIA else 0.25
        if net in skip:
            return 0, len(endpoints(net)) - 1
        pts = endpoints(net)
        if len(pts) < 2:
            return 0, 0
        width, clearance = rule_for(net)
        tries = widths or [width]
        connected = [0]
        todo = list(range(1, len(pts)))
        for w in tries:
            remaining = []
            for i in todo:
                best = min(connected, key=lambda j: math.hypot(
                    pts[i][0] - pts[j][0], pts[i][1] - pts[j][1]))
                vc = via_cost if via_cost is not None else (
                    60 if net.startswith("QSPI") else 30)
                if router.connect(net, pts[i], pts[best], w, clearance,
                                  via_cost=vc, max_expand=900000,
                                  via_radius=vrad):
                    connected.append(i)
                else:
                    remaining.append(i)
            todo = remaining
            if not todo:
                break
        return len(connected), len(todo)

    ux, uy = PLACEMENT["U1"][:2]
    # USB_PC_DP/DM sit on the same QFN side as QSPI.  Escape them inward to
    # vias inside the package outline, then run on B.Cu to the series resistors,
    # so they never compete with the QSPI channel.
    for pin, via_x, via_y in (("47", ux + 2.3, uy + 1.0),
                              ("46", ux + 2.3, uy + 1.9)):
        px, py = ux + 3.4375, uy + (1.0 if pin == "47" else 1.4)
        if pin == "47":
            router.commit_track("USB_PC_DP_MCU", "F", (px, py),
                                (via_x, via_y), 0.127, 0.0)
        else:
            router.commit_track("USB_PC_DM_MCU", "F", (px, py),
                                (px - 0.7, py), 0.127, 0.0)
            router.commit_track("USB_PC_DM_MCU", "F", (px - 0.7, py),
                                (px - 0.7, via_y), 0.127, 0.0)
            router.commit_track("USB_PC_DM_MCU", "F", (px - 0.7, via_y),
                                (via_x, via_y), 0.127, 0.0)
        net = "USB_PC_DP_MCU" if pin == "47" else "USB_PC_DM_MCU"
        router.commit_via(net, (via_x, via_y), 0.25, 0.225)
    # Run the rest of each pair to the series resistor on B.Cu and come back to
    # F.Cu on a via beside the pad.  Reading the pad position keeps this in
    # sync with the placement table.
    for net, via_y, ref in (("USB_PC_DP_MCU", uy + 1.0, "R1"),
                            ("USB_PC_DM_MCU", uy + 1.9, "R2")):
        px, py = pad_center(fps, ref, "1")
        if not router.connect(net, (ux + 2.3, via_y, "FB"), (px, py, "F"),
                              0.2, rule_for(net)[1], via_cost=20,
                              max_expand=900000, via_radius=0.225):
            print(f"UNROUTED {net} to {ref}", flush=True)

    # U1 pin 19 is ground: strap it into the exposed pad before routing so the
    # signal escapes have to go around it (it is inside the QFN footprint)
    router.commit_track("GND", "F", (ux - 3.4375, uy - 1.0),
                        (ux - 1.55, uy - 1.0), 0.2, 0.0)

    # Every SMD ground pad needs its own via: there is no F.Cu ground pour.
    gnd_ok = gnd_fail = 0
    for ref, pin, pad in by_net.get("GND", []):
        if pad.GetLayerSet().Contains(pcbnew.B_Cu):
            continue
        bb = pad.GetBoundingBox()
        p = (TOMM(bb.GetCenter().x), TOMM(bb.GetCenter().y), "F")
        _tracks, vias = router.connect_to_plane("GND", p, 0.2, 0.1, 0.225)
        if vias:
            gnd_ok += 1
        else:
            gnd_fail += 1
    print(f"GND pad vias: {gnd_ok} ok, {gnd_fail} failed", flush=True)

    # All nine +3V3 pins on U1 get their plane via before QSPI and USB claim
    # the space around the package.  Doing it at the end leaves pins 33/48/49
    # boxed in.
    prerouted_3v3 = set()
    for ref, pin, pad in by_net.get("+3V3", []):
        if ref != "U1":
            continue
        bb = pad.GetBoundingBox()
        p = (TOMM(bb.GetCenter().x), TOMM(bb.GetCenter().y), "F")
        _tracks, vias = router.connect_to_plane("+3V3", p, 0.127, 0.1, 0.225)
        if vias:
            prerouted_3v3.add((ref, pin))

    skip = {n.strip() for n in os.environ.get("PCB_SKIP_NETS", "").split(",") if n.strip()}
    skip |= {"USB_PC_DP_MCU", "USB_PC_DM_MCU"}
    report = {}

    # 1. SW2 crosses the whole left half of the board to U1 pin 18; give it
    # the corridor first, otherwise the later nets box it in.
    report["SW2_LYRE"] = do_net("SW2_LYRE", [0.2, 0.15, 0.127], via_cost=8)

    # 2. QSPI flash bus: six nets between U1 and U2, nested fan, F.Cu first
    for net in ("QSPI_SS", "QSPI_SD3", "QSPI_SD1", "QSPI_SCLK", "QSPI_SD2", "QSPI_SD0"):
        report[net] = do_net(net, [0.15, 0.127], via_cost=45)

    # 2. power before the 0.2 mm USB/CC signals: a 0.5 mm VBUS track needs
    # 0.45 mm of clearance, which no longer fits around the connectors once the
    # signal nets are in place.
    for net in ("+5V", "VBUS_PC", "VBUS_IPAD", "VBUS_USB_A"):
        w, _ = rule_for(net)
        report[net] = do_net(net, [w, 0.35, 0.25, 0.2], via_cost=25)

    # 3. core rail and crystals: local, need short clean paths
    report["+1V1"] = do_net("+1V1", [0.2, 0.15])
    for net in ("X1_XIN", "X1_XOUT_MCU", "X1_XOUT", "X2_XI", "X2_XO"):
        report[net] = do_net(net, [0.15, 0.127])

    # 4. USB and CC nets at the three connectors
    for net in ("USB_PC_DM", "USB_PC_DP",
                "USB_MIDI_DM_MCU", "USB_MIDI_DP_MCU",
                "USB_MIDI_DM", "USB_MIDI_DP",
                "CC1_PC", "CC2_PC", "CC1_IPAD", "CC2_IPAD"):
        report[net] = do_net(net, [0.2, 0.15, 0.127], via_cost=10)

    # 5. short local nets around U1
    for net in ("STATUS_LED", "RUN",
                "USB_A_DP_MCU", "USB_A_DM_MCU",
                "MIDI_UART_TX", "MIDI_UART_RX",
                "CH345_RST", "CH345_V3",
                "TPS_EN", "TPS_ILIM", "TPS_FAULT",
                "LED_A", "BOOTSEL"):
        report[net] = do_net(net, [0.2, 0.15, 0.127], via_cost=8)

    # 6. switches: fixed THT parts at the board edges.  SW3 is furthest away.
    for net in ("SW3_SUSTAIN", "SW5_RESET", "SW1_MUTE"):
        report[net] = do_net(net, [0.2, 0.15, 0.127], via_cost=6)

    # 7. USB-A data at J2
    for net in ("USB_A_DM", "USB_A_DP"):
        report[net] = do_net(net, via_cost=15)

    # +3V3 lives on the In2 plane: stub every pad to a via
    ok = fail = 0
    for ref, pin, pad in by_net.get("+3V3", []):
        if (ref, pin) in prerouted_3v3:
            ok += 1
            continue
        bb = pad.GetBoundingBox()
        p = (TOMM(bb.GetCenter().x), TOMM(bb.GetCenter().y), "F")
        tracks, vias = router.connect_to_plane("+3V3", p, 0.2, 0.127, 0.225)
        if vias:
            ok += 1
        else:
            fail += 1
    report["+3V3"] = (ok + 1, fail)

    # stitching vias in whatever free space is left
    stitched = 0
    guard = [router._dilate(int.from_bytes(bytes(router.copper[0]), "little"), 7),
             router._dilate(int.from_bytes(bytes(router.copper[1]), "little"), 7)]
    edge = router.edge_mask(0.5)

    def gnd_via(x, y):
        nonlocal stitched
        if not (0.8 < x < 60.8 and 0.8 < y < 34.6):
            return False
        i = router.idx(router.cx(x), router.cy(y))
        bit = 0xFF << (8 * i)
        if (guard[0] & bit) or (guard[1] & bit) or router.padguard[i] or edge[i]:
            return False
        if not router.commit_via("GND", (x, y)):
            return False
        disc = bytearray(router.n)
        router.stamp_disc(disc, x, y, 0.7)
        for lay in (0, 1):
            guard[lay] |= int.from_bytes(bytes(disc), "little")
        stitched += 1
        return True

    # GND vias next to the RP2040 thermal pad, outside the exposed pad
    for dx, dy in ((2.2, 2.2), (-2.2, 2.2), (2.2, -2.2), (-2.2, -2.2),
                   (2.6, 0.0), (-2.6, 0.0), (0.0, 2.6), (0.0, -2.6),
                   (3.0, 1.2), (-3.0, -1.2), (1.2, 3.0), (-1.2, -3.0)):
        gnd_via(ux + dx, uy + dy)
    for y in (0.9, 4.0, 8.0, 12.0, 16.0, 20.0, 24.0, 28.0, 32.0, 36.0, 40.0, 43.0):
        for x in (0.9, 5.0, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0,
                  50.0, 55.0, 57.0):
            gnd_via(x, y)
    print(f"GND stitching vias: {stitched}", flush=True)

    # QFN-56 escapes use the 0.127 mm minimum width
    u1 = fps["U1"].GetBoundingBox()
    qfn = (TOMM(u1.GetLeft()) - 0.1, TOMM(u1.GetTop()) - 0.1,
           TOMM(u1.GetRight()) + 0.1, TOMM(u1.GetBottom()) + 0.1)

    def width_for(layer, p0, p1, width):
        if layer != "F":
            return width
        for (x, y) in (p0, p1):
            if qfn[0] <= x <= qfn[2] and qfn[1] <= y <= qfn[3]:
                return min(width, 0.127)
        return width

    # emit the copper into the board
    for net, geom in router.net_geom.items():
        if net.startswith("__nc"):
            continue
        ni = board.FindNet(net)
        for item in geom:
            if item[0] == "trk":
                _, layer, p0, p1, width, _extra = item
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(pcbnew.VECTOR2I(MM(p0[0]), MM(p0[1])))
                t.SetEnd(pcbnew.VECTOR2I(MM(p1[0]), MM(p1[1])))
                w = width_for(layer, p0, p1, width)
                if layer == "F":
                    t.SetLayer(pcbnew.F_Cu)
                else:
                    t.SetLayer(pcbnew.B_Cu)
                t.SetWidth(MM(w))
                t.SetNet(ni)
                board.Add(t)
            else:
                _, p, drill, radius = item
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(MM(p[0]), MM(p[1])))
                v.SetWidth(MM(2 * radius))
                v.SetDrill(MM(drill))
                v.SetViaType(pcbnew.VIATYPE_THROUGH)
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
                v.SetNet(ni)
                board.Add(v)

    unrouted = sum(f for _, f in report.values())
    print(f"routed {len(report)} nets, {unrouted} unrouted pad connections")
    for net in sorted(report):
        ok, bad = report[net]
        if bad:
            print(f"  UNROUTED {net}: {bad} of {ok + bad}")
    return report


STACKUP = """	(stackup
		(layer "F.SilkS"
			(type "Top Silk Screen")
		)
		(layer "F.Paste"
			(type "Top Solder Paste")
		)
		(layer "F.Mask"
			(type "Top Solder Mask")
			(thickness 0.01)
		)
		(layer "F.Cu"
			(type "copper")
			(thickness 0.035)
		)
		(layer "dielectric 1"
			(type "prepreg")
			(thickness 0.1)
			(material "FR4")
			(epsilon_r 4.5)
			(loss_tangent 0.02)
		)
		(layer "In1.Cu"
			(type "copper")
			(thickness 0.0175)
		)
		(layer "dielectric 2"
			(type "core")
			(thickness 1.24)
			(material "FR4")
			(epsilon_r 4.5)
			(loss_tangent 0.02)
		)
		(layer "In2.Cu"
			(type "copper")
			(thickness 0.0175)
		)
		(layer "dielectric 3"
			(type "prepreg")
			(thickness 0.1)
			(material "FR4")
			(epsilon_r 4.5)
			(loss_tangent 0.02)
		)
		(layer "B.Cu"
			(type "copper")
			(thickness 0.035)
		)
		(layer "B.Mask"
			(type "Bottom Solder Mask")
			(thickness 0.01)
		)
		(layer "B.Paste"
			(type "Bottom Solder Paste")
		)
		(layer "B.SilkS"
			(type "Bottom Silk Screen")
		)
		(copper_finish "HASL lead free")
		(dielectric_constraints no)
	)
"""


def write_stackup(path):
    """Insert the JLCPCB 4-layer stackup if the file does not have one."""
    text = Path(path).read_text(encoding="utf-8")
    if "(stackup" in text:
        return
    marker = "\t(setup\n"
    i = text.find(marker)
    if i < 0:
        print("stackup: no (setup section found")
        return
    text = text[:i + len(marker)] + STACKUP + text[i + len(marker):]
    Path(path).write_text(text, encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-placement", action="store_true")
    ap.add_argument("--no-route", action="store_true")
    ap.add_argument("--out", default=str(PCB_PATH))
    args = ap.parse_args(argv)

    netlist = yaml.safe_load((ROOT / "netlist.yaml").read_text(encoding="utf-8"))
    board = new_board()
    add_outline(board)
    add_nets(board, netlist)
    fps = place_footprints(board, netlist)
    report_nets(board, netlist)
    bad = check_placement(board, fps)
    if args.check_placement:
        return 1 if bad else 0

    if not args.no_route:
        route(board, netlist, fps)

    add_zones(board)
    add_silk(board)
    board.BuildConnectivity()
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(board.Zones())
    pcbnew.SaveBoard(args.out, board)
    write_stackup(str(args.out))
    pro = Path(args.out).with_suffix(".kicad_pro")
    if not pro.exists():
        write_project(str(pro))
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
