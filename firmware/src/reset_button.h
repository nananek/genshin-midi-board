#ifndef RESET_BUTTON_H
#define RESET_BUTTON_H

// MIDI リセットボタン (SW5, GP14) 入力 (ハード依存層)。
// デバウンス本体は debounced_switch を共有する。
// core0 のメインループからのみ呼ぶこと。

void reset_button_init(void);

// 各メインループイテレーションで呼ぶ。押下の確定エッジで
// CC123 (All Notes Off) と CC121 (Reset All Controllers) を
// 全 16 チャンネルへ CH345 経由で送る。
void reset_button_poll(void);

#endif // RESET_BUTTON_H
