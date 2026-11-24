#ifndef BOARD_PINS_H
#define BOARD_PINS_H

// RP2040 MIDI bridge (design study, revision A)
//
// The pin names are kept independent of the board so that config.h can use
// them directly.  RP2040 QSPI uses pins 51-56, not GPIO0-5, so GP0/1 remain
// available for the debug UART.

#define PIN_USB_HOST_DP 12
#define PIN_USB_HOST_DM 13

#define MIDI_UART_INDEX 1
#define MIDI_UART_TX_PIN 4
#define MIDI_UART_RX_PIN 5

#define MUTE_SWITCH_PIN 28
#define LYRE_SWITCH_PIN 29
#define SUSTAIN_SWITCH_PIN 27
#define MIDI_RESET_BUTTON_PIN 14

#define STATUS_LED_PIN 25

#define DEBUG_UART_TX_PIN 0
#define DEBUG_UART_RX_PIN 1

#define BOARD_TUH_RHPORT 1
#define BOARD_TUD_RHPORT 0

#define MIDI_RESET_DEBOUNCE_MS 20
#define SUSTAIN_DEBOUNCE_MS 20

#endif // BOARD_PINS_H
