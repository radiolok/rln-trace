// Tang Nano 9K on the bench: CMSIS-DAP probe for the STM32F4-Discovery (bench
// step 6, the shifting engine). dap_core takes whole CMSIS-DAP packets framed
// over the BL702 UART (sw/dap/dap_uart.py); the same wires as top_jtag:
// TCK/SWCLK, TMS/SWDIO, TDI, TDO, nTRST, nSRST (open drain).
//
// S1 (pin 4) reset. LEDs (lit low): 0 SWDIO driven, 1 UART activity,
// 2 srst asserted, 3 trst asserted, 4 TDO level, 5 heartbeat.
//
// SPDX-License-Identifier: BSD-3-Clause

module top_dap #(
    parameter int DIV = 9               // 3 Mbaud
) (
    input  logic       clk27,
    input  logic       s1_n,
    output logic [5:0] led_n,
    input  logic       uart_rxd,
    output logic       uart_txd,

    output logic       jtck,
    inout  tri         jtms,            // TMS / SWDIO
    output logic       jtdi,
    input  logic       jtdo,
    output logic       jtrst_n,
    output tri         jsrst_n
);
    // reset: S1, and 16 cycles after configuration (flip-flops start at 0)
    logic [2:0] rst_s;
    logic [4:0] por = '0;
    wire        rst = rst_s[2] || !por[4];

    always_ff @(posedge clk27) begin
        rst_s <= {rst_s[1:0], !s1_n};
        if (!por[4])
            por <= por + 1'b1;
    end

    logic rx_strobe, tms, tms_oe, trst, srst;

    dap_uart #(.CLK_HZ(27000000), .DIV(DIV)) u_dap (
        .clk(clk27), .rst, .rxd(uart_rxd), .txd(uart_txd), .rx_strobe,
        .tck(jtck), .tms, .tms_oe, .swdio(jtms), .tdi(jtdi), .tdo(jtdo), .trst, .srst
    );

    assign jtms    = tms_oe ? tms : 1'bz;
    assign jtrst_n = !trst;
    assign jsrst_n = srst ? 1'b0 : 1'bz;

    logic [20:0] act;
    logic [24:0] beat;

    always_ff @(posedge clk27) begin
        beat <= beat + 1'b1;
        if (rx_strobe)
            act <= '1;
        else if (act != '0)
            act <= act - 1'b1;
    end

    assign led_n = ~{beat[24], jtdo, trst, srst, act != '0, tms_oe};
endmodule
