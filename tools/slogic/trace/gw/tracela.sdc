// Такты образа: TRACECLK до 84 МГц (STM32F407 на 168 МГц), OSCB ~30 МГц (на деле, не 52,5),
// TCK от FT2232H. Домены связаны только через синхронизаторы и квазистатику — асинхронны.
create_clock -name traceclk -period 11.905 -waveform {0 5.952} [get_ports {ch[12]}]
create_clock -name osc -period 19.0 [get_nets {clk}]
create_clock -name tck -period 100 [get_nets {tck}]
set_clock_groups -asynchronous -group [get_clocks {traceclk}] -group [get_clocks {osc}] -group [get_clocks {tck}]
