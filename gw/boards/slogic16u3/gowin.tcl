# gw_sh gowin.tcl in a copy of this folder on drive C: (Gowin EDA 1.9.12.04, Windows)
set_device GW5AT-LV15MG132C1/I0 -device_version B
add_file top.sv
add_file slogic16u3.cst
set_option -top_module top_slogic16u3
set_option -output_base_name slogic16u3
set_option -verilog_std sysv2017
# CPU/SSPI/I2C dual-purpose pins are plain GPIO; MSPI (flash), JTAG, RECONFIG_N,
# DONE, READY and MODE stay configuration pins
set_option -use_sspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1
# the MODE button (RECONFIG_N) must load the golden DFU image
set_option -multi_boot 1
set_option -multiboot_spi_flash_address 800000
set_option -multiboot_address_width 24
run all
