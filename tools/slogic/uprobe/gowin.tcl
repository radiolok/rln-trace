# gw_sh gowin.tcl в копии этой папки на диске C:; результат impl/pnr/uprobe.fs (SRAM по JTAG)
set_device GW5AT-LV15MG132C1/I0 -device_version B
add_file uprobe.v
add_file uprobe.cst
set_option -top_module top
set_option -output_base_name uprobe
set_option -verilog_std v2001
# двойные выводы SSPI, CPU (D04–D15) и I2C — обычные входы; MSPI (флеш), JTAG, RECONFIG_N,
# DONE, READY, MODE остаются служебными
set_option -use_sspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1
run all
