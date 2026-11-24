#!/usr/bin/env python3
"""Delete one generation of track_dangling items from the DRC report."""
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fix_drc_report import blocks, seg_info, pt_seg


def main(board, report):
    p = Path(board)
    text = p.read_text(encoding="utf-8")
    rpt = Path(report).read_text(encoding="utf-8")
    edits = {}
    for block in re.split(r"\n(?=\[)", rpt):
        if not block.startswith("[track_dangling]"):
            continue
        for t in re.finditer(r"@\(([-\d.]+) mm, ([-\d.]+) mm\): Track "
                             r"\[([^\]]*)\] on ([FB])\.Cu, length ([-\d.]+) mm",
                             block):
            x, y, net, lay, lg = (float(t.group(1)), float(t.group(2)),
                                  t.group(3), t.group(4), float(t.group(5)))
            best = None
            for st, en, blk in blocks(text, "segment"):
                info = seg_info(blk)
                if not info:
                    continue
                l, n, p0, p1, w = info
                if l != lay or n != net:
                    continue
                if pt_seg((x, y), p0, p1) > 0.03:
                    continue
                sl = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
                err = abs(sl - lg)
                if best is None or err < best[0]:
                    best = (err, st, en)
            if best and best[0] < 0.08:
                edits[(best[1], best[2])] = ""
    for (st, en) in sorted(edits, reverse=True):
        text = text[:st] + text[en:]
    p.write_text(text, encoding="utf-8")
    print(len(edits))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
