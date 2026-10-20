// TPIU deformatter: 16-byte frames from the aligned halfword stream.
//
// Everything in the formatter output is a multiple of a halfword: a frame is
// 8 halfwords, the full sync 0xFFFF 0x7FFF, the halfword sync 0x7FFF. A frame
// never holds 0xFF at an even byte (that would be an ID change to the reserved
// ID 0x7F), so 0xFFFF is held back for one halfword: followed by 0x7FFF it is a
// full sync, otherwise it is data. A lone 0x7FFF is a halfword sync and dropped.
//
//   HUNT    wait for the aligner to lock on a full sync (in_first)
//   VERIFY  frames are counted but not sent; the next full sync must come on a
//           frame boundary, otherwise back to HUNT
//   LOCK    frames go out with a 64-bit number; a sync off the boundary drops
//           the partial frame and restarts the frame there; cfg_misalign_max
//           such syncs in a row, or cfg_lock_timeout halfwords without a sync
//           on the boundary, send it back to HUNT
//
// Out frame byte 0 is out_frame[7:0]. Frame numbers count every frame
// completed in LOCK, so they keep counting through idle frames dropped later.
//
// SPDX-License-Identifier: BSD-3-Clause

module tpiu_deframer (
    input  logic         clk,
    input  logic         rst,

    input  logic [15:0]  in_data,
    input  logic         in_first,
    input  logic         in_valid,
    output logic         in_ready,

    output logic         hunt,           // to the aligner

    output logic [127:0] out_frame,
    output logic [63:0]  out_num,
    output logic         out_valid,
    input  logic         out_ready,
    output logic         frame_strobe,   // a frame completed in LOCK

    input  logic [15:0]  cfg_verify_timeout,  // halfwords, 0 = wait forever
    input  logic [23:0]  cfg_lock_timeout,    // halfwords, 0 = off
    input  logic [3:0]   cfg_misalign_max,    // 0 behaves as 1

    output logic [1:0]   state,
    output logic [31:0]  cnt_lock,       // VERIFY -> LOCK
    output logic [31:0]  cnt_resync,     // LOCK -> HUNT
    output logic [31:0]  cnt_misaligned, // syncs off the frame boundary in LOCK
    output logic [31:0]  cnt_hsync       // halfword syncs dropped
);
    localparam logic [1:0] HUNT = 2'd0, VERIFY = 2'd1, LOCK = 2'd2;
    localparam logic [15:0] HW_FF = 16'hFFFF, HW_SYNC = 16'h7FFF;

    logic [15:0] buf_hw [7];         // halfwords 0..6 of the frame being built
    logic [2:0]  pos;
    logic        pend;               // 0xFFFF held back
    logic [23:0] timer;              // halfwords since the last sync on the boundary
    logic [3:0]  misrun;
    logic [63:0] frame_no;

    // HUNT with in_first starts VERIFY on this very halfword
    logic        start;
    logic [1:0]  st;
    logic        st_pend;
    logic [2:0]  st_pos;
    logic [23:0] st_timer;

    assign start    = (state == HUNT) && in_first;
    assign st       = start ? VERIFY : state;
    assign st_pend  = start ? 1'b0 : pend;
    assign st_pos   = start ? 3'd0 : pos;
    assign st_timer = start ? 24'd0 : timer;

    logic blocked;
    assign blocked = out_valid && !out_ready;

    // what this halfword does
    logic act, sync_ev, commit, commit_ff, set_pend, hsync;
    logic [15:0] commit_hw;

    always_comb begin
        act       = in_valid && !blocked && (st != HUNT);
        sync_ev   = 1'b0;
        commit    = 1'b0;
        commit_ff = 1'b0;
        set_pend  = 1'b0;
        hsync     = 1'b0;
        if (act) begin
            if (st_pend) begin
                if (in_data == HW_SYNC) sync_ev   = 1'b1;
                else                    commit_ff = 1'b1;   // in_data waits a cycle
            end else if (in_data == HW_FF) begin
                set_pend = 1'b1;
            end else if (in_data == HW_SYNC) begin
                hsync = 1'b1;
            end else begin
                commit = 1'b1;
            end
        end
        commit_hw = commit_ff ? HW_FF : in_data;
    end

    // a halfword is consumed unless the held 0xFFFF goes out in front of it
    assign in_ready = (st == HUNT && !in_first) || (!blocked && !commit_ff);

    logic       any_commit, frame_done, aligned_sync, timeout;
    logic [3:0] mis_limit;
    assign any_commit   = commit || commit_ff;
    assign frame_done   = any_commit && (st_pos == 3'd7);
    assign aligned_sync = sync_ev && (st_pos == 3'd0);
    assign mis_limit    = (cfg_misalign_max == 4'd0) ? 4'd1 : cfg_misalign_max;
    assign timeout      = act && !aligned_sync &&
                          ((st == VERIFY && cfg_verify_timeout != 16'd0 &&
                            st_timer >= {8'd0, cfg_verify_timeout}) ||
                           (st == LOCK && cfg_lock_timeout != 24'd0 &&
                            st_timer >= cfg_lock_timeout));

    logic go_hunt;
    always_comb begin
        go_hunt = timeout;
        if (sync_ev && !aligned_sync) begin
            if (st == VERIFY) go_hunt = 1'b1;
            if (st == LOCK && misrun + 4'd1 >= mis_limit) go_hunt = 1'b1;
        end
    end

    assign frame_strobe = frame_done && (st == LOCK) && !go_hunt;

    always_ff @(posedge clk) begin
        if (rst) begin
            state          <= HUNT;
            pos            <= '0;
            pend           <= 1'b0;
            timer          <= '0;
            misrun         <= '0;
            frame_no       <= '0;
            out_frame      <= '0;
            out_num        <= '0;
            out_valid      <= 1'b0;
            hunt           <= 1'b0;
            cnt_lock       <= '0;
            cnt_resync     <= '0;
            cnt_misaligned <= '0;
            cnt_hsync      <= '0;
            for (int i = 0; i < 7; i++) buf_hw[i] <= '0;
        end else begin
            hunt <= 1'b0;
            if (out_valid && out_ready) out_valid <= 1'b0;

            if (start) begin
                state <= VERIFY;
                pos   <= '0;
                pend  <= 1'b0;
                timer <= '0;
            end

            if (act) begin
                timer <= (st_timer == 24'hFF_FFFF) ? st_timer : st_timer + 24'd1;

                if (set_pend)  pend <= 1'b1;
                if (sync_ev || commit_ff) pend <= 1'b0;
                if (hsync)     cnt_hsync <= cnt_hsync + 32'd1;

                if (any_commit) begin
                    if (st_pos != 3'd7) buf_hw[st_pos] <= commit_hw;
                    pos <= st_pos + 3'd1;
                end

                if (frame_strobe) begin
                    out_frame <= {commit_hw, buf_hw[6], buf_hw[5], buf_hw[4],
                                  buf_hw[3], buf_hw[2], buf_hw[1], buf_hw[0]};
                    out_num   <= frame_no;
                    out_valid <= 1'b1;
                    frame_no  <= frame_no + 64'd1;
                end

                if (sync_ev) begin
                    pos <= '0;
                    if (aligned_sync) begin
                        timer  <= '0;
                        misrun <= '0;
                        if (st == VERIFY) begin
                            state    <= LOCK;
                            cnt_lock <= cnt_lock + 32'd1;
                        end
                    end else if (st == LOCK) begin
                        cnt_misaligned <= cnt_misaligned + 32'd1;
                        misrun         <= misrun + 4'd1;
                    end
                end

                if (go_hunt) begin
                    state  <= HUNT;
                    pos    <= '0;
                    pend   <= 1'b0;
                    misrun <= '0;
                    hunt   <= 1'b1;
                    if (st == LOCK) cnt_resync <= cnt_resync + 32'd1;
                end
            end
        end
    end
endmodule
