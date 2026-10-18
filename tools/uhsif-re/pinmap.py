#!/usr/bin/env python3
"""Pin maps chosen by UHSIF_GPIO_Init, collected with the spike for every remap / width combination.

usage: python3 -I pinmap.py uhsif.elf [fpga|soc|master] > pinmap.md
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import spike  # noqa: E402

WIDTH = {0: 8, 1: 16, 2: 24, 3: 32}


def pins_of(log):
    """GPIO_Init log lines -> {mode: [PA13, ...]} in call order."""
    out = {}
    for line in log:
        line = line.strip()
        if not line.startswith("GPIO_Init("):
            continue
        port = line[len("GPIO_Init(GPIO"):][0]
        bits = line[line.index("{") + 1:line.index("}")].split(",")
        mode = line.rsplit("mode=", 1)[1].rstrip(")")
        out.setdefault(mode, []).extend(f"P{port}{b}" for b in bits if b)
    return out


def main():
    elf = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "fpga"
    m = {"fpga": 0, "soc": 1, "master": 2}[mode]
    print(f"# UHSIF_GPIO_Init pin maps, mode={mode}\n")
    print("| port_rm | clk_rm | width | AFIO_PCFR1 | pins by GPIO mode |")
    print("|---|---|---|---|---|")
    for port_rm in range(3):
        for clk_rm in range(4):
            for wb in range(4):
                s = spike.Spike(elf)
                ret = s.call("UHSIF_GPIO_Init", m, port_rm, clk_rm, 4 if m == 2 else 0, wb)
                afio = [l for l in s.log if "AFIO+0x000" in l and "<=" in l]
                afio = afio[-1].split("<=")[1].split()[0] if afio else "-"
                groups = "; ".join(f"{k}: {' '.join(v)}" for k, v in pins_of(s.log).items())
                print(f"| {port_rm} | {clk_rm} | {WIDTH[wb]} | {afio} | {groups if ret == 0 else f'error 0x{ret:x}'} |")


if __name__ == "__main__":
    main()
