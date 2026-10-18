#!/usr/bin/env python3
"""Run libUHSIF.a functions under Unicorn and log every peripheral access.

The library is first linked into a flat ELF (see Makefile): code at 0x10000, data at 0x20000000,
every external symbol at a trap address 0x00F00000 + 16*i.  Unicorn (QEMU 5) lacks Zba/Zbb/Zbs and
the WCH xw2p2 compressed byte load/store, so those few instructions are executed by a code hook.

usage: python3 -I spike.py uhsif.elf [fpga|soc|master] > trace.txt
"""
import sys
from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_RISCV, UC_MODE_RISCV32, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_MEM_WRITE
from unicorn.riscv_const import UC_RISCV_REG_PC, UC_RISCV_REG_X0

M32 = 0xFFFFFFFF
STUB = 0x00F00000
RET = 0x00FFF000
STACK_TOP = 0x2000F000
REG = lambda i: UC_RISCV_REG_X0 + i
ABI = "zero ra sp gp tp t0 t1 t2 s0 s1 a0 a1 a2 a3 a4 a5 a6 a7 s2 s3 s4 s5 s6 s7 s8 s9 s10 s11 t3 t4 t5 t6".split()

NAMES = {0x40010000: "AFIO", 0x40010800: "GPIOA", 0x40010C00: "GPIOB", 0x40011000: "GPIOC",
         0x40011400: "GPIOD", 0x40011800: "GPIOE", 0x40011C00: "GPIOF", 0x40021000: "RCC",
         0x40038000: "UHSIF", 0xE000E000: "PFIC"}
GPIO_MODE = {0x0: "AIN", 0x04: "IN_FLOATING", 0x28: "IPD", 0x48: "IPU", 0x14: "Out_OD",
             0x10: "Out_PP", 0x1C: "AF_OD", 0x18: "AF_PP"}


def region(a):
    for base in sorted(NAMES, reverse=True):
        if a >= base:
            return f"{NAMES[base]}+0x{a - base:03x}"
    return f"0x{a:08x}"


def sx(v, bits):
    v &= (1 << bits) - 1
    return v - (1 << bits) if v >> (bits - 1) else v


class Spike:
    def __init__(self, elf):
        self.uc = uc = Uc(UC_ARCH_RISCV, UC_MODE_RISCV32)
        uc.mem_map(0x00010000, 0x10000)
        uc.mem_map(0x20000000, 0x10000)
        uc.mem_map(STUB, 0x100000)
        uc.mem_map(0x40000000, 0x100000)       # HB peripherals incl. UHSIF 0x40038000..
        uc.mem_map(0xE000E000, 0x1000)         # PFIC
        f = ELFFile(open(elf, "rb"))
        for s in f.iter_sections():
            if s["sh_type"] == "SHT_PROGBITS" and s["sh_addr"]:
                uc.mem_write(s["sh_addr"], s.data())
        self.sym, funcs = {}, []
        for s in f.get_section_by_name(".symtab").iter_symbols():
            if s.name == ".LANCHOR0":
                self.sym["rodata"] = s["st_value"]                       # GPIO_InitTypeDef pool
            elif s.name and not s.name.startswith((".L", "$")):
                self.sym[s.name] = s["st_value"]
                if s["st_info"]["type"] == "STT_FUNC" and s["st_size"]:
                    funcs.append((s["st_value"], s["st_size"], s.name))
        self.stubs = {a: n for n, a in self.sym.items() if STUB <= a < STUB + 0x1000}
        self.func_at = sorted((a, n) for a, _, n in funcs)
        self.dscr = {k: next((self.sym[n] for n in names if n in self.sym), None)
                     for k, names in (("IN", ("SOCKET_DSCR_RD", "uhsif_dscr_in")),
                                      ("OUT", ("SOCKET_DSCR_WR", "uhsif_dscr_out")))}
        text = f.get_section_by_name(".text")
        self.patch = self.find_unsupported(text, funcs)
        # Hooks run before the instruction; never touch PC from a hook.  Unsupported instructions
        # become NOPs of the same size, stub slots become real returns, mret becomes ret.
        for a, (_, n) in self.patch.items():
            uc.mem_write(a, b"\x01\x00" if n == 2 else (0x13).to_bytes(4, "little"))
        for a in self.find_mret(text, funcs):
            uc.mem_write(a, (0x00008067).to_bytes(4, "little"))
        for a, n in self.stubs.items():
            back = 5 if n.startswith("__riscv_save_") else 1          # jal t0 / ra
            uc.mem_write(a, (0x67 | back << 15).to_bytes(4, "little"))   # jalr x0, 0(t0|ra)
        self.log = []
        uc.hook_add(UC_HOOK_CODE, self.on_stub, begin=STUB, end=STUB + 0xFFF)
        for a in self.patch:
            uc.hook_add(UC_HOOK_CODE, self.on_patch, begin=a, end=a)
        uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, self.on_mmio, begin=0x40000000, end=0x400FFFFF)
        uc.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, self.on_mmio, begin=0xE000E000, end=0xE000EFFF)

    # --- helpers ---
    def r(self, i):
        return self.uc.reg_read(REG(i))

    def w(self, i, v):
        if i:
            self.uc.reg_write(REG(i), v & M32)

    def rd(self, a, n):
        return int.from_bytes(self.uc.mem_read(a, n), "little")

    def where(self, pc):
        name, base = "?", 0
        for a, n in self.func_at:
            if a <= pc:
                name, base = n, a
        return f"{name}+0x{pc - base:x}"

    def emit(self, text):
        self.log.append(text)

    # --- instructions Unicorn does not know ---
    @staticmethod
    def walk(text, funcs):
        """(address, raw, size) of every instruction inside a function symbol."""
        t, base = text.data(), text["sh_addr"]
        for start, size, _ in funcs:
            i, end = start - base, start - base + size
            while i < end:
                h = int.from_bytes(t[i:i + 2], "little")
                n = 4 if h & 3 == 3 else 2
                yield base + i, int.from_bytes(t[i:i + n], "little"), n
                i += n

    def find_mret(self, text, funcs):
        return [a for a, ins, n in self.walk(text, funcs) if n == 4 and ins == 0x30200073]

    def find_unsupported(self, text, funcs):
        out = {}
        for a, ins, n in self.walk(text, funcs):
            if n == 4:
                op, f3, f7 = ins & 0x7F, (ins >> 12) & 7, ins >> 25
                if (op == 0x33 and f7 in (0x10, 0x04)) or (op == 0x13 and f3 in (1, 5) and f7 in (0x14, 0x24, 0x34)):
                    out[a] = (ins, 4)
            elif ins & 3 == 0 and (ins >> 13) in (1, 5):
                out[a] = (ins, 2)
        return out


    def on_patch(self, uc, pc, size, _):
        ins, n = self.patch[pc]
        if n == 2:                                 # WCH xw2p2: c.lbu / c.sb
            imm = ((ins >> 12) & 1) | ((ins >> 5) & 1) << 1 | ((ins >> 6) & 1) << 2 | ((ins >> 10) & 3) << 3
            rs1, r2 = 8 + ((ins >> 7) & 7), 8 + ((ins >> 2) & 7)
            a = (self.r(rs1) + imm) & M32
            if ins >> 13 == 1:
                self.w(r2, self.rd(a, 1))
            else:
                uc.mem_write(a, bytes([self.r(r2) & 0xFF]))
        else:
            rd, f3, rs1, rs2, f7 = (ins >> 7) & 31, (ins >> 12) & 7, (ins >> 15) & 31, (ins >> 20) & 31, ins >> 25
            x1, x2 = self.r(rs1), self.r(rs2)
            if ins & 0x7F == 0x33 and f7 == 0x10:  # sh1add/sh2add/sh3add
                v = (x1 << {2: 1, 4: 2, 6: 3}[f3]) + x2
            elif ins & 0x7F == 0x33 and f7 == 0x04:  # zext.h (pack rs2=0)
                v = x1 & 0xFFFF
            else:                                    # bseti / bclri / binvi
                sh = rs2
                v = {0x14: x1 | 1 << sh, 0x24: x1 & ~(1 << sh), 0x34: x1 ^ 1 << sh}[f7]
            self.w(rd, v)

    # --- external functions ---
    SAVED = [1, 8, 9] + list(range(18, 28))       # ra, s0, s1, s2..s11

    @staticmethod
    def frame(n):
        return 16 if n < 4 else 32 if n < 8 else 48 if n < 12 else 64

    def on_stub(self, uc, pc, size, _):
        name = self.stubs.get(pc)
        if name is None:
            return
        a = [self.r(10 + i) for i in range(4)]
        if name.startswith("__riscv_save_"):
            n = int(name.rsplit("_", 1)[1]); fr = self.frame(n); sp = self.r(2) - fr
            for k, reg in enumerate(self.SAVED[:n + 1]):
                uc.mem_write(sp + fr - 4 * (k + 1), self.r(reg).to_bytes(4, "little"))
            self.w(2, sp)
            return
        if name.startswith("__riscv_restore_"):
            n = int(name.rsplit("_", 1)[1]); fr = self.frame(n); sp = self.r(2)
            for k, reg in enumerate(self.SAVED[:n + 1]):
                self.w(reg, self.rd(sp + fr - 4 * (k + 1), 4))
            self.w(2, sp + fr)
            return
        if name == "memcpy":
            uc.mem_write(a[0], bytes(uc.mem_read(a[1], a[2])))
            self.emit(f"    memcpy(0x{a[0]:08x}, {self.symname(a[1])}, {a[2]})")
        elif name == "memset":
            uc.mem_write(a[0], bytes([a[1] & 0xFF]) * a[2])
            self.emit(f"    memset({self.symname(a[0])}, {a[1]}, {a[2]})")
        elif name == "GPIO_Init":
            pin, spd, mode = self.rd(a[1], 2), self.rd(a[1] + 4, 4), self.rd(a[1] + 8, 4)
            bits = ",".join(str(i) for i in range(16) if pin >> i & 1)
            self.emit(f"    GPIO_Init({NAMES.get(a[0], hex(a[0]))}, pins={{{bits}}}, speed={spd}, mode={GPIO_MODE.get(mode, hex(mode))})")
        elif name.startswith("RCC_"):
            self.emit(f"    {name}(0x{a[0]:x}, {a[1]})")
        else:
            self.emit(f"    -> {name}(0x{a[0]:x})")

    def symname(self, a):
        best = max(((n, s) for n, s in self.sym.items() if s <= a and a - s < 0x200 and not (STUB <= s < STUB + 0x1000)),
                   key=lambda t: t[1], default=None)
        return f"{best[0]}+0x{a - best[1]:x}" if best else f"0x{a:08x}"

    # --- peripheral accesses ---
    def on_mmio(self, uc, access, addr, size, value, _):
        pc = uc.reg_read(UC_RISCV_REG_PC)
        if access == UC_MEM_WRITE:
            self.emit(f"  W{size} {region(addr):14} <= 0x{value & ((1 << 8 * size) - 1):08x}   @{self.where(pc)}")
        else:
            v = self.rd(addr, size)
            self.emit(f"  R{size} {region(addr):14} => 0x{v:08x}   @{self.where(pc)}")

    def dscr_name(self, addr):
        """'IN[k]' / 'OUT[k]' for a descriptor address, else None."""
        for k, base in self.dscr.items():
            if base is not None and base <= addr < base + 32 * 32 and (addr - base) % 32 == 0:
                return f"{k}[{(addr - base) // 32}]"
        return None

    def dump_dscr(self, socks=range(32)):
        """32 descriptors x 32 bytes per direction, indexed by line*8 + buf; word 2 (own address >> 5)
        is printed as 'self' so that dumps of different builds compare equal."""
        for k, base in self.dscr.items():
            for i in socks:
                a = base + 32 * i
                words = [self.rd(a + 4 * j, 4) for j in range(8)]
                if any(words):
                    txt = ["self" if j == 2 and w == a >> 5 else f"{w:08x}" for j, w in enumerate(words)]
                    self.emit(f"  DSCR_{k}[{i:2}]: " + " ".join(txt))

    # --- run ---
    def call(self, name, *args, preset=None):
        for a, v in (preset or {}).items():
            self.uc.mem_write(a, v.to_bytes(4, "little"))
        for i in range(32):
            self.w(i, 0)
        self.w(1, RET); self.w(2, STACK_TOP)
        for i, v in enumerate(args):
            self.w(10 + i, v)
        self.emit(f"\n== {name}({', '.join(hex(v) for v in args)})")
        try:
            self.uc.emu_start(self.sym[name], RET, count=200000)
        except Exception as e:
            self.emit(f"!! {e} at {self.where(self.uc.reg_read(UC_RISCV_REG_PC))}")
        ret = self.r(10)
        self.emit(f"== -> 0x{ret:x}")
        return ret


TX, RX = 0x20008000, 0x2000A000                 # stand-ins for USBSS_EP1_Tx_Buf / Rx_Buf


def scenario(s, m, port_rm=2, clk_rm=1, width=3, lines=((0, 0, 8, TX, 0), (1, 1, 8, RX, 0))):
    """The WCH example flow, then transfers, every interrupt case, register access, shutdown."""
    s.call("UHSIF_Get_Ver")
    s.call("UHSIF_GPIO_Init", m, port_rm, clk_rm, 4 if m == 2 else 0, width)
    s.call("UHSIF_Cfg")
    for cfg in lines:
        s.call("UHSIF_Line_Cfg", *cfg)
    s.dump_dscr()
    s.call("UHSIF_Start", 1)
    for line, dir_, count, _, _ in lines:
        for rnd in range(2):                     # second round takes the re-arm path
            for buf in range(count):
                s.call("UHSIF_Trans_Cfg", line, buf, (100 + 37 * buf) if dir_ else 0)
        s.call("UHSIF_Trans_Cfg", line, count, 0)   # buffer out of range
    s.call("UHSIF_Trans_Cfg", 3 if len(lines) < 4 else 0, 0, 0)   # line not enabled
    s.dump_dscr()
    # interrupt: flag of line n in UHSIF+0x14 bit 11+n, current socket in UHSIF+0xfc+4n,
    # socket status in 0x40039000 + sock*0x40 + 0x10
    for line, _, count, _, _ in lines:
        for buf in sorted({0, count - 1}):
            sock = buf * 4 + line
            for st in (0x0, 0x1, 0x40, 0x41, 0x80, 0x81, 0x100, 0x101, 0x1C1):
                s.call("UHSIF_IRQHandler", preset={0x40038014: 1 << (11 + line),
                                                   0x400380FC + 4 * line: sock,
                                                   0x40039010 + sock * 0x40: st,
                                                   0x40039008 + sock * 0x40: 0x1234 + sock})
    s.call("UHSIF_IRQHandler", preset={0x40038014: 0, 0x40039010: 0x40})   # no line flag
    s.call("UHSIF_Reg_Cfg", m, 5, 0x12345678)
    s.call("UHSIF_Reg_Cfg", m, 76, 0)
    s.call("UHSIF_Reg_Cfg", 3, 0, 0)
    s.call("UHSIF_Start", 0)


def main():
    elf, mode = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "fpga")
    s = Spike(elf)
    s.emit(f"# libUHSIF spike, mode={mode}; patched {len(s.patch)} insns")
    scenario(s, {"fpga": 0, "soc": 1, "master": 2}[mode])
    print("\n".join(s.log))


if __name__ == "__main__":
    main()
