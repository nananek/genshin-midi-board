#!/usr/bin/env python3
"""Design-rule checks for the RP2040 frisk board study.

This is not a KiCad DRC.  It checks the numbers that are easy to lose while
editing the design: connector spacing, pin conflicts, switch count, via
process limits, and the floorplan keep-outs.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
DESIGN = ROOT / "hardware" / "rp2040_frisk" / "design.yaml"


class Check:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.notes: list[str] = []

    def require(self, ok: bool, message: str) -> None:
        if ok:
            self.notes.append(f"OK   {message}")
        else:
            self.failures.append(f"FAIL {message}")

    def near(self, value: float, expected: float, tol: float, message: str) -> None:
        self.require(abs(value - expected) <= tol, f"{message}: {value:.3f} (expected {expected:.3f} +/- {tol:.3f})")


def rect(entry: dict[str, Any]) -> tuple[float, float, float, float]:
    if "body" in entry:
        return tuple(float(v) for v in entry["body"])  # type: ignore[return-value]
    if "x_mm" in entry:
        return (float(entry["x_mm"]), float(entry["y_mm"]), float(entry["w_mm"]), float(entry["h_mm"]))
    return (float(entry["x"]), float(entry["y"]), float(entry["w"]), float(entry["h"]))


def overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float], eps: float = 0.01) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (
        ax + aw <= bx + eps
        or bx + bw <= ax + eps
        or ay + ah <= by + eps
        or by + bh <= ay + eps
    )


def main() -> int:
    data = yaml.safe_load(DESIGN.read_text(encoding="utf-8"))
    c = Check()

    board = data["board"]
    W, H = float(board["width_mm"]), float(board["height_mm"])
    c.near(W, 57.6, 0.001, "board width")
    c.near(H, 31.4, 0.001, "board height")
    c.require(int(board["layers"]) == 4, "board is 4 layers")
    c.near(float(board["chamfer_mm"]), 2.0, 0.001, "corner punch cut")

    fab = data["fabrication"]
    c.require(float(fab["via_diameter_mm"]) == 0.5, "default via diameter is 0.5 mm")
    c.require(float(fab["via_drill_mm"]) == 0.3, "default via drill is 0.3 mm")
    c.require(fab["via_in_pad"] is False, "via-in-pad is forbidden")
    c.require(fab["plugged_vias"] is False, "plugged vias are forbidden")
    c.require(fab["advanced_via_process"] is False, "advanced via process is forbidden")
    c.require(0.15 not in [float(v) for v in fab["allowed_via_drills_mm"]], "0.15 mm drill is not allowed")
    c.require(0.2 not in [float(v) for v in fab["allowed_via_drills_mm"]], "0.2 mm drill is not allowed")
    c.require(0.15 not in [float(v) for v in fab["allowed_via_diameters_mm"]], "0.15 mm via diameter is not allowed")
    c.require(0.45 in [float(v) for v in fab["allowed_via_diameters_mm"]], "0.45 mm via is allowed")

    connectors = {entry["ref"]: entry for entry in data["connectors"]}
    j1, j3, j2 = connectors["J1"], connectors["J3"], connectors["J2"]
    pitch = abs(float(j3["x_mm"]) - float(j1["x_mm"]))
    c.require(pitch >= 25.0, f"USB-C centre pitch is at least 25 mm: {pitch:.2f} mm")
    c.near(pitch, 29.0, 0.001, "USB-C centre pitch")
    gap = pitch - float(j1["courtyard"][2])
    c.require(gap >= 15.0, f"USB-C courtyard gap is at least 15 mm: {gap:.2f} mm")
    c.near(gap, 18.36, 0.02, "USB-C courtyard gap")

    for ref, entry in connectors.items():
        x, y, w, h = entry["courtyard"]
        c.require(x >= 0 and y >= 0 and x + w <= W + 0.001 and y + h <= H + 0.001,
                  f"{ref} courtyard is inside the board")
        c.require(entry["edge"] in ("top", "bottom"), f"{ref} is on a long edge")

    left_margin = float(j1["courtyard"][0])
    right_margin = W - (float(j3["courtyard"][0]) + float(j3["courtyard"][2]))
    c.require(left_margin >= 5.0, f"left USB-C edge margin: {left_margin:.2f} mm")
    c.require(right_margin >= 5.0, f"right USB-C edge margin: {right_margin:.2f} mm")

    ports = {entry["id"]: entry for entry in data["ports"]}
    c.require(set(ports) == {"keyboard", "pc", "ipad"}, "three ports are defined: keyboard, PC, iPad")
    c.require(ports["keyboard"]["connector"] == "J2", "keyboard uses USB-A J2")
    c.require(ports["pc"]["connector"] == "J1", "PC uses USB-C J1")
    c.require(ports["ipad"]["connector"] == "J3", "iPad uses USB-C J3")

    pins: dict[int, str] = {}
    gpios: dict[int, str] = {}
    gpio_nets: dict[int, str] = {}
    for entry in data["pinmap"]:
        pin = entry["rp2040_pin"]
        if isinstance(pin, int):
            c.require(pin not in pins, f"RP2040 pin {pin} is used once ({entry['signal']})")
            pins[pin] = entry["signal"]
        gpio = entry["gpio"]
        if isinstance(gpio, int):
            c.require(gpio not in gpios, f"GPIO{gpio} is used once ({entry['signal']})")
            gpios[gpio] = entry["signal"]
            if entry.get("net"):
                gpio_nets[gpio] = entry["net"]

    required_gpios = {12, 13, 4, 5, 28, 29, 27, 14, 25}
    c.require(required_gpios <= set(gpios), "all required GPIOs are assigned")

    switches = data["switches"]
    c.require(len(switches) == 5, "five switches are defined")
    c.require({s["ref"] for s in switches} == {"SW1", "SW2", "SW3", "SW4", "SW6"}, "SW1..SW4 and SW6 exist")
    switch_gpios = [s["gpio"] for s in switches if s["gpio"] is not None]
    c.require(len(switch_gpios) == len(set(switch_gpios)), "switch GPIOs do not collide")
    for s in switches:
        if s["gpio"] is not None:
            c.require(s["gpio"] in gpios, f"{s['ref']} GPIO is in the pin map")
            c.require(gpio_nets.get(s["gpio"]) == s["net"],
                      f"{s['ref']} net {s['net']} matches the pin map")
    c.require(next(s for s in switches if s["ref"] == "SW4")["gpio"] is None, "SW4 is a power switch, not a GPIO input")

    smt_missing = [
        b["ref"] for b in data["bom"]
        if b["assembly"] == "SMT" and not b.get("lcsc")
    ]
    c.require(not smt_missing, f"every SMT BOM line has an LCSC part: {smt_missing}")
    c.require(any(b["assembly"] == "THT" for b in data["bom"]), "hand-solder THT parts are marked")

    rectangles: list[tuple[str, tuple[float, float, float, float]]] = []
    for entry in data["connectors"]:
        rectangles.append((entry["ref"], tuple(float(v) for v in entry["courtyard"])))
    for entry in data["placements"]:
        x, y, w, h = rect(entry)
        rectangles.append((entry["ref"], (x - w / 2, y - h / 2, w, h)))
    for entry in data["switches"]:
        rectangles.append((entry["ref"], tuple(float(v) for v in entry["body"])))

    for i, (ref_a, a) in enumerate(rectangles):
        for ref_b, b in rectangles[i + 1:]:
            if overlap(a, b):
                c.failures.append(f"FAIL floorplan overlap: {ref_a} and {ref_b}")

    for entry in data["placements"]:
        x, y, w, h = rect(entry)
        c.require(x - w / 2 >= 0 and y - h / 2 >= 0 and x + w / 2 <= W and y + h / 2 <= H,
                  f"{entry['ref']} is inside the board")
    for entry in data["switches"]:
        x, y, w, h = entry["body"]
        c.require(x >= 0 and y >= 0 and x + w <= W and y + h <= H,
                  f"{entry['ref']} body is inside the board")

    for note in c.notes:
        print(note)
    for failure in c.failures:
        print(failure, file=sys.stderr)

    print()
    print(f"{len(c.notes)} checks passed, {len(c.failures)} failed")
    return 1 if c.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
