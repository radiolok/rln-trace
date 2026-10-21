// Behavioural stand-ins for the Gowin primitives used by the board tops, for
// lint and simulation only. Synthesis uses the real primitives.
//
// SPDX-License-Identifier: BSD-3-Clause

/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off UNUSEDPARAM */
/* verilator lint_off MULTIDRIVEN */

module rPLL #(
    parameter FCLKIN = "100.0", parameter IDIV_SEL = 0, parameter FBDIV_SEL = 0, parameter ODIV_SEL = 8,
    parameter PSDA_SEL = "0000", parameter DEVICE = "GW2AR-18C"
) (
    output logic CLKOUT, output logic CLKOUTP, output logic CLKOUTD, output logic CLKOUTD3,
    output logic LOCK,
    input  logic CLKIN, input logic CLKFB, input logic RESET, input logic RESET_P,
    input  logic [5:0] FBDSEL, input logic [5:0] IDSEL, input logic [5:0] ODSEL,
    input  logic [3:0] PSDA, input logic [3:0] DUTYDA, input logic [3:0] FDLY
);
    assign CLKOUT = CLKIN;
    assign CLKOUTP = CLKIN;
    assign CLKOUTD = CLKIN;
    assign CLKOUTD3 = CLKIN;
    assign LOCK = !RESET;
endmodule

module ODDR #(parameter TXCLK_POL = 0, parameter INIT = 0) (
    input logic D0, input logic D1, input logic TX, input logic CLK, output logic Q0, output logic Q1
);
    logic r, f;
    always_ff @(posedge CLK) r <= D0;
    always_ff @(negedge CLK) f <= D1;
    assign Q0 = CLK ? r : f;
    assign Q1 = TX;
endmodule

module IOBUF (output logic O, inout wire IO, input logic I, input logic OEN);
    assign IO = OEN ? 1'bz : I;
    assign O = IO;
endmodule

/* verilator lint_on MULTIDRIVEN */
/* verilator lint_on UNUSEDPARAM */
/* verilator lint_on UNUSEDSIGNAL */
