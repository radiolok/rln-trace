# gw_sh gowin.tcl в папке сборки на диске C: (её собирает build.sh); результат impl/pnr/usb2.fs.
set_device GW5AT-LV15MG132C1/I0 -device_version B
add_file usb2.v
add_file usb_desc.v
add_file serdes.v
add_file sdlib.v
add_file pll_40m.v
add_file pll_usb.v
add_file usb2phy.v
add_file usb2dev.v
add_file usb2.cst
add_file usb2.sdc
set_csr serdes.csr
set_option -top_module top
set_option -output_base_name usb2
set_option -verilog_std v2001
set_option -use_sspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1
run all
