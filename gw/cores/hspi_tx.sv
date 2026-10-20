// HSPI transmitter towards the CH569 (FPGA sends, CH569 receives).
//
// Per the CH569/565 datasheet V1.0, chapter 10. Signal names are the CH569 ones
// on the receive side; the FPGA clocks the CH569 HRCLK with its own clock.
//
//   hspi_req  -> HRACT   request, held for the whole packet
//   hspi_ack  <- HTACK   receiver ready (a free DMA buffer); async, synchronised
//   hspi_vld  -> HRVLD   data on the bus is valid; may drop inside a packet
//   hspi_data -> HD[W-1:0], driven while hspi_oe
//
// Packet: 32-bit header, payload, CRC; every part goes out low bits first.
//   header  [31:30] TLL2B = 0 (payload is whole 32-bit words), [29:26] TSQN
//           packet number mod 16, [25:0] USDF user field (in_usdf)
//   CRC     over header and payload bytes in bus order: CRC16 0x8005 for W = 8
//           and 16, CRC32 0x04C11DB7 for W = 32. Init, reflection and output XOR
//           are not in the datasheet: parameters here, to be measured on the
//           bench (step 0)
//
// Sequence: raise req; wait for ack; header, payload words from in_*, CRC; drop
// req; wait for ack to fall (or cfg_ack_timeout cycles); cfg_gap idle cycles.
// The payload source must not end a packet past 4096 bytes.
//
// SPDX-License-Identifier: BSD-3-Clause

module hspi_tx #(
    parameter int W = 16,
    parameter int CRC_W = (W == 32) ? 32 : 16,
    parameter logic [CRC_W-1:0] CRC_INIT = '0,
    parameter bit CRC_REFLECT = 1'b0,
    parameter logic [CRC_W-1:0] CRC_XOROUT = '0
) (
    input  logic         clk,
    input  logic         rst,

    input  logic [31:0]  in_data,
    input  logic         in_last,
    input  logic         in_valid,
    output logic         in_ready,
    input  logic [25:0]  in_usdf,        // taken when the packet starts

    output logic         hspi_req,
    output logic         hspi_vld,
    output logic [W-1:0] hspi_data,
    output logic         hspi_oe,
    input  logic         hspi_ack,

    input  logic [7:0]   cfg_gap,
    input  logic [7:0]   cfg_ack_timeout,   // 0 = wait for ack low forever

    output logic [3:0]   seq,
    output logic [31:0]  cnt_packets,
    output logic [31:0]  cnt_ack_timeout
);
    localparam int BPW = 32 / W;                         // beats per 32-bit word
    localparam int CRC_BEATS = (CRC_W + W - 1) / W;
    localparam logic [CRC_W-1:0] POLY = (CRC_W == 32) ? CRC_W'(32'h04C1_1DB7) : CRC_W'(16'h8005);

    function automatic logic [CRC_W-1:0] crc_beat(input logic [CRC_W-1:0] c, input logic [W-1:0] beat);
        logic [CRC_W-1:0] r;
        logic [7:0] d;
        logic fb;
        r = c;
        for (int i = 0; i < W / 8; i++) begin
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

    // ack from the CH569 clock domain
    logic [1:0] ack_sync;
    logic       ack;
    always_ff @(posedge clk) ack_sync <= {ack_sync[0], hspi_ack};
    assign ack = ack_sync[1];

    typedef enum logic [2:0] {S_IDLE, S_WAIT_ACK, S_SEND, S_END, S_WAIT_LOW, S_GAP} state_t;
    typedef enum logic [1:0] {P_HDR, P_DATA, P_CRC} phase_t;

    state_t      state;
    phase_t      phase;
    logic [31:0] sh;                 // word being sent, low beat first
    logic [2:0]  left;               // beats left in sh
    logic        sh_last;
    logic [CRC_W-1:0] crc;
    logic [25:0] usdf;
    logic [7:0]  cnt;

    // next beat: from sh, or straight from the input when sh is empty
    logic        from_in, emit, take;
    logic [31:0] cur_sh;
    logic [2:0]  cur_left;
    logic        cur_last;
    logic [CRC_W-1:0] crc_n;

    always_comb begin
        from_in  = (state == S_SEND) && (phase == P_DATA) && (left == 3'd0);
        take     = from_in && in_valid;
        cur_sh   = from_in ? in_data : sh;
        cur_left = from_in ? 3'(BPW) : left;
        cur_last = from_in ? in_last : sh_last;
        emit     = (state == S_SEND) && (from_in ? in_valid : (left != 3'd0));
        crc_n    = crc_beat(crc, cur_sh[W-1:0]);
    end

    assign in_ready = take;

    always_ff @(posedge clk) begin
        if (rst) begin
            state           <= S_IDLE;
            phase           <= P_HDR;
            sh              <= '0;
            left            <= '0;
            sh_last         <= 1'b0;
            crc             <= CRC_INIT;
            usdf            <= '0;
            cnt             <= '0;
            seq             <= '0;
            hspi_req        <= 1'b0;
            hspi_vld        <= 1'b0;
            hspi_data       <= '0;
            hspi_oe         <= 1'b0;
            cnt_packets     <= '0;
            cnt_ack_timeout <= '0;
        end else begin
            case (state)
                S_IDLE: begin
                    if (in_valid) begin
                        hspi_req <= 1'b1;
                        usdf     <= in_usdf;
                        state    <= S_WAIT_ACK;
                    end
                end

                S_WAIT_ACK: begin
                    if (ack) begin
                        sh      <= {2'b00, seq, usdf};
                        left    <= 3'(BPW);
                        sh_last <= 1'b0;
                        phase   <= P_HDR;
                        crc     <= CRC_INIT;
                        hspi_oe <= 1'b1;
                        state   <= S_SEND;
                    end
                end

                S_SEND: begin
                    hspi_vld <= emit;
                    if (emit) begin
                        hspi_data <= cur_sh[W-1:0];
                        sh        <= cur_sh >> W;
                        left      <= cur_left - 3'd1;
                        sh_last   <= cur_last;
                        if (phase != P_CRC) crc <= crc_n;
                        if (cur_left == 3'd1) begin
                            case (phase)
                                P_HDR: phase <= P_DATA;
                                P_DATA: if (cur_last) begin
                                    phase <= P_CRC;
                                    sh    <= 32'(crc_final(crc_n));
                                    left  <= 3'(CRC_BEATS);
                                end
                                default: state <= S_END;
                            endcase
                        end
                    end
                end

                S_END: begin
                    hspi_req    <= 1'b0;
                    hspi_vld    <= 1'b0;
                    hspi_oe     <= 1'b0;
                    seq         <= seq + 4'd1;
                    cnt_packets <= cnt_packets + 32'd1;
                    cnt         <= '0;
                    state       <= S_WAIT_LOW;
                end

                S_WAIT_LOW: begin
                    cnt <= cnt + 8'd1;
                    if (!ack) begin
                        cnt   <= '0;
                        state <= S_GAP;
                    end else if (cfg_ack_timeout != 8'd0 && cnt == cfg_ack_timeout) begin
                        cnt             <= '0;
                        cnt_ack_timeout <= cnt_ack_timeout + 32'd1;
                        state           <= S_GAP;
                    end
                end

                S_GAP: begin
                    cnt <= cnt + 8'd1;
                    if (cnt >= cfg_gap) state <= S_IDLE;
                end

                default: state <= S_IDLE;
            endcase
        end
    end
endmodule
