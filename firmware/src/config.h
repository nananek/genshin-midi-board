#ifndef CONFIG_H
#define CONFIG_H

// ===========================================================================
//  原神 MIDI → NKRO HID + CH345 USB-MIDI 設定 (RP2040)
//
//  構成:
//    [MIDI キーボード] --USB--> PIO-USB host (RP2040)
//    RP2040 native USB = NKRO HID キーボード (操作対象 PC へ)
//    RP2040 UART1       = CH345 (31250 8N1) へ生 MIDI を送信
//    CH345 USB          = 制御 PC/DAW へ USB-MIDI として見える
//
//  ピンの正本は include/board_pins.h。ここの既定値は board_pins.h を
//  使わないホスト単体テスト向けのフォールバックで、同じ名前なら
//  board_pins.h の値が優先される。
//
//  すべて #ifndef ガード付きなので、CMake / コンパイル時 -D で上書きできる。
// ===========================================================================

#include "board_pins.h"

// ---------------------------------------------------------------------------
//  移調 (キャリブレーション用)
//  入力 MIDI ノート番号に「加算する半音数」。12 = 1 オクターブ上。
//  実機で MIDI キーボードと原神の発音を鳴らし比べてズレていたら調整する。
// ---------------------------------------------------------------------------
#ifndef OCTAVE_OFFSET
#define OCTAVE_OFFSET 0
#endif

// ---------------------------------------------------------------------------
//  定義済みノート範囲 (固定)
//  低音域ド=48 … 高音域シ=83 の 3 オクターブ。 C4=MIDI60 基準。
// ---------------------------------------------------------------------------
#define NOTE_RANGE_LOW  48
#define NOTE_RANGE_HIGH 83

// ---------------------------------------------------------------------------
//  範囲外ノートのポリシー
//    IGNORE : MIDI 47 以下 / 84 以上は無視する (デフォルト)
//    WRAP   : 最寄りの定義済みオクターブへ ±12 ずつ折り返して丸め込む
// ---------------------------------------------------------------------------
#define OUT_OF_RANGE_IGNORE 0
#define OUT_OF_RANGE_WRAP   1
#ifndef OUT_OF_RANGE_POLICY
#define OUT_OF_RANGE_POLICY OUT_OF_RANGE_IGNORE
#endif

// ---------------------------------------------------------------------------
//  PIO-USB ホスト (MIDI 入力側) の GPIO
//  D+ を PIN_USB_HOST_DP、D- は必ずその隣 (DP+1) を使うこと。
//  基板では D+ = GP12 / D- = GP13。
// ---------------------------------------------------------------------------
#ifndef PIN_USB_HOST_DP
#define PIN_USB_HOST_DP 12
#endif

// ---------------------------------------------------------------------------
//  MIDI 受信チャンネルのフィルタ
//  0 = 全チャンネル受け付け。 1..16 = そのチャンネルのみ。
// ---------------------------------------------------------------------------
#ifndef MIDI_CHANNEL_FILTER
#define MIDI_CHANNEL_FILTER 0
#endif

// ---------------------------------------------------------------------------
//  CH345 (UART ↔ USB-MIDI) 接続
//  RP2040 の UART1 を CH345 の MIN/MOUT にクロス接続する。
//  TX=GP4, RX=GP5, 31250 bps 8N1。デバッグログは UART0 (GP0/GP1)。
//  MIDI バイト列は CH345 へそのまま流す (USB-MIDI クラス)。
// ---------------------------------------------------------------------------
#ifndef MIDI_UART_INDEX
#define MIDI_UART_INDEX 1
#endif
#ifndef MIDI_UART_TX_PIN
#define MIDI_UART_TX_PIN 4
#endif
#ifndef MIDI_UART_RX_PIN
#define MIDI_UART_RX_PIN 5
#endif
#ifndef MIDI_UART_BAUD
#define MIDI_UART_BAUD 31250
#endif
// tuh_midi_stream_read を 1 回に読み出す最大バイト数。
#ifndef MIDI_STREAM_CHUNK_MAX
#define MIDI_STREAM_CHUNK_MAX 64
#endif

// ---------------------------------------------------------------------------
//  原神モードスイッチ (任意)
//  ON (LOW) で NKRO HID のキーボード出力を停止する。UART の MIDI 出力は
//  継続する。ミュート突入時は全キー解放レポートを HID へ送る。
//  既定配線: GP28 ↔ GND をトグルスイッチで開閉 (内部プルアップ)。
// ---------------------------------------------------------------------------
#ifndef MUTE_SWITCH_ENABLE
#define MUTE_SWITCH_ENABLE 1
#endif
#ifndef MUTE_SWITCH_PIN
#define MUTE_SWITCH_PIN 28
#endif
// 0 = LOW でミュート (内部プルアップ + スイッチを GND へ閉じる配線が既定)
#ifndef MUTE_SWITCH_ACTIVE_LEVEL
#define MUTE_SWITCH_ACTIVE_LEVEL 0
#endif
#ifndef MUTE_SWITCH_DEBOUNCE_MS
#define MUTE_SWITCH_DEBOUNCE_MS 20
#endif

// ---------------------------------------------------------------------------
//  予備スイッチ (任意)
//  旧ボード2のサステインスイッチを、PIO-USB MIDI-HID ガジェット側の
//  予備入力へ移したもの。既定では状態を読むだけで MIDI へは送らない。
//  SPARE_SWITCH_CC を 0..127 にすると、エッジでその CC を CH345 へ送る
//  (例: 64 にすると従来のサステインと同じ動作)。
//  既定配線: GP27 ↔ GND (内部プルアップ、アクティブ LOW)。
// ---------------------------------------------------------------------------
#ifndef SPARE_SWITCH_ENABLE
#define SPARE_SWITCH_ENABLE 1
#endif
#ifndef SPARE_SWITCH_PIN
#define SPARE_SWITCH_PIN 27
#endif
#ifndef SPARE_SWITCH_ACTIVE_LEVEL
#define SPARE_SWITCH_ACTIVE_LEVEL 0
#endif
#ifndef SPARE_SWITCH_DEBOUNCE_MS
#define SPARE_SWITCH_DEBOUNCE_MS 20
#endif
// -1 = MIDI へ送らない (純粋な予備入力)。0..127 = その CC を送る。
#ifndef SPARE_SWITCH_CC
#define SPARE_SWITCH_CC (-1)
#endif
// SPARE_SWITCH_CC を送るときの MIDI チャンネル (0-indexed、既定 0 = ch1)。
#ifndef SPARE_SWITCH_MIDI_CHANNEL
#define SPARE_SWITCH_MIDI_CHANNEL 0
#endif

// ---------------------------------------------------------------------------
//  サステインスイッチ (SW5)
//  GP26 ↔ GND のトグルスイッチ (内部プルアップ、アクティブ LOW)。
//  押下で CC64=127、離すと CC64=0 を CH345 へ送る (20 ms デバウンス)。
//  ピンとデバウンス時間の正本は board_pins.h。
// ---------------------------------------------------------------------------
#ifndef SUSTAIN_SWITCH_ENABLE
#define SUSTAIN_SWITCH_ENABLE 1
#endif
#ifndef SUSTAIN_SWITCH_PIN
#define SUSTAIN_SWITCH_PIN 26
#endif
#ifndef SUSTAIN_SWITCH_ACTIVE_LEVEL
#define SUSTAIN_SWITCH_ACTIVE_LEVEL 0
#endif
#ifndef SUSTAIN_SWITCH_DEBOUNCE_MS
#define SUSTAIN_SWITCH_DEBOUNCE_MS SUSTAIN_DEBOUNCE_MS
#endif
#ifndef SUSTAIN_SWITCH_CC
#define SUSTAIN_SWITCH_CC 64
#endif
// 0-indexed (既定 0 = ch1)。MIDI キーボードの送信チャンネルに合わせる。
#ifndef SUSTAIN_SWITCH_MIDI_CHANNEL
#define SUSTAIN_SWITCH_MIDI_CHANNEL 0
#endif

// ---------------------------------------------------------------------------
//  MIDI リセットボタン (SW6)
//  GP14 ↔ GND のタクトスイッチ (内部プルアップ、アクティブ LOW)。
//  押下で CC123 (All Notes Off) と CC121 (Reset All Controllers) を
//  全 16 チャンネルへ送る。CH345T の RST は叩かない。
// ---------------------------------------------------------------------------
#ifndef MIDI_RESET_BUTTON_ENABLE
#define MIDI_RESET_BUTTON_ENABLE 1
#endif
#ifndef MIDI_RESET_BUTTON_PIN
#define MIDI_RESET_BUTTON_PIN 14
#endif
#ifndef MIDI_RESET_BUTTON_ACTIVE_LEVEL
#define MIDI_RESET_BUTTON_ACTIVE_LEVEL 0
#endif
#ifndef MIDI_RESET_BUTTON_DEBOUNCE_MS
#define MIDI_RESET_BUTTON_DEBOUNCE_MS MIDI_RESET_DEBOUNCE_MS
#endif

// ---------------------------------------------------------------------------
//  ステータス LED (LED1)
//  GP25 → 1 kΩ → LED → GND (アクティブ HIGH)。
//  status_led_task() が時間ベースで点滅させるのでメインループを止めない。
// ---------------------------------------------------------------------------
#ifndef STATUS_LED_ENABLE
#define STATUS_LED_ENABLE 1
#endif
#ifndef STATUS_LED_PIN
#define STATUS_LED_PIN 25
#endif
#ifndef STATUS_LED_ACTIVE_LEVEL
#define STATUS_LED_ACTIVE_LEVEL 1
#endif

// ---------------------------------------------------------------------------
//  デバッグ UART (UART0 GP0/GP1)
//  CH345 は UART1 なので衝突しない。
// ---------------------------------------------------------------------------
#ifndef DEBUG_UART_BAUD
#define DEBUG_UART_BAUD 115200
#endif

// ---------------------------------------------------------------------------
//  楽器モードスイッチ (任意)
//  ON にすると古びたライアー (スメール音階) 用のマッピングを使う。
//  既定配線: GP29 ↔ GND をトグルスイッチで開閉 (内部プルアップ)。
// ---------------------------------------------------------------------------
#ifndef LYRE_SWITCH_ENABLE
#define LYRE_SWITCH_ENABLE 1
#endif
#ifndef LYRE_SWITCH_PIN
#define LYRE_SWITCH_PIN 29
#endif
#ifndef LYRE_SWITCH_ACTIVE_LEVEL
#define LYRE_SWITCH_ACTIVE_LEVEL 0
#endif
#ifndef LYRE_SWITCH_DEBOUNCE_MS
#define LYRE_SWITCH_DEBOUNCE_MS MUTE_SWITCH_DEBOUNCE_MS
#endif

#endif // CONFIG_H
