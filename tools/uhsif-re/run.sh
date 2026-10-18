#!/bin/sh
# Full libUHSIF.a teardown: fetch, relink, Ghidra decompile, disassemble, spike traces.
# Output goes to build/ (git-ignored).  Needs: curl, binutils (ar), Python 3 venv with
# pyelftools capstone unicorn ziglang; Ghidra in $GHIDRA (optional, skipped if unset).
set -eu
cd "$(dirname "$0")"
PY=${PY:-python3}
B=build
mkdir -p $B/lib
URL=https://raw.githubusercontent.com/openwch/ch32h417/main/EVT/EXAM/UHSIF/UHSIF_SLAVE/Common/libUHSIF.a
[ -f $B/lib/libUHSIF.a ] || curl -sSLf --retry 3 -o $B/lib/libUHSIF.a $URL
(cd $B/lib && ar x libUHSIF.a)

# every external symbol -> trap address 0x00F00000 + 16*i
DS=$(nm $B/lib/lib.o | awk '$1=="U"{print $2}' | awk '{printf " --defsym=%s=0x%x", $1, 15728640 + 16*(NR-1)}')
$PY -m ziglang ld.lld -m elf32lriscv --no-relax -T link.ld $DS -e UHSIF_Cfg $B/lib/lib.o -o $B/uhsif.elf -Map $B/uhsif.map

$PY -I disasm.py $B/uhsif.elf > $B/uhsif.dis
for m in fpga soc master; do
    $PY -I spike.py $B/uhsif.elf $m > $B/trace_$m.txt
    $PY -I pinmap.py $B/uhsif.elf $m > $B/pinmap_$m.md
done

if [ -n "${GHIDRA:-}" ]; then
    mkdir -p $B/ghidra
    "$GHIDRA/support/analyzeHeadless" $B/ghidra uhsif -import $B/uhsif.elf -overwrite \
        -scriptPath "$PWD" -postScript DumpAll.java "$PWD/$B/uhsif.c" > $B/ghidra.log 2>&1
fi
ls -l $B
