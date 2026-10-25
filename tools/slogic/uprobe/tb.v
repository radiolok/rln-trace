// Симуляция uprobe.v: заглушки OSCB, GW_JTAG, IOBUF; команды ER2 и кадр ER1.
// iverilog -g2012 -o tb tb.v uprobe.v && vvp -n tb
`timescale 1ns/1ps
module OSCB #(parameter FREQ_MODE = "", parameter FREQ_DIV = 1, parameter DYN_TRIM_EN = "")
    (output OSCOUT, output OSCREF, input OSCEN, input FMODE, input [7:0] RTRIM, input [5:0] RTCTRIM);
    reg c = 0; always #16.5 c = ~c; assign OSCOUT = c;
endmodule
module IOBUF (output O, inout IO, input I, input OEN);
    assign IO = OEN ? 1'bz : I;
    assign O = IO;
endmodule
module GW_JTAG (input tck_pad_i, tms_pad_i, tdi_pad_i, output tdo_pad_o, output tck_o, tdi_o, test_logic_reset_o, run_test_idle_er1_o, run_test_idle_er2_o,
    shift_dr_capture_dr_o, update_dr_o, pause_dr_o, enable_er1_o, enable_er2_o, input tdo_er1_i, tdo_er2_i);
    // tck_o инвертирован, как на GW5A
    assign tck_o = ~tb.tck, tdi_o = tb.tdi, shift_dr_capture_dr_o = tb.sh, update_dr_o = tb.upd,
        enable_er1_o = tb.en1, enable_er2_o = tb.en2;
endmodule
module tb;
    localparam NW = 26;
    reg tck = 0, tdi = 0, sh = 0, upd = 0, en1 = 0, en2 = 0;
    wire [21:0] p;
    // «плата»: p[3] и p[5] — одна цепь (D+), снаружи подтяжка вниз (хост 15 кОм)
    assign (weak1, weak0) p[3] = p[5];
    pulldown (p[5]);
    // остальные — тоже вниз, кроме p[10] (вверх)
    genvar g;
    generate for (g = 0; g < 22; g = g + 1) if (g != 3 && g != 5 && g != 10) begin : pd pulldown (p[g]); end endgenerate
    pullup (p[10]);
    top #(.WIN_LOG2(10), .DEPTH_LOG2(8)) dut (.p(p), .tck_pad_i(1'b0), .tms_pad_i(1'b0), .tdi_pad_i(1'b0), .tdo_pad_o());
    task clk1; begin #50 tck = 1; #50 tck = 0; end endtask
    task er2(input [31:0] v);
        integer n;
        begin
            en2 = 1; sh = 1; clk1;  // Capture-DR
            for (n = 0; n < 32; n = n + 1) begin tdi = v[n]; clk1; end
            sh = 0; upd = 1; clk1; upd = 0; en2 = 0; clk1;
        end
    endtask
    reg [32*NW+7:0] got;
    reg [32*NW-1:0] fr;
    task er1;
        integer n;
        begin
            en1 = 1; sh = 1; clk1;  // Capture-DR
            for (n = 0; n < 32 * NW + 8; n = n + 1) begin got = {dut.tdo1, got[32*NW+7:1]}; clk1; end
            sh = 0; en1 = 0; clk1;
            fr = got;  // начало кадра — по метке, как в uprobe.py
            for (n = 7; n >= 0; n = n - 1) if (((got >> n) & 32'hFFFFFFFF) == 32'h554E4C52) fr = got >> n;
        end
    endtask
    integer k;
    initial begin
        er2(32'hD000_0020);    // val p[5] = 1
        er2(32'hC000_0020);    // oe p[5]
        er2(32'hA800_0000);    // пуск записи, чтение с 0
        #20000;
        er2(32'hC000_0000);    // отпустить
        #(33 * 1024 * 3);
        er1;
        $display("magic %h ver %h cmd %h oe %h val %h lvl %h st %h", fr[0+:32], fr[32+:32], fr[64+:32], fr[96+:32], fr[128+:32], fr[160+:32], fr[192+:32]);
        $display("edges p3/p2 %h p5/p4 %h  was1 %h was0 %h", fr[32*8+:32], fr[32*9+:32], fr[32*18+:32], fr[32*19+:32]);
        for (k = 22; k < NW; k = k + 1) $display("buf %0d: dt %0d p %h", k - 22, fr[32*k+22+:10], fr[32*k+:22]);
        $finish;
    end
endmodule
