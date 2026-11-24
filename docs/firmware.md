# ファームウェア実装メモ

## 1. 方針

ファームウェアは RP2040 向けに pico-sdk で実装します。USB ホスト（PIO-USB）、native USB デバイス（HID）、UART1（CH345T）の構成です。ピンは GP4/5、GP12/13、GP27/28/29 を使います。

## 2. ボード定義

`firmware/include/board_pins.h` にピンをまとめています。

| 機能 | GPIO | 備考 |
| --- | --- | --- |
| PIO-USB D+ | 12 | D- は 13 |
| CH345T TX | 4 | UART1 TX |
| CH345T RX | 5 | UART1 RX |
| 原神モード SW1 | 28 | アクティブ LOW |
| 楽器モード SW2 | 29 | アクティブ LOW |
| サステイン SW3 | 27 | アクティブ LOW |
| MIDI リセット SW5 | 14 | アクティブ LOW |
| ステータス LED | 25 | アクティブ HIGH |
| デバッグ UART TX | 0 | UART0 |
| デバッグ UART RX | 1 | UART0 |

## 3. ビルド

pico-sdk 2.x を使います。

```sh
export PICO_SDK_PATH=/path/to/pico-sdk
cmake -B build -DPICO_BOARD=pico
cmake --build build -j
```

`PICO_BOARD=pico` は RP2040 の 2 MB flash、GP25 LED、UART0 GP0/1 を前提にします。今回の flash は W25Q128（16 MB）ですが、ファームウェアは 2 MB に収まるため、`pico` の設定で問題ありません。flash 容量を正しく認識させたい場合は、カスタムボード定義で `PICO_FLASH_SIZE_BYTES` を 16 MB にします。

## 4. PIO-USB

Pico-PIO-USB は RP2040 に対応しています。D+ を GP12、D- を GP13 に設定します。

```c
pio_usb_configuration_t pio_cfg = PIO_USB_DEFAULT_CONFIG;
pio_cfg.pin_dp = 12;
tuh_configure(1, TUH_CFGID_RPI_PIO_USB_CONFIGURATION, &pio_cfg);
tuh_init(1);
```

RP2040 では PIO-USB ホストを rhport 1、native USB デバイスを rhport 0 にします。`config.h` の `BOARD_TUH_RHPORT` / `BOARD_TUD_RHPORT` は次のようにします。

```c
#define BOARD_TUH_RHPORT 1
#define BOARD_TUD_RHPORT 0
```

PIO-USB は 120 MHz を要求します。12 MHz 水晶から `set_sys_clock_khz(120000, true)` で生成します。

## 5. スイッチ

`debounced_switch` を使います。

- SW1: `MUTE_SWITCH_PIN 28`
- SW2: `LYRE_SWITCH_PIN 29`
- SW3: `SUSTAIN_SWITCH_PIN 27`
- SW5: `MIDI_RESET_BUTTON_PIN 14`

SW3 は押下で CC64=127、離すと CC64=0 を CH345T へ送ります。SW5 は押下で CC123（All Notes Off）と CC121（Reset All Controllers）を全 16 チャンネルへ送ります。どちらも 20 ms デバウンスです。

SW4 は GPIO ではなく、TPS2553 の EN を制御する電源スイッチです。ファームウェアからは触りません。

## 6. MIDI リセット

SW5 の処理は、CH345T の RST を叩くのではなく、MIDI メッセージで行います。

```c
for (uint8_t ch = 0; ch < 16; ch++) {
    midi_uart_send_cc(ch, 123, 0); // All Notes Off
    midi_uart_send_cc(ch, 121, 0); // Reset All Controllers
}
```

CH345T の RST をハードウェアでリセットしたい場合は、GPIO からトランジスタ経由で RST を引く追加回路が必要です。今回は不要とします。

## 7. ステータス LED

GP25 をアクティブ HIGH で点灯させます。状態の例:

- 起動中: ゆっくり点滅
- native USB が設定済み: 点灯
- MIDI キーボードが未接続: 短い点滅
- エラー: 速い点滅

## 8. デバッグ UART

UART0 を GP0（TX）/ GP1（RX）、115200 8N1 で使います。`stdio_init_all()` の既定は RP2040 の UART0 です。CH345T は UART1 なので衝突しません。

## 9. 実装上の注意

- `PICO_BOARD` は `pico` またはカスタム RP2040 ボードにする
- `set_sys_clock_khz(120000, true)` を設定する
- PIO-USB の rhport を 1、native USB を 0 にする
- `config.h` に `SUSTAIN_SWITCH_PIN 27`、`MIDI_RESET_BUTTON_PIN 14`、`STATUS_LED_PIN 25` を定義する
- `main.c` にサステインと MIDI リセットのポーリングを追加する
- `usb_descriptors.c` と `nkro_report.c` はボード非依存を保つ
- `midi_uart.c` は UART1 GP4/5、31250 を使う

## 10. 確認事項

- RP2040 で PIO-USB ホストと native USB デバイスを同時に動かす
- PIO-USB と UART1 の割り込みが衝突しない
- CH345T の UART 31250 で取りこぼしがない
- NKRO の 21 同時押しが PC で認識される
- iPad が CH345T を USB-MIDI として認識する
- SW3 の CC64 と SW5 の CC123/CC121 が DAW で見える
