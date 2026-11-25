#!/usr/bin/env python3
"""Build the JLCPCB-ready release assets for rp2040_midi_bridge.

Run inside the KiCad container so that pcbnew and kicad-cli match the tool
version used for the design:

    make fab VERSION=v0.0.2

The output is a set of separately uploadable files:

    dist/rp2040_midi_bridge-v<version>-gerber.zip   PCB fabrication
    dist/rp2040_midi_bridge-v<version>-bom.csv      SMT BOM
    dist/rp2040_midi_bridge-v<version>-cpl.csv      SMT CPL
    dist/rp2040_midi_bridge-v<version>-README.txt
    dist/rp2040_midi_bridge-v<version>-LICENSE
    dist/rp2040_midi_bridge-v<version>-manifest.sha256

The layout and the release conditions are defined in AGENTS.md section 3.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import math
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

REQUIRED_GERBER_SUFFIXES = {
    "F_Cu.gbr", "In1_Cu.gbr", "In2_Cu.gbr", "B_Cu.gbr",
    "F_Mask.gbr", "B_Mask.gbr",
    "F_Silkscreen.gbr", "B_Silkscreen.gbr",
    "F_Paste.gbr", "B_Paste.gbr",
    "Edge_Cuts.gbr",
}

EXCLUDE_ATTRS = pcbnew.FP_EXCLUDE_FROM_POS_FILES | pcbnew.FP_EXCLUDE_FROM_BOM

# JLCPCB's part library origin for this USB-C receptacle sits 1.571 mm behind
# the KiCad footprint origin, measured along the connector axis.  Compensate so
# the connector body lands where the board expects it.
USB_C_FOOTPRINT = "USB_C_Receptacle_HRO_TYPE-C-31-M-12"
USB_C_POSITION_OFFSET_MM = 1.571

# JLCPCB library orientations that differ from the KiCad footprints.  These
# were read from the JLCPCB assembly preview for this board; U1 already lines
# up.  The TPS2553 library orientation is 180 degrees from the KiCad SOT-23-6
# footprint (pin 1 = IN).
CPL_ROTATION_OFFSETS = {
    "U2": 270,  # W25Q128, SOIC-8
    "U3": 270,  # CH345T, SSOP-20
    "U4": 270,  # AP2112K, SOT-23-5
    "U5": 180,  # TPS2553, SOT-23-6 (pin 1 = IN)
    "U6": 270,  # USBLC6, SOT-23-6
    "U7": 270,  # USBLC6, SOT-23-6
    "U8": 270,  # USBLC6, SOT-23-6
}


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
        # The drill/place origin is set to that corner in gen_pcb.py, and the
        # Gerbers and drill files are plotted with the same origin.
        dx = dy = 0.0
        if part["footprint"] == USB_C_FOOTPRINT:
            rad = math.radians(part["rotation_deg"])
            dx = -USB_C_POSITION_OFFSET_MM * math.sin(rad)
            dy = USB_C_POSITION_OFFSET_MM * math.cos(rad)
        cpl_x = part["x_mm"] + dx
        cpl_y = height - part["y_mm"] + dy
        if not (0.0 <= cpl_x <= width and 0.0 <= cpl_y <= height):
            fail(f"{ref} is outside the board after the CPL correction")
        rotation = (part["rotation_deg"] + CPL_ROTATION_OFFSETS.get(ref, 0)) % 360
        rows.append({
            "Designator": ref,
            "Mid X": f"{cpl_x:.3f}",
            "Mid Y": f"{cpl_y:.3f}",
            "Layer": part["side"],
            "Rotation": f"{rotation:.3f}".rstrip("0").rstrip("."),
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

Files
-----
{PROJECT}-{version}-gerber.zip       PCB fabrication (upload as-is)
{PROJECT}-{version}-bom.csv          SMT BOM (upload to the BOM field)
{PROJECT}-{version}-cpl.csv          SMT CPL (upload to the CPL field)
{PROJECT}-{version}-README.txt       This file
{PROJECT}-{version}-LICENSE          MIT
{PROJECT}-{version}-manifest.sha256  SHA-256 of the other five files

JLCPCB upload
-------------
1. PCB: select "Add gerber file" and upload {PROJECT}-{version}-gerber.zip
   without extracting it.  The ZIP contains Gerber X2, Excellon drill and a
   .gbrjob file at its root.  BOM and CPL are not inside this ZIP.
2. SMT: enable SMT assembly, then upload {PROJECT}-{version}-bom.csv as the
   BOM and {PROJECT}-{version}-cpl.csv as the CPL.
3. Confirm the part rotations in the assembly preview before ordering.

Known issues
------------
- 実機未検証の試作です。製造、組立、動作は保証しません。
- J2、SW1〜SW5 は手はんだです。BOM と CPL に含まれません。
- SW6（BOOT）と SW7（RUN）は SMT タクトで、BOM と CPL に含まれます。表シルクに
  BOOT / RUN を表示しています。
- J2 は上面実装です。開口は基板の下辺（外側）に合わせています。2 つの
  ø2.3 mm シェル穴は信号ピン列から 2.7 mm 開口側です。裏面シルクに
  VCC / D- / D+ / GND と J2 USB-A (TOP) を表示しています。
- J1/J3 のシェル固定タブは THT です。SMT 実装のあとに手はんだしてください。
- J1/J3 の CPL 位置は JLCPCB の USB-C 部品原点に合わせて 1.571 mm 補正しています。
- CPL の回転は JLCPCB の部品ライブラリに合わせ、U2 / U3 / U4 / U6 / U7 を
  270°、U5 を 180° 補正しています。U8 は基板上で 90° 回転しているため CPL の
  回転は 0°、U1 は KiCad の値のままです。実装プレビューで最終確認してください。
- 裏面に基板名とリポジトリ URL の QR コードを配置しています。
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


def check_gerber_zip(zip_path: Path) -> tuple[int, list[str]]:
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if any("/" in name or "\\" in name for name in names):
            fail("the Gerber ZIP must be flat; remove subdirectories")
        if any(Path(name).name != name or name.startswith(".") for name in names):
            fail("the Gerber ZIP contains an unexpected path or dot file")
        forbidden = {"bom.csv", "cpl.csv", "README.txt", "LICENSE", "manifest.sha256"}
        if forbidden & set(names):
            fail("BOM, CPL, README, LICENSE or manifest leaked into the Gerber ZIP")
        allowed = {".gbr", ".drl", ".gbrjob"}
        for name in names:
            if Path(name).suffix.lower() not in allowed:
                fail(f"unexpected file in the Gerber ZIP: {name}")

        suffixes = {
            name[len(PROJECT) + 1:] if name.startswith(f"{PROJECT}-") else name
            for name in names
            if name.lower().endswith(".gbr")
        }
        normalized = {name.replace("SilkS", "Silkscreen") for name in suffixes}
        missing = REQUIRED_GERBER_SUFFIXES - normalized
        if missing:
            fail(f"missing Gerber layers: {sorted(missing)}")

        diameters: set[float] = set()
        for name in names:
            if not name.lower().endswith(".drl"):
                continue
            text = zf.read(name).decode("utf-8", errors="replace")
            for m in re.finditer(r"^T\d+C([0-9.]+)", text, re.MULTILINE):
                diameters.add(float(m.group(1)))
        if not diameters:
            fail("the Gerber ZIP has no drill hits")
        for diameter in sorted(diameters):
            if abs(diameter - 0.15) < 1e-9:
                fail("a 0.15 mm drill is in the Gerber ZIP")
            if diameter < 0.25:
                fail(f"{diameter} mm drill is below the supported 0.25 mm minimum")
        return sum(name.lower().endswith(".gbr") for name in names), [
            f"{d:.2f}" for d in sorted(diameters)
        ]


def write_manifest(assets: list[Path], path: Path) -> None:
    lines = [f"{sha256(asset)}  {asset.name}" for asset in assets]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def verify_manifest(manifest: Path, assets: list[Path]) -> None:
    lines = manifest.read_text(encoding="utf-8").splitlines()
    by_name = {asset.name: asset for asset in assets}
    if len(lines) != len(assets):
        fail("manifest.sha256 does not cover every release asset")
    for line in lines:
        digest, name = line.split("  ", 1)
        if name not in by_name:
            fail(f"manifest entry {name} is not a release asset")
        if sha256(by_name[name]) != digest:
            fail(f"manifest digest mismatch for {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", required=True, help="release tag, for example v0.0.2")
    parser.add_argument("--commit", required=True, help="commit hash the tag points at")
    args = parser.parse_args()

    version = args.version
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?", version):
        fail(f"--version must look like v0.0.2, got {version!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", args.commit):
        fail(f"--commit must be a full 40-character hash, got {args.commit!r}")
    if not PCB.exists():
        fail(f"{PCB.relative_to(ROOT)} does not exist")

    board = pcbnew.LoadBoard(str(PCB))
    aux = board.GetDesignSettings().GetAuxOrigin()
    expected_aux_y = pcbnew.FromMM(float(BOARD["height_mm"]))
    if aux.x != 0 or abs(aux.y - expected_aux_y) > 1:
        fail(
            "drill/place origin is "
            f"({aux.x / 1_000_000:.3f}, {aux.y / 1_000_000:.3f}) mm; "
            f"expected (0, {BOARD['height_mm']})"
        )
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
        "--use-drill-file-origin",
        str(PCB),
    ])
    run([
        "kicad-cli", "pcb", "export", "drill",
        "--output", str(gerber_dir),
        "--format", "excellon",
        "--drill-origin", "plot",
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
    (staging / "README.txt").write_text(unicodedata.normalize("NFC", readme), encoding="utf-8")

    check_drills(gerber_dir)

    # The Gerber ZIP is uploaded as-is: flat, with only fabrication files.
    gerber_zip = DIST / f"{PROJECT}-{version}-gerber.zip"
    if gerber_zip.exists():
        gerber_zip.unlink()
    with zipfile.ZipFile(gerber_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(gerber_dir.iterdir()):
            if path.is_file():
                zf.write(path, path.name)

    assets = [
        gerber_zip,
        DIST / f"{PROJECT}-{version}-bom.csv",
        DIST / f"{PROJECT}-{version}-cpl.csv",
        DIST / f"{PROJECT}-{version}-README.txt",
        DIST / f"{PROJECT}-{version}-LICENSE",
    ]
    shutil.copy2(staging / "bom.csv", assets[1])
    shutil.copy2(staging / "cpl.csv", assets[2])
    shutil.copy2(staging / "README.txt", assets[3])
    shutil.copy2(staging / "LICENSE", assets[4])

    gerber_count, drill_sizes = check_gerber_zip(gerber_zip)
    manifest = DIST / f"{PROJECT}-{version}-manifest.sha256"
    write_manifest(assets, manifest)
    verify_manifest(manifest, assets)

    print()
    print(f"wrote {gerber_zip.relative_to(ROOT)}")
    print(f"wrote {assets[1].relative_to(ROOT)}")
    print(f"wrote {assets[2].relative_to(ROOT)}")
    print(f"wrote {assets[3].relative_to(ROOT)}")
    print(f"wrote {assets[4].relative_to(ROOT)}")
    print(f"wrote {manifest.relative_to(ROOT)}")
    print(f"  SMT placements: {len(smt_refs)}")
    print(f"  THT (hand solder, not in BOM/CPL): {len(tht_refs)} -> {', '.join(sorted(tht_refs))}")
    print(f"  Gerber files in ZIP: {gerber_count}")
    print(f"  Drill diameters (mm): {', '.join(drill_sizes)}")
    for asset in assets:
        print(f"  {asset.name}  {sha256(asset)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
