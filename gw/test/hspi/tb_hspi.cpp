// selftest_hspi testbench: generator -> HSPI -> CH569 receive model -> check.c,
// the same stream check as sw/usbstream on the PC.
//
// Build-time parameters (must match the -G values): HSPI_W, HSPI_CRC_INIT,
// HSPI_CRC_REFLECT, HSPI_CRC_XOROUT.
//
// SPDX-License-Identifier: BSD-3-Clause
#include <cstring>

#include "Vselftest_hspi.h"
#include "verilated.h"

#include "sim.h"
#include "ch569_hspi.h"
#include "check.h"

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

struct Run {
	unsigned kind = STREAM_KIND_PRBS31;
	unsigned block_words = 1024;
	unsigned packets = 200;
	unsigned ack_delay = 0, drain_min = 0, drain_max = 0;
	unsigned gap = 0;
	int corrupt_wire = -1, corrupt_payload = -1;
	uint32_t usdf = 0x2A5A5A5;
	uint32_t seed = 1;
};

struct Out {
	parser chk;
	uint64_t packets, crc_err, seq_err, len_err, tll_err, proto_err, stalls;
	uint32_t usdf;
	double efficiency; // payload bytes per cycle / bus bytes per cycle
	uint32_t dut_packets, dut_blocks;
};

static Out run(const Run &r)
{
	auto *top = new Vselftest_hspi;
	Ch569HspiRx rx(r.seed);
	rx.width = HSPI_W;
	rx.crc = HspiCrc{HSPI_W == 32 ? 32 : 16, (uint32_t)HSPI_CRC_INIT, HSPI_CRC_REFLECT != 0, (uint32_t)HSPI_CRC_XOROUT};
	rx.ack_delay_max = r.ack_delay;
	rx.drain_min = r.drain_min;
	rx.drain_max = r.drain_max;
	rx.corrupt_wire_at = r.corrupt_wire;
	rx.corrupt_payload_at = r.corrupt_payload;

	Out o{};
	std::memset(&o.chk, 0, sizeof(o.chk));
	rx.sink = [&](const uint8_t *p, size_t n) { check_parse(&o.chk, p, n); };

	top->cfg_enable = 0;
	top->cfg_kind = r.kind;
	top->cfg_block_words = r.block_words;
	top->cfg_usdf = r.usdf;
	top->cfg_gap = r.gap;
	top->cfg_ack_timeout = 0;
	top->hspi_ack = 0;
	reset(top);
	top->cfg_enable = 1;

	uint64_t cycles = 0, first = 0, last = 0, limit = 400ull * r.packets * (r.block_words * 4 / (HSPI_W / 8) + 64);
	uint64_t seen = 0;
	while (cycles < limit) {
		top->hspi_ack = rx.ack;
		top->eval();
		rx.cycle(top->hspi_req, top->hspi_vld, top->hspi_data, top->hspi_oe);
		uint64_t done = rx.packets + rx.crc_err;
		if (done != seen) {
			if (seen == 0)
				first = cycles;
			last = cycles;
			seen = done;
		}
		tick(top);
		cycles++;
		if (done >= r.packets) {
			top->cfg_enable = 0;
			if (rx.idle())
				break;
		}
	}
	// let the model drain its buffers
	for (int i = 0; i < 4 * (int)r.drain_max + 16; i++) {
		top->hspi_ack = rx.ack;
		top->eval();
		rx.cycle(top->hspi_req, top->hspi_vld, top->hspi_data, top->hspi_oe);
		tick(top);
	}

	o.packets = rx.packets;
	o.crc_err = rx.crc_err;
	o.seq_err = rx.seq_err;
	o.len_err = rx.len_err;
	o.tll_err = rx.tll_err;
	o.proto_err = rx.proto_err;
	o.stalls = rx.stall_cycles;
	o.usdf = rx.last_usdf;
	o.dut_packets = top->cnt_packets;
	o.dut_blocks = top->cnt_blocks;
	if (seen > 1 && last > first)
		o.efficiency = (double)r.block_words * 4 * (seen - 1) / (last - first) / (HSPI_W / 8);
	top->final();
	delete top;
	return o;
}

static void expect_clean(const Out &o, const Run &r)
{
	EXPECT_EQ(o.crc_err, 0u);
	EXPECT_EQ(o.seq_err, 0u);
	EXPECT_EQ(o.len_err, 0u);
	EXPECT_EQ(o.tll_err, 0u);
	EXPECT_EQ(o.proto_err, 0u);
	EXPECT(o.packets >= r.packets);
	EXPECT_EQ(o.chk.blocks, o.packets);
	EXPECT_EQ(check_errors(&o.chk), 0u);
	EXPECT_EQ(o.chk.skipped, 0u);
	EXPECT_EQ(o.chk.block_len, r.block_words * 4);
	EXPECT_EQ(o.usdf, r.usdf);
	EXPECT_EQ(o.dut_packets, o.dut_blocks);
}

int main(int argc, char **argv)
{
	Verilated::commandArgs(argc, argv);
	std::printf("HSPI %d bit, CRC%d init %x reflect %d xorout %x\n", HSPI_W, HSPI_W == 32 ? 32 : 16,
	            (unsigned)HSPI_CRC_INIT, HSPI_CRC_REFLECT, (unsigned)HSPI_CRC_XOROUT);

	std::printf("model CRC against the catalogue check values of \"123456789\"\n");
	{
		const uint8_t *m = (const uint8_t *)"123456789";
		EXPECT_EQ((HspiCrc{16, 0, false, 0}.compute(m, 9)), 0xFEE8u);                       // CRC-16/UMTS
		EXPECT_EQ((HspiCrc{16, 0, true, 0}.compute(m, 9)), 0xBB3Du);                        // CRC-16/ARC
		EXPECT_EQ((HspiCrc{16, 0xFFFF, true, 0xFFFF}.compute(m, 9)), 0xB4C8u);              // CRC-16/USB
		EXPECT_EQ((HspiCrc{32, 0xFFFFFFFF, true, 0xFFFFFFFF}.compute(m, 9)), 0xCBF43926u);  // CRC-32
		EXPECT_EQ((HspiCrc{32, 0xFFFFFFFF, false, 0}.compute(m, 9)), 0x0376E6E7u);          // CRC-32/MPEG-2
	}

	std::printf("full rate, 4096-byte PRBS31 blocks\n");
	{
		Run r;
		Out o = run(r);
		expect_clean(o, r);
		EXPECT_EQ(o.chk.prbs_blocks, o.chk.blocks);
		std::printf("    bus efficiency %.3f\n", o.efficiency);
		EXPECT(o.efficiency > 0.98);
	}

	std::printf("CH569 slow to free buffers, slow to ack: no data lost\n");
	{
		Run r;
		r.kind = STREAM_KIND_WORD;
		r.block_words = 128;
		r.packets = 300;
		r.ack_delay = 12;
		r.drain_min = 0;
		r.drain_max = 3 * (512 / (HSPI_W / 8));
		r.gap = 3;
		r.seed = 2;
		Out o = run(r);
		expect_clean(o, r);
		EXPECT(o.stalls > 0);
	}

	std::printf("bit flip on the bus: CRC drops the packet, the PC sees a lost block\n");
	{
		Run r;
		r.block_words = 256;
		r.packets = 40;
		r.corrupt_wire = 5;
		r.seed = 3;
		Out o = run(r);
		EXPECT_EQ(o.crc_err, 1u);
		EXPECT_EQ(o.seq_err, 0u);
		EXPECT_EQ(o.chk.lost, 1u);
		EXPECT_EQ(o.chk.bad_blocks, 0u);
	}

	std::printf("payload corrupted after the CRC check: the PC sees a bad block\n");
	{
		Run r;
		r.block_words = 256;
		r.packets = 40;
		r.corrupt_payload = 7;
		r.seed = 4;
		Out o = run(r);
		EXPECT_EQ(o.crc_err, 0u);
		EXPECT_EQ(o.chk.bad_blocks, 1u);
		EXPECT_EQ(o.chk.lost, 0u);
	}

	std::printf(g_failed ? "FAILED\n" : "all passed\n");
	return g_failed;
}
