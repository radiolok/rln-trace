/*
 * hspi2usb: HSPI from the FPGA -> USB3 EP2 IN (bridge.c). Step 0 of the bench:
 * gw/cores/selftest_hspi.sv in the FPGA, sw/usbstream on the PC. The SRCI
 * command switches to the internal self-test source for checking without an
 * FPGA; SRCH back to HSPI; STAT returns the counters (EP1, usb_cmd.c).
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "app_usb.h"
#include "bridge.h"

int main(void)
{
	app_init("rln-trace hspi2usb");
	bridge_init();
	for(;;) {
		bridge_poll();
		app_status_poll();
	}
}
