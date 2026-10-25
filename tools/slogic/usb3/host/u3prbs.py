#!/usr/bin/env python3
"""Скорость и целость EP1 IN образа usb3ref: вендор-запрос 0x02 = 1 включает PRBS15 (x^15 + x^14 + 1, 8 бит на байт,
первый бит — бит 0), асинхронная очередь передач libusb (python-libusb1), сверка каждого байта.
Windows (WinUSB ставится сам по MS OS 2.0) или Linux. Порядок — как в host/usb3_prbs.py ciniml.

    py u3prbs.py -s 10 -q 4 -b 1048576 [-n]   # -n — без сверки
    py u3prbs.py --loop 200                   # петля: EP1 OUT → EP1 IN, 200 посылок 8…3072 байт (DPP от хоста —
                                              # приём, CRC-32 в разборщике), затем поток в обе стороны
    pip install libusb1                       # один раз
"""
import argparse
import time

import usb1

VID, PID = 0x1209, 0x0001


def prbs15_table():
    s, out = 0x7FFF, bytearray(32767)
    for i in range(32767):
        v = 0
        for k in range(8):
            b = ((s >> 14) ^ (s >> 13)) & 1
            s = ((s << 1) | b) & 0x7FFF
            v |= b << k
        out[i] = v
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-s", "--seconds", type=float, default=10.0)
    ap.add_argument("-q", "--queue", type=int, default=4, help="передач в полёте")
    ap.add_argument("-b", "--block", type=int, default=1 << 20, help="байт в передаче")
    ap.add_argument("-n", "--nocheck", action="store_true")
    ap.add_argument("--loop", type=int, metavar="N", help="петля EP1 OUT → IN: N посылок, затем поток")
    a = ap.parse_args()
    tab = prbs15_table()
    tab2 = tab * (a.block // len(tab) + 3)
    with usb1.USBContext() as ctx:
        h = ctx.openByVendorIDAndProductID(VID, PID)
        if h is None:
            raise SystemExit("нет устройства")
        h.claimInterface(0)
        h.controlWrite(0x40, 0x02, 0x0000, 0, b"")  # петля, затем слить остаток
        try:
            while True:
                h.bulkRead(0x81, 1 << 16, timeout=50)
        except usb1.USBErrorTimeout:
            pass
        if a.loop:
            loop(h, ctx, a)
            return
        h.controlWrite(0x40, 0x02, 0x0001, 0, b"")  # PRBS (последовательность заново)
        st = {"total": 0, "errs": 0, "phase": None, "run": True, "fail": None}
        order, done = [], {}

        def check(d):
            if st["phase"] is None:
                for skip in range(8):
                    p = (tab + tab[:64]).find(d[skip:skip + 32])
                    if p >= 0:
                        break
                if p < 0:
                    raise SystemExit(f"фаза PRBS не найдена: {d[:16].hex()}")
                st["phase"], d = p, d[skip:]
            ref = tab2[st["phase"]:st["phase"] + len(d)]
            if d != ref:
                st["errs"] += sum(1 for x, y in zip(d, ref) if x != y)
                p = (tab + tab[:64]).find(d[-32:])
                st["phase"] = (p + 32) % len(tab) if p >= 0 else 0
            else:
                st["phase"] = (st["phase"] + len(d)) % len(tab)

        def cb(t):
            if t.getStatus() != usb1.TRANSFER_COMPLETED:
                st["fail"] = st["fail"] or t.getStatus()
                st["run"] = False
                return
            done[id(t)] = t.getBuffer()[:t.getActualLength()]
            # проверка — строго в порядке отправки (на одной точке libusb и так завершает по порядку)
            while order and id(order[0]) in done:
                t0 = order.pop(0)
                d = bytes(done.pop(id(t0)))
                st["total"] += len(d)
                if not a.nocheck:
                    check(d)
                if st["run"]:
                    t0.submit()
                    order.append(t0)

        xs = []
        for _ in range(a.queue):
            t = h.getTransfer()
            t.setBulk(0x81, a.block, callback=cb, timeout=2000)
            xs.append(t)
        t_start = time.perf_counter()
        for t in xs:
            t.submit()
            order.append(t)
        while time.perf_counter() - t_start < a.seconds and st["run"]:
            ctx.handleEventsTimeout(0.1)
        st["run"] = False
        dt = time.perf_counter() - t_start
        while any(t.isSubmitted() for t in xs):
            ctx.handleEventsTimeout(0.1)
        h.controlWrite(0x40, 0x02, 0x0000, 0, b"")
        print(f"очередь {a.queue} × {a.block} Б: {st['total'] / 1e6:.1f} МБ за {dt:.2f} с = "
              f"{st['total'] / dt / 1e6:.1f} МБ/с, ошибочных байт {st['errs']}"
              + ("" if a.nocheck else ", сверка вся") + (f", сбой передачи {st['fail']}" if st["fail"] else ""))


def loop(h, ctx, a):
    """Режим петли (0x02 = 0): байты EP1 OUT уходят в EP1 IN; короткий пакет закрывается по паузе потока."""
    import random
    rnd = random.Random(1)
    bad = 0
    for i in range(a.loop):
        n = rnd.choice([8, 12, 511, 512, 513, 1023, 1024, 1025, 2048, 3072]) if i % 2 else rnd.randint(8, 3072)
        d = bytes(rnd.getrandbits(8) for _ in range(n))
        h.bulkWrite(0x01, d, timeout=2000)
        got = b""
        while len(got) < n:
            got += h.bulkRead(0x81, 4096, timeout=2000)
        if got != d:
            bad += 1
            if bad <= 5:
                k = next((j for j in range(min(len(got), n)) if got[j] != d[j]), min(len(got), n))
                print(f"  посылка {i}: {n} байт, вернулось {len(got)}, расхождение с байта {k}")
    print(f"петля: {a.loop} посылок 8…3072 байт, не совпало {bad}")
    # поток в обе стороны: запись и чтение одновременно (асинхронно), сверка всего, что вернулось
    tot = 1 << 26 if a.seconds >= 10 else 1 << 24
    src = bytes(rnd.getrandbits(8) for _ in range(1 << 20))
    st = {"wr": 0, "rd": 0, "err": 0, "buf": b""}

    def wcb(t):
        if t.getStatus() == usb1.TRANSFER_COMPLETED and st["wr"] < tot:
            st["wr"] += t.getActualLength()
            if st["wr"] < tot:
                t.submit()

    def rcb(t):
        if t.getStatus() != usb1.TRANSFER_COMPLETED:
            return
        d = bytes(t.getBuffer()[:t.getActualLength()])
        off = st["rd"] % len(src)
        ref = (src[off:] + src * 2)[:len(d)]
        if d != ref:
            st["err"] += 1
        st["rd"] += len(d)
        if st["rd"] < tot:
            t.submit()

    w = h.getTransfer(); w.setBulk(0x01, src, callback=wcb, timeout=5000)
    r = [h.getTransfer() for _ in range(2)]
    for t in r:
        t.setBulk(0x81, 1 << 16, callback=rcb, timeout=5000)
    t0 = time.perf_counter()
    for t in r:
        t.submit()
    w.submit()
    while st["rd"] < tot and time.perf_counter() - t0 < 60:
        ctx.handleEventsTimeout(0.1)
    dt = time.perf_counter() - t0
    for t in r + [w]:
        if t.isSubmitted():
            t.cancel()
    while any(t.isSubmitted() for t in r + [w]):
        ctx.handleEventsTimeout(0.1)
    print(f"поток в обе стороны: {st['rd'] / 1e6:.1f} МБ туда и обратно за {dt:.2f} с = {st['rd'] / dt / 1e6:.1f} МБ/с "
          f"в каждую сторону, несовпавших передач {st['err']}")


if __name__ == "__main__":
    main()
