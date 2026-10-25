// Симуляция tracela.v: синтетический поток TPIU (trace.py encode) на линиях,
// запись в режимах 0 и 1, кадры ER1 — в файлы для trace.py decode.
//   python3 trace.py encode --out gw/stream.hex
//   iverilog -g2012 -o tb gw/tb.v gw/tracela.v && vvp -n tb && python3 trace.py decode gw/tb_m0.hex
`timescale 1ns/1ps
module OSCB #(parameter FREQ_MODE = "", parameter FREQ_DIV = 1, parameter DYN_TRIM_EN = "")
    (output OSCOUT, output OSCREF, input OSCEN, input FMODE, input [7:0] RTRIM, input [5:0] RTCTRIM);
    reg c = 0; always #16.7 c = ~c; assign OSCOUT = c;
endmodule
module GW_JTAG (input tck_pad_i, tms_pad_i, tdi_pad_i, output tdo_pad_o, output tck_o, tdi_o, test_logic_reset_o, run_test_idle_er1_o, run_test_idle_er2_o,
    shift_dr_capture_dr_o, update_dr_o, pause_dr_o, enable_er1_o, enable_er2_o, input tdo_er1_i, tdo_er2_i);
    assign tck_o = tb.tck, tdi_o = tb.tdi, shift_dr_capture_dr_o = tb.sh, update_dr_o = tb.upd,
        enable_er1_o = tb.en1, enable_er2_o = tb.en2;
endmodule
module tb;
    localparam DL = 12, H = 10, NW = H + (1 << DL);
    parameter HALF = 400;  // полупериод TRACECLK, нс
    reg tck = 0, tdi = 0, sh = 0, upd = 0, en1 = 0, en2 = 0;
    reg [15:0] ch = 0;
    top #(.DEPTH_LOG2(DL), .WIN_LOG2(14)) dut (.ch(ch), .tck_pad_i(1'b0), .tms_pad_i(1'b0), .tdi_pad_i(1'b0), .tdo_pad_o());

    reg [3:0] st [0:65535];
    integer ns = 0, k = 0, n, off, fd;
    initial begin
        for (n = 0; n < 65536; n = n + 1) st[n] = 4'hx;
        $readmemh("gw/stream.hex", st);
        while (st[ns] !== 4'hx) ns = ns + 1;
    end
    reg run_src = 0;
    always begin
        #HALF;
        if (run_src && k < ns) begin
            ch[12] = ~ch[12];
            #2 ch[11:8] = st[k];  // данные меняются чуть позже фронта такта
            k = k + 1;
        end
    end

    task wr(input [31:0] c);
        begin
            en2 = 1; sh = 1;
            tdi = 1'bx; #50 tck = 1; #50 tck = 0;  // Capture-DR
            for (n = 0; n < 32; n = n + 1) begin tdi = c[n]; #50 tck = 1; #50 tck = 0; end
            sh = 0; upd = 1; #50 tck = 1; #50 tck = 0; upd = 0; en2 = 0;
        end
    endtask
    reg [32*NW+7:0] got;
    task rd(input [8*16:1] fname);
        begin
            en1 = 1; sh = 1;
            for (n = 0; n < 32 * NW + 8; n = n + 1) begin
                got = {dut.tdo1, got[32*NW+7:1]};
                #50 tck = 1; #50 tck = 0;
            end
            sh = 0; en1 = 0; #50 tck = 1; #50 tck = 0;
            for (off = 7; off >= 0; off = off - 1)
                if (((got >> off) & 32'hFFFFFFFF) == 32'h414E4C52) got = got >> off;
            fd = $fopen(fname, "w");
            for (n = 0; n < NW; n = n + 1) $fdisplay(fd, "%h", got[32 * n +: 32]);
            $fclose(fd);
            $display("%0s: w0 %h cmd %h st %h miss %h", fname, got[31:0], got[95:64], got[127:96], got[159:128]);
        end
    endtask

    initial begin
        #1000;
        wr({4'hA, 1'b1, 2'd0, 9'd0, 16'd0});  // пуск, режим 0
        run_src = 1;
        #(HALF * (ns + 10));
        wr({4'hA, 1'b0, 2'd0, 9'd0, 16'd0});
        rd("gw/tb_m0.hex");
        run_src = 0; k = 0;
        wr({4'hA, 1'b1, 2'd1, 9'd6, 16'd0});  // пуск, режим 1, dly 6
        run_src = 1;
        #(HALF * (ns + 10));
        wr({4'hA, 1'b0, 2'd1, 9'd6, 16'd0});
        rd("gw/tb_m1.hex");
        $finish;
    end
endmodule
