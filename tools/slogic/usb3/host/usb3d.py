#!/usr/bin/env python3
"""Образ usb3d (tools/slogic/usb3/usb3d.v): регистры по вендор-запросам EP0, поток EP1 IN.
Windows (WinUSB ставится сам по MS OS 2.0; pip install libusb1 numpy) или Linux.

    py usb3d.py                         # состояние: линк, частота TRACECLK, счётчики, задержки
    py usb3d.py --dly 224 224 224 224   # IODELAY TRACED0..3 (ступени ~12,5 пс)
    py usb3d.py test --rate 2 -s 10     # тестовый источник: слово раз в 2 такта pclk (250 МБ/с), проверка
                                        # непрерывности; разрывы должны совпасть со счётчиком потерь
    py usb3d.py cap -s 5 -o run.bin     # трасса в файл (слова как у режима 2 tracela: байт = {спад, фронт})

Регистры — шапка usb3d.v.
"""
import argparse
import sys
import time

import numpy as np
import usb1

VID, PID = 0x1209, 0x0001
MAGIC = 0x33554C52  # "RLU3"
F_PCLK = 125e6
STATES = ["PhyWait", "Disabled", "Inactive", "RxDetReset", "RxDetActive", "RxDetQuiet", "PollLfps", "PollRxEq",
          "PollActive", "PollConfig", "PollIdle", "U0", "U3", "U3Wake", "RecActive", "RecConfig", "RecIdle",
          "HotRstActive", "HotRstExit"]


class Dev:
    def __init__(self, ctx):
        self.h = ctx.openByVendorIDAndProductID(VID, PID)
        if self.h is None:
            sys.exit(f"нет устройства {VID:04x}:{PID:04x}")
        self.h.claimInterface(0)
        if self.rd(0) != MAGIC:
            sys.exit(f"регистр 0 = {self.rd(0):#010x}, а не \"RLU3\": загружен не usb3d?")

    def rd(self, a):
        return int.from_bytes(self.h.controlRead(0xC0, 0x04, 0, a, 4, timeout=1000), "little")

    def wr(self, a, v):
        self.h.controlWrite(0x40, 0x03, v & 0xFFFF, a, b"", timeout=1000)

    def ctrl(self, run, src, clear=False):
        self.wr(0, (run & 1) | (src & 3) << 1 | (8 if clear else 0))

    def drain(self):
        try:
            while True:
                self.h.bulkRead(0x81, 1 << 16, timeout=50)
        except usb1.USBErrorTimeout:
            pass


def status(d):
    r = [d.rd(i) for i in range(10)]
    st = r[8] & 31
    print(f"линк: {STATES[st] if st < len(STATES) else st}, U0 {r[8] >> 5 & 1}, link cfg {r[8] >> 6 & 1}, "
          f"device cfg {r[8] >> 7 & 1}, адрес {r[8] >> 8 & 127}; версия {r[1] >> 24}, CTRL {r[1] & 0xFFFF:#x}")
    print(f"TRACECLK: {r[2] / (2 ** 20 / F_PCLK) / 1e6:.3f} МГц; IODELAY {[r[7] >> 8 * i & 255 for i in range(4)]}")
    print(f"слов: отдано {r[3]}, трассы принято {r[9]}, потеряно — трассы {r[4]}, теста {r[5]}; "
          f"sfifo сейчас {r[6] & 0xFFFF}, наибольшее {r[6] >> 16}")


def stream(ctx, d, seconds, block, queue, sink):
    """Асинхронная очередь чтения EP1 IN; sink(bytes) — по порядку. Возвращает (байт, секунд)."""
    st = {"n": 0, "run": True, "fail": None}
    order, done = [], {}

    def cb(t):
        if t.getStatus() not in (usb1.TRANSFER_COMPLETED, usb1.TRANSFER_TIMED_OUT):
            if t.getStatus() != usb1.TRANSFER_CANCELLED:
                st["fail"] = st["fail"] or t.getStatus()
            st["run"] = False
            return
        done[id(t)] = bytes(t.getBuffer()[:t.getActualLength()])
        while order and id(order[0]) in done:
            t0 = order.pop(0)
            b = done.pop(id(t0))
            st["n"] += len(b)
            sink(b)
            if st["run"]:
                t0.submit()
                order.append(t0)

    xs = []
    for _ in range(queue):
        t = d.h.getTransfer()
        t.setBulk(0x81, block, callback=cb, timeout=200)
        xs.append(t)
    t0 = time.perf_counter()
    for t in xs:
        t.submit()
        order.append(t)
    while time.perf_counter() - t0 < seconds and st["run"]:
        ctx.handleEventsTimeout(0.1)
    st["run"] = False
    dt = time.perf_counter() - t0
    while any(t.isSubmitted() for t in xs):
        ctx.handleEventsTimeout(0.1)
    if st["fail"]:
        print(f"сбой передачи: {st['fail']}")
    return st["n"], dt


def cmd_test(ctx, d, a):
    d.ctrl(0, 1)
    d.drain()
    d.wr(1, a.rate)
    d.ctrl(0, 1, clear=True)
    s = {"exp": None, "gaps": 0, "lost": 0, "back": 0, "tail": b""}

    def sink(b):
        b = s["tail"] + b
        n = len(b) // 4
        s["tail"] = b[4 * n:]
        if not n:
            return
        w = np.frombuffer(b, "<u4", n).astype(np.int64)
        prev = np.empty_like(w)
        prev[0] = w[0] if s["exp"] is None else s["exp"]
        prev[1:] = w[:-1] + 1
        diff = w - prev
        s["gaps"] += int(np.count_nonzero(diff))
        s["lost"] += int(diff[diff > 0].sum())
        s["back"] += int(np.count_nonzero(diff < 0))
        s["exp"] = int(w[-1]) + 1

    d.ctrl(1, 1)
    n, dt = stream(ctx, d, a.seconds, a.block, a.queue, sink)
    d.ctrl(0, 1)
    time.sleep(0.05)
    nw, gdrop = d.rd(3), d.rd(5)
    print(f"тест rate {a.rate} ({F_PCLK / max(a.rate, 1) * 4 / 1e6:.0f} МБ/с от источника): принято {n / 1e6:.1f} МБ за "
          f"{dt:.2f} с = {n / dt / 1e6:.1f} МБ/с")
    print(f"  разрывов {s['gaps']}, пропало по разрывам {s['lost']}, назад {s['back']}; потерь по счётчику {gdrop}; "
          f"отдано {nw} слов, принято {n // 4}")
    ok = s["back"] == 0 and s["lost"] <= gdrop and (gdrop == 0) == (s["lost"] == 0)
    print("  " + ("сходится" if ok else "НЕ сходится") + (f" (последние {gdrop - s['lost']} потерь — после последнего "
                                                        f"принятого слова)" if gdrop > s["lost"] else ""))
    status(d)


def cmd_cap(ctx, d, a):
    d.ctrl(0, 0)
    d.drain()
    d.ctrl(0, 0, clear=True)
    f = open(a.out, "wb")
    d.ctrl(1, 0)
    n, dt = stream(ctx, d, a.seconds, a.block, a.queue, f.write)
    d.ctrl(0, 0)
    f.close()
    print(f"трасса: {n} байт за {dt:.2f} с = {n / dt / 1e6:.2f} МБ/с → {a.out}")
    status(d)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dly", type=int, nargs=4, metavar="D", help="IODELAY TRACED0..3")
    sub = ap.add_subparsers(dest="cmd")
    for name in ("test", "cap"):
        p = sub.add_parser(name)
        p.add_argument("-s", "--seconds", type=float, default=5.0)
        p.add_argument("-b", "--block", type=int, default=1 << 20)
        p.add_argument("-q", "--queue", type=int, default=4)
        if name == "test":
            p.add_argument("--rate", type=int, default=4, help="период источника, тактов pclk (1 = 500 МБ/с)")
        else:
            p.add_argument("-o", "--out", default="trace.bin")
    a = ap.parse_args()
    with usb1.USBContext() as ctx:
        d = Dev(ctx)
        if a.dly:
            d.wr(2, a.dly[0] | a.dly[1] << 8)
            d.wr(3, a.dly[2] | a.dly[3] << 8)
        if a.cmd == "test":
            cmd_test(ctx, d, a)
        elif a.cmd == "cap":
            cmd_cap(ctx, d, a)
        else:
            status(d)


if __name__ == "__main__":
    main()
