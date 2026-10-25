#!/bin/sh
# Сборка образа USB3 в Gowin EDA (Windows) из WSL. Стек — ciniml/rtl/usb3 (Veryl → SystemVerilog, `veryl` в PATH).
# IP Gowin генерируются из установленной Gowin EDA: обёртка SerDes — GowinModGen (ip/serdes.mod), тела USB 3.0 PHY
# и арбитра upar — синтезом зашифрованных исходников в нетлисты (как IP в usb2). В git они не попадают.
#   sh build.sh                          → usb3ref.fs  (эталонный верх ciniml/board/top.v)
#   PNR="place_option=3 serdesRetiming=1" TAG=x sh build.sh   — опции PnR, своя папка сборки
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
GW=/mnt/c/Gowin/Gowin_V1.9.12.04_x64/IDE
IPC=$GW/ipcore/SERDES_IP
B=/mnt/c/Users/Public/rln-usb3
WB='C:\Users\Public\rln-usb3'
N=usb3ref
PNR=${PNR-"place_option=3 route_option=2 serdesRetiming=1"}
mkdir -p "$B/ip" "$B/upar" "$B/phy"

# IP: один раз (стереть $B, чтобы пересоздать)
if [ ! -f "$B/ip/serdes.v" ]; then
    cp "$HERE/ip/serdes.mod" "$B/ip/"
    (cd /mnt/c && "$GW/bin/GowinModGen.exe" -do "$WB\\ip\\serdes.mod" > /dev/null)
fi
if [ ! -f "$B/upar_arbiter.vg" ]; then
    cp "$IPC"/data/Upar_Arbiter/* "$HERE/../usb2/ip/syn_ip.tcl" "$B/upar/"
    cp "$HERE/ip/upar_define.vh" "$B/upar/define.vh"
    cp "$HERE/ip/upar_parameter.vh" "$B/upar/parameter.vh"
    (cd "$B/upar" && "$GW/bin/gw_sh.exe" syn_ip.tcl upar_arbiter "~upar_arbiter_wrap.SerDes_Top" \
        upar_arbiter_wrap.v upar_arbiter.v > syn.log)
    cp "$B/upar/impl/gwsynthesis/upar_arbiter.vg" "$B/"
fi
if [ ! -f "$B/usb3_0_phy.vg" ]; then
    cp "$IPC"/IPlib/USB30PHY/data/* "$HERE/ip/usb3_0_phy_name.v" "$HERE/ip/usb3_0_phy_top_define.vh" \
       "$HERE/../usb2/ip/syn_ip.tcl" "$B/phy/"
    (cd "$B/phy" && "$GW/bin/gw_sh.exe" syn_ip.tcl usb3_0_phy USB3_0_PHY_Top usb3_0_phy_top.v usb3_0_phy.v > syn.log)
    cp "$B/phy/impl/gwsynthesis/usb3_0_phy.vg" "$B/"
fi

# стек: Veryl → SystemVerilog
(cd "$HERE/ciniml/rtl/usb3" && veryl build > /dev/null 2>&1)
U="usb3_pkg usb3_crc_pkg usb3_scrambler usb3_rx_fifo usb3_rx_parser usb3_tx_framer usb3_ltssm usb3_link usb3_top
   usb3_descriptor_rom usb3_device"

D="$B/${N}${TAG:+_$TAG}"
rm -rf "${D:?}"; mkdir -p "$D"
for f in $U; do cp "$HERE/ciniml/rtl/usb3/$f.sv" "$D/"; done
C="$HERE/ciniml/board"
cp "$C/top.v" "$C/pll_ref125.v" "$C/jtag_status.v" "$C/pins.cst" "$C/timing.sdc" "$C/serdes.csr" \
   "$B/ip/serdes.v" "$B/upar_arbiter.vg" "$B/usb3_0_phy.vg" "$GW/data/ipcores/gw_jtag.v" "$D/"
echo "// пусто: TRACE и прочие define эталона не используются" > "$D/defines_gen.v"
{ echo "set_device GW5AT-LV15MG132C1/I0 -device_version B"
  for f in defines_gen.v top.v pll_ref125.v; do echo "add_file $f"; done
  for f in $U; do echo "add_file $f.sv"; done
  for f in jtag_status.v serdes.v upar_arbiter.vg usb3_0_phy.vg gw_jtag.v pins.cst timing.sdc; do echo "add_file $f"; done
  echo "set_csr serdes.csr"
  echo "set_option -top_module top"
  echo "set_option -output_base_name $N"
  echo "set_option -verilog_std sysv2017"
  for o in done ready cpu i2c sspi; do echo "set_option -use_${o}_as_gpio 1"; done
  for kv in $PNR; do echo "set_option -${kv%%=*} ${kv#*=}"; done
  echo "run all"; } > "$D/gowin.tcl"
(cd "$D" && "$GW/bin/gw_sh.exe" gowin.tcl > build.log 2>&1) || { tail -20 "$D/build.log"; exit 1; }
grep -E "ERROR" "$D/build.log" && exit 1
F=$(grep -m1 -oE "pclk +125\.000\(MHz\) +[0-9.]+" "$D/impl/pnr/$N.tr" | awk '{print $3}')
OUT="$HERE/$N${TAG:+_$TAG}.fs"
rm -f "$OUT"; cp "$D/impl/pnr/$N.fs" "$OUT"
echo "$(basename "$OUT") готов, pclk ${F:-?} МГц (нужно 125)"
