#!/usr/bin/env python3
"""Iteratively remove dead-end track chains, using the diag.json snapshot.

The board text is edited by matching each segment's net, layer and endpoints.
"""
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


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


def main():
    D = json.load(open(ROOT / "diag.json"))
    pcb = ROOT / "rp2040_frisk.kicad_pcb"
    text = pcb.read_text(encoding="utf-8")
    # collect segment records with text offsets
    recs = []
    for st, en, blk in blocks(text, "segment"):
        import re
        net = re.search(r'\(net "([^"]*)"\)', blk).group(1)
        lay = "F" if '(layer "F.Cu")' in blk else "B"
        s = re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", blk)
        e = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", blk)
        recs.append({"st": st, "en": en, "net": net, "lay": lay,
                     "p0": (float(s.group(1)), float(s.group(2))),
                     "p1": (float(e.group(1)), float(e.group(2))),
                     "dead": False})
    pads = [(p["net"], p["x0"], p["y0"], p["x1"], p["y1"], p["f"], p["b"]) for p in D["pads"]]
    vias = [(v["net"], v["x"], v["y"]) for v in D["vias"]]
    removed = 0
    for _ in range(1000):
        ends = {}
        for r in recs:
            if r["dead"]:
                continue
            for p in (r["p0"], r["p1"]):
                ends.setdefault(r["net"], []).append((p[0], p[1], r))
        hit = []
        for r in recs:
            if r["dead"]:
                continue
            net = r["net"]
            for p in (r["p0"], r["p1"]):
                x, y = p
                if any(pn == net and (pf if r["lay"] == "F" else pb) and
                       x0 - 0.02 <= x <= x1 + 0.02 and
                       y0 - 0.02 <= y <= y1 + 0.02
                       for pn, x0, y0, x1, y1, pf, pb in pads):
                    continue
                if any(vn == net and math.hypot(x - vx, y - vy) < 0.03
                       for vn, vx, vy in vias):
                    continue
                if any(o is not r and math.hypot(x - ex, y - ey) < 0.03
                       for ex, ey, o in ends.get(net, [])):
                    continue
                hit.append(r)
                break
        if not hit:
            break
        for r in hit:
            r["dead"] = True
            removed += 1
    for r in sorted([r for r in recs if r["dead"]], key=lambda r: r["st"],
                    reverse=True):
        text = text[:r["st"]] + text[r["en"]:]
    pcb.write_text(text, encoding="utf-8")
    print("removed", removed, "dead-end segments")


if __name__ == "__main__":
    main()
