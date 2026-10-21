/*
 * HSPI -> USB bridge: the FPGA sends packets over HSPI (gw/cores/hspi_tx.sv),
 * the CH569 queues them and sends them to EP2 IN.
 *
 * Buffers: a pool of BRIDGE_BUFS blocks of 4096 bytes in RAMX. HSPI receives
 * into two DMA slots (RX_TOG_EN); after each good packet the filled block goes
 * to the queue and the slot gets a fresh block from the pool. EP2 IN sends the
 * queue head: on USB3 one burst per block, on USB2 512 bytes at a time. With
 * the pool empty a packet lands in a scratch block and is counted as dropped.
 *
 * Internal source (bridge_set_source(SRC_INTERNAL)): HSPI is off and the main
 * loop fills blocks in the stream.h format itself, through the same queue and
 * USB path, so the bridge can be checked with sw/usbstream without an FPGA.
 *
 * The pool and the queue are shared by the HSPI and USB interrupts and the main
 * loop: every access runs with interrupts masked.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "CH56x_common.h"
#include "CH56x_debug_log.h"

#include "board.h"
#include "bridge.h"
#include "ep2.h"
#include "stream.h"

#define BLOCK 4096u

static __attribute__((aligned(16))) uint8_t pool[BRIDGE_BUFS][BLOCK] __attribute__((section(".DMADATA")));
static __attribute__((aligned(16))) uint8_t scratch[BLOCK] __attribute__((section(".DMADATA")));

struct bridge_stats bridge_stats;

static uint8_t *free_list[BRIDGE_BUFS];
static unsigned free_n;

static struct {
	uint8_t *buf;
	uint16_t len;
} queue[BRIDGE_BUFS];
static unsigned q_head, q_n;

static uint8_t *slot_buf[2];        /* HSPI DMA slots */
static enum bridge_source source;

/* USB side */
static enum { USB_NONE, USB_SS, USB_HS } usb_speed;
static uint8_t *usb_cur;            /* block being sent */
static uint16_t usb_len, usb_off;
static uint32_t internal_seq;

static uint8_t *pool_get(void)
{
	return free_n ? free_list[--free_n] : 0;
}

static void pool_put(uint8_t *b)
{
	if(b && b != scratch)
		free_list[free_n++] = b;
}

/* Start the next block on EP2 IN if the endpoint is idle; interrupts masked */
static void usb_kick(void)
{
	if(usb_cur || !q_n || usb_speed == USB_NONE)
		return;
	usb_cur = queue[q_head].buf;
	usb_len = queue[q_head].len;
	usb_off = 0;
	q_head = (q_head + 1) % BRIDGE_BUFS;
	q_n--;
	if(usb_speed == USB_SS) {
		ep2_ss_send(usb_cur, usb_len);
	} else {
		usb_off = usb_len < 512 ? usb_len : 512;
		ep2_hs_send(usb_cur, usb_off);
	}
}

static void queue_push(uint8_t *b, uint16_t len)
{
	unsigned tail = (q_head + q_n) % BRIDGE_BUFS;
	queue[tail].buf = b;
	queue[tail].len = len;
	q_n++;
	usb_kick();
}

static void block_done(void)
{
	pool_put(usb_cur);
	usb_cur = 0;
	bridge_stats.usb_blocks++;
	if((bridge_stats.usb_blocks & 63) == 0)
		board_led(BOARD_LED_ACTIVITY, (bridge_stats.usb_blocks >> 6) & 1);
	usb_kick();
}

/* A bus reset drops the block in flight */
static void usb_restart(int speed)
{
	pool_put(usb_cur);
	usb_cur = 0;
	usb_speed = speed;
	usb_kick();
}

void ep2_ss_ready(void) { usb_restart(USB_SS); }
void ep2_hs_ready(void) { usb_restart(USB_HS); }
void ep2_ss_done(void) { block_done(); }

void ep2_hs_done(void)
{
	if(usb_off < usb_len) {
		uint16_t n = usb_len - usb_off < 512 ? usb_len - usb_off : 512;
		ep2_hs_send(usb_cur + usb_off, n);
		usb_off += n;
		return;
	}
	block_done();
}

/* ------------------------------------------------------------------ HSPI */

static void hspi_start(void)
{
	for(int i = 0; i < 2; i++) {
		slot_buf[i] = pool_get();
		if(!slot_buf[i])
			slot_buf[i] = scratch;
	}
	HSPI_DoubleDMA_Init(HSPI_DEVICE, BRIDGE_HSPI_MODE,
	                    (uint32_t)slot_buf[0], (uint32_t)slot_buf[1], 0);
#if BRIDGE_HSPI_RX_FALLING
	R8_HSPI_AUX |= RB_HSPI_RCK_MOD;
#else
	R8_HSPI_AUX &= ~RB_HSPI_RCK_MOD;
#endif
}

static void hspi_stop(void)
{
	PFIC_DisableIRQ(HSPI_IRQn);
	R8_HSPI_CTRL &= ~(RB_HSPI_ENABLE | RB_HSPI_DMA_EN);
	R8_HSPI_CTRL |= RB_HSPI_ALL_CLR | RB_HSPI_TRX_RST;
	pool_put(slot_buf[0]);
	pool_put(slot_buf[1]);
	slot_buf[0] = slot_buf[1] = 0;
}

__attribute__((interrupt("WCH-Interrupt-fast"))) void HSPI_IRQHandler(void)
{
	uint8_t flags = R8_HSPI_INT_FLAG;

	if(flags & RB_HSPI_IF_R_DONE) {
		uint8_t st = R8_HSPI_RTX_STATUS;
		/* RX_TOG names the slot in use now: the packet went to the other one */
		int slot = (R8_HSPI_RX_SC & RB_HSPI_RX_TOG) ? 0 : 1;
		uint16_t len = slot ? R16_HSPI_RX_LEN1 : R16_HSPI_RX_LEN0;

		R8_HSPI_INT_FLAG = RB_HSPI_IF_R_DONE;
		if(len == 0)
			len = BLOCK;
		bridge_stats.hspi_packets++;
		bridge_stats.last_usdf = slot ? R32_HSPI_UDF1 : R32_HSPI_UDF0;
		if(st & RB_HSPI_CRC_ERR)
			bridge_stats.hspi_crc_err++;
		if(st & RB_HSPI_NUM_MIS)
			bridge_stats.hspi_num_mis++;
		if(st & (RB_HSPI_CRC_ERR | RB_HSPI_NUM_MIS)) {
			board_led(BOARD_LED_ERROR, 1);
		} else if(slot_buf[slot] == scratch) {
			bridge_stats.dropped++;
			board_led(BOARD_LED_ERROR, 1);
		} else {
			queue_push(slot_buf[slot], len);
			slot_buf[slot] = 0;
		}
		/* a fresh block for the slot that just finished */
		if(!slot_buf[slot]) {
			uint8_t *b = pool_get();
			slot_buf[slot] = b ? b : scratch;
		}
		if(slot)
			R32_HSPI_RX_ADDR1 = (uint32_t)slot_buf[1];
		else
			R32_HSPI_RX_ADDR0 = (uint32_t)slot_buf[0];
	}
	if(flags & RB_HSPI_IF_FIFO_OV) {
		R8_HSPI_INT_FLAG = RB_HSPI_IF_FIFO_OV;
		bridge_stats.hspi_fifo_ov++;
		board_led(BOARD_LED_ERROR, 1);
	}
}

/* ------------------------------------------------------------------ control */

void bridge_init(void)
{
	free_n = 0;
	for(int i = 0; i < BRIDGE_BUFS; i++)
		free_list[free_n++] = pool[i];
	source = SRC_HSPI;
	hspi_start();
}

void bridge_set_source(enum bridge_source s)
{
	uint32_t m = ep2_irq_save();
	if(s != source) {
		if(source == SRC_HSPI)
			hspi_stop();
		source = s;
		if(source == SRC_HSPI)
			hspi_start();
		else
			internal_seq = 0;
	}
	ep2_irq_restore(m);
}

enum bridge_source bridge_source(void)
{
	return source;
}

void bridge_poll(void)
{
	if(source != SRC_INTERNAL)
		return;
	for(;;) {
		uint32_t m = ep2_irq_save();
		uint8_t *b = pool_get();
		ep2_irq_restore(m);
		if(!b)
			return;
		uint32_t *w = (uint32_t *)b;
		w[0] = STREAM_MAGIC;
		w[1] = internal_seq++;
		w[2] = BLOCK;
		w[3] = STREAM_KIND_WORD;
		for(uint32_t k = STREAM_HDR_WORDS; k < BLOCK / 4; k++)
			w[k] = stream_word(k);
		m = ep2_irq_save();
		queue_push(b, BLOCK);
		ep2_irq_restore(m);
	}
}

unsigned bridge_pool_free(void)
{
	return free_n;
}

unsigned bridge_queued(void)
{
	return q_n;
}
