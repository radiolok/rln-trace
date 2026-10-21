// Симуляция pinmap.v с моделью SPI-флеш: iverilog -g2012 -o tb tb.v pinmap.v && vvp tb
// Проверяет последовательность команд, адреса стирания и записи, страницу отчёта.
`timescale 1ns/1ps

module OSCB #(parameter FREQ_MODE = "25", parameter FREQ_DIV = 10, parameter DYN_TRIM_EN = "FALSE")
    (output reg OSCOUT = 0, output OSCREF, input OSCEN, input FMODE, input [7:0] RTRIM, input [5:0] RTCTRIM);
    always #9.5 OSCOUT = ~OSCOUT;
endmodule

module tb;
    localparam NP = 40;
    reg [NP-1:0] p = 0;
    wire cs_n, sck, mosi;
    reg miso = 1'bz;

    top #(.NP(NP), .WIN_LOG2(14), .POR_LOG2(6)) dut (
        .p(p), .f_cs_n(cs_n), .f_sck(sck), .f_mosi(mosi), .f_miso(miso));

    // источник: вывод i переключается каждые (i+1)*40 нс, вывод 39 стоит в 1, 38 — в 0
    genvar gi;
    generate for (gi = 0; gi < 38; gi = gi + 1) begin : src
        initial forever #((gi + 1) * 40) p[gi] = ~p[gi];
    end endgenerate
    initial begin p[39] = 1; p[38] = 0; end

    // модель флеш
    reg [7:0] cmd, sh;
    integer nb, nbit, polls, wel, erased, progs;
    reg [23:0] addr;
    reg [7:0] page [0:255];
    reg [23:0] idv = 24'h0B4018;
    reg [7:0] outb;

    initial begin erased = 0; progs = 0; wel = 0; polls = 0; end

    always @(negedge cs_n) begin nb = 0; nbit = 0; end
    always @(posedge sck) if (!cs_n) begin
        sh = {sh[6:0], mosi};
        nbit = nbit + 1;
        if (nbit == 8) begin
            nbit = 0;
            if (nb == 0) cmd = sh;
            else if (nb <= 3) addr = {addr[15:0], sh};
            else if (cmd == 8'h02) begin
                if (!wel) $display("ОШИБКА: запись без WREN");
                page[nb - 4] = sh; progs = progs + 1;
            end
            nb = nb + 1;
        end
    end
    // выход флеш меняется по спаду SCK
    always @(negedge sck) if (!cs_n) begin
        if (nb >= 1 && cmd == 8'h9F) outb = idv >> (8 * (3 - nb));
        else if (nb >= 1 && cmd == 8'h05) outb = (polls % 5 != 4) ? 8'h03 : 8'h00;
        else outb = 8'hFF;
        miso = outb[7 - nbit];
    end
    always @(posedge cs_n) begin
        miso = 1'bz;
        case (cmd)
            8'h06: wel = 1;
            8'h05: polls = polls + 1;
            8'h20: begin
                if (!wel) $display("ОШИБКА: стирание без WREN");
                if (addr != 24'h7F0000) $display("ОШИБКА: стирание по 0x%06x", addr);
                erased = erased + 1; wel = 0;
            end
            8'h02: begin
                if (addr != 24'h7F0000) $display("ОШИБКА: запись по 0x%06x", addr);
                wel = 0;
            end
            8'hFF, 8'h66, 8'h99, 8'h9F: ;
            default: $display("ОШИБКА: неожиданная команда %02x", cmd);
        endcase
        $display("%t команда %02x, байт %0d", $time, cmd, nb);
    end

    integer w, j;
    initial begin
        wait (dut.st == 7 || dut.st == 8);
        #1000;
        if (dut.st != 7) $display("ОШИБКА: автомат в FAIL, JEDEC %06x", dut.jid);
        $display("стираний %0d, записано байт %0d", erased, progs);
        $write("заголовок:");
        for (j = 0; j < 16; j = j + 1) $write(" %02x", page[j]);
        $display("");
        for (j = 0; j < NP; j = j + 1) begin
            w = {page[16 + 4*j + 3], page[16 + 4*j + 2], page[16 + 4*j + 1], page[16 + 4*j]};
            $display("вывод %2d: был1 %0d был0 %0d конец %0d фронтов %0d",
                     j, w[31], w[30], w[29], w[28:0]);
        end
        $finish;
    end
endmodule
