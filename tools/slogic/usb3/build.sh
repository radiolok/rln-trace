#!/bin/sh
# Сборка образа USB3 в Gowin EDA (Windows) из WSL. Стек — ciniml/rtl/usb3 (Veryl → SystemVerilog, `veryl` в PATH).
# IP Gowin генерируются из установленной Gowin EDA: обёртка SerDes — GowinModGen (ip/serdes.mod), тела USB 3.0 PHY
# и арбитра upar — синтезом зашифрованных исходников в нетлисты (как IP в usb2). В git они не попадают.
#
# pclk 125 МГц на GW5AT-15 закрывается не в каждой расстановке, а зерна у PnR Gowin нет: варианты PnR (place_option
# 1..4) собираются параллельно, в usb3ref.fs идёт тот, у которого pclk выше.
#   sh build.sh d                                 → usb3d.fs (SRAM по JTAG), usb3d.bin (флеш через DFU, multiboot → DFU)
#   sh build.sh                                   → usb3ref.fs  (эталонный верх ciniml/board/top.v)
#   PLACE="3 4" sh build.sh                       — только эти place_option
#   PNR_EXTRA="replicate_resources=1" sh build.sh — добавить опции ко всем вариантам
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
GW=/mnt/c/Gowin/Gowin_V1.9.12.04_x64/IDE
IPC=$GW/ipcore/SERDES_IP
B=/mnt/c/Users/Public/rln-usb3
WB='C:\Users\Public\rln-usb3'
if [ "${1:-}" = d ]; then
    N=usb3d; TOPM=usb3d
    TOPF="$HERE/usb3d.v"; CST="$HERE/usb3d.cst"; SDC="$HERE/usb3d.sdc"
else
    N=usb3ref; TOPM=top
    TOPF="$HERE/ciniml/board/top.v"; CST="$HERE/ciniml/board/pins.cst"; SDC="$HERE/ciniml/board/timing.sdc"
fi
PLACE=${PLACE:-"1 2 3 4"}
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
C="$HERE/ciniml/board"

# один вариант PnR в своей папке: build_one <метка> <опции>; печатает «<метка> <pclk>»
build_one() {
    D="$B/${N}_$1"
    rm -rf "${D:?}"; mkdir -p "$D"
    for f in $U; do cp "$HERE/ciniml/rtl/usb3/$f.sv" "$D/"; done
    cp "$TOPF" "$D/top.v"; cp "$CST" "$D/pins.cst"; cp "$SDC" "$D/timing.sdc"
    cp "$HERE/u3stream.v" "$HERE/afifo.v" "$D/"
    cp "$C/pll_ref125.v" "$C/jtag_status.v" "$C/serdes.csr" \
       "$B/ip/serdes.v" "$B/upar_arbiter.vg" "$B/usb3_0_phy.vg" "$GW/data/ipcores/gw_jtag.v" "$D/"
    echo "// пусто: TRACE и прочие define эталона не используются" > "$D/defines_gen.v"
    { echo "set_device GW5AT-LV15MG132C1/I0 -device_version B"
      for f in defines_gen.v top.v pll_ref125.v; do echo "add_file $f"; done
      [ "$N" = usb3d ] && echo "add_file u3stream.v" && echo "add_file afifo.v"
      for f in $U; do echo "add_file $f.sv"; done
      for f in jtag_status.v serdes.v upar_arbiter.vg usb3_0_phy.vg gw_jtag.v pins.cst timing.sdc; do echo "add_file $f"; done
      echo "set_csr serdes.csr"
      echo "set_option -top_module $TOPM"
      echo "set_option -output_base_name $N"
      echo "set_option -verilog_std sysv2017"
      for o in done ready cpu i2c sspi; do echo "set_option -use_${o}_as_gpio 1"; done
      # multiboot на золотой образ (DFU): после записи во флеш кнопка MODE возвращает прибор в DFU
      echo "set_option -multi_boot 1"
      echo "set_option -multiboot_spi_flash_address 800000"
      echo "set_option -multiboot_address_width 24"
      echo "set_option -bit_format bin"
      for kv in $2; do echo "set_option -${kv%%=*} ${kv#*=}"; done
      echo "run all"; } > "$D/gowin.tcl"
    if (cd "$D" && "$GW/bin/gw_sh.exe" gowin.tcl > build.log 2>&1) && ! grep -q "ERROR" "$D/build.log"; then
        echo "$1 $(grep -m1 -oE "pclk +125\.000\(MHz\) +[0-9.]+" "$D/impl/pnr/$N.tr" | awk '{print $3}')"
    else
        echo "$1 ошибка" ; tail -5 "$D/build.log" >&2
    fi
}

R="$B/results.txt"
: > "$R"
for p in $PLACE; do
    build_one "p$p" "place_option=$p route_option=2 serdesRetiming=1 ${PNR_EXTRA:-}" >> "$R" &
done
wait
sort -k2 -rn "$R" | sed 's/^/  /'
BEST=$(grep -v ошибка "$R" | sort -k2 -rn | head -1)
[ -n "$BEST" ] || { echo "ни один вариант не собрался"; exit 1; }
set -- $BEST
rm -f "$HERE/$N.fs" "$HERE/$N.bin"; cp "$B/${N}_$1/impl/pnr/$N.fs" "$HERE/$N.fs"
[ -f "$B/${N}_$1/impl/pnr/$N.bin" ] && cp "$B/${N}_$1/impl/pnr/$N.bin" "$HERE/$N.bin"
OK=$(awk -v f="$2" 'BEGIN { print (f >= 125) ? "закрыт" : "НЕ закрыт" }')
echo "$N.fs ← вариант $1: pclk $2 МГц, тайминг $OK"
