/*
 * EP2 IN of usbstream: one block buffer, its header rewritten before every send
 * (stream.h). USB3 sends 4096-byte blocks as bursts, USB2 512-byte packets.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "CH56x_common.h"
#include "ep2.h"
#include "stream.h"

#define SS_BLOCK 4096
#define HS_BLOCK 512

static __attribute__((aligned(16))) uint8_t blk[SS_BLOCK] __attribute__((section(".DMADATA")));

void ep2_ss_ready(void)
{
	stream_start(blk, SS_BLOCK);
	ep2_ss_send(blk, SS_BLOCK);
}

void ep2_ss_done(void)
{
	stream_next(blk, SS_BLOCK);
	ep2_ss_send(blk, SS_BLOCK);
}

void ep2_hs_ready(void)
{
	stream_start(blk, HS_BLOCK);
	ep2_hs_send(blk, HS_BLOCK);
}

void ep2_hs_done(void)
{
	stream_next(blk, HS_BLOCK);
	ep2_hs_send(blk, HS_BLOCK);
}
