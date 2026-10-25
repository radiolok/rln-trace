#!/usr/bin/env python3
"""Приём трассы BE-U1000 (RISC-V N-Trace через PIB, 4 бита) на SLogic16U3.

Приёмник — тот же образ tracela.v в режиме 2 (IDDR от TRACECLK), запись и чтение — из
../trace.py. Трассер настраивается через beu1000/ocd.py (постоянный OpenOCD).

  python3 beu1000/ntrace.py cal                  # окно каждой линии по IODELAY на узоре калибровки
  python3 beu1000/ntrace.py cap --save x.json    # запись и разбор MSEO
  python3 beu1000/ntrace.py decode x.json
Адаптер ПЛИС — RLN_FPGA_USB, адаптер платы — RLN_BEU_USB (места на шине USB).
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import trace as tr  # noqa: E402

# Узор калибровки PIB, 4 бита: байты 5A 5A F0 0F младшим полубайтом вперёд.
CAL = [0xA, 0x5, 0xA, 0x5, 0x0, 0xF, 0xF, 0x0]


def lane_ok(nib, lane):
    """Совпадает ли линия с узором калибровки при каком-либо сдвиге по кругу."""
    ref = [(x >> lane) & 1 for x in CAL]
    bits = [(x >> lane) & 1 for x in nib]
    n = len(ref)
    for off in range(n):
        if all(bits[i] == ref[(i + off) % n] for i in range(len(bits))):
            return True
    return False


def cmd_cal(a):
    steps = list(range(0, 256, a.step))
    if steps[-1] != 255:
        steps.append(255)
    table = {}
    for d in steps:
        h, words = tr.capture(2, d, iodelay=[d] * 4)
        nib = tr.nibbles_mode1(words[:a.words])
        table[d] = [lane_ok(nib, l) for l in range(4)]
        print(f"IODELAY {d:3}: " + " ".join("D%d %s" % (l, "+" if ok else ".") for l, ok in enumerate(table[d]))
              + "   " + "".join(f"{x:x}" for x in nib[:16]))
    for l in range(4):
        good = [d for d in steps if table[d][l]]
        print(f"D{l}: годные задержки {good[0]}…{good[-1]}" if good else f"D{l}: годных нет",
              "(с дырами)" if good and len(good) != (good[-1] - good[0]) // a.step + 1 else "")
    if a.save:
        json.dump({str(d): v for d, v in table.items()}, open(a.save, "w"), indent=1)


# ---- N-Trace: поток полубайтов → сообщения ----

def messages(nib):
    """Сообщения N-Trace из потока полубайтов (младший вперёд). Простой — полубайты F.
    Простой может быть нечётной длины, поэтому выравнивание — заново после каждого простоя:
    начало сообщения — первый полубайт после F с MSEO (младшие 2 бита) = 00."""
    msgs, n = [], len(nib)
    bad = 0
    i = nib.index(0xF) if 0xF in nib else n  # до первого простоя — хвост сообщения, начатого до записи
    while i < n:
        if nib[i] == 0xF:
            i += 1
            continue
        if nib[i] & 3:
            bad += 1  # не начало сообщения: середина того, что началось до записи, или сбой
            i += 1
            continue
        start, cur = i, []
        while i + 1 < n:
            b = nib[i] | nib[i + 1] << 4
            cur.append(b)
            i += 2
            if b & 3 == 3:
                break
        else:
            break  # обрыв в конце записи
        msgs.append((start, bytes(cur)))
    return msgs, bad


# Поля сообщений N-Trace 1.0 (табл. «Fields in Messages»): фиксированные — (имя, бит),
# переменные — (имя, None). SRC у BE-U1000 нет (trTeInhibitSrc = 1, только чтение).
LAYOUT = {
    2: ("Ownership", [("PROCESS", None)]),
    3: ("DirectBranch", [("ICNT", None)]),
    4: ("IndirectBranch", [("BTYPE", 2), ("ICNT", None), ("UADDR", None)]),
    8: ("Error", [("ETYPE", 4), ("ECODE", None)]),
    9: ("ProgTraceSync", [("SYNC", 4), ("ICNT", None), ("FADDR", None)]),
    11: ("DirectBranchSync", [("SYNC", 4), ("ICNT", None), ("FADDR", None)]),
    12: ("IndirectBranchSync", [("SYNC", 4), ("BTYPE", 2), ("ICNT", None), ("FADDR", None)]),
    27: ("ResourceFull", [("RCODE", 4), ("RDATA", None)]),
    28: ("IndirectBranchHist", [("BTYPE", 2), ("ICNT", None), ("UADDR", None), ("HIST", None)]),
    29: ("IndirectBranchHistSync", [("SYNC", 4), ("BTYPE", 2), ("ICNT", None), ("FADDR", None), ("HIST", None)]),
    30: ("RepeatBranch", [("BCNT", None)]),
    33: ("ProgTraceCorrelation", [("EVCODE", 4), ("CDF", 2), ("ICNT", None), ("HIST", None)]),
}
EVCODE_NAMES = {0: "вход в отладку", 1: "сон", 4: "трасса выключена"}
SYNC_NAMES = {0: "внешний триггер", 1: "выход из сброса", 2: "периодическая", 3: "выход из отладки",
              4: "переполнение I-CNT", 5: "включение трассы", 6: "событие", 7: "после переполнения FIFO",
              9: "выход из сна"}


def parse_msg(msg):
    """Сообщение → (TCODE, {поле: значение}). Биты MDO склеиваются младшим вперёд; поле
    переменной длины кончается на байте с MSEO = 01 или 11 (TSTAMP, если есть, — последний)."""
    bits, ends, nb = 0, [], 0
    for b in msg:
        bits |= (b >> 2) << nb
        nb += 6
        if b & 3:
            ends.append(nb)
    tcode = bits & 0x3F
    name, lay = LAYOUT.get(tcode, (f"TCODE{tcode}", []))
    pos, out, k = 6, {}, 0
    if (bits & 0xF) in (0, 1) and tcode not in (32,) and len(ends) == 1 and tcode != 0x10 and \
            (tcode not in LAYOUT or tcode == 33):
        # BE-U1000 шлёт ResourceFull без TCODE: сразу RCODE (4 бита) и RDATA одним полем. Младшие
        # биты первого байта — RCODE (0 — I-CNT полон, 1 — HIST полон), выше — уже данные, поэтому
        # «TCODE» выходит 1/17/33/49 или 0/16/48. Настоящий ProgTraceCorrelation (33) — от двух полей.
        return 27, {"RCODE": bits & 0xF, "RDATA": bits >> 4, "NOTCODE": 1}
    for fname, w in lay:
        if w is not None:
            out[fname] = bits >> pos & ((1 << w) - 1)
            pos += w
        else:
            if k >= len(ends):
                if not (tcode == 33 and fname == "HIST"):  # в BTM у ProgTraceCorrelation HIST нет
                    out["_err"] = f"нет конца поля {fname}"
                break
            out[fname] = bits >> pos & ((1 << (ends[k] - pos)) - 1)
            pos = ends[k]
            k += 1
    if k < len(ends):
        out["TSTAMP"] = bits >> pos & ((1 << (ends[k] - pos)) - 1)
    return tcode, out


TCODES = {t: n for t, (n, _) in LAYOUT.items()}
LAYOUT[27] = ("ResourceFull", [("RCODE", 4), ("RDATA", None)])  # RDATA[1] (HREPEAT) попадёт в TSTAMP


def fmt_msg(tcode, f):
    s = TCODES.get(tcode, f"TCODE{tcode}")
    for k, v in f.items():
        if k == "NOTCODE":
            s += " [без TCODE]"
        elif k in ("FADDR", "UADDR"):
            s += f" {k}={v << 1:#x}"
        elif k == "EVCODE":
            s += f" EVCODE={v} ({EVCODE_NAMES.get(v, '?')})"
        elif k == "SYNC":
            s += f" SYNC={v} ({SYNC_NAMES.get(v, '?')})"
        else:
            s += f" {k}={v}"
    return s


# ---- путь программы по ELF ----

ELF = os.path.join(HERE, "fw", "trace.elf")
# objdump — из тулчейна в подмодуле au/mcu-sdk, иначе из архива SDK 2.3.0 (как в fw/Makefile)
OBJDUMP = os.path.normpath(os.path.join(HERE, "..", "..", "..", "..", "au", "mcu-sdk", "Tools", "toolchain", "bin",
                                        "riscv32-none-elf-objdump"))
if not os.path.exists(OBJDUMP):
    OBJDUMP = os.path.expanduser("~/.local/opt/baikal-mcu-sdk-2.3.0/Tools/toolchain/riscv32-none-elf/bin/"
                                 "riscv32-none-elf-objdump")
COND = {"beq", "bne", "blt", "bge", "bltu", "bgeu", "beqz", "bnez", "blez", "bgez", "bltz", "bgtz",
        "bgt", "ble", "bgtu", "bleu", "c.beqz", "c.bnez"}
DJUMP = {"j", "jal", "c.j", "c.jal"}
IJUMP = {"jalr", "jr", "ret", "c.jr", "c.jalr", "mret"}


def disasm(elf=ELF):
    """{адрес: (размер, мнемоника, цель прямого перехода или None, функция)}."""
    import re
    import subprocess
    out = subprocess.run([OBJDUMP, "-d", elf],
                         capture_output=True, text=True).stdout
    dis, func = {}, "?"
    for line in out.splitlines():
        m = re.match(r"^([0-9a-f]+) <(.+)>:$", line)
        if m:
            func = m[2]
            continue
        m = re.match(r"^\s*([0-9a-f]+):\s+([0-9a-f]+)\s+(\S+)\s*(.*)$", line)
        if not m:
            continue
        addr, enc, mn, ops = int(m[1], 16), m[2], m[3], m[4]
        tgt = None
        if mn in COND or mn in DJUMP:
            t = re.search(r"\b([0-9a-f]{6,})\s*<", ops)
            tgt = int(t[1], 16) if t else None
        dis[addr] = (len(enc) // 2, mn, tgt, func, ops)
    return dis


def hist_bits(h):
    """HIST → исходы условных переходов по порядку (старший единичный бит — стоп-бит)."""
    n = h.bit_length() - 1
    return [(h >> k) & 1 for k in range(n - 1, -1, -1)]


class Flow:
    """Восстановление пути по сообщениям. I-CNT — полуслова от прошлого сообщения; в BTM взятый
    условный переход — DirectBranch, невзятые молчат; в HTM исход каждого условного перехода —
    бит HIST (в IndirectBranchHist или ResourceFull). rows — построчно: [адрес, № сообщения, что сделано]."""

    def __init__(self, dis, htm=False):
        self.dis, self.htm, self.pc, self.ref = dis, htm, None, 0
        self.ninstr, self.errors, self.calls, self.rows = 0, [], [], []
        self.pend_icnt, self.bits, self.last_branch, self.lost = 0, [], None, 0

    def walk_bits(self, mi):
        """BE-U1000: по заполнении HIST (ResourceFull без TCODE) кодер сбрасывает I-CNT, не передав
        его. Конец блока определяется самим HIST: идти, пока не уйдёт последний бит, — блок кончается
        на условном переходе, который его взял; I-CNT следующего сообщения считается от него."""
        if self.pend_icnt:
            raise ValueError("I-CNT из ResourceFull перед ResourceFull(HIST) — не разобрано")
        while self.bits:
            pc = self.pc
            d = self.dis.get(pc)
            if d is None:
                raise ValueError(f"нет инструкции по адресу {pc:#x}")
            size, mn, tgt = d[0], d[1], d[2]
            if mn in COND:
                t = self.bits.pop(0)
                nxt, act = (tgt, f"HIST {t}: взят → {tgt:08x}") if t else (pc + size, "HIST 0: не взят")
            elif mn in DJUMP:
                nxt, act = tgt, f"прямой → {tgt:08x}"
            elif mn in IJUMP:
                raise ValueError(f"косвенный переход {pc:#x} внутри ResourceFull(HIST)")
            else:
                nxt, act = pc + size, "дальше"
            self.rows.append([pc, mi, act])
            self.ninstr += 1
            self.pc = nxt

    def walk(self, icnt, mi):
        """Пройти icnt полуслов от self.pc (с отложенным I-CNT из ResourceFull), двигая pc через
        каждую инструкцию; последняя запись rows — последняя инструкция блока."""
        left, last = icnt + self.pend_icnt, None
        self.pend_icnt = 0
        while left > 0:
            pc = self.pc
            d = self.dis.get(pc)
            if d is None:
                raise ValueError(f"нет инструкции по адресу {pc:#x}")
            size, mn, tgt = d[0], d[1], d[2]
            left -= size // 2
            if left < 0:
                raise ValueError(f"I-CNT кончился посреди инструкции {pc:#x}")
            if mn in COND:
                if self.htm:
                    if not self.bits:
                        raise ValueError(f"условный переход {pc:#x}, а битов HIST не осталось")
                    t = self.bits.pop(0)
                    nxt, act = (tgt, f"HIST {t}: взят → {tgt:08x}") if t else (pc + size, "HIST 0: не взят")
                else:
                    nxt, act = pc + size, "не взят"
            elif mn in DJUMP:
                nxt, act = tgt, f"прямой → {tgt:08x}"
            elif mn in IJUMP:
                if left > 0:
                    raise ValueError(f"косвенный переход {pc:#x} посреди блока")
                nxt, act = None, "косвенный"
            else:
                nxt, act = pc + size, "дальше"
            self.rows.append([pc, mi, act])
            self.ninstr += 1
            last = (pc, d)
            self.pc = nxt
        return last

    def msg(self, tcode, f, mi=-1):
        try:
            self._msg(tcode, f, mi)
        except ValueError as e:
            self.errors.append(f"сообщение {mi}: {e}")
            self.pc, self.bits, self.pend_icnt = None, [], 0  # ждать синхронизации

    def _msg(self, tcode, f, mi):
        if tcode == 8:  # Error: сообщения потеряны, дальше — только с синхронизации
            self.lost += 1
            self.calls.append("|")
            self.pc, self.bits, self.pend_icnt = None, [], 0
            return
        if "FADDR" in f:
            addr = f["FADDR"] << 1
            if "HIST" in f:
                self.bits += hist_bits(f["HIST"])
            if self.pc is not None and f.get("ICNT"):
                a, d = self.walk(f["ICNT"], mi)
                nxt = self.pc
                if tcode == 11:
                    nxt = d[2]
                if tcode in (9, 11) and nxt != addr:
                    self.errors.append(f"сообщение {mi}: синхронизация, дошли до {nxt or 0:#x}, а F-ADDR {addr:#x}")
                if tcode in (12, 29) and d[1] not in IJUMP and f.get("BTYPE") == 0 and self.pc is None:
                    pass
                self.rows[-1][2] += f" → F-ADDR {addr:08x}" if tcode != 9 else ""
            if self.bits:
                self.errors.append(f"сообщение {mi}: после синхронизации остались биты HIST ({len(self.bits)} шт.)")
            self.pc = self.ref = addr
            self.bits, self.pend_icnt = [], 0
            if addr in FUNC_START:  # трасса включилась на входе в функцию (триггер trace-on)
                self.calls.append(self.dis[addr][3])
            return
        if tcode == 27 and self.pc is None:
            return  # до первой синхронизации привязать некуда
        if tcode == 27:  # ResourceFull
            if f["RCODE"] == 0:
                self.pend_icnt += f["RDATA"]
            elif f["RCODE"] in (1, 2):
                self.bits += hist_bits(f["RDATA"]) * (1 + (f.get("TSTAMP", 0) if f["RCODE"] == 2 else 0))
                if f.get("NOTCODE"):
                    self.walk_bits(mi)
            return
        if tcode == 30:  # RepeatBranch: повторить прошлое сообщение о переходе B-CNT раз
            if self.last_branch:
                for _ in range(f["BCNT"]):
                    self._msg(*self.last_branch, mi)
            return
        if self.pc is None:
            return
        if tcode == 33:  # трасса остановлена: I-CNT и HIST до точки остановки, дальше — до синхронизации
            if "HIST" in f:
                self.bits += hist_bits(f["HIST"])
            if f["ICNT"]:
                self.walk(f["ICNT"], mi)
                self.rows[-1][2] += " — трасса остановлена"
            self.pc, self.bits = None, []
            self.calls.append("|")
            return
        if tcode == 3:
            a, d = self.walk(f["ICNT"], mi)
            if d[1] not in COND:
                raise ValueError(f"DirectBranch, а последняя инструкция {a:#x} — {d[1]}")
            self.pc = d[2]
            self.rows[-1][2] = f"взят → {d[2]:08x}"
            self.last_branch = (tcode, f)
        elif tcode in (4, 28):
            if tcode == 28:
                self.bits += hist_bits(f["HIST"])
            a, d = self.walk(f["ICNT"], mi)
            new = (f["UADDR"] << 1) ^ self.ref
            if f["BTYPE"] == 0 and d[1] not in IJUMP:
                raise ValueError(f"IndirectBranch, а последняя инструкция {a:#x} — {d[1]}")
            if self.bits:
                raise ValueError(f"остались неиспользованные биты HIST ({len(self.bits)} шт.)")
            self.pc = self.ref = new
            self.rows[-1][2] = f"косвенный → {new:08x} (U-ADDR)"
            self.last_branch = (tcode, f)
            self.calls.append(self.dis.get(new, (0, "", None, "?"))[3] + ("" if new in FUNC_START else "+"))


FUNC_START = set()


def check_pattern(calls):
    """Проход цикла fw/main.c: ret в main, затем вызов ops[i % 3] и ret. Узнаём i по паре
    (чётность → inc_even/inc_odd идёт до op, op → i % 3) — последовательность op должна
    идти a, b, c, a, ... без пропусков."""
    ops = [c for c in calls if c in ("op_a", "op_b", "op_c", "|")]  # «|» — разрыв после Error
    order = {"op_a": 0, "op_b": 1, "op_c": 2}
    gaps = sum(1 for x, y in zip(ops, ops[1:]) if "|" not in (x, y) and (order[x] + 1) % 3 != order[y])
    ops = [c for c in ops if c != "|"]
    return len(ops), gaps


def report(nib, verbose=True, limit=40, elf=ELF):
    msgs, bad = messages(nib)
    idle = sum(1 for x in nib if x == 0xF)
    hist = {}
    parsed = []
    for start, m in msgs:
        t, f = parse_msg(m)
        parsed.append((start, m, t, f))
        hist[t] = hist.get(t, 0) + 1
    print(f"полубайтов {len(nib)}, простоя {idle}, сообщений {len(msgs)}, вне сообщений {bad}")
    for t, c in sorted(hist.items()):
        print(f"  TCODE {t:2} {TCODES.get(t, '?'):22} {c}")
    dis = disasm(elf)
    FUNC_START.clear()
    FUNC_START.update(a for a, d in dis.items() if dis.get(a - 2, (0, 0, 0, None))[3] != d[3]
                      and dis.get(a - 4, (0, 0, 0, None))[3] != d[3])
    htm = sum(t in (28, 29) for _, _, t, _ in parsed) > sum(t == 3 for _, _, t, _ in parsed)
    fl = Flow(dis, htm=htm)
    for i, (start, m, t, f) in enumerate(parsed):
        fl.msg(t, f, i)
        if verbose and i < limit:
            tail = ""
            if fl.pc is not None and t in (3, 4, 9, 11, 12, 28, 29):
                d = dis.get(fl.pc)
                tail = f"→ {fl.pc:#x} <{d[3] if d else '?'}>"
            print(f"  @{start:6} {m.hex(' '):24} {fmt_msg(t, f):58} {tail}")
    n, gaps = check_pattern(fl.calls)
    nbytes = sum(len(m) for _, m in msgs)
    print(f"байт трассы {nbytes}, инструкций восстановлено {fl.ninstr} — {8 * nbytes / max(1, fl.ninstr):.2f} бит "
          f"на инструкцию; сообщений Error {fl.lost}; ошибок пути {len(fl.errors)}")
    for e in fl.errors[:10]:
        print("  !", e)
    print(f"вызовов op_a/op_b/op_c {n}, нарушений порядка a→b→c {gaps}")
    ok = msgs and not fl.errors and n and not gaps
    print("ИТОГ: " + ("трасса цела, путь программы совпал" if ok else "ОШИБКИ")
          + (f" (с потерями: {fl.lost} Error, декодер восстанавливался по синхронизации)" if ok and fl.lost else ""))
    return parsed, fl, dis


def cmd_cap(a):
    h, words = tr.capture(2, a.dly, iodelay=a.iodelay)
    print(f"записано {len(words)} слов, TRACECLK-домен: пропусков {h['miss']}")
    elf = a.elf
    if a.save:
        import shutil
        elf = os.path.splitext(a.save)[0] + ".elf"  # прошивка — рядом с записью, для разбора потом
        shutil.copy(a.elf, elf)
        json.dump({"header": h, "words": words, "note": a.note, "elf": os.path.basename(elf)}, open(a.save, "w"))
    report(tr.nibbles_mode1(words), limit=a.limit, elf=elf)


def elf_of(a, d):
    if a.elf != ELF or "elf" not in d:
        return a.elf
    return os.path.join(os.path.dirname(os.path.abspath(a.file)), d["elf"])


def cmd_decode(a):
    d = json.load(open(a.file))
    report(tr.nibbles_mode1(d["words"]), limit=a.limit, elf=elf_of(a, d))


def cmd_table(a):
    """Кусок трассы таблицей Markdown: строка исходника → инструкция → сообщение N-Trace (байты и
    поля) → что сделал декодер. Окно — с --skip-го появления функции/адреса --start, --count инструкций."""
    import contextlib
    import io
    import subprocess
    d = json.load(open(a.file))
    elf = elf_of(a, d)
    with contextlib.redirect_stdout(io.StringIO()):
        parsed, fl, dis = report(tr.nibbles_mode1(d["words"]), verbose=False, elf=elf)
    start = int(a.start, 0) if a.start[0].isdigit() else min(x for x, v in dis.items() if v[3] == a.start)
    hits = [i for i, r in enumerate(fl.rows) if r[0] == start]
    if len(hits) <= a.skip:
        sys.exit(f"адрес {start:#x} встречается {len(hits)} раз")
    win = fl.rows[hits[a.skip]:hits[a.skip] + a.count]
    a2l = subprocess.run([OBJDUMP.replace("objdump", "addr2line"), "-e", elf] + [hex(r[0]) for r in win],
                         capture_output=True, text=True).stdout.splitlines()
    src = open(os.path.join(HERE, "fw", "main.c")).read().splitlines()
    print("| Исходник `main.c` | Адрес | Инструкция | Сообщение N-Trace | Декодер |")
    print("|---|---|---|---|---|")
    prev_line, prev_mi = None, None
    for (addr, mi, act), loc in zip(win, a2l):
        loc = loc.split(" (")[0]
        ln = int(loc.split(":")[-1]) if loc.split(":")[-1].isdigit() else 0
        code = f"{ln}: `{src[ln - 1].strip()}`" if ln and ln != prev_line else ""
        prev_line = ln
        if mi != prev_mi:
            _, m, t, f = parsed[mi]
            msg = f"`{m.hex(' ')}` {fmt_msg(t, f).replace('[без TCODE]', '(без TCODE)')}"
        else:
            msg = "″"
        prev_mi = mi
        size, mn, tgt, func, ops = dis[addr]
        ins = f"{mn} {ops.split('<')[0].split('#')[0].strip()}".strip()
        print(f"| {code} | `{addr:08x}` | `{ins}` | {msg} | {act} |")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("cal", help="окно линий по IODELAY на узоре калибровки")
    p.add_argument("--step", type=int, default=16)
    p.add_argument("--words", type=int, default=1024, help="сколько слов записи проверять")
    p.add_argument("--save")
    p.set_defaults(fn=cmd_cal)
    p = sub.add_parser("cap", help="запись и разбор")
    p.add_argument("--dly", type=int, default=255)
    p.add_argument("--iodelay", type=int, nargs=4)
    p.add_argument("--save")
    p.add_argument("--note", default="")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--elf", default=ELF)
    p.set_defaults(fn=cmd_cap)
    p = sub.add_parser("decode", help="разбор сохранённой записи")
    p.add_argument("file")
    p.add_argument("--limit", type=int, default=40)
    p.add_argument("--elf", default=ELF)
    p.set_defaults(fn=cmd_decode)
    p = sub.add_parser("table", help="кусок трассы: исходник → инструкция → сообщение → декодер (Markdown)")
    p.add_argument("file")
    p.add_argument("--start", default="main", help="функция или адрес начала окна")
    p.add_argument("--skip", type=int, default=0)
    p.add_argument("--count", type=int, default=40)
    p.add_argument("--elf", default=ELF)
    p.set_defaults(fn=cmd_table)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
