// HSPI receiver from the CH569 (CH569 sends, FPGA receives): commands, DAP.
//
// Per the CH569/565 datasheet V1.0, chapter 10; see doc/ch569-hspi.md. The
// receive logic runs on the CH569 HTCLK (rx_clk); packets cross to the sys
// clock through an async FIFO.
//
//   rx_req  <- HTREQ   request, held for the whole packet
//   rx_rdy  -> HTRDY   ready: raised on a request when the FIFO has room for a
//                      packet of MAX_WORDS words, dropped when the request ends
//   rx_vld  <- HTVLD   data valid
//   rx_data <- HD[W-1:0]
//
// Output on the sys side: the packet as 32-bit words, the header word first,
// then the payload, then a closing word with out_last set and data 0. out_good
// on the closing word says the packet is fine: CRC matches, the packet number
// is the expected one, TLL2B is 0 (payload in whole words), it fits MAX_WORDS.
// A consumer keeps the words until out_last and drops the packet without
// out_good. The CRC bytes are held back in a delay line and never come out.
//
// cfg_raw: every byte that came over the bus, CRC included; the closing word
// holds the bytes left over after the last whole word, {count[7:0], bytes[23:0]},
// and out_good is always set. For measuring the CRC parameters on the bench
// (tools/hspi-crc). Change cfg_* only between packets.
//
// SPDX-License-Identifier: BSD-3-Clause

module hspi_rx #(
    parameter int W = 16,
    parameter int CRC_W = (W == 32) ? 32 : 16,
    parameter logic [CRC_W-1:0] CRC_INIT = '0,
    parameter bit CRC_REFLECT = 1'b0,
    parameter logic [CRC_W-1:0] CRC_XOROUT = '0,
    parameter int MAX_WORDS = 128,      // header included
    parameter int FIFO_AW = 9
) (
    input  logic         rx_clk,
    input  logic         rx_rst,
    input  logic         rx_req,
    input  logic         rx_vld,
    input  logic [W-1:0] rx_data,
    output logic         rx_rdy,

    input  logic         cfg_raw,        // rx_clk domain, quasi-static

    input  logic         clk,
    input  logic         rst,
    output logic [31:0]  out_data,
    output logic         out_last,
    output logic         out_good,
    output logic         out_valid,
    input  logic         out_ready,

    output logic [31:0]  cnt_packets,    // rx_clk domain
    output logic [31:0]  cnt_bad
);
    localparam int BYTES = W / 8;
    localparam int BPW = 32 / W;
    localparam int DLY = CRC_W / W;                       // beats of CRC at the end
    localparam logic [CRC_W-1:0] POLY = (CRC_W == 32) ? CRC_W'(32'h04C1_1DB7) : CRC_W'(16'h8005);

    function automatic logic [CRC_W-1:0] crc_beat(input logic [CRC_W-1:0] c, input logic [W-1:0] beat);
        logic [CRC_W-1:0] r;
        logic [7:0] d;
        logic fb;
        r = c;
        for (int i = 0; i < BYTES; i++) begin
            d = beat[8*i +: 8];
            for (int b = 0; b < 8; b++) begin
                fb = r[CRC_W-1] ^ (CRC_REFLECT ? d[b] : d[7-b]);
                r = {r[CRC_W-2:0], 1'b0};
                if (fb) r = r ^ POLY;
            end
        end
        crc_beat = r;
    endfunction

    function automatic logic [CRC_W-1:0] crc_final(input logic [CRC_W-1:0] c);
        logic [CRC_W-1:0] r;
        for (int i = 0; i < CRC_W; i++) r[i] = CRC_REFLECT ? c[CRC_W-1-i] : c[i];
        crc_final = r ^ CRC_XOROUT;
    endfunction

    // ---------------------------------------------------------------- rx_clk
    logic         active;            // request granted
    logic [W-1:0] dly [DLY];         // last DLY beats: the CRC once the packet ends
    logic [$clog2(DLY+1)-1:0] dly_n; // beats in the delay line
    logic [CRC_W-1:0] crc;
    logic [31:0]  acc;
    logic [2:0]   acc_n;             // beats in acc
    logic [15:0]  words;             // words written for this packet
    logic         too_long;
    logic [3:0]   expected_seq;
    logic [5:0]   hdr;               // TLL2B and TSQN of the header

    logic [33:0]  f_wdata;           // {good, last, data}
    logic         f_wen, f_full;
    logic [FIFO_AW:0] f_free;

    // beat leaving the delay line (or the raw beat)
    logic         beat_in, beat_out;
    logic [W-1:0] beat;
    assign beat_in  = active && rx_vld;
    assign beat_out = beat_in && (cfg_raw || dly_n == DLY[$clog2(DLY+1)-1:0]);
    assign beat     = cfg_raw ? rx_data : dly[0];

    logic [CRC_W-1:0] got_crc;
    always_comb begin
        got_crc = '0;
        for (int i = 0; i < DLY; i++) got_crc[W*i +: W] = dly[i];
    end

    logic         ending;            // request dropped: close the packet
    assign ending = active && !rx_req;

    // packet checks at the end of the request
    logic         crc_ok, good;
    always_comb begin
        crc_ok = dly_n == DLY[$clog2(DLY+1)-1:0] && words != 16'd0 && acc_n == 3'd0 &&
                 crc_final(crc) == got_crc;
        good   = cfg_raw ||
                 (crc_ok && !too_long && hdr[5:4] == 2'b00 && hdr[3:0] == expected_seq);
    end

    logic [31:0]  leftover;
    always_comb begin
        leftover = '0;
        if (acc_n != 3'd0) leftover = acc >> (W * (BPW - 32'(acc_n)));
        leftover[31:24] = 8'(acc_n) * 8'(BYTES);
    end

    logic [31:0]  acc_next;
    assign acc_next = (acc >> W) | ({{(32-W){1'b0}}, beat} << (32 - W));

    always_ff @(posedge rx_clk) begin
        if (rx_rst) begin
            active       <= 1'b0;
            rx_rdy       <= 1'b0;
            dly_n        <= '0;
            crc          <= CRC_INIT;
            acc          <= '0;
            acc_n        <= '0;
            words        <= '0;
            too_long     <= 1'b0;
            expected_seq <= '0;
            hdr          <= '0;
            f_wen        <= 1'b0;
            f_wdata      <= '0;
            cnt_packets  <= '0;
            cnt_bad      <= '0;
            for (int i = 0; i < DLY; i++) dly[i] <= '0;
        end else begin
            f_wen <= 1'b0;

            if (!active) begin
                // a request: grant it only with room for a whole packet
                if (rx_req && f_free >= (FIFO_AW+1)'(MAX_WORDS + 1)) begin
                    active   <= 1'b1;
                    rx_rdy   <= 1'b1;
                    dly_n    <= '0;
                    crc      <= CRC_INIT;
                    acc_n    <= '0;
                    words    <= '0;
                    too_long <= 1'b0;
                end
            end else if (ending) begin
                active <= 1'b0;
                rx_rdy <= 1'b0;
                // closing word: status only, or the leftover bytes in raw mode
                f_wen   <= 1'b1;
                f_wdata <= {good, 1'b1, cfg_raw ? leftover : 32'd0};
                cnt_packets <= cnt_packets + 32'd1;
                if (!good) cnt_bad <= cnt_bad + 32'd1;
                // with a sound CRC the sender's number is trusted: a skipped number
                // marks one packet bad, not all that follow; without it the sender
                // has still counted the packet
                if (!cfg_raw) expected_seq <= crc_ok ? hdr[3:0] + 4'd1 : expected_seq + 4'd1;
            end else begin
                if (beat_in && !cfg_raw) begin
                    for (int i = 0; i < DLY - 1; i++) dly[i] <= dly[i+1];
                    dly[DLY-1] <= rx_data;
                    if (dly_n != DLY[$clog2(DLY+1)-1:0]) dly_n <= dly_n + 1'b1;
                end
                if (beat_out) begin
                    if (!cfg_raw) crc <= crc_beat(crc, beat);
                    acc <= acc_next;
                    if (acc_n == 3'(BPW - 1)) begin
                        acc_n <= '0;
                        if (words == 16'd0) hdr <= acc_next[31:26];
                        if (words < 16'(MAX_WORDS)) begin
                            f_wen   <= 1'b1;
                            f_wdata <= {1'b0, 1'b0, acc_next};
                            words   <= words + 16'd1;
                        end else begin
                            too_long <= 1'b1;
                        end
                    end else begin
                        acc_n <= acc_n + 3'd1;
                    end
                end
            end
        end
    end

    // ---------------------------------------------------------------- crossing
    logic [33:0] r_data;

    async_fifo #(.DW(34), .AW(FIFO_AW)) u_fifo (
        .wclk(rx_clk), .wrst(rx_rst), .wdata(f_wdata), .wen(f_wen), .wfull(f_full), .wfree(f_free),
        .rclk(clk), .rrst(rst), .rdata(r_data), .rvalid(out_valid), .rready(out_ready)
    );

    assign out_data = r_data[31:0];
    assign out_last = r_data[32];
    assign out_good = r_data[33];

    // f_full cannot happen: a packet is granted only with room for MAX_WORDS + 1
    logic unused;
    assign unused = f_full;
endmodule
