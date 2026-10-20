/*
 * Проверка потока самопроверки, см. check.h.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include <string.h>

#include "check.h"

/* PRBS31 одинакова во всех блоках: ожидаемые слова считаются один раз */
static uint32_t prbs_tab[BLOCK_MAX / 4];
static int prbs_ready;

static void prbs_init(void)
{
	uint32_t s = STREAM_PRBS31_SEED;

	for(uint32_t k = STREAM_HDR_WORDS; k < BLOCK_MAX / 4; k++)
		prbs_tab[k] = stream_prbs31(&s);
	prbs_ready = 1;
}

static void lose_sync(struct parser *p)
{
	if(p->synced)
		p->desync++;
	p->synced = 0;
	p->k = 0;
}

static void header_done(struct parser *p)
{
	uint32_t len = p->hdr[2], seq = p->hdr[1];

	if(len < 512 || len > BLOCK_MAX || len % 4 ||
	   (p->hdr[3] != STREAM_KIND_WORD && p->hdr[3] != STREAM_KIND_PRBS31)) {
		lose_sync(p);
		return;
	}
	p->kind = p->hdr[3];
	if(p->kind == STREAM_KIND_PRBS31) {
		p->prbs_blocks++;
		if(!prbs_ready)
			prbs_init();
	}
	p->words = len / 4;
	p->block_len = len;
	p->synced = 1;
	p->bad = 0;
	p->blocks++;

	if(p->have_seq && seq != p->next_seq) {
		uint32_t d = seq - p->next_seq;
		if(seq == 0)
			p->restarts++;
		else if(d < 0x80000000u)
			p->lost += d;
		else
			p->dups++;
	}
	p->next_seq = seq + 1;
	p->have_seq = 1;
}

void check_parse(struct parser *p, const uint8_t *buf, size_t len)
{
	size_t n = len / 4;

	p->bytes += len;
	for(size_t i = 0; i < n; i++, p->offset += 4) {
		uint32_t w;
		memcpy(&w, buf + 4 * i, 4);

		if(p->k < STREAM_HDR_WORDS) {
			if(p->k == 0 && w != STREAM_MAGIC) {
				/* блок начинается только на границе пакета */
				if(p->synced)
					lose_sync(p);
				p->skipped += 4;
				continue;
			}
			if(p->k == 0 && !p->synced && p->offset % 512) {
				p->skipped += 4;
				continue;
			}
			p->hdr[p->k++] = w;
			if(p->k == STREAM_HDR_WORDS)
				header_done(p);
			continue;
		}
		if(w != (p->kind == STREAM_KIND_PRBS31 ? prbs_tab[p->k] : stream_word(p->k))) {
			p->bad_words++;
			p->bad = 1;
		}
		if(++p->k == p->words) {
			if(p->bad)
				p->bad_blocks++;
			p->k = 0;
		}
	}
	if(len % 4) {
		/* пакеты кратны 512 байтам, хвост — признак сбоя */
		p->skipped += len % 4;
		lose_sync(p);
	}
}

uint64_t check_errors(const struct parser *p)
{
	return p->lost + p->dups + p->restarts + p->bad_blocks + p->desync;
}
