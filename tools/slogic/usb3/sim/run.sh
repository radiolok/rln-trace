#!/bin/sh
# Симуляция тракта потока usb3d (u3stream, afifo) в iverilog из OSS CAD Suite. Запускать из tools/slogic/usb3:
#   sh sim/run.sh
set -e
cd "$(dirname "$0")/.."
OSS=${OSS:-$HOME/.local/opt/oss-cad-suite/bin}
"$OSS/iverilog" -g2012 -s tb -o sim/tb_stream.vvp sim/tb_stream.v u3stream.v afifo.v
"$OSS/vvp" -n sim/tb_stream.vvp
