/*
 * HSPI -> USB bridge, see bridge.c.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#ifndef BRIDGE_H
#define BRIDGE_H

#include <stdint.h>

#ifndef BRIDGE_BUFS
#define BRIDGE_BUFS 16          /* 4096-byte blocks in RAMX */
#endif
#ifndef BRIDGE_HSPI_WIDTH
#define BRIDGE_HSPI_WIDTH 8     /* 8 on the bench (Tang Nano 20K), 16 on probe B */
#endif
#ifndef BRIDGE_HSPI_RX_FALLING
#define BRIDGE_HSPI_RX_FALLING 0 /* sample HD on the falling edge of HRCLK */
#endif

#if BRIDGE_HSPI_WIDTH == 8
#define BRIDGE_HSPI_MODE RB_HSPI_DAT8_MOD
#elif BRIDGE_HSPI_WIDTH == 16
#define BRIDGE_HSPI_MODE RB_HSPI_DAT16_MOD
#elif BRIDGE_HSPI_WIDTH == 32
#define BRIDGE_HSPI_MODE RB_HSPI_DAT32_MOD
#else
#error BRIDGE_HSPI_WIDTH must be 8, 16 or 32
#endif

enum bridge_source { SRC_HSPI, SRC_INTERNAL };

struct bridge_stats {
	uint32_t hspi_packets;
	uint32_t hspi_crc_err;
	uint32_t hspi_num_mis;
	uint32_t hspi_fifo_ov;
	uint32_t dropped;       /* good packets lost for want of a free block */
	uint32_t usb_blocks;
	uint32_t last_usdf;
};

extern struct bridge_stats bridge_stats;

void bridge_init(void);
void bridge_set_source(enum bridge_source s);
enum bridge_source bridge_source(void);
void bridge_poll(void);       /* main loop: the internal source */
unsigned bridge_pool_free(void);
unsigned bridge_queued(void);

#endif /* BRIDGE_H */
