// Self-test source over HSPI: selftest_gen blocks, one block per HSPI packet.
// Step 0 of the bench plan: FPGA -> HSPI -> CH569 -> USB -> sw/usbstream.
//
// SPDX-License-Identifier: BSD-3-Clause

module selftest_hspi #(
    parameter int W = 16,
    parameter int CRC_W = (W == 32) ? 32 : 16,
    parameter logic [CRC_W-1:0] CRC_INIT = '0,
    parameter bit CRC_REFLECT = 1'b0,
    parameter logic [CRC_W-1:0] CRC_XOROUT = '0
) (
    input  logic         clk,
    input  logic         rst,

    input  logic         cfg_enable,
    input  logic         cfg_kind,
    input  logic [13:0]  cfg_block_words,   // at most 1024: an HSPI packet carries 4096 bytes
    input  logic [25:0]  cfg_usdf,
    input  logic         cfg_hold,
    input  logic [7:0]   cfg_gap,
    input  logic [7:0]   cfg_ack_timeout,

    output logic         hspi_req,
    output logic         hspi_vld,
    output logic [W-1:0] hspi_data,
    output logic         hspi_oe,
    input  logic         hspi_ack,

    output logic [3:0]   seq,               // number of the next HSPI packet
    output logic [31:0]  cnt_blocks,
    output logic [31:0]  cnt_packets,
    output logic [31:0]  cnt_ack_timeout
);
    logic [31:0] data;
    logic        last, valid, ready;

    selftest_gen u_gen (
        .clk, .rst,
        .cfg_enable, .cfg_kind, .cfg_block_words,
        .out_data(data), .out_last(last), .out_valid(valid), .out_ready(ready),
        .cnt_blocks
    );

    hspi_tx #(
        .W(W), .CRC_W(CRC_W), .CRC_INIT(CRC_INIT), .CRC_REFLECT(CRC_REFLECT), .CRC_XOROUT(CRC_XOROUT)
    ) u_tx (
        .clk, .rst,
        .in_data(data), .in_last(last), .in_valid(valid), .in_ready(ready), .in_usdf(cfg_usdf),
        .hspi_req, .hspi_vld, .hspi_data, .hspi_oe, .hspi_ack,
        .cfg_hold, .cfg_gap, .cfg_ack_timeout,
        .seq, .cnt_packets, .cnt_ack_timeout
    );
endmodule
