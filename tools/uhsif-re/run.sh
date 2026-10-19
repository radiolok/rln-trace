#!/bin/sh
# Full libUHSIF.a teardown: fetch, relink, Ghidra decompile, disassemble, spike traces,
# then build the open driver (fw/uhsif) and check it against the library in the spike.
# Output goes to build/ (git-ignored).  Needs: curl, binutils (ar), Python 3 venv with
# pyelftools capstone unicorn ziglang; Ghidra in $GHIDRA (optional, skipped if unset).
# libUHSIF.a comes from the au/ch32h417 submodule; WCH_REF=<rev> downloads that revision instead.
set -eu
cd "$(dirname "$0")"
PY=${PY:-python3}
B=build
mkdir -p $B/lib
SUB=../../au/ch32h417/EVT/EXAM/UHSIF/UHSIF_SLAVE/Common/libUHSIF.a
URL=https://raw.githubusercontent.com/openwch/ch32h417/${WCH_REF:-main}/EVT/EXAM/UHSIF/UHSIF_SLAVE/Common/libUHSIF.a
if [ -z "${WCH_REF:-}" ] && [ -f $SUB ]; then
    cp $SUB $B/lib/libUHSIF.a                  # submodule au/ch32h417
elif [ ! -f $B/lib/libUHSIF.a ]; then
    curl -sSLf --retry 5 --retry-all-errors -o $B/lib/libUHSIF.a $URL
fi
sha256sum $B/lib/libUHSIF.a
(cd $B/lib && ar x libUHSIF.a)

# every external symbol -> trap address 0x00F00000 + 16*i
DS=$(nm $B/lib/lib.o | awk '$1=="U"{print $2}' | awk '{printf " --defsym=%s=0x%x", $1, 15728640 + 16*(NR-1)}')
$PY -m ziglang ld.lld -m elf32lriscv --no-relax -T link.ld $DS -e UHSIF_Cfg $B/lib/lib.o -o $B/uhsif.elf -Map $B/uhsif.map

$PY -I disasm.py $B/uhsif.elf > $B/uhsif.dis
for m in fpga soc master; do
    $PY -I spike.py $B/uhsif.elf $m > $B/trace_$m.txt
    $PY -I pinmap.py $B/uhsif.elf $m > $B/pinmap_$m.md
done

# open driver: tables from libUHSIF.a, RV32IMAC build with zig cc, same stubs, compare
O=$B/open
mkdir -p $O
$PY -I extract_tables.py $B/lib/lib.o > $O/uhsif_tables.c
for f in ../../fw/uhsif/uhsif.c $O/uhsif_tables.c; do
    $PY -m ziglang cc -target riscv32-freestanding-none -mcpu=generic_rv32+m+a+c -Os \
        -ffunction-sections -fdata-sections -fno-builtin -DUHSIF_NO_STDPERIPH -I../../fw/uhsif \
        -Wall -Wextra -Werror -c $f -o $O/$(basename $f .c).o
done
DS=$(nm $O/uhsif.o $O/uhsif_tables.o | awk '$1=="U"{print $2}' | sort -u | grep -vx uhsif_tables \
    | awk '{printf " --defsym=%s=0x%x", $1, 15728640 + 16*(NR-1)}')
$PY -m ziglang ld.lld -m elf32lriscv --no-relax -T link.ld $DS -e UHSIF_Cfg $O/uhsif.o $O/uhsif_tables.o -o $O/uhsif_open.elf
rc=0; $PY -I compare.py $B/uhsif.elf $O/uhsif_open.elf > $B/compare.txt || rc=$?
cat $B/compare.txt
[ $rc -eq 0 ] || exit $rc

if [ -n "${GHIDRA:-}" ]; then
    mkdir -p $B/ghidra
    "$GHIDRA/support/analyzeHeadless" $B/ghidra uhsif -import $B/uhsif.elf -overwrite \
        -scriptPath "$PWD" -postScript DumpAll.java "$PWD/$B/uhsif.c" > $B/ghidra.log 2>&1
fi
ls -l $B
