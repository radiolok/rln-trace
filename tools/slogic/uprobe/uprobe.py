#!/usr/bin/env python3
"""Поиск линий USB2 SLogic16U3: образ uprobe (SRAM), JTAG через OpenOCD и FT2232H.

Каждый из 22 свободных GPIO по команде — вход, 0 или 1 (4 мА). Кто сидит на одной цепи с
ведомым выводом, идёт за ним; если цепь — D+ (или D−), Windows видит подключение.

    openFPGALoader -c ft2232 --busdev-num … -m uprobe.fs
    python3 uprobe.py frame                 # уровни, фронты, был 0/1
    python3 uprobe.py scan                  # каждый вывод по очереди в 1 и в 0: кто идёт следом
    python3 uprobe.py hold H13=1 --sec 3    # держать, смотреть устройства Windows (usbipd list)
    python3 uprobe.py cap H13=1 --sec 1     # то же с записью смен уровней (сброс шины хостом)
    python3 uprobe.py release               # все выводы — входы

Адаптер ПЛИС выбирается по месту на шине: RLN_FPGA_USB=1-2.
"""

import argparse
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OPENOCD = os.path.expanduser("~/.local/opt/oss-cad-suite/bin/openocd")
USBIPD = "/mnt/c/Program Files/usbipd-win/usbipd.exe"
F_OSC = 2 ** 26 / 2.24  # OSCB ~30 МГц (измерено, см. jprobe)
MAGIC = 0x554E4C52  # "RLNU"
H = 22

CFG = """adapter driver ftdi
ftdi vid_pid 0x0403 0x6010
ftdi channel 0
ftdi layout_init 0x0008 0x000b
adapter speed 2000
transport select jtag
jtag newtap gw5a tap -irlen 8 -expected-id 0x0001681b
"""
if os.environ.get("RLN_FPGA_USB"):
    CFG += f"adapter usb location {os.environ['RLN_FPGA_USB']}\n"


def pins():
    """[(шарик, площадка, банк, функция)] в порядке p[i] из uprobe.cst."""
    out = []
    for line in open(os.path.join(HERE, "uprobe.cst")):
        r = re.match(r'IO_LOC "p\[(\d+)\]" (\w+);\s*//\s*(\w+) банк (\d)\s*(.*)', line)
        if r:
            assert int(r[1]) == len(out)
            out.append((r[2], r[3], int(r[4]), r[5].strip()))
    return out


PINS = pins()
NP = len(PINS)
BALL = {b: i for i, (b, *_) in enumerate(PINS)}


def openocd(cmds, timeout=120):
    r = subprocess.run([OPENOCD, "-c", CFG.replace("\n", "; "), "-c",
                        "init; " + "; ".join(cmds) + "; shutdown"],
                       capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr


def er2(word):
    return ["irscan gw5a.tap 0x43", f"drscan gw5a.tap 32 {word:#x}"]


def er1(tag, nwords=H):
    # +1 слово: на железе первым идёт лишний бит, кадр ищется по метке
    return ["irscan gw5a.tap 0x42", f"puts \"DR{tag} [drscan gw5a.tap {32 * (nwords + 1)} 0]\""]


def drive(oe, val):
    """Все в Z, потом уровень, потом разрешение: ни один вывод не проходит через чужой уровень
    (D13 на мгновение в 0 перезапускает конфигурацию ПЛИС)."""
    return er2(0xC << 28) + er2(0xD << 28 | val) + er2(0xC << 28 | oe)


def parse(out, nwords=H):
    res = {}
    for m in re.finditer(r"^DR(\w*) (\S+)$", out, re.M):
        v = int(m[2], 16)
        for off in range(8):
            w = [(v >> (off + 32 * j)) & 0xFFFFFFFF for j in range(nwords)]
            if w[0] == MAGIC:
                res[m[1]] = w
                break
        else:
            sys.exit(f"нет \"RLNU\" в ER1 ({m[1]}): образ не загружен?\n" + out[-800:])
    if not res:
        sys.exit("OpenOCD не вернул данные:\n" + out[-1500:])
    return res


def header(w):
    return {"ver": w[1] & 0xFF, "depth_log2": w[1] >> 8 & 0xFF, "win_log2": w[1] >> 16 & 0xFF,
            "seq": w[1] >> 24, "cmd": w[2], "oe": w[3], "val": w[4], "lvl": w[5],
            "wptr": w[6] & 0xFFFFF, "run": w[6] >> 30 & 1, "full": w[6] >> 31,
            "edges": [w[7 + i // 2] >> (16 * (i % 2)) & 0xFFFF for i in range(NP)],
            "was1": w[18], "was0": w[19], "gclk": w[20]}


def mask_str(m):
    return " ".join(PINS[i][0] for i in range(NP) if m >> i & 1) or "—"


def parse_assign(items):
    """["H13=1", "C13=z"] → (oe, val)."""
    oe = val = 0
    for it in items:
        b, _, v = it.partition("=")
        i = BALL.get(b.upper())
        if i is None:
            sys.exit(f"нет вывода {b}; есть: {' '.join(BALL)}")
        if v.lower() in ("0", "1"):
            oe |= 1 << i
            val |= int(v) << i
        elif v.lower() != "z":
            sys.exit(f"{it}: уровень 0, 1 или z")
    return oe, val


def usb_devices():
    """Подключённые устройства Windows: {BUSID: строка}."""
    try:
        r = subprocess.run([USBIPD, "list"], capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    dev = {}
    for line in r.stdout.splitlines():
        if line.startswith("Persisted"):
            break
        m = re.match(r"^(\d+-\d+)\s+(\S+)\s+(.*?)\s{2,}", line)
        if m:
            dev[m[1]] = f"{m[2]} {m[3]}"
    return dev


def cmd_frame(a):
    h = header(parse(openocd(er1("")))[""])
    t = 2 ** h["win_log2"] / F_OSC
    print(f"v{h['ver']}, окно {t:.2f} с, seq {h['seq']}; oe {mask_str(h['oe'])}; "
          f"ведём 1: {mask_str(h['oe'] & h['val'])}")
    if h["ver"] >= 2:
        print(f"G13: {h['gclk']} тактов за окно ≈ {h['gclk'] / t / 1e6:.3f} МГц (по OSCB, ±несколько %)")
    print(f"{'вывод':6} {'площадка':9} {'банк':4} {'ур.':3} {'был':4} {'фронтов':>7}  функция")
    for i, (b, pad, bank, fn) in enumerate(PINS):
        seen = ("1" if h["was1"] >> i & 1 else "") + ("0" if h["was0"] >> i & 1 else "")
        drv = "←" + str(h["val"] >> i & 1) if h["oe"] >> i & 1 else ""
        print(f"{b:6} {pad:9} {bank:4} {h['lvl'] >> i & 1:3} {seen:4} {h['edges'][i]:7}  {fn} {drv}")


def cmd_release(a):
    parse(openocd(drive(0, 0) + er1("")))
    print("все выводы — входы")


def cmd_scan(a):
    """Каждый вывод по очереди ведём в 1, затем в 0; остальные — входы. Читаем уровни
    после паузы. Пока все входы — опорный кадр. Выводы, которые снаружи держатся в 1, в 0 не
    ведём: D13 = 0 перезапускает конфигурацию ПЛИС (2026-10-25)."""
    base = header(parse(openocd(drive(0, 0) + [f"sleep {a.ms}"] + er1("")))[""])["lvl"]
    cmds = drive(0, 0) + [f"sleep {a.ms}"] + er1("base")
    for i in range(NP):
        for v in ((1, 0) if not base >> i & 1 or a.force0 else (1,)):
            cmds += drive(1 << i, v << i) + [f"sleep {a.ms}"] + er1(f"p{i}v{v}")
    cmds += drive(0, 0)
    res = parse(openocd(cmds, timeout=300))
    base = header(res["base"])["lvl"]
    print(f"все входы: в 1 — {mask_str(base)}")
    print(f"{'ведём':6} {'сам 1/0':7}  за 1 поднялись              за 0 опустились")
    full = (1 << NP) - 1
    for i, (b, *_rest) in enumerate(PINS):
        l1 = header(res[f"p{i}v1"])["lvl"]
        l0 = header(res[f"p{i}v0"])["lvl"] if f"p{i}v0" in res else base & ~(1 << i)
        me = 1 << i
        own = f"{l1 >> i & 1}/{l0 >> i & 1 if f'p{i}v0' in res else '-'}"
        up = l1 & ~base & full & ~me
        down = ~l0 & base & full & ~me
        mark = "" if own in ("1/0", "1/-") else "  ← вывод не идёт за своим уровнем"
        print(f"{b:6} {own:7}  {mask_str(up):27} {mask_str(down)}{mark}")


def cmd_hold(a):
    oe, val = parse_assign(a.assign)
    before = usb_devices()
    parse(openocd(drive(oe, val) + er1("")))
    time.sleep(a.sec)
    after = usb_devices()
    h = header(parse(openocd(er1("")))[""])
    if not a.keep:
        parse(openocd(drive(0, 0) + er1("")))
    print(f"вели: {' '.join(a.assign)}; уровни 1: {mask_str(h['lvl'])}")
    for k in sorted(set(before) | set(after)):
        if before.get(k) != after.get(k):
            print(f"  Windows {k}: {before.get(k, '—')}  →  {after.get(k, '—')}")
    if before == after:
        print("  в Windows без изменений" + (f" (SLogic: {', '.join(v for v in after.values() if v.startswith('0000:'))})" if after else ""))


def cmd_cap(a):
    oe, val = parse_assign(a.assign)
    out = openocd(er2(0xA << 28 | 1 << 27) + er2(0xA << 28) + drive(oe, val) +
                  [f"sleep {int(a.sec * 1000)}"] + (drive(0, 0) if not a.keep else []) + er1(""))
    h = header(parse(out)[""])
    n = min(h["wptr"], a.max)
    print(f"записано {h['wptr']} смен{' (буфер полон)' if h['full'] else ''}, читаю {n}")
    words = []
    for base in range(0, n, a.chunk):
        cmds = []
        for addr in range(base, min(n, base + a.chunk * 8), a.chunk):
            cmds += er2(0xA << 28 | addr) + er1(f"a{addr}", H + a.chunk)
        res = parse(openocd(cmds), H + a.chunk)
        for addr in range(base, min(n, base + a.chunk * 8), a.chunk):
            words += res[f"a{addr}"][H:H + min(a.chunk, n - addr)]
        if len(words) >= n:
            break
    words = words[:n]
    t, prev = 0, None
    for x in words:
        dt, lv = x >> 22, x & ((1 << NP) - 1)
        t += dt
        ch = lv ^ prev if prev is not None else lv
        sat = "≥" if dt == 1023 else " "
        print(f"{t / F_OSC * 1e6:12.2f} мкс {sat}{dt:5}  1: {mask_str(lv):40}  смена: {mask_str(ch)}")
        prev = lv


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("frame").set_defaults(fn=cmd_frame)
    sp.add_parser("release").set_defaults(fn=cmd_release)
    p = sp.add_parser("scan")
    p.add_argument("--ms", type=int, default=20, help="пауза после смены уровня")
    p.add_argument("--force0", action="store_true", help="вести в 0 и те, что снаружи в 1 (опасно: D13)")
    p.set_defaults(fn=cmd_scan)
    for name, fn in (("hold", cmd_hold), ("cap", cmd_cap)):
        p = sp.add_parser(name)
        p.add_argument("assign", nargs="+", help="ШАРИК=0|1|z")
        p.add_argument("--sec", type=float, default=2.0)
        p.add_argument("--keep", action="store_true", help="не отпускать выводы в конце")
        if name == "cap":
            p.add_argument("--max", type=int, default=2000, help="сколько смен читать")
            p.add_argument("--chunk", type=int, default=512)
        p.set_defaults(fn=fn)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
