#!/bin/sh
# Симуляция ядра Daisho + usb2_utmi (iverilog из OSS CAD Suite). Запускать из tools/slogic/usb2:
#   sh sim/run.sh        # HS
#   sh sim/run.sh -DFS   # FS
set -e
cd "$(dirname "$0")/.."
OSS=${OSS:-$HOME/.local/opt/oss-cad-suite/bin}
D=daisho
"$OSS/iverilog" -g2005 -I $D "$@" -o sim/tb_usb2d.vvp sim/tb_usb2d.v usb2_utmi.v \
    $D/usb2_top.v $D/usb2_packet.v $D/usb2_protocol.v $D/usb2_ep0.v $D/usb2_ep.v $D/usb2_crc.v \
    $D/usb2_ep_ram.v $D/usb2_ep0in_ram.v $D/usb2_descrip_rom.v
"$OSS/vvp" -n sim/tb_usb2d.vvp
