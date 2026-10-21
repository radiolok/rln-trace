/*
 * usbstream: the CH569 streams self-test blocks (stream.h) over EP2 IN without
 * an FPGA; sw/usbstream checks them on the PC. The stream itself lives in
 * ep2_stream.c, driven by the USB interrupts.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "app_usb.h"

int main(void)
{
	app_init("rln-trace usbstream");
	for(;;)
		app_status_poll();
}
