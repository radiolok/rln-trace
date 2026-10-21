/*
 * WCH CH569W evaluation board (CH569W-R0-1V0, EVT/PUB/CH569WSCH.pdf in
 * openwch/ch569): LED0 green on PB24, LED1 blue on PB22, LED2 yellow on PB23,
 * each from VIO through 1 kOhm to the pin, lit when the pin is low. No user
 * button on a GPIO: Download is HD0/PA5 at power-on, Reset is RST#.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "CH56x_common.h"
#include "board.h"

const char board_name[] = "WCH CH569W EVT";

static const uint32_t led_pin[3] = {
	GPIO_Pin_24, /* BOARD_LED_STATUS:   LED0 green */
	GPIO_Pin_22, /* BOARD_LED_ACTIVITY: LED1 blue */
	GPIO_Pin_23, /* BOARD_LED_ERROR:    LED2 yellow */
};

void board_init(void)
{
	/* everything input floating, UART1 (PA7/PA8) left to the debug log */
	GPIOA_ModeCfg(GPIO_Pin_All & ~(GPIO_Pin_7 | GPIO_Pin_8), GPIO_ModeIN_Floating);
	GPIOB_ModeCfg(GPIO_Pin_All, GPIO_ModeIN_Floating);
	for(int i = 0; i < 3; i++) {
		GPIOB_SetBits(led_pin[i]); /* off */
		GPIOB_ModeCfg(led_pin[i], GPIO_Slowascent_PP_8mA);
	}
}

void board_led(int led, int on)
{
	if(led < 0 || led > 2)
		return;
	if(on)
		GPIOB_ResetBits(led_pin[led]);
	else
		GPIOB_SetBits(led_pin[led]);
}
