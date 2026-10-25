# gw_sh gowin.tcl в копии этой папки на диске C:; результат impl/pnr/sdprobe.fs (SRAM по JTAG).
# serdes.csr — из serdes.toml: serdes_toml_to_csr_15k.exe --comment -o serdes.csr serdes.toml
set_device GW5AT-LV15MG132C1/I0 -device_version B
add_file sdprobe.v
add_file serdes.v
add_file sdlib.v
add_file sdprobe.sdc
set_csr serdes.csr
set_option -top_module top
set_option -output_base_name sdprobe
set_option -verilog_std v2001
run all
