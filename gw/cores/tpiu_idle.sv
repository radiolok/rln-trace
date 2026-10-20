// Idle frame filter after the deformatter.
//
// Tracks the trace source ID through the frames the same way a host decoder
// does: bytes 0, 2, .. 14 with bit 0 set are ID changes, byte 15 holds the aux
// bits. An ID change with its aux bit set takes effect after the next data
// byte, possibly in the next frame. A frame is idle when all its data bytes
// belong to ID 0 and the ID state after it equals the state before it; only
// such frames can be dropped without changing what the host decodes.
//
// SPDX-License-Identifier: BSD-3-Clause

module tpiu_idle (
    input  logic         clk,
    input  logic         rst,

    input  logic         cfg_drop,

    input  logic [127:0] in_frame,
    input  logic [63:0]  in_num,
    input  logic         in_valid,
    output logic         in_ready,

    output logic [127:0] out_frame,
    output logic [63:0]  out_num,
    output logic         out_valid,
    input  logic         out_ready,

    output logic [31:0]  cnt_idle
);
    logic [6:0] cur_id, pend_id;
    logic       pend_v;

    logic [6:0] n_cur, n_pend;
    logic       n_pend_v, busy;

    always_comb begin
        logic [7:0] b;
        n_cur    = cur_id;
        n_pend   = pend_id;
        n_pend_v = pend_v;
        busy     = 1'b0;
        for (int i = 0; i < 15; i++) begin
            b = in_frame[8*i +: 8];
            if ((i % 2 == 0) && b[0]) begin
                if (in_frame[120 + i / 2]) begin
                    n_pend   = b[7:1];
                    n_pend_v = 1'b1;
                end else begin
                    n_cur = b[7:1];
                end
            end else begin
                if (n_cur != 7'd0) busy = 1'b1;
                if (n_pend_v) begin
                    n_cur    = n_pend;
                    n_pend_v = 1'b0;
                end
            end
        end
    end

    logic idle, in_fire;
    assign idle = !busy && (n_cur == cur_id) && (n_pend_v == pend_v) &&
                  (!pend_v || n_pend == pend_id);
    assign in_ready = !out_valid || out_ready;
    assign in_fire  = in_valid && in_ready;

    always_ff @(posedge clk) begin
        if (rst) begin
            cur_id    <= '0;
            pend_id   <= '0;
            pend_v    <= 1'b0;
            out_frame <= '0;
            out_num   <= '0;
            out_valid <= 1'b0;
            cnt_idle  <= '0;
        end else begin
            if (out_valid && out_ready) out_valid <= 1'b0;
            if (in_fire) begin
                cur_id  <= n_cur;
                pend_id <= n_pend;
                pend_v  <= n_pend_v;
                if (cfg_drop && idle) begin
                    cnt_idle <= cnt_idle + 32'd1;
                end else begin
                    out_frame <= in_frame;
                    out_num   <= in_num;
                    out_valid <= 1'b1;
                end
            end
        end
    end
endmodule
