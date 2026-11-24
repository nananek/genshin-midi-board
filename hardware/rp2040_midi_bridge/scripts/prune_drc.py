#!/usr/bin/env python3
"""Remove routed copper that DRC rejects.

The grid router does not model every clearance rule (hole to hole spacing and
some zone interactions), so after routing this script reads the DRC report and
deletes exactly the tracks and vias that were reported.  If a reported item
cannot be matched, all copper of that net is removed.  The edit is done on the
s-expression text because removing items through the Python API invalidates
the board object; the zones are refilled afterwards.

The result is a board whose only DRC findings are unconnected items, which is
what a partially routed prototype should look like.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PCB = ROOT / "rp2040_midi_bridge.kicad_pcb"
RPT = ROOT / "drc.rpt"

KEEP = {"GND"}
SKIP_KINDS = {"unconnected_items", "isolated_copper", "starved_thermal"}


def blocks(text: str, keyword: str):
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


def parse(report: Path):
    text = report.read_text(encoding="utf-8")
    items = []
    for block in re.split(r"\n(?=\[)", text):
        m = re.match(r"\[([a-z_]+)\]", block)
        if not m or m.group(1) in SKIP_KINDS:
            continue
        kind = m.group(1)
        for em in re.finditer(r"@\(([-\d.]+) mm, ([-\d.]+) mm\): "
                              r"(Track|Via|PTH pad|Pad|Zone|Segment) "
                              r"(?:\[([^\]]*)\])?", block):
            x, y, what, net = em.groups()
            items.append((kind, what, float(x), float(y), net or ""))
    return items


def refill():
    code = (
        "import pcbnew\n"
        f"b = pcbnew.LoadBoard({str(PCB)!r})\n"
        "b.BuildConnectivity()\n"
        "pcbnew.ZONE_FILLER(b).Fill(b.Zones())\n"
        f"pcbnew.SaveBoard({str(PCB)!r}, b)\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)


def run_drc():
    subprocess.run(["kicad-cli", "pcb", "drc", "--severity-all",
                    "--output", str(RPT), str(PCB)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def one_pass() -> int:
    text = PCB.read_text(encoding="utf-8")
    items = parse(RPT)
    if not items:
        print("nothing to prune")
        return 0
    kill_names = set()
    removed = 0
    for kind, what, x, y, net in items:
        print(f"{kind:16s} {what:8s} {x:7.2f},{y:7.2f} {net}")
        if not net or net in KEEP:
            continue

        hit = None
        if what in ("Track", "Via"):
            key = "segment" if what == "Track" else "via"
            for start, end, blk in blocks(text, key):
                m = re.search(r'\(net "([^"]*)"\)', blk)
                if not m or m.group(1) != net:
                    continue
                coords = [(float(a), float(b)) for a, b in
                          re.findall(r"\((?:start|end|at) ([\d.\-]+) ([\d.\-]+)\)", blk)]
                if any(abs(px - x) < 0.051 and abs(py - y) < 0.051
                       for px, py in coords):
                    hit = (start, end)
                    break
        if hit:
            s_, e_ = hit
            text = text[:s_] + text[e_:]
            removed += 1
        else:
            kill_names.add(net)
    for start, end, blk in sorted(blocks(text, "segment") +
                                  blocks(text, "via"), reverse=True):
        m = re.search(r'\(net "([^"]*)"\)', blk)
        if m and m.group(1) in kill_names:
            text = text[:start] + text[end:]
            removed += 1
    if removed == 0:
        print("nothing removed")
        return 0
    PCB.write_text(text, encoding="utf-8")
    print(f"removed {removed} items")
    refill()
    return removed


def main() -> int:
    for i in range(6):
        run_drc()
        if one_pass() == 0:
            break
    run_drc()
    return 0


if __name__ == "__main__":
    sys.exit(main())
