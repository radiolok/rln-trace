// Cycle model of the CH569 HSPI receive side (CH569/565 datasheet V1.0, ch. 10),
// clocked by the FPGA clock (HRCLK).
//
// Two DMA buffers (RX_TOG_EN). On a request (HRACT) the model raises HTACK
// after ack_delay cycles if a buffer is free, otherwise it waits until the
// "firmware" empties one; draining a buffer takes a random time, like the USB
// side would. While HRVLD is high a beat is sampled each cycle. When HRACT
// falls the packet is checked: header, CRC, packet number, length, and the
// payload goes to the buffer. A buffer delivers its payload to `sink` when it
// is drained, so the payload order is the packet order.
//
// The CRC here is written independently of the RTL: the reflected variant is
// the LSB-first loop with the reflected polynomial.
//
// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <algorithm>
#include <cstdint>
#include <deque>
#include <functional>
#include <vector>

#include "sim.h"

struct HspiCrc {
	int width;          // 16 or 32
	uint32_t init;
	bool reflect;
	uint32_t xorout;

	uint32_t mask() const { return width == 32 ? 0xFFFFFFFFu : 0xFFFFu; }
	uint32_t poly() const { return width == 32 ? 0x04C11DB7u : 0x8005u; }

	static uint32_t reflect_bits(uint32_t v, int n)
	{
		uint32_t r = 0;
		for (int i = 0; i < n; i++)
			if (v >> i & 1)
				r |= 1u << (n - 1 - i);
		return r;
	}

	uint32_t compute(const uint8_t *p, size_t n) const
	{
		uint32_t c;
		if (reflect) {
			uint32_t rp = reflect_bits(poly(), width);
			c = reflect_bits(init, width);
			for (size_t i = 0; i < n; i++) {
				c ^= p[i];
				for (int b = 0; b < 8; b++)
					c = (c & 1) ? (c >> 1) ^ rp : c >> 1;
			}
		} else {
			uint32_t top = 1u << (width - 1);
			c = init;
			for (size_t i = 0; i < n; i++) {
				c ^= (uint32_t)p[i] << (width - 8);
				for (int b = 0; b < 8; b++)
					c = (c & top) ? (c << 1) ^ poly() : c << 1;
				c &= mask();
			}
		}
		return (c ^ xorout) & mask();
	}
};

struct Ch569HspiRx {
	// config
	int width = 16;                 // bus bits: 8, 16, 32
	HspiCrc crc{16, 0, false, 0};
	unsigned ack_delay_max = 4;     // cycles from request to HTACK
	unsigned drain_min = 0, drain_max = 0; // cycles to empty a buffer
	int corrupt_payload_at = -1;    // packet index: flip a payload bit after the CRC check
	int corrupt_wire_at = -1;       // packet index: flip a bit on the bus (CRC must catch it)
	std::function<void(const uint8_t *, size_t)> sink;

	// output to the DUT
	bool ack = false;

	// statistics
	uint64_t packets = 0, bytes = 0;
	uint64_t crc_err = 0, seq_err = 0, len_err = 0, tll_err = 0, proto_err = 0;
	uint64_t stall_cycles = 0;      // request waiting for a free buffer
	uint32_t last_usdf = 0;

	explicit Ch569HspiRx(uint32_t seed) : rnd(seed) {}

	// Call once per cycle with the DUT outputs sampled before the clock edge.
	void cycle(bool req, bool vld, uint32_t data, bool oe)
	{
		drain();
		switch (st) {
		case IDLE:
			if (vld)
				proto_err++; // data without a granted request
			if (req) {
				if (free_buffers() > 0) {
					wait = rnd.below(ack_delay_max + 1);
					st = GRANT;
				} else {
					stall_cycles++;
				}
			}
			break;
		case GRANT:
			if (!req) {
				proto_err++;
				st = IDLE;
			} else if (wait == 0) {
				ack = true;
				beats.clear();
				st = RECV;
			} else {
				wait--;
			}
			if (vld)
				proto_err++;
			break;
		case RECV:
			if (vld && !oe)
				proto_err++;
			if (!req) {
				ack = false;
				finish();
				st = IDLE;
			} else if (vld) {
				uint32_t mask = width == 32 ? 0xFFFFFFFFu : (1u << width) - 1;
				beats.push_back(data & mask);
			}
			break;
		}
	}

	bool idle() const { return st == IDLE && full.empty(); }

private:
	enum { IDLE, GRANT, RECV } st = IDLE;
	Rnd rnd;
	unsigned wait = 0;
	unsigned expected_seq = 0;
	std::vector<uint32_t> beats;

	struct Buffer {
		std::vector<uint8_t> payload;
		uint64_t ready_at;
	};
	std::deque<Buffer> full;
	uint64_t now = 0;

	int free_buffers() const { return 2 - (int)full.size(); }

	void drain()
	{
		now++;
		while (!full.empty() && full.front().ready_at <= now) {
			if (sink)
				sink(full.front().payload.data(), full.front().payload.size());
			full.pop_front();
		}
	}

	void finish()
	{
		std::vector<uint8_t> b;
		for (uint32_t v : beats)
			for (int i = 0; i < width / 8; i++)
				b.push_back(v >> (8 * i));
		uint64_t index = packets + crc_err + seq_err + len_err + tll_err;
		if ((int64_t)index == corrupt_wire_at && b.size() > 8)
			b[6] ^= 0x04;

		size_t crc_bytes = crc.width / 8;
		if (b.size() < 4 + crc_bytes + 1 || b.size() - 4 - crc_bytes > 4096) {
			len_err++;
			return;
		}
		uint32_t hdr = b[0] | b[1] << 8 | b[2] << 16 | (uint32_t)b[3] << 24;
		size_t body = b.size() - crc_bytes;
		uint32_t got = 0;
		for (size_t i = 0; i < crc_bytes; i++)
			got |= (uint32_t)b[body + i] << (8 * i);
		if (crc.compute(b.data(), body) != got) {
			// the packet is lost; the transmitter has counted it, so the number moves on
			crc_err++;
			expected_seq = (expected_seq + 1) & 15;
			return;
		}
		if (hdr >> 30) {
			tll_err++;
			return;
		}
		unsigned tsqn = hdr >> 26 & 15;
		if (tsqn != expected_seq) {
			seq_err++;
			expected_seq = (tsqn + 1) & 15;
			return;
		}
		expected_seq = (expected_seq + 1) & 15;
		last_usdf = hdr & 0x3FFFFFF;

		Buffer buf;
		buf.payload.assign(b.begin() + 4, b.begin() + body);
		if ((int64_t)packets == corrupt_payload_at)
			buf.payload[buf.payload.size() / 2] ^= 0x01;
		// the firmware empties the buffers one after the other
		unsigned d = drain_max > drain_min ? drain_min + rnd.below(drain_max - drain_min + 1) : drain_min;
		uint64_t from = full.empty() ? now : std::max(now, full.back().ready_at);
		buf.ready_at = from + d;
		bytes += buf.payload.size();
		packets++;
		full.push_back(std::move(buf));
	}
};
