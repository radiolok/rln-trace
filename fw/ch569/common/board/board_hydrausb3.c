/*
 * HydraUSB3 v1: one user LED (ULED, PB22) through the BSP board file
 * (wch-ch56x-bsp/board/hydrausb3_v1.c), used as the status LED.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "CH56x_common.h"
#include "board.h"

const char board_name[] = "HydraUSB3 v1";

void board_init(void)
{
	bsp_gpio_init();
}

void board_led(int led, int on)
{
	if(led != BOARD_LED_STATUS)
		return;
	if(on)
		bsp_uled_on();
	else
		bsp_uled_off();
}
