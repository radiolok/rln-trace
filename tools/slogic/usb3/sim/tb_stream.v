// Стенд тракта потока usb3d (u3stream): трасса через afifo и тестовый источник, потребитель со случайным ready.
// Проверки: непрерывность или разрывы, равные счётчикам потерь; слово каждый такт при ready = 1.
//   sh sim/run.sh
`timescale 1ns/1ps
module tb;
    reg tclk = 0, pclk = 0;
    always #8 tclk = ~tclk;      // 62,5 МГц
    always #4 pclk = ~pclk;      // 125 МГц
    reg run = 0, clr = 0; reg [1:0] src = 0; reg [15:0] rate = 0;
    reg t_we = 0; reg [31:0] t_wd = 0; reg [1:0] tph = 0; reg t_on = 0;
    always @(posedge tclk) begin            // слово трассы раз в 4 такта: значение — счётчик
        tph <= tph + 1;
        t_we <= t_on && tph == 3;
        if (t_on && tph == 3) t_wd <= t_wd + 1;
    end
    reg ready = 0; integer pr = 50;        // вероятность ready, %
    wire valid; wire [31:0] data;
    wire [31:0] w_out, w_in, tdrop, gdrop, tfreq, fill;
    u3stream #(.FIFO_LOG2(12)) dut (.tclk(tclk), .t_we(t_we), .t_wd(t_wd), .pclk(pclk), .run(run), .src(src),
        .rate(rate), .clr(clr), .o_valid(valid), .o_data(data), .i_ready(ready),
        .o_w_out(w_out), .o_w_in(w_in), .o_tdrop(tdrop), .o_gdrop(gdrop), .o_tfreq(tfreq), .o_fill(fill));
    integer got = 0, gaps = 0, lost = 0, errors = 0, bub = 0; reg [31:0] expv = 0; reg first = 1;
    reg stall = 0; reg [31:0] gen_n = 0;
    always @(posedge pclk) begin
        ready <= !stall && ($urandom % 100) < pr;
        if (valid && ready) begin
            got = got + 1;
            if (!first && data != expv) begin
                gaps = gaps + 1;
                if (data > expv) lost = lost + (data - expv);
                else begin errors = errors + 1; if (errors < 5) $display("  ОШИБКА: назад %h после %h", data, expv - 1); end
            end
            first = 0; expv = data + 1;
        end
        if (ready && !valid && src == 1 && run) bub = bub + 1;
    end
    task reset_rx; begin got = 0; gaps = 0; lost = 0; first = 1; bub = 0; end endtask
    task check(input integer name, input [31:0] drops); begin
        $display("%0d: получено %0d, разрывов %0d, пропало по разрывам %0d, потерь по счётчику %0d, w_out %0d, наиб. заполнение %0d",
                 name, got, gaps, lost, drops, w_out, fill[31:16]);
        if (lost != drops || errors) begin $display("  ОШИБКА: разрывы не равны счётчику"); errors = errors + 1; end
    end endtask
    initial begin
        $dumpfile("sim/tb_stream.vcd"); $dumpvars(0, tb);
        repeat (20) @(posedge pclk);
        // 1. трасса, ready 50 % (выход в 4 раза быстрее входа) — потерь нет
        run = 1; src = 0; t_on = 1; pr = 50;
        repeat (40000) @(posedge pclk);
        t_on = 0; repeat (2000) @(posedge pclk);
        $display("1 — трасса, ready 50 %%"); check(1, tdrop);
        if (gaps || tdrop) errors = errors + 1;
        // 2. трасса, потребитель стоит 600 мкс: 4 К слов в sfifo + 512 в afifo, остальное теряется
        reset_rx; clr = 1; @(posedge pclk); clr = 0;
        t_on = 1; stall = 1; repeat (75000) @(posedge pclk); stall = 0;
        repeat (20000) @(posedge pclk); t_on = 0; repeat (5000) @(posedge pclk);
        $display("2 — трасса, потребитель стоит 600 мкс"); check(2, tdrop);
        if (tdrop == 0) begin $display("  ОШИБКА: потерь нет"); errors = errors + 1; end
        // 3. тестовый источник rate 1, ready 100 %: слово каждый такт, без пузырей
        reset_rx; run = 0; @(posedge pclk); clr = 1; src = 1; rate = 1; pr = 100; @(posedge pclk); clr = 0; run = 1;
        repeat (20) @(posedge pclk); bub = 0;
        repeat (20000) @(posedge pclk);
        $display("3 тест rate 1, ready 100 %%: пузырей %0d", bub);
        if (bub) errors = errors + 1;
        run = 0; repeat (100) @(posedge pclk);
        check(3, gdrop);
        // 4. тестовый источник rate 1, ready 30 %: потери sfifo, разрывы = gdrop
        reset_rx; clr = 1; pr = 30; @(posedge pclk); clr = 0; run = 1;
        repeat (60000) @(posedge pclk); gen_n = dut.tgen_val + dut.tgen_we; run = 0; pr = 100; repeat (20000) @(posedge pclk);
        lost = lost + (gen_n - expv);   // хвост: потерянные после последнего принятого слова разрывом не видны
        $display("4 — тестовый источник rate 1, ready 30 %%"); check(4, gdrop);
        if (gdrop == 0) errors = errors + 1;
        // (частотомер: окно 2^20 pclk = 8,4 мс — в симуляции не проверяется)
        if (errors) $display("ИТОГ: ошибок %0d", errors); else $display("ИТОГ: всё сошлось");
        $finish;
    end
endmodule
