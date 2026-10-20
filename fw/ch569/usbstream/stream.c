/*
 * Генератор потока самопроверки, формат — в stream.h.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include "stream.h"

static uint32_t stream_seq;

static void stream_hdr(uint8_t *buf, uint32_t len)
{
	uint32_t *w = (uint32_t *)buf;

	w[0] = STREAM_MAGIC;
	w[1] = stream_seq++;
	w[2] = len;
	w[3] = 0;
}

void stream_start(uint8_t *buf, uint32_t len)
{
	uint32_t *w = (uint32_t *)buf;

	for(uint32_t k = STREAM_HDR_WORDS; k < len / 4; k++)
		w[k] = stream_word(k);
	stream_seq = 0;
	stream_hdr(buf, len);
}

void stream_next(uint8_t *buf, uint32_t len)
{
	stream_hdr(buf, len);
}
