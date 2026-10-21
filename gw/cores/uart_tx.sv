// UART transmitter, 8N1, LSB first. DIV clock cycles per bit.
//
// SPDX-License-Identifier: BSD-3-Clause

module uart_tx #(
    parameter int DIV = 521             // 60 MHz / 115200
) (
    input  logic       clk,
    input  logic       rst,
    input  logic [7:0] data,
    input  logic       valid,
    output logic       ready,
    output logic       tx
);
    logic [9:0]  sh;                    // stop, data, start; bit 0 goes out first
    logic [3:0]  bits;                  // bits left in sh
    logic [$clog2(DIV)-1:0] cnt;

    assign ready = (bits == 4'd0);

    always_ff @(posedge clk) begin
        if (rst) begin
            sh   <= '1;
            bits <= '0;
            cnt  <= '0;
            tx   <= 1'b1;
        end else if (bits == 4'd0) begin
            tx <= 1'b1;
            if (valid) begin
                sh   <= {1'b1, data, 1'b0};
                bits <= 4'd10;
                cnt  <= '0;
            end
        end else begin
            tx <= sh[0];
            if (cnt == $clog2(DIV)'(DIV - 1)) begin
                cnt  <= '0;
                sh   <= {1'b1, sh[9:1]};
                bits <= bits - 4'd1;
            end else begin
                cnt <= cnt + 1'b1;
            end
        end
    end
endmodule
