#include <stdio.h>

#include "reset_button.h"
#include "debounced_switch.h"
#include "midi_uart.h"
#include "config.h"

// ===========================================================================
//  MIDI リセットボタン入力 (ハード依存層)。
//  既定配線: GP14 ↔ GND のタクトスイッチ (内部プルアップ、アクティブ LOW)。
//  押下で全 16 チャンネルへ CC123 / CC121 を送る。CH345T の RST は叩かない。
// ===========================================================================

#if MIDI_RESET_BUTTON_ENABLE

#define MIDI_CHANNEL_COUNT 16u
#define MIDI_CC_ALL_NOTES_OFF 123u
#define MIDI_CC_RESET_ALL_CONTROLLERS 121u

static debounced_switch_t s_sw;

void reset_button_init(void) {
    debounced_switch_init(&s_sw, MIDI_RESET_BUTTON_PIN,
                          (bool)MIDI_RESET_BUTTON_ACTIVE_LEVEL,
                          (uint32_t)MIDI_RESET_BUTTON_DEBOUNCE_MS);
}

void reset_button_poll(void) {
    if (debounced_switch_poll(&s_sw) != DEBOUNCED_SWITCH_ENTER) {
        return;
    }
    for (unsigned ch = 0; ch < MIDI_CHANNEL_COUNT; ch++) {
        midi_uart_send_cc((uint8_t)ch, MIDI_CC_ALL_NOTES_OFF, 0u);
        midi_uart_send_cc((uint8_t)ch, MIDI_CC_RESET_ALL_CONTROLLERS, 0u);
    }
    printf("[reset] CC123/CC121 on %u channels\r\n", (unsigned)MIDI_CHANNEL_COUNT);
}

#else

void reset_button_init(void) {}
void reset_button_poll(void) {}

#endif
