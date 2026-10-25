#!/usr/bin/env python3
"""Скорость и целость EP1 IN образа usb3ref: вендор-запрос 0x02 = 1 включает PRBS15 (x^15 + x^14 + 1, 8 бит на байт,
первый бит — бит 0), асинхронная очередь передач libusb (python-libusb1), сверка каждого байта.
Windows (WinUSB ставится сам по MS OS 2.0) или Linux. Порядок — как в host/usb3_prbs.py ciniml.

    py u3prbs.py -s 10 -q 4 -b 1048576 [-n]   # -n — без сверки
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


if __name__ == "__main__":
    main()
