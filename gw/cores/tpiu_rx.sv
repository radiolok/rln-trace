// TPIU receive chain in the sys domain: bit alignment, deformatter, idle filter.
// Input: raw trace words from the TRC_CLK domain FIFO, bit 0 earliest.
//
// SPDX-License-Identifier: BSD-3-Clause

module tpiu_rx (
    input  logic         clk,
    input  logic         rst,

    input  logic [31:0]  in_data,
    input  logic         in_valid,
    output logic         in_ready,

    output logic [127:0] out_frame,
    output logic [63:0]  out_num,
    output logic         out_valid,
    input  logic         out_ready,
    output logic         frame_strobe,

    input  logic [15:0]  cfg_verify_timeout,
    input  logic [23:0]  cfg_lock_timeout,
    input  logic [3:0]   cfg_misalign_max,
    input  logic         cfg_drop_idle,

    output logic         locked,
    output logic [4:0]   shift,
    output logic [1:0]   state,
    output logic [31:0]  cnt_lock,
    output logic [31:0]  cnt_resync,
    output logic [31:0]  cnt_misaligned,
    output logic [31:0]  cnt_hsync,
    output logic [31:0]  cnt_idle
);
    logic [15:0]  hw_data;
    logic         hw_first, hw_valid, hw_ready, hunt;
    logic [127:0] fr_frame;
    logic [63:0]  fr_num;
    logic         fr_valid, fr_ready;

    tpiu_align u_align (
        .clk, .rst, .hunt,
        .in_data, .in_valid, .in_ready,
        .out_data(hw_data), .out_first(hw_first), .out_valid(hw_valid), .out_ready(hw_ready),
        .locked, .shift
    );

    tpiu_deframer u_deframer (
        .clk, .rst,
        .in_data(hw_data), .in_first(hw_first), .in_valid(hw_valid), .in_ready(hw_ready),
        .hunt,
        .out_frame(fr_frame), .out_num(fr_num), .out_valid(fr_valid), .out_ready(fr_ready),
        .frame_strobe,
        .cfg_verify_timeout, .cfg_lock_timeout, .cfg_misalign_max,
        .state, .cnt_lock, .cnt_resync, .cnt_misaligned, .cnt_hsync
    );

    tpiu_idle u_idle (
        .clk, .rst, .cfg_drop(cfg_drop_idle),
        .in_frame(fr_frame), .in_num(fr_num), .in_valid(fr_valid), .in_ready(fr_ready),
        .out_frame, .out_num, .out_valid, .out_ready,
        .cnt_idle
    );
endmodule
