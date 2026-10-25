# gw_sh gowin.tcl в копии этой папки на диске C:; результат impl/pnr/tracela.fs (SRAM по JTAG)
set_device GW5AT-LV15MG132C1/I0 -device_version B
add_file tracela.v
add_file tracela.cst
add_file tracela.sdc
set_option -top_module top
set_option -output_base_name tracela
set_option -verilog_std v2001
set_option -use_sspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1
# MODE (RECONFIG_N) должна вернуть золотой образ DFU, если образ попадёт во флеш
set_option -multi_boot 1
set_option -multiboot_spi_flash_address 800000
set_option -multiboot_address_width 24
run all
