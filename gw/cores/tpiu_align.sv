// Bit alignment of the raw trace stream on the TPIU full sync 0x7FFFFFFF.
//
// The input is the trace port stream packed into 32-bit words, bit 0 earliest,
// at an unknown bit offset. While hunting, every new word forms a 64-bit window
// with the previous one and all 32 offsets are compared with the full sync at
// once, so ports of 1, 2 and 4 bits are all covered. A sync ends with its only
// zero bit, so at most one offset can match. After a match the stream is cut at
// that offset into halfwords, little-endian byte order, starting with the
// halfword right after the sync; that one is flagged out_first.
//
// SPDX-License-Identifier: BSD-3-Clause

module tpiu_align (
    input  logic        clk,
    input  logic        rst,

    input  logic        hunt,        // drop the alignment and search again

    input  logic [31:0] in_data,
    input  logic        in_valid,
    output logic        in_ready,

    output logic [15:0] out_data,
    output logic        out_first,
    output logic        out_valid,
    input  logic        out_ready,

    output logic        locked,
    output logic [4:0]  shift
);
    localparam logic [31:0] SYNC = 32'h7FFF_FFFF;

    logic [31:0] prev;
    logic        have_prev;
    logic [31:0] hold;               // aligned word being sent as two halfwords
    logic        hold_valid;
    logic        hold_high;          // low halfword already sent
    logic        first;

    logic [63:0] window;
    logic        found;
    logic [4:0]  found_shift;

    assign window = {in_data, prev};

    always_comb begin
        found = 1'b0;
        found_shift = '0;
        for (int s = 31; s >= 0; s--) begin
            if (window[s +: 32] == SYNC) begin
                found = 1'b1;
                found_shift = 5'(s);
            end
        end
    end

    logic out_fire, in_fire, hold_done;
    assign out_fire  = out_valid && out_ready;
    assign hold_done = !hold_valid || (hold_high && out_fire);
    assign in_ready  = !locked || hold_done;
    assign in_fire   = in_valid && in_ready;

    assign out_valid = hold_valid;
    assign out_data  = hold_high ? hold[31:16] : hold[15:0];
    assign out_first = first && !hold_high;

    always_ff @(posedge clk) begin
        if (rst) begin
            prev       <= '0;
            have_prev  <= 1'b0;
            hold       <= '0;
            hold_valid <= 1'b0;
            hold_high  <= 1'b0;
            first      <= 1'b0;
            locked     <= 1'b0;
            shift      <= '0;
        end else if (hunt) begin
            hold_valid <= 1'b0;
            hold_high  <= 1'b0;
            first      <= 1'b0;
            locked     <= 1'b0;
        end else begin
            if (out_fire) begin
                if (!hold_high) begin
                    hold_high <= 1'b1;
                end else begin
                    hold_valid <= 1'b0;
                    hold_high  <= 1'b0;
                end
                first <= 1'b0;
            end
            if (in_fire) begin
                prev      <= in_data;
                have_prev <= 1'b1;
                if (!locked) begin
                    if (have_prev && found) begin
                        // the data after the sync starts at this offset in the next window
                        locked <= 1'b1;
                        shift  <= found_shift;
                        first  <= 1'b1;
                    end
                end else begin
                    hold       <= window[{1'b0, shift} +: 32];
                    hold_valid <= 1'b1;
                    hold_high  <= 1'b0;
                end
            end
        end
    end
endmodule
