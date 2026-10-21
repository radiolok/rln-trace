#!/usr/bin/env python3
"""SLogic16U3 в режиме обновления (DFU, 359f:30f1): чтение SPI-флеш ПЛИС.

В DFU прибор отдаёт мост USB-SPI к конфигурационной флеш (bulk OUT/IN на
интерфейсе 0). Протокол взят из веб-прошивальщика Sipeed
(github.com/sipeed/slogic_ota_server, src/spi.js и src/flash.js):
пакет [u32 команда][u32 длина][данные], блок из десяти регистров u32
SPI-мастера (раскладка как у ATCSPI200).

Утилита только читает: ID и UID флеш, дамп, карта занятых блоков 64 КиБ.

    python3 tools/slogic/slogic_dfu.py id
    python3 tools/slogic/slogic_dfu.py dump slogic16u3-factory.bin

Нужен pyusb (pip install pyusb) и доступ к 359f:30f1 (udev-правило из
README прошивальщика). Вход в DFU: кнопка MODE, индикатор мигает красным.
"""

import argparse
import hashlib
import struct
import sys
import time

import usb.core
import usb.util

VID, PID_DFU = 0x359F, 0x30F1

CMD_SET_REGISTER = 0x00020000
CMD_READ_REGISTER = 0x00020001
CMD_READ_DATA = 0x00020002
REGS = 40

W_CONTROL, W_TRANSFER_FORMAT, W_TRANSFER_CONTROL = 0, 1, 2
W_TIMING, W_CONFIGURATION, W_STATUS = 4, 6, 7

MODE_WRITE_READ, MODE_WRITE_ONLY, MODE_READ_ONLY = 0x3, 0x1, 0x2
MODE_WRITE_DUMMY_READ, MODE_NO_DATA = 0x5, 0x7

READ_CHUNK = 64  # как у прошивальщика для 16U3; FIFO моста маленький
BLOCK = 0x10000


def default_regs():
    w = [0] * 10
    w[W_TRANSFER_FORMAT] = (0x2 << 16) | (0x7 << 8) | (1 << 7)
    w[W_TIMING] = (0x2 << 8) | 0xFF
    w[W_CONFIGURATION] = (0x6 << 4) | 0x6
    w[W_STATUS] = (1 << 22) | (1 << 14)
    return w


def transfer_control(mode, wr=0, rd=0, dummy=0):
    return ((mode & 0xF) << 24) | ((wr & 0x1FF) << 12) | ((dummy & 0x3) << 9) | (rd & 0x1FF)


class Bridge:
    def __init__(self, dev, timeout_ms=1000):
        self.dev = dev
        self.timeout = timeout_ms
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
        dev.set_configuration()
        usb.util.claim_interface(dev, 0)
        intf = dev.get_active_configuration()[(0, 0)]
        is_bulk = lambda e: usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
        self.ep_out = next(e for e in intf if is_bulk(e) and
                           usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        self.ep_in = next(e for e in intf if is_bulk(e) and
                          usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)

    def _send(self, cmd, data=b""):
        pkt = struct.pack("<II", cmd, len(data)) + data
        n = self.ep_out.write(pkt, self.timeout)
        if n != len(pkt):
            raise IOError(f"короткая запись {n}/{len(pkt)}")

    def _recv(self, n):
        mps = self.ep_in.wMaxPacketSize or 64
        size = -(-n // mps) * mps
        return bytes(self.ep_in.read(size, self.timeout))[:n]

    def read_regs(self):
        self._send(CMD_READ_REGISTER)
        raw = self._recv(REGS)
        if len(raw) < REGS:
            raise IOError(f"короткое чтение регистров ({len(raw)} байт)")
        return struct.unpack("<10I", raw)

    def set_regs(self, w, payload=b""):
        self._send(CMD_SET_REGISTER, struct.pack("<10I", *w) + payload)

    def assert_idle(self):
        st = self.read_regs()[W_STATUS]
        if st & 1 or not (st >> 14) & 1:
            raise IOError(f"мост SPI не свободен (status 0x{st:08x})")

    def reset(self):
        w = default_regs()
        w[W_CONTROL] = 0b111
        w[W_TRANSFER_CONTROL] = transfer_control(MODE_NO_DATA)
        self.set_regs(w)

    def xfer(self, wr, rd_n=0, dummy=0):
        wr_n = len(wr)
        pad = (4 - wr_n % 4) % 4
        tx = bytes(wr) + b"\xff" * pad
        if rd_n == 0:
            tc = transfer_control(MODE_WRITE_ONLY, wr_n - 1)
        elif wr_n == 0:
            tc = transfer_control(MODE_READ_ONLY, rd=rd_n - 1)
        elif dummy <= pad:
            tc = transfer_control(MODE_WRITE_READ, wr_n - 1 + dummy, rd_n - 1)
        else:
            tc = transfer_control(MODE_WRITE_DUMMY_READ, wr_n - 1 + pad, rd_n - 1, dummy - 1 - pad)
        w = default_regs()
        w[W_TRANSFER_CONTROL] = tc
        self.set_regs(w, tx)
        data = b""
        if rd_n:
            self._send(CMD_READ_DATA)
            data = self._recv(rd_n)
        self.assert_idle()
        return data


def open_flash():
    dev = usb.core.find(idVendor=VID, idProduct=PID_DFU)
    if dev is None:
        sys.exit("нет 359f:30f1: переведите прибор в DFU кнопкой MODE (мигает красным)")
    b = Bridge(dev)
    b.reset()
    jid = b.xfer(b"\x9f", 3)
    if jid in (b"\xff\xff\xff", b"\x00\x00\x00"):
        b.reset()
        jid = b.xfer(b"\x9f", 3)
        if jid in (b"\xff\xff\xff", b"\x00\x00\x00"):
            sys.exit(f"флеш не отвечает (JEDEC ID {jid.hex()})")
    uid = b.xfer(b"\x4b", 16, 4)
    cap = 2 ** jid[2] if 16 <= jid[2] <= 28 else 0
    return b, jid, uid, cap


def read(b, addr, n):
    out = bytearray()
    t0 = time.time()
    while len(out) < n:
        a = addr + len(out)
        need = min(READ_CHUNK, n - len(out))
        part = b.xfer(bytes([0x0B, a >> 16 & 0xFF, a >> 8 & 0xFF, a & 0xFF]), need, 1)
        if len(part) != need:
            raise IOError(f"короткое чтение по 0x{a:06x}")
        out += part
        if len(out) % BLOCK == 0 or len(out) == n:
            rate = len(out) / max(time.time() - t0, 1e-3) / 1024
            print(f"\r  0x{len(out):06x}/0x{n:06x}  {rate:.0f} КиБ/с", end="", file=sys.stderr)
    print(file=sys.stderr)
    return bytes(out)


def block_map(img):
    """Занятые блоки 64 КиБ: (начало, конец, байт не 0xFF)."""
    runs, start = [], None
    for off in range(0, len(img), BLOCK):
        used = img[off:off + BLOCK].count(0xFF) != min(BLOCK, len(img) - off)
        if used and start is None:
            start = off
        if not used and start is not None:
            runs.append((start, off))
            start = None
    if start is not None:
        runs.append((start, len(img)))
    return runs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("id", help="JEDEC ID, UID и объём флеш")
    d = sub.add_parser("dump", help="прочитать флеш в файл")
    d.add_argument("out")
    d.add_argument("--size", type=lambda s: int(s, 0), help="сколько байт (по умолчанию весь объём)")
    a = ap.parse_args()

    b, jid, uid, cap = open_flash()
    print(f"JEDEC ID {jid.hex()}  UID {uid.hex()}  объём {cap // 1024} КиБ" if cap else
          f"JEDEC ID {jid.hex()}  UID {uid.hex()}  объём не опознан")
    if a.cmd == "id":
        return
    size = a.size or cap
    if not size:
        sys.exit("объём не опознан, задайте --size")
    img = read(b, 0, size)
    with open(a.out, "wb") as f:
        f.write(img)
    print(f"{a.out}: {len(img)} байт, sha256 {hashlib.sha256(img).hexdigest()}")
    for s, e in block_map(img):
        print(f"  занято 0x{s:06x}..0x{e:06x} ({(e - s) // 1024} КиБ)")


if __name__ == "__main__":
    main()
