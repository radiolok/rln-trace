// tpiu_rx testbench: generated TPIU streams with known frames, any bit offset,
// halfword syncs, misaligned syncs, bit slips, idle frames, random stalls.
//
// SPDX-License-Identifier: BSD-3-Clause
#include <array>
#include <cstring>
#include <vector>

#include "Vtpiu_rx.h"
#include "verilated.h"

#include "sim.h"
#include "tpiu_gen.h"

// ---------------------------------------------------------------- run

struct Config {
	uint16_t verify_timeout = 0;
	uint32_t lock_timeout = 0;
	uint8_t misalign_max = 2;
	bool drop_idle = false;
	unsigned in_stall = 30, out_stall = 30; // percent of cycles without valid / ready
};

struct Result {
	std::vector<Expected> got;
	uint32_t lock, resync, misaligned, hsync, idle;
	int state;
	uint64_t in_cycles; // cycles until the last word was taken
};

static Result run(const std::vector<uint32_t> &words, const Config &c, uint32_t seed)
{
	Rnd r(seed);
	auto *top = new Vtpiu_rx;
	top->cfg_verify_timeout = c.verify_timeout;
	top->cfg_lock_timeout = c.lock_timeout;
	top->cfg_misalign_max = c.misalign_max;
	top->cfg_drop_idle = c.drop_idle;
	top->in_valid = 0;
	top->out_ready = 0;
	reset(top);

	Result res{};
	size_t i = 0, idle_cycles = 0;
	uint64_t cycles = 0;
	while (idle_cycles < 200) {
		top->in_valid = i < words.size() && !r.pct(c.in_stall);
		top->in_data = i < words.size() ? words[i] : 0;
		top->out_ready = !r.pct(c.out_stall);
		top->eval();
		bool in_fire = top->in_valid && top->in_ready;
		if (top->out_valid && top->out_ready) {
			Expected e;
			for (int b = 0; b < 16; b++)
				e.f[b] = top->out_frame[b / 4] >> (8 * (b % 4));
			e.num = top->out_num;
			res.got.push_back(e);
		}
		tick(top);
		if (in_fire && ++i == words.size())
			res.in_cycles = cycles;
		cycles++;
		idle_cycles = i < words.size() ? 0 : idle_cycles + 1;
	}
	res.lock = top->cnt_lock;
	res.resync = top->cnt_resync;
	res.misaligned = top->cnt_misaligned;
	res.hsync = top->cnt_hsync;
	res.idle = top->cnt_idle;
	res.state = top->state;
	top->final();
	delete top;
	return res;
}

static void compare(const Result &res, const std::vector<Expected> &exp)
{
	EXPECT_EQ(res.got.size(), exp.size());
	size_t n = std::min(res.got.size(), exp.size());
	for (size_t i = 0; i < n; i++) {
		if (res.got[i].f != exp[i].f || res.got[i].num != exp[i].num) {
			std::printf("    frame %zu: num %llu, expected %llu%s\n", i, (unsigned long long)res.got[i].num,
			            (unsigned long long)exp[i].num, res.got[i].f != exp[i].f ? ", data differs" : "");
			g_failed = 1;
			break;
		}
	}
}

// garbage, sync, a few frames dropped in VERIFY, sync, then the frames that count
struct Scenario {
	Stream s;
	std::vector<Expected> exp;
	uint64_t num = 0;
	Rnd r;
	explicit Scenario(uint32_t seed) : r(seed)
	{
		for (int i = 0; i < 6; i++)
			s.bytes.push_back(r.u32() & 0x7F);
		s.sync();
		for (int i = 0; i < 3; i++)
			s.frame(random_frame(r));
		s.sync();
	}
	void good(const Frame &f)
	{
		s.frame(f);
		exp.push_back({f, num++});
	}
	void good(int n)
	{
		for (int i = 0; i < n; i++)
			good(random_frame(r));
	}
	void tail()
	{
		for (int i = 0; i < 4; i++)
			s.sync();
	}
};

int main(int argc, char **argv)
{
	Verilated::commandArgs(argc, argv);

	std::printf("clean stream at every bit offset\n");
	for (unsigned off = 0; off < 32; off++) {
		Scenario sc(100 + off);
		for (int k = 0; k < 6; k++) {
			sc.good(5);
			sc.s.sync();
		}
		sc.tail();
		Result res = run(pack(sc.s.bytes, off, sc.r), Config{}, off);
		compare(res, sc.exp);
		EXPECT_EQ(res.lock, 1u);
		EXPECT_EQ(res.resync, 0u);
		EXPECT_EQ(res.state, 2);
	}

	std::printf("no stalls, full rate\n");
	{
		Scenario sc(7);
		sc.good(200);
		sc.tail();
		Config c;
		c.in_stall = c.out_stall = 0;
		auto words = pack(sc.s.bytes, 13, sc.r);
		Result res = run(words, c, 7);
		compare(res, sc.exp);
		// one 32-bit word per two cycles: the aligner sends it as two halfwords
		EXPECT(res.in_cycles <= 2 * words.size() + 8);
	}

	std::printf("halfword syncs between and inside frames\n");
	{
		Scenario sc(11);
		for (int k = 0; k < 40; k++) {
			Frame f = random_frame(sc.r);
			int at = sc.r.below(9); // halfword position, 8 = after the frame
			for (int h = 0; h < 8; h++) {
				if (h == at)
					sc.s.hsync();
				sc.s.raw({f[2 * h], f[2 * h + 1]});
			}
			if (at == 8)
				sc.s.hsync();
			sc.exp.push_back({f, sc.num++});
		}
		sc.tail();
		Result res = run(pack(sc.s.bytes, 5, sc.r), Config{}, 11);
		compare(res, sc.exp);
		EXPECT_EQ(res.hsync, 40u);
	}

	std::printf("sync off the frame boundary in LOCK: partial frame dropped, lock kept\n");
	{
		Scenario sc(21);
		sc.good(4);
		sc.s.half_frame(random_frame(sc.r), 3);
		sc.s.sync();
		sc.good(4);
		sc.s.sync();
		sc.good(4);
		sc.tail();
		Result res = run(pack(sc.s.bytes, 9, sc.r), Config{}, 21);
		compare(res, sc.exp);
		EXPECT_EQ(res.misaligned, 1u);
		EXPECT_EQ(res.resync, 0u);
	}

	std::printf("misaligned syncs in a row: back to HUNT, then lock again\n");
	{
		Scenario sc(31);
		sc.good(3);
		sc.s.half_frame(random_frame(sc.r), 2);
		sc.s.sync();
		sc.s.half_frame(random_frame(sc.r), 5);
		sc.s.sync(); // second in a row with misalign_max = 2 -> HUNT, consumed
		for (int i = 0; i < 3; i++)
			sc.s.frame(random_frame(sc.r)); // aligner hunting: ignored
		sc.s.sync();                        // found -> VERIFY
		sc.s.frame(random_frame(sc.r));     // dropped in VERIFY
		sc.s.sync();                        // -> LOCK
		sc.good(5);
		sc.tail();
		Result res = run(pack(sc.s.bytes, 17, sc.r), Config{}, 31);
		compare(res, sc.exp);
		EXPECT_EQ(res.misaligned, 2u);
		EXPECT_EQ(res.resync, 1u);
		EXPECT_EQ(res.lock, 2u);
	}

	std::printf("VERIFY fails on a misaligned second sync\n");
	{
		Rnd r(41);
		Stream s;
		s.raw({1, 2, 3});
		s.sync();
		s.half_frame(random_frame(r), 3);
		s.sync(); // VERIFY -> HUNT
		s.frame(random_frame(r));
		s.sync(); // VERIFY
		s.frame(random_frame(r));
		s.sync(); // LOCK
		std::vector<Expected> exp;
		for (int i = 0; i < 5; i++) {
			Frame f = random_frame(r);
			s.frame(f);
			exp.push_back({f, (uint64_t)i});
		}
		for (int i = 0; i < 4; i++)
			s.sync();
		Result res = run(pack(s.bytes, 3, r), Config{}, 41);
		compare(res, exp);
		EXPECT_EQ(res.lock, 1u);
	}

	std::printf("bit slip: lock timeout, hunt, lock at the new offset\n");
	{
		Scenario sc(51);
		sc.good(6);
		size_t slip_at = sc.s.bytes.size() * 8 + 37; // inside the next frame
		for (int i = 0; i < 6; i++)
			sc.s.frame(random_frame(sc.r)); // garbled by the slip, then timeout
		for (int k = 0; k < 3; k++) {
			sc.s.sync(); // hunt finds it: VERIFY, then LOCK on the next one
			for (int i = 0; i < 2; i++)
				sc.s.frame(random_frame(sc.r));
		}
		sc.s.sync();
		for (int i = 0; i < 5; i++) {
			Frame f = random_frame(sc.r);
			sc.s.frame(f);
		}
		sc.tail();
		Config c;
		c.lock_timeout = 8 * 8; // eight frames without an aligned sync: longer than the six good ones
		Result res = run(pack(sc.s.bytes, 2, sc.r, {slip_at}), c, 51);
		// the six frames before the slip come out unchanged, then the stream relocks
		EXPECT(res.got.size() >= 6);
		for (size_t i = 0; i < 6 && i < res.got.size(); i++) {
			EXPECT(res.got[i].f == sc.exp[i].f);
			EXPECT_EQ(res.got[i].num, (uint64_t)i);
		}
		EXPECT_EQ(res.resync, 1u);
		EXPECT_EQ(res.lock, 2u);
		EXPECT_EQ(res.state, 2);
		// the last five frames after relock are delivered
		EXPECT(res.got.size() >= 11);
	}

	std::printf("idle frames: dropped only when they do not change the ID state\n");
	for (int drop = 0; drop < 2; drop++) {
		Scenario sc(61);
		IdState st;
		auto push = [&](const Frame &f) {
			sc.s.frame(f);
			bool idle = idle_frame(f, st);
			if (!(drop && idle))
				sc.exp.push_back({f, sc.num});
			sc.num++;
		};
		// frames dropped in VERIFY never reach the filter: its ID state starts at reset
		Frame idle0{};
		idle0[0] = 0x01; // ID change to 0, then zeros
		for (int k = 0; k < 30; k++) {
			switch (sc.r.below(4)) {
			case 0: push(idle0); break;
			case 1: push(id_frame(sc.r, 1 + sc.r.below(0x6F))); break;
			case 2: push(id_frame(sc.r, 0)); break;
			default: push(random_frame(sc.r)); break;
			}
		}
		sc.tail();
		Config c;
		c.drop_idle = drop;
		Result res = run(pack(sc.s.bytes, 23, sc.r), c, 61);
		compare(res, sc.exp);
		if (drop)
			EXPECT(res.idle > 0);
		else
			EXPECT_EQ(res.idle, 0u);
	}

	std::printf(g_failed ? "FAILED\n" : "all passed\n");
	return g_failed;
}
