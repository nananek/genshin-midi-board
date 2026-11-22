#!/usr/bin/env python3
"""Export CSV tables from design.yaml so the Markdown and CSV cannot drift."""

from __future__ import annotations

import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "hardware" / "rp2040_frisk"
DESIGN = yaml.safe_load((BASE / "design.yaml").read_text(encoding="utf-8"))


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {path.relative_to(ROOT)}")


def main() -> None:
    write_csv(
        BASE / "pinmap.csv",
        ["signal", "rp2040_pin", "gpio", "net", "destination", "note"],
        [{**row, "note": row.get("note") or "-"} for row in DESIGN["pinmap"]],
    )
    write_csv(
        BASE / "bom.csv",
        ["ref", "value", "footprint", "lcsc", "assembly", "note"],
        [{**row, "note": row.get("note") or "-"} for row in DESIGN["bom"]],
    )
    placement = []
    for entry in DESIGN["connectors"]:
        placement.append({
            "ref": entry["ref"],
            "type": entry["type"],
            "x_mm": entry["x_mm"],
            "y_mm": entry["y_mm"],
            "rotation_deg": entry["rotation_deg"],
            "edge": entry["edge"],
            "role": entry["type"],
        })
    for entry in DESIGN["placements"]:
        placement.append({
            "ref": entry["ref"],
            "type": entry["value"],
            "x_mm": entry["x_mm"],
            "y_mm": entry["y_mm"],
            "rotation_deg": entry.get("rotation_deg", 0),
            "edge": "",
            "role": entry["package"],
        })
    write_csv(
        BASE / "placement.csv",
        ["ref", "type", "x_mm", "y_mm", "rotation_deg", "edge", "role"],
        placement,
    )


if __name__ == "__main__":
    main()
