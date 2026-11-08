// UART receiver, 8N1, LSB first. DIV clock cycles per bit. Bits are sampled in
// the middle; after the middle of the stop bit the receiver is ready for the
// next start edge, so a sender with a slightly faster clock does not lose bytes.
// A byte with a bad stop bit is dropped.
//
// SPDX-License-Identifier: BSD-3-Clause

module uart_rx #(
    parameter int DIV = 521             // 60 MHz / 115200
) (
    input  logic       clk,
    input  logic       rst,
    input  logic       rx,
    output logic [7:0] data,
    output logic       valid            // one cycle per byte
);
    logic [1:0]  rx_s;
    logic [3:0]  bits;                  // 0 idle, 10 start .. 1 stop
    logic [7:0]  sh;
    logic [$clog2(DIV)-1:0] cnt;

    always_ff @(posedge clk) begin
        rx_s  <= {rx_s[0], rx};
        valid <= 1'b0;
        if (rst) begin
            rx_s <= '1;
            bits <= '0;
            cnt  <= '0;
        end else if (bits == 4'd0) begin
            if (!rx_s[1]) begin
                bits <= 4'd10;
                cnt  <= $clog2(DIV)'(DIV / 2);  // first sample in the middle of the start bit
            end
        end else if (cnt == $clog2(DIV)'(DIV - 1)) begin
            cnt  <= '0;
            bits <= bits - 4'd1;
            if (bits == 4'd10 && rx_s[1])
                bits <= '0;                 // glitch, not a start bit
            else if (bits == 4'd1) begin
                data  <= sh;
                valid <= rx_s[1];
            end else if (bits != 4'd10)
                sh <= {rx_s[1], sh[7:1]};
        end else begin
            cnt <= cnt + 1'b1;
        end
    end
endmodule
