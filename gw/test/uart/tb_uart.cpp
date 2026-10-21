// uart_hex + uart_tx: packets in, the serial line decoded back to text and
// compared with the hex lines find_crc.py expects.
//
// SPDX-License-Identifier: BSD-3-Clause
#include <string>
#include <vector>

#include "Vuart_hex_top.h"
#include "verilated.h"

#include "sim.h"

static const int DIV = 5;

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
	for (long cyc = 0; cyc < 2'000'000 && got.size() < want.size(); cyc++) {
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
	}
	EXPECT(got == want);
	if (got != want)
		std::printf("    got:\n%s    want:\n%s", got.c_str(), want.c_str());
	delete top;
	std::printf(g_failed ? "FAILED\n" : "all passed\n");
	return g_failed;
}
