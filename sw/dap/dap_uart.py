#!/usr/bin/env python3
"""CMSIS-DAP packets over a UART to gw/cores/dap_core.sv (Tang Nano 9K, gw/boards/tangnano9k/top_dap.sv):
frames [length, 2 bytes LE][packet] both ways. A bench check against the STM32F4-Discovery:

    dap_uart.py /dev/ttyUSB1                 # SWD: DPIDR, power-up, flash words, RAM read speed; JTAG: IDCODE
    dap_uart.py /dev/ttyUSB1 --clock 3000000 --kib 64
    dap_uart.py /dev/ttyUSB1 --swo 1000000 -s 5   # SWO: the demo firmware's ITM counter over PB3, continuity check

SPDX-License-Identifier: BSD-3-Clause
"""
import argparse
import struct
import sys
import time

import serial

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), "../../au/slogic16u3-trace/tools"))

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


def swd_connect(d, a):
    d.cmd([0x02, 0x01])
    d.ok([0x11] + list(struct.pack("<I", a.clock)))
    d.ok([0x04, 0, 0xFF, 0xFF, 0, 0])   # WAIT retries: the demo firmware may run HCLK at 31 kHz
    d.ok([0x13, 0x00])
    d.ok([0x12, 136] + [0xFF] * 7 + [0x9E, 0xE7] + [0xFF] * 7 + [0x00])
    dpidr, = d.transfer([(rq(DP, RD, 0), None)])
    print(f"  DPIDR {dpidr:#010x}")
    d.transfer([(rq(DP, WR, 0x0), 0x1E), (rq(DP, WR, 0x8), 0), (rq(DP, WR, 0x4), 0x50000000)])
    return dpidr


def rd32(d, addr):
    return d.transfer([(rq(AP, WR, 0x0), 0x23000002), (rq(AP, WR, 0x4), addr), (rq(AP, RD, 0xC), None)])[0]


def wr32(d, addr, v):
    d.transfer([(rq(AP, WR, 0x0), 0x23000002), (rq(AP, WR, 0x4), addr), (rq(AP, WR, 0xC), v)])


def swd(d, a):
    print("SWD")
    dpidr = swd_connect(d, a)
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


CFG = 0x20000000        # struct cfg of tools/targets/stm32f407/main.c
HCLK = 16000000         # HSI / 1


def swo(d, a):
    """The demo firmware to HSI / 1 without ETM, TPIU to SWO (NRZ, formatter bypass: ITM only), capture."""
    import tpiu_decode as tp
    print("SWO")
    swd_connect(d, a)
    if rd32(d, CFG) != 0x544E4C52 or rd32(d, 0xE000EDF0) & 1 << 17:
        # halted, or cfg overwritten (an OpenOCD working area lives at 0x20000000): run the firmware from reset
        print("  core halted or cfg lost: reset")
        wr32(d, 0xE000EDF0, 0xA05F0000)                      # DHCSR: debug off, the core runs
        d.cmd([0x10, 0x00, 0x80, 0, 0, 0, 0])                # nRESET low
        time.sleep(0.05)
        d.cmd([0x10, 0x80, 0x80, 0, 0, 0, 0])
        time.sleep(0.2)
        swd_connect(d, a)
        if rd32(d, CFG) != 0x544E4C52:
            sys.exit("no demo firmware cfg at 0x20000000")
    seq = rd32(d, CFG + 4) + 1
    for off, v in ((0x08, 0), (0x10, 1), (0x14, 4), (0x38, 0), (0x04, seq)):  # src HSI, hdiv 1, width 4, no ETM
        wr32(d, CFG + off, v)
    t = time.time()
    while rd32(d, CFG + 0x20) != seq:
        if time.time() - t > 2:
            sys.exit("the firmware did not apply the new mode")
    acpr = round(HCLK / a.swo) - 1
    wr32(d, 0xE0040010, acpr)                                # TPI_ACPR: SWO = HCLK / (ACPR + 1)
    wr32(d, 0xE00400F0, 2)                                   # TPI_SPPR: NRZ
    wr32(d, 0xE0040304, 0x100)                               # TPI_FFCR: formatter bypassed
    wr32(d, 0xE0042004, rd32(d, 0xE0042004) & ~0xC0)         # DBGMCU_CR: TRACE_MODE async, TRACE_IOEN kept
    baud = HCLK / (acpr + 1)
    d.ok([0x17, 1])
    d.ok([0x18, 1])
    r = d.cmd([0x19] + list(struct.pack("<I", int(baud))))
    if struct.unpack("<I", r[1:5])[0] == 0:
        sys.exit(f"SWO {baud:g} baud not supported")
    d.ok([0x1A, 1])
    data, over, t = bytearray(), False, time.time()
    while time.time() - t < a.seconds:
        r = d.cmd([0x1C, 0xFF, 0xFF])
        over |= bool(r[1] & 0x80)
        data += r[4:4 + (r[2] | r[3] << 8)]
    dt = time.time() - t
    d.ok([0x1A, 0])
    vals, st = tp.itm(bytes(data))
    gaps = tp.gaps_of(vals)
    print(f"  SWO {baud / 1e6:g} Mbaud (ACPR {acpr}): {len(data)} bytes in {dt:.2f} s = {len(data) / dt / 1e3:.1f} kB/s, "
          f"buffer overrun: {over}")
    print(f"  ITM: {len(vals)} values" + (f" {vals[0]:#x}..{vals[-1]:#x}" if vals else "") +
          f", gaps {len(gaps)}, other packets {st}")
    for x, y in gaps[:5]:
        print(f"    gap {x:#x} -> {y:#x}")
    return bool(vals) and not gaps and not over


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("port")
    ap.add_argument("-b", "--baud", type=int, default=3000000)
    ap.add_argument("--clock", type=int, default=1000000, help="SWCLK/TCK, Hz (dap_core caps it at 27 MHz / 8)")
    ap.add_argument("--kib", type=int, default=16, help="RAM to read for the speed test")
    ap.add_argument("--swo", type=int, metavar="BAUD", help="SWO test at this rate instead (HCLK 16 MHz / n)")
    ap.add_argument("-s", "--seconds", type=float, default=3.0, help="SWO capture time")
    a = ap.parse_args()
    d = Dap(a.port, a.baud)
    print(f"firmware {d.info(0x04)[:-1].decode()}, caps {d.info(0xF0)[0]:#x}, packet {d.size} bytes, "
          f"SWO buffer {struct.unpack('<I', d.info(0xFD))[0]} bytes")
    if a.swo:
        ok = swo(d, a)
        print("PASS" if ok else "FAIL")
        return 0 if ok else 1
    ok = swd(d, a) == 0x2BA01477
    ok &= jtag(d, a) == 0x4BA00477
    d.cmd([0x02, 0x01])
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
