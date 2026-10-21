// tpiu_tx -> trace_rx loopback: every frame that comes out must be the frame
// tpiu_tx defines for its number, numbers consecutive; port widths 1, 2, 4,
// with and without halfword syncs, syncs every frame or rarely.
//
// SPDX-License-Identifier: BSD-3-Clause
#include <array>
#include <vector>

#include "Vtpiu_loop_top.h"
#include "verilated.h"

#include "sim.h"

using Frame = std::array<uint8_t, 16>;

// the frame tpiu_tx sends as number k (see gw/cores/tpiu_tx.sv)
static Frame frame_of(uint32_t k)
{
	Frame f;
	for (int i = 0; i < 16; i++) {
		uint8_t b;
		if (i == 0)
			b = 0x03;
		else if (i == 1 || i == 3 || i == 5 || i == 7)
			b = k >> (4 * (i - 1));
		else if (i == 9 || i == 11 || i == 13)
			b = (uint8_t)k ^ (uint8_t)(0x35 * i);
		else if (i == 15)
			b = (uint8_t)((k & 0x7F) << 1);
		else
			b = (uint8_t)((uint8_t)k + 0x1D * i) & 0xFE;
		f[i] = b;
	}
	return f;
}

struct Case {
	unsigned width;   // 1, 2, 4
	unsigned every;
	bool hsync;
};

static void run(const Case &c, uint32_t seed)
{
	Rnd r(seed);
	auto *top = new Vtpiu_loop_top;
	top->cfg_enable = 0;
	top->cfg_width = c.width == 1 ? 0 : c.width == 2 ? 1 : 2;
	top->cfg_sync_every = c.every;
	top->cfg_hsync = c.hsync;
	top->out_ready = 1;
	top->trc_clk = top->clk = 0;
	top->trc_rst = top->rst = 1;
	top->eval();

	// TRACECLK 84 MHz, sys 100 MHz
	uint64_t th = 5952, sh = 5000, t_trc = th, t_sys = sh, trc_cycles = 0, sys_cycles = 0;
	std::vector<std::pair<Frame, uint64_t>> got;
	while (got.size() < 300 && sys_cycles < 400000) {
		bool trc_edge = t_trc <= t_sys, sys_edge = t_sys <= t_trc;
		bool trc_rise = trc_edge && !top->trc_clk, sys_rise = sys_edge && !top->clk;
		if (sys_rise && top->out_valid && top->out_ready) {
			Frame f;
			for (int i = 0; i < 16; i++)
				f[i] = top->out_frame[i / 4] >> (8 * (i % 4));
			got.push_back({f, top->out_num});
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
		if (trc_rise && ++trc_cycles == 8)
			top->trc_rst = 0;
		if (sys_rise) {
			if (++sys_cycles == 8)
				top->rst = 0;
			if (sys_cycles == 12)
				top->cfg_enable = 1;
			top->out_ready = !r.pct(10);
		}
		top->eval();
	}
	EXPECT(got.size() >= 300);
	if (!got.empty()) {
		const Frame &f0 = got[0].first;
		uint32_t k0 = f0[1] | f0[3] << 8 | f0[5] << 16 | (uint32_t)f0[7] << 24;
		for (size_t i = 0; i < got.size(); i++) {
			if (got[i].first != frame_of(k0 + i) || got[i].second != got[0].second + i) {
				std::printf("    width %u every %u hsync %d: frame %zu wrong\n", c.width, c.every, c.hsync, i);
				g_failed = 1;
				break;
			}
		}
	}
	EXPECT_EQ(top->cnt_overflow, 0u);
	EXPECT_EQ(top->cnt_lock, 1u);
	if (c.hsync)
		EXPECT(top->cnt_hsync > 100);
	delete top;
}

int main(int argc, char **argv)
{
	Verilated::commandArgs(argc, argv);
	std::printf("tpiu_tx -> trace_rx: widths 1, 2, 4; syncs every 1 and 64 frames; halfword syncs\n");
	uint32_t seed = 1;
	for (unsigned w : {1u, 2u, 4u})
		for (unsigned every : {1u, 64u})
			for (bool hs : {false, true})
				run(Case{w, every, hs}, seed++);
	std::printf(g_failed ? "FAILED\n" : "all passed\n");
	return g_failed;
}
