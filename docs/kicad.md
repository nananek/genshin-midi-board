# KiCad 作業手順

## 1. ツール

KiCad 10.0.7 を Docker で使います。ホストに KiCad を入れる必要はありません。

```sh
./scripts/kicad.sh kicad-cli version
./scripts/kicad.sh python3 -c "import pcbnew; print(pcbnew.Version())"
```

`scripts/kicad.sh` はリポジトリを `/work` にマウントし、rootless Docker で書き込み権限が合わない場合はコンテナ内だけ root に切り替えます。

## 2. プロジェクト

```text
hardware/rp2040_midi_bridge/
  rp2040_midi_bridge.kicad_pro
  rp2040_midi_bridge.kicad_sch
  rp2040_midi_bridge.kicad_pcb
  sym-lib-table
  fp-lib-table
  lib/                    プロジェクト固有のシンボルとフットプリント
  erc.rpt
  drc.rpt
```

`design.yaml` と `netlist.yaml` が設計の正本です。回路図と PCB はこの 2 つから生成するか、少なくとも差分を照合します。

## 3. 回路図

```sh
make erc
# または
./scripts/kicad.sh kicad-cli sch erc --severity-all \
  --output hardware/rp2040_midi_bridge/erc.rpt \
  hardware/rp2040_midi_bridge/rp2040_midi_bridge.kicad_sch
```

ERC は 0 error を目標にします。ライブラリ未読込の警告は、プロジェクトローカルの `sym-lib-table` と `lib/` で解消します。

## 4. PCB

```sh
make drc
# または
./scripts/kicad.sh kicad-cli pcb drc --severity-all \
  --output hardware/rp2040_midi_bridge/drc.rpt \
  hardware/rp2040_midi_bridge/rp2040_midi_bridge.kicad_pcb
```

DRC は 0 violations / 0 unconnected を目標にします。配線途中で未接続が残る場合は、`drc.rpt` の unconnected 数を記録します。

基板名、J2 のピン名、裏面の QR コードは `make silk` で更新します。`gen_pcb.py` から基板を作り直す場合も、同じ `silk_art.py` を使います。

```sh
make silk
```

## 5. 製造前の監査

```sh
make kicad-check
```

`make kicad-check` は ERC、DRC、`scripts/check_kicad_pcb.py` を実行します。`check_kicad_pcb.py` は次を機械的に確認します。

- 基板外形が 62.0 × 35.0 mm
- 4 層（F.Cu / In1.Cu / In2.Cu / B.Cu）
- ビアが 0.5/0.3 mm または 0.45/0.25 mm
- 0.15 / 0.2 mm ドリルがない
- via-in-pad がない
- plugged / capped / filled がない
- blind / buried / micro via がない

## 6. スタックアップ

| 層 | 役割 |
| --- | --- |
| F.Cu | 部品、USB、信号、GND ベタ |
| In1.Cu | ベタ GND |
| In2.Cu | +3V3 プレーン |
| B.Cu | 信号、GND ベタ、THT のはんだ面 |

4 層、t1.6 mm、外層 1 oz、内層 0.5 oz、HASL lead-free を想定します。

## 7. 配線の優先順位

1. USB-A D+/D-（GP12/13 → 22 Ω → USBLC6 → J2）
2. native USB D+/D-（RP2040 pin46/47 → 27 Ω → USBLC6 → J1）
3. CH345T USB D+/D- → J3
4. QSPI（RP2040 pin51-56 → W25Q128）
5. 水晶（X1/X2）
6. +5V / +3V3 / VBUS
7. スイッチ GPIO

USB は Full-Speed なのでインピーダンス制御は必須ではありませんが、D+/D- は同一層を基本とし、長さ差 2 mm 以内にします。

## 8. 発注データ

タグを打つコミットで `make fab` を実行すると、JLCPCB にそのままアップロードできるファイル一式を作ります。

```sh
make check
make erc
make drc
make fab VERSION=v0.0.4
```

出力は次の 6 ファイルです。

```text
dist/rp2040_midi_bridge-v0.0.4-gerber.zip        PCB 用。展開せずアップロードする
dist/rp2040_midi_bridge-v0.0.4-bom.csv           SMT BOM
dist/rp2040_midi_bridge-v0.0.4-cpl.csv           SMT CPL
dist/rp2040_midi_bridge-v0.0.4-README.txt        タグ、コミット、アップロード手順
dist/rp2040_midi_bridge-v0.0.4-LICENSE           MIT
dist/rp2040_midi_bridge-v0.0.4-manifest.sha256   上記 5 ファイルの SHA-256
```

Gerber ZIP は直下に Gerber X2、Excellon ドリル、`.gbrjob` だけを入れます。BOM と CPL は SMT のアップロード欄へ個別に渡します。`dist/` はコミットしません。

Gerber、ドリル、CPL は基板左下のドリル/配置原点を共有します。`gen_pcb.py` が原点を (0, 35) に設定し、`make fab` は Gerber を `--use-drill-file-origin`、ドリルを `--drill-origin plot` で出力します。J1/J3 の CPL は JLCPCB の USB-C 部品原点に合わせて 1.571 mm 補正しています。配布条件と構成は [AGENTS.md](../AGENTS.md) の 3 節を参照してください。JLCPCB のチェック項目は [jlcpcb.md](jlcpcb.md) にあります。

## 9. 注意

- 0.15 mm ドリルを 1 本でも入れると、JLCPCB の advanced オプションが付きます。以前の試作で実際にオプション料金が付きました。
- Type-C の A7/B7 はパッド内ビアを使わず、パッド外のビアへドッグボーンで逃がします。
- RP2040 のサーマルパッド内にビアを置きません。
- USB-C は 29.0 mm ピッチを維持します。
