# RP2040 Frisk MIDI → NKRO HID + USB-MIDI

USB MIDI キーボード（KORG microKEY2）を USB-A で受け、PC へは NKRO HID キーボード、iPad へは USB-MIDI デバイスとして同時に見せる基板の設計案です。

RP2350A ベアチップ + 6 層基板の構成を、**RP2040（QFN-56）+ CH345T + 4 層基板**に置き換えます。外形は `nananek/serial-km-emulator` と同じ 57.6 × 31.4 mm、四隅 2 mm の 45° パンチカットです。USB-C は長辺に 29.0 mm ピッチで離し、樹脂部が干渉しない余裕を確保します。

> このリポジトリは**設計検討（design study）**です。回路図・PCB 配線・DRC/ERC・実機検証はまだ含みません。次の工程で KiCad に落とします。

## 結論

| 項目 | 採用 |
| --- | --- |
| MCU | RP2040 QFN-56（RP2350A ベアチップから変更） |
| MIDI デバイス側 | CH345T（UART 31250 ↔ USB-MIDI） |
| 基板 | 57.6 × 31.4 × 1.6 mm、4 層、四隅 2 mm パンチカット |
| USB-A | PIO-USB ホスト（KORG microKEY2） |
| USB-C 1 | RP2040 native USB、NKRO HID → PC |
| USB-C 2 | CH345T、USB-MIDI → iPad |
| スイッチ | 元実装の SW1〜SW6 を維持（5 × スライド、1 × タクト） |
| 製造 | JLCPCB、4 層、0.5/0.3 mm ビア、via-in-pad なし |

## なぜ RP2040 か

RP2350A の QFN-60 は、今回の 3 ポート + CH345 + スイッチを 4 層でまとめると、QFN の逃げと Type-C の A7/B7 逃げが窮屈になり、via-in-pad や 0.15 mm ドリルに手を伸ばしやすい構成でした。実際、現行の 6 層版は U1 pin22 と J3 A7/B7 に via-in-pad を使っています。

RP2040 の QFN-56 は 0.4 mm ピッチで、外周パッドを外側へ逃がすだけで全ピンを引き出せます。Raspberry Pi Pico は同じ QFN-56 を 2 層で使っており、4 層なら GND プレーンを保ちながら標準ビアだけで配線できます。ファームウェアも pico-sdk のままで、PIO-USB、native USB、UART1 の使い方は RP2350 とほぼ同じです。

詳しい比較は [docs/design.md](docs/design.md) と [docs/decisions.md](docs/decisions.md) を参照してください。

## 3 ポートの構成

```text
[KORG microKEY2]
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
         x=14.0                     x=43.0
    ┌────┐                            ┌────┐
    │    │        SW6 RESET           │    │
    │    │           ●                │    │
    ├────┴────────────────────────────┴────┤
    │                                       │
 SW1│                                       │SW3
 SW2│          RP2040 / flash              │
    │          CH345 / power               │
    │                                       │
    ├────┬────────────────────────────┬────┤
    │SW4 │        J2 USB-A            │SW5 │
    └────┘       (microKEY2)          └────┘
```

- 基板: 57.6 × 31.4 mm、t1.6 mm、4 層、四隅 2 mm の 45° パンチカット
- J1/J3: 上長辺、中心間 **29.0 mm**。コートヤード間の隙間は **18.36 mm**
- J2: 下長辺、USB-A レセプタクル。口は基板外へ出す
- J1/J3 の口は基板端から外へ出す。ケースを使う場合は上壁に 2 か所、下壁に 1 か所の開口を開ける
- serial-km-emulator の PR #16/#23 では Type-C を 10 mm ピッチに寄せて樹脂部が干渉した。今回は同じ失敗を避けるため、29 mm ピッチを確保する

## スイッチ

元実装（`rp2350_zero_carrier`）の SW1〜SW6 をそのまま残します。

| Ref | 部品 | 機能 | 接続 |
| --- | --- | --- | --- |
| SW1 | NKK 115643 スライド | 原神モード（HID ミュート） | GP28 ↔ GND |
| SW2 | NKK 115643 スライド | 楽器モード（スメール音階） | GP29 ↔ GND |
| SW3 | NKK 115643 スライド | 予備 | GP27 ↔ GND |
| SW4 | NKK 115643 スライド | USB-A VBUS 手動 ON/OFF | TPS2553 EN 制御 |
| SW5 | NKK 115643 スライド | サステイン（CC64） | GP26 ↔ GND |
| SW6 | DTS-63-N-V-BLK タクト | MIDI リセット（CC123/CC121） | GP14 ↔ GND |

スライドスイッチは 3 ピン品の中央コモンを GPIO、片側を GND、残りを NC にします。GPIO は内部プルアップ、アクティブ LOW、20 ms デバウンスです。SW6 は片側 2 ピンを GND、反対側 2 ピンを GP14 に束ねます。

## ファイル構成

```text
README.md                         この文書
docs/design.md                    詳細設計（電源、ピン、回路、配置）
docs/decisions.md                 代替案の比較と採用理由
docs/jlcpcb.md                    JLCPCB 向け製造制約と発注チェック
docs/firmware.md                  ファームウェア移植メモ
hardware/rp2040_frisk/design.yaml 設計の単一ソース
hardware/rp2040_frisk/pinmap.csv  ピン割り当て
hardware/rp2040_frisk/bom.csv     BOM
hardware/rp2040_frisk/floorplan.svg 配置検討図（生成物）
firmware/include/board_pins.h     ファームウェア用ボード定義
scripts/gen_floorplan.py          配置図生成
scripts/check_design.py           設計制約チェック
tests/test_design.py              設計制約の単体テスト
```

## 検証

```sh
make check          # 設計制約チェック + 単体テスト
make floorplan      # hardware/rp2040_frisk/floorplan.svg を再生成
```

`make check` は次を確認します。

- 基板寸法、層数、パンチカット
- USB-C 2 ポートのピッチとエッジ余裕
- ビア径・ドリル径（0.5/0.3 mm のみ、0.15 mm なし）
- via-in-pad / plugged via の禁止
- ピン割り当ての重複
- スイッチ 6 個の機能と接続
- BOM の SMT 部品に LCSC 型番があること
