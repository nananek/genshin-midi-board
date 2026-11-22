# RP2040 Frisk 基板（設計検討）

57.6 × 31.4 mm、4 層、RP2040 + CH345T の設計検討データです。回路図と PCB 配線はまだありません。

## ファイル

| ファイル | 内容 |
| --- | --- |
| `design.yaml` | 基板、コネクタ、配置、スイッチ、ピン、BOM、製造ルールの正本 |
| `netlist.yaml` | 83 部品、54 ネットのピン接続。回路図と PCB の共通ソース |
| `pinmap.csv` | ピン割り当て（`design.yaml` から生成） |
| `bom.csv` | BOM（`design.yaml` から生成） |
| `placement.csv` | コネクタと主要部品の配置（`design.yaml` から生成） |
| `floorplan.svg` | 配置・干渉検討図（`scripts/gen_floorplan.py` から生成） |
| `rp2040_frisk.kicad_sch` | KiCad 10 回路図（次の工程で追加） |
| `rp2040_frisk.kicad_pcb` | KiCad 10 基板（次の工程で追加） |

## 再生成

```sh
make tables
make floorplan
make check
```

## 外形

- 57.6 × 31.4 mm、t1.6 mm
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

このディレクトリのデータは設計検討用です。KiCad の回路図、PCB、ガーバー、BOM/CPL は含みません。発注前に [../../docs/jlcpcb.md](../../docs/jlcpcb.md) のチェックリストを実行してください。
