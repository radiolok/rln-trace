// Test top: uart_hex -> uart_tx, a short bit time for simulation.
//
// SPDX-License-Identifier: BSD-3-Clause

module uart_hex_top (
    input  logic        clk,
    input  logic        rst,
    input  logic [31:0] in_data,
    input  logic        in_last,
    input  logic        in_good,
    input  logic        in_valid,
    output logic        in_ready,
    output logic        txd
);
    logic [7:0] ch;
    logic       ch_valid, ch_ready;

    uart_hex u_hex (
        .clk, .rst, .in_data, .in_last, .in_good, .in_valid, .in_ready,
        .out_data(ch), .out_valid(ch_valid), .out_ready(ch_ready)
    );

    uart_tx #(.DIV(5)) u_tx (.clk, .rst, .data(ch), .valid(ch_valid), .ready(ch_ready), .tx(txd));
endmodule
