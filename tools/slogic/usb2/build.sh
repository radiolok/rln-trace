#!/bin/sh
# Сборка образа usb2 в Gowin EDA (Windows) из WSL. IP Gowin синтезируются из зашифрованных
# исходников установленной Gowin EDA в нетлисты (ip/syn_ip.tcl) — в git они не попадают.
#   sh build.sh            → usb2.fs
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
GW=/mnt/c/Gowin/Gowin_V1.9.12.04_x64/IDE
IPC=$GW/ipcore
B=/mnt/c/Users/Public/rln-usb2
SD=$HERE/../sdprobe
mkdir -p "$B/phy" "$B/dev"
if [ ! -f "$B/usb2phy.v" ]; then
    cp "$IPC"/USBTwoSoftPHY/data/* "$HERE/ip/usb2_0_softphy_name.v" "$HERE/ip/syn_ip.tcl" "$B/phy/"
    (cd "$B/phy" && "$GW/bin/gw_sh.exe" syn_ip.tcl usb2phy USB2_0_SoftPHY_Top usb2_0_softphy_top.v usb2_0_softphy.v > syn.log)
    cp "$B/phy/impl/gwsynthesis/usb2phy.vg" "$B/usb2phy.v"
fi
if [ ! -f "$B/usb2dev.v" ]; then
    cp "$IPC"/USB_DEVICE_CONTROLLER/data/* "$HERE/ip/usb_device_controller_define.v" "$HERE/ip/syn_ip.tcl" "$B/dev/"
    (cd "$B/dev" && "$GW/bin/gw_sh.exe" syn_ip.tcl usb2dev USB_Device_Controller_Top usb_device_controller_top.v usb_device_controller.v > syn.log)
    cp "$B/dev/impl/gwsynthesis/usb2dev.vg" "$B/usb2dev.v"
fi
for m in pll_40m pll_usb; do
    if [ ! -f "$B/$m.v" ]; then
        sed "s#^-path .*#-path C:/Users/Public/rln-usb2/#" "$HERE/ip/$m.mod" > "$B/$m.mod"
        (cd "$B" && "$GW/bin/GowinModGen.exe" -do "C:\\Users\\Public\\rln-usb2\\$m.mod" > /dev/null)
    fi
done
cp "$HERE"/usb2.v "$HERE"/usb_desc.v "$HERE"/usb2.cst "$HERE"/usb2.sdc "$HERE"/gowin.tcl "$SD"/serdes.v "$SD"/sdlib.v "$SD"/serdes.toml "$B/"
(cd "$B" && "$GW/bin/serdes_toml_to_csr_15k.exe" --comment -o serdes.csr serdes.toml > /dev/null)
(cd "$B" && "$GW/bin/gw_sh.exe" gowin.tcl > build.log 2>&1) || { tail -20 "$B/build.log"; exit 1; }
grep -E "ERROR" "$B/build.log" && exit 1
rm -f "$HERE/usb2.fs"; cp "$B/impl/pnr/usb2.fs" "$HERE/usb2.fs"
echo "usb2.fs готов"
