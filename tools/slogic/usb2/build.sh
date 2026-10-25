#!/bin/sh
# Сборка образа usb2 в Gowin EDA (Windows) из WSL. IP Gowin синтезируются из зашифрованных
# исходников установленной Gowin EDA в нетлисты (ip/syn_ip.tcl) — в git они не попадают.
#   sh build.sh            → usb2.fs   (контроллер Gowin, usb2.v)
#   sh build.sh d          → usb2d.fs  (ядро Daisho + usb2_utmi.v, usb2d.v)
set -e
V=${1:-}
HERE=$(cd "$(dirname "$0")" && pwd)
GW=/mnt/c/Gowin/Gowin_V1.9.12.04_x64/IDE
IPC=$GW/ipcore
B=/mnt/c/Users/Public/rln-usb2
mkdir -p "$B/phy" "$B/dev"
if [ ! -f "$B/usb2phy.v" ]; then
    cp "$IPC"/USBTwoSoftPHY/data/* "$HERE/ip/usb2_0_softphy_name.v" "$HERE/ip/syn_ip.tcl" "$B/phy/"
    (cd "$B/phy" && "$GW/bin/gw_sh.exe" syn_ip.tcl usb2phy USB2_0_SoftPHY_Top usb2_0_softphy_top.v usb2_0_softphy.v > syn.log)
    cp "$B/phy/impl/gwsynthesis/usb2phy.vg" "$B/usb2phy.v"
fi
if [ -z "$V" ] && [ ! -f "$B/usb2dev.v" ]; then
    cp "$IPC"/USB_DEVICE_CONTROLLER/data/* "$HERE/ip/usb_device_controller_define.v" "$HERE/ip/syn_ip.tcl" "$B/dev/"
    (cd "$B/dev" && "$GW/bin/gw_sh.exe" syn_ip.tcl usb2dev USB_Device_Controller_Top usb_device_controller_top.v usb_device_controller.v > syn.log)
    cp "$B/dev/impl/gwsynthesis/usb2dev.vg" "$B/usb2dev.v"
fi
for m in pll_60m pll_usb; do
    if [ ! -f "$B/$m.v" ]; then
        sed "s#^-path .*#-path C:/Users/Public/rln-usb2/#" "$HERE/ip/$m.mod" > "$B/$m.mod"
        (cd "$B" && "$GW/bin/GowinModGen.exe" -do "C:\\Users\\Public\\rln-usb2\\$m.mod" > /dev/null)
    fi
done
cp "$HERE"/usb2.cst "$HERE"/usb2.sdc "$HERE"/../sdprobe/sdlib.v \
   "$HERE"/serdes/serdes.v "$HERE"/serdes/customized_phy.v "$HERE"/serdes/serdes.csr "$B/"
if [ "$V" = d ]; then
    N=usb2d
    mkdir -p "$B/d"
    cp "$HERE"/usb2d.v "$HERE"/usb2_utmi.v "$HERE"/daisho/*.v "$HERE"/daisho/*.vh "$B/d/"
    cp "$B"/usb2phy.v "$B"/pll_60m.v "$B"/pll_usb.v "$B"/usb2.cst "$B"/usb2.sdc "$B"/sdlib.v \
       "$B"/serdes.v "$B"/customized_phy.v "$B"/serdes.csr "$B/d/"
    { echo "set_device GW5AT-LV15MG132C1/I0 -device_version B"
      for f in usb2d.v usb2_utmi.v usb2_top.v usb2_packet.v usb2_protocol.v usb2_ep0.v usb2_ep.v usb2_crc.v \
               usb2_ep_ram.v usb2_ep0in_ram.v usb2_descrip_rom.v serdes.v customized_phy.v sdlib.v \
               pll_60m.v pll_usb.v usb2phy.v usb2.cst usb2.sdc; do echo "add_file $f"; done
      sed -n '/^set_csr/,$p' "$HERE/gowin.tcl" | sed "s/-output_base_name usb2/-output_base_name $N/"
    } > "$B/d/gowin.tcl"
    D="$B/d"
else
    N=usb2
    cp "$HERE"/usb2.v "$HERE"/usb_desc.v "$HERE"/gowin.tcl "$B/"
    D="$B"
fi
(cd "$D" && "$GW/bin/gw_sh.exe" gowin.tcl > build.log 2>&1) || { tail -20 "$D/build.log"; exit 1; }
grep -E "ERROR" "$D/build.log" && exit 1
rm -f "$HERE/$N.fs"; cp "$D/impl/pnr/$N.fs" "$HERE/$N.fs"
echo "$N.fs готов"
