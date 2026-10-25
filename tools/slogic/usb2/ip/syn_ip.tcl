# Синтез одного IP Gowin в нетлист: gw_sh syn_ip.tcl <имя> <верхний модуль> <файлы…>
# (в копии папки на диске C:; результат impl/gwsynthesis/<имя>.vg). Площадки не вставляются.
set name [lindex $argv 0]
set top [lindex $argv 1]
set_device GW5AT-LV15MG132C1/I0 -device_version B
foreach f [lrange $argv 2 end] { add_file $f }
set_option -top_module $top
set_option -output_base_name $name
set_option -verilog_std v2001
set_option -disable_io_insertion 1
run syn
