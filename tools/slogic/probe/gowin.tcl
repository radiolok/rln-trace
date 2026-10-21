# gw_sh gowin.tcl в копии этой папки; результат impl/pnr/probe.bin
set_device GW5AT-LV15CS130C1/I0 -device_version B
add_file probe.v
set_option -top_module top
set_option -output_base_name probe
# RECONFIG_N (кнопка MODE, если она разведена на него) грузит золотой образ DFU
set_option -multi_boot 1
set_option -multiboot_spi_flash_address 800000
set_option -multiboot_address_width 24
run all
