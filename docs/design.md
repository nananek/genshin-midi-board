# 詳細設計

## 1. 設計の要点

RP2350A ベアチップ + 6 層基板の構成を、RP2040 QFN-56 + CH345T + 4 層基板に置き換えます。機能は次の 3 ポートです。

1. USB-A: KORG microKEY2 を PIO-USB ホストで受ける
2. USB-C: PC へ NKRO HID キーボードを出す
3. USB-C: iPad へ USB-MIDI デバイスを出す

MCU は 1 個、USB デバイスコントローラは RP2040 の native USB と CH345T の 2 個です。PC と iPad は物理的に別ポートなので、片方が未接続でももう片方は動作します。

この文書は設計検討であり、回路図・PCB 配線・DRC/ERC はまだありません。数値の正本は [design.yaml](../hardware/rp2040_frisk/design.yaml) です。

## 2. ブロック図

```text
                +-------------------------------+
 KORG microKEY2 |                               |
   USB-A (J2)   |  PIO-USB host                 |
      |         |  GP12/13                      |
      +-------->|                               |
                |  RP2040                       |      USB-C (J1)      +------+
                |  core1: MIDI parse            +----> native USB ----->| PC   |
                |  core1: raw MIDI -> UART1     |      27R + ESD        | HID  |
                |                               |                      +------+
                |  core0: NKRO HID              |
                |  core0: switches              |      USB-C (J3)      +------+
                |                               +----> CH345T --------->| iPad |
                |  UART1 GP4/5, 31250           |      USB-MIDI        | MIDI |
                +-------------------------------+                      +------+
```

RP2040 の core1 が PIO-USB ホストと MIDI パースを担当し、core0 が NKRO HID とスイッチを担当します。生 MIDI は UART1 から CH345T へそのまま流します。

## 3. 電源

```text
J1 VBUS -- D1 --+
                +-- +5V -- AP2112K-3.3 -- +3V3 -- RP2040 / flash / crystal
J3 VBUS -- D2 --+     |
                      +-- CH345T VCC
                      |
                      +-- TPS2553 IN -- OUT -- SW4 -- J2 VBUS
```

| レール | 電源 | 負荷 | 備考 |
| --- | --- | --- | --- |
| +5V | J1/J3 VBUS のダイオード OR | CH345T、TPS2553 | BAT54WS ×2。逆流防止 |
| +3V3 | AP2112K-3.3（600 mA） | RP2040、flash、水晶、LED | 1 uF 入力、1 uF 出力 |
| VBUS_USB_A | TPS2553（500 mA 制限） | microKEY2 | SW4 で手動 ON/OFF |

PC と iPad の両方が給電した場合は、VBUS の高い側から電流を取ります。BAT54WS の順方向電圧降下で +5V は約 4.7 V になります。CH345T の最低動作電圧（データシート記載値）と AP2112K の最低入力電圧を発注前に確認してください。

電流の見積もりは、RP2040 が約 50 mA、CH345T が約 20 mA、microKEY2 が約 100 mA、LED とその他が約 10 mA です。合計 200 mA 弱で、AP2112K の 600 mA と TPS2553 の 500 mA に収まります。

## 4. USB-A ホスト（キーボード）

RP2040 の PIO-USB をホストとして使います。D+ は GP12、D- は GP13 です。PIO-USB は D- が D+ の隣の GPIO であることを要求するため、この並びを崩しません。

- GP12 → 22 Ω → USBLC6-2SC6 → J2 D+
- GP13 → 22 Ω → USBLC6-2SC6 → J2 D-
- J2 VBUS は TPS2553 の OUT から SW4 を経由して供給
- J2 VBUS に 100 uF（C27）と 100 nF（C26）
- TPS2553 の ILIM は 52.3 kΩ（500 mA 設定）
- TPS2553 の EN は 100 kΩ で GND にプルダウンし、SW4 で +3V3 に接続
- FAULT は 100 kΩ で +3V3 にプルアップし、テストパッドへ出す

KORG microKEY2 は USB バスパワーで動作するクラスコンプライアントの USB-MIDI キーボードです。PIO-USB ホストの VBUS は 5 V、500 mA 制限で十分です。

PIO-USB は 120 MHz のシステムクロックを要求します。RP2040 の 12 MHz 水晶から 120 MHz を作れるため、`set_sys_clock_khz(120000, true)` をそのまま使えます。

## 5. USB-C（PC、NKRO HID）

RP2040 の native USB をデバイスとして使い、NKRO HID キーボードを出します。

- USB_DP（pin 47）→ 27 Ω → USBLC6-2SC6 → J1 D+
- USB_DM（pin 46）→ 27 Ω → USBLC6-2SC6 → J1 D-
- J1 CC1/CC2 → 各 5.1 kΩ → GND
- J1 VBUS → D1 → +5V
- J1 VBUS に 100 nF（C24）

HID レポートは現行ファームウェアと同じ 5 バイト（modifier 1 + キービットマップ 4）の NKRO です。PC 側は USB 2.0 Full-Speed の HID キーボードとして見えます。

## 6. USB-C（iPad、USB-MIDI）

CH345T を UART 31250 と USB-MIDI のブリッジとして使います。

| CH345T pin | 機能 | 接続 |
| --- | --- | --- |
| 1 | RST | 10 kΩ で +5V にプルアップ、TP11 へ【要確認】 |
| 3 | MOUT | RP2040 GP5（UART1 RX） |
| 4 | MIN | RP2040 GP4（UART1 TX） |
| 5 | V3 | 100 nF → GND |
| 6 | UD+ | 22 Ω → USBLC6-2SC6 → J3 D+ |
| 7 | UD- | 22 Ω → USBLC6-2SC6 → J3 D- |
| 8, 17 | GND | GND |
| 9 | XI | Y2 12 MHz |
| 10 | XO | Y2 12 MHz |
| 19 | VCC | +5V、100 nF + 10 uF |
| 2, 11-16, 18, 20 | NC | 未接続 |

J3 の CC1/CC2 は各 5.1 kΩ で GND に落とします。J3 VBUS は D2 経由で +5V に入れ、CH345T の電源にします。

現行基板は CH345T の RST を GND に直結しています。CH345T のリセット極性をデータシートで確認し、GND 直結が正しいかを発注前に確定してください。この設計案では、10 kΩ プルアップとテストパッドを置き、必要ならテストパッドで GND に落とせる形にしています。

CH345T の水晶負荷容量は現行基板と同じ 22 pF の暫定値です。データシート推奨値で確定します。

## 7. RP2040 の最小構成

| 項目 | 接続 |
| --- | --- |
| QSPI flash | U2 W25Q128JVSIQ、RP2040 pin 51-56 |
| 水晶 | Y1 12 MHz、XIN pin 20 / XOUT pin 21、15 pF ×2、XOUT に 1 kΩ 直列 |
| VREG_IN | pin 44、+3V3、1 uF |
| VREG_VOUT | pin 45、+1V1、1 uF + 100 nF |
| DVDD | pin 23 / 50、+1V1、100 nF ×2 |
| IOVDD | pin 1 / 10 / 22 / 33 / 42 / 49、+3V3、100 nF ×6 |
| USB_VDD | pin 48、+3V3、100 nF |
| ADC_AVDD | pin 43、+3V3、100 nF |
| TESTEN | pin 19、GND |
| RUN | pin 26、10 kΩ で +3V3、TP6 |
| SWD | pin 24/25、TP4/TP5 |
| BOOTSEL | QSPI_SS（pin 56）、TP7、1 kΩ 経由で GND に落とす |
| サーマルパッド | pin 57、GND |

QSPI は RP2040 の専用ピン（51-56）を使います。GPIO0-5 は QSPI に使われません。QSPI の配線は 25 mm 以内、等長 2 mm 以内、スタブなしにします。

RP2040 のサーマルパッド内にはビアを置きません。F.Cu の GND からパッド外の 0.5/0.3 mm ビアへ落とし、In1 の GND プレーンに接続します。最終ホップだけ 0.45/0.25 mm を使います。

## 8. ピン割り当て

| 機能 | RP2040 pin | GPIO | ネット | 接続先 |
| --- | --- | --- | --- | --- |
| PIO-USB D+ | 15 | GP12 | USB_A_DP_GP12 | 22 Ω → U6 → J2 D+ |
| PIO-USB D- | 16 | GP13 | USB_A_DM_GP13 | 22 Ω → U6 → J2 D- |
| CH345T MIN（TX） | 6 | GP4 | MIDI_UART_TX | CH345T pin 4 |
| CH345T MOUT（RX） | 7 | GP5 | MIDI_UART_RX | CH345T pin 3 |
| native USB D+ | 47 | - | USB_PC_DP | 27 Ω → U7 → J1 D+ |
| native USB D- | 46 | - | USB_PC_DM | 27 Ω → U7 → J1 D- |
| 原神モード SW1 | 40 | GP28 | SW1_MUTE | SW1 pin 2 |
| 楽器モード SW2 | 41 | GP29 | SW2_LYRE | SW2 pin 2 |
| サステイン SW3 | 39 | GP27 | SW3_SUSTAIN | SW3 pin 2 |
| MIDI リセット SW6 | 17 | GP14 | SW6_RESET | SW6 pin 3/4 |
| ステータス LED | 37 | GP25 | STATUS_LED | 1 kΩ → LED1 → GND |
| デバッグ UART TX | 2 | GP0 | UART0_TX | TP1 |
| デバッグ UART RX | 3 | GP1 | UART0_RX | TP2 |
| QSPI | 51-56 | - | QSPI_* | U2 |
| 水晶 | 20/21 | - | XIN/XOUT | Y1 |
| SWD | 24/25 | - | SWCLK/SWDIO | TP4/TP5 |
| RUN | 26 | - | RUN | TP6 |
| BOOTSEL | 56 | - | QSPI_SS | TP7 |

GPIO6-11、GPIO15-24 は未使用です。テストパッドか将来の拡張に残します。

## 9. スイッチ

| Ref | 部品 | 機能 | 接続 | 動作 |
| --- | --- | --- | --- | --- |
| SW1 | NKK 115643 | 原神モード | GP28 ↔ GND | ON で NKRO HID をミュート。UART の MIDI は継続 |
| SW2 | NKK 115643 | 楽器モード | GP29 ↔ GND | ON でスメール音階に切り替え |
| SW3 | NKK 115643 | サステイン | GP27 ↔ GND | ON で CC64=127、OFF で CC64=0 |
| SW4 | NKK 115643 | USB-A VBUS | TPS2553 EN | ON で USB-A へ 5 V を供給 |
| SW6 | DTS-63-N-V-BLK | MIDI リセット | GP14 ↔ GND | 押下で CC123 と CC121 を全チャンネルへ送る |

スライドスイッチは 3 ピン品の中央コモンを GPIO、片側を GND、残りを NC にします。GPIO は内部プルアップ、アクティブ LOW、20 ms デバウンスです。SW6 は 4 ピンの片側 2 本を GND、反対側 2 本を GP14 に束ねます。

SW4 は USB-A の VBUS を直接切らず、TPS2553 の EN を制御します。スイッチに 500 mA を流さないため、NKK 115643 の定格を気にせず使えます。

## 10. 基板と配置

### 外形

- 62.0 × 35.0 mm、t1.6 mm、4 層
- 四隅 2 mm の 45° パンチカット
- 固定穴なし。紙ケース、両面テープ、スポンジで固定
- 表面のみ SMT 実装。THT は手はんだ

### コネクタ

| Ref | 種類 | 位置（中心） | 向き | 備考 |
| --- | --- | --- | --- | --- |
| J1 | USB-C | (16.5, 2.4) | 口は上 | PC / NKRO HID |
| J3 | USB-C | (45.5, 2.4) | 口は上 | iPad / USB-MIDI |
| J2 | USB-A | (31.0, 31.6) | 口は下、180° | microKEY2 |

J1 と J3 の中心間は 29.0 mm、コートヤード間の隙間は 18.36 mm です。serial-km-emulator の PR #16 では 10 mm ピッチにした結果、2 本の Type-C ケーブルの樹脂部が干渉しました。今回は 29 mm ピッチを確保し、同じ失敗を避けます。

J1/J3 のコートヤードは基板左右端から 11.18 mm 内側にあります。USB-C の口は基板端から外へ出るため、紙ケースの上壁に 2 か所の開口を開けます。J2 は下壁に 1 か所です。

### スイッチ

- SW1 / SW2: 左短辺、y=9.0 / 24.5、アクチュエータは左
- SW3: 右短辺、y=9.0、アクチュエータは右。サステインに使う
- SW4: 下長辺の左寄り、x=15.0、アクチュエータは下
- SW6: 上長辺の中央、x=31.0、タクトの押し子は上

SW6 は J1 と J3 の間の 18 mm の隙間に置きます。USB-C ケーブルの樹脂部は J1/J3 の中心から約 6 mm まで広がるため、中央のタクトには触れません。

### 主要部品の配置

| Ref | 部品 | 中心 | 回転 | 目的 |
| --- | --- | --- | --- | --- |
| U1 | RP2040 | (20.0, 12.5) | 270° | 中央左。QSPI を U2 へ向ける |
| U2 | W25Q128 | (32.0, 12.0) | 90° | QSPI を短く |
| U3 | CH345T | (44.0, 12.5) | 0° | J3 の近く |
| U4 | AP2112K | (27.0, 20.1) | 0° | USB-A の上 |
| U5 | TPS2553 | (18.0, 20.2) | 0° | USB-A の左 |
| U6 | USBLC6（USB-A） | (22.6, 20.1) | 0° | J2 の近く |
| U7 | USBLC6（PC） | (12.9, 9.6) | 0° | J1 の近く |
| U8 | USBLC6（iPad） | (37.0, 9.7) | 0° | J3 の近く |
| X1 | 12 MHz（RP2040） | (12.6, 13.4) | 0° | XIN/XOUT の近く |
| X2 | 12 MHz（CH345T） | (38.8, 19.4) | 0° | CH345T の近く |

配置検討図は [floorplan.svg](../hardware/rp2040_frisk/floorplan.svg) です。この図は外形・コネクタ・スイッチ・主要 IC の干渉を見るためのもので、製造データではありません。

### 紙ケース

外形 62.0 × 35.0 mm に合わせ、A4 から作る 1 枚折りの紙ケースを用意しています。

| 項目 | 値 |
| --- | --- |
| 内寸 | 63.0 × 36.0 × 9.0 mm |
| 用紙 | 0.3 mm のカードストック（220 g/m² 程度） |
| 印刷 | A4 横、100%、用紙に合わせない |
| 開口 | USB-C ×2（後壁）、USB-A（前壁）、SW1/SW2（左壁）、SW3（右壁）、SW4（前壁）、SW6（後壁＋蓋）、LED（蓋） |

展開図と折り方は [paper_case.md](paper_case.md) を参照してください。基板は底面に置くだけで、固定穴はありません。

### スタックアップ

| 層 | 役割 |
| --- | --- |
| F.Cu | 部品、USB、信号、GND ベタ |
| In1.Cu | ベタ GND |
| In2.Cu | +3V3 プレーン |
| B.Cu | 信号、GND ベタ、THT のはんだ面 |

USB は Full-Speed（12 Mbps）なのでインピーダンス制御は必須ではありませんが、D+/D- は同一層を通し、In1 の GND を基準にします。QSPI と水晶の下は In1 を分割しません。

### 配線ルール

- USB D+/D- は同一層、長さ差 2 mm 以内。USB-A 側は 22 Ω、native USB は 27 Ω の直列抵抗をコネクタ近傍に置く。
- Type-C の A7/B7 はパッド内ビアを使わず、パッド外の 0.5/0.3 mm ビアへドッグボーンで逃がす。最終ホップだけ 0.45/0.25 mm を使う。PR #22 と同じ考え方。
- QFN-56 のパッドは外側へ 0.127 mm で逃がし、パッド列の外に 0.5/0.3 mm ビアを置く。最終ホップは 0.45/0.25 mm。0.15/0.2 mm ドリルは使わない。
- QSPI は 25 mm 以内、等長 2 mm 以内。水晶は XIN/XOUT の近くに置き、GND ガードを入れる。
- +5V と VBUS は 0.8 mm 以上。USB-A の VBUS は 1.0 mm を基本にする。
- ビアは 0.5 mm 径 / 0.3 mm ドリルを基本とし、最終ホップだけ 0.45 mm 径 / 0.25 mm ドリル。テントのまま。プラグ、キャップ、フィルはしない。
- SMD パッド内にビアを置かない。サーマルパッドも同じ。
- 基板端から銅まで 0.3 mm 以上。

## 11. BOM

詳細は [bom.csv](../hardware/rp2040_frisk/bom.csv) を参照してください。主要部品は次のとおりです。

| Ref | 部品 | LCSC | 実装 |
| --- | --- | --- | --- |
| U1 | RP2040 | C2040 | SMT |
| U2 | W25Q128JVSIQ | C97521 | SMT |
| U3 | CH345T | C5246448 | SMT |
| U4 | AP2112K-3.3TRG1 | C51118 | SMT |
| U5 | TPS2553DBVR | C55266 | SMT |
| U6-U8 | USBLC6-2SC6 | C7519 | SMT |
| J1/J3 | TYPE-C-31-M-12 | C165948 | SMT |
| J2 | USB-A 5075AR-04-WH | - | THT |
| SW1-SW4 | NKK 115643 | - | THT |
| SW6 | DTS-63-N-V-BLK | - | THT |

AP2112K-3.3TRG1 の LCSC 型番と C27 の 100 uF セラミックコンデンサは発注前に再確認します。

## 12. ファームウェア

現行の RP2350 ファームウェアを RP2040 に移します。ピン割り当ては GP4/5、GP12/13、GP27/28/29 をそのまま使うため、`config.h` の変更は最小です。GP27 は SW3 のサステイン、GP14 は MIDI リセット、GP25 は LED に使います。GP26 は未使用です。

ビルドは pico-sdk 2.x の `PICO_BOARD=pico` を基本にし、ボード定義でピンを上書きします。PIO-USB は RP2040 対応の `sekigon-gonnoc/Pico-PIO-USB` を使います。native USB は TinyUSB の HID、CH345T は UART1 の生 MIDI 出力です。

詳細は [firmware.md](firmware.md) を参照してください。

## 13. 検証

### 設計段階

- `make check` で外形、コネクタ間隔、ビア、ピン、スイッチ、BOM を確認
- KiCad で回路図を起こし、ERC 0 を確認
- PCB 配線後に DRC 0 / unconnected 0 を確認
- ドリルファイルに 0.15 mm がないことを確認
- via-in-pad がないことを DFM プレビューで確認
- BOM/CPL の回転補正を確認

### 実機

1. J1 を PC に接続し、NKRO HID キーボードとして認識される
2. J2 に microKEY2 を接続し、Note On/Off が UART0 ログに出る
3. J3 を iPad に接続し、USB-MIDI デバイスとして認識される
4. 3 和音以上を弾いて、PC 側で全キーが同時に押される
5. 黒鍵が無視される
6. SW1 で HID がミュートされ、SW2 で音階が変わる
7. SW3 で CC64 が送られ、SW6 で CC123/CC121 が送られる
8. SW4 を OFF にすると microKEY2 の VBUS が落ちる
9. PC と iPad の片方だけ給電しても動作する
10. キーボードを抜き差しして、HID の全キーが解放される

## 14. 未確定事項

- CH345T の RST 極性。現行基板は GND 直結。データシートで確認する。
- CH345T の水晶負荷容量。22 pF は暫定。
- AP2112K-3.3TRG1 の LCSC 型番。
- 100 uF 1210 セラミックコンデンサの型番と在庫。
- USB-A コネクタ（Neltron 5075AR-04-WH）の入手性。
- Type-C ケーブルの樹脂部寸法。29 mm ピッチで足りるか、実物で確認する。
- 紙ケースの開口位置。J1/J3 が上、J2 が下、スイッチが左右と下に増える。
- JLCPCB の 4 層スタックアップ、0.1 mm 配線間隔、0.2 mm ホール間隔、0.45 mm ビア径が標準範囲か。
- RP2040 の PIO-USB と CH345T の UART を同時に動かしたときの取りこぼし。実機で確認する。
- U1 の回転。配置図はブロック位置の検討であり、QSPI を U2 へ、native USB を J1 へ向ける回転は KiCad で決める。

## 付録: ネット接続

回路図を起こすときの接続メモです。パッシブの番号は [bom.csv](../hardware/rp2040_frisk/bom.csv) と突き合わせます。

### 電源

| ネット | 接続 |
| --- | --- |
| VBUS_PC | J1 A4/A9/B4/B9、C24、D1 アノード、U7 pin5 |
| VBUS_IPAD | J3 A4/A9/B4/B9、C25、D2 アノード、U8 pin5 |
| +5V | D1 カソード、D2 カソード、C28、U3 pin19、C20、C21、U4 pin1、C30、U5 pin1、C29 |
| +3V3 | U4 pin5、C4、C5、U1 pin1/10/22/33/42/49（IOVDD）、U1 pin44（VREG_IN）、U1 pin48（USB_VDD）、U1 pin43（ADC_AVDD）、U2 pin8、R10、R11、R12、R16、SW4 pin3、R13 |
| +1V1 | U1 pin45（VREG_VOUT）、C2、C3、U1 pin23/50（DVDD） |
| GND | 全コネクタ、IC、スイッチ、パッシブの GND |

### USB-A ホスト

| ネット | 接続 |
| --- | --- |
| USB_A_DP_GP12 | U1 pin15 → R3 22 Ω → U6 I/O1 → J2 pin3 |
| USB_A_DM_GP13 | U1 pin16 → R4 22 Ω → U6 I/O2 → J2 pin2 |
| VBUS_USB_A | U5 OUT → J2 pin1、C26、C27、U6 VBUS |
| TPS_EN | U5 EN、R10 100 kΩ → GND、SW4 pin2 |
| TPS_ILIM | U5 ILIM、R9 52.3 kΩ → GND |
| TPS_FAULT | U5 FAULT、R11 100 kΩ → +3V3、TP |

J2 のシェル pin5/6 は GND です。

### PC 側 USB-C

| ネット | 接続 |
| --- | --- |
| USB_PC_DP | U1 pin47 → R1 27 Ω → U7 I/O1 → J1 A6/B6 |
| USB_PC_DM | U1 pin46 → R2 27 Ω → U7 I/O2 → J1 A7/B7 |
| CC1_PC | J1 A5 → R5 5.1 kΩ → GND |
| CC2_PC | J1 B5 → R6 5.1 kΩ → GND |

J1 のシールドは GND です。

### iPad 側 USB-C

| ネット | 接続 |
| --- | --- |
| USB_MIDI_DP | U3 pin6 → R17 22 Ω → U8 I/O1 → J3 A6/B6 |
| USB_MIDI_DM | U3 pin7 → R18 22 Ω → U8 I/O2 → J3 A7/B7 |
| CC1_IPAD | J3 A5 → R7 5.1 kΩ → GND |
| CC2_IPAD | J3 B5 → R8 5.1 kΩ → GND |

R17/R18 は CH345T 側の 22 Ω です。USB-A 側の R3/R4 と合わせて 22 Ω は 4 本になります。J3 のシールドは GND です。

### CH345T

| ピン | 接続 |
| --- | --- |
| 1 RST | R16 100 kΩ → +5V、TP11 |
| 3 MOUT | U1 pin7（GP5、UART1 RX） |
| 4 MIN | U1 pin6（GP4、UART1 TX） |
| 5 V3 | C19 100 nF → GND |
| 6 UD+ | R17 22 Ω → U8 → J3 D+ |
| 7 UD- | R18 22 Ω → U8 → J3 D- |
| 8, 17 GND | GND |
| 9 XI | Y2、C22 22 pF → GND |
| 10 XO | Y2、C23 22 pF → GND |
| 19 VCC | +5V、C20 100 nF、C21 10 uF |
| 2, 11-16, 18, 20 | NC |

### RP2040 と QSPI

| RP2040 | U2 W25Q128 | 備考 |
| --- | --- | --- |
| pin51 QSPI_SD3 | pin7 IO3/HOLD | |
| pin52 QSPI_SCLK | pin6 CLK | |
| pin53 QSPI_SD0 | pin5 DI/IO0 | |
| pin54 QSPI_SD2 | pin3 WP/IO2 | |
| pin55 QSPI_SD1 | pin2 DO/IO1 | |
| pin56 QSPI_SS | pin1 CS | R12 10 kΩ → +3V3、TP7 は 1 kΩ 経由で GND |

U2 pin8 は +3V3、C16 100 nF。pin4 は GND。

### 水晶と LED

| ネット | 接続 |
| --- | --- |
| XIN | U1 pin20、Y1、C17 15 pF → GND |
| XOUT | U1 pin21 → R14 1 kΩ → Y1、C18 15 pF → GND |
| STATUS_LED | U1 pin37（GP25）→ R13 1 kΩ → LED1 → GND |

### スイッチ

| Ref | 接続 |
| --- | --- |
| SW1 | pin2 → GP28、pin3 → GND、pin1 → NC |
| SW2 | pin2 → GP29、pin3 → GND、pin1 → NC |
| SW3 | pin2 → GP27、pin3 → GND、pin1 → NC（サステイン） |
| SW4 | pin2 → TPS_EN、pin3 → +3V3、pin1 → NC |
| SW6 | pin1/2 → GND、pin3/4 → GP14 |
