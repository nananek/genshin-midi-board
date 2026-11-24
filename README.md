# RP2040 MIDI → NKRO HID + USB-MIDI

USB MIDI キーボードを USB-A で受け、PC へは NKRO HID キーボード、iPad へは USB-MIDI デバイスとして同時に見せる基板の設計案です。

**RP2040（QFN-56）+ CH345T + 4 層基板**の構成です。外形は **62.0 × 35.0 mm**、四隅 2 mm の 45° パンチカットです。USB-C は長辺に 29.0 mm ピッチで離し、樹脂部が干渉しない余裕を確保します。ケースは A4 から作る紙ケース（内寸 63 × 36 × 9 mm）を想定しています。展開図は [docs/paper_case.md](docs/paper_case.md) と [docs/paper_case_a4.pdf](docs/paper_case_a4.pdf) にあります。

> 回路図と PCB の初期版を追加しました。回路図は ERC 0、PCB は 4 層で 0 DRC・未接続 0 です。実機検証はまだです。

## 結論

| 項目 | 採用 |
| --- | --- |
| MCU | RP2040 QFN-56 |
| MIDI デバイス側 | CH345T（UART 31250 ↔ USB-MIDI） |
| 基板 | 62.0 × 35.0 × 1.6 mm、4 層、四隅 2 mm パンチカット |
| USB-A | PIO-USB ホスト |
| USB-C 1 | RP2040 native USB、NKRO HID → PC |
| USB-C 2 | CH345T、USB-MIDI → iPad |
| スイッチ | SW1〜SW5（4 × スライド、1 × タクト） |
| 製造 | JLCPCB、4 層、0.5/0.3 mm ビア（最終ホップは 0.45/0.25 mm）、via-in-pad なし |

## 構成の要点

RP2040 の QFN-56 は 0.4 mm ピッチで、外周パッドを外側へ逃がすだけで全ピンを引き出せます。4 層なら GND プレーンを保ちながら標準ビアだけで配線できます。ファームウェアは pico-sdk で、PIO-USB、native USB、UART1 を使います。

詳しい設計は [docs/design.md](docs/design.md) と [docs/decisions.md](docs/decisions.md) を参照してください。

## 3 ポートの構成

```text
[USB MIDI キーボード]
      │ USB-A (J2)
      ▼
  PIO-USB host (GP12/13)
      │
      ├── Note On/Off ──► RP2040 native USB ── USB-C (J1) ──► PC (NKRO HID)
      │
      └── raw MIDI ── UART1 31250 (GP4/5) ──► CH345T ── USB-C (J3) ──► iPad (USB-MIDI)
```

PC と iPad は物理的に別ポートです。PC 側が未接続でも iPad へ MIDI は流れ、iPad 側が未接続でも PC へ HID は流れます。基板の電源は J1 または J3 の VBUS からダイオード OR で取ります。

## 基板外形とコネクタ

```text
         J1 USB-C (PC)              J3 USB-C (iPad)
         x=16.5                     x=45.5
    ┌────┐                            ┌────┐
    │    │        SW5 RESET           │    │
    │    │           ●                │    │
    ├────┴────────────────────────────┴────┤
    │                                       │
 SW1│                                       │SW3
 SW2│          RP2040 / flash              │
    │          CH345 / power               │
    │                                       │
    ├────┬────────────────────────────┬────┤
    │SW4 │        J2 USB-A            │    │
    └────┘    (MIDI キーボード)        └────┘
```

- 基板: 62.0 × 35.0 mm、t1.6 mm、4 層、四隅 2 mm の 45° パンチカット
- J1/J3: 上長辺、中心間 **29.0 mm**。コートヤード間の隙間は **18.36 mm**
- J2: 下長辺、USB-A レセプタクル。口は基板外へ出す
- J1/J3 の口は基板端から外へ出す。紙ケースの上壁に 2 か所、下壁に 1 か所の開口を開ける
- Type-C を 10 mm ピッチに寄せるとケーブルの樹脂部が干渉する。今回は同じ失敗を避けるため、29 mm ピッチを確保する

## スイッチ

スイッチは SW1〜SW5 の 5 個です。

| Ref | 部品 | 機能 | 接続 |
| --- | --- | --- | --- |
| SW1 | NKK 115643 スライド | 原神モード（HID ミュート） | GP28 ↔ GND |
| SW2 | NKK 115643 スライド | 楽器モード（スメール音階） | GP29 ↔ GND |
| SW3 | NKK 115643 スライド | サステイン（CC64） | GP27 ↔ GND |
| SW4 | NKK 115643 スライド | USB-A VBUS 手動 ON/OFF | TPS2553 EN 制御 |
| SW5 | DTS-63-N-V-BLK タクト | MIDI リセット（CC123/CC121） | GP14 ↔ GND |

スライドスイッチは 3 ピン品の中央コモンを GPIO、片側を GND、残りを NC にします。GPIO は内部プルアップ、アクティブ LOW、20 ms デバウンスです。SW5 は片側 2 ピンを GND、反対側 2 ピンを GP14 に束ねます。

## ファイル構成

```text
README.md                         この文書
AGENTS.md                         作業ルール（製造データの配布を含む）
docs/design.md                    詳細設計（電源、ピン、回路、配置）
docs/decisions.md                 設計判断と採用理由
docs/jlcpcb.md                    JLCPCB 向け製造制約と発注チェック
docs/firmware.md                  ファームウェアの実装メモ
docs/paper_case.md                紙ケースの印刷・折り手順
docs/paper_case_a4.pdf            A4 1:1 の紙ケース展開図
hardware/rp2040_midi_bridge/design.yaml 設計の単一ソース
hardware/rp2040_midi_bridge/pinmap.csv  ピン割り当て
hardware/rp2040_midi_bridge/bom.csv     BOM
hardware/rp2040_midi_bridge/floorplan.svg 配置検討図（生成物）
firmware/include/board_pins.h     ファームウェア用ボード定義
scripts/gen_floorplan.py          配置図生成
scripts/check_design.py           設計制約チェック
tests/test_design.py              設計制約の単体テスト
```

## 検証

```sh
make check          # 設計制約チェック + 単体テスト
make floorplan      # hardware/rp2040_midi_bridge/floorplan.svg を再生成
make silk           # 基板名、USB-A のピン名、裏面 QR を更新
```

`make check` は次を確認します。

- 基板寸法、層数、パンチカット
- USB-C 2 ポートのピッチとエッジ余裕
- ビア径・ドリル径（0.5/0.3 mm と 0.45/0.25 mm、0.15/0.2 mm なし）
- via-in-pad / plugged via の禁止
- ピン割り当ての重複
- スイッチ 5 個の機能と接続
- BOM の SMT 部品に LCSC 型番があること

## 製造データの配布

ガーバー、ドリル、BOM、CPL は設計データとは分けて扱います。リポジトリにはコミットせず、検証済みのリビジョンだけをリリースとして配布します。`make fab VERSION=v0.0.4` で、JLCPCB にそのままアップロードできる Gerber ZIP、BOM、CPL を `dist/` に作ります。Gerber ZIP は展開せず PCB のアップロードへ、BOM と CPL は SMT の欄へ個別に渡します。手順と禁止事項は [AGENTS.md](AGENTS.md) にまとめています。

## ライセンス

[MIT](LICENSE) です。`hardware/rp2040_midi_bridge/lib/` の KiCad シンボルは公式 KiCad ライブラリ由来で、CC-BY-SA 4.0（設計への利用例外あり）です。製造データの配布条件は [AGENTS.md](AGENTS.md) を参照してください。
