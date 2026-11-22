#ifndef STATUS_LED_H
#define STATUS_LED_H

// ステータス LED (LED1, GP25) の非ブロッキング点滅 (ハード依存層)。
// core0 のメインループからのみ呼ぶこと。

typedef enum {
    STATUS_LED_OFF = 0, // 消灯
    STATUS_LED_BOOT,    // 起動中: ゆっくり点滅 (500 ms 周期)
    STATUS_LED_READY,   // native USB 設定済み + MIDI キーボード接続: 点灯
    STATUS_LED_NO_MIDI, // native USB 設定済み + MIDI 未接続: 短い点滅 (100 ms / 2 s)
    STATUS_LED_ERROR,   // エラー: 速い点滅 (100 ms 周期、現状は遷移元の予備)
} status_led_state_t;

void status_led_init(void);

// 状態を切り替える。同じ状態のときは何もしない。
// 点滅の位相は切り替え時点からやり直す。
void status_led_set_state(status_led_state_t state);

// 各メインループイテレーションで呼ぶ。待ち合わせをしない (sleep 禁止)。
void status_led_task(void);

#endif // STATUS_LED_H
