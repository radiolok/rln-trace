// Прозвонка SLogic16U3 (GW5AT-15, MG132) с результатом через JTAG. Все
// кандидаты — только входы, выходов у образа нет: результат читается
// пользовательским регистром JTAG (GW_JTAG, инструкция ER1 = 0x42).
//
// Окна по 2^WIN_LOG2 тактов идут подряд; в конце каждого результат
// защёлкивается в кадр, seq увеличивается. Кадр — слова по 32 бита, первым
// по TDO идёт бит 0 слова 0:
//   0       "RLNJ" (0x4A4E4C52)
//   1       [7:0] версия, [15:8] NP, [23:16] WIN_LOG2, [31:24] seq
//   2+2i    вывод p[i]: [23:0] фронтов (насыщается), [24] был 0, [25] был 1,
//           [26] уровень в конце окна
//   3+2i    [23:0] фронтов после фильтра помех: уровень засчитывается, когда
//           продержался 2^FLT_LOG2 тактов (16 ≈ 530 нс)
//   2+2NP   [23:0] 0xC0FFEE, [31:24] seq — совпадает со словом 1, если кадр
//           не попал на смену окна
// ER2 (0x43) отдаёт 0x12345678 по кругу — проверка канала без прозвонки.
module top #(
    parameter NP = 36,  // больше нельзя: Gowin считает 4 вывода GW_JTAG в лимит 40 I/O
    parameter WIN_LOG2 = 26,  // 2^26 тактов ≈ 2,24 с (OSCB ≈ 30 МГц)
    parameter FLT_LOG2 = 4
) (
    input wire [NP-1:0] p,
    // JTAG: имена «волшебные» — Gowin EDA сам сажает их на выводы JTAG,
    // в .cst их быть не должно (так же делает LiteX, GowinJTAG)
    input wire tck_pad_i, tms_pad_i, tdi_pad_i,
    output wire tdo_pad_o
);
    localparam NW = 2 * NP + 3;

    // FREQ_MODE "210" / 4 — по расчёту 52,5 МГц, на деле ~30 МГц (окно 2^26 = 2,24 с по seq)
    wire clk;
    OSCB #(.FREQ_MODE("210"), .FREQ_DIV(4), .DYN_TRIM_EN("FALSE")) osc (
        .OSCOUT(clk), .OSCREF(), .OSCEN(1'b1), .FMODE(1'b1),
        .RTRIM(8'd0), .RTCTRIM(6'd0));

    // ---- счёт фронтов, окна подряд ----
    reg [NP-1:0] s1 = 0, s2 = 0, s3 = 0;
    reg [NP-1:0] seen0 = 0, seen1 = 0;
    reg [WIN_LOG2-1:0] tmr = 0;
    reg [7:0] seq = 0;
    wire win_end = &tmr;

    always @(posedge clk) {s3, s2, s1} <= {s2, s1, p};

    reg [24*NP-1:0] cnt = 0, fcnt = 0;
    reg [NP-1:0] flt = 0;
    reg [FLT_LOG2*NP-1:0] stab = 0;
    reg [32*NW-1:0] frame = 0;
    localparam [7:0] VER = 2, NP8 = NP, WIN8 = WIN_LOG2;

    integer i;
    always @(posedge clk) begin
        tmr <= tmr + 1'b1;
        seen0 <= win_end ? {NP{1'b0}} : seen0 | ~s2;
        seen1 <= win_end ? {NP{1'b0}} : seen1 | s2;
        if (win_end) begin
            seq <= seq + 1'b1;
            frame[0 +: 32] <= "JNLR";
            frame[32 +: 32] <= {seq + 8'd1, WIN8, NP8, VER};
            frame[32 * (NW - 1) +: 32] <= {seq + 8'd1, 24'hC0FFEE};
        end
        for (i = 0; i < NP; i = i + 1) begin
            if (win_end) begin
                frame[32 * (2 + 2 * i) +: 32] <= {5'd0, s2[i], seen1[i] | s2[i], seen0[i] | ~s2[i], cnt[24 * i +: 24]};
                frame[32 * (3 + 2 * i) +: 32] <= {8'd0, fcnt[24 * i +: 24]};
                cnt[24 * i +: 24] <= 24'd0;
                fcnt[24 * i +: 24] <= 24'd0;
            end else begin
                if (s2[i] ^ s3[i] && ~&cnt[24 * i +: 24])
                    cnt[24 * i +: 24] <= cnt[24 * i +: 24] + 1'b1;
                if (flt[i] ^ s2[i] && &stab[FLT_LOG2 * i +: FLT_LOG2] && ~&fcnt[24 * i +: 24])
                    fcnt[24 * i +: 24] <= fcnt[24 * i +: 24] + 1'b1;
            end
            // фильтр: stab считает такты, пока вход отличается от flt
            if (flt[i] == s2[i])
                stab[FLT_LOG2 * i +: FLT_LOG2] <= 0;
            else if (&stab[FLT_LOG2 * i +: FLT_LOG2]) begin
                flt[i] <= s2[i];
                stab[FLT_LOG2 * i +: FLT_LOG2] <= 0;
            end else
                stab[FLT_LOG2 * i +: FLT_LOG2] <= stab[FLT_LOG2 * i +: FLT_LOG2] + 1'b1;
        end
    end

    // ---- пользовательский JTAG ----
    wire tck, sh_cap, en1, en2;
    reg [11:0] idx = 0;
    wire [11:0] j = idx;  // на железе первым приходит лишний бит, jprobe.py его пропускает
    wire [4:0] bi = j[4:0];
    wire tdo1 = j < 32 * NW ? frame[j] : 1'b0;
    wire [31:0] c2 = 32'h12345678;
    wire tdo2 = c2[bi];

    GW_JTAG jtag (
        .tck_pad_i(tck_pad_i), .tms_pad_i(tms_pad_i), .tdi_pad_i(tdi_pad_i), .tdo_pad_o(tdo_pad_o),
        .tck_o(tck), .tdi_o(), .test_logic_reset_o(),
        .run_test_idle_er1_o(), .run_test_idle_er2_o(),
        .shift_dr_capture_dr_o(sh_cap), .update_dr_o(), .pause_dr_o(),
        .enable_er1_o(en1), .enable_er2_o(en2),
        .tdo_er1_i(tdo1), .tdo_er2_i(tdo2));

    // В Capture-DR и Shift-DR сигнал один. Если на железе кадр всё же
    // сдвинут, jprobe.py найдёт его начало по "RLNJ".
    always @(posedge tck) idx <= (en1 | en2) & sh_cap ? idx + 1'b1 : 12'd0;
endmodule
