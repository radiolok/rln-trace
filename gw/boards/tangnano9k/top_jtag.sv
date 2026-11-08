// Tang Nano 9K on the bench: JTAG probe for the STM32F4-Discovery (bench step 6,
// first piece). OpenOCD speaks remote_bitbang to sw/rbb/rbb_bridge.py, which
// forwards the bytes to the BL702 UART; rbb_jtag drives the pins.
//
//   clk27 straight, no PLL; UART DIV = 27 MHz / baud: 9 = 3 Mbaud (default), 18 = 1.5, 27 = 1.
//   nSRST is open drain (the Discovery has its own pull-up and reset button),
//   nTRST push-pull. TDO has the pad pull-up.
//
// S1 (pin 4) reset. LEDs (lit low): 0 remote_bitbang 'B', 1 UART activity,
// 2 srst asserted, 3 trst asserted, 4 TDO level, 5 heartbeat.
//
// SPDX-License-Identifier: BSD-3-Clause

module top_jtag #(
    parameter int DIV = 9               // 3 Mbaud
) (
    input  logic       clk27,
    input  logic       s1_n,
    output logic [5:0] led_n,
    input  logic       uart_rxd,
    output logic       uart_txd,

    output logic       jtck,
    output logic       jtms,
    output logic       jtdi,
    input  logic       jtdo,
    output logic       jtrst_n,
    output tri         jsrst_n
);
    logic [2:0] rst_s;
    wire        rst = rst_s[2];

    always_ff @(posedge clk27)
        rst_s <= {rst_s[1:0], !s1_n};

    logic rx_strobe, trst, srst, led;

    rbb_uart #(.DIV(DIV)) u_rbb (
        .clk(clk27), .rst, .rxd(uart_rxd), .txd(uart_txd), .rx_strobe,
        .tck(jtck), .tms(jtms), .tdi(jtdi), .tdo(jtdo), .trst, .srst, .led
    );

    assign jtrst_n = !trst;
    assign jsrst_n = srst ? 1'b0 : 1'bz;

    // activity: ~40 ms after the last byte
    logic [20:0] act;
    logic [24:0] beat;

    always_ff @(posedge clk27) begin
        beat <= beat + 1'b1;
        if (rx_strobe)
            act <= '1;
        else if (act != '0)
            act <= act - 1'b1;
    end

    assign led_n = ~{beat[24], jtdo, trst, srst, act != '0, led};
endmodule
