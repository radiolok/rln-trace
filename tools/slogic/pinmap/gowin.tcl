# gw_sh gowin.tcl в копии этой папки; результат impl/pnr/pinmap.bin
set_device GW5AT-LV15CS130C1/I0 -device_version B
add_file pinmap.v
add_file pinmap.cst
set_option -top_module top
set_option -output_base_name pinmap
# все конфигурационные выводы, кроме JTAG, RECONFIG_N, DONE, READY и MODE, — обычные входы
set_option -use_mspi_as_gpio 1
set_option -use_sspi_as_gpio 1
set_option -use_cpu_as_gpio 1
set_option -use_i2c_as_gpio 1
# кнопка MODE (RECONFIG_N) грузит золотой образ DFU
set_option -multi_boot 1
set_option -multiboot_spi_flash_address 800000
set_option -multiboot_address_width 24
run all
