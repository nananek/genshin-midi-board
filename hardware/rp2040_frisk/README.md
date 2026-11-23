# RP2040 Frisk 基板（設計検討）

62 × 35 mm、4 層、RP2040 + CH345T の設計検討データです。回路図は `rp2040_frisk.kicad_sch` にあり、ERC 0 で通ります。PCB は 4 層・0 DRC まで来ていますが、未接続 23 点が残っています。

## ファイル

| ファイル | 内容 |
| --- | --- |
| `design.yaml` | 基板、コネクタ、配置、スイッチ、ピン、BOM、製造ルールの正本 |
| `netlist.yaml` | 82 部品、53 ネットのピン接続。回路図と PCB の共通ソース |
| `pinmap.csv` | ピン割り当て（`design.yaml` から生成） |
| `bom.csv` | BOM（`design.yaml` から生成） |
| `placement.csv` | コネクタと主要部品の配置（`design.yaml` から生成） |
| `floorplan.svg` | 配置・干渉検討図（`scripts/gen_floorplan.py` から生成） |
| `rp2040_frisk.kicad_pro` / `.kicad_sch` | KiCad 10 の回路図プロジェクト（`netlist.yaml` から生成） |
| `sym-lib-table` / `fp-lib-table` | プロジェクトローカルと公式のライブラリ参照 |
| `lib/` | 公式に無いシンボルとフットプリント（`lib/README.md` 参照） |
| `erc.rpt` | `kicad-cli sch erc --severity-all` の結果 |
| `rp2040_frisk.kicad_pcb` | KiCad 10 基板（0 DRC、未接続 23） |
| `drc.rpt` | `kicad-cli pcb drc --severity-all` の結果 |

## 再生成

```sh
make tables
make netlist
make floorplan
make check
```

回路図は `netlist.yaml` から生成します。KiCad 10 のコンテナで実行してください。

```sh
./scripts/kicad.sh python3 hardware/rp2040_frisk/scripts/gen_sch.py
make erc
```

## 外形

- 62 × 35 mm、t1.6 mm
- 四隅 2 mm の 45° パンチカット
- 固定穴なし

## コネクタ

| Ref | 種類 | 位置 | 役割 |
| --- | --- | --- | --- |
| J1 | USB-C | 上辺 x=14.0 | PC / NKRO HID |
| J3 | USB-C | 上辺 x=43.0 | iPad / USB-MIDI |
| J2 | USB-A | 下辺 x=29.5 | microKEY2 |

J1/J3 の中心間は 29.0 mm、コートヤード間は 18.36 mm です。Type-C ケーブルの樹脂部が干渉しない余裕を確保しています。

## 注意

このディレクトリのデータは設計検討用です。KiCad の PCB、ガーバー、BOM/CPL は含みません。発注前に [../../docs/jlcpcb.md](../../docs/jlcpcb.md) のチェックリストを実行してください。
