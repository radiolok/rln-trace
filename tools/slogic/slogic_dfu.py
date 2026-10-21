#!/usr/bin/env python3
"""SLogic16U3 в режиме обновления (DFU, 359f:30f1): чтение SPI-флеш ПЛИС.

В DFU прибор отдаёт мост USB-SPI к конфигурационной флеш (bulk OUT/IN на
интерфейсе 0). Протокол взят из веб-прошивальщика Sipeed
(github.com/sipeed/slogic_ota_server, src/spi.js и src/flash.js):
пакет [u32 команда][u32 длина][данные], блок из десяти регистров u32
SPI-мастера (раскладка как у ATCSPI200).

ID и UID флеш, дамп, карта занятых блоков 64 КиБ, запись основного образа.

    python3 tools/slogic/slogic_dfu.py id
    python3 tools/slogic/slogic_dfu.py dump slogic16u3-factory.bin
    python3 tools/slogic/slogic_dfu.py write probe.bin --backup slogic16u3-factory.bin
    python3 tools/slogic/slogic_dfu.py restore slogic16u3-factory.bin

Раскладка флеш (16 МиБ): 0x000000 — приложение (первая загрузка ПЛИС),
0x800000 — золотой образ, он же загрузчик DFU: GW5A грузит его сам, если
образ по 0x0 не прошёл проверку (UG704, 3.6.3). Запись в область от 0x800000
утилита не делает никогда — это единственный путь восстановления без JTAG.

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
WRITE_CHUNK = 12  # у 16U3 FIFO моста сбоит уже на 16 байтах (devices.js)
BLOCK = 0x10000
PAGE = 0x100
GOLDEN = 0x800000


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


def wait_wip(b, timeout_s=5.0):
    t0 = time.time()
    while True:
        sr = b.xfer(b"\x05", 1)[0]
        if sr == 0xFF:
            raise IOError("статус флеш 0xFF: шина SPI не отвечает")
        if not sr & 1:
            return
        if time.time() - t0 > timeout_s:
            raise IOError("флеш не закончила запись вовремя")


def with_wren(b, op):
    b.xfer(b"\x06")
    try:
        op()
    except Exception:
        b.xfer(b"\x04")
        raise
    wait_wip(b)
    b.xfer(b"\x04")


def a24(a):
    return bytes([a >> 16 & 0xFF, a >> 8 & 0xFF, a & 0xFF])


def write_main(b, img):
    """Стереть всю основную область, записать и сверить img с адреса 0x0.

    Стирается всё до 0x800000, а не только место под img: иначе за коротким
    образом останется хвост прежнего."""
    if not 0 < len(img) <= GOLDEN:
        sys.exit(f"образ {len(img)} байт не помещается в 0x000000..0x{GOLDEN:06x}")
    blocks = GOLDEN // BLOCK
    for i in range(blocks):
        print(f"\r  стирание {i + 1}/{blocks}", end="", file=sys.stderr)
        with_wren(b, lambda: b.xfer(b"\xd8" + a24(i * BLOCK)))
    print(file=sys.stderr)
    if read(b, 0, len(img)).count(0xFF) != len(img):
        sys.exit("после стирания флеш не чистая")
    done, t0 = 0, time.time()
    while done < len(img):
        need = min(WRITE_CHUNK, PAGE - (done & 0xFF), len(img) - done)
        chunk = img[done:done + need]
        if chunk.count(0xFF) != need:
            with_wren(b, lambda: b.xfer(b"\x02" + a24(done) + chunk))
        done += need
        if done % 0x4000 < need or done == len(img):
            rate = done / max(time.time() - t0, 1e-3) / 1024
            print(f"\r  запись 0x{done:06x}/0x{len(img):06x}  {rate:.0f} КиБ/с", end="", file=sys.stderr)
    print(file=sys.stderr)
    back = read(b, 0, len(img))
    if back != img:
        diff = next(i for i in range(len(img)) if back[i] != img[i])
        sys.exit(f"сверка не прошла: первое расхождение по 0x{diff:06x}")
    print(f"записано и сверено {len(img)} байт с 0x000000")


def check_golden(b, backup):
    """Золотой образ во флеш должен совпадать с бэкапом: бэкап именно этого прибора."""
    gold = backup[GOLDEN:]
    end = len(gold.rstrip(b"\xff"))
    if end == 0:
        sys.exit("в бэкапе нет золотого образа по 0x800000")
    if read(b, GOLDEN, end) != gold[:end]:
        sys.exit("золотой образ во флеш не совпадает с бэкапом: бэкап не от этого прибора?")


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
    w = sub.add_parser("write", help="записать образ с 0x0 (золотой образ не трогается)")
    w.add_argument("image")
    w.add_argument("--backup", required=True, help="полный дамп этого прибора (dump)")
    r = sub.add_parser("restore", help="вернуть заводское приложение из полного дампа")
    r.add_argument("backup")
    a = ap.parse_args()

    b, jid, uid, cap = open_flash()
    print(f"JEDEC ID {jid.hex()}  UID {uid.hex()}  объём {cap // 1024} КиБ" if cap else
          f"JEDEC ID {jid.hex()}  UID {uid.hex()}  объём не опознан")
    if a.cmd == "id":
        return
    if a.cmd in ("write", "restore"):
        backup = open(a.backup, "rb").read()
        if len(backup) != cap:
            sys.exit(f"бэкап {len(backup)} байт, а флеш {cap}: нужен полный дамп")
        check_golden(b, backup)
        if a.cmd == "write":
            img = open(a.image, "rb").read()
        else:
            app = backup[:GOLDEN]
            img = app[:len(app.rstrip(b"\xff"))]
        write_main(b, img)
        print("переподключите прибор (по питанию)")
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
