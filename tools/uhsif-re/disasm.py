#!/usr/bin/env python3
"""Linear disassembly of the relinked libUHSIF ELF with capstone, plus the opcodes capstone 5 lacks:
Zba/Zbb/Zbs and the WCH xw2p2 compressed byte load/store (which collide with c.fld / c.fsd).

usage: python3 -I disasm.py uhsif.elf > uhsif.dis
"""
import sys
from elftools.elf.elffile import ELFFile
from capstone import Cs, CS_ARCH_RISCV, CS_MODE_RISCV32, CS_MODE_RISCVC

ABI = "zero ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6".split()


def extra32(ins):
    op, rd, f3, rs1, rs2, f7 = ins & 0x7F, (ins >> 7) & 31, (ins >> 12) & 7, (ins >> 15) & 31, (ins >> 20) & 31, ins >> 25
    if op == 0x33 and f7 == 0x10 and f3 in (2, 4, 6):
        return f"sh{f3 // 2}add {ABI[rd]}, {ABI[rs1]}, {ABI[rs2]}"
    if op == 0x33 and f7 == 0x04 and f3 == 4 and rs2 == 0:
        return f"zext.h {ABI[rd]}, {ABI[rs1]}"
    if op == 0x13 and f3 == 1 and f7 in (0x14, 0x24, 0x34):
        return f"{ {0x14: 'bseti', 0x24: 'bclri', 0x34: 'binvi'}[f7]} {ABI[rd]}, {ABI[rs1]}, {rs2}"
    return None


def xw16(h):
    """WCH xw2p2: quadrant 0, funct3 001 = c.lbu, 101 = c.sb; uimm[4:0] = {b11, b10, b6, b5, b12}."""
    if h & 3 or (h >> 13) not in (1, 5):
        return None
    imm = (h >> 12 & 1) | (h >> 5 & 1) << 1 | (h >> 6 & 1) << 2 | (h >> 10 & 3) << 3
    rs1, r2 = ABI[8 + (h >> 7 & 7)], ABI[8 + (h >> 2 & 7)]
    return f"c.lbu {r2}, {imm}({rs1})" if h >> 13 == 1 else f"c.sb {r2}, {imm}({rs1})"


def main():
    f = ELFFile(open(sys.argv[1], "rb"))
    sec = f.get_section_by_name(".text")
    t, base = sec.data(), sec["sh_addr"]
    syms = {}
    for s in f.get_section_by_name(".symtab").iter_symbols():
        if s.name and not s.name.startswith("$"):
            syms.setdefault(s["st_value"], s.name)
    end = min(a for a, n in syms.items() if n.startswith("Uhsif"))
    md = Cs(CS_ARCH_RISCV, CS_MODE_RISCV32 | CS_MODE_RISCVC)
    i = 0
    while base + i < end:
        a = base + i
        if a in syms:
            print(f"<{syms[a]}>:")
        h = int.from_bytes(t[i:i + 2], "little")
        size = 4 if h & 3 == 3 else 2
        word = int.from_bytes(t[i:i + size], "little")
        text = xw16(word) if size == 2 else extra32(word)
        if text:
            text += "    ; *"
        else:
            ins = list(md.disasm(t[i:i + size], a, 1))
            text = f"{ins[0].mnemonic} {ins[0].op_str}" if ins else "???"
        print(f"{a:6x}: {word:0{size * 2}x}  {text}")
        i += size


if __name__ == "__main__":
    main()
