#!/bin/sh
# Линт Verilator (-Wall) своего кода usb3d вместе со стеком (SystemVerilog из veryl build). Запускать из tools/slogic/usb3:
#   sh sim/lint.sh
# Примитивы Gowin и ciniml/board — заглушки (sim/gowin_stubs.v). Отключено одно: PROCASSINIT — начальные значения
# регистров в объявлении для ПЛИС Gowin нарочные (состояние после конфигурации, так же пишет эталон ciniml).
# Стек ciniml (вершины Usb3Top и Usb3Device) — с отключениями из его Veryl.toml и ещё PINCONNECTEMPTY: так Veryl
# выводит неподключённый выход (`o_lfsr: _`).
set -e
cd "$(dirname "$0")/.."
V=${OSS:-$HOME/.local/opt/oss-cad-suite/bin}/verilator
R=ciniml/rtl/usb3
(cd $R && veryl build > /dev/null 2>&1)
SV="$R/usb3_pkg.sv $R/usb3_crc_pkg.sv $R/usb3_descriptor_rom.sv $R/usb3_scrambler.sv $R/usb3_rx_fifo.sv
    $R/usb3_rx_parser.sv $R/usb3_tx_framer.sv $R/usb3_ltssm.sv $R/usb3_link.sv $R/usb3_top.sv $R/usb3_device.sv"
echo "== usb3d.v (-Wall)"
$V --lint-only -Wall -Wno-PROCASSINIT --top-module usb3d sim/gowin_stubs.v $SV usb3d.v u3stream.v afifo.v 2>&1 \
    | grep -E "^%(Warning|Error)" | grep -E "usb3d\.v|u3stream\.v|afifo\.v|gowin_stubs" || echo "чисто"
echo "== стек ciniml (отключения Veryl.toml)"
W=$(sed -n '/compile_args/,/]/p' $R/Veryl.toml | grep -oE '"-Wno-[A-Z]+"' | tr -d '"' | tr '\n' ' ')
for t in Usb3Top Usb3Device; do
    O=$($V --lint-only -Wall $W -Wno-PROCASSINIT -Wno-DECLFILENAME -Wno-PINCONNECTEMPTY --top-module $t $SV 2>&1 \
        | grep -E "^%(Warning|Error)" | grep -v "Exiting due" | sort -u || true)
    if [ -n "$O" ]; then echo "$t:"; echo "$O"; else echo "$t: чисто"; fi
done
