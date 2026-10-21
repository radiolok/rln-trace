/*
 * EP2 IN fed by the application (fw/ch569/common/usb, fork of the HydraUSB3 BSP).
 *
 * The USB stack calls the application:
 *   ep2_ss_ready()  USB3 endpoints configured, nothing armed on EP2 IN
 *   ep2_ss_done()   USB3: the data passed to ep2_ss_send() is gone
 *   ep2_hs_ready()  USB2 endpoints configured (after every bus reset)
 *   ep2_hs_done()   USB2: the packet passed to ep2_hs_send() is gone
 * and offers:
 *   ep2_ss_send()   arm EP2 IN with 1..4096 bytes: a burst of up to 4 packets
 *                   of 1024, the last one shorter if needed; ERDY tells the host
 *   ep2_hs_send()   arm EP2 IN with one packet of 1..512 bytes
 * Buffers must be in RAMX (DMA) and 16-byte aligned. With nothing armed the
 * host gets NRDY (USB3) or NAK (USB2) and waits.
 *
 * The callbacks run in the USB interrupt. Calling the send functions from
 * elsewhere needs the USB interrupts masked (ep2_irq_save / ep2_irq_restore).
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#ifndef EP2_H
#define EP2_H

#include <stdint.h>

void ep2_ss_ready(void);
void ep2_ss_done(void);
void ep2_hs_ready(void);
void ep2_hs_done(void);

void ep2_ss_send(const uint8_t *buf, uint32_t len);
void ep2_hs_send(const uint8_t *buf, uint32_t len);

/* Global interrupt mask around code shared with interrupt handlers */
static inline uint32_t ep2_irq_save(void)
{
	uint32_t m;
	__asm__ volatile("csrrci %0, mstatus, 8" : "=r"(m) :: "memory");
	return m;
}

static inline void ep2_irq_restore(uint32_t m)
{
	__asm__ volatile("csrs mstatus, %0" :: "r"(m & 8) : "memory");
}

#endif /* EP2_H */
