#!/bin/sh
# Опыт: варианты ограничений выводов USB при том же нетлисте. Аргументы — имя:sed-выражение к usb2.cst.
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
GW=/mnt/c/Gowin/Gowin_V1.9.12.04_x64/IDE
SRC=/mnt/c/Users/Public/rln-usb2
for v in "$@"; do
    name=${v%%:*}; expr=${v#*:}
    B=/mnt/c/Users/Public/rln-usb2-$name
    rm -rf "$B"; mkdir -p "$B"
    cp "$SRC"/*.v "$SRC"/*.cst "$SRC"/*.sdc "$SRC"/gowin.tcl "$SRC"/serdes.csr "$B/"
    sed -i "$expr" "$B/usb2.cst"
    ( cd "$B" && "$GW/bin/gw_sh.exe" gowin.tcl > build.log 2>&1 && cp impl/pnr/usb2.fs "$HERE/usb2-$name.fs" \
      && echo "$name готов" || { echo "$name: ОШИБКА"; grep ERROR build.log | head -3; } ) &
done
wait
