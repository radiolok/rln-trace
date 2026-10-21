// Synthetic TPIU trace port for the bench (step 2 loopback, Tang Nano 9K): a
// formatter stream with known frames, as DDR samples for an output register.
//
// Stream: a full sync (FF FF FF 7F), then frames, a full sync before every
// cfg_sync_every-th frame, optionally a halfword sync (FF 7F) after every frame.
// Frame k (16 bytes) is computable from k alone, so a receiver checks it:
//   byte 0             0x03: ID change to 1, effective at once (aux bit 0 = 0)
//   bytes 1, 3, 5, 7   k, little-endian (odd bytes are plain data)
//   bytes 9, 11, 13    k[7:0] ^ (0x35 * i)
//   bytes 2 .. 14 even (k[7:0] + 0x1D * i) with bit 0 clear (data, never 0xFF)
//   byte 15            aux bits {k[6:0], 0}
// Port width 1, 2 or 4 bits; each clock gives two samples, out_first going
// out before out_second (rising and falling edge of TRACECLK). TRACEDATA[0] is
// the earliest bit of a sample, low bits of a byte first: the order
// trace_capture expects.
//
// SPDX-License-Identifier: BSD-3-Clause

module tpiu_tx (
    input  logic        clk,
    input  logic        rst,

    input  logic        cfg_enable,
    input  logic [1:0]  cfg_width,        // 0: 1 bit, 1: 2 bits, 2: 4 bits
    input  logic [7:0]  cfg_sync_every,   // frames between full syncs, 0 = 1
    input  logic        cfg_hsync,        // a halfword sync after every frame

    output logic [3:0]  out_first,
    output logic [3:0]  out_second,
    output logic [31:0] frames            // frames sent
);
    typedef enum logic [1:0] {P_SYNC, P_FRAME, P_HSYNC} part_t;

    part_t       part;
    logic [3:0]  idx;                     // byte within the part
    logic [31:0] k;
    logic [7:0]  since_sync;
    logic [7:0]  cur;                     // byte being sent
    logic [1:0]  sub;                     // slice of cur this cycle (widths 1, 2)

    function automatic logic [7:0] frame_byte(input logic [31:0] n, input logic [3:0] i);
        logic [7:0] b;
        case (i)
            4'd0:  b = 8'h03;
            4'd1:  b = n[7:0];
            4'd3:  b = n[15:8];
            4'd5:  b = n[23:16];
            4'd7:  b = n[31:24];
            4'd9, 4'd11, 4'd13: b = n[7:0] ^ (8'h35 * {4'd0, i});
            4'd15: b = {n[6:0], 1'b0};
            default: b = (n[7:0] + 8'h1D * {4'd0, i}) & 8'hFE;
        endcase
        frame_byte = b;
    endfunction

    always_comb begin
        case (part)
            P_SYNC:  cur = (idx == 4'd3) ? 8'h7F : 8'hFF;
            P_HSYNC: cur = (idx == 4'd1) ? 8'h7F : 8'hFF;
            default: cur = frame_byte(k, idx);
        endcase
    end

    // cycles per byte: 4 bits -> 1, 2 bits -> 2, 1 bit -> 4
    logic [1:0] last_sub;
    assign last_sub = (cfg_width == 2'd2) ? 2'd0 : (cfg_width == 2'd1) ? 2'd1 : 2'd3;

    always_comb begin
        out_first  = '0;
        out_second = '0;
        if (cfg_enable) begin
            case (cfg_width)
                2'd2: begin out_first = cur[3:0]; out_second = cur[7:4]; end
                2'd1: begin out_first = {2'b0, cur[4*sub +: 2]}; out_second = {2'b0, cur[4*sub + 2 +: 2]}; end
                default: begin out_first = {3'b0, cur[2*sub]}; out_second = {3'b0, cur[2*sub + 1]}; end
            endcase
        end
    end

    logic       byte_done, part_done;
    logic [7:0] every;
    assign byte_done = cfg_enable && (sub == last_sub);
    assign part_done = byte_done && (idx == (part == P_FRAME ? 4'd15 : part == P_SYNC ? 4'd3 : 4'd1));
    assign every     = (cfg_sync_every == 8'd0) ? 8'd1 : cfg_sync_every;

    always_ff @(posedge clk) begin
        if (rst) begin
            part       <= P_SYNC;
            idx        <= '0;
            sub        <= '0;
            k          <= '0;
            since_sync <= '0;
            frames     <= '0;
        end else if (cfg_enable) begin
            sub <= byte_done ? 2'd0 : sub + 2'd1;
            if (byte_done) idx <= idx + 4'd1;
            if (part_done) begin
                idx <= '0;
                case (part)
                    P_FRAME: begin
                        k      <= k + 32'd1;
                        frames <= frames + 32'd1;
                        if (cfg_hsync) begin
                            part <= P_HSYNC;
                        end else if (since_sync + 8'd1 >= every) begin
                            part       <= P_SYNC;
                            since_sync <= '0;
                        end else begin
                            since_sync <= since_sync + 8'd1;
                        end
                    end
                    P_HSYNC: begin
                        if (since_sync + 8'd1 >= every) begin
                            part       <= P_SYNC;
                            since_sync <= '0;
                        end else begin
                            part       <= P_FRAME;
                            since_sync <= since_sync + 8'd1;
                        end
                    end
                    default: part <= P_FRAME;
                endcase
            end
        end
    end
endmodule
