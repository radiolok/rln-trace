#!/usr/bin/env python3
"""Кадр образа usb2d (ядро Daisho) через JTAG: такты, состояние шины, счётчики (см. шапку usb2d.v).

    RLN_FPGA_USB=1-2 python3 usb2d.py              # кадр
    RLN_FPGA_USB=1-2 python3 usb2d.py --cork 1     # не отдавать данные EP1 IN
    RLN_FPGA_USB=1-2 python3 usb2d.py --off 1      # отключиться от шины (0 — подключиться)
    RLN_FPGA_USB=1-2 python3 usb2d.py --fs 1       # только FS; --blind 1 — HS без чирпов хоста
    RLN_FPGA_USB=1-2 python3 usb2d.py --pat 2 --len 16
    RLN_FPGA_USB=1-2 python3 usb2d.py log -n 200   # журнал: пакеты UTMI и события шины
    RLN_FPGA_USB=1-2 python3 usb2d.py rearm        # журнал заново
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uprobe"))
import uprobe as u  # noqa: E402
from usb2 import PID, H, NW, frame  # noqa: E402

MAGIC = 0x444E4C52  # "RLND"
STATES = ["OFF", "FS", "FSRST", "CHIRP_K", "CHIRP_WAIT", "HS", "HS_REV", "SUSP", "RESUME", "BUSRST"]
LS = ["SE0", "J", "K", "SE1"]
NAMES = {4: "сбросов шины", 5: "SOF", 6: "vendor-запросов", 7: "пакетов EP1 IN", 8: "байт EP1 IN",
         9: "пакетов EP2 OUT", 10: "байт EP2 OUT", 11: "err_crc_pid", 14: "err_crc_tok", 15: "err_crc_pkt",
         16: "err_pid_out_of_seq", 17: "err_setup_pkt"}
# поле команды: (бит, ширина)
FIELDS = {"cork": (0, 1), "off": (1, 1), "pat": (4, 2), "fs": (7, 1), "len": (8, 8), "blind": (16, 1)}


def st_name(s):
    return STATES[s] if s < len(STATES) else str(s)


def cmd_rearm(a):
    w = frame()
    frame(u.er2(0xA << 28 | (w[2] ^ 4) & 0x0FFFFFFF))
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
        dt = "" if prev is None else f"+{((t - prev) & 0xFFFFFFFF) / 60:10.2f} мкс"
        prev = t
        if x >> 29 & 1:
            print(f"{i:5} {dt:16} ── {st_name(x >> 12 & 15):10} linestate {LS[x >> 10 & 3]:3} opmode {x >> 8 & 3} "
                  f"xcvr {x >> 6 & 3} term {x >> 5 & 1} чирпов {x & 7}")
            continue
        tx, err, ln, pid, b1 = x >> 31, x >> 30 & 1, x >> 16 & 0x3FF, x >> 8 & 0xFF, x & 0xFF
        name = PID.get(pid, f"?{pid:02x}")
        extra = f" {b1:02x}" if ln > 1 else ""
        if pid in (0xE1, 0x69, 0x2D, 0xB4) and ln >= 3:
            extra = f" адрес {b1 & 0x7F}"
        print(f"{i:5} {dt:16} {'→ хост' if tx else '← хост'} {name:6}{extra:12} {ln:4} байт{'  ОШИБКА' if err else ''}")


def cmd_status(a):
    cmds = []
    sets = {k: getattr(a, k) for k in FIELDS if getattr(a, k) is not None}
    if sets:
        c = frame()[2] & 0x0FFFFFFF
        for k, v in sets.items():
            b, n = FIELDS[k]
            if k == "len":
                v //= 4
            c = c & ~((1 << n) - 1 << b) | (v & (1 << n) - 1) << b
        cmds = u.er2(0xA << 28 | c)
    w = u.parse(u.openocd(cmds + u.er1("", NW)), NW)[""]
    t = 2 ** 24 / u.F_OSC
    st = w[3]
    print(f"v{w[1] & 0xFF}, seq {w[1] >> 24}, команда {w[2]:#x}")
    print(f"PLL1 {st & 1}, PLL2 {st >> 1 & 1}, сброс {st >> 2 & 1}, HS {st >> 3 & 1}, configured {st >> 4 & 1}, "
          f"suspend {st >> 5 & 1}, linestate {LS[st >> 6 & 3]}")
    print(f"шина {st_name(st >> 8 & 15)}, чирпов хоста {st >> 12 & 7}, opmode {st >> 15 & 3}, "
          f"xcvrselect {st >> 17 & 3}, termselect {st >> 19 & 1}, кадр {w[18]}")
    print(f"60 МГц: {w[12] / t / 1e6:.3f}, 125 МГц: {w[13] / t / 1e6:.3f} (по OSCB)")
    for i, n in NAMES.items():
        print(f"  {n:20} {w[i]}")
    print(f"  последний vendor-запрос {w[19] & 0xFF:#04x}, wValue {w[19] >> 16:#06x}")
    print(f"  журнал: {w[23] & 0x1FFF} записей{' (полон)' if w[23] >> 31 else ''}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cork", type=int, choices=(0, 1))
    ap.add_argument("--off", type=int, choices=(0, 1), help="1 — отключиться от шины")
    ap.add_argument("--fs", type=int, choices=(0, 1), help="1 — без чирпа, только FS")
    ap.add_argument("--blind", type=int, choices=(0, 1), help="1 — HS через 100 мкс после чирпа, без KJ хоста")
    ap.add_argument("--pat", type=int, choices=(0, 1, 2, 3), help="EP1 IN: 0 счётчик, 1 0x00, 2 0xFF, 3 0x7E")
    ap.add_argument("--len", type=int, help="длина пакета EP1 IN, байт (кратно 4, до 512; 0 — по умолчанию)")
    sp = ap.add_subparsers(dest="cmd")
    p = sp.add_parser("log")
    p.add_argument("-n", type=int, default=100)
    sp.add_parser("rearm")
    a = ap.parse_args()
    u.MAGIC = MAGIC
    {"log": cmd_log, "rearm": cmd_rearm}.get(a.cmd, cmd_status)(a)


if __name__ == "__main__":
    main()
