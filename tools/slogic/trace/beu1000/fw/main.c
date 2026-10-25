/* Источник трассы для BE-U1000: известная последовательность ветвлений.
 *
 * Каждый проход цикла: условный переход по чётности n (inc_even / inc_odd), вызов через
 * указатель из таблицы ops[n % 3] (косвенный переход — в сообщении будет адрес) и возврат
 * (тоже косвенный). По трассе можно проверить, что последовательность функций совпадает
 * с n = 0, 1, 2, ... и что ни одно сообщение не потеряно.
 *
 * bits(i) — внутренний цикл на nbits шагов (по умолчанию 8) с ветвлением по битам i: 2 * nbits
 * условных переходов на проход (по данным и переход цикла). В BTM каждый взятый — сообщение DirectBranch, в HTM — бит HIST
 * в ближайшем IndirectBranchHist; на этом и видна разница в потоке. */
#include <stdint.h>

volatile uint32_t n;        /* номер прохода — смотреть по SBA */
volatile uint32_t acc;
volatile uint32_t nbits = 8;  /* длина внутреннего цикла bits() — меняется по SBA на ходу */
volatile uint32_t pat = 0xFFFFFFFF;  /* не 0xFFFFFFFF — в bits() идёт pat вместо i (известные исходы) */

__attribute__((noinline)) static void inc_even(void) { acc += 2; }
__attribute__((noinline)) static void inc_odd(void) { acc += 1; }
__attribute__((noinline)) static void op_a(void) { acc ^= 0x5A; }
__attribute__((noinline)) static void op_b(void) { acc = acc << 1 | acc >> 31; }
__attribute__((noinline)) static void op_c(void) { acc -= 3; }

static void (*const ops[3])(void) = { op_a, op_b, op_c };

__attribute__((noinline)) static uint32_t bits(uint32_t x)
{
    uint32_t r = 0;
    uint32_t len = nbits;
    for (uint32_t b = 0; b < len; b++) {
        if (x & (1u << (b & 31))) {
            r += b;
            __asm__ volatile("" ::: "memory");  /* не дать компилятору убрать ветвление */
        } else {
            r ^= b;
            __asm__ volatile("" ::: "memory");
        }
    }
    return r;
}

int main(void)
{
    for (uint32_t i = 0;; i++) {
        n = i;
        if (i & 1)
            inc_odd();
        else
            inc_even();
        acc += bits(pat == 0xFFFFFFFF ? i : pat);
        ops[i % 3]();
    }
}
