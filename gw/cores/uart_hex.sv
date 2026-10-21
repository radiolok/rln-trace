// Packets from hspi_rx as text lines for the UART: the bytes in hex, in bus
// order, one packet per line -- the input format of tools/hspi-crc/find_crc.py.
//
// Words are printed low byte first. The closing word (in_last) adds the bytes
// counted in its top byte (raw mode: the bytes after the last whole word); in
// normal mode that count is 0. A packet without in_good ends with " #bad"
// (a comment for find_crc.py).
//
// SPDX-License-Identifier: BSD-3-Clause

module uart_hex (
    input  logic        clk,
    input  logic        rst,

    input  logic [31:0] in_data,
    input  logic        in_last,
    input  logic        in_good,
    input  logic        in_valid,
    output logic        in_ready,

    output logic [7:0]  out_data,
    output logic        out_valid,
    input  logic        out_ready
);
    typedef enum logic [1:0] {S_LOAD, S_HEX, S_TAIL} state_t;

    state_t      state;
    logic [31:0] word;
    logic [3:0]  nib, nibs;          // nibble to print, nibbles in this word
    logic        last, good;
    logic [2:0]  tail;               // index into " #bad\n" or "\n"

    logic [3:0]  n;
    logic [1:0]  byte_i;
    assign byte_i = nib[2:1];               // nib < 8 while printing
    assign n = nib[0] ? word[8*byte_i +: 4] : word[8*byte_i + 4 +: 4];

    logic [7:0] hexc;
    assign hexc = (n < 4'd10) ? 8'h30 + {4'd0, n} : 8'h57 + {4'd0, n};   // '0'.., 'a'..

    logic [7:0] tailc;
    always_comb begin
        case (good ? tail + 3'd5 : tail)
            3'd0: tailc = 8'h20;     // ' '
            3'd1: tailc = 8'h23;     // '#'
            3'd2: tailc = 8'h62;     // 'b'
            3'd3: tailc = 8'h61;     // 'a'
            3'd4: tailc = 8'h64;     // 'd'
            default: tailc = 8'h0A;  // '\n'
        endcase
    end

    assign in_ready  = (state == S_LOAD);
    assign out_valid = (state == S_HEX) || (state == S_TAIL);
    assign out_data  = (state == S_HEX) ? hexc : tailc;

    logic [2:0] count;
    assign count = (in_data[31:24] > 8'd3) ? 3'd3 : in_data[26:24];

    always_ff @(posedge clk) begin
        if (rst) begin
            state <= S_LOAD;
            word  <= '0;
            nib   <= '0;
            nibs  <= '0;
            last  <= 1'b0;
            good  <= 1'b0;
            tail  <= '0;
        end else begin
            case (state)
                S_LOAD: if (in_valid) begin
                    word <= in_data;
                    last <= in_last;
                    good <= in_good;
                    nib  <= '0;
                    tail <= '0;
                    nibs <= in_last ? {count, 1'b0} : 4'd8;
                    if (in_last && count == 3'd0)
                        state <= S_TAIL;
                    else
                        state <= S_HEX;
                end
                S_HEX: if (out_ready) begin
                    nib <= nib + 4'd1;
                    if (nib + 4'd1 == nibs) state <= last ? S_TAIL : S_LOAD;
                end
                S_TAIL: if (out_ready) begin
                    tail <= tail + 3'd1;
                    if (good || tail == 3'd5) state <= S_LOAD;
                end
                default: state <= S_LOAD;
            endcase
        end
    end
endmodule
