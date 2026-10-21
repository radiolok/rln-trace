/********************************** (C) COPYRIGHT *******************************
* File Name          : app_usb.c
* Description        : USB start-up for the rln-trace CH569 firmware
* Copyright (c) 2022 Benjamin VERNOUX
* SPDX-License-Identifier: Apache-2.0
*
* rln-trace: the start-up sequence of hydrausb3_fw 88879fa HydraUSB3_USB/User/Main.c,
*            with the board layer (board.h) and a non-blocking status LED.
*******************************************************************************/
#include "CH56x_common.h"
#include "CH56x_debug_log.h"

#include "CH56x_usb30_devbulk.h"
#include "CH56x_usb20_devbulk.h"
#include "CH56x_usb30_devbulk_LIB.h"
#include "CH56x_usb_devbulk_desc_cmd.h"

#include "hydrausb3_usb_devbulk_vid_pid.h"

#include "app_usb.h"
#include "board.h"

debug_log_buf_t log_buf;

/* FLASH_ROMA Read Unique ID (8bytes/64bits) */
#define FLASH_ROMA_UID_ADDR (0x77fe4)
static usb_descriptor_serial_number_t unique_id;

static usb_descriptor_usb_vid_pid_t vid_pid = {
	.vid = USB_VID,
	.pid = USB_PID
};

uint32_t app_ms(void)
{
	return (uint32_t)(bsp_get_tick() / bsp_get_nbtick_1ms());
}

void app_init(const char *name)
{
	board_init();
	bsp_init(APP_FREQ_SYS);
	log_init(&log_buf);

	log_printf("%s on %s, CPU %d MHz\n", name, board_name, (int)(APP_FREQ_SYS / 1000000));
	memset(&unique_id, 0, 8);
	FLASH_ROMA_READ(FLASH_ROMA_UID_ADDR, (uint32_t *)&unique_id, 8);

	// USB2 & USB3 are managed in LINK_IRQHandler()/TMR0_IRQHandler()/USBHS_IRQHandler()/USBSS_IRQHandler()
	R32_USB_CONTROL = 0;
	PFIC_EnableIRQ(USBSS_IRQn);
	PFIC_EnableIRQ(LINK_IRQn);

	PFIC_EnableIRQ(TMR0_IRQn);
	R8_TMR0_INTER_EN = RB_TMR_IE_CYC_END;
	TMR0_TimerInit(67000000); // USB3.0 connection failure timeout about 0.56 seconds

	usb_descriptor_set_string_serial_number(&unique_id);
	usb_descriptor_set_usb_vid_pid(&vid_pid);

	/* USB3.0 initialization, make sure that the two USB3.0 interrupts are enabled before initialization */
	USB30D_init(ENABLE);
}

void app_status_poll(void)
{
	static int last_type = -1;
	uint32_t period = 0;

	if(g_DeviceConnectstatus == USB_INT_CONNECT_ENUM) {
		if(g_DeviceUsbType == USB_U30_SPEED)
			period = 500;
		else if(g_DeviceUsbType == USB_U20_SPEED)
			period = 1000;
		if(g_DeviceUsbType != last_type) {
			last_type = g_DeviceUsbType;
			log_printf(g_DeviceUsbType == USB_U30_SPEED ? "USB3\n" : "USB2\n");
		}
	}
	board_led(BOARD_LED_STATUS, period ? (app_ms() % period) < period / 2 : 1);
}

__attribute__((interrupt("WCH-Interrupt-fast"))) void HardFault_Handler(void)
{
	board_led(BOARD_LED_ERROR, 1);
	while(1)
		;
}
