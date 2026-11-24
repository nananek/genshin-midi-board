#!/usr/bin/env python3
"""Local DRC cleanup on the WIP board (text level).

* drop duplicate/edge GND stitching vias that carry no track
* drop the tiny dangling B.Cu stubs
* narrow the six tracks that sit 0.075-0.08 mm from a pad/via
"""
import re
import sys
from pathlib import Path


def blocks(text, keyword):
    out = []
    needle = f"\t({keyword}\n"
    start = 0
    while True:
        i = text.find(needle, start)
        if i < 0:
            return out
        depth = 0
        for j in range(i, len(text)):
            if text[j] == "(":
                depth += 1
            elif text[j] == ")":
                depth -= 1
                if depth == 0:
                    out.append((i, j + 1, text[i:j + 1]))
                    start = j + 1
                    break
        else:
            return out


DROP_VIAS = [(9.4844, 3.3505), (26.9005, 19.7502), (2.0505, 0.5505)]

DROP_TRACKS = [
    ("B", "TPS_EN", 16.8625, 21.15),
    ("B", "TPS_EN", 15.7, 22.95),
    ("B", "VBUS_USB_A", 23.75, 20.15),
    ("B", "VBUS_IPAD", 47.9, 6.45),
    ("B", "VBUS_IPAD", 43.05, 6.445),
    ("B", "VBUS_IPAD", 38.15, 9.65),
]

NARROW = [
    ("F", "VBUS_IPAD", 52.2, 9.95, 0.6),
    ("F", "VBUS_IPAD", 50.2, 13.6, 0.6),
    ("F", "VBUS_IPAD", 51.75, 11.35, 0.6),
    ("B", "VBUS_USB_A", 25.3, 23.55, 0.7),
    ("F", "USB_PC_DP", 16.6, 7.35, 0.127),
    ("F", "USB_PC_DM", 12.45, 10.4, 0.127),
]


def midpoint(blk):
    m = re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", blk)
    n = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", blk)
    if not m or not n:
        return None
    return ((float(m.group(1)) + float(n.group(1))) / 2,
            (float(m.group(2)) + float(n.group(2))) / 2)


def layer_of(blk):
    if '(layer "F.Cu")' in blk:
        return "F"
    if '(layer "B.Cu")' in blk:
        return "B"
    return "?"


def main(path):
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    removed = 0
    for start, end, blk in reversed(blocks(text, "via")):
        at = re.search(r"\(at ([-\d.]+) ([-\d.]+)\)", blk)
        if not at:
            continue
        x, y = float(at.group(1)), float(at.group(2))
        if any(abs(x - vx) < 0.02 and abs(y - vy) < 0.02 for vx, vy in DROP_VIAS):
            text = text[:start] + text[end:]
            removed += 1
    for start, end, blk in reversed(blocks(text, "segment")):
        net = re.search(r'\(net "([^"]*)"\)', blk)
        if not net:
            continue
        mid = midpoint(blk)
        if not mid:
            continue
        lay = layer_of(blk)
        for dl, dn, dx, dy in DROP_TRACKS:
            if (lay == dl and net.group(1) == dn and
                    abs(mid[0] - dx) < 0.03 and abs(mid[1] - dy) < 0.03):
                text = text[:start] + text[end:]
                removed += 1
                break
    narrowed = 0
    for start, end, blk in blocks(text, "segment"):
        net = re.search(r'\(net "([^"]*)"\)', blk)
        mid = midpoint(blk)
        if not net or not mid:
            continue
        lay = layer_of(blk)
        for nl, nn, nx, ny, width in NARROW:
            if (lay == nl and net.group(1) == nn and
                    abs(mid[0] - nx) < 0.05 and abs(mid[1] - ny) < 0.05):
                new = re.sub(r"\(width [-\d.]+\)", f"(width {width})", blk)
                if new != blk:
                    text = text[:start] + new + text[end:]
                    narrowed += 1
                break
    p.write_text(text, encoding="utf-8")
    print(f"removed {removed}, narrowed {narrowed}")


if __name__ == "__main__":
    main(sys.argv[1])
