# Gowin EDA batch build of top_step0 (gw_sh gowin.tcl), run by `make -C gw board-gowin`
# in a copy of the sources: src/*.sv, src/tangnano20k.cst, src/top_step0.sdc.
set_device GW2AR-LV18QN88C8/I7 -device_version C
foreach f [lsort [glob src/*.sv]] { add_file $f }
add_file src/tangnano20k.cst
add_file src/top_step0.sdc
set_option -top_module top_step0
set_option -verilog_std sysv2017
set_option -output_base_name top_step0
# pins 85/86 double as SSPI, 80 and others as MSPI on the GW2AR: free them for user IO
set_option -use_sspi_as_gpio 1
set_option -use_mspi_as_gpio 1
set_option -use_ready_as_gpio 1
set_option -use_done_as_gpio 1
set_option -rw_check_on_ram 1
run all
