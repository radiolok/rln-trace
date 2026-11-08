// rbb_uart: remote_bitbang bytes on the serial line in, pins and answers out.
// The sender runs one cycle per bit faster than the receiver, so the answer
// queue fills up during a long run of 'R'.
//
// SPDX-License-Identifier: BSD-3-Clause
#include <string>

#include "Vrbb_uart.h"
#include "verilated.h"

#include "sim.h"

static const int DIV = 32;              // rbb_uart is built with -GDIV=32
static const int HOST_DIV = DIV - 1;

static Vrbb_uart *top;
static std::string got;
static int rx_cnt = -1, rx_bit, rx_prev = 1;
static uint8_t rx_sh;

// one cycle plus the decoder of txd (8N1, sampled in the middle of each bit)
static void step()
{
	tick(top);
	int tx = top->txd;
	if (rx_cnt < 0) {
		if (rx_prev && !tx) {
			rx_cnt = DIV / 2;
			rx_bit = 0;
		}
	} else if (--rx_cnt == 0) {
		if (rx_bit >= 1 && rx_bit <= 8)
			rx_sh = rx_sh >> 1 | tx << 7;
		if (rx_bit == 9) {
			EXPECT(tx == 1);
			got += (char)rx_sh;
			rx_cnt = -1;
		} else {
			rx_bit++;
			rx_cnt = DIV;
		}
	}
	rx_prev = tx;
}

static void send(char c)
{
	unsigned frame = 0x200 | (uint8_t)c << 1;
	for (int b = 0; b < 10; b++) {
		top->rxd = frame >> b & 1;
		for (int i = 0; i < HOST_DIV; i++)
			step();
	}
}

static void idle(int n)
{
	top->rxd = 1;
	for (int i = 0; i < n; i++)
		step();
}

int main(int argc, char **argv)
{
	Verilated::commandArgs(argc, argv);
	top = new Vrbb_uart;
	top->rxd = 1;
	top->tdo = 0;
	reset(top);

	EXPECT_EQ(top->tms, 1);
	EXPECT_EQ(top->tck, 0);
	for (int v = 0; v < 8; v++) {
		send('0' + v);
		idle(4);
		EXPECT_EQ(top->tck << 2 | top->tms << 1 | top->tdi, v);
	}
	for (int v = 0; v < 4; v++) {
		send('r' + v);
		idle(4);
		EXPECT_EQ(top->trst << 1 | top->srst, v);
	}
	send('B');
	idle(4);
	EXPECT_EQ(top->led, 1);
	send('b');
	send('Q');
	send('Z');
	idle(4);
	EXPECT_EQ(top->led, 0);
	EXPECT_EQ(top->tck << 2 | top->tms << 1 | top->tdi, 7);
	EXPECT(got.empty());

	// back-to-back reads, TDO changed between them as OpenOCD would after a TCK edge
	Rnd r(3);
	std::string want;
	for (int i = 0; i < 64; i++) {
		int t = r.pct(50);
		top->tdo = t;
		send(i % 3 ? '4' + (i & 3) : '2');
		send('R');
		want += t ? '1' : '0';
	}
	idle(DIV * 10 * 20);
	EXPECT(got == want);
	if (got != want)
		std::printf("    got  %s\n    want %s\n", got.c_str(), want.c_str());

	delete top;
	std::printf("%s\n", g_failed ? "FAIL" : "ok");
	return g_failed;
}
