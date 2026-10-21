/*
 * Board layer of the rln-trace CH569 firmware: safe pin state and three logical
 * LEDs. Boards with fewer LEDs ignore the missing ones.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#ifndef BOARD_H
#define BOARD_H

enum {
	BOARD_LED_STATUS = 0,   /* USB state */
	BOARD_LED_ACTIVITY = 1, /* data moving */
	BOARD_LED_ERROR = 2,    /* something was lost or broken */
};

extern const char board_name[];

void board_init(void);
void board_led(int led, int on);

#endif /* BOARD_H */
