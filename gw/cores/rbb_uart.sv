// remote_bitbang over a UART: uart_rx -> rbb_jtag -> uart_tx.
//
// SPDX-License-Identifier: BSD-3-Clause

module rbb_uart #(
    parameter int DIV = 27              // 27 MHz / 1 Mbaud
) (
    input  logic clk,
    input  logic rst,
    input  logic rxd,
    output logic txd,
    output logic rx_strobe,             // a byte came in

    output logic tck,
    output logic tms,
    output logic tms_oe,
    input  logic swdio,
    output logic tdi,
    input  logic tdo,
    output logic trst,
    output logic srst,
    output logic led
);
    logic [7:0] cmd, ans;
    logic       ans_valid, ans_ready;

    uart_rx #(.DIV(DIV)) u_rx (.clk, .rst, .rx(rxd), .data(cmd), .valid(rx_strobe));

    rbb_jtag u_jtag (
        .clk, .rst, .cmd, .cmd_valid(rx_strobe),
        .ans, .ans_valid, .ans_ready,
        .tck, .tms, .tms_oe, .swdio, .tdi, .tdo, .trst, .srst, .led
    );

    uart_tx #(.DIV(DIV)) u_tx (.clk, .rst, .data(ans), .valid(ans_valid), .ready(ans_ready), .tx(txd));
endmodule
