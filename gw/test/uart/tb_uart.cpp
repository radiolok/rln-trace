// uart_hex + uart_status through uart_mux + uart_tx: packets in, status lines
// started at random, the serial line decoded back to text. Packet lines must
// come out whole and in order, as find_crc.py expects; status lines whole too.
//
// SPDX-License-Identifier: BSD-3-Clause
#include <cstdlib>
#include <string>
#include <vector>

#include "Vuart_hex_top.h"
#include "verilated.h"

#include "sim.h"

static const int DIV = 5;

// all packet text and every started status line received
static bool packets_done(const std::string &got, size_t packet_chars, int status_lines, size_t status_len)
{
	return got.size() >= packet_chars + status_lines * status_len;
}

struct Packet {
	std::vector<uint8_t> bytes;
	bool good;
};

int main(int argc, char **argv)
{
	Verilated::commandArgs(argc, argv);
	Rnd r(1);
	std::vector<Packet> pk;
	for (int i = 0; i < 12; i++) {
		Packet p;
		unsigned n = 4 + r.below(24);
		for (unsigned k = 0; k < n; k++)
			p.bytes.push_back(r.u32());
		p.good = i != 5;
		pk.push_back(p);
	}
	// words as hspi_rx gives them in raw mode: whole words, then {count, leftover}
	struct W {
		uint32_t d;
		bool last, good;
	};
	std::vector<W> words;
	std::string want;
	static const char *hex = "0123456789abcdef";
	for (auto &p : pk) {
		size_t whole = p.bytes.size() / 4 * 4;
		for (size_t i = 0; i < whole; i += 4)
			words.push_back({(uint32_t)(p.bytes[i] | p.bytes[i + 1] << 8 | p.bytes[i + 2] << 16 | p.bytes[i + 3] << 24), false, p.good});
		uint32_t c = 0;
		unsigned left = p.bytes.size() - whole;
		for (unsigned k = 0; k < left; k++)
			c |= (uint32_t)p.bytes[whole + k] << (8 * k);
		words.push_back({c | left << 24, true, p.good});
		for (uint8_t b : p.bytes)
			want += {hex[b >> 4], hex[b & 15]};
		want += p.good ? "\n" : " #bad\n";
	}

	auto *top = new Vuart_hex_top;
	reset(top);
	size_t wi = 0;
	std::string got;
	int prev = 1, cnt = -1, bit = 0;
	uint8_t sh = 0;
	top->status = 0x0123456789ABCDEFull;
	int status_lines = 0;
	std::string want_status = "# 89abcdef 01234567\n";
	for (long cyc = 0; cyc < 4'000'000; cyc++) {
		top->status_start = !top->status_busy && r.pct(1) && status_lines < 8;
		if (top->status_start)
			status_lines++;
		top->in_valid = wi < words.size() && !r.pct(20);
		if (wi < words.size()) {
			top->in_data = words[wi].d;
			top->in_last = words[wi].last;
			top->in_good = words[wi].good;
		}
		top->eval();
		bool fire = top->in_valid && top->in_ready;
		// serial decoder: start bit edge, then sample in the middle of each bit
		int tx = top->txd;
		if (cnt < 0 && prev && !tx) {
			cnt = DIV + DIV / 2;
			bit = 0;
			sh = 0;
		} else if (cnt >= 0 && --cnt == 0) {
			if (bit < 8) {
				sh |= tx << bit;
				bit++;
				cnt = DIV;
			} else {
				EXPECT(tx == 1); // stop bit
				got += (char)sh;
				cnt = -1;
			}
		}
		prev = tx;
		tick(top);
		if (fire)
			wi++;
		if (wi == words.size() && !top->status_busy && cnt < 0 && packets_done(got, want.size(), status_lines, want_status.size()))
			break;
	}
	// split into lines: status lines out, packet lines in order
	std::string packets;
	int status_seen = 0;
	size_t a = 0;
	for (size_t b; (b = got.find('\n', a)) != std::string::npos; a = b + 1) {
		std::string line = got.substr(a, b + 1 - a);
		if (line[0] == '#') {
			EXPECT(line == want_status);
			status_seen++;
		} else {
			packets += line;
		}
	}
	EXPECT(a == got.size());
	EXPECT(packets == want);
	EXPECT_EQ(status_seen, status_lines);
	EXPECT(status_lines > 2);
	if (getenv("TB_DEBUG"))
		std::printf("    status lines %d, chars %zu\n", status_lines, got.size());
	if (packets != want)
		std::printf("    got:\n%s    want:\n%s", got.c_str(), want.c_str());
	delete top;
	std::printf(g_failed ? "FAILED\n" : "all passed\n");
	return g_failed;
}
