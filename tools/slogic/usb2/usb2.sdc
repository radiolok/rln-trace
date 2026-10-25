// 125 МГц: tx_pcs_clkout линии 0 SerDes (генератор на REFCLK0); 60/960 МГц — PLL (выводятся сами), OSCB, TCK
create_clock -name sd_txclk -period 8.0 [get_nets {sd_txclk}]
create_clock -name osc -period 19.0 [get_nets {osc}]
create_clock -name tck -period 100 [get_nets {tck}]
