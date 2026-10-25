// Такты: OSCB ~30 МГц, TCK, такты квада до 250 МГц — все асинхронны друг другу
create_clock -name osc -period 19.0 [get_nets {clk}]
create_clock -name tck -period 100 [get_nets {tck}]
