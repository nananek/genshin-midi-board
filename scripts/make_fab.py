#!/usr/bin/env python3
"""Build the tagged-release fabrication package for rp2040_midi_bridge.

Run inside the KiCad container so that pcbnew and kicad-cli match the tool
version used for the design:

    make fab VERSION=v0.1.0

The output is dist/rp2040_midi_bridge-v<version>-gerber.zip.  The ZIP layout
and the release conditions are defined in AGENTS.md section 3.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import re
import shutil
import subprocess
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pcbnew
import yaml

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / "hardware" / "rp2040_midi_bridge"
PCB = BASE / "rp2040_midi_bridge.kicad_pcb"
DESIGN = yaml.safe_load((BASE / "design.yaml").read_text(encoding="utf-8"))
PROJECT = DESIGN["project"]["name"]
BOARD = DESIGN["board"]
DIST = ROOT / "dist"

GERBER_LAYERS = ",".join([
    "F.Cu", "In1.Cu", "In2.Cu", "B.Cu",
    "F.Paste", "B.Paste",
    "F.SilkS", "B.SilkS",
    "F.Mask", "B.Mask",
    "Edge.Cuts",
])

EXCLUDE_ATTRS = pcbnew.FP_EXCLUDE_FROM_POS_FILES | pcbnew.FP_EXCLUDE_FROM_BOM


def fail(message: str) -> None:
    print(f"FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def expand_refs(spec: str) -> list[str]:
    """Expand 'C6-C16,R1,R2' into individual reference designators."""
    refs: list[str] = []
    for token in spec.split(","):
        token = token.strip()
        if not token:
            continue
        m = re.fullmatch(r"([A-Za-z]+)(\d+)-([A-Za-z]+)(\d+)", token)
        if m:
            prefix1, start, prefix2, end = m.groups()
            if prefix1 != prefix2:
                fail(f"cannot expand mixed prefixes in {token!r}")
            lo, hi = int(start), int(end)
            if lo > hi:
                fail(f"reversed range in {token!r}")
            refs.extend(f"{prefix1}{i}" for i in range(lo, hi + 1))
        else:
            refs.append(token)
    return refs


def pcb_parts(board: pcbnew.BOARD) -> dict[str, dict]:
    parts: dict[str, dict] = {}
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        attrs = fp.GetAttributes()
        pos = fp.GetPosition()
        parts[ref] = {
            "value": fp.GetValue(),
            "footprint": str(fp.GetFPID().GetLibItemName()),
            "x_mm": pos.x / 1_000_000,
            "y_mm": pos.y / 1_000_000,
            "rotation_deg": fp.GetOrientationDegrees() % 360,
            "side": "Bottom" if fp.GetLayer() == pcbnew.B_Cu else "Top",
            "smd": bool(attrs & pcbnew.FP_SMD),
            "tht": bool(attrs & pcbnew.FP_THROUGH_HOLE),
            "excluded": bool(attrs & EXCLUDE_ATTRS),
        }
    return parts


def build_bom(parts: dict[str, dict]) -> tuple[list[dict], set[str], set[str]]:
    rows: list[dict] = []
    smt_refs: set[str] = set()
    tht_refs: set[str] = set()
    seen: set[str] = set()

    for entry in DESIGN["bom"]:
        refs = expand_refs(entry["ref"])
        for ref in refs:
            if ref in seen:
                fail(f"BOM lists {ref} more than once")
            seen.add(ref)
            if ref not in parts:
                fail(f"BOM lists {ref}, but the PCB has no such footprint")
        assembly = entry["assembly"]
        if assembly == "SMT":
            if not entry.get("lcsc"):
                fail(f"SMT BOM row {entry['ref']} has no LCSC part number")
            for ref in refs:
                if not parts[ref]["smd"]:
                    fail(f"BOM marks {ref} as SMT, but the PCB footprint is not SMD")
                if parts[ref]["excluded"]:
                    fail(f"BOM includes {ref}, but the PCB excludes it from BOM/CPL")
            smt_refs.update(refs)
            rows.append({
                "Comment": entry["value"],
                "Designator": ",".join(refs),
                "Footprint": entry["footprint"],
                "LCSC Part #": entry["lcsc"],
            })
        elif assembly == "THT":
            for ref in refs:
                if not parts[ref]["tht"]:
                    fail(f"BOM marks {ref} as THT, but the PCB footprint is not through-hole")
            tht_refs.update(refs)
    return rows, smt_refs, tht_refs


def build_cpl(parts: dict[str, dict]) -> list[dict]:
    rows: list[dict] = []
    width = float(BOARD["width_mm"])
    height = float(BOARD["height_mm"])
    for ref, part in sorted(parts.items()):
        if part["excluded"] or not part["smd"]:
            continue
        if not (0.0 <= part["x_mm"] <= width and 0.0 <= part["y_mm"] <= height):
            fail(f"{ref} is outside the {width} x {height} mm board")
        # KiCad's Y axis points down from the top-left board origin.  JLCPCB
        # wants millimetres from the bottom-left corner with Y pointing up.
        cpl_y = height - part["y_mm"]
        rows.append({
            "Designator": ref,
            "Mid X": f"{part['x_mm']:.3f}",
            "Mid Y": f"{cpl_y:.3f}",
            "Layer": part["side"],
            "Rotation": f"{part['rotation_deg']:.3f}".rstrip("0").rstrip("."),
        })
    return rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def kicad_version() -> str:
    out = subprocess.run(
        ["kicad-cli", "version"], check=True, capture_output=True, text=True
    ).stdout.strip()
    return out.splitlines()[0] if out else "unknown"


def render_readme(
    version: str, commit: str, generated: str, kicad: str, smt_count: int, tht_count: int
) -> str:
    return f"""\
{PROJECT} {version}
{'=' * (len(PROJECT) + 1 + len(version))}

Tag:            {version}
Commit:         {commit}
Board revision: {DESIGN['project']['revision']}
Generated:      {generated}
KiCad:          {kicad}
Generated by:   scripts/make_fab.py

Board
-----
Size:            {BOARD['width_mm']} x {BOARD['height_mm']} mm
Thickness:       {BOARD['thickness_mm']} mm
Layers:          {BOARD['layers']} (F.Cu / In1.Cu GND / In2.Cu +3V3 / B.Cu)
Finish:          {BOARD['finish']}
Solder mask:     {BOARD['solder_mask']}
Silkscreen:      {BOARD['silkscreen']}
Corner cut:      {BOARD['chamfer_mm']} mm, 45 degrees, all four corners
Assembly:        top side SMT only ({smt_count} placements, {tht_count} THT parts hand-soldered)

Contents
--------
gerbers/         Gerber X2 for copper, mask, silk, paste and Edge.Cuts
gerbers/*.drl    Excellon drill files
bom.csv          JLCPCB BOM (SMT parts only)
cpl.csv          JLCPCB CPL (SMT parts only, coordinates from bottom-left)
manifest.sha256  SHA-256 of the files in this ZIP
LICENSE          MIT

Known issues
------------
- 実機未検証の試作です。製造、組立、動作は保証しません。
- J2、SW1〜SW4、SW6 は手はんだです。BOM と CPL に含まれません。
- J1/J3 のシェル固定タブは THT です。SMT 実装のあとに手はんだしてください。
- CPL の回転は KiCad の値をそのまま出力しています。JLCPCB の実装プレビューで
  部品の向きを確認してください。
- U4 (AP2112K-3.3TRG1) と C27 (100uF) の LCSC 型番は発注前に再確認してください。
- 0.15 mm ドリルと via-in-pad は使いません。発注画面の DFM プレビューで確認してください。

License
-------
リポジトリ全体は MIT です（LICENSE を参照）。
hardware/rp2040_midi_bridge/lib/ の KiCad シンボルは公式 KiCad ライブラリ由来で、
CC-BY-SA 4.0（設計への利用例外あり）です。
"""


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(staging: Path) -> Path:
    files = sorted(
        p for p in staging.rglob("*") if p.is_file() and p.name != "manifest.sha256"
    )
    lines = [f"{sha256(p)}  {p.relative_to(staging).as_posix()}" for p in files]
    path = staging / "manifest.sha256"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def check_drills(gerber_dir: Path) -> list[str]:
    drills = sorted(gerber_dir.glob("*.drl"))
    if not drills:
        fail("no Excellon drill file was generated")
    diameters: set[float] = set()
    for path in drills:
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"^T\d+C([0-9.]+)", text, re.MULTILINE):
            diameters.add(float(m.group(1)))
    for diameter in sorted(diameters):
        if abs(diameter - 0.15) < 1e-9:
            fail("a 0.15 mm drill is present; JLCPCB would add the advanced via option")
        if diameter < 0.25:
            fail(f"{diameter} mm drill is below the supported 0.25 mm minimum")
    return [f"{d:.2f}" for d in sorted(diameters)]


def check_gerbers(gerber_dir: Path) -> int:
    required_suffixes = {
        "F_Cu.gbr", "In1_Cu.gbr", "In2_Cu.gbr", "B_Cu.gbr",
        "F_Mask.gbr", "B_Mask.gbr",
        "F_Silkscreen.gbr", "B_Silkscreen.gbr",
        "F_Paste.gbr", "B_Paste.gbr",
        "Edge_Cuts.gbr",
    }
    actual = {p.name for p in gerber_dir.glob("*.gbr")}
    suffixes = {
        name[len(PROJECT) + 1:] if name.startswith(f"{PROJECT}-") else name
        for name in actual
    }
    # KiCad may use either the short or the translated silkscreen name.
    normalized = {name.replace("SilkS", "Silkscreen") for name in suffixes}
    missing = required_suffixes - normalized
    if missing:
        fail(f"missing Gerber layers: {sorted(missing)}")
    return len(actual)


def normalize_text(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="release tag, for example v0.1.0")
    parser.add_argument("--commit", required=True, help="commit hash the tag points at")
    args = parser.parse_args()

    version = args.version
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
        fail(f"--version must look like v0.1.0, got {version!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        fail(f"--commit must be a full 40-character hash, got {args.commit!r}")
    if not PCB.exists():
        fail(f"{PCB.relative_to(ROOT)} does not exist")

    board = pcbnew.LoadBoard(str(PCB))
    parts = pcb_parts(board)
    bom_rows, smt_refs, tht_refs = build_bom(parts)
    cpl_rows = build_cpl(parts)

    pcb_smd = {ref for ref, p in parts.items() if p["smd"] and not p["excluded"]}
    pcb_tht = {ref for ref, p in parts.items() if p["tht"] and not p["excluded"]}
    if smt_refs != pcb_smd:
        fail(f"BOM/PCB SMT mismatch: BOM-only={sorted(smt_refs - pcb_smd)}, "
             f"PCB-only={sorted(pcb_smd - smt_refs)}")
    cpl_refs = {row["Designator"] for row in cpl_rows}
    if cpl_refs != smt_refs:
        fail(f"CPL/BOM mismatch: CPL-only={sorted(cpl_refs - smt_refs)}, "
             f"BOM-only={sorted(smt_refs - cpl_refs)}")
    if tht_refs != pcb_tht:
        fail(f"BOM/PCB THT mismatch: BOM-only={sorted(tht_refs - pcb_tht)}, "
             f"PCB-only={sorted(pcb_tht - tht_refs)}")

    staging = DIST / f"fab-{version}"
    if staging.exists():
        shutil.rmtree(staging)
    gerber_dir = staging / "gerbers"
    gerber_dir.mkdir(parents=True)

    run([
        "kicad-cli", "pcb", "export", "gerbers",
        "--output", str(gerber_dir),
        "--layers", GERBER_LAYERS,
        "--no-protel-ext",
        str(PCB),
    ])
    run([
        "kicad-cli", "pcb", "export", "drill",
        "--output", str(gerber_dir),
        "--format", "excellon",
        "--drill-origin", "absolute",
        "--excellon-zeros-format", "decimal",
        "--excellon-units", "mm",
        "--excellon-separate-th",
        str(PCB),
    ])

    write_csv(staging / "bom.csv", ["Comment", "Designator", "Footprint", "LCSC Part #"], bom_rows)
    write_csv(staging / "cpl.csv", ["Designator", "Mid X", "Mid Y", "Layer", "Rotation"], cpl_rows)
    shutil.copy2(ROOT / "LICENSE", staging / "LICENSE")

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    readme = render_readme(
        version, args.commit, generated, kicad_version(), len(smt_refs), len(tht_refs)
    )
    (staging / "README.txt").write_text(normalize_text(readme), encoding="utf-8")

    gerber_count = check_gerbers(gerber_dir)
    drill_sizes = check_drills(gerber_dir)
    manifest = write_manifest(staging)

    zip_path = DIST / f"{PROJECT}-{version}-gerber.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(staging.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(staging).as_posix())

    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
        for required in ("bom.csv", "cpl.csv", "README.txt", "LICENSE", "manifest.sha256"):
            if required not in names:
                fail(f"{required} is missing from {zip_path.name}")
        if any(name.startswith("/") or ".." in Path(name).parts for name in names):
            fail("ZIP contains an absolute path or a parent traversal")
        manifest_lines = zf.read("manifest.sha256").decode("utf-8").splitlines()
        for line in manifest_lines:
            digest, rel = line.split("  ", 1)
            if rel not in names:
                fail(f"manifest entry {rel} is not in the ZIP")
            if hashlib.sha256(zf.read(rel)).hexdigest() != digest:
                fail(f"manifest digest mismatch for {rel}")
        if "manifest.sha256" not in names:
            fail("manifest.sha256 is missing from the ZIP")

    print()
    print(f"wrote {zip_path.relative_to(ROOT)}")
    print(f"  SMT placements: {len(smt_refs)}")
    print(f"  THT (hand solder, not in BOM/CPL): {len(tht_refs)} -> {', '.join(sorted(tht_refs))}")
    print(f"  Gerber files: {gerber_count}")
    print(f"  Drill diameters (mm): {', '.join(drill_sizes)}")
    print(f"  SHA-256: {sha256(zip_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
