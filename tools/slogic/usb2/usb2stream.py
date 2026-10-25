#!/usr/bin/env python3
"""Поток EP1 IN образа usb2 / usb2d: скорость и непрерывность счётчика 32-битных слов (младший байт
первым). Разрыв счётчика = потерянные или повторённые данные.

    python3 usb2stream.py --sec 5
    python3 usb2stream.py --sec 5 --out run.bin     # ещё и сохранить поток
    python3 usb2stream.py --out-test 4096           # записать в OUT (проверка приёма): EP1 у usb2,
                                                    # EP2 у usb2d — берётся из дескриптора
"""
import argparse
import struct
import sys
import time

import usb.core
import usb.util

VID, PID = 0x1209, 0x0001


def open_dev():
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        sys.exit(f"нет устройства {VID:04x}:{PID:04x}")
    try:
        if dev.is_kernel_driver_active(0):
            dev.detach_kernel_driver(0)
    except (NotImplementedError, usb.core.USBError):
        pass
    dev.set_configuration(1)
    usb.util.claim_interface(dev, 0)
    return dev


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sec", type=float, default=3.0)
    ap.add_argument("--chunk", type=int, default=64 * 1024)
    ap.add_argument("--out")
    ap.add_argument("--out-test", type=int, metavar="N", help="отправить N байт в OUT")
    a = ap.parse_args()
    dev = open_dev()
    speed = {1: "LS", 2: "FS", 3: "HS", 4: "SS"}.get(dev.speed, dev.speed)
    print(f"{dev.manufacturer} / {dev.product} / {dev.serial_number}, скорость {speed}")
    if a.out_test:
        ep = usb.util.find_descriptor(dev.get_active_configuration()[(0, 0)], custom_match=lambda e:
                                      usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)
        n = dev.write(ep.bEndpointAddress, (bytes(range(256)) * (a.out_test // 256 + 1))[:a.out_test], timeout=2000)
        print(f"OUT {ep.bEndpointAddress:#04x}: записано {n} байт")
        return
    f = open(a.out, "wb") if a.out else None
    total = gaps = 0
    expect = None
    tail = b""
    t0 = time.monotonic()
    while time.monotonic() - t0 < a.sec:
        try:
            buf = bytes(dev.read(0x81, a.chunk, timeout=1000))
        except usb.core.USBTimeoutError:
            print("тайм-аут чтения")
            continue
        if f:
            f.write(buf)
        total += len(buf)
        data = tail + buf
        n = len(data) // 4
        tail = data[4 * n:]
        for (w,) in struct.iter_unpack("<I", data[:4 * n]):
            if expect is not None and w != expect:
                if gaps < 10:
                    print(f"  разрыв: ждали {expect:#010x}, пришло {w:#010x} ({(w - expect) & 0xFFFFFFFF:+d} слов)")
                gaps += 1
            expect = (w + 1) & 0xFFFFFFFF
    dt = time.monotonic() - t0
    print(f"{total} байт за {dt:.2f} с — {total / dt / 1e6:.3f} МБ/с, разрывов {gaps}, последнее слово {expect - 1 if expect else None}")


if __name__ == "__main__":
    main()
