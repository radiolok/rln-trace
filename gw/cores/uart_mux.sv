// Two character streams onto one UART, a whole line at a time: the source that
// got the line keeps it until it sends '\n'. When both wait, they take turns,
// so a busy source cannot starve the other.
//
// SPDX-License-Identifier: BSD-3-Clause

module uart_mux (
    input  logic       clk,
    input  logic       rst,

    input  logic [7:0] a_data,
    input  logic       a_valid,
    output logic       a_ready,
    input  logic [7:0] b_data,
    input  logic       b_valid,
    output logic       b_ready,

    output logic [7:0] out_data,
    output logic       out_valid,
    input  logic       out_ready
);
    logic locked, sel;                   // sel: 0 = a, 1 = b
    logic prefer_b;                      // b goes first at the next line boundary
    logic cur;

    assign cur       = locked ? sel : (b_valid && (prefer_b || !a_valid));
    assign out_data  = cur ? b_data : a_data;
    assign out_valid = cur ? b_valid : a_valid;
    assign a_ready   = !cur && out_ready;
    assign b_ready   = cur && out_ready;

    always_ff @(posedge clk) begin
        if (rst) begin
            locked   <= 1'b0;
            sel      <= 1'b0;
            prefer_b <= 1'b0;
        end else if (out_valid && out_ready) begin
            locked <= out_data != 8'h0A;
            sel    <= cur;
            if (out_data == 8'h0A) prefer_b <= !cur;
        end
    end
endmodule
