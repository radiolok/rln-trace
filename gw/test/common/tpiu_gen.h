// TPIU formatter stream builder and reference ID tracker for the testbenches.
//
// SPDX-License-Identifier: BSD-3-Clause
#pragma once

#include <array>
#include <cstdint>
#include <vector>

#include "sim.h"

using Frame = std::array<uint8_t, 16>;

struct Expected {
	Frame f;
	uint64_t num;
};

// ---------------------------------------------------------------- stream builder

struct Stream {
	std::vector<uint8_t> bytes;
	void sync() { bytes.insert(bytes.end(), {0xFF, 0xFF, 0xFF, 0x7F}); }
	void hsync() { bytes.insert(bytes.end(), {0xFF, 0x7F}); }
	void frame(const Frame &f) { bytes.insert(bytes.end(), f.begin(), f.end()); }
	void raw(std::initializer_list<uint8_t> b) { bytes.insert(bytes.end(), b); }
	void half_frame(const Frame &f, int halfwords) { bytes.insert(bytes.end(), f.begin(), f.begin() + 2 * halfwords); }
};

// A valid formatter frame: even bytes are never 0xFF (ID 0x7F is reserved).
static Frame random_frame(Rnd &r)
{
	Frame f;
	for (int i = 0; i < 16; i++) {
		f[i] = r.u32();
		if (i % 2 == 0 && i < 15)
			while (f[i] == 0xFF)
				f[i] = r.u32();
	}
	return f;
}

// Frame with data for source `id`: ID change to id at byte 0, then data.
static Frame id_frame(Rnd &r, uint8_t id)
{
	Frame f = random_frame(r);
	f[0] = (uint8_t)(id << 1 | 1);
	f[15] &= 0x7E; // aux bit 0 clear: change is immediate; bit 7 clear
	for (int i = 2; i < 15; i += 2)
		f[i] &= 0xFE; // data, not ID changes
	return f;
}

// LSB-first bit stream of the bytes after `offset` garbage bits; bit positions
// listed in `slips` (counted in the bytes, before the offset) are left out.
static std::vector<uint8_t> to_bits(const std::vector<uint8_t> &bytes, unsigned offset, Rnd &r,
                                    const std::vector<size_t> &slips = {})
{
	std::vector<uint8_t> bits;
	for (unsigned i = 0; i < offset; i++)
		bits.push_back(r.u32() & 1);
	for (size_t i = 0; i < bytes.size(); i++)
		for (int b = 0; b < 8; b++) {
			bool slipped = false;
			for (size_t s : slips)
				if (s == i * 8 + b)
					slipped = true;
			if (!slipped)
				bits.push_back(bytes[i] >> b & 1);
		}
	return bits;
}

// The bit stream in 32-bit words, bit 0 earliest, zero-padded.
static std::vector<uint32_t> pack(const std::vector<uint8_t> &bytes, unsigned offset, Rnd &r,
                                  const std::vector<size_t> &slips = {})
{
	std::vector<uint8_t> bits = to_bits(bytes, offset, r, slips);
	while (bits.size() % 32)
		bits.push_back(0);
	std::vector<uint32_t> words(bits.size() / 32, 0);
	for (size_t i = 0; i < bits.size(); i++)
		words[i / 32] |= (uint32_t)bits[i] << (i % 32);
	return words;
}

// ---------------------------------------------------------------- reference ID tracker

struct IdState {
	uint8_t cur = 0, pend = 0;
	bool pend_v = false;
	bool operator==(const IdState &o) const { return cur == o.cur && pend_v == o.pend_v && (!pend_v || pend == o.pend); }
};

// true if the frame is idle (all data under ID 0, state unchanged); updates st
static bool idle_frame(const Frame &f, IdState &st)
{
	IdState before = st;
	bool busy = false;
	for (int i = 0; i < 15; i++) {
		if (i % 2 == 0 && (f[i] & 1)) {
			uint8_t id = f[i] >> 1;
			if (f[15] >> (i / 2) & 1) {
				st.pend = id;
				st.pend_v = true;
			} else {
				st.cur = id;
			}
		} else {
			if (st.cur)
				busy = true;
			if (st.pend_v) {
				st.cur = st.pend;
				st.pend_v = false;
			}
		}
	}
	return !busy && st == before;
}
