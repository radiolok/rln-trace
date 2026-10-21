// Test top: uart_hex and uart_status through uart_mux into uart_tx, a short bit
// time for simulation.
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
    input  logic [63:0] status,
    input  logic        status_start,
    output logic        status_busy,
    output logic        txd
);
    logic [7:0] hex_c, st_c, ch;
    logic       hex_v, hex_r, st_v, st_r, ch_v, ch_r;

    uart_hex u_hex (
        .clk, .rst, .in_data, .in_last, .in_good, .in_valid, .in_ready,
        .out_data(hex_c), .out_valid(hex_v), .out_ready(hex_r)
    );

    uart_status #(.N(2)) u_status (
        .clk, .rst, .words(status), .start(status_start), .busy(status_busy),
        .out_data(st_c), .out_valid(st_v), .out_ready(st_r)
    );

    uart_mux u_mux (
        .clk, .rst,
        .a_data(hex_c), .a_valid(hex_v), .a_ready(hex_r),
        .b_data(st_c), .b_valid(st_v), .b_ready(st_r),
        .out_data(ch), .out_valid(ch_v), .out_ready(ch_r)
    );

    uart_tx #(.DIV(5)) u_tx (.clk, .rst, .data(ch), .valid(ch_v), .ready(ch_r), .tx(txd));
endmodule
