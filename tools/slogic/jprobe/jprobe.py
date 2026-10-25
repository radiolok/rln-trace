#!/usr/bin/env python3
"""Прозвонка SLogic16U3 по JTAG: читает кадр образа jprobe (регистр ER1,
инструкция 0x42) через OpenOCD и FT2232H и сопоставляет выводы с каналами.

Образ грузится только в SRAM: openFPGALoader -c ft2232 -m jprobe.fs.
Источник — tools/slogic/pinmap/stm32 на F4-Discovery: канал CHk переключается
500 кГц / 2^k раз в секунду; канал опознаётся по log2(ожидаемое / измеренное).

    python3 tools/slogic/jprobe/jprobe.py              # один кадр
    python3 tools/slogic/jprobe/jprobe.py --er2        # проверка канала: 0x12345678
    python3 tools/slogic/jprobe/jprobe.py -n 3 --save run.json
"""

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OPENOCD = os.path.expanduser("~/.local/opt/oss-cad-suite/bin/openocd")
F_OSC = 2 ** 26 / 2.24  # OSCB "210"/4 на GW5AT-15 даёт ~30 МГц, а не 52,5: окно 2^26 измерено по seq — 2,24 с
F_SRC = 16e6 / 32
SRC = [f"PD{k}" for k in range(8)] + ["PE8", "PE9"] + [f"PE{k}" for k in range(2, 8)]  # CH8/CH9 — с PE8/PE9
MAGIC = 0x4A4E4C52  # "RLNJ"

CFG = """adapter driver ftdi
ftdi vid_pid 0x0403 0x6010
ftdi channel 0
ftdi layout_init 0x0008 0x000b
adapter speed 1000
transport select jtag
jtag newtap gw5a tap -irlen 8 -expected-id 0x0001681b
"""


CST = os.path.join(HERE, "jprobe.cst")


def balls():
    m = {}
    for line in open(CST):
        r = re.match(r'IO_LOC "p\[(\d+)\]" (\w+);\s*//\s*(\w+) банк (\d)', line)
        if r:
            m[int(r[1])] = (r[2], r[3], int(r[4]))
    return m


def scan(ir, nwords):
    """Сдвигает nwords 32-битных слов из регистра ir, возвращает список u32.
    Поле одно: drscan с несколькими полями в OpenOCD 0.12+dev отдаёт только первое."""
    cmd = f"init; irscan gw5a.tap {ir:#x}; puts \"DR [drscan gw5a.tap {32 * nwords} 0]\"; shutdown"
    r = subprocess.run([OPENOCD, "-c", CFG.replace("\n", "; "), "-c", cmd],
                       capture_output=True, text=True, timeout=30)
    m = re.search(r"^DR (.*)$", r.stdout + r.stderr, re.M)
    if not m:
        sys.exit("OpenOCD не вернул данные:\n" + r.stderr[-2000:])
    v = int(m[1].strip(), 16)
    return [(v >> (32 * j)) & 0xFFFFFFFF for j in range(nwords)]


def bits(words):
    return [(w >> i) & 1 for w in words for i in range(32)]


def align(words):
    """Ищет "RLNJ" со сдвигом в битах, если кадр начался не с бита 0. На железе
    первым приходит лишний бит (off = 1): Capture-DR не двигает индекс образа."""
    b = bits(words)
    for off in range(8):
        w = [sum(b[off + 32 * j + i] << i for i in range(32)) for j in range((len(b) - off) // 32)]
        if w and w[0] == MAGIC:
            return off, w
    return None, words


def read_frame(np_max=64):
    hdr = scan(0x42, 4)
    off, w = align(hdr)
    if off is None:
        sys.exit("нет \"RLNJ\" в ER1: " + " ".join(f"{x:08x}" for x in hdr))
    n = (w[1] >> 8) & 0xFF
    words = scan(0x42, 2 * n + 3 + 1)
    off, w = align(words)
    return off, w[:2 * n + 3]


def decode(w):
    ver, n, win, seq = w[1] & 0xFF, (w[1] >> 8) & 0xFF, (w[1] >> 16) & 0xFF, w[1] >> 24
    tail = w[2 * n + 2]
    ok = (tail & 0xFFFFFF) == 0xC0FFEE and tail >> 24 == seq
    pins = []
    for i in range(n):
        x, y = w[2 + 2 * i], w[3 + 2 * i]
        pins.append({"raw": x & 0xFFFFFF, "cnt": y & 0xFFFFFF,
                     "seen0": x >> 24 & 1, "seen1": x >> 25 & 1, "last": x >> 26 & 1})
    return {"ver": ver, "n": n, "win": win, "seq": seq, "ok": ok, "pins": pins}


def scale(pins, base):
    """Поправка частоты: доля октавы, на которую все чистые каналы сдвинуты от
    расчёта (генератор ПЛИС и HSI STM32 — с точностью до процентов). Целую
    октаву она не ловит: при неверной F_OSC все каналы уедут на ±1."""
    fr = sorted((math.log2(base / p["cnt"]) + 0.5) % 1 - 0.5 for p in pins if p["cnt"] >= 1000)
    return fr[len(fr) // 2] if fr else 0.0


def report(f):
    t = 2 ** f["win"] / F_OSC
    base = F_SRC * t
    names = balls()
    d = scale(f["pins"], base)
    print(f"версия {f['ver']}, выводов {f['n']}, окно 2^{f['win']} ≈ {t:.2f} с, seq {f['seq']}, "
          f"поправка частоты {2 ** -d:.3f}" + ("" if f["ok"] else "  [кадр разорван сменой окна — прочитать ещё раз]"))
    found, quiet = {}, []
    print(f"\n{'p':>3} {'шарик':5} {'площадка':8} {'б':1} {'сырых':>8} {'фронтов':>8} {'k':>6}  уровни  канал")
    for i, p in enumerate(f["pins"]):
        ball, pad, bank = names.get(i, ("?", "?", 0))
        lv = ("0" if p["seen0"] else "") + ("1" if p["seen1"] else "")
        guess, ks = "", ""
        if p["cnt"]:
            k = math.log2(base / p["cnt"]) - d
            kr = round(k)
            ks = f"{k:6.2f}"
            if 0 <= kr < len(SRC) and abs(k - kr) < 0.15 and p["cnt"] >= 4:
                guess = f"CH{kr} ({SRC[kr]})"
                found.setdefault(kr, []).append(ball)
            elif p["cnt"] == 0xFFFFFF:
                guess = "насыщение — такт?"
            else:
                guess = "не наш меандр"
        else:
            quiet.append(f"{ball}={p['last']}")
        if p["raw"] != p["cnt"] and p["cnt"]:
            guess += f"  дребезг {p['raw'] - p['cnt']:+}"
        print(f"{i:3} {ball:5} {pad:8} {bank} {p['raw']:8} {p['cnt']:8} {ks:>6}  {lv:6}  {guess}")
    print("\nКанал → шарик MG132:")
    for k in range(len(SRC)):
        print(f"  CH{k:<2} ({SRC[k]:4}) → {', '.join(found.get(k, ['—']))}")
    print(f"\nБез фронтов (шарик=уровень): {' '.join(quiet)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--er2", action="store_true", help="прочитать константу ER2 (0x43)")
    ap.add_argument("-n", type=int, default=1, help="сколько кадров подряд (по одному на окно)")
    ap.add_argument("--save", help="сохранить кадры в JSON")
    ap.add_argument("--cst", help="раскладка образа, если он собран не с jprobe.cst")
    a = ap.parse_args()
    if a.cst:
        global CST
        CST = a.cst

    if a.er2:
        b = bits(scan(0x43, 4))
        for off in range(8):
            w = sum(b[off + i] << i for i in range(32))
            if w == 0x12345678:
                print(f"ER2: 12345678 со сдвигом {off} бит — канал JTAG работает")
                return
        sys.exit("ER2: 12345678 не найден: " + "".join(map(str, b)))
        return
    frames = []
    for j in range(a.n):
        if j:
            time.sleep(1.4)
        off, w = read_frame()
        if off:
            print(f"(кадр сдвинут на {off} бит)")
        f = decode(w)
        frames.append(f)
        report(f)
    if a.save:
        json.dump(frames, open(a.save, "w"), indent=1)


if __name__ == "__main__":
    main()
