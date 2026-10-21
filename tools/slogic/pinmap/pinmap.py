#!/usr/bin/env python3
"""Отчёт прозвонки SLogic16U3: читает страницу 0x7F0000 в режиме DFU и
сопоставляет выводы ПЛИС с каналами по частоте.

Образ pinmap.bin считает фронты на 40 свободных выводах GW5AT-15 за окно
2^WIN тактов внутреннего генератора (~52,5 МГц) и пишет результат во флеш.
Источник — stm32/ на F4-Discovery (CH0..7 — PD0..7, CH8..15 — PE0..7):
канал CHk переключается 500 кГц / 2^k раз в секунду. Канал опознаётся по log2(ожидаемое / измеренное).

    python3 tools/slogic/pinmap/pinmap.py            # прибор в DFU (кнопка MODE)
    python3 tools/slogic/pinmap/pinmap.py --file page.bin
"""

import argparse
import math
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPORT = 0x7F0000
F_OSC = 210e6 / 4
F_SRC = 16e6 / 32
SRC = [f"PD{k}" for k in range(8)] + [f"PE{k}" for k in range(8)]


def balls():
    m = {}
    for line in open(os.path.join(HERE, "pinmap.cst")):
        r = re.match(r'IO_LOC "p\[(\d+)\]" (\w+);', line)
        if r:
            m[int(r[1])] = r[2]
    return m


def read_page():
    sys.path.insert(0, os.path.dirname(HERE))
    import slogic_dfu
    b, jid, _, _ = slogic_dfu.open_flash()
    print(f"JEDEC ID {jid.hex()}")
    return slogic_dfu.read(b, REPORT, 256)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="страница из файла вместо прибора")
    ap.add_argument("--save", help="сохранить сырую страницу")
    a = ap.parse_args()

    page = open(a.file, "rb").read()[:256] if a.file else read_page()
    if a.save:
        open(a.save, "wb").write(page)
    if page[:4] != b"RLNP":
        sys.exit(f"отчёта нет (начало страницы {page[:16].hex()}): образ не дошёл до записи")
    ver, n, win = page[4], page[5], page[9]
    t = 2 ** win / F_OSC
    print(f"версия {ver}, выводов {n}, JEDEC {page[6:9].hex()}, окно 2^{win} тактов ≈ {t:.2f} с")
    names = balls()

    found, quiet = {}, []
    print(f"\n{'p':>3} {'шарик':5} {'фронтов':>10} {'Гц':>11}  уровни  канал")
    for i in range(n):
        w, = struct.unpack_from("<I", page, 16 + 4 * i)
        s1, s0, last, cnt = w >> 31 & 1, w >> 30 & 1, w >> 29 & 1, w & 0x1FFFFFFF
        lv = ("0" if s0 else "") + ("1" if s1 else "")
        guess = ""
        if cnt:
            k = math.log2(F_SRC * t / cnt)
            kr = round(k)
            if 0 <= kr < len(SRC) and abs(k - kr) < 0.3 and cnt >= 4:
                guess = f"CH{kr} ({SRC[kr]})"
                found.setdefault(kr, []).append(names[i])
            elif cnt == 0x1FFFFFFF:
                guess = "насыщение — такт?"
            else:
                guess = f"не наш меандр (k≈{k:.2f})"
        else:
            quiet.append(f"{names[i]}={last}")
        print(f"{i:3} {names[i]:5} {cnt:10} {cnt / 2 / t:11.1f}  {lv:6}  {guess}")

    print("\nКанал → шарик ПЛИС:")
    for k in range(len(SRC)):
        print(f"  CH{k:<2} ({SRC[k]:4}) → {', '.join(found.get(k, ['—']))}")
    print(f"\nБез фронтов (шарик=уровень): {' '.join(quiet)}")


if __name__ == "__main__":
    main()
