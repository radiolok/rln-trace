/*
 * Проверка потока самопроверки fw/ch569/usbstream (формат — stream.h).
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#ifndef CHECK_H
#define CHECK_H

#include <stddef.h>
#include <stdint.h>

#define STREAM_HOST
#include "stream.h"

#define BLOCK_MAX 65536

/* Обнулённая структура — начальное состояние */
struct parser {
	uint32_t hdr[STREAM_HDR_WORDS];
	uint32_t k;          /* слово внутри блока */
	uint32_t words;      /* длина текущего блока в словах */
	int synced;
	int have_seq;
	int bad;             /* в текущем блоке есть испорченные слова */
	uint32_t next_seq;
	uint64_t offset;     /* байт от начала приёма */

	uint64_t bytes;
	uint64_t blocks;
	uint64_t lost;       /* пропущенные номера */
	uint64_t dups;       /* повтор или откат номера */
	uint64_t restarts;   /* номер 0 посреди потока: прошивка переинициализировала USB */
	uint64_t bad_blocks;
	uint64_t bad_words;
	uint64_t desync;     /* потеря синхронизации после первой */
	uint64_t skipped;    /* байт до синхронизации */
	uint32_t block_len;
};

/* Разобрать очередной кусок потока; куски идут подряд, блок может их пересекать */
void check_parse(struct parser *p, const uint8_t *buf, size_t len);
/* Ошибок после первой синхронизации */
uint64_t check_errors(const struct parser *p);

#endif /* CHECK_H */
