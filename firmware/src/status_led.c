#include "status_led.h"
#include "pico/stdlib.h"
#include "hardware/gpio.h"
#include "config.h"

// ===========================================================================
//  ステータス LED 出力 (ハード依存層)。
//  既定配線: GP25 → 1 kΩ → LED → GND (アクティブ HIGH)。
//  absolute_time による経過時間で点滅させるため、メインループを止めない。
// ===========================================================================

#if STATUS_LED_ENABLE

typedef struct {
    uint32_t on_ms;
    uint32_t off_ms;
} led_pattern_t;

static status_led_state_t s_state = STATUS_LED_OFF;
static bool s_level; // 論理点灯状態 (アクティブレベル適用前)
static absolute_time_t s_phase_since;

static void write_level(bool on) {
    gpio_put(STATUS_LED_PIN,
             STATUS_LED_ACTIVE_LEVEL ? on : !on);
    s_level = on;
}

static led_pattern_t pattern_of(status_led_state_t state) {
    switch (state) {
    case STATUS_LED_BOOT:    return (led_pattern_t){ .on_ms = 500, .off_ms = 500 };
    case STATUS_LED_NO_MIDI: return (led_pattern_t){ .on_ms = 100, .off_ms = 1900 };
    case STATUS_LED_ERROR:   return (led_pattern_t){ .on_ms = 100, .off_ms = 100 };
    default:                 return (led_pattern_t){ .on_ms = 0, .off_ms = 0 };
    }
}

void status_led_init(void) {
    gpio_init(STATUS_LED_PIN);
    gpio_set_dir(STATUS_LED_PIN, GPIO_OUT);
    s_level = false;
    write_level(false);
    s_state = STATUS_LED_OFF;
    status_led_set_state(STATUS_LED_BOOT);
}

void status_led_set_state(status_led_state_t state) {
    if (state == s_state) {
        return;
    }
    s_state = state;
    s_phase_since = get_absolute_time();

    switch (state) {
    case STATUS_LED_OFF:
        write_level(false);
        break;
    case STATUS_LED_READY:
        write_level(true);
        break;
    default:
        write_level(true); // 点滅は点灯から始める
        break;
    }
}

void status_led_task(void) {
    // 点灯/消灯を固定した状態はここで終わり。
    if (s_state == STATUS_LED_OFF || s_state == STATUS_LED_READY) {
        return;
    }

    led_pattern_t pattern = pattern_of(s_state);
    uint32_t limit_ms = s_level ? pattern.on_ms : pattern.off_ms;
    int64_t elapsed_ms = absolute_time_diff_us(s_phase_since, get_absolute_time()) / 1000;
    if (elapsed_ms >= (int64_t)limit_ms) {
        write_level(!s_level);
        s_phase_since = get_absolute_time();
    }
}

#else

void status_led_init(void) {}
void status_led_set_state(status_led_state_t state) { (void)state; }
void status_led_task(void) {}

#endif
