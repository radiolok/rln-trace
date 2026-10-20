/*
 * Поток самопроверки EP2 IN: CH569 сам генерирует блоки, ПК проверяет их без ПЛИС.
 *
 * Блок занимает одну передачу точки: 4096 байт на USB3 (пачка из 4 пакетов по 1024),
 * 512 байт на USB2. Слова little-endian:
 *   [0] STREAM_MAGIC
 *   [1] номер блока, с нуля после каждой инициализации USB
 *   [2] длина блока в байтах
 *   [3] 0
 *   [k] stream_word(k) для k = 4 .. len/4 - 1
 * Нагрузка от номера блока не зависит: прошивка заполняет её один раз и перед каждой
 * отправкой переписывает только заголовок. Номер ловит потерю и повтор блока, нагрузка —
 * порчу и сдвиг данных.
 *
 * Заголовок общий с утилитой на ПК (sw/usbstream).
 *
 * SPDX-License-Identifier: BSD-3-Clause
 */
#ifndef STREAM_H
#define STREAM_H

#include <stdint.h>

#define STREAM_MAGIC    0x534E4C52u /* "RLNS" */
#define STREAM_HDR_WORDS 4

static inline uint32_t stream_word(uint32_t k)
{
	return k * 0x9E3779B1u + 0x7F4A7C15u;
}

#ifndef STREAM_HOST
/* Заполнить нагрузку и заголовок первого блока, номер с нуля */
void stream_start(uint8_t *buf, uint32_t len);
/* Заголовок следующего блока; буфер не должен быть в работе у DMA */
void stream_next(uint8_t *buf, uint32_t len);
#endif

#endif /* STREAM_H */
