// Small helpers shared by the Verilator testbenches.
//
// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <string>

static int g_failed;

#define EXPECT(cond)                                                                  \
	do {                                                                              \
		if (!(cond)) {                                                                \
			std::printf("    %s:%d: %s\n", __FILE__, __LINE__, #cond);                \
			g_failed = 1;                                                             \
		}                                                                             \
	} while (0)

#define EXPECT_EQ(a, b)                                                               \
	do {                                                                              \
		auto va_ = (a);                                                               \
		auto vb_ = (b);                                                               \
		if (!(va_ == vb_)) {                                                          \
			std::printf("    %s:%d: %s == %s (%llu != %llu)\n", __FILE__, __LINE__,   \
			            #a, #b, (unsigned long long)va_, (unsigned long long)vb_);    \
			g_failed = 1;                                                             \
		}                                                                             \
	} while (0)

// One clock cycle: inputs set before the call, outputs read before the call
// see the combinational result of those inputs.
template <class T> static void tick(T *top)
{
	top->clk = 0;
	top->eval();
	top->clk = 1;
	top->eval();
}

template <class T> static void reset(T *top, int cycles = 4)
{
	top->rst = 1;
	for (int i = 0; i < cycles; i++)
		tick(top);
	top->rst = 0;
}

// Random duty: true with probability pct percent.
struct Rnd {
	std::mt19937 gen;
	explicit Rnd(uint32_t seed) : gen(seed) {}
	uint32_t u32() { return gen(); }
	uint32_t below(uint32_t n) { return n ? gen() % n : 0; }
	bool pct(unsigned p) { return below(100) < p; }
};
