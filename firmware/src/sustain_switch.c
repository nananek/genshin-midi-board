#include <stdio.h>

#include "sustain_switch.h"
#include "debounced_switch.h"
#include "midi_uart.h"
#include "config.h"

// ===========================================================================
//  サステインスイッチ入力 (ハード依存層)。
//  既定配線: GP26 ↔ GND のトグルスイッチ。閉じる (LOW) = アクティブ = ペダル ON。
//  押下で CC64=127、解放で CC64=0 を CH345 へ送る。
// ===========================================================================

#if SUSTAIN_SWITCH_ENABLE

static debounced_switch_t s_sw;
static bool s_active;

void sustain_switch_init(void) {
    debounced_switch_init(&s_sw, SUSTAIN_SWITCH_PIN,
                          (bool)SUSTAIN_SWITCH_ACTIVE_LEVEL,
                          (uint32_t)SUSTAIN_SWITCH_DEBOUNCE_MS);
    s_active = debounced_switch_is_active(&s_sw);
}

void sustain_switch_poll(void) {
    debounced_switch_edge_t edge = debounced_switch_poll(&s_sw);
    s_active = debounced_switch_is_active(&s_sw);
    switch (edge) {
    case DEBOUNCED_SWITCH_ENTER:
        midi_uart_send_cc((uint8_t)SUSTAIN_SWITCH_MIDI_CHANNEL,
                          (uint8_t)SUSTAIN_SWITCH_CC, 127u);
        printf("[sustain] CC%d=127\r\n", SUSTAIN_SWITCH_CC);
        break;
    case DEBOUNCED_SWITCH_EXIT:
        midi_uart_send_cc((uint8_t)SUSTAIN_SWITCH_MIDI_CHANNEL,
                          (uint8_t)SUSTAIN_SWITCH_CC, 0u);
        printf("[sustain] CC%d=0\r\n", SUSTAIN_SWITCH_CC);
        break;
    default:
        break;
    }
}

bool sustain_switch_is_active(void) {
    return s_active;
}

#else

void sustain_switch_init(void) {}
void sustain_switch_poll(void) {}
bool sustain_switch_is_active(void) { return false; }

#endif
