#!/usr/bin/env python3
"""CMSIS-DAP packets over a UART to gw/cores/dap_core.sv (Tang Nano 9K, gw/boards/tangnano9k/top_dap.sv):
frames [length, 2 bytes LE][packet] both ways. A bench check against the STM32F4-Discovery:

    dap_uart.py /dev/ttyUSB1                 # SWD: DPIDR, power-up, flash words, RAM read speed; JTAG: IDCODE
    dap_uart.py /dev/ttyUSB1 --clock 3000000 --kib 64

SPDX-License-Identifier: BSD-3-Clause
"""
import argparse
import struct
import sys
import time

import serial

DP, AP, WR, RD = 0, 1, 0, 2


def rq(ap, rd, a):
    return ap | rd | (a >> 2) << 2


class Dap:
    def __init__(self, port, baud):
        for _ in range(3):              # the BL702 sometimes ignores the rate on the first open
            self.s = serial.Serial(port, baud, timeout=0.5)
            self.s.reset_input_buffer()
            try:
                self.size = struct.unpack("<H", self.info(0xFF))[0]
                return
            except IOError:
                self.s.close()
        sys.exit(f"{port}: no answer from dap_core (top_dap loaded?)")

    def cmd(self, pkt):
        self.s.write(struct.pack("<H", len(pkt)) + bytes(pkt))
        hdr = self.s.read(2)
        if len(hdr) < 2:
            raise IOError("no answer")
        n = struct.unpack("<H", hdr)[0]
        r = self.s.read(n)
        if len(r) < n or r[0] != pkt[0]:
            raise IOError(f"bad answer to {pkt[0]:#04x}: {r.hex()}")
        return r

    def info(self, i):
        r = self.cmd([0x00, i])
        return r[2:2 + r[1]]

    def ok(self, pkt):
        r = self.cmd(pkt)
        if r[1] != 0:
            raise IOError(f"command {pkt[0]:#04x}: status {r[1]:#x}")
        return r

    def transfer(self, reqs):
        """reqs: [(request, value or None)] -> read values; raises on a bad ACK."""
        pkt = [0x05, 0, len(reqs)]
        for r, v in reqs:
            pkt.append(r)
            if not r & RD:
                pkt += struct.pack("<I", v)
        r = self.cmd(pkt)
        if r[1] != len(reqs) or r[2] != 1:
            raise IOError(f"transfer: {r[1]} of {len(reqs)} done, ack {r[2]}")
        return list(struct.unpack(f"<{(len(r) - 3) // 4}I", r[3:]))


def swd(d, a):
    print("SWD")
    d.cmd([0x02, 0x01])
    d.ok([0x11] + list(struct.pack("<I", a.clock)))
    d.ok([0x04, 0, 0x40, 0, 0, 0])
    d.ok([0x13, 0x00])
    d.ok([0x12, 136] + [0xFF] * 7 + [0x9E, 0xE7] + [0xFF] * 7 + [0x00])
    dpidr, = d.transfer([(rq(DP, RD, 0), None)])
    print(f"  DPIDR {dpidr:#010x}")
    d.transfer([(rq(DP, WR, 0x0), 0x1E), (rq(DP, WR, 0x8), 0), (rq(DP, WR, 0x4), 0x50000000)])
    st, = d.transfer([(rq(DP, RD, 0x4), None)])
    print(f"  CTRL/STAT {st:#010x}")
    d.transfer([(rq(AP, WR, 0x0), 0x23000012), (rq(AP, WR, 0x4), 0x08000000)])
    w = d.transfer([(rq(AP, RD, 0xC), None)] * 4)
    print("  flash 0x08000000:", " ".join(f"{x:08x}" for x in w))
    idc, = d.transfer([(rq(AP, WR, 0x4), 0xE0042000), (rq(AP, RD, 0xC), None)])
    print(f"  DBGMCU_IDCODE {idc:#010x}")

    per = min((d.size - 3) // 4, 255) // 8 * 8 - 8   # reads per packet, room for the TAR write
    n, data, t = a.kib * 256, [], time.time()
    addr = 0x20000000
    while len(data) < n:
        k = min(per, n - len(data), (0x400 - (addr & 0x3FF)) // 4)  # TAR auto-increment stays in 1 KB
        data += d.transfer([(rq(AP, WR, 0x4), addr)] + [(rq(AP, RD, 0xC), None)] * k)
        addr += 4 * k
    dt = time.time() - t
    print(f"  RAM read {a.kib} KiB in {dt:.2f} s = {a.kib / dt:.1f} KiB/s ({per} words per packet)")
    return dpidr


def jtag(d, a):
    print("JTAG")
    d.cmd([0x02, 0x02])
    d.ok([0x12, 136] + [0xFF] * 7 + [0x3C, 0xE7] + [0xFF] * 8)  # SWJ-DP: SWD -> JTAG, then Test-Logic-Reset
    r = d.ok([0x14, 6, 0x45, 0x00, 0x01, 0x00, 0x41, 0x00, 0x02, 0x00, 0x80 | 31, 0, 0, 0, 0, 0xC1, 0x00])
    lo = struct.unpack("<I", r[2:6])[0] & 0x7FFFFFFF
    idcode = lo | (r[6] & 1) << 31
    print(f"  IDCODE {idcode:#010x}")
    d.ok([0x14, 1, 0x45, 0x00])        # back to Test-Logic-Reset
    return idcode


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("port")
    ap.add_argument("-b", "--baud", type=int, default=3000000)
    ap.add_argument("--clock", type=int, default=1000000, help="SWCLK/TCK, Hz (dap_core caps it at 27 MHz / 8)")
    ap.add_argument("--kib", type=int, default=16, help="RAM to read for the speed test")
    a = ap.parse_args()
    d = Dap(a.port, a.baud)
    print(f"firmware {d.info(0x04)[:-1].decode()}, caps {d.info(0xF0)[0]:#x}, packet {d.size} bytes")
    ok = swd(d, a) == 0x2BA01477
    ok &= jtag(d, a) == 0x4BA00477
    d.cmd([0x02, 0x01])
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
