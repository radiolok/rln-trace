#!/usr/bin/env python3
"""Run the same scenarios on libUHSIF.a and on the open driver, compare what they do.

Compared: every peripheral access in order (address, R/W, value), return codes, callbacks and
their arguments, the final GPIO mode of every pin, DMA descriptors. Not compared: PCs, memset /
memcpy calls, the order of GPIO_Init calls, where the descriptors happen to be linked (socket
registers that point at them are rewritten as descriptor names).

usage: python3 -I compare.py lib.elf open.elf
"""
import difflib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spike  # noqa: E402

ACCESS = re.compile(r"^  ([RW])(\d) (\S+) +(<=|=>) 0x([0-9a-f]+)")
GPIO = re.compile(r"^    GPIO_Init\(GPIO(\w), pins=\{([\d,]*)\}, speed=(\d+), mode=(\w+)\)")


VOID = ("UHSIF_Cfg", "UHSIF_Start", "UHSIF_IRQHandler")


def normalize(s):
    """a0 after a void function and the "argument" of a void OUT callback are just leftovers."""
    out, pins, func = [], {}, None

    def flush():
        out.extend(f"    pin P{p} {m}" for p, m in sorted(pins.items()))
        pins.clear()

    for line in s.log:
        if line.startswith("\n== ") or line.startswith("== "):
            flush()
            head = line.strip()
            if head.startswith("== ->"):
                if func in VOID:
                    out.append("== -> (void)")
                    continue
            else:
                func = head[3:].split("(")[0]
        if line.startswith(("    memset", "    memcpy")) or not line.strip():
            continue
        g = GPIO.match(line)
        if g:
            for b in filter(None, g.group(2).split(",")):
                pins[f"{g.group(1)}{int(b):02d}"] = f"speed={g.group(3)} mode={g.group(4)}"
            continue
        a = ACCESS.match(line)
        if a:
            rw, size, reg, arrow, val = a.groups()
            v = int(val, 16)
            m = re.match(r"UHSIF\+0x(1[0-9a-f]{3})$", reg)
            if m and int(m.group(1), 16) % 0x40 == 0 and int(m.group(1), 16) < 0x2000:
                name = s.dscr_name(0x20000000 | (v & 0xFFFF) << 5)
                if name:
                    val = f"{v >> 16:04x}:{name}"
            out.append(f"  {rw}{size} {reg} {arrow} {val}")
            continue
        line = line.split("   @")[0].rstrip()
        if "_OUT_Callback(" in line:
            line = line.split("(")[0] + "()"
        out.append(line)
    flush()
    return out


def run(elf, fn):
    s = spike.Spike(elf)
    fn(s)
    return normalize(s)


def scenarios():
    TX, RX = spike.TX, spike.RX
    for m in range(3):
        def gpio(s, m=m):
            for rm in range(4):
                for clk in range(5):
                    for w in range(5):
                        s.call("UHSIF_GPIO_Init", m, rm, clk, 4 if m == 2 else 0, w)
            s.call("UHSIF_GPIO_Init", m, 0, 0, 0x40, 0)
            s.call("UHSIF_GPIO_Init", 3, 0, 0, 0, 0)
        yield f"gpio sweep, mode {m}", gpio
        yield f"WCH example flow, mode {m}", lambda s, m=m: spike.scenario(s, m)
        four = ((0, 1, 3, TX, 5), (1, 0, 1, RX, 4094), (2, 0, 8, TX + 0x20000, 0), (3, 1, 2, RX + 0x20000, 0x3FFF))
        yield f"four lines, 16 bit, remap 0, mode {m}", \
            lambda s, m=m: spike.scenario(s, m, port_rm=0, clk_rm=0, width=1, lines=four)

        def errors(s, m=m):
            s.call("UHSIF_GPIO_Init", m, 1, 3, 0, 0)
            s.call("UHSIF_Cfg")
            s.call("UHSIF_Line_Cfg", 0, 2, 1, TX, 0)
            s.call("UHSIF_Line_Cfg", 0, 0, 9, TX, 0)
            s.call("UHSIF_Line_Cfg", 0, 0, 1, 0, 0)
            s.call("UHSIF_Trans_Cfg", 0, 0, 0)
        yield f"argument errors, mode {m}", errors


def main():
    lib, own = sys.argv[1], sys.argv[2]
    bad = 0
    for name, fn in scenarios():
        a, b = run(lib, fn), run(own, fn)
        accesses = sum(1 for x in a if ACCESS.match(x) or x.startswith("  R") or x.startswith("  W"))
        if a == b:
            print(f"OK    {name}: {len(a)} lines, {accesses} accesses")
            continue
        bad += 1
        print(f"DIFF  {name}")
        for d in list(difflib.unified_diff(a, b, "libUHSIF", "open", n=3, lineterm=""))[:60]:
            print("      " + d)
    print("all equal" if not bad else f"{bad} scenario(s) differ")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
