// Cycle model of the CH569 HSPI transmit side (CH569/565 datasheet V1.0, ch. 10),
// clocked by its own HTCLK.
//
// HTREQ up; wait for HTRDY; at least 10 cycles to fill the FIFO; header,
// payload, CRC with HTVLD, which drops at random inside the packet (FIFO
// empty); HTREQ and HTVLD down; a gap. The packet number counts every packet
// sent (no hardware ACK mode).
//
// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <cstdint>
#include <deque>
#include <vector>

#include "ch569_hspi.h"
#include "sim.h"

struct HspiPacket {
	std::vector<uint8_t> payload;
	uint32_t usdf = 0;
	bool flip_bit = false;   // one bit flipped on the bus
	bool skip_seq = false;   // the packet number jumps by one before this packet
	unsigned tll = 0;        // TLL2B in the header
	std::vector<uint8_t> wire; // filled when sent: header + payload + CRC as on the bus
};

struct Ch569HspiTx {
	int width = 16;
	HspiCrc crc{16, 0, false, 0};
	unsigned vld_gap_pct = 10;   // chance of HTVLD low on a cycle inside a packet
	unsigned gap_max = 6;

	bool req = false, vld = false;
	uint32_t data = 0;

	std::deque<HspiPacket> queue;
	std::vector<HspiPacket> sent;

	explicit Ch569HspiTx(uint32_t seed) : rnd(seed) {}

	// Call once per HTCLK cycle with HTRDY sampled before the edge; sets the
	// outputs for the next cycle.
	void cycle(bool rdy)
	{
		switch (st) {
		case IDLE:
			if (wait) {
				wait--;
			} else if (!queue.empty()) {
				req = true;
				st = WAIT_RDY;
			}
			break;
		case WAIT_RDY:
			if (rdy) {
				wait = 10 + rnd.below(6);
				st = PREP;
				build();
			}
			break;
		case PREP:
			if (wait)
				wait--;
			else
				st = SEND;
			break;
		case SEND:
			if (pos < beats.size() && !rnd.pct(vld_gap_pct)) {
				vld = true;
				data = beats[pos++];
				return;
			}
			if (pos == beats.size()) {
				req = false;
				vld = false;
				sent.push_back(std::move(queue.front()));
				queue.pop_front();
				wait = rnd.below(gap_max + 1);
				st = IDLE;
				return;
			}
			break;
		}
		vld = false;
	}

	bool idle() const { return st == IDLE && queue.empty(); }

private:
	enum { IDLE, WAIT_RDY, PREP, SEND } st = IDLE;
	Rnd rnd;
	unsigned wait = 0, seq = 0;
	size_t pos = 0;
	std::vector<uint32_t> beats;

	void build()
	{
		HspiPacket &p = queue.front();
		if (p.skip_seq)
			seq = (seq + 1) & 15;
		uint32_t hdr = (p.tll & 3u) << 30 | (seq & 15u) << 26 | (p.usdf & 0x3FFFFFFu);
		seq = (seq + 1) & 15;
		std::vector<uint8_t> b = {(uint8_t)hdr, (uint8_t)(hdr >> 8), (uint8_t)(hdr >> 16), (uint8_t)(hdr >> 24)};
		b.insert(b.end(), p.payload.begin(), p.payload.end());
		uint32_t c = crc.compute(b.data(), b.size());
		for (int i = 0; i < crc.width / 8; i++)
			b.push_back(c >> (8 * i));
		if (p.flip_bit)
			b[4 + b.size() / 3] ^= 0x10;
		p.wire = b;
		beats.clear();
		for (size_t i = 0; i < b.size(); i += width / 8) {
			uint32_t v = 0;
			for (int k = 0; k < width / 8 && i + k < b.size(); k++)
				v |= (uint32_t)b[i + k] << (8 * k);
			beats.push_back(v);
		}
		pos = 0;
	}
};
