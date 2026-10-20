// Self-test stream generator: blocks in the fw/ch569/usbstream/stream.h format,
// checked on the PC by sw/usbstream (check.c).
//
//   word 0  STREAM_MAGIC
//   word 1  block number from 0
//   word 2  block length in bytes
//   word 3  payload kind: 0 = stream_word(k), 1 = PRBS31 from the seed
//   word k  payload, k = 4 .. len/4 - 1
//
// stream_word(k) = k * 0x9E3779B1 + 0x7F4A7C15 is a running sum here. PRBS31 is
// x^31 + x^28 + 1, 32 steps per word, first bit in bit 0, restarted from
// 0x7FFFFFFF in every block. The config is taken at the start of each block.
//
// SPDX-License-Identifier: BSD-3-Clause

module selftest_gen (
    input  logic        clk,
    input  logic        rst,

    input  logic        cfg_enable,
    input  logic        cfg_kind,          // 0 = stream_word, 1 = PRBS31
    input  logic [13:0] cfg_block_words,   // 128 .. 16383 (512 B .. 64 KiB - 4)

    output logic [31:0] out_data,
    output logic        out_last,
    output logic        out_valid,
    input  logic        out_ready,

    output logic [31:0] cnt_blocks
);
    localparam logic [31:0] MAGIC = 32'h534E_4C52;   // "RLNS"
    localparam logic [31:0] STEP  = 32'h9E37_79B1;
    localparam logic [31:0] WORD4 = 32'h7F4A_7C15 + 32'd4 * STEP;
    localparam logic [30:0] SEED  = 31'h7FFF_FFFF;

    logic        active;
    logic        kind;
    logic [13:0] words;
    logic [13:0] k;
    logic [31:0] seq;
    logic [31:0] weyl;
    logic [30:0] prbs;

    logic [31:0] prbs_word;
    logic [30:0] prbs_next;

    always_comb begin
        logic [30:0] s;
        logic        b;
        s = prbs;
        prbs_word = '0;
        for (int i = 0; i < 32; i++) begin
            b = s[30] ^ s[27];
            s = {s[29:0], b};
            prbs_word[i] = b;
        end
        prbs_next = s;
    end

    always_comb begin
        case (k)
            14'd0:   out_data = MAGIC;
            14'd1:   out_data = seq;
            14'd2:   out_data = {16'd0, words, 2'b00};
            14'd3:   out_data = {31'd0, kind};
            default: out_data = kind ? prbs_word : weyl;
        endcase
    end

    logic [13:0] start_words;
    assign start_words = (cfg_block_words < 14'd128) ? 14'd128 : cfg_block_words;

    assign out_valid = active;
    assign out_last  = (k == words - 14'd1);

    always_ff @(posedge clk) begin
        if (rst) begin
            active     <= 1'b0;
            kind       <= 1'b0;
            words      <= 14'd128;
            k          <= '0;
            seq        <= '0;
            weyl       <= WORD4;
            prbs       <= SEED;
            cnt_blocks <= '0;
        end else begin
            if (!active || (out_ready && out_last)) begin
                // block boundary: take the config for the next block
                active <= cfg_enable;
                kind   <= cfg_kind;
                words  <= start_words;
                k      <= '0;
                weyl   <= WORD4;
                prbs   <= SEED;
                if (active) begin
                    seq        <= seq + 32'd1;
                    cnt_blocks <= cnt_blocks + 32'd1;
                end
            end else if (out_ready) begin
                k <= k + 14'd1;
                if (k >= 14'd4) begin
                    weyl <= weyl + STEP;
                    prbs <= prbs_next;
                end
            end
        end
    end
endmodule
