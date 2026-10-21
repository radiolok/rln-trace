// trace_rx testbench: two free-running clocks, TPIU stream fed as DDR samples
// for ports of 1, 2 and 4 bits in both sample orders, across the async FIFO.
//
// SPDX-License-Identifier: BSD-3-Clause
#include <vector>

#include "Vtrace_rx.h"
#include "verilated.h"

#include "sim.h"
#include "tpiu_gen.h"

struct Clocks {
	uint64_t trc_half, sys_half; // ps
};

static uint64_t half_ps(double mhz) { return (uint64_t)(1e6 / mhz / 2 + 0.5); }

struct Case {
	unsigned width = 4;         // 1, 2, 4
	bool fall_first = false;    // sample order of the stream
	bool cfg_fall_first = false;// what the DUT is told
	double trc_mhz = 84, sys_mhz = 100;
	unsigned out_stall = 20;
	uint32_t seed = 1;
};

struct Result {
	std::vector<Expected> got;
	uint32_t overflow, lock, resync;
	int state;
};

static Result run(const std::vector<uint8_t> &bits, const Case &c)
{
	Rnd r(c.seed);
	auto *top = new Vtrace_rx;
	top->cfg_enable = 0;
	top->cfg_width = c.width == 1 ? 0 : c.width == 2 ? 1 : 2;
	top->cfg_fall_first = c.cfg_fall_first;
	top->cfg_verify_timeout = 0;
	top->cfg_lock_timeout = 0;
	top->cfg_misalign_max = 2;
	top->cfg_drop_idle = 0;
	top->out_ready = 1;
	top->trc_d_rise = top->trc_d_fall = 0;

	uint64_t th = half_ps(c.trc_mhz), sh = half_ps(c.sys_mhz);
	uint64_t t_trc = th, t_sys = sh;
	top->trc_clk = 0;
	top->clk = 0;
	top->trc_rst = top->rst = 1;
	top->eval();

	size_t pos = 0;            // next bit to feed
	uint64_t sys_cycles = 0, trc_cycles = 0, idle_after = 0;
	Result res{};
	auto feed = [&]() {
		unsigned a = 0, b = 0;
		for (unsigned i = 0; i < c.width; i++) {
			a |= (pos + i < bits.size() ? bits[pos + i] : 0) << i;
			b |= (pos + c.width + i < bits.size() ? bits[pos + c.width + i] : 0) << i;
		}
		// a is the earlier sample of the cycle
		top->trc_d_rise = c.fall_first ? b : a;
		top->trc_d_fall = c.fall_first ? a : b;
		pos += 2 * c.width;
	};

	const uint64_t never = ~0ull;
	while (true) {
		// TRACECLK stops when the stream is over, like a halted target
		if (pos >= bits.size() && !top->trc_clk)
			t_trc = never;
		bool trc_edge = t_trc <= t_sys;
		bool sys_edge = t_sys <= t_trc;
		bool trc_rise = trc_edge && !top->trc_clk;
		bool sys_rise = sys_edge && !top->clk;

		if (sys_rise && top->out_valid && top->out_ready) {
			Expected e;
			for (int i = 0; i < 16; i++)
				e.f[i] = top->out_frame[i / 4] >> (8 * (i % 4));
			e.num = top->out_num;
			res.got.push_back(e);
		}
		if (trc_edge) {
			top->trc_clk = !top->trc_clk;
			t_trc += th;
		}
		if (sys_edge) {
			top->clk = !top->clk;
			t_sys += sh;
		}
		top->eval();

		if (trc_rise) {
			trc_cycles++;
			if (trc_cycles == 8)
				top->trc_rst = 0;
			if (top->trc_rst == 0 && top->cfg_enable)
				feed();
		}
		if (sys_rise) {
			sys_cycles++;
			if (sys_cycles == 8)
				top->rst = 0;
			if (sys_cycles == 16)
				top->cfg_enable = 1;
			top->out_ready = !r.pct(c.out_stall);
			if (t_trc == never)
				idle_after++;
			if (idle_after > 500 || sys_cycles > 50'000'000)
				break;
		}
		top->eval();
	}
	res.overflow = top->cnt_overflow;
	res.lock = top->cnt_lock;
	res.resync = top->cnt_resync;
	res.state = top->state;
	top->final();
	delete top;
	return res;
}

// garbage, sync, three frames for VERIFY, sync, n good frames, syncs to flush
static std::vector<uint8_t> scenario(Rnd &r, int n, std::vector<Expected> &exp, unsigned offset)
{
	Stream s;
	for (int i = 0; i < 5; i++)
		s.bytes.push_back(r.u32() & 0x7F);
	s.sync();
	for (int i = 0; i < 3; i++)
		s.frame(random_frame(r));
	s.sync();
	for (int i = 0; i < n; i++) {
		Frame f = random_frame(r);
		s.frame(f);
		exp.push_back({f, (uint64_t)i});
		if (i % 16 == 15)
			s.sync();
	}
	for (int i = 0; i < 6; i++)
		s.sync();
	return to_bits(s.bytes, offset, r);
}

static void compare(const Result &res, const std::vector<Expected> &exp)
{
	EXPECT_EQ(res.got.size(), exp.size());
	for (size_t i = 0; i < std::min(res.got.size(), exp.size()); i++)
		if (res.got[i].f != exp[i].f || res.got[i].num != exp[i].num) {
			std::printf("    frame %zu differs\n", i);
			g_failed = 1;
			break;
		}
}

int main(int argc, char **argv)
{
	Verilated::commandArgs(argc, argv);

	std::printf("ports of 1, 2, 4 bits, both sample orders, various clock ratios\n");
	const double ratios[][2] = {{84, 100}, {24, 100}, {100, 60}, {150, 100}};
	uint32_t seed = 10;
	for (unsigned w : {1u, 2u, 4u})
		for (int ff = 0; ff < 2; ff++)
			for (auto &rt : ratios) {
				// the sys side takes a word every two cycles: keep the input below that
				double words_per_us = rt[0] * 2 * w / 32;
				if (words_per_us > rt[1] / 2 * 0.9)
					continue;
				Case c;
				c.width = w;
				c.fall_first = c.cfg_fall_first = ff;
				c.trc_mhz = rt[0];
				c.sys_mhz = rt[1];
				c.seed = seed++;
				Rnd r(c.seed);
				std::vector<Expected> exp;
				auto bits = scenario(r, 120, exp, r.below(32));
				Result res = run(bits, c);
				compare(res, exp);
				EXPECT_EQ(res.overflow, 0u);
				EXPECT_EQ(res.lock, 1u);
				EXPECT_EQ(res.state, 2);
				if (g_failed) {
					std::printf("    width %u fall_first %d trc %.0f sys %.0f\n", w, ff, rt[0], rt[1]);
					return 1;
				}
			}

	std::printf("STM32F407 worst case: 4 bits, TRACECLK 84 MHz, sys 100 MHz, long run\n");
	{
		Case c;
		c.out_stall = 0;
		Rnd r(77);
		std::vector<Expected> exp;
		auto bits = scenario(r, 3000, exp, 5);
		Result res = run(bits, c);
		compare(res, exp);
		EXPECT_EQ(res.overflow, 0u);
	}

	// With the nibbles of each byte swapped, two syncs in a row still contain 31 ones and a
	// zero at a shifted offset, so the deformatter may lock; the frames are garbage.
	std::printf("wrong sample order: no real frame comes out\n");
	{
		Case c;
		c.fall_first = true;
		c.cfg_fall_first = false;
		Rnd r(5);
		std::vector<Expected> exp;
		auto bits = scenario(r, 60, exp, 0);
		Result res = run(bits, c);
		for (const Expected &g : res.got)
			for (const Expected &e : exp)
				EXPECT(g.f != e.f);
	}

	std::printf("sys too slow: words dropped and counted, lock lost and found again\n");
	{
		Case c;
		c.trc_mhz = 100;
		c.sys_mhz = 25;
		c.out_stall = 0;
		Rnd r(9);
		std::vector<Expected> exp;
		auto bits = scenario(r, 400, exp, 3);
		Result res = run(bits, c);
		EXPECT(res.overflow > 0);
		EXPECT(res.got.size() < exp.size());
	}

	std::printf(g_failed ? "FAILED\n" : "all passed\n");
	return g_failed;
}
