#!/usr/bin/env python3
"""Поток EP1 IN образа usb2 / usb2d: скорость и непрерывность счётчика 32-битных слов (младший байт
первым). Разрыв счётчика = потерянные или повторённые данные.

    python3 usb2stream.py --sec 5
    python3 usb2stream.py --sec 5 --out run.bin     # ещё и сохранить поток
    python3 usb2stream.py --out-test 4096           # записать в OUT (проверка приёма): EP1 у usb2,
                                                    # EP2 у usb2d — берётся из дескриптора

На Windows без usbipd (usb2d сам просит WinUSB через MS OS 2.0; libusb — pip install libusb-package):

    py usb2stream.py --sec 30
"""
import argparse
import array
import sys
import time

import numpy as np
import usb.core
import usb.util

VID, PID = 0x1209, 0x0001


def open_dev():
    backend = None
    if sys.platform == "win32":
        import libusb_package
        backend = libusb_package.get_libusb1_backend()
    dev = usb.core.find(idVendor=VID, idProduct=PID, backend=backend)
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
    rbuf = array.array("B", bytes(a.chunk))  # чтение в готовый буфер — без выделения памяти на каждый вызов
    t0 = time.monotonic()
    while time.monotonic() - t0 < a.sec:
        try:
            n = dev.read(0x81, rbuf, timeout=1000)
        except usb.core.USBTimeoutError:
            print("тайм-аут чтения")
            continue
        buf = memoryview(rbuf)[:n]
        if f:
            f.write(buf)
        total += n
        data = tail + bytes(buf) if tail else buf
        nw = len(data) // 4
        tail = bytes(data[4 * nw:])
        if not nw:
            continue
        # проверка счётчика на numpy: в цикле Python 7 млн слов/с съедают весь процессор
        w = np.frombuffer(data, "<u4", nw)
        prev = np.empty_like(w)
        prev[0] = w[0] if expect is None else expect
        prev[1:] = w[:-1] + np.uint32(1)
        bad = np.flatnonzero(w != prev)
        for i in bad[:max(0, 10 - gaps)]:
            print(f"  разрыв: ждали {prev[i]:#010x}, пришло {w[i]:#010x} ({(int(w[i]) - int(prev[i])) & 0xFFFFFFFF:+d} слов)")
        gaps += len(bad)
        expect = int(w[-1] + np.uint32(1))
    dt = time.monotonic() - t0
    print(f"{total} байт за {dt:.2f} с — {total / dt / 1e6:.3f} МБ/с, разрывов {gaps}, последнее слово {expect - 1 if expect else None}")


if __name__ == "__main__":
    main()
