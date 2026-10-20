/*
 * Тест check.c: синтетический поток с подброшенными ошибками, разбор кусками
 * произвольной длины.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "check.h"

static int failed;

#define EXPECT(cond) do { if(!(cond)) { printf("  %s:%d: %s\n", __FILE__, __LINE__, #cond); failed = 1; } } while(0)

/* поток из n блоков по len байт с номерами first.. */
static size_t gen(uint8_t *buf, uint32_t len, uint32_t first, int n)
{
	for(int b = 0; b < n; b++) {
		uint32_t *w = (uint32_t *)(buf + (size_t)b * len);
		w[0] = STREAM_MAGIC;
		w[1] = first + b;
		w[2] = len;
		w[3] = 0;
		for(uint32_t k = STREAM_HDR_WORDS; k < len / 4; k++)
			w[k] = stream_word(k);
	}
	return (size_t)n * len;
}

/* разбор кусками: chunk == 0 — случайные длины, кратные 4 */
static struct parser run(const uint8_t *buf, size_t len, size_t chunk)
{
	struct parser p;
	memset(&p, 0, sizeof(p));
	srand(1);
	for(size_t off = 0; off < len;) {
		size_t n = chunk ? chunk : 4 * (1 + (size_t)rand() % 3000);
		if(n > len - off)
			n = len - off;
		check_parse(&p, buf + off, n);
		off += n;
	}
	return p;
}

int main(void)
{
	enum { N = 64 };
	static uint8_t buf[N * 4096 + 4096], tmp[N * 4096];
	struct parser p;
	size_t len;

	printf("чистый поток USB3 и USB2, разные куски\n");
	for(uint32_t bl = 512; bl <= 4096; bl *= 8) {
		len = gen(buf, bl, 100, N);
		size_t chunks[] = { 0, 4, 512, 1024, 4096, 65536 };
		for(size_t i = 0; i < sizeof(chunks) / sizeof(chunks[0]); i++) {
			p = run(buf, len, chunks[i]);
			EXPECT(p.blocks == N && check_errors(&p) == 0 && p.skipped == 0 && p.block_len == bl);
		}
	}

	printf("начало посреди блока: синхронизация на границе 512\n");
	len = gen(buf, 4096, 0, N);
	p = run(buf + 1024, len - 1024, 0);
	EXPECT(p.blocks == N - 1 && check_errors(&p) == 0 && p.skipped == 3072);

	printf("потеря блоков\n");
	len = gen(buf, 4096, 0, 10);
	len += gen(buf + len, 4096, 13, 10); /* 10..12 пропали */
	p = run(buf, len, 0);
	EXPECT(p.lost == 3 && p.dups == 0 && p.blocks == 20);

	printf("повтор блока\n");
	len = gen(buf, 4096, 0, 10);
	len += gen(buf + len, 4096, 9, 5);
	p = run(buf, len, 0);
	EXPECT(p.dups == 1 && p.lost == 0);

	printf("рестарт номера\n");
	len = gen(buf, 4096, 50, 10);
	len += gen(buf + len, 4096, 0, 10);
	p = run(buf, len, 0);
	EXPECT(p.restarts == 1 && p.lost == 0 && p.dups == 0);

	printf("переход номера через 2^32\n");
	len = gen(buf, 512, 0xFFFFFFFCu, 10);
	p = run(buf, len, 0);
	EXPECT(check_errors(&p) == 0 && p.blocks == 10);

	printf("испорченное слово нагрузки\n");
	len = gen(buf, 4096, 0, N);
	buf[5 * 4096 + 2000] ^= 0x10;
	p = run(buf, len, 0);
	EXPECT(p.bad_blocks == 1 && p.bad_words == 1 && p.desync == 0 && p.blocks == N);

	printf("испорченный маркер: блок теряется, синхронизация возвращается\n");
	len = gen(buf, 4096, 0, N);
	buf[7 * 4096] ^= 1;
	p = run(buf, len, 0);
	EXPECT(p.desync == 1 && p.lost == 1 && p.blocks == N - 1);

	printf("выпавший пакет 1024 байт внутри блока\n");
	len = gen(tmp, 4096, 0, N);
	memcpy(buf, tmp, 3 * 4096 + 1024);
	memcpy(buf + 3 * 4096 + 1024, tmp + 3 * 4096 + 2048, len - 3 * 4096 - 2048);
	p = run(buf, len - 1024, 0);
	EXPECT(check_errors(&p) > 0 && p.blocks >= N - 2);

	printf("хвост не кратен 4\n");
	len = gen(buf, 512, 0, 4);
	memset(&p, 0, sizeof(p));
	check_parse(&p, buf, 1026);
	check_parse(&p, buf + 1026, len - 1026);
	EXPECT(check_errors(&p) > 0);

	printf(failed ? "ОШИБКИ\n" : "всё верно\n");
	return failed;
}
