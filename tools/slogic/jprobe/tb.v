// Симуляция jprobe.v: заглушки OSCB и GW_JTAG, сдвиг кадра ER1 как по JTAG.
// Сдвиг начала кадра на железе другой (лишний бит впереди), поэтому кадр ищется по метке.
// iverilog -g2012 -o tb tb.v jprobe.v && vvp tb
`timescale 1ns/1ps
module OSCB #(parameter FREQ_MODE = "", parameter FREQ_DIV = 1, parameter DYN_TRIM_EN = "")
    (output OSCOUT, output OSCREF, input OSCEN, input FMODE, input [7:0] RTRIM, input [5:0] RTCTRIM);
    reg c = 0; always #9.5 c = ~c; assign OSCOUT = c;
endmodule
module GW_JTAG (input tck_pad_i, tms_pad_i, tdi_pad_i, output tdo_pad_o, output tck_o, tdi_o, test_logic_reset_o, run_test_idle_er1_o, run_test_idle_er2_o,
    shift_dr_capture_dr_o, update_dr_o, pause_dr_o, enable_er1_o, enable_er2_o, input tdo_er1_i, tdo_er2_i);
    assign tck_o = tb.tck, shift_dr_capture_dr_o = tb.sh, enable_er1_o = tb.en1, enable_er2_o = tb.en2;
endmodule
module tb;
    localparam NP = 36, NW = 2 * NP + 3;
    reg tck = 0, sh = 0, en1 = 0, en2 = 0;
    reg [NP-1:0] p = 0;
    top #(.WIN_LOG2(12)) dut (.p(p), .tck_pad_i(1'b0), .tms_pad_i(1'b0), .tdi_pad_i(1'b0), .tdo_pad_o());
    // p[3] — 1/40 такта источника, p[7] — 1/160, p[10] держится в 1
    always #400 p[3] = ~p[3];
    always #1600 p[7] = ~p[7];
    initial p[10] = 1;
    reg [32*NW+7:0] got;
    reg [32*NW-1:0] fr;
    integer n, k, off;
    task scan(input e2);
        begin
            en1 = !e2; en2 = e2; sh = 1;
            for (n = 0; n < 32 * NW + 8; n = n + 1) begin   // Capture-DR и Shift-DR: TDO читается до фронта TCK
                got = {e2 ? dut.tdo2 : dut.tdo1, got[32*NW+7:1]};
                #50 tck = 1; #50 tck = 0;
            end
            sh = 0; en1 = 0; en2 = 0; #50 tck = 1; #50 tck = 0;
            // начало кадра — по "RLNJ" (ER2 — по 0x12345678), как в jprobe.py
            fr = got;
            for (off = 7; off >= 0; off = off - 1)
                if (((got >> off) & 32'hFFFFFFFF) == (e2 ? 32'h12345678 : 32'h4A4E4C52)) fr = got >> off;
        end
    endtask
    initial begin
        #(19 * 4096 * 2.5);
        scan(0);
        $display("w0 %h w1 %h last %h", fr[0 +: 32], fr[32 +: 32], fr[32*(NW-1) +: 32]);
        for (k = 0; k < 12; k = k + 1) $display("p[%0d] %h %h", k, fr[32*(2+2*k) +: 32], fr[32*(3+2*k) +: 32]);
        scan(1);
        $display("ER2 %h", fr[0 +: 32]);
        $finish;
    end
endmodule
