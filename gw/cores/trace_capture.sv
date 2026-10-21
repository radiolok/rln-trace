// Trace port capture in the TRC_CLK domain: DDR samples -> 32-bit words.
//
// Each TRC_CLK cycle brings two samples of TRACEDATA from the input DDR
// register: one taken on the rising edge, one on the falling edge. Which of the
// two is earlier in the cycle depends on how the platform IDDR pairs them, hence
// cfg_fall_first. Port width 1, 2 or 4 bits uses TRACEDATA[0], [1:0] or [3:0];
// TRACEDATA[0] is the earliest bit of a sample. The bits form an LSB-first stream
// cut into 32-bit words (bit 0 earliest), the input of tpiu_align. 32 is a
// multiple of 2, 4 and 8 bits per cycle, so a word is always 16, 8 or 4 cycles.
//
// Change the config only while cfg_enable is low.
//
// SPDX-License-Identifier: BSD-3-Clause

module trace_capture (
    input  logic        clk,
    input  logic        rst,

    input  logic [3:0]  d_rise,
    input  logic [3:0]  d_fall,

    input  logic        cfg_enable,
    input  logic [1:0]  cfg_width,       // 0: 1 bit, 1: 2 bits, 2: 4 bits
    input  logic        cfg_fall_first,

    output logic [31:0] word,
    output logic        word_valid
);
    logic [3:0]  first, second;
    /* verilator lint_off UNUSEDSIGNAL */
    logic [31:0] acc;               // the lowest bits are shifted out before use
    /* verilator lint_on UNUSEDSIGNAL */
    logic [31:0] acc_n;
    logic [3:0]  cnt, last_cnt;

    assign first  = cfg_fall_first ? d_fall : d_rise;
    assign second = cfg_fall_first ? d_rise : d_fall;

    always_comb begin
        case (cfg_width)
            2'd0:    begin acc_n = {second[0],   first[0],   acc[31:2]}; last_cnt = 4'd15; end
            2'd1:    begin acc_n = {second[1:0], first[1:0], acc[31:4]}; last_cnt = 4'd7;  end
            default: begin acc_n = {second,      first,      acc[31:8]}; last_cnt = 4'd3;  end
        endcase
    end

    always_ff @(posedge clk) begin
        if (rst || !cfg_enable) begin
            acc        <= '0;
            cnt        <= '0;
            word       <= '0;
            word_valid <= 1'b0;
        end else begin
            acc        <= acc_n;
            word_valid <= (cnt == last_cnt);
            if (cnt == last_cnt) begin
                word <= acc_n;
                cnt  <= '0;
            end else begin
                cnt <= cnt + 4'd1;
            end
        end
    end
endmodule
