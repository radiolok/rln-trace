#!/usr/bin/env python3
"""Опыты прозвонки SLogic16U3 с управлением источником: STM32F4-Discovery через
постоянный сервер OpenOCD (ST-LINK, Tcl-порт 6667), ПЛИС — образ jprobe через
OpenOCD + FT2232H (jprobe.py).

Сервер ST-LINK держать запущенным всё время опытов: отдельные запуски
`openocd ... shutdown` отпускают ядро, и прошивка снова бежит.

    openocd -f board/stm32f4discovery.cfg -c "gdb_port disabled; telnet_port disabled; tcl_port 6667; init" &
    python3 tools/slogic/jprobe/bench.py window          # длина окна по смене seq
    python3 tools/slogic/jprobe/bench.py gate PD0 PE8     # гашение линий по одной: какой вывод замолк
    python3 tools/slogic/jprobe/bench.py static          # STM32 стоит, все линии в 1, затем в 0
    python3 tools/slogic/jprobe/bench.py run             # отпустить прошивку
"""

import argparse
import socket
import sys
import time

import jprobe

GPIO = {"PD": 0x40020C00, "PE": 0x40021000}
MODER, IDR, ODR = 0x00, 0x10, 0x14
# линии источника: CH0..CH7 — PD0..PD7, CH8/CH9 — PE8/PE9, CH10..CH15 — PE2..PE7, CK0/CK1 — PE10/PE11
D_ALL, E_ALL = 0xFF, 0xFFC
D_KEEP = 0x5000  # PD12 (зелёный) и PD14 (красный) — индикаторы прошивки


class Stm:
    def __init__(self, port=6667):
        try:
            self.s = socket.create_connection(("127.0.0.1", port))
        except OSError:
            sys.exit(f"нет сервера OpenOCD на Tcl-порту {port}: запустить его, см. --help")

    def tcl(self, cmd):
        self.s.sendall(cmd.encode() + b"\x1a")
        b = b""
        while not b.endswith(b"\x1a"):
            b += self.s.recv(4096)
        return b[:-1].decode()

    def rd(self, a):
        return int(self.tcl(f"format %08x [read_memory {a:#x} 32 1]"), 16)

    def wr(self, a, v):
        self.tcl(f"write_memory {a:#x} 32 {v:#x}")

    def state(self):
        return self.tcl("stm32f4x.cpu curstate")


def frame(skip=2):
    """Кадр окна, целиком прошедшего после вызова (skip смен seq)."""
    q = jprobe.decode(jprobe.read_frame()[1])["seq"]
    while True:
        time.sleep(0.4)
        f = jprobe.decode(jprobe.read_frame()[1])
        if (f["seq"] - q) % 256 >= skip and f["ok"]:
            return f


def line(name):
    port, bit = name[:2].upper(), int(name[2:])
    if port not in GPIO or not 0 <= bit < 16:
        sys.exit(f"линия {name}: ждём PDn или PEn")
    return GPIO[port], bit


def cmd_window(stm, a):
    f = lambda: jprobe.decode(jprobe.read_frame()[1])["seq"]
    q = f()
    while f() == q:
        time.sleep(0.05)
    t0, q = time.time(), (q + 1) % 256
    n = 0
    while n < a.n:
        if f() != q:
            q, n = (q + 1) % 256, n + 1
        time.sleep(0.02)
    t = (time.time() - t0) / a.n
    print(f"окно ≈ {t:.3f} с, OSCB ≈ {2 ** 26 / t / 1e6:.2f} МГц (для WIN_LOG2 = 26)")


def cmd_gate(stm, a):
    if stm.state() != "running":
        sys.exit("прошивка источника стоит: bench.py run")
    names = jprobe.balls()
    act = lambda f: {names[i][0]: p["cnt"] for i, p in enumerate(f["pins"]) if p["cnt"] > 2}
    base = act(frame())
    print("все линии:", " ".join(f"{k}={v}" for k, v in base.items()))
    for ln in a.lines:
        port, bit = line(ln)
        m = stm.rd(port + MODER)
        try:
            stm.wr(port + MODER, m & ~(3 << 2 * bit))  # вход: линия отпущена
            f = act(frame())
        finally:
            stm.wr(port + MODER, m)
        gone = [k for k in base if f.get(k, 0) < base[k] * 0.5]
        new = [f"{k}={v}" for k, v in f.items() if k not in base]
        print(f"{ln} погашен → замолчали: {' '.join(gone) or 'никто'}"
              + (f"; появились: {' '.join(new)}" if new else ""))


def cmd_static(stm, a):
    names = jprobe.balls()
    stm.tcl("halt")
    for tag, d, e in (("все 1", D_ALL, E_ALL), ("все 0", 0, 0)):
        stm.wr(GPIO["PD"] + ODR, D_KEEP | d)
        stm.wr(GPIO["PE"] + ODR, e)
        f = frame()
        hi = [names[i][0] for i, p in enumerate(f["pins"]) if p["last"] and not p["seen0"]]
        fl = [names[i][0] for i, p in enumerate(f["pins"]) if p["seen0"] and p["seen1"]]
        print(f"{tag}: в 1 — {' '.join(hi) or 'никто'} | мерцают — {' '.join(fl) or 'нет'}")
    if not a.keep:
        stm.tcl("resume")
    print("прошивка источника", stm.state())


def cmd_hold(stm, a):
    stm.tcl("halt")
    v = 1 if a.level == "1" else 0
    stm.wr(GPIO["PD"] + ODR, D_KEEP | D_ALL * v)
    stm.wr(GPIO["PE"] + ODR, E_ALL * v)
    print(f"STM32 стоит, PD0–PD7, PE2–PE11 = {v}: IDR_D {stm.rd(GPIO['PD'] + IDR):08x}, "
          f"IDR_E {stm.rd(GPIO['PE'] + IDR):08x}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cst", help="раскладка образа, если он собран не с jprobe.cst")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("window", help="длина окна и частота OSCB по смене seq")
    w.add_argument("-n", type=int, default=3, help="сколько окон мерить")
    g = sub.add_parser("gate", help="гасить линии по одной (MODER → вход) на работающей прошивке")
    g.add_argument("lines", nargs="+", help="PD0 … PD7, PE2 … PE11")
    st = sub.add_parser("static", help="STM32 стоит, все линии в 1, затем в 0")
    st.add_argument("--keep", action="store_true", help="не отпускать прошивку после опыта")
    h = sub.add_parser("hold", help="остановить STM32 и держать все линии в 1 или 0 (замеры мультиметром)")
    h.add_argument("level", choices=["0", "1"])
    sub.add_parser("run", help="отпустить прошивку источника")
    a = ap.parse_args()
    if a.cst:
        jprobe.CST = a.cst
    stm = Stm()
    if a.cmd == "run":
        stm.tcl("resume")
        print("прошивка источника", stm.state())
    else:
        {"window": cmd_window, "gate": cmd_gate, "static": cmd_static, "hold": cmd_hold}[a.cmd](stm, a)


if __name__ == "__main__":
    main()
