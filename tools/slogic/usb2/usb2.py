#!/usr/bin/env python3
"""Кадр образа usb2 через JTAG: такты, состояние USB, счётчики (см. шапку usb2.v).

    RLN_FPGA_USB=1-2 python3 usb2.py           # кадр
    RLN_FPGA_USB=1-2 python3 usb2.py --cork 1  # не отдавать данные EP1 IN (0 — отдавать)
    RLN_FPGA_USB=1-2 python3 usb2.py --reset 1 # держать контроллер в сбросе
    RLN_FPGA_USB=1-2 python3 usb2.py --pat 2 --len 16  # EP1 IN: байты 0xFF, пакеты по 16 байт
    RLN_FPGA_USB=1-2 python3 usb2.py log -n 200 # журнал пакетов UTMI
    RLN_FPGA_USB=1-2 python3 usb2.py rearm     # журнал заново
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uprobe"))
import uprobe as u  # noqa: E402

MAGIC = 0x424E4C52  # "RLNB"
NW = 24
H = 24
DBG = ["rx_nak", "tx_nak", "tx_zlp", "rx_failed", "tx_failed", "token_failed", "token_valid",
       "addr_mismatch", "endpt_val"]
PID = {0xE1: "OUT", 0x69: "IN", 0xA5: "SOF", 0x2D: "SETUP", 0xC3: "DATA0", 0x4B: "DATA1",
       0x87: "DATA2", 0x0F: "MDATA", 0xD2: "ACK", 0x5A: "NAK", 0x1E: "STALL", 0x96: "NYET",
       0x3C: "PRE/ERR", 0x78: "SPLIT", 0xB4: "PING"}
NAMES = ["сбросов шины", "SOF", "SETUP", "IN EP1", "txpktfin EP1", "байт отдано EP1",
         "байт принято EP1", "rxpktval"]


def frame(cmds=()):
    return u.parse(u.openocd(list(cmds) + u.er1("", NW)), NW)[""]


def cmd_rearm(a):
    w = frame()
    frame(u.er2(0xA << 28 | (w[2] ^ 4) & 7))
    print("журнал заново")


def cmd_log(a):
    w = frame()
    n = min(w[23] & 0x1FFF, a.n)
    print(f"записей {w[23] & 0x1FFF}{' (полон)' if w[23] >> 31 else ''}, показываю {n}")
    words, chunk = [], 256
    for base in range(0, 2 * n, chunk * 8):
        cmds = []
        addrs = list(range(base, min(2 * n, base + chunk * 8), chunk))
        for ad in addrs:
            cmds += u.er2(0xB << 28 | ad) + u.er1(f"a{ad}", H + chunk)
        res = u.parse(u.openocd(cmds), H + chunk)
        for ad in addrs:
            words += res[f"a{ad}"][H:H + min(chunk, 2 * n - ad)]
    prev = None
    for i in range(n):
        x, t = words[2 * i], words[2 * i + 1]
        tx, err, ln, pid, b1 = x >> 31, x >> 30 & 1, x >> 16 & 0x3FF, x >> 8 & 0xFF, x & 0xFF
        dt = "" if prev is None else f"+{((t - prev) & 0xFFFFFFFF) / 60:10.2f} мкс"
        prev = t
        name = PID.get(pid, f"?{pid:02x}")
        extra = f" {b1:02x}" if ln > 1 else ""
        if pid in (0xE1, 0x69, 0x2D, 0xB4) and ln >= 3:
            extra = f" адрес {b1 & 0x7F}"
        print(f"{i:5} {dt:16} {'→ хост' if tx else '← хост'} {name:6}{extra:12} {ln:4} байт{'  ОШИБКА' if err else ''}")


def cmd_status(a):
    cmds = []
    if a.cork is not None or a.reset is not None or a.pat is not None or a.len is not None:
        w = frame()
        c = w[2] & 0x0FFFFFFF
        if a.cork is not None:
            c = c & ~1 | a.cork
        if a.reset is not None:
            c = c & ~2 | a.reset << 1
        if a.pat is not None:
            c = c & ~0x30 | a.pat << 4
        if a.len is not None:
            c = c & ~0xFF00 | (a.len // 4) << 8
        cmds = u.er2(0xA << 28 | c)
    w = u.parse(u.openocd(cmds + u.er1("", NW)), NW)[""]
    t = 2 ** 24 / u.F_OSC
    st = w[3]
    print(f"v{w[1] & 0xFF}, seq {w[1] >> 24}, команда {w[2]:#x}")
    print(f"PLL1 {st & 1}, PLL2 {st >> 1 & 1}, сброс {st >> 2 & 1}, HS {st >> 3 & 1}, online {st >> 4 & 1}, "
          f"suspend {st >> 5 & 1}, linestate {st >> 6 & 3}, точка {st >> 8 & 15}")
    print(f"60 МГц: {w[12] / t / 1e6:.3f}, 125 МГц: {w[13] / t / 1e6:.3f} (по OSCB); "
          f"отношение {w[12] / max(w[13], 1) * 125:.4f} МГц при 125 точно")
    for i, n in enumerate(NAMES):
        print(f"  {n:18} {w[4 + i]}")
    print("  dbg (тактов): " + ", ".join(f"{n} {w[14 + i]}" for i, n in enumerate(DBG)))
    print(f"  журнал: {w[23] & 0x1FFF} записей{' (полон)' if w[23] >> 31 else ''}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cork", type=int, choices=(0, 1))
    ap.add_argument("--reset", type=int, choices=(0, 1))
    ap.add_argument("--pat", type=int, choices=(0, 1, 2, 3), help="EP1 IN: 0 счётчик, 1 0x00, 2 0xFF, 3 0x7E")
    ap.add_argument("--len", type=int, help="длина пакета EP1 IN, байт (кратно 4, до 1020; 0 — по умолчанию)")
    sp = ap.add_subparsers(dest="cmd")
    p = sp.add_parser("log")
    p.add_argument("-n", type=int, default=100)
    sp.add_parser("rearm")
    a = ap.parse_args()
    u.MAGIC = MAGIC
    {"log": cmd_log, "rearm": cmd_rearm}.get(a.cmd, cmd_status)(a)


if __name__ == "__main__":
    main()
