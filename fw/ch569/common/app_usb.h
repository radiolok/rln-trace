/*
 * USB start-up and the status LED shared by the rln-trace CH569 firmware.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#ifndef APP_USB_H
#define APP_USB_H

#include <stdint.h>

#define APP_FREQ_SYS 120000000u

/* Clocks, board, log, USB3 with USB2 fall-back; USB runs from interrupts */
void app_init(const char *name);
/* Status LED without blocking: steady until enumerated, then blinks every
 * 500 ms on USB3, 1 s on USB2. Call often from the main loop. */
void app_status_poll(void);
/* Milliseconds since start */
uint32_t app_ms(void);

#endif /* APP_USB_H */
