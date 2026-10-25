#!/bin/sh
# Опыт: варианты настроек SoftPHY параллельно. Каждый — своя папка на C:, нетлист PHY
# пересинтезируется со своим usb2_0_softphy_name.v, остальное — из готовой папки сборки.
#   sh variants.sh "tx1n:1:" "tx1a:1:V_120" …   → usb2-<имя>.fs
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
GW=/mnt/c/Gowin/Gowin_V1.9.12.04_x64/IDE
SRC=/mnt/c/Users/Public/rln-usb2
for v in "$@"; do
    name=${v%%:*}; rest=${v#*:}; txd=${rest%%:*}; extra=${rest#*:}
    B=/mnt/c/Users/Public/rln-usb2-$name
    rm -rf "$B"; mkdir -p "$B/phy"
    cp "$SRC"/*.v "$SRC"/*.cst "$SRC"/*.sdc "$SRC"/gowin.tcl "$SRC"/serdes.csr "$B/"
    cp "$GW"/ipcore/USBTwoSoftPHY/data/* "$HERE/ip/syn_ip.tcl" "$B/phy/"
    { printf '`define module_name USB2_0_SoftPHY_Top\n`define TX_DELAY_%s_BIT\n`define UTMI\n' "$txd"
      [ -n "$extra" ] && printf '`define %s\n' $extra
      printf '`define GW5AT\n'
      for k in VENDOR_ID_HIGH VENDOR_ID_LOW PRODUCT_ID_HIGH PRODUCT_ID_LOW; do printf "\`define DEFAULT_%s 8'h00\n" $k; done
    } > "$B/phy/usb2_0_softphy_name.v"
    ( cd "$B/phy" && "$GW/bin/gw_sh.exe" syn_ip.tcl usb2phy USB2_0_SoftPHY_Top usb2_0_softphy_top.v usb2_0_softphy.v > syn.log 2>&1 \
      && cp impl/gwsynthesis/usb2phy.vg ../usb2phy.v && cd .. && "$GW/bin/gw_sh.exe" gowin.tcl > build.log 2>&1 \
      && cp impl/pnr/usb2.fs "$HERE/usb2-$name.fs" && echo "$name готов" || echo "$name: ОШИБКА" ) &
done
wait
