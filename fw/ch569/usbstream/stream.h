/*
 * Поток самопроверки EP2 IN: CH569 сам генерирует блоки, ПК проверяет их без ПЛИС.
 *
 * Блок занимает одну передачу точки: 4096 байт на USB3 (пачка из 4 пакетов по 1024),
 * 512 байт на USB2. Слова little-endian:
 *   [0] STREAM_MAGIC
 *   [1] номер блока, с нуля после каждой инициализации USB
 *   [2] длина блока в байтах
 *   [3] вид нагрузки: STREAM_KIND_WORD или STREAM_KIND_PRBS31
 *   [k] нагрузка, k = 4 .. len/4 - 1:
 *       STREAM_KIND_WORD   — stream_word(k);
 *       STREAM_KIND_PRBS31 — PRBS31 (x^31 + x^28 + 1) с начальным состоянием
 *                            STREAM_PRBS31_SEED в каждом блоке, по 32 бита на слово,
 *                            первый бит — в бите 0 (stream_prbs31()).
 * Нагрузка от номера блока не зависит: прошивка заполняет её один раз и перед каждой
 * отправкой переписывает только заголовок. Номер ловит потерю и повтор блока, нагрузка —
 * порчу и сдвиг данных. PRBS31 даёт на линиях больше переключений, это вид для генератора
 * в ПЛИС (gw/cores/selftest_gen.sv); прошивка CH569 шлёт STREAM_KIND_WORD.
 *
 * Заголовок общий с утилитой на ПК (sw/usbstream) и тестбенчами gw.
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#ifndef STREAM_H
#define STREAM_H

#include <stdint.h>

#define STREAM_MAGIC    0x534E4C52u /* "RLNS" */
#define STREAM_HDR_WORDS 4

#define STREAM_KIND_WORD   0
#define STREAM_KIND_PRBS31 1

#define STREAM_PRBS31_SEED 0x7FFFFFFFu

static inline uint32_t stream_word(uint32_t k)
{
	return k * 0x9E3779B1u + 0x7F4A7C15u;
}

/* Следующие 32 бита PRBS31, *state — 31 бит регистра */
static inline uint32_t stream_prbs31(uint32_t *state)
{
	uint32_t s = *state, w = 0;

	for(int i = 0; i < 32; i++) {
		uint32_t b = ((s >> 30) ^ (s >> 27)) & 1u;
		s = ((s << 1) | b) & 0x7FFFFFFFu;
		w |= b << i;
	}
	*state = s;
	return w;
}

#ifndef STREAM_HOST
/* Заполнить нагрузку и заголовок первого блока, номер с нуля */
void stream_start(uint8_t *buf, uint32_t len);
/* Заголовок следующего блока; буфер не должен быть в работе у DMA */
void stream_next(uint8_t *buf, uint32_t len);
#endif

#endif /* STREAM_H */
