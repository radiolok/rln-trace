// 62,5 МГц от генератора 125 МГц через SerDes Q0; 60/480 МГц — PLL (выводятся сами), OSCB, TCK
create_clock -name ref62 -period 16.0 [get_pins {sd/gtr12_quad_inst0/FABRIC_CM1_LIFE_CLK_O}]
create_clock -name osc -period 19.0 [get_nets {osc}]
create_clock -name tck -period 100 [get_nets {tck}]
