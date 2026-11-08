// dap_uart + dap_core: CMSIS-DAP packets over the serial line against pin-level
// target models. SWD: a DP (DPIDR, CTRL/STAT with power-up acks, SELECT,
// RDBUFF) and a MEM-AP (CSW, TAR with auto-increment, DRW) with posted reads
// and injected WAIT answers. JTAG: a TAP with a 4-bit IR and IDCODE. SWO: a
// UART stream at a rate that does not divide the clock, 2 % off the set one.
//
// SPDX-License-Identifier: BSD-3-Clause
#include <cstdio>
#include <string>
#include <vector>

#include "Vdap_uart.h"
#include "verilated.h"

#include "sim.h"

static const int DIV = 4;               // dap_uart is built with -GDIV=4
typedef std::vector<uint8_t> Bytes;

static Vdap_uart *top;
static long cycles;

// ---------------------------------------------------------------- SWD target
struct Swd {
	enum { IDLE, REQ, TRN, ACK, READ, WTRN, WDATA, TRN2 } ph = IDLE;
	int ones = 0, zeros = 0, n = 0, i = 0;
	bool reset_seen = false, armed = false, oe = false, bit = true;
	uint8_t req = 0;
	int ack = 0;
	uint64_t sh = 0;
	uint32_t data = 0, ctrl = 0, csw = 0, tar = 0, ap_buf = 0;
	int wait_left = 0, waits = 0, faults = 0;
	uint32_t mem[64];

	bool ap() const { return req >> 1 & 1; }
	bool rnw() const { return req >> 2 & 1; }
	int addr() const { return (req >> 3 & 3) << 2; }

	uint32_t read_reg()
	{
		if (!ap()) {
			switch (addr()) {
			case 0x0: return 0x2ba01477;
			case 0x4: return ctrl | (ctrl & 0x50000000u) << 1;
			case 0xC: return ap_buf;
			}
			return 0;
		}
		uint32_t prev = ap_buf;          // posted: this read returns the previous one
		switch (addr()) {
		case 0x0: ap_buf = csw; break;
		case 0x4: ap_buf = tar; break;
		case 0xC:
			ap_buf = mem[(tar >> 2) & 63];
			if ((csw >> 4 & 3) == 1)
				tar += 4;
			break;
		}
		return prev;
	}

	void write_reg(uint32_t v)
	{
		if (!ap()) {
			if (addr() == 0x4)
				ctrl = v;
			return;
		}
		switch (addr()) {
		case 0x0: csw = v; break;
		case 0x4: tar = v; break;
		case 0xC:
			mem[(tar >> 2) & 63] = v;
			if ((csw >> 4 & 3) == 1)
				tar += 4;
			break;
		}
	}

	// a rising SWCLK edge, h = the line as the host leaves it
	void edge(int h)
	{
		// a line reset (50 ones) followed by two idle cycles arms the DP
		ones = h ? ones + 1 : 0;
		if (ones >= 50) {
			reset_seen = true;
			armed = false;
			zeros = 0;
			ph = IDLE;
			oe = false;
			return;
		}
		if (!armed) {
			zeros = h ? 0 : zeros + 1;
			if (reset_seen && zeros >= 2 && ones == 0)
				armed = true;
			if (h)
				reset_seen = false;
			return;
		}
		switch (ph) {
		case IDLE:
			if (h) {
				ph = REQ;
				req = 1;
				n = 1;
			}
			break;
		case REQ:
			req |= h << n;
			if (++n == 8) {
				int par = __builtin_popcount(req >> 1 & 15) & 1;
				if ((req & 1) && !(req >> 6 & 1) && (req >> 7 & 1) && par == (req >> 5 & 1)) {
					ph = TRN;
					n = 1;
				} else
					ph = IDLE;
			}
			break;
		case TRN:
			if (--n == 0) {
				ack = 1;
				if (ap() && wait_left > 0) {
					wait_left--;
					waits++;
					ack = 2;
				}
				ph = ACK;
				i = 0;
				oe = true;
				bit = ack & 1;
			}
			break;
		case ACK:
			if (++i < 3) {
				bit = ack >> i & 1;
				break;
			}
			if (ack == 1 && rnw()) {
				data = read_reg();
				ph = READ;
				i = 0;
				bit = data & 1;
			} else {
				oe = false;
				ph = ack == 1 ? WTRN : TRN2;
				n = 1;
			}
			break;
		case READ:
			i++;
			if (i < 32)
				bit = data >> i & 1;
			else if (i == 32)
				bit = __builtin_popcount(data) & 1;
			else {
				oe = false;
				ph = TRN2;
				n = 1;
			}
			break;
		case WTRN:
			if (--n == 0) {
				ph = WDATA;
				i = 0;
				sh = 0;
			}
			break;
		case WDATA:
			sh |= (uint64_t)h << i;
			if (++i == 33) {
				if ((int)(sh >> 32 & 1) == (__builtin_popcount((uint32_t)sh) & 1))
					write_reg((uint32_t)sh);
				else
					faults++;
				ph = IDLE;
			}
			break;
		case TRN2:
			if (--n == 0)
				ph = IDLE;
			break;
		}
	}
} swd;

// ---------------------------------------------------------------- JTAG TAP
struct Tap {
	enum { TLR, RTI, SELDR, CAPDR, SHDR, EX1DR, PDR, EX2DR, UPDR, SELIR, CAPIR, SHIR, EX1IR, PIR, EX2IR, UPIR };
	int s = TLR;
	uint32_t dr = 0, ir = 1, irs = 0;
	int tdo = 0;

	void edge(int tms, int tdi)
	{
		static const int next[16][2] = {
			{RTI, TLR}, {RTI, SELDR}, {CAPDR, SELIR}, {SHDR, EX1DR}, {SHDR, EX1DR}, {PDR, UPDR}, {PDR, EX2DR}, {SHDR, UPDR},
			{RTI, SELDR}, {CAPIR, TLR}, {SHIR, EX1IR}, {SHIR, EX1IR}, {PIR, UPIR}, {PIR, EX2IR}, {SHIR, UPIR}, {RTI, SELDR}};
		if (s == SHDR)
			dr = dr >> 1 | (uint32_t)tdi << 31;
		if (s == SHIR)
			irs = (irs >> 1 | tdi << 3) & 15;
		s = next[s][tms];
		if (s == TLR)
			ir = 1;
		if (s == CAPDR)
			dr = ir == 1 ? 0x4ba00477 : 0;
		if (s == CAPIR)
			irs = 1;
		if (s == UPIR)
			ir = irs;
		tdo = s == SHDR ? dr & 1 : s == SHIR ? irs & 1 : 0;
	}
} tap;

// SWO transmitter: bytes at `swo_cyc` clock cycles per bit (fractional)
static std::vector<uint8_t> swo_q;
static size_t swo_i;
static double swo_cyc, swo_t = -1;

static int swo_line()
{
	if (swo_t < 0) {
		if (swo_i >= swo_q.size())
			return 1;
		swo_t = 0;
	}
	int bit = (int)(swo_t / swo_cyc);
	swo_t += 1;
	if (bit >= 10) {                    // stop bit done
		swo_i++;
		swo_t = -1;
		return 1;
	}
	unsigned frame = 0x200 | swo_q[swo_i] << 1;
	return frame >> bit & 1;
}

static bool jtag_on;
static int prev_tck;
static std::string got;
static int rx_cnt = -1, rx_bit, rx_prev = 1;
static uint8_t rx_sh;
static std::vector<uint8_t> rx_bytes;

static void step()
{
	tick(top);
	cycles++;
	int line = top->tms_oe ? top->tms : swd.oe ? swd.bit : 1;
	if (top->tms_oe && swd.oe)
		g_failed = 1;                   // both drive SWDIO
	if (top->tck && !prev_tck) {
		if (jtag_on)
			tap.edge(top->tms, top->tdi);
		else
			swd.edge(line);
		line = top->tms_oe ? top->tms : swd.oe ? swd.bit : 1;
	}
	prev_tck = top->tck;
	top->swdio = line;
	top->tdo = tap.tdo;
	top->swo = swo_line();

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
			rx_bytes.push_back(rx_sh);
			rx_cnt = -1;
		} else {
			rx_bit++;
			rx_cnt = DIV;
		}
	}
	rx_prev = tx;
}

static void send(uint8_t c)
{
	unsigned frame = 0x200 | c << 1;
	for (int b = 0; b < 10; b++) {
		top->rxd = frame >> b & 1;
		for (int i = 0; i < DIV; i++)
			step();
	}
	top->rxd = 1;
}

static Bytes dap(const Bytes &req)
{
	rx_bytes.clear();
	send(req.size() & 255);
	send(req.size() >> 8);
	for (uint8_t b : req)
		send(b);
	for (long t = 0; t < 4'000'000; t++) {
		step();
		if (rx_bytes.size() >= 2 && rx_bytes.size() >= 2u + (rx_bytes[0] | rx_bytes[1] << 8))
			break;
	}
	EXPECT(rx_bytes.size() >= 2);
	if (rx_bytes.size() < 2)
		return {};
	return Bytes(rx_bytes.begin() + 2, rx_bytes.end());
}

static void put32(Bytes &b, uint32_t v)
{
	for (int i = 0; i < 4; i++)
		b.push_back(v >> 8 * i);
}

static uint32_t get32(const Bytes &b, size_t at)
{
	return at + 4 <= b.size() ? b[at] | b[at + 1] << 8 | b[at + 2] << 16 | (uint32_t)b[at + 3] << 24 : 0xDEADBEEF;
}

static void expect_bytes(const Bytes &got_, const Bytes &want, const char *what)
{
	if (got_ != want) {
		std::printf("    %s: got", what);
		for (uint8_t b : got_)
			std::printf(" %02x", b);
		std::printf(", want");
		for (uint8_t b : want)
			std::printf(" %02x", b);
		std::printf("\n");
		g_failed = 1;
	}
}

// transfer request bytes: APnDP, RnW, A[3:2]
enum { DP = 0, AP = 1, WR = 0, RD = 2 };
static uint8_t rq(int ap, int rd, int a) { return ap | rd | (a >> 2) << 2; }

int main(int argc, char **argv)
{
	Verilated::commandArgs(argc, argv);
	top = new Vdap_uart;
	top->rxd = 1;
	top->swdio = 1;
	reset(top);
	for (int i = 0; i < 64; i++)
		swd.mem[i] = 0x1000 + i * 0x11;

	expect_bytes(dap({0x00, 0xFF}), {0x00, 0x02, 0x00, 0x02}, "Info packet size");
	expect_bytes(dap({0x00, 0xF0}), {0x00, 0x01, 0x07}, "Info caps");
	expect_bytes(dap({0x00, 0xFD}), {0x00, 0x04, 0x00, 0x20, 0x00, 0x00}, "Info SWO buffer");
	expect_bytes(dap({0x00, 0x04}), {0x00, 0x06, '2', '.', '1', '.', '0', 0}, "Info firmware");
	expect_bytes(dap({0x00, 0x01}), {0x00, 0x00}, "Info vendor");
	expect_bytes(dap({0x42}), {0xFF}, "unknown command");
	expect_bytes(dap({0x02, 0x01}), {0x02, 0x01}, "Connect SWD");
	expect_bytes(dap({0x11, 0x80, 0x96, 0x98, 0x00}), {0x11, 0x00}, "SWJ_Clock 10 MHz");
	expect_bytes(dap({0x04, 0x00, 0x08, 0x00, 0x00, 0x00}), {0x04, 0x00}, "TransferConfigure");

	// line reset, JTAG-to-SWD, line reset, idle
	expect_bytes(dap({0x12, 136, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x9E, 0xE7,
	                  0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00}), {0x12, 0x00}, "SWJ_Sequence");
	EXPECT(swd.armed);

	// DPIDR, power-up, CSW, TAR, four posted DRW reads
	Bytes r = {0x05, 0x00, 10, rq(DP, RD, 0x0), rq(DP, WR, 0x4)};
	put32(r, 0x50000000);
	r.push_back(rq(DP, RD, 0x4));
	r.push_back(rq(AP, WR, 0x0));
	put32(r, 0x23000012);
	r.push_back(rq(AP, WR, 0x4));
	put32(r, 0x20000010);
	for (int i = 0; i < 4; i++)
		r.push_back(rq(AP, RD, 0xC));
	r.push_back(rq(DP, RD, 0x0));
	Bytes a = dap(r);
	EXPECT_EQ(a.size(), 3u + 4 * 7);
	EXPECT_EQ(a[1], 10);
	EXPECT_EQ(a[2], 1);
	EXPECT_EQ(get32(a, 3), 0x2ba01477u);
	EXPECT_EQ(get32(a, 7), 0xF0000000u);
	for (int i = 0; i < 4; i++)
		EXPECT_EQ(get32(a, 11 + 4 * i), swd.mem[4 + i]);
	EXPECT_EQ(get32(a, 27), 0x2ba01477u);

	// writes, then reads ending with a posted one (collected through RDBUFF), WAITs retried
	r = {0x05, 0x00, 7, rq(AP, WR, 0x4)};
	put32(r, 0x20000040);
	r.push_back(rq(AP, WR, 0xC));
	put32(r, 0xCAFE0001);
	r.push_back(rq(AP, WR, 0xC));
	put32(r, 0xCAFE0002);
	r.push_back(rq(AP, WR, 0x4));
	put32(r, 0x20000040);
	swd.wait_left = 3;
	r.push_back(rq(AP, RD, 0xC));
	r.push_back(rq(AP, RD, 0xC));
	r.push_back(rq(AP, RD, 0x4));
	a = dap(r);
	EXPECT_EQ(swd.waits, 3);
	EXPECT_EQ(swd.faults, 0);
	EXPECT_EQ(a.size(), 3u + 4 * 3);
	EXPECT_EQ(a[1], 7);
	EXPECT_EQ(a[2], 1);
	EXPECT_EQ(get32(a, 3), 0xCAFE0001u);
	EXPECT_EQ(get32(a, 7), 0xCAFE0002u);
	EXPECT_EQ(get32(a, 11), 0x20000048u);

	// WAIT longer than the retry count: stops with ack 2
	swd.wait_left = 100;
	a = dap({0x05, 0x00, 2, rq(DP, RD, 0x0), rq(AP, RD, 0xC)});
	EXPECT_EQ(a.size(), 3u + 4);
	EXPECT_EQ(a[1], 1);
	EXPECT_EQ(a[2], 2);
	swd.wait_left = 0;

	// SWD_Sequence: 8 cycles out, 8 cycles in (the line floats high)
	expect_bytes(dap({0x1D, 2, 0x08, 0x00, 0x88}), {0x1D, 0x00, 0xFF}, "SWD_Sequence");

	// SWJ_Pins: nRESET low, then released
	a = dap({0x10, 0x00, 0x80, 0, 0, 0, 0});
	EXPECT_EQ(top->srst, 1);
	EXPECT_EQ(a.size(), 2u);
	dap({0x10, 0x80, 0x80, 0, 0, 0, 0});
	EXPECT_EQ(top->srst, 0);

	// SWO, UART mode: set 2.5 Mbaud, the target sends at 2.55
	expect_bytes(dap({0x17, 0x01}), {0x17, 0x00}, "SWO_Transport");
	expect_bytes(dap({0x18, 0x02}), {0x18, 0xFF}, "SWO_Mode Manchester");
	expect_bytes(dap({0x18, 0x01}), {0x18, 0x00}, "SWO_Mode UART");
	expect_bytes(dap({0x19, 0x80, 0x96, 0x98, 0x00}), {0x19, 0, 0, 0, 0}, "SWO_Baudrate too high");
	expect_bytes(dap({0x19, 0xA0, 0x25, 0x26, 0x00}), {0x19, 0xA0, 0x25, 0x26, 0x00}, "SWO_Baudrate 2.5 M");
	expect_bytes(dap({0x1A, 0x01}), {0x1A, 0x00}, "SWO_Control start");
	Rnd sr(7);
	for (int i = 0; i < 300; i++)
		swo_q.push_back(sr.u32());
	swo_cyc = 27e6 / 2.55e6;
	for (long t = 0; swo_i < swo_q.size() && t < 1'000'000; t++)
		step();
	for (int i = 0; i < 100; i++)
		step();
	expect_bytes(dap({0x1B}), {0x1B, 0x01, 44, 1, 0, 0}, "SWO_Status");
	a = dap({0x1C, 200, 0});
	EXPECT_EQ(a.size(), 4u + 200);
	if (a.size() >= 4) {
		EXPECT_EQ(a[1], 1);
		EXPECT_EQ(a[2] | a[3] << 8, 200);
	}
	Bytes b = dap({0x1C, 0xFF, 0xFF});
	a.insert(a.end(), b.begin() + std::min<size_t>(4, b.size()), b.end());
	expect_bytes(Bytes(a.begin() + std::min<size_t>(4, a.size()), a.end()), swo_q, "SWO_Data");
	expect_bytes(dap({0x1A, 0x00}), {0x1A, 0x00}, "SWO_Control stop");
	expect_bytes(dap({0x1B}), {0x1B, 0x00, 0, 0, 0, 0}, "SWO_Status after stop");

	// JTAG: Test-Logic-Reset, Shift-DR, IDCODE in 31 + 1 bits
	jtag_on = true;
	expect_bytes(dap({0x02, 0x02}), {0x02, 0x02}, "Connect JTAG");
	a = dap({0x14, 6, 0x45, 0x00, 0x01, 0x00, 0x41, 0x00, 0x02, 0x00, 0x80 | 31, 0, 0, 0, 0, 0xC1, 0x00});
	EXPECT_EQ(a.size(), 2u + 4 + 1);
	uint32_t id = (get32(a, 2) & 0x7FFFFFFF) | (uint32_t)(a.size() > 6 ? a[6] & 1 : 0) << 31;
	EXPECT_EQ(id, 0x4ba00477u);
	expect_bytes(dap({0x05, 0x00, 1, rq(DP, RD, 0)}), {0x05, 0x00, 0x00}, "Transfer in JTAG mode");

	std::printf("%ld cycles\n", cycles);
	delete top;
	std::printf("%s\n", g_failed ? "FAIL" : "ok");
	return g_failed;
}
