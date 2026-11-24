#!/usr/bin/env python3
"""Apply DRC-report-driven local fixes by matching the reported point to a
segment (not its midpoint)."""
import math
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


def seg_info(blk):
    s = re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", blk)
    e = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", blk)
    w = re.search(r"\(width ([-\d.]+)\)", blk)
    net = re.search(r'\(net "([^"]*)"\)', blk)
    if not (s and e and w and net):
        return None
    lay = "F" if '(layer "F.Cu")' in blk else ("B" if '(layer "B.Cu")' in blk else "?")
    p0 = (float(s.group(1)), float(s.group(2)))
    p1 = (float(e.group(1)), float(e.group(2)))
    return lay, net.group(1), p0, p1, float(w.group(1))


def pt_seg(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def find(text, net, lay, x, y, length=None):
    best = None
    for start, end, blk in blocks(text, "segment"):
        info = seg_info(blk)
        if not info:
            continue
        l, n, p0, p1, w = info
        if l != lay or n != net:
            continue
        d = pt_seg((x, y), p0, p1)
        if d > 0.03:
            continue
        lg = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        err = abs(lg - length) if length is not None else d
        if best is None or err < best[0]:
            best = (err, start, end, blk, w, lg)
    return best


def main(board, report):
    p = Path(board)
    text = p.read_text(encoding="utf-8")
    rpt = Path(report).read_text(encoding="utf-8")
    removed = narrowed = 0
    edits = []
    for block in re.split(r"\n(?=\[)", rpt):
        m = re.match(r"\[([a-z_]+)\]", block)
        if not m:
            continue
        kind = m.group(1)
        items = re.findall(r"@\(([-\d.]+) mm, ([-\d.]+) mm\): "
                           r"(Track|Via|Pad|PTH pad) (?:[^\[]*)\[([^\]]*)\]"
                           r"[^,]*(?:, length ([-\d.]+) mm)?", block)
        if kind == "clearance":
            for x, y, what, net, _lg in items:
                if what != "Track":
                    continue
                x, y = float(x), float(y)
                # find by net and nearest point, any layer matching the block
                lay = "F" if "on F.Cu" in block else ("B" if "on B.Cu" in block else None)
                target = 0.127 if net.startswith("USB_") else 0.6
                cands = []
                for start, end, blk in blocks(text, "segment"):
                    info = seg_info(blk)
                    if not info:
                        continue
                    l, n, p0, p1, w = info
                    if n != net or w <= target:
                        continue
                    if lay and l != lay:
                        continue
                    if pt_seg((x, y), p0, p1) <= 0.03:
                        cands.append((start, end, blk, w))
                for start, end, blk, w in cands:
                    new = re.sub(r"\(width [-\d.]+\)", f"(width {target})", blk)
                    edits.append((start, end, new))
                    narrowed += 1
        elif kind == "track_dangling":
            for x, y, what, net, lg in items:
                if what != "Track" or not lg or float(lg) > 0.6:
                    continue
                x, y, lg = float(x), float(y), float(lg)
                for lay in ("F", "B"):
                    best = find(text, net, lay, x, y, lg)
                    if best and best[0] <= 0.05:
                        edits.append((best[1], best[2], ""))
                        removed += 1
                        break
    for start, end, new in sorted(edits, key=lambda e: e[0], reverse=True):
        text = text[:start] + new + text[end:]
    p.write_text(text, encoding="utf-8")
    print(f"removed {removed} stubs, narrowed {narrowed} tracks")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
