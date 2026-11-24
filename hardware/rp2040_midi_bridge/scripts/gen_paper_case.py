#!/usr/bin/env python3
"""Generate the A4 / 1:1 paper case net for the RP2040 MIDI bridge board.

The case is a one-piece tuck box cut from 0.3 mm cardstock.  Its inner size
follows ``design.yaml``: the 62.0 x 35.0 mm board plus 0.5 mm clearance on all
four sides, 9.0 mm high.  Connector and switch openings are derived from the
same file, so moving J1 or SW3 moves the cut-out.

Only the Python standard library is used.  The PDF user space is millimetres
(1 mm = 72/25.4 pt), which keeps the print size independent of the viewer.

Usage:
    python3 hardware/rp2040_midi_bridge/scripts/gen_paper_case.py
    python3 hardware/rp2040_midi_bridge/scripts/gen_paper_case.py --pdf /tmp/case.pdf

Outputs (default):
    docs/paper_case_a4.pdf   A4 landscape, 1:1
    docs/paper_case_a4.svg   1:1 preview of the same drawing
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MM = 72.0 / 25.4
A4_W, A4_H = 297.0, 210.0

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DESIGN = ROOT / "hardware" / "rp2040_midi_bridge" / "design.yaml"
PDF_OUT = ROOT / "docs" / "paper_case_a4.pdf"
SVG_OUT = ROOT / "docs" / "paper_case_a4.svg"

# The net sits in the lower-left of the sheet, the notes in the right column.
NET_X, NET_Y = 34.0, 62.0
NOTES_X = 120.0


# ---------------------------------------------------------------------------
# YAML subset reader
#
# design.yaml is written by hand and read by other scripts with PyYAML, but the
# case generator has to stay standard-library only.  This reader understands
# the subset used by the file: block maps, block lists of scalars or maps,
# flow lists of scalars, quoted strings, numbers, null/true/false and comments.
# ---------------------------------------------------------------------------


def _strip_comment(line: str) -> str:
    out: list[str] = []
    quote = ""
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).rstrip()


def _split_flow(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    quote = ""
    cur: list[str] = []
    for ch in text:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch in "[{":
            depth += 1
            cur.append(ch)
        elif ch in "]}":
            depth -= 1
            cur.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if cur:
        parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _scalar(text: str) -> Any:
    t = text.strip()
    if t[:1] in "\"'":
        return t[1:-1]
    low = t.lower()
    if low in ("", "~", "null"):
        return None
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if t.startswith("[") and t.endswith("]"):
        return [_scalar(p) for p in _split_flow(t[1:-1])]
    if t.startswith("{") and t.endswith("}"):
        return {p.split(":", 1)[0].strip(): _scalar(p.split(":", 1)[1])
                for p in _split_flow(t[1:-1])}
    try:
        return int(t)
    except ValueError:
        pass
    try:
        return float(t)
    except ValueError:
        return t


def _is_map_entry(text: str) -> bool:
    if text[:1] in "\"'":
        return False
    key, sep, _ = text.partition(":")
    return bool(sep) and bool(key.strip()) and " " not in key.strip()


class _Lines:
    def __init__(self, text: str) -> None:
        self.lines: list[tuple[int, str]] = []
        for raw in text.splitlines():
            clean = _strip_comment(raw)
            if not clean.strip():
                continue
            if clean.strip() in ("---", "..."):
                continue
            indent = len(clean) - len(clean.lstrip(" "))
            self.lines.append((indent, clean.strip()))

    def __len__(self) -> int:
        return len(self.lines)

    def __getitem__(self, i: int) -> tuple[int, str]:
        return self.lines[i]


def _parse_block(lines: _Lines, i: int, indent: int) -> tuple[Any, int]:
    if i >= len(lines):
        return None, i
    if lines[i][1].startswith("-"):
        items: list[Any] = []
        while i < len(lines) and lines[i][0] == indent and lines[i][1].startswith("-"):
            rest = lines[i][1][1:].strip()
            i += 1
            if not rest:
                if i < len(lines) and lines[i][0] > indent:
                    value, i = _parse_block(lines, i, lines[i][0])
                else:
                    value = None
                items.append(value)
                continue
            if _is_map_entry(rest):
                sub = _Lines("")
                sub.lines.append((indent + 2, rest))
                while i < len(lines) and lines[i][0] > indent:
                    sub.lines.append(lines[i])
                    i += 1
                value, _ = _parse_block(sub, 0, indent + 2)
                items.append(value)
            else:
                items.append(_scalar(rest))
        return items, i

    result: dict[str, Any] = {}
    while i < len(lines) and lines[i][0] == indent and not lines[i][1].startswith("-"):
        key, sep, rest = lines[i][1].partition(":")
        if not sep:
            raise ValueError("expected 'key: value' in %r" % lines[i][1])
        key = key.strip()
        rest = rest.strip()
        i += 1
        if rest and not rest.startswith("#"):
            result[key] = _scalar(rest)
        elif i < len(lines) and lines[i][0] > indent:
            result[key], i = _parse_block(lines, i, lines[i][0])
        else:
            result[key] = None
    return result, i


def load_yaml(text: str) -> Any:
    """Parse the subset of YAML used by design.yaml."""
    lines = _Lines(text)
    if not len(lines):
        return None
    value, _ = _parse_block(lines, 0, lines[0][0])
    return value


def read_design(path: Path = DESIGN) -> dict[str, Any]:
    return load_yaml(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseSpec:
    """Case dimensions and tuck hardware, in millimetres."""

    clearance: float = 0.5
    height: float = 9.0
    tab_d: float = 7.0
    lid_overhang: float = 0.5
    tuck_d: float = 6.8            # tip lands at z=2.2, above the 1.6 mm board
    tuck_w: float = 14.0
    tuck_x: float = 40.5
    tuck_r: float = 2.0
    slit_len: float = 12.0
    slit_x: float = 41.5
    slit_h: float = 1.0
    slit_drop: float = 3.5
    lip_w: float = 15.0
    lip_x: float = 40.5
    lip_d: float = 7.4             # catches the tongue, stops at the board top
    paper_t: float = 0.3


# Opening sizes: (length along the wall, height, z of the lower edge).
# USB-C: 14 x 4.5 clears the plug overmould (the mouth overhangs the board).
# USB-A: 15 x 7.0.  The shell of a right-angle USB-A is 13.1 x 5.7 and sits
#     close to the top of the 9 mm wall; the extra height is deliberate.
# Slide: 7 x 3.6 covers the lever travel and the usual 2-5 mm height band.
# Tact:  8.6 x 4.4 is the body window; the press hole is in the lid.
USB_C_OPEN = (14.0, 4.5, 1.2)
USB_A_OPEN = (15.0, 7.0, 1.2)
SLIDE_OPEN = (7.0, 3.6, 1.8)
TACT_WINDOW = (8.6, 4.4, 1.8)
LED_HOLE_D = 3.0
PRESS_HOLE_D = 5.0

WALLS = ("front", "back", "left", "right", "lid")


@dataclass
class Opening:
    """A rectangular cut-out in a wall (or the front/back of the lid)."""

    ref: str
    kind: str
    wall: str
    along: float          # centre along the wall, net coordinate
    length: float         # size along the wall
    height: float         # size in z
    z0: float             # lower edge above the floor
    rect: tuple[float, float, float, float]   # net x, y, w, h
    board: tuple[float, float]                # board coordinate of the anchor


@dataclass
class Hole:
    """A circular hole in the lid."""

    ref: str
    kind: str
    center: tuple[float, float]
    diameter: float
    board: tuple[float, float]


@dataclass
class Case:
    board_w: float
    board_h: float
    board_t: float
    chamfer: float
    spec: CaseSpec
    openings: list[Opening] = field(default_factory=list)
    holes: list[Hole] = field(default_factory=list)

    @property
    def w(self) -> float:
        return self.board_w + 2.0 * self.spec.clearance

    @property
    def d(self) -> float:
        return self.board_h + 2.0 * self.spec.clearance

    @property
    def h(self) -> float:
        return self.spec.height

    # --- panel rectangles (net coordinates, y up, floor origin) -----------
    @property
    def panels(self) -> dict[str, tuple[float, float, float, float]]:
        s, W, D, H = self.spec, self.w, self.d, self.h
        return {
            "floor": (0.0, 0.0, W, D),
            "front": (0.0, -H, W, H),
            "back": (0.0, D, W, H),
            "left": (-H, 0.0, H, D),
            "right": (W, 0.0, H, D),
            "lid": (-s.lid_overhang, D + H, W + 2 * s.lid_overhang, D),
            "lip": (s.lip_x, -H - s.lip_d, s.lip_w, s.lip_d),
            "tongue": (s.tuck_x, D + H + D, s.tuck_w, s.tuck_d),
        }

    @property
    def tabs(self) -> dict[str, tuple[float, float, float, float]]:
        s, W, D, H = self.spec, self.w, self.d, self.h
        return {
            "LF": (-H, -s.tab_d, H, s.tab_d),
            "LB": (-H, D, H, s.tab_d),
            "RF": (W, -s.tab_d, H, s.tab_d),
            "RB": (W, D, H, s.tab_d),
        }

    @property
    def folds(self) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        s, W, D, H = self.spec, self.w, self.d, self.h
        return [
            ((-H, 0.0), (W + H, 0.0)),          # floor / front wall + end tabs
            ((-H, D), (W + H, D)),              # floor / back wall + end tabs
            ((0.0, 0.0), (0.0, D)),             # floor / left wall
            ((W, 0.0), (W, D)),                 # floor / right wall
            ((0.0, D + H), (W, D + H)),         # back wall / lid
            ((s.tuck_x, D + H + D), (s.tuck_x + s.tuck_w, D + H + D)),
            ((s.lip_x, -H), (s.lip_x + s.lip_w, -H)),
        ]

    def board_polygon(self) -> list[tuple[float, float]]:
        """Board outline on the floor, chamfered and y-flipped into net space."""
        c, W, D = self.chamfer, self.w, self.d
        m = self.spec.clearance
        pts = [
            (c, 0.0), (self.board_w - c, 0.0),
            (self.board_w, c), (self.board_w, self.board_h - c),
            (self.board_w - c, self.board_h), (c, self.board_h),
            (0.0, self.board_h - c), (0.0, c),
        ]
        return [(m + x, D - m - y) for x, y in pts]


def wall_rect(wall: str, u: float, z0: float, length: float, height: float,
              case: Case) -> tuple[float, float, float, float]:
    """Place a wall opening in net coordinates.

    ``u`` runs left-to-right on the front/back walls and back-to-front on the
    left/right walls.  ``z0`` is the lower edge above the floor.
    """
    W, D, H = case.w, case.d, case.h
    if wall == "back":
        return (u - length / 2.0, D + z0, length, height)
    if wall == "front":
        return (u - length / 2.0, -(z0 + height), length, height)
    if wall == "left":
        return (-(z0 + height), u - length / 2.0, height, length)
    if wall == "right":
        return (W + z0, u - length / 2.0, height, length)
    raise ValueError("wall opening cannot be on %r" % wall)


def _nearest_wall(body: list[float], board_w: float, board_h: float) -> str:
    x, y, w, h = (float(v) for v in body)
    gaps = {
        "left": x,
        "right": board_w - (x + w),
        "back": y,
        "front": board_h - (y + h),
    }
    return min(gaps, key=lambda k: gaps[k])


def build_case(design: dict[str, Any], spec: CaseSpec | None = None) -> Case:
    """Derive the case geometry from design.yaml."""
    spec = spec or CaseSpec()
    board = design["board"]
    case = Case(
        board_w=float(board["width_mm"]),
        board_h=float(board["height_mm"]),
        board_t=float(board["thickness_mm"]),
        chamfer=float(board["chamfer_mm"]),
        spec=spec,
    )

    for conn in design["connectors"]:
        ref = str(conn["ref"])
        wall = {"top": "back", "bottom": "front"}.get(conn["edge"])
        if wall is None:
            continue
        ctype = str(conn["type"])
        length, height, z0 = USB_C_OPEN if "USB-C" in ctype else USB_A_OPEN
        bx, by = float(conn["x_mm"]), float(conn["y_mm"])
        u = spec.clearance + bx
        case.openings.append(Opening(
            ref=ref, kind=ctype, wall=wall, along=u, length=length,
            height=height, z0=z0,
            rect=wall_rect(wall, u, z0, length, height, case),
            board=(bx, by),
        ))

    for sw in design["switches"]:
        ref = str(sw["ref"])
        wall = _nearest_wall(sw["body"], case.board_w, case.board_h)
        stype = str(sw["type"])
        length, height, z0 = TACT_WINDOW if stype == "tact" else SLIDE_OPEN
        bx, by = float(sw["x_mm"]), float(sw["y_mm"])
        # The left/right walls run front (net y=0) to back (net y=D), so the
        # board's top-down y has to be flipped before it becomes a wall u.
        u = (spec.clearance + bx if wall in ("front", "back")
             else case.d - spec.clearance - by)
        case.openings.append(Opening(
            ref=ref, kind=stype, wall=wall, along=u, length=length,
            height=height, z0=z0,
            rect=wall_rect(wall, u, z0, length, height, case),
            board=(bx, by),
        ))
        if stype == "tact":
            # The tact is pressed from above.  A wall window alone cannot reach
            # the stem, so the lid gets its own press hole over the switch.
            case.holes.append(Hole(
                ref=ref, kind="press", center=lid_point(case, bx, by),
                diameter=PRESS_HOLE_D, board=(bx, by),
            ))

    for part in design.get("placements", []):
        if str(part["ref"]) != "LED1":
            continue
        bx, by = float(part["x_mm"]), float(part["y_mm"])
        case.holes.append(Hole(
            ref="LED1", kind="LED", center=lid_point(case, bx, by),
            diameter=LED_HOLE_D, board=(bx, by),
        ))

    return case


def lid_point(case: Case, board_x: float, board_y: float) -> tuple[float, float]:
    """Board coordinate -> lid position, measured from the hinge at the back."""
    s = case.spec
    return (s.clearance + board_x,
            case.d + case.h + s.clearance + board_y + s.paper_t / 2.0)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _overlap(a: tuple[float, float, float, float],
             b: tuple[float, float, float, float], gap: float = 0.0) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return (ax < bx + bw + gap and bx < ax + aw + gap
            and ay < by + bh + gap and by < ay + ah + gap)


def validate(case: Case) -> list[str]:
    """Return a list of problems; an empty list means the net is sound."""
    s = case.spec
    W, D, H = case.w, case.d, case.h
    errors: list[str] = []

    # --- tuck hardware ----------------------------------------------------
    if not (s.tuck_d > s.slit_drop + s.slit_h / 2.0):
        errors.append("tuck tongue (%.1f) does not reach past the slit (%.1f)"
                      % (s.tuck_d, s.slit_drop + s.slit_h / 2.0))
    if s.lip_d < s.tuck_d:
        errors.append("inner lip (%.1f) is shallower than the tongue (%.1f)"
                      % (s.lip_d, s.tuck_d))
    if s.lip_d >= H:
        errors.append("inner lip (%.1f) reaches the floor" % s.lip_d)
    if not (s.slit_len < s.tuck_w <= s.slit_len + 3.0):
        errors.append("tuck tongue (%.1f) must be 0-3 mm wider than the slit "
                      "(%.1f) to grip" % (s.tuck_w, s.slit_len))
    if s.lip_w < s.slit_len + 2.0:
        errors.append("inner lip (%.1f) needs 1 mm of paper either side of the "
                      "slit (%.1f)" % (s.lip_w, s.slit_len))
    if s.lip_x > s.slit_x or s.lip_x + s.lip_w < s.slit_x + s.slit_len:
        errors.append("inner lip does not cover the slit")
    if s.lip_x < 0 or s.lip_x + s.lip_w > W:
        errors.append("inner lip is outside the front wall")
    if s.lip_x < s.tab_d + 0.5 or s.lip_x + s.lip_w > W - s.tab_d - 0.5:
        errors.append("inner lip runs into a front glue tab")
    if s.slit_x < 0 or s.slit_x + s.slit_len > W:
        errors.append("slit is outside the front wall")
    if s.tuck_x < 0 or s.tuck_x + s.tuck_w > W:
        errors.append("tuck tongue is outside the lid")

    # The slit and the lip must stay clear of a front-wall opening, otherwise
    # the tongue would block the plug or the plug would tear the lip.
    for opening in case.openings:
        if opening.wall != "front":
            continue
        ox, oy, ow, oh = opening.rect
        slit = (s.slit_x, -H + s.slit_drop - s.slit_h / 2.0, s.slit_len, s.slit_h)
        if _overlap(opening.rect, slit, 0.5):
            errors.append("slit runs into %s" % opening.ref)
        if ox < s.lip_x + s.lip_w and s.lip_x < ox + ow:
            errors.append("%s reaches behind the inner lip" % opening.ref)
        if ox + ow > s.lip_x - 1.0:
            errors.append("%s leaves less than 1 mm of paper before the lip fold"
                          % opening.ref)

    # --- openings ---------------------------------------------------------
    for wall in WALLS:
        wall_openings = [o for o in case.openings if o.wall == wall]
        for i, a in enumerate(wall_openings):
            for b in wall_openings[i + 1:]:
                if _overlap(a.rect, b.rect, 1.0):
                    errors.append("%s and %s are closer than 1 mm on the %s wall"
                                  % (a.ref, b.ref, wall))

    for opening in case.openings:
        if opening.z0 < 0.5 or opening.z0 + opening.height > H - 0.6:
            errors.append("%s leaves less than 0.6 mm of wall (z %.1f-%.1f)"
                          % (opening.ref, opening.z0, opening.z0 + opening.height))
        x, y, w, h = opening.rect
        if opening.wall in ("front", "back"):
            if x < 0.5 or x + w > W - 0.5:
                errors.append("%s is closer than 0.5 mm to the corner" % opening.ref)
        elif opening.wall in ("left", "right"):
            if y < 0.5 or y + h > D - 0.5:
                errors.append("%s is closer than 0.5 mm to the corner" % opening.ref)

    # --- lid holes --------------------------------------------------------
    lid = case.panels["lid"]
    hinge = case.d + case.h
    for hole in case.holes:
        cx, cy = hole.center
        r = hole.diameter / 2.0
        if cx - r < lid[0] + 1.0 or cx + r > lid[0] + lid[2] - 1.0:
            errors.append("%s hole is too close to the lid edge" % hole.ref)
        if cy + r > lid[1] + lid[3] - 1.0:
            errors.append("%s hole is too close to the tuck edge" % hole.ref)
        if cy - r < hinge + 1.5:
            errors.append("%s hole is too close to the hinge" % hole.ref)
    for i, a in enumerate(case.holes):
        for b in case.holes[i + 1:]:
            gap = math.hypot(a.center[0] - b.center[0], a.center[1] - b.center[1])
            if gap < (a.diameter + b.diameter) / 2.0 + 1.0:
                errors.append("%s and %s holes are closer than 1 mm"
                              % (a.ref, b.ref))

    # --- sheet ------------------------------------------------------------
    x0, y0, x1, y1 = net_bounds(case)
    if x0 < 8.0 or y0 < 8.0 or x1 > A4_W - 8.0 or y1 > A4_H - 8.0:
        errors.append("net does not fit the A4 sheet with an 8 mm margin "
                      "(%.1f,%.1f)-(%.1f,%.1f)" % (x0, y0, x1, y1))
    return errors


def net_bounds(case: Case) -> tuple[float, float, float, float]:
    """Sheet-space bounding box of the cut net, including the leader labels."""
    xs: list[float] = []
    ys: list[float] = []
    for x, y, w, h in list(case.panels.values()) + list(case.tabs.values()):
        xs += [x, x + w]
        ys += [y, y + h]
    for opening in case.openings:
        x, y, w, h = opening.rect
        xs += [x, x + w]
        ys += [y, y + h]
    for hole in case.holes:
        xs += [hole.center[0] - hole.diameter, hole.center[0] + hole.diameter]
        ys += [hole.center[1] - hole.diameter, hole.center[1] + hole.diameter]
    # dimension lines with their end ticks: -7 / +8 around the panels
    xs += [-case.h - 7.0 - 1.2, case.w + case.h + 8.0]
    ys += [-case.h - case.spec.lip_d - 6.0 - 1.2]
    return (min(xs) + NET_X, min(ys) + NET_Y, max(xs) + NET_X, max(ys) + NET_Y)


# ---------------------------------------------------------------------------
# Canvas: a tiny PDF writer and an SVG writer sharing one drawing routine
# ---------------------------------------------------------------------------


def _num(v: float) -> str:
    return ("%.3f" % v).rstrip("0").rstrip(".")


def text_width(s: str, size: float) -> float:
    """Rough Helvetica advance width, good enough for labels and centring."""
    return 0.52 * len(s) * size


class PdfCanvas:
    """Millimetre drawing surface that writes a one-page PDF."""

    def __init__(self, width: float = A4_W, height: float = A4_H) -> None:
        self.w, self.h = width, height
        self.ops: list[str] = []

    def line(self, x1: float, y1: float, x2: float, y2: float,
             width: float = 0.25, dash: tuple[float, float] | None = None,
             gray: float | None = None) -> None:
        d = "[%s %s] 0 d" % (_num(dash[0]), _num(dash[1])) if dash else "[] 0 d"
        g = "" if gray is None else "%s G " % _num(gray)
        close = "" if gray is None else " 0 G"
        self.ops.append("%s %s%s w %s %s m %s %s l S%s" % (
            d, g, _num(width), _num(x1), _num(y1), _num(x2), _num(y2), close))

    def rect(self, x: float, y: float, w: float, h: float, width: float = 0.25,
             dash: tuple[float, float] | None = None,
             gray: float | None = None) -> None:
        self.line(x, y, x + w, y, width, dash, gray)
        self.line(x + w, y, x + w, y + h, width, dash, gray)
        self.line(x + w, y + h, x, y + h, width, dash, gray)
        self.line(x, y + h, x, y, width, dash, gray)

    def polyline(self, pts: list[tuple[float, float]], width: float = 0.25,
                 dash: tuple[float, float] | None = None,
                 gray: float | None = None) -> None:
        for a, b in zip(pts, pts[1:]):
            self.line(a[0], a[1], b[0], b[1], width, dash, gray)

    def polygon(self, pts: list[tuple[float, float]], width: float = 0.25,
                gray: float | None = None) -> None:
        self.polyline(pts + [pts[0]], width, gray=gray)

    def circle(self, cx: float, cy: float, r: float, width: float = 0.25,
               n: int = 48) -> None:
        pts = [(cx + r * math.cos(2 * math.pi * i / n),
                cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
        self.polygon(pts, width)

    def fill(self, pts: list[tuple[float, float]], gray: float = 0.9) -> None:
        path = ["%s %s m" % (_num(pts[0][0]), _num(pts[0][1]))]
        for x, y in pts[1:]:
            path.append("%s %s l" % (_num(x), _num(y)))
        path.append("h")
        self.ops.append("%s g %s f 0 g" % (_num(gray), " ".join(path)))

    def text(self, s: str, x: float, y: float, size: float = 3.0,
             angle: float = 0.0) -> None:
        s = s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        if angle:
            c, sn = math.cos(math.radians(angle)), math.sin(math.radians(angle))
            tm = "%s %s %s %s %s %s Tm" % (
                _num(c * size), _num(sn * size), _num(-sn * size),
                _num(c * size), _num(x), _num(y))
        else:
            tm = "%s 0 0 %s %s %s Tm" % (
                _num(size), _num(size), _num(x), _num(y))
        self.ops.append("BT /F1 1 Tf %s (%s) Tj ET" % (tm, s))

    def save(self, path: Path) -> None:
        content = ("q\n%s 0 0 %s 0 0 cm\n1 J 1 j 0 G 0 g\n" % (
            _num(MM), _num(MM))) + "\n".join(self.ops) + "\nQ\n"
        stream = content.encode("latin-1")
        objs = [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            ("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %s %s] "
             "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>" % (
                 _num(self.w * MM), _num(self.h * MM))).encode("ascii"),
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"endstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
            b"/Encoding /WinAnsiEncoding >>",
        ]
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: list[int] = []
        for i, body in enumerate(objs, 1):
            offsets.append(len(out))
            out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
        for off in offsets:
            out += b"%010d 00000 n \n" % off
        out += (b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n"
                % (len(objs) + 1, xref))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes(out))


class SvgCanvas:
    """Same drawing calls, emitted as a 1:1 SVG (page in millimetres)."""

    def __init__(self, width: float = A4_W, height: float = A4_H) -> None:
        self.w, self.h = width, height
        self.ops: list[str] = ['<rect width="100%" height="100%" fill="#ffffff"/>']
        self.ops.append(
            '<style>text{font-family:Helvetica,Arial,sans-serif;fill:#000}'
            '</style>')

    def _y(self, y: float) -> float:
        return self.h - y

    def line(self, x1: float, y1: float, x2: float, y2: float,
             width: float = 0.25, dash: tuple[float, float] | None = None,
             gray: float | None = None) -> None:
        color = "#000" if gray is None else "#%02x%02x%02x" % (
            (int(255 * gray),) * 3)
        extra = ' stroke-dasharray="%s %s"' % (dash[0], dash[1]) if dash else ""
        self.ops.append(
            '<line x1="%.3f" y1="%.3f" x2="%.3f" y2="%.3f" stroke="%s" '
            'stroke-width="%.3f"%s/>' % (
                x1, self._y(y1), x2, self._y(y2), color, width, extra))

    def rect(self, x: float, y: float, w: float, h: float, width: float = 0.25,
             dash: tuple[float, float] | None = None,
             gray: float | None = None) -> None:
        color = "#000" if gray is None else "#%02x%02x%02x" % (
            (int(255 * gray),) * 3)
        extra = ' stroke-dasharray="%s %s"' % (dash[0], dash[1]) if dash else ""
        self.ops.append(
            '<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" fill="none" '
            'stroke="%s" stroke-width="%.3f"%s/>' % (
                x, self._y(y + h), w, h, color, width, extra))

    def polyline(self, pts: list[tuple[float, float]], width: float = 0.25,
                 dash: tuple[float, float] | None = None,
                 gray: float | None = None) -> None:
        for a, b in zip(pts, pts[1:]):
            self.line(a[0], a[1], b[0], b[1], width, dash, gray)

    def polygon(self, pts: list[tuple[float, float]], width: float = 0.25,
                gray: float | None = None) -> None:
        color = "#000" if gray is None else "#%02x%02x%02x" % (
            (int(255 * gray),) * 3)
        points = " ".join("%.3f,%.3f" % (x, self._y(y)) for x, y in pts)
        self.ops.append(
            '<polygon points="%s" fill="none" stroke="%s" stroke-width="%.3f"/>'
            % (points, color, width))

    def circle(self, cx: float, cy: float, r: float, width: float = 0.25,
               n: int = 48) -> None:
        self.ops.append(
            '<circle cx="%.3f" cy="%.3f" r="%.3f" fill="none" stroke="#000" '
            'stroke-width="%.3f"/>' % (cx, self._y(cy), r, width))

    def fill(self, pts: list[tuple[float, float]], gray: float = 0.9) -> None:
        color = "#%02x%02x%02x" % ((int(255 * gray),) * 3)
        points = " ".join("%.3f,%.3f" % (x, self._y(y)) for x, y in pts)
        self.ops.append('<polygon points="%s" fill="%s" stroke="none"/>'
                        % (points, color))

    def text(self, s: str, x: float, y: float, size: float = 3.0,
             angle: float = 0.0) -> None:
        s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        transform = (' transform="rotate(%.1f %.3f %.3f)"'
                     % (-angle, x, self._y(y))) if angle else ""
        self.ops.append(
            '<text x="%.3f" y="%.3f" font-size="%.3f"%s>%s</text>' % (
                x, self._y(y), size, transform, s))

    def save(self, path: Path) -> None:
        head = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                '<svg xmlns="http://www.w3.org/2000/svg" width="%gmm" '
                'height="%gmm" viewBox="0 0 %g %g">\n' % (
                    self.w, self.h, self.w, self.h))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(head + "\n".join(self.ops) + "\n</svg>\n",
                        encoding="utf-8")


class Frame:
    """Shift a canvas so the net origin (floor lower-left) is at (ox, oy)."""

    def __init__(self, canvas: Any, ox: float, oy: float) -> None:
        self.c, self.ox, self.oy = canvas, ox, oy

    def line(self, x1, y1, x2, y2, width=0.25, dash=None, gray=None) -> None:
        self.c.line(self.ox + x1, self.oy + y1, self.ox + x2, self.oy + y2,
                    width, dash, gray)

    def rect(self, x, y, w, h, width=0.25, dash=None, gray=None) -> None:
        self.c.rect(self.ox + x, self.oy + y, w, h, width, dash, gray)

    def polyline(self, pts, width=0.25, dash=None, gray=None) -> None:
        for a, b in zip(pts, pts[1:]):
            self.line(a[0], a[1], b[0], b[1], width, dash, gray)

    def polygon(self, pts, width=0.25, gray=None) -> None:
        self.polyline(list(pts) + [pts[0]], width, gray=gray)

    def circle(self, cx, cy, r, width=0.25) -> None:
        self.c.circle(self.ox + cx, self.oy + cy, r, width)

    def fill(self, pts, gray=0.9) -> None:
        self.c.fill([(self.ox + x, self.oy + y) for x, y in pts], gray)

    def text(self, s, x, y, size=3.0, angle=0.0) -> None:
        self.c.text(s, self.ox + x, self.oy + y, size, angle)

    def ctext(self, s, x, y, size=3.0, angle=0.0) -> None:
        width = text_width(s, size)
        if angle:
            self.text(s, x, y - width / 2.0, size, angle)
        else:
            self.text(s, x - width / 2.0, y - 0.35 * size, size)

    def vtext(self, s, x, y, size=3.0) -> None:
        """Text running up the page, baseline at x."""
        self.text(s, x, y - text_width(s, size) / 2.0, size, 90.0)


# ---------------------------------------------------------------------------
# Drawing
# ---------------------------------------------------------------------------


def arc_pts(cx: float, cy: float, r: float, a0: float, a1: float,
            steps: int = 16) -> list[tuple[float, float]]:
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / steps)),
             cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / steps)))
            for i in range(steps + 1)]


def dim_h(f: Frame, x1: float, x2: float, y: float, label: str,
          size: float = 2.6) -> None:
    f.line(x1, y, x2, y, 0.15)
    for x in (x1, x2):
        f.line(x, y - 1.2, x, y + 1.2, 0.15)
    f.ctext(label, (x1 + x2) / 2.0, y + 1.9, size)


def dim_v(f: Frame, x: float, y1: float, y2: float, label: str,
          size: float = 2.6) -> None:
    f.line(x, y1, x, y2, 0.15)
    for y in (y1, y2):
        f.line(x - 1.2, y, x + 1.2, y, 0.15)
    f.vtext(label, x - 1.6, (y1 + y2) / 2.0, size)


def draw_net(f: Frame, case: Case) -> None:
    s = case.spec
    W, D, H = case.w, case.d, case.h
    tabs = case.tabs
    panels = case.panels

    # --- cut outline -------------------------------------------------------
    f.rect(0.0, 0.0, W, D)                      # floor
    f.rect(0.0, D, W, H)                        # back wall
    f.rect(-H, 0.0, H, D)                       # left wall
    f.rect(W, 0.0, H, D)                        # right wall
    for x, y, w, h in tabs.values():
        f.rect(x, y, w, h)

    # Front wall with the lip dangling from the rim, in one cut path.
    f.polyline([
        (0.0, -H), (0.0, 0.0), (W, 0.0), (W, -H),
        (s.lip_x + s.lip_w, -H), (s.lip_x + s.lip_w, -H - s.lip_d),
        (s.lip_x, -H - s.lip_d), (s.lip_x, -H), (0.0, -H),
    ])

    # Lid with the tuck tongue on its far edge.
    lx, ly, lw, lh = panels["lid"]
    y0 = ly + lh
    tx, tw, td, tr = s.tuck_x, s.tuck_w, s.tuck_d, s.tuck_r
    f.polyline(
        [(lx, ly), (lx, y0), (tx, y0), (tx, y0 + td - tr)]
        + arc_pts(tx + tr, y0 + td - tr, tr, 180.0, 90.0)
        + [(tx + tw - tr, y0 + td)]
        + arc_pts(tx + tw - tr, y0 + td - tr, tr, 90.0, 0.0)
        + [(tx + tw, y0 + td - tr), (tx + tw, y0), (lx + lw, y0), (lx + lw, ly),
           (lx, ly)]
    )

    # --- fold lines: knock the cut line out, then dash it -----------------
    for a, b in case.folds:
        f.line(a[0], a[1], b[0], b[1], 0.9, gray=1.0)
    for a, b in case.folds:
        f.line(a[0], a[1], b[0], b[1], 0.22, dash=(2.2, 1.4))

    # --- openings ---------------------------------------------------------
    for opening in case.openings:
        x, y, w, h = opening.rect
        f.rect(x, y, w, h, 0.3)
        label = opening.ref
        if opening.wall == "back":
            f.ctext(label, x + w / 2.0, y + h + 1.5, 2.2)
        elif opening.wall == "front":
            f.ctext(label, x + w / 2.0, y - 1.5, 2.2)
        elif opening.wall == "left":
            f.vtext(label, -(opening.z0 + opening.height) - 1.6,
                    y + h / 2.0, 2.2)
        elif opening.wall == "right":
            f.vtext(label, W + opening.z0 + opening.height + 2.8,
                    y + h / 2.0, 2.2)

    for hole in case.holes:
        cx, cy = hole.center
        r = hole.diameter / 2.0
        f.circle(cx, cy, r, 0.3)
        f.line(cx - r - 1.2, cy, cx - r - 0.4, cy, 0.15)
        f.line(cx + r + 0.4, cy, cx + r + 1.2, cy, 0.15)
        f.line(cx, cy - r - 1.2, cx, cy - r - 0.4, 0.15)
        f.line(cx, cy + r + 0.4, cx, cy + r + 1.2, 0.15)

    # --- board outline on the floor ---------------------------------------
    poly = case.board_polygon()
    f.fill(poly, 0.945)
    f.polygon(poly, 0.18, gray=0.45)

    # --- tuck slit in the front wall --------------------------------------
    slit_y = -H + s.slit_drop
    f.rect(s.slit_x, slit_y - s.slit_h / 2.0, s.slit_len, s.slit_h, 0.3)

    # --- panel labels ------------------------------------------------------
    f.ctext("FRONT", 6.5, -H + 2.0, 2.6)
    f.ctext("LIP", s.lip_x + s.lip_w / 2.0, -H - s.lip_d / 2.0 - 1.0, 2.6)
    f.ctext("BACK", 6.5, D + 2.4, 2.6)
    f.ctext("LID", W / 2.0, D + H + D / 2.0 - 1.0, 4.2)
    f.ctext("TUCK", s.tuck_x + s.tuck_w / 2.0, D + H + D + s.tuck_d / 2.0 - 0.6, 2.4)
    f.vtext("LEFT", -6.6, D / 2.0, 2.6)
    f.vtext("RIGHT", W + 5.8, D / 2.0, 2.6)
    f.ctext("BOARD", W / 2.0, D / 2.0 + 1.6, 4.2)
    f.ctext("%.1f x %.1f x %.1f" % (case.board_w, case.board_h, case.board_t),
            W / 2.0, D / 2.0 - 3.4, 2.6)
    f.ctext("components up", W / 2.0, D / 2.0 - 7.4, 2.4)
    for x, y, w, h in tabs.values():
        f.ctext("G", x + w / 2.0, y + h / 2.0 - 0.9, 3.2)

    # --- dimensions --------------------------------------------------------
    dim_h(f, 0.0, W, -H - s.lip_d - 6.0, "%.1f inner" % W)
    dim_v(f, W + H + 7.0, 0.0, D, "%.1f inner" % D)
    dim_v(f, -H - 7.0, 0.0, H, "%.1f high" % H)


def draw_notes(c: Any, case: Case) -> None:
    s = case.spec
    W, D, H = case.w, case.d, case.h
    x = NOTES_X
    y = 176.0

    c.text("ASSEMBLY", x, y, 4.2)
    y -= 7.2
    lines = [
        '1. Print A4 landscape at 100% / "Actual size". Never "fit to page".',
        "2. Check the 100 mm bar. The printed side becomes the inside.",
        "3. Score every dashed line. Cut the solid lines and the openings.",
        "4. Fold the four walls up. Fold the LIP down inside the FRONT wall.",
        "5. Glue the four G tabs to the inside of the FRONT and BACK walls.",
        "6. Drop the board in: J1/J3 at BACK, J2 at FRONT, SW1/SW2 at LEFT.",
        "7. Close the lid, then push the %.0f x %.1f mm TUCK tongue through the"
        % (s.tuck_w, s.tuck_d),
        "   %.0f x %.1f mm slit. The LIP behind it catches and holds the tongue."
        % (s.slit_len, s.slit_h),
        "8. Open by lifting the lid's front edge; the tongue slides back out.",
    ]
    for line in lines:
        c.text(line, x, y, 2.75)
        y -= 3.4

    y -= 3.0
    c.text("OPENINGS  (board mm, x from the left, y from the top)", x, y, 3.4)
    y -= 5.6
    columns = [(0.0, "ref"), (9.0, "part"), (25.0, "wall"), (43.0, "position"),
               (75.0, "size"), (95.0, "z above floor")]
    for dx, name in columns:
        c.text(name, x + dx, y, 2.55)
    y -= 3.9
    for opening in case.openings:
        along = ("x=%.1f" % opening.board[0]
                 if opening.wall in ("front", "back")
                 else "y=%.1f" % opening.board[1])
        size = ("%.1f x %.1f" % (opening.length, opening.height)
                if opening.wall in ("front", "back")
                else "%.1f x %.1f" % (opening.height, opening.length))
        z = "%.1f-%.1f" % (opening.z0, opening.z0 + opening.height)
        c.text(opening.ref, x, y, 2.55)
        c.text(opening.kind.replace(" receptacle", ""), x + 9.0, y, 2.55)
        c.text(opening.wall, x + 25.0, y, 2.55)
        c.text(along, x + 43.0, y, 2.55)
        c.text(size, x + 75.0, y, 2.55)
        c.text(z, x + 95.0, y, 2.55)
        y -= 3.25
    for hole in case.holes:
        c.text(hole.ref, x, y, 2.55)
        c.text(hole.kind, x + 9.0, y, 2.55)
        c.text("lid", x + 25.0, y, 2.55)
        c.text("x=%.1f y=%.1f" % hole.board, x + 43.0, y, 2.55)
        c.text("dia %.1f" % hole.diameter, x + 75.0, y, 2.55)
        c.text("centre", x + 95.0, y, 2.55)
        y -= 3.25

    y -= 3.2
    c.text("DIMENSIONS (mm)", x, y, 3.4)
    y -= 5.4
    for line in [
        "inner         %5.1f x %4.1f x %3.1f" % (W, D, H),
        "board         %5.1f x %4.1f x %3.1f" % (case.board_w, case.board_h,
                                                  case.board_t),
        "clearance     %.1f on all four sides (0.3 mm cardstock)" % s.clearance,
        "glue tab      %.1f deep, four corners" % s.tab_d,
        "tuck tongue   %.1f wide x %.1f deep, %.1f radius tip"
        % (s.tuck_w, s.tuck_d, s.tuck_r),
        "tuck slit     %.1f x %.1f, %.1f below the front rim"
        % (s.slit_len, s.slit_h, s.slit_drop),
        "inner lip     %.1f x %.1f, behind the slit" % (s.lip_w, s.lip_d),
        "lid           %.1f deep, %.1f overhang each side"
        % (D, s.lid_overhang),
    ]:
        c.text(line, x, y, 2.65)
        y -= 3.25

    y -= 3.4
    c.text("LINE TYPES", x, y, 3.4)
    y -= 4.8
    c.line(x, y, x + 14.0, y, 0.3)
    c.text("cut / opening edge", x + 17.0, y - 0.9, 2.65)
    y -= 4.8
    c.line(x, y, x + 14.0, y, 0.22, dash=(2.2, 1.4))
    c.text("valley fold (score, do not cut)", x + 17.0, y - 0.9, 2.65)
    y -= 4.8
    c.line(x, y, x + 14.0, y, 0.18, gray=0.45)
    c.text("board outline (reference only)", x + 17.0, y - 0.9, 2.65)

    y -= 4.8
    c.text("FIT NOTES", x, y, 3.4)
    y -= 5.0
    usb_a = next((o for o in case.openings if "USB-A" in o.kind), None)
    strip = H - (usb_a.z0 + usb_a.height) if usb_a else 0.0
    for line in [
        "The USB-A opening is %.1f mm tall: a right-angle A shell sits high"
        % (usb_a.height if usb_a else 0.0),
        "on a 1.6 mm board. If yours is taller, trim the %.1f mm strip above"
        % strip,
        "the opening. The LED and reset holes go through the lid.",
    ]:
        c.text(line, x, y, 2.55)
        y -= 3.2


def draw_scale(c: Any, x: float = 15.0, y: float = 21.0,
               length: float = 100.0) -> None:
    c.line(x, y, x + length, y, 0.3)
    for i in range(int(length) + 1):
        if i % 10 == 0:
            tick, w = 3.2, 0.3
        elif i % 5 == 0:
            tick, w = 2.0, 0.2
        else:
            tick, w = 1.0, 0.15
        c.line(x + i, y, x + i, y + tick, w)
    for i in range(0, int(length) + 1, 25):
        c.text("%d" % i, x + i - (3.0 if i >= 100 else 0.0), y - 4.6, 3.0)
    c.text("100 mm print check (mm)", x, y + 7.6, 3.2)
    c.text("If this bar is not 100 mm, the printer scaled the page.",
           x, y - 9.0, 2.6)


def draw_sheet(canvas: Any, case: Case) -> None:
    f = Frame(canvas, NET_X, NET_Y)

    canvas.text("RP2040 MIDI  /  PAPER CASE", 15, 198, 6.5)
    canvas.text("A4 landscape, 1:1 net for one-piece tuck box, "
                "0.3 mm cardstock.", 15, 191, 3.4)
    canvas.text('Print at 100% / "Actual size". Do not use "fit to page".',
                15, 186.5, 3.4)
    canvas.text("Printed side = inside. Solid = cut, dashed = valley fold, "
                "grey = board outline.", 15, 181.5, 3.0)

    draw_net(f, case)
    draw_notes(canvas, case)
    draw_scale(canvas)

    canvas.text(
        "Generated by hardware/rp2040_midi_bridge/scripts/gen_paper_case.py from "
        "design.yaml. Board %.1f x %.1f mm." % (case.board_w, case.board_h),
        120, 10, 2.3)


def render_pdf(case: Case) -> PdfCanvas:
    canvas = PdfCanvas()
    draw_sheet(canvas, case)
    return canvas


def render_svg(case: Case) -> SvgCanvas:
    canvas = SvgCanvas()
    draw_sheet(canvas, case)
    return canvas


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def report(case: Case) -> None:
    s = case.spec
    print("inner %.1f x %.1f x %.1f mm  (board %.1f x %.1f, clearance %.1f)"
          % (case.w, case.d, case.h, case.board_w, case.board_h, s.clearance))
    for opening in case.openings:
        print("  %-4s %-9s %-5s %s  %.1f x %.1f  z %.1f-%.1f"
              % (opening.ref, opening.kind.replace(" receptacle", ""),
                 opening.wall,
                 "x=%.1f" % opening.board[0] if opening.wall in ("front", "back")
                 else "y=%.1f" % opening.board[1],
                 opening.length, opening.height,
                 opening.z0, opening.z0 + opening.height))
    for hole in case.holes:
        print("  %-4s %-9s lid   x=%.1f y=%.1f  dia %.1f"
              % (hole.ref, hole.kind, hole.board[0], hole.board[1],
                 hole.diameter))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--design", default=str(DESIGN))
    parser.add_argument("--pdf", default=str(PDF_OUT))
    parser.add_argument("--svg", default=str(SVG_OUT))
    parser.add_argument("--no-svg", action="store_true",
                        help="only write the PDF")
    args = parser.parse_args(argv)

    case = build_case(read_design(Path(args.design)))
    errors = validate(case)
    if errors:
        for error in errors:
            print("paper case: " + error, file=sys.stderr)
        return 1

    pdf = Path(args.pdf)
    render_pdf(case).save(pdf)
    print("wrote %s" % pdf)
    if not args.no_svg:
        svg = Path(args.svg)
        render_svg(case).save(svg)
        print("wrote %s" % svg)
    report(case)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
