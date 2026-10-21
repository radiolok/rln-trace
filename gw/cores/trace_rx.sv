// Trace receive path across both clock domains:
//   TRC_CLK: trace_capture -> async_fifo   |   sys: async_fifo -> tpiu_rx
//
// There is no backpressure to the target: when the FIFO is full the word is
// dropped and counted; the deformatter loses the frame alignment and hunts
// again. The drop count crosses to sys as a Gray-coded counter.
//
// cfg_* of the capture are quasi-static: they cross into TRC_CLK through
// two-flop synchronisers; change them only with cfg_enable low.
// trc_rst and sys_rst must overlap.
//
// SPDX-License-Identifier: BSD-3-Clause

module trace_rx #(
    parameter int FIFO_AW = 5
) (
    input  logic         trc_clk,
    input  logic         trc_rst,
    input  logic [3:0]   trc_d_rise,
    input  logic [3:0]   trc_d_fall,

    input  logic         clk,
    input  logic         rst,

    input  logic         cfg_enable,
    input  logic [1:0]   cfg_width,
    input  logic         cfg_fall_first,
    input  logic [15:0]  cfg_verify_timeout,
    input  logic [23:0]  cfg_lock_timeout,
    input  logic [3:0]   cfg_misalign_max,
    input  logic         cfg_drop_idle,

    output logic [127:0] out_frame,
    output logic [63:0]  out_num,
    output logic         out_valid,
    input  logic         out_ready,
    output logic         frame_strobe,

    output logic         locked,
    output logic [4:0]   shift,
    output logic [1:0]   state,
    output logic [15:0]  cnt_overflow,      // words dropped at the FIFO, wraps
    output logic [31:0]  cnt_lock,
    output logic [31:0]  cnt_resync,
    output logic [31:0]  cnt_misaligned,
    output logic [31:0]  cnt_hsync,
    output logic [31:0]  cnt_idle
);
    // ---------------------------------------------------------------- TRC_CLK
    logic [3:0] cfg_t1, cfg_t2;
    always_ff @(posedge trc_clk) begin
        cfg_t1 <= {cfg_enable, cfg_width, cfg_fall_first};
        cfg_t2 <= cfg_t1;
    end

    logic [31:0] word;
    logic        word_valid, full;

    trace_capture u_capture (
        .clk(trc_clk), .rst(trc_rst),
        .d_rise(trc_d_rise), .d_fall(trc_d_fall),
        .cfg_enable(cfg_t2[3]), .cfg_width(cfg_t2[2:1]), .cfg_fall_first(cfg_t2[0]),
        .word, .word_valid
    );

    logic [15:0] ovf_bin, ovf_gray;
    always_ff @(posedge trc_clk) begin
        if (trc_rst) begin
            ovf_bin  <= '0;
            ovf_gray <= '0;
        end else if (word_valid && full) begin
            ovf_bin  <= ovf_bin + 16'd1;
            ovf_gray <= (ovf_bin + 16'd1) ^ ((ovf_bin + 16'd1) >> 1);
        end
    end

    // ---------------------------------------------------------------- crossing
    logic [31:0] f_data;
    logic        f_valid, f_ready;

    async_fifo #(.DW(32), .AW(FIFO_AW)) u_fifo (
        .wclk(trc_clk), .wrst(trc_rst), .wdata(word), .wen(word_valid), .wfull(full),
        .rclk(clk), .rrst(rst), .rdata(f_data), .rvalid(f_valid), .rready(f_ready)
    );

    // ---------------------------------------------------------------- sys
    logic [15:0] ovf_s1, ovf_s2;
    always_ff @(posedge clk) begin
        if (rst) begin
            ovf_s1       <= '0;
            ovf_s2       <= '0;
            cnt_overflow <= '0;
        end else begin
            ovf_s1 <= ovf_gray;
            ovf_s2 <= ovf_s1;
            for (int i = 0; i < 16; i++) cnt_overflow[i] <= ^(ovf_s2 >> i);
        end
    end

    tpiu_rx u_tpiu (
        .clk, .rst,
        .in_data(f_data), .in_valid(f_valid), .in_ready(f_ready),
        .out_frame, .out_num, .out_valid, .out_ready, .frame_strobe,
        .cfg_verify_timeout, .cfg_lock_timeout, .cfg_misalign_max, .cfg_drop_idle,
        .locked, .shift, .state,
        .cnt_lock, .cnt_resync, .cnt_misaligned, .cnt_hsync, .cnt_idle
    );
endmodule
