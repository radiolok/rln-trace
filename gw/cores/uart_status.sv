// Status line for the UART: "# " and N 32-bit words in hex separated by
// spaces, then "\n". The words are taken on start; busy until the newline went.
// The leading '#' makes it a comment for tools/hspi-crc/find_crc.py.
//
// SPDX-License-Identifier: BSD-3-Clause

module uart_status #(
    parameter int N = 4
) (
    input  logic            clk,
    input  logic            rst,
    input  logic [32*N-1:0] words,      // word 0 printed first
    input  logic            start,
    output logic            busy,

    output logic [7:0]      out_data,
    output logic            out_valid,
    input  logic            out_ready
);
    logic [32*N-1:0] w;
    localparam int WIW = $clog2(N + 1);
    localparam logic [WIW-1:0] LAST = WIW'(N - 1);
    logic [WIW-1:0]  wi;                 // word being printed
    logic [3:0]      pos;                // 0..7 nibbles, 8 separator
    logic            head;               // printing "# "
    logic            head2;

    logic [3:0] nib;
    assign nib = w[32*wi + 28 - 4*pos +: 4];

    always_comb begin
        if (head)                       out_data = head2 ? 8'h20 : 8'h23;   // "# "
        else if (pos == 4'd8)           out_data = (wi == LAST) ? 8'h0A : 8'h20;
        else if (nib < 4'd10)           out_data = 8'h30 + {4'd0, nib};
        else                            out_data = 8'h57 + {4'd0, nib};
    end
    assign out_valid = busy;

    always_ff @(posedge clk) begin
        if (rst) begin
            busy  <= 1'b0;
            w     <= '0;
            wi    <= '0;
            pos   <= '0;
            head  <= 1'b0;
            head2 <= 1'b0;
        end else if (!busy) begin
            if (start) begin
                busy  <= 1'b1;
                w     <= words;
                wi    <= '0;
                pos   <= '0;
                head  <= 1'b1;
                head2 <= 1'b0;
            end
        end else if (out_ready) begin
            if (head) begin
                head2 <= 1'b1;
                if (head2) head <= 1'b0;
            end else if (pos == 4'd8) begin
                pos <= '0;
                if (wi == LAST) busy <= 1'b0;
                else             wi <= wi + 1'b1;
            end else begin
                pos <= pos + 4'd1;
            end
        end
    end
endmodule
