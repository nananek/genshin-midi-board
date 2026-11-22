#ifndef SUSTAIN_SWITCH_H
#define SUSTAIN_SWITCH_H

#include <stdbool.h>

// サステインスイッチ (SW3, GP27) 入力 (ハード依存層)。
// デバウンス本体は debounced_switch を共有する。
// core0 のメインループからのみ呼ぶこと。

void sustain_switch_init(void);

// 各メインループイテレーションで呼ぶ。押下/解放の確定エッジで
// CH345 (UART1 31250) へ CC64 を送る。送信は内部で完結する。
void sustain_switch_poll(void);

// 現在のデバウンス済み状態 (true = 押下中)。
bool sustain_switch_is_active(void);

#endif // SUSTAIN_SWITCH_H
