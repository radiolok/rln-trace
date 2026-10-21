// hspi_rx testbench: CH569 transmit model on its own HTCLK, packets checked on
// the sys side: payload, header, the good flag for CRC / number / TLL2B / length
// faults, flow control through HTRDY, raw mode for the CRC measurement.
//
// Build-time parameters (must match the -G values): HSPI_W, HSPI_CRC_INIT,
// HSPI_CRC_REFLECT, HSPI_CRC_XOROUT. MAX_WORDS is the RTL default, 128.
//
// SPDX-License-Identifier: BSD-3-Clause
#include <cstdlib>
#include <vector>

#include "Vhspi_rx.h"
#include "verilated.h"

#include "sim.h"
#include "ch569_hspi.h"
#include "ch569_hspi_tx.h"

#ifndef HSPI_W
#define HSPI_W 16
#endif
#ifndef HSPI_CRC_INIT
#define HSPI_CRC_INIT 0
#endif
#ifndef HSPI_CRC_REFLECT
#define HSPI_CRC_REFLECT 0
#endif
#ifndef HSPI_CRC_XOROUT
#define HSPI_CRC_XOROUT 0
#endif

static const unsigned MAX_WORDS = 128;

struct RxPacket {
	std::vector<uint32_t> words; // header, payload; the closing word separately
	uint32_t closing = 0;
	bool good = false;
};

struct Case {
	double rx_mhz = 120, sys_mhz = 100;
	unsigned out_stall = 10;
	bool raw = false;
	uint32_t seed = 1;
};

static std::vector<RxPacket> run(Ch569HspiTx &tx, const Case &c, Vhspi_rx *&top_out)
{
	Rnd r(c.seed);
	auto *top = new Vhspi_rx;
	top->cfg_raw = c.raw;
	top->rx_req = top->rx_vld = 0;
	top->rx_data = 0;
	top->out_ready = 1;
	top->rx_clk = top->clk = 0;
	top->rx_rst = top->rst = 1;
	top->eval();

	uint64_t rh = (uint64_t)(1e6 / c.rx_mhz / 2), sh = (uint64_t)(1e6 / c.sys_mhz / 2);
	uint64_t t_rx = rh, t_sys = sh, rx_cycles = 0, sys_cycles = 0, idle = 0;
	std::vector<RxPacket> got;
	RxPacket cur;

	while (idle < 2000 && sys_cycles < 20'000'000) {
		bool rx_edge = t_rx <= t_sys, sys_edge = t_sys <= t_rx;
		bool rx_rise = rx_edge && !top->rx_clk, sys_rise = sys_edge && !top->clk;
		bool rdy = top->rx_rdy;

		if (sys_rise && top->out_valid && top->out_ready) {
			if (top->out_last) {
				cur.closing = top->out_data;
				cur.good = top->out_good;
				got.push_back(cur);
				cur = RxPacket{};
			} else {
				cur.words.push_back(top->out_data);
			}
		}
		if (rx_edge) {
			top->rx_clk = !top->rx_clk;
			t_rx += rh;
		}
		if (sys_edge) {
			top->clk = !top->clk;
			t_sys += sh;
		}
		top->eval();
		if (rx_rise) {
			if (++rx_cycles == 8)
				top->rx_rst = 0;
			if (!top->rx_rst) {
				tx.cycle(rdy);
				top->rx_req = tx.req;
				top->rx_vld = tx.vld;
				top->rx_data = tx.data;
			}
		}
		if (sys_rise) {
			if (++sys_cycles == 8)
				top->rst = 0;
			top->out_ready = !r.pct(c.out_stall);
			idle = tx.idle() && !top->out_valid ? idle + 1 : 0;
		}
		top->eval();
	}
	top_out = top;
	return got;
}

static Ch569HspiTx make_tx(uint32_t seed)
{
	Ch569HspiTx tx(seed);
	tx.width = HSPI_W;
	tx.crc = HspiCrc{HSPI_W == 32 ? 32 : 16, (uint32_t)HSPI_CRC_INIT, HSPI_CRC_REFLECT != 0, (uint32_t)HSPI_CRC_XOROUT};
	return tx;
}

static HspiPacket random_packet(Rnd &r, unsigned max_payload_words)
{
	HspiPacket p;
	unsigned n = 4 * (1 + r.below(max_payload_words));
	for (unsigned i = 0; i < n; i++)
		p.payload.push_back(r.u32());
	p.usdf = r.u32() & 0x3FFFFFF;
	return p;
}

static uint32_t le32(const uint8_t *b) { return b[0] | b[1] << 8 | b[2] << 16 | (uint32_t)b[3] << 24; }

// packet as hspi_rx should give it: header word, payload words
static std::vector<uint32_t> expected_words(const HspiPacket &p)
{
	std::vector<uint32_t> w = {le32(p.wire.data())};
	for (size_t i = 0; i + 4 <= p.payload.size(); i += 4)
		w.push_back(le32(p.payload.data() + i));
	return w;
}

int main(int argc, char **argv)
{
	Verilated::commandArgs(argc, argv);
	std::printf("HSPI RX %d bit, CRC%d init %x reflect %d xorout %x\n", HSPI_W, HSPI_W == 32 ? 32 : 16,
	            (unsigned)HSPI_CRC_INIT, HSPI_CRC_REFLECT, (unsigned)HSPI_CRC_XOROUT);

	std::printf("clean packets of random length, HTVLD gaps, both clock orders\n");
	for (auto [rx, sys] : {std::pair{120.0, 100.0}, std::pair{60.0, 100.0}, std::pair{120.0, 40.0}}) {
		Rnd r(1);
		Ch569HspiTx tx = make_tx(2);
		for (int i = 0; i < 60; i++)
			tx.queue.push_back(random_packet(r, MAX_WORDS - 1));
		Case c;
		c.rx_mhz = rx;
		c.sys_mhz = sys;
		Vhspi_rx *top;
		auto got = run(tx, c, top);
		EXPECT_EQ(got.size(), tx.sent.size());
		for (size_t i = 0; i < std::min(got.size(), tx.sent.size()); i++) {
			EXPECT(got[i].good);
			EXPECT(got[i].words == expected_words(tx.sent[i]));
			EXPECT_EQ(got[i].closing, 0u);
		}
		EXPECT_EQ(top->cnt_bad, 0u);
		delete top;
	}

	std::printf("sys side stalls for long: HTRDY holds the sender back, nothing lost\n");
	{
		Rnd r(3);
		Ch569HspiTx tx = make_tx(4);
		for (int i = 0; i < 40; i++)
			tx.queue.push_back(random_packet(r, MAX_WORDS - 1));
		Case c;
		c.out_stall = 97;
		Vhspi_rx *top;
		auto got = run(tx, c, top);
		EXPECT_EQ(got.size(), 40u);
		for (size_t i = 0; i < std::min(got.size(), tx.sent.size()); i++)
			EXPECT(got[i].good && got[i].words == expected_words(tx.sent[i]));
		delete top;
	}

	std::printf("faults: bit flip, skipped number, TLL2B, too long; the rest stays good\n");
	{
		Rnd r(5);
		Ch569HspiTx tx = make_tx(6);
		std::vector<bool> want;
		for (int i = 0; i < 24; i++) {
			HspiPacket p = random_packet(r, 30);
			bool good = true;
			switch (i) {
			case 4: p.flip_bit = true; good = false; break;
			case 9: p.skip_seq = true; good = false; break;
			case 14: p.tll = 2; good = false; break;
			case 19:
				p.payload.resize(4 * MAX_WORDS, 0x5A); // header + MAX_WORDS words > MAX_WORDS
				good = false;
				break;
			}
			tx.queue.push_back(p);
			want.push_back(good);
		}
		Case c;
		Vhspi_rx *top;
		auto got = run(tx, c, top);
		EXPECT_EQ(got.size(), want.size());
		for (size_t i = 0; i < std::min(got.size(), want.size()); i++) {
			if (got[i].good != want[i]) {
				std::printf("    packet %zu: good %d, expected %d\n", i, got[i].good, (int)want[i]);
				g_failed = 1;
			}
			if (want[i])
				EXPECT(got[i].words == expected_words(tx.sent[i]));
		}
		EXPECT(got.size() > 19 && got[19].words.size() == MAX_WORDS);
		EXPECT_EQ(top->cnt_bad, 4u);
		delete top;
	}

	std::printf("raw mode: every byte from the bus, CRC included\n");
	{
		Rnd r(7);
		Ch569HspiTx tx = make_tx(8);
		for (int i = 0; i < 20; i++)
			tx.queue.push_back(random_packet(r, 20));
		Case c;
		c.raw = true;
		Vhspi_rx *top;
		auto got = run(tx, c, top);
		EXPECT_EQ(got.size(), tx.sent.size());
		for (size_t i = 0; i < std::min(got.size(), tx.sent.size()); i++) {
			std::vector<uint8_t> b;
			for (uint32_t w : got[i].words)
				for (int k = 0; k < 4; k++)
					b.push_back(w >> (8 * k));
			unsigned left = got[i].closing >> 24;
			for (unsigned k = 0; k < left; k++)
				b.push_back(got[i].closing >> (8 * k));
			EXPECT(b == tx.sent[i].wire);
			EXPECT(got[i].good);
			// HSPI_RAW_DUMP: packets for tools/hspi-crc/find_crc.py, as on the bench
			if (const char *path = getenv("HSPI_RAW_DUMP")) {
				static FILE *f = fopen(path, "w");
				for (uint8_t x : b)
					fprintf(f, "%02x", x);
				fprintf(f, "\n");
				fflush(f);
			}
		}
		delete top;
	}

	std::printf(g_failed ? "FAILED\n" : "all passed\n");
	return g_failed;
}
