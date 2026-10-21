// Test top: tpiu_tx on TRACECLK straight into trace_rx (sample order: first = rising).
//
// SPDX-License-Identifier: BSD-3-Clause

module tpiu_loop_top (
    input  logic         trc_clk,
    input  logic         trc_rst,
    input  logic         clk,
    input  logic         rst,
    input  logic         cfg_enable,
    input  logic [1:0]   cfg_width,
    input  logic [7:0]   cfg_sync_every,
    input  logic         cfg_hsync,
    output logic [127:0] out_frame,
    output logic [63:0]  out_num,
    output logic         out_valid,
    input  logic         out_ready,
    output logic [31:0]  frames_sent,
    output logic [15:0]  cnt_overflow,
    output logic [31:0]  cnt_lock,
    output logic [31:0]  cnt_hsync
);
    logic [3:0] first, second;
    logic       frame_strobe, locked;
    logic [4:0] shift;
    logic [1:0] state;
    logic [31:0] cnt_resync, cnt_misaligned, cnt_idle;

    tpiu_tx u_tx (
        .clk(trc_clk), .rst(trc_rst), .cfg_enable, .cfg_width, .cfg_sync_every, .cfg_hsync,
        .out_first(first), .out_second(second), .frames(frames_sent)
    );

    trace_rx u_rx (
        .trc_clk, .trc_rst, .trc_d_rise(first), .trc_d_fall(second),
        .clk, .rst,
        .cfg_enable, .cfg_width, .cfg_fall_first(1'b0),
        .cfg_verify_timeout(16'd0), .cfg_lock_timeout(24'd0), .cfg_misalign_max(4'd2), .cfg_drop_idle(1'b0),
        .out_frame, .out_num, .out_valid, .out_ready, .frame_strobe,
        .locked, .shift, .state, .cnt_overflow, .cnt_lock, .cnt_resync, .cnt_misaligned, .cnt_hsync, .cnt_idle
    );

    logic unused;
    assign unused = ^{frame_strobe, locked, shift, state, cnt_resync, cnt_misaligned, cnt_idle};
endmodule
