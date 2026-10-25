#!/usr/bin/env python3
"""Трасса STM32F4 → SLogic16U3, шаг 1: проверка, что данные TPIU доходят.

Источник — tools/slogic/trace/stm32 (ITM-счётчик через TPIU), приёмник —
образ gw/tracela.v в SRAM ПЛИС, читается через JTAG (FT2232H, OpenOCD).

    python3 trace.py stm --src hsi --hdiv 512 --width 4   # режим источника (ядро под сбросом)
    python3 trace.py freq                                  # частоты линий по частотомеру образа
    python3 trace.py cap --mode 0 --save run.json          # смены уровней: фаза данных, разбор
    python3 trace.py cap --mode 1 --dly 20                 # выборка по фронту TRACECLK (OSCB)
    python3 trace.py cap --mode 2 --dly 0                  # IDDR от TRACECLK, IODELAY 0..255
    python3 trace.py decode run.json                       # разбор сохранённой записи
    python3 trace.py encode --out stream.hex               # синтетический поток для tb.v
"""

import argparse
import bisect
import json
import math
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
OPENOCD = os.path.expanduser("~/.local/opt/oss-cad-suite/bin/openocd")
F_OSC = 2 ** 26 / 2.24  # OSCB "210"/4 на GW5AT-15 — ~30 МГц (измерено при прозвонке, journal Э3)
H = 14  # слов заголовка ER1
MAGIC = 0x414E4C52  # "RLNA"

FPGA_CFG = """adapter driver ftdi
ftdi vid_pid 0x0403 0x6010
ftdi channel 0
ftdi layout_init 0x0008 0x000b
adapter speed 2000
transport select jtag
jtag newtap gw5a tap -irlen 8 -expected-id 0x0001681b
"""
# Две одинаковые FT2232H без серийников (наша и отладчик на EVU-BA-2.5): адаптер ПЛИС —
# по месту на шине USB, например RLN_FPGA_USB=1-2 (см. /sys/bus/usb/devices).
if os.environ.get("RLN_FPGA_USB"):
    FPGA_CFG += f"adapter usb location {os.environ['RLN_FPGA_USB']}\n"

# ---- источник: STM32F4-Discovery через ST-LINK ----
# На HCLK в десятки кГц ST-LINK не держит связь с бегущим ядром, поэтому режим
# пишется под сбросом (ядро на HSI 16 МГц), прошивка читает его при старте.
CFG_ADDR = 0x20000000
CFG_MAGIC = 0x544E4C52
SRC = {"hsi": 0, "hse": 1, "pll": 2}


def openocd(args, cmd, timeout=60):
    r = subprocess.run([OPENOCD] + args + ["-c", cmd], capture_output=True, text=True, timeout=timeout)
    return r.stdout + r.stderr


def stm_set(src, pll_n, hdiv, width, burst, idle, n0=None, ospeed=3, etm=1):
    """n0 — начальное значение счётчика ITM (поле n), иначе продолжает с прошлого;
    ospeed — крутизна выводов трассы (OSPEEDR 0..3)."""
    words = [CFG_MAGIC, 0, SRC[src], pll_n, hdiv, width, burst, idle]
    setn = f"write_memory {CFG_ADDR + 0x2C:#x} 32 {n0:#x}; " if n0 is not None else ""
    setn += f"write_memory {CFG_ADDR + 0x34:#x} 32 {ospeed}; write_memory {CFG_ADDR + 0x38:#x} 32 {etm}; "
    cmd = ("init; reset halt; "
           f"write_memory {CFG_ADDR:#x} 32 {{{' '.join(hex(w) for w in words)}}}; " + setn +
           f"puts \"CFG [read_memory {CFG_ADDR:#x} 32 16]\"; resume; shutdown")
    out = openocd(["-f", "board/stm32f4discovery.cfg",
                   "-c", "reset_config srst_only srst_nogate connect_assert_srst"], cmd)
    m = re.search(r"^CFG (.*)$", out, re.M)
    if not m:
        sys.exit("ST-LINK: нет ответа\n" + out[-1500:])
    v = [int(x, 16) for x in m[1].split()]
    print(f"прошлый прогон: hclk {v[9]} Гц, err {v[10]}, отправлено {v[11]}, переприменений трассы {v[12]}, "
          f"ETMIDR {v[15]:08x}")
    base = {"hsi": 16e6, "hse": 8e6, "pll": pll_n * 0.5e6}[src]
    print(f"задано: {src} / {hdiv}, HCLK {base / hdiv / 1e3:g} кГц, TRACECLK ≈ {base / hdiv / 2e3:g} кГц, "
          f"порт {width} бит")


# ---- приёмник: JTAG ПЛИС ----

def fpga(cmds):
    out = openocd(["-c", FPGA_CFG.replace("\n", "; ")], "init; " + "; ".join(cmds) + "; shutdown", timeout=120)
    return out


def er2(word):
    return [f"irscan gw5a.tap 0x43", f"drscan gw5a.tap 32 {word:#x}"]


def er1(tag, nwords):
    # +1 слово: на железе первым идёт лишний бит (см. jprobe), кадр ищется по метке
    return ["irscan gw5a.tap 0x42", f"puts \"DR{tag} [drscan gw5a.tap {32 * (nwords + 1)} 0]\""]


def align(v, nwords):
    for off in range(8):
        w = [(v >> (off + 32 * j)) & 0xFFFFFFFF for j in range(nwords)]
        if w[0] == MAGIC:
            return w
    return None


def parse(out, nwords):
    res = {}
    for m in re.finditer(r"^DR(\w*) (\S+)$", out, re.M):
        w = align(int(m[2], 16), nwords)
        if w is None:
            sys.exit(f"нет \"RLNA\" в ER1 ({m[1]}): образ не загружен?\n" + out[-800:])
        res[m[1]] = w
    if not res:
        sys.exit("OpenOCD не вернул данные:\n" + out[-1500:])
    return res


def command(mode=0, dly=0, addr=0, arm=False):
    return 0xA << 28 | int(arm) << 27 | (mode & 3) << 25 | (dly & 0x1FF) << 16 | (addr & 0xFFFF)


def header(w):
    st = w[3]
    return {"ver": w[1] & 0xFF, "depth_log2": w[1] >> 8 & 0xFF, "win_log2": w[1] >> 16 & 0xFF,
            "seq": w[1] >> 24, "cmd": w[2], "wptr": st & 0x1FFFF, "mode": st >> 28 & 3,
            "run": st >> 30 & 1, "full": st >> 31, "miss": w[4],
            "edges": [x & 0xFFFFFF for x in w[5:10]], "tclk": w[10],
            "iodelay": [w[11] >> (8 * i) & 0xFF for i in range(4)],
            "er2_sr": w[12], "er2_shifts": w[13] & 0xFFFF, "er2_updates": w[13] >> 16}


# перестановка линий данных под проводку стенда (2026-10-25 PE5/PE6 стояли наоборот — было "0132")
LANES = "0123"

LINES = ["TRACECLK", "TRACED0", "TRACED1", "TRACED2", "TRACED3"]


def cmd_freq(a):
    w = parse(fpga(er1("", H)), H)[""]
    h = header(w)
    t = 2 ** h["win_log2"] / F_OSC
    print(f"окно 2^{h['win_log2']} ≈ {t:.3f} с, seq {h['seq']}")
    for name, e in zip(LINES, h["edges"]):
        print(f"  {name:9} {e:9} фронтов  {e / 2 / t / 1e3:10.3f} кГц (по OSCB, честно до ~10 МГц)")
    print(f"  TRACECLK  {h['tclk']:9} тактов   {h['tclk'] / t / 1e3:10.3f} кГц (счётчик в домене TRACECLK)")
    print(f"  IODELAY по линиям: {h['iodelay']}")
    return h


def lane_delay(lane, steps):
    """Команда 0xB: IODELAY линии TRACED<lane> (None — всех четырёх)."""
    return 0xB << 28 | (lane is None) << 26 | (lane or 0) << 24 | steps & 0xFF


def capture(mode, dly, chunk=1024, wait=30.0, iodelay=None):
    """Пуск записи, ожидание заполнения, чтение буфера. Режим 2: dly — IODELAY всех
    линий, либо iodelay — список из четырёх задержек по линиям."""
    pre = []
    if mode == 2:
        iodelay = iodelay or [dly] * 4
        for i, d in enumerate(iodelay):
            pre += er2(lane_delay(i, d))
        dly = 0
    w = parse(fpga(pre + er2(command(mode, dly, arm=True)) + er2(command(mode, dly)) + er1("", H)), H)[""]
    h = header(w)
    if mode == 2 and h["iodelay"] != iodelay:
        print(f"! IODELAY в образе {h['iodelay']}, ждали {iodelay}")
    if h["cmd"] != command(mode, dly):
        print(f"! эхо команды {h['cmd']:08x}, ждали {command(mode, dly):08x} — TDI сдвинут?")
    depth = 1 << h["depth_log2"]
    t0 = time.time()
    while not h["full"]:
        if time.time() - t0 > wait:
            print(f"! буфер не заполнился за {wait:.0f} с: {h['wptr']} слов — пишу что есть")
            break
        time.sleep(0.5)
        h = header(parse(fpga(er1("", H)), H)[""])
    n = depth if h["full"] else h["wptr"]
    if n == 0:
        return h, []
    cmds = []
    for a in range(0, n, chunk):
        cmds += er2(command(mode, dly, addr=a)) + er1(f"{a}", H + chunk)
    res = parse(fpga(cmds), H + chunk)
    words = []
    for a in range(0, n, chunk):
        words += res[str(a)][H:H + min(chunk, n - a)]
    return h, words


# ---- разбор записи ----

def events(words):
    """Режим 0: [(время в тактах, линии)] с разворотом 27-битной метки времени."""
    ev, hi, last = [], 0, None
    for x in words:
        ts = x >> 5
        if last is not None and ts < last:
            hi += 1 << 27
        last = ts
        ev.append((hi + ts, x & 0x1F))
    return ev


def phase_analysis(ev):
    """Фазы смен данных внутри полупериода TRACECLK (0 — на фронте такта)."""
    clk = [(t, v & 1) for t, v in ev]
    edges = [t for (t, c), (_, c0) in zip(clk[1:], clk) if c != c0]
    data_ch = [t for (t, v), (_, v0) in zip(ev[1:], ev) if (v ^ v0) & 0x1E]
    ph = []
    for t in data_ch:
        k = bisect.bisect_right(edges, t) - 1
        if 0 <= k < len(edges) - 1:
            ph.append((t - edges[k]) / (edges[k + 1] - edges[k]))
    return edges, ph


def sample_nibbles(ev, edges, phi):
    times = [t for t, _ in ev]
    out = []
    for e0, e1 in zip(edges, edges[1:]):
        t = e0 + phi * (e1 - e0)
        k = bisect.bisect_right(times, t) - 1
        out.append(ev[k][1] >> 1 if k >= 0 else 0)
    return out


def nibbles_mode1(words):
    return [(x >> (4 * i)) & 0xF for x in words for i in range(8)]


SYNC = b"\xff\xff\xff\x7f"


def to_bytes(samples, width, off):
    bits = [(s >> b) & 1 for s in samples for b in range(width)]
    bits = bits[off:]
    return bytes(sum(bits[8 * i + b] << b for b in range(8)) for i in range(len(bits) // 8))


def frames(hw, st):
    """Кадры форматтера (16 байт) из потока полуслов, ID → bytes."""
    data, cur = {}, None
    b = b"".join(x.to_bytes(2, "little") for x in hw)
    for p in range(0, len(b) - 15, 16):
        f, aux = b[p:p + 16], b[p + 15]
        st["frames"] += 1
        for i in range(8):
            x, ab = f[2 * i], aux >> i & 1
            nxt = f[2 * i + 1] if i < 7 else None
            if x & 1:
                if ab and nxt is not None:
                    data.setdefault(cur, bytearray()).append(nxt)
                cur = x >> 1
                if not ab and nxt is not None:
                    data.setdefault(cur, bytearray()).append(nxt)
            else:
                data.setdefault(cur, bytearray()).append(x & 0xFE | ab)
                if nxt is not None:
                    data.setdefault(cur, bytearray()).append(nxt)
    return data


def tpiu(samples, width):
    """Разбор потока TPIU. Синхронизация: полуслово 0x7FFF (байты FF 7F) — в непрерывном
    режиме TPIU вставляет его в простое в любом месте, даже внутри кадра; полная 0x7FFFFFFF
    задаёт начало кадра. Сдвиг бит ищется по числу полуслов 0x7FFF; если полной
    синхронизации нет, начало кадра (одно из 8 положений) — по непрерывности счётчика ITM.
    Возвращает (сдвиг, {id: bytes}, статистика)."""
    best = None
    for off in range(16):
        b = to_bytes(samples, width, off % 8 + 8 * (off // 8))
        hw = [int.from_bytes(b[i:i + 2], "little") for i in range(0, len(b) - 1, 2)]
        n = hw.count(0x7FFF)
        if best is None or n > best[0]:
            best = (n, off, hw)
    n, off, hw = best
    if n == 0:
        return None, {}, {"half": 0}
    st = {"half": 0, "full": 0, "frames": 0, "phase": None}
    clean, starts = [], []
    for i, x in enumerate(hw):
        if x == 0x7FFF:
            if clean and clean[-1] == 0xFFFF:  # 0xFFFF 0x7FFF — полная синхронизация
                clean.pop()
                st["full"] += 1
                starts.append(len(clean))
            else:
                st["half"] += 1
            continue
        clean.append(x)
    if starts:
        ph = starts[0] % 8
        cand = [ph]
    else:
        cand = range(8)
    res = None
    for ph in cand:
        s = dict(st, frames=0, phase=ph)
        data = frames(clean[ph:], s)
        vals, _ = itm(bytes(data.get(1, b"")))
        score = len(vals) - 10 * len(check(vals))
        if res is None or score > res[0]:
            res = (score, data, s)
    return off, res[1], res[2]


def itm(b):
    """Пакеты ITM: значения стимул-порта 0 (32 бита) и счётчики служебных."""
    vals, st, i = [], {"sync": 0, "overflow": 0, "other": 0, "bad": 0}, 0
    while i < len(b):
        h = b[i]
        if h == 0:
            j = i
            while j < len(b) and b[j] == 0:
                j += 1
            if j < len(b) and b[j] == 0x80 and j - i >= 5:
                st["sync"] += 1
                i = j + 1
            else:
                i = j
            continue
        if h == 0x70:
            st["overflow"] += 1
            i += 1
            continue
        if h & 3:  # программный (SWIT) или аппаратный источник
            n = {1: 1, 2: 2, 3: 4}[h & 3]
            if i + 1 + n > len(b):
                break
            v = int.from_bytes(b[i + 1:i + 1 + n], "little")
            if not h & 4 and h >> 3 == 0 and n == 4:
                vals.append(v)
            else:
                st["other"] += 1
            i += 1 + n
            continue
        # метка времени или расширение: продолжение по биту 7
        st["other"] += 1
        i += 1
        if h & 0x80:
            while i < len(b) and b[i] & 0x80:
                i += 1
            i += 1
    return vals, st


def itm_packets(b):
    """Пакеты ITM целиком, для показа: [(смещение, байты, описание)]."""
    out, i = [], 0
    while i < len(b):
        h = b[i]
        if h == 0:
            j = i
            while j < len(b) and b[j] == 0:
                j += 1
            if j < len(b) and b[j] == 0x80:
                out.append((i, b[i:j + 1], "синхронизация"))
                i = j + 1
            else:
                out.append((i, b[i:j], "нули"))
                i = j
        elif h == 0x70:
            out.append((i, b[i:i + 1], "переполнение"))
            i += 1
        elif h & 3:
            n = {1: 1, 2: 2, 3: 4}[h & 3]
            v = int.from_bytes(b[i + 1:i + 1 + n], "little")
            what = "аппаратный источник" if h & 4 else f"стимул-порт {h >> 3}"
            out.append((i, b[i:i + 1 + n], f"{what}: {v:#0{2 + 2 * n}x} ({v})"))
            i += 1 + n
        else:
            j = i + 1
            if h & 0x80:
                while j < len(b) and b[j] & 0x80:
                    j += 1
                j += 1
            out.append((i, b[i:j], "метка времени / расширение"))
            i = j
    return out


# ---- ETM (ETMv3.5, Cortex-M4): пакеты и инструкции ----
# Правила — по OpenCSD (decoder/source/etmv3): атом P-заголовка — одна инструкция
# (E — выполнена, N — не прошла по условию); пакет адреса ветвления идёт после
# атома косвенного перехода и сжат относительно прошлого выданного адреса.
OBJDUMP = os.path.expanduser("~/.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/bin/arm-none-eabi-objdump")
ELF = os.path.join(HERE, "stm32", "trace.elf")
COND = "(eq|ne|cs|hs|cc|lo|mi|pl|vs|vc|hi|ls|ge|lt|gt|le|al)?"


def etm_packets(b, alt=True):
    """Разбор потока ETM в пакеты: [{"off", "raw", "type", ...}]."""
    out, i, last = [], 0, 0
    synced = False
    while i < len(b):
        h, st = b[i], i
        pk = {"off": i}
        if not synced:  # до первой A-sync — пропуск
            if h == 0:
                j = i
                while j < len(b) and b[j] == 0:
                    j += 1
                if j < len(b) and b[j] == 0x80 and j - i >= 5:
                    synced = True
                    out.append(dict(pk, raw=b[i:j + 1], type="A-sync"))
                    i = j + 1
                    continue
            i += 1
            continue
        if h & 1:  # адрес ветвления
            j, C, val, bits = i, True, 0, 0
            exc = False
            while C and j - i < 4 and j < len(b):
                x = b[j]
                C = bool(x & 0x80)
                if j == i:
                    v, n = (x & 0x7E) >> 1, 6
                elif alt and not C:
                    exc = bool(x & 0x40)
                    v, n = x & 0x3F, 6
                else:
                    v, n = x & 0x7F, 7
                val |= v << bits
                bits += n
                j += 1
            if C and j < len(b):
                x = b[j]
                exc = bool(x & 0x40)
                val |= (x & 0xF) << bits
                bits += 4
                j += 1
            val <<= 1
            bits += 1
            e = None
            if exc and j < len(b):  # байты исключения
                e0 = b[j]
                j += 1
                e = (e0 >> 1) & 0xF
                if e0 & 0x80 and j < len(b):
                    e1 = b[j]
                    j += 1
                    if not e1 & 0x40:
                        e |= (e1 & 0x1F) << 4
                        if e1 & 0x80 and j < len(b):
                            j += 1
            mask = (1 << bits) - 1 if bits < 32 else 0xFFFFFFFF
            last = (last & ~mask) | (val & mask)
            pk.update(raw=b[i:j], type="ветвление", addr=last, exc=e)
            i = j
        elif h & 0x81 == 0x80:  # P-заголовок
            if h & 3 == 0:
                E, N = (h >> 2) & 0xF, (h >> 6) & 1
                atoms = "E" * E + "N" * N
            elif h & 3 == 2:
                atoms = ("N" if h & 8 else "E") + ("N" if h & 4 else "E")
            else:
                atoms = ""
            pk.update(raw=b[i:i + 1], type="P-заголовок", atoms=atoms)
            i += 1
        elif h == 0:
            j = i
            while j < len(b) and b[j] == 0:
                j += 1
            pk.update(raw=b[i:j + 1], type="A-sync")
            i = j + 1
        elif h == 0x08:  # I-sync: инфо, адрес (4), возможно LSiP
            if i + 6 > len(b):
                break
            info = b[i + 1]
            a = int.from_bytes(b[i + 2:i + 6], "little")
            j = i + 6
            if info & 0x80:
                while j < len(b) and b[j] & 0x80:
                    j += 1
                j += 1
            last = a & ~1
            reason = ["периодическая", "трасса включена", "после переполнения", "выход из отладки"][(info >> 5) & 3]
            pk.update(raw=b[i:j], type="I-sync", addr=last, thumb=a & 1, reason=reason)
            i = j
        elif h in (0x0C, 0x66, 0x7E, 0x76):
            pk.update(raw=b[i:i + 1], type={0x0C: "триггер", 0x66: "пусто", 0x7E: "вход в исключение",
                                            0x76: "выход из исключения"}[h])
            i += 1
        elif h & 0xFB == 0x42:  # метка времени
            j = i + 1
            while j < len(b) and b[j] & 0x80:
                j += 1
            pk.update(raw=b[i:j + 1], type="метка времени")
            i = j + 1
        else:
            pk.update(raw=b[i:i + 1], type="неизвестный")
            synced = False  # ждать A-sync
            i += 1
        out.append(pk)
    return out


def disasm(elf=ELF):
    """{адрес: (размер, текст, вид, цель)}; вид: None, "direct", "indirect"."""
    r = subprocess.run([OBJDUMP, "-d", elf], capture_output=True, text=True)
    out, func = {}, ""
    for line in r.stdout.splitlines():
        m = re.match(r"^([0-9a-f]+) <(.*)>:$", line)
        if m:
            func = m[2]
            continue
        m = re.match(r"^\s*([0-9a-f]+):\t([0-9a-f ]+?)\s*\t(\S+)\s*(.*)$", line)
        if not m:
            continue
        a = int(m[1], 16)
        size = len(m[2].replace(" ", "")) // 2
        mn, ops = m[3], m[4].split("@")[0].strip()
        kind, tgt = None, None
        if re.fullmatch(r"b(l)?" + COND + r"(\.n|\.w)?", mn) or mn in ("cbz", "cbnz"):
            t = re.search(r"\b([0-9a-f]{7,8})\b", ops)
            if t:
                kind, tgt = "direct", int(t[1], 16)
        elif mn in ("bx", "blx") or mn.startswith(("tbb", "tbh")):
            kind = "indirect"
        elif mn.startswith(("pop", "ldm")) and "pc" in ops:
            kind = "indirect"
        elif re.match(r"(ldr|mov)", mn) and ops.startswith("pc"):
            kind = "indirect"
        out[a] = (size, f"{mn}\t{ops}".strip(), kind, tgt, func)
    return out


def etm_instructions(pkts, dis):
    """Восстановление выполненных инструкций: [(адрес, атом, текст, функция)] и
    события (I-sync, ветвления) со сверкой адреса."""
    rows, st = [], {"isync": 0, "isync_ok": 0, "isync_bad": 0, "lost": 0, "instr": 0, "E": 0, "N": 0}
    addr = None
    for p in pkts:
        t = p["type"]
        if t == "I-sync":
            st["isync"] += 1
            if addr is not None:
                st["isync_ok" if addr == p["addr"] else "isync_bad"] += 1
                if addr != p["addr"]:
                    rows.append(("!", f"I-sync {p['addr']:#010x}, а декодер ждал {addr:#010x}"))
            addr = p["addr"]
            rows.append(("sync", f"I-sync {addr:#010x} ({p['reason']})"))
        elif t == "ветвление":
            addr = p["addr"]
            rows.append(("br", f"адрес ветвления {addr:#010x}" + (f", исключение {p['exc']}" if p["exc"] else "")))
        elif t == "P-заголовок":
            for k, a in enumerate(p["atoms"]):
                if addr is None:
                    break
                ins = dis.get(addr)
                if ins is None:
                    rows.append(("!", f"нет инструкции по адресу {addr:#010x}"))
                    st["lost"] += 1
                    addr = None
                    break
                size, text, kind, tgt, func = ins
                rows.append((addr, a, text, func, p, k))
                st["instr"] += 1
                st[a] += 1
                if a == "E" and kind == "direct":
                    addr = tgt
                elif a == "E" and kind == "indirect":
                    addr = None  # ждём пакет адреса
                else:
                    addr += size
        elif t in ("вход в исключение", "выход из исключения"):
            rows.append(("ex", t))
    return rows, st


def check(vals):
    gaps = [(a, b) for a, b in zip(vals, vals[1:]) if (b - a) & 0xFFFFFFFF != 1]
    return gaps


def mode1_dly(r):
    """Режим 1 берёт выборку через dly + 1 тактов после того, как фронт прошёл синхронизатор."""
    return max(0, min(511, round(r["phi"] * r["half_period"]) - 1))


def report(h, words, width, phi=None, verbose=True, lanes="0123"):
    """Разбор записи; возвращает словарь итогов (для sweep и журнала)."""
    r = {"words": len(words), "mode": h["mode"], "miss": h["miss"]}
    if h["mode"] == 0:
        ev = events(words)
        edges, ph = phase_analysis(ev)
        r["edges"] = len(edges)
        if len(edges) < 4:
            print("фронтов TRACECLK в записи нет")
            return r
        hp = [b - a for a, b in zip(edges, edges[1:])]
        hps = sorted(hp)
        r["half_period"] = hps[len(hps) // 2]
        r["half_min"], r["half_max"] = hps[0], hps[-1]
        if verbose:
            print(f"событий {len(ev)}, фронтов TRACECLK {len(edges)}, полупериод (тактов OSCB): "
                  f"мин {hps[0]}, медиана {r['half_period']}, макс {hps[-1]} "
                  f"→ TRACECLK ≈ {F_OSC / 2 / r['half_period'] / 1e3:.2f} кГц")
        hist = [0] * 10
        for x in ph:
            hist[min(int(x * 10), 9)] += 1
        r["phase_hist"] = hist
        if verbose:
            print("смены данных по фазе полупериода (0 = фронт такта):")
            for k, c in enumerate(hist):
                print(f"  {k / 10:.1f}–{(k + 1) / 10:.1f} {c:7} " + "#" * min(60, c * 60 // max(1, max(hist))))
        if phi is None:
            # круговое среднее фазы смен; выборка — напротив
            sx = sum(math.cos(2 * math.pi * x) for x in ph)
            sy = sum(math.sin(2 * math.pi * x) for x in ph)
            m = (math.atan2(sy, sx) / (2 * math.pi)) % 1 if ph else 0.0
            phi = (m + 0.5) % 1
        r["phi"] = phi
        if verbose:
            print(f"выборка на фазе {phi:.2f}; для режима 1: dly ≈ {mode1_dly(r)} тактов")
        samples = sample_nibbles(ev, edges, phi)
    else:
        samples = nibbles_mode1(words)
        if verbose:
            print(f"полубайтов {len(samples)}" + (f", пропущено фронтов {h['miss']}" if h["mode"] == 1 else ""))
    r["samples"] = len(samples)
    if lanes != "0123":  # бит i выборки = линия TRACED<lanes[i]> по проводке
        samples = [sum((x >> int(c) & 1) << i for i, c in enumerate(lanes)) for x in samples]
    off, data, st = tpiu(samples, width)
    r["tpiu"] = st
    if off is None:
        print("синхронизация TPIU (FF 7F) не найдена")
        if verbose:
            print("первые выборки:", "".join(f"{s:x}" for s in samples[:128]))
        return r
    r["ids"] = {str(k): len(v) for k, v in data.items()}
    vals, ist = itm(bytes(data.get(1, b"")))
    gaps = check(vals)
    r.update(values=len(vals), gaps=len(gaps), itm=ist,
             first=vals[0] if vals else None, last=vals[-1] if vals else None)
    if verbose:
        print(f"TPIU: сдвиг {off} бит, синхронизаций: полных {st['full']}, полуслов {st['half']}; "
              f"начало кадра {st['phase']}, кадров {st['frames']}, "
              f"байтов по ID: {r['ids']}")
        print(f"ITM: значений {len(vals)}, {('с ' + str(vals[0]) + ' по ' + str(vals[-1])) if vals else ''}; "
              f"разрывов {len(gaps)}; служебные {ist}")
        for a, b in gaps[:10]:
            print(f"  разрыв {a:#x} → {b:#x}")
    ok = vals and not gaps
    print("ИТОГ: " + ("данные идут, счётчик непрерывен" if ok else "ОШИБКИ"))
    return r


def cmd_cap(a):
    h, words = capture(a.mode, a.dly, iodelay=a.iodelay)
    print(f"записано {len(words)} слов, режим {h['mode']}")
    if a.save:
        json.dump({"header": h, "words": words, "width": a.width, "note": a.note}, open(a.save, "w"))
    return report(h, words, a.width, a.phi, lanes=a.lanes)


def cmd_sweep(a):
    """Перебор скоростей: для каждого делителя AHB — частотомер, режим 0 (фаза, полупериод),
    режим 1 с задержкой от режима 0. Итоги — в runs/sweep-<src>.json."""
    out = []
    for hdiv in a.hdiv:
        print(f"\n===== {a.src} / {hdiv} =====")
        stm_set(a.src, a.pll_n, hdiv, a.width, 16, 64)
        time.sleep(1.2)
        h = cmd_freq(a)
        row = {"src": a.src, "hdiv": hdiv, "edges": h["edges"]}
        h0, w0 = capture(0, 0, wait=10)
        r0 = report(h0, w0, a.width, verbose=False, lanes=a.lanes)
        row["m0"] = r0
        if "half_period" in r0:
            dly = mode1_dly(r0)
            h1, w1 = capture(1, dly, wait=10)
            row["m1"] = dict(report(h1, w1, a.width, verbose=False, lanes=a.lanes), dly=dly)
        out.append(row)
        json.dump(out, open(os.path.join(HERE, "runs", f"sweep-{a.src}.json"), "w"), indent=1)
    print("\nделитель  TRACECLK, кГц  полупериод  режим 0: знач/разрывов   режим 1: знач/разрывов/пропуск фронтов")
    for row in out:
        r0, r1 = row["m0"], row.get("m1", {})
        f = row["edges"][0] / 2 / (2 ** 24 / F_OSC) / 1e3
        print(f"{row['hdiv']:8} {f:14.1f} {r0.get('half_period', '-'):>11}  "
              f"{r0.get('values', 0):8}/{r0.get('gaps', '-'):<8}  {r1.get('values', 0):8}/{r1.get('gaps', '-')}/{r1.get('miss', '-')}")


POINTS2 = ["hsi:0:512", "hsi:0:64", "hsi:0:8", "hsi:0:2", "hsi:0:1",
           "pll:336:16", "pll:336:8", "pll:336:4", "pll:336:2",
           "pll:100:1", "pll:136:1", "pll:200:1", "pll:264:1", "pll:300:1", "pll:336:1"]


def cmd_sweep2(a):
    """Режим 2 (IDDR от TRACECLK): частоты источника × задержки IODELAY.
    Итоги — в runs/sweep2.json, таблица: значений/разрывов на каждую задержку."""
    path = os.path.join(HERE, "runs", a.out)
    out = []
    for pt in a.points:
        src, n, hdiv = pt.split(":")
        n, hdiv = int(n) or 336, int(hdiv)
        print(f"\n===== {pt} =====")
        stm_set(src, n, hdiv, 4, 16, 64, a.n0, a.ospeed)
        time.sleep(1.5)
        h = cmd_freq(a)
        row = {"point": pt, "ospeed": a.ospeed, "n0": a.n0, "tclk_hz": h["tclk"] / (2 ** h["win_log2"] / F_OSC), "dly": {}}
        for d in a.dly:
            hh, w = capture(2, d, wait=10)
            r = report(hh, w, 4, verbose=False)
            row["dly"][d] = {k: r.get(k) for k in ("values", "gaps", "tpiu", "samples")}
            print(f"  IODELAY {d:3}: значений {r.get('values', 0)}, разрывов {r.get('gaps', '-')}")
        out.append(row)
        json.dump(out, open(path, "w"), indent=1)
    print("\nTRACECLK, МГц  " + " ".join(f"{d:>9}" for d in a.dly) + "   (значений/разрывов по IODELAY)")
    for row in out:
        cells = []
        for d in a.dly:
            r = row["dly"][d]
            cells.append(f"{r['values'] or 0}/{r['gaps'] if r['gaps'] is not None else '-'}")
        print(f"{row['tclk_hz'] / 1e6:13.3f}  " + " ".join(f"{c:>9}" for c in cells) + f"   {row['point']}")


def cmd_lanes(a):
    """Окно каждой линии: остальные три — на base, линия L — по списку задержек.
    Итоги — в runs/<out>: значений/разрывов на каждую пару (линия, задержка)."""
    src, n, hdiv = a.point.split(":")
    stm_set(src, int(n) or 336, int(hdiv), 4, 16, 64)
    time.sleep(1.5)
    h = cmd_freq(a)
    res = {"point": a.point, "tclk_hz": h["tclk"] / (2 ** h["win_log2"] / F_OSC), "base": a.base, "lanes": {}}
    for lane in a.lane:
        res["lanes"][lane] = {}
        for d in a.dly:
            iod = [a.base] * 4
            iod[lane] = d
            hh, w = capture(2, 0, wait=10, iodelay=iod)
            r = report(hh, w, 4, verbose=False)
            res["lanes"][lane][d] = [r.get("values", 0), r.get("gaps")]
            print(f"  TRACED{lane} IODELAY {d:3}: значений {r.get('values', 0)}, разрывов {r.get('gaps', '-')}")
        json.dump(res, open(os.path.join(HERE, "runs", a.out), "w"), indent=1)
    print(f"\n{a.point}, TRACECLK {res['tclk_hz'] / 1e6:.3f} МГц, остальные линии на {a.base}; "
          "+ — чисто, . — сбой")
    print("        " + "".join(f"{d:>4}" for d in a.dly))
    for lane, row in res["lanes"].items():
        print(f"TRACED{lane} " + "".join(f"{'+' if v[0] > 100 and v[1] == 0 else '.':>4}" for v in row.values()))


def cmd_show(a):
    """Итоговая трасса: пакеты ITM и ETM, восстановленные инструкции. Полный листинг —
    в файл (--out), на экран — первые строки каждого уровня."""
    if a.file:
        d = json.load(open(a.file))
        h, words = d["header"], d["words"]
    else:
        h, words = capture(2, 0, iodelay=[a.dly] * 4)
        if a.save:
            json.dump({"header": h, "words": words, "width": 4, "note": "show"}, open(a.save, "w"))
    samples = nibbles_mode1(words)
    off, data, st = tpiu(samples, 4)
    lines = []
    w = lines.append
    t = 2 ** h["win_log2"] / F_OSC
    w(f"Запись: {len(words)} слов = {len(samples)} полубайт, TRACECLK {h['tclk'] / t / 1e6:.2f} МГц, "
      f"IODELAY {h['iodelay']}")
    w(f"TPIU: синхронизаций полных {st['full']}, полуслов {st['half']}, кадров {st['frames']}; "
      "байтов по ID: " + ", ".join(f"{k}: {len(v)}" for k, v in sorted(data.items(), key=lambda x: str(x[0]))))
    itmb, etmb = bytes(data.get(1, b"")), bytes(data.get(2, b""))
    vals, ist = itm(itmb)
    gaps = check(vals)
    w(f"ITM (ID 1): {len(vals)} значений счётчика, разрывов {len(gaps)}")
    pk = etm_packets(etmb, alt=bool(a.alt))
    dis = disasm()
    rows, est = etm_instructions(pk, dis)
    kinds = {}
    for p in pk:
        kinds[p["type"]] = kinds.get(p["type"], 0) + 1
    w(f"ETM (ID 2): {len(etmb)} байт, пакетов {len(pk)}: " + ", ".join(f"{k} {v}" for k, v in kinds.items()))
    w(f"инструкций {est['instr']} (E {est['E']}, N {est['N']}); I-sync {est['isync']}, из них сверено с "
      f"декодером {est['isync_ok'] + est['isync_bad']}: совпало {est['isync_ok']}, нет {est['isync_bad']}; "
      f"потерь адреса {est['lost']}")
    head = list(lines)

    def section(title, items, n):
        w("")
        w(f"=== {title} ===")
        head.append("")
        head.append(f"=== {title} (первые {n} из {len(items)}) ===")
        for k, x in enumerate(items):
            w(x)
            if k < n:
                head.append(x)

    section("ITM: пакеты", [f"{o:6}  {r.hex(' '):20} {txt}" for o, r, txt in itm_packets(itmb)], a.n_itm)

    def etm_txt(p):
        x = p["type"]
        if x == "P-заголовок":
            x += f" {p['atoms']}"
        elif x in ("ветвление", "I-sync"):
            x += f" → {p['addr']:#010x} {func_of(dis, p['addr'])}"
            if x.startswith("I-sync"):
                x += f" ({p['reason']})"
        return f"{p['off']:6}  {p['raw'].hex(' '):20} {x}"
    section("ETM: пакеты", [etm_txt(p) for p in pk], a.n_etm)

    def ins_txt(r):
        if isinstance(r[0], int):
            return f"  {r[0]:08x}  {r[1]}  {r[3]:12} {r[2]}"
        return f"  -- {r[1]}"
    section("ETM: инструкции", [ins_txt(r) for r in rows], a.n_ins)
    print("\n".join(head))
    if a.out:
        open(a.out, "w").write("\n".join(lines) + "\n")
        print(f"\nполный листинг: {a.out}")


def cmd_table(a):
    """Кусок трассы таблицей Markdown: строка исходника → инструкция → пакет ETM и атом →
    что сделал декодер. Окно — с n-го (--skip) появления адреса --start, --count инструкций."""
    d = json.load(open(a.file))
    samples = nibbles_mode1(d["words"])
    _, data, _ = tpiu(samples, 4)
    pk = etm_packets(bytes(data.get(2, b"")), alt=True)
    dis = disasm()
    rows = [r for r in etm_instructions(pk, dis)[0] if isinstance(r[0], int)]
    hits = [i for i, r in enumerate(rows) if r[0] == a.start]
    if len(hits) <= a.skip:
        sys.exit(f"адрес {a.start:#x} встречается {len(hits)} раз")
    win = rows[hits[a.skip]:hits[a.skip] + a.count]
    a2l = subprocess.run([OBJDUMP.replace("objdump", "addr2line"), "-e", ELF] + [hex(r[0]) for r in win],
                         capture_output=True, text=True).stdout.splitlines()
    a2l = [x.split(" (")[0] for x in a2l]  # «(discriminator N)»
    src = open(os.path.join(HERE, "stm32", "main.c")).read().splitlines()
    print("| Исходник `main.c` | Адрес | Инструкция | Пакет ETM (смещение: байт) | Атом | Декодер |")
    print("|---|---|---|---|---|---|")
    prev_line, prev_pk = None, None
    for r, loc in zip(win, a2l):
        addr, atom, text, func, p, k = r
        ln = int(loc.split(":")[-1]) if loc.split(":")[-1].isdigit() else 0
        code = f"{ln}: `{src[ln - 1].strip()}`" if ln and ln != prev_line else ""
        prev_line = ln
        n = len(p["atoms"])
        pkt = f"{p['off']}: `{p['raw'].hex()}` = {p['atoms']}" if p is not prev_pk else "″"
        prev_pk = p
        size, _, kind, tgt, _ = dis[addr]
        if atom == "E" and kind == "direct":
            nxt = f"переход → {tgt:08x}"
        elif atom == "E" and kind == "indirect":
            nxt = "ждать адрес ветвления"
        elif kind:
            nxt = f"не выполнен → {addr + size:08x}"
        else:
            nxt = "дальше"
        ins = text.split("<")[0].strip().replace("\t", " ")
        print(f"| {code} | `{addr:08x}` | `{ins}` | {pkt} | {atom} ({k + 1}/{n}) | {nxt} |")


def func_of(dis, addr):
    x = dis.get(addr)
    return f"<{x[4]}>" if x else "<?>"


def cmd_decode(a):
    if a.file.endswith(".hex"):  # кадр ER1 из симуляции (tb.v): заголовок + буфер
        w = [int(x.replace("x", "0"), 16) for x in open(a.file).read().split()]
        h = header(w[:H])
        n = 1 << h["depth_log2"] if h["full"] else h["wptr"]
        print(f"запись: {n} слов, режим {h['mode']}, полон {h['full']}")
        report(h, w[H:H + n], a.width, a.phi, lanes=a.lanes)
        return
    d = json.load(open(a.file))
    report(d["header"], d["words"], d.get("width", a.width), a.phi, lanes=a.lanes)


# ---- синтетический поток для симуляции ----

def encode(nvals=160, burst=16, idle_syncs=3, width=4):
    def frames(data):
        out = bytearray()
        for k in range(0, len(data), 14):
            d = list(data[k:k + 14]) + [0] * (14 - len(data[k:k + 14]))  # хвост — нули (ITM их пропустит)
            f = [3] + [0] * 15  # байт 0: смена ID на 1, сразу
            aux = 0
            for j, x in enumerate(d):
                pos = j + 1
                if pos % 2:
                    f[pos] = x
                else:
                    f[pos] = x & 0xFE
                    aux |= (x & 1) << (pos // 2)
            f[15] = aux
            out += bytes(f)
        return out

    stream = bytearray(SYNC * 2)
    n = 0x12345670
    while n < 0x12345670 + nvals:
        itmb = bytearray()
        for _ in range(burst):
            itmb += bytes([0x03]) + n.to_bytes(4, "little")
            n += 1
        stream += frames(itmb) + SYNC * idle_syncs
    bits = [(x >> b) & 1 for x in stream for b in range(8)]
    return [sum(bits[i + b] << b for b in range(width)) for i in range(0, len(bits), width)]


def cmd_encode(a):
    s = encode(width=a.width)
    open(a.out, "w").write("\n".join(f"{x:x}" for x in s) + "\n")
    print(f"{len(s)} выборок по {a.width} бит → {a.out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("stm", help="режим источника")
    p.add_argument("--src", choices=SRC, default="hsi")
    p.add_argument("--pll-n", type=int, default=336, help="PLL: SYSCLK = n/2 МГц")
    p.add_argument("--hdiv", type=int, default=512)
    p.add_argument("--width", type=int, default=4)
    p.add_argument("--burst", type=int, default=16)
    p.add_argument("--idle", type=int, default=64)
    p.add_argument("--n0", type=lambda x: int(x, 0), help="начальное значение счётчика ITM")
    p.add_argument("--ospeed", type=int, default=3, help="крутизна выводов трассы OSPEEDR 0..3")
    p.add_argument("--etm", type=int, default=1, help="1 — трасса инструкций ETM (ID 2)")
    sub.add_parser("freq", help="частоты линий")
    p = sub.add_parser("cap", help="запись и разбор")
    p.add_argument("--mode", type=int, default=0)
    p.add_argument("--dly", type=int, default=0, help="режим 1: такты OSCB; режим 2: IODELAY всех линий")
    p.add_argument("--iodelay", type=int, nargs=4, help="режим 2: IODELAY по линиям TRACED0..3")
    p.add_argument("--width", type=int, default=4)
    p.add_argument("--phi", type=float, help="фаза выборки в режиме 0 (по умолчанию — напротив смен данных)")
    p.add_argument("--save")
    p.add_argument("--note", default="")
    p.add_argument("--lanes", default=LANES, help="перестановка линий данных: бит i = TRACED<lanes[i]>")
    p = sub.add_parser("sweep", help="перебор скоростей")
    p.add_argument("--src", choices=SRC, default="hsi")
    p.add_argument("--pll-n", type=int, default=336)
    p.add_argument("--hdiv", type=int, nargs="+", default=[512, 256, 128, 64, 16, 8, 4, 2, 1])
    p.add_argument("--width", type=int, default=4)
    p.add_argument("--lanes", default=LANES)
    p = sub.add_parser("sweep2", help="режим 2: частоты × задержки IODELAY")
    p.add_argument("--points", nargs="+", default=POINTS2, help="источник:pll_n:делитель")
    p.add_argument("--dly", type=int, nargs="+", default=[0, 64, 128, 192, 255])
    p.add_argument("--out", default="sweep2.json")
    p.add_argument("--ospeed", type=int, default=3, help="крутизна выводов трассы STM32")
    p.add_argument("--n0", type=lambda x: int(x, 0), help="начальное значение счётчика (0x0f000000 — худший шаблон)")
    p = sub.add_parser("lanes", help="режим 2: окно каждой линии по IODELAY")
    p.add_argument("--point", default="pll:248:1", help="источник:pll_n:делитель")
    p.add_argument("--base", type=int, default=48, help="задержка остальных линий")
    p.add_argument("--lane", type=int, nargs="+", default=[0, 1, 2, 3])
    p.add_argument("--dly", type=int, nargs="+", default=list(range(0, 256, 16)) + [255])
    p.add_argument("--out", default="lanes.json")
    p = sub.add_parser("show", help="итоговая трасса: пакеты ITM/ETM и инструкции")
    p.add_argument("--file", help="разобрать сохранённую запись вместо новой")
    p.add_argument("--save", help="сохранить запись")
    p.add_argument("--dly", type=int, default=32, help="IODELAY всех линий")
    p.add_argument("--alt", type=int, default=1, help="альтернативное кодирование адреса ветвления (ETMIDR[20])")
    p.add_argument("--out", default=os.path.join(HERE, "runs", "show.txt"))
    p.add_argument("--n-itm", type=int, default=8)
    p.add_argument("--n-etm", type=int, default=30)
    p.add_argument("--n-ins", type=int, default=60)
    p = sub.add_parser("table", help="кусок трассы: исходник → инструкция → пакет ETM (Markdown)")
    p.add_argument("file")
    p.add_argument("--start", type=lambda x: int(x, 0), default=0x8000356)
    p.add_argument("--skip", type=int, default=0, help="какое по счёту появление адреса взять")
    p.add_argument("--count", type=int, default=24)
    p = sub.add_parser("decode", help="разбор сохранённой записи")
    p.add_argument("file")
    p.add_argument("--width", type=int, default=4)
    p.add_argument("--lanes", default=LANES)
    p.add_argument("--phi", type=float)
    p = sub.add_parser("encode", help="синтетический поток TPIU для tb.v")
    p.add_argument("--out", default="stream.hex")
    p.add_argument("--width", type=int, default=4)
    a = ap.parse_args()
    if a.cmd == "stm":
        stm_set(a.src, a.pll_n, a.hdiv, a.width, a.burst, a.idle, a.n0, a.ospeed, a.etm)
    elif a.cmd == "freq":
        cmd_freq(a)
    elif a.cmd == "cap":
        cmd_cap(a)
    elif a.cmd == "sweep":
        cmd_sweep(a)
    elif a.cmd == "sweep2":
        cmd_sweep2(a)
    elif a.cmd == "lanes":
        cmd_lanes(a)
    elif a.cmd == "show":
        cmd_show(a)
    elif a.cmd == "table":
        cmd_table(a)
    elif a.cmd == "decode":
        cmd_decode(a)
    elif a.cmd == "encode":
        cmd_encode(a)


if __name__ == "__main__":
    main()
