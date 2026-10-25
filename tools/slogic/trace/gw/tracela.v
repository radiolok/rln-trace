// Приёмник трассы TPIU на SLogic16U3 с выдачей через JTAG (GW_JTAG, как
// tools/slogic/jprobe).
// Шаг 1 (режимы 0, 1): пятиканальный логический анализатор на внутреннем генераторе
// OSCB (~30 МГц) — годится до TRACECLK ~4 МГц, показывает, как данные стоят
// относительно фронтов.
// Шаг 2 (режим 2): приём от самого TRACECLK — глобальный такт с N9, данные через
// IODELAY (dly × ~12,5 пс) в IDDR, свой буфер с тактом TRACECLK.
//
// Линии: l[0] = TRACECLK (CH12, N9), l[4:1] = TRACED0..3 (CH8..CH11).
//
// Режимы (задаются командой ER2):
//   0  смены уровней: слово {ts[26:0], l[4:0]} на каждую смену любой линии и
//      принудительно раз в 2^26 тактов (чтобы склеить переполнение ts)
//   1  выборка по фронту: через dly + 1 тактов после каждого фронта TRACECLK
//      (после синхронизатора) берётся TRACED[3:0]; 8 полубайт на слово, первый — в [3:0]
//   2  IDDR от TRACECLK, задержка данных — IODELAY своя у каждой линии (команда 0xB);
//      полубайт по фронту, потом по спаду; 8 полубайт на слово, первый — в [3:0].
//      Порт 4 бита.
// Запись идёт с команды «пуск» до заполнения буфера (2^DEPTH_LOG2 слов). У режимов
// 0/1 и 2 буферы раздельные (такты записи разные); чтение — из буфера режима команды.
//
// ER2 (0x43), DR 32 бита на вход: [31:28] 0xA — метка, [27] пуск, [26:25] режим,
//   [24:16] dly, [15:0] адрес чтения (слово буфера).
//   Или [31:28] 0xB — задержка IODELAY линии TRACED[25:24] (все четыре, если [26]) =
//   [7:0] ступеней по ~12,5 пс; пуск записи не трогает.
// ER1 (0x42), DR на выход, первым по TDO идёт бит 0 слова 0:
//   0  "RLNA" (0x414E4C52)
//   1  [7:0] версия, [15:8] DEPTH_LOG2, [23:16] WIN_LOG2, [31:24] seq окна частотомера
//   2  последняя команда ER2 (эхо: проверка, что TDI дошёл без сдвига)
//   3  [16:0] записано слов, [29:28] режим записи, [30] идёт запись, [31] буфер полон
//      (для режима команды: 0/1 — буфер OSCB, 2 — буфер TRACECLK)
//   4  фронтов, пропущенных режимом 1 (новый фронт раньше выборки)
//   5..9  фронтов линии l[i] за окно 2^WIN_LOG2 тактов, [31:24] seq окна
//   10 тактов TRACECLK за окно (счётчик в домене TRACECLK, через код Грея)
//   11 задержки IODELAY: [7:0] TRACED0 … [31:24] TRACED3
//   12 сдвиговый регистр ER2 (отладка JTAG)
//   13 [15:0] тактов сдвига ER2, [31:16] Update-DR при ER2 (отладка JTAG)
//   14..  буфер с адреса чтения
module top #(
    parameter DEPTH_LOG2 = 13,  // два буфера по 8 Кслов: 32 из 35 BSRAM
    parameter WIN_LOG2 = 24  // 2^24 тактов ≈ 0,56 с (OSCB ≈ 30 МГц)
) (
    input wire [15:0] ch,
    // JTAG: «волшебные» имена, в .cst их нет (см. jprobe.v)
    input wire tck_pad_i, tms_pad_i, tdi_pad_i,
    output wire tdo_pad_o
);
    localparam H = 14, DEPTH = 1 << DEPTH_LOG2;
    localparam [7:0] VER = 3, DL8 = DEPTH_LOG2, WL8 = WIN_LOG2;

    wire clk;
    OSCB #(.FREQ_MODE("210"), .FREQ_DIV(4), .DYN_TRIM_EN("FALSE")) osc (
        .OSCOUT(clk), .OSCREF(), .OSCEN(1'b1), .FMODE(1'b1),
        .RTRIM(8'd0), .RTCTRIM(6'd0));

    wire [4:0] l = {ch[11:8], ch[12]};
    reg [4:0] s1 = 0, s2 = 0, s3 = 0;
    always @(posedge clk) {s3, s2, s1} <= {s2, s1, l};

    // ---- команда из JTAG-домена ----
    reg [31:0] cmd = 0;
    reg [31:0] dls = 0;  // задержки IODELAY линий, по 8 бит
    reg arm_t = 0;
    reg [2:0] arm_s = 0;
    always @(posedge clk) arm_s <= {arm_s[1:0], arm_t};
    wire arm = arm_s[2] ^ arm_s[1];

    // ---- запись ----
    reg [31:0] mem [0:DEPTH-1];
    reg [DEPTH_LOG2:0] wptr = 0;
    reg run = 0, full = 0;
    reg [1:0] mode = 0;
    reg [8:0] dly = 0, dcnt = 0;
    reg pend = 0;
    reg [2:0] ncnt = 0;
    reg [31:0] acc = 0, miss = 0;
    reg [26:0] ts = 0;
    reg we = 0;
    reg [31:0] wd = 0;

    always @(posedge clk) begin
        ts <= ts + 1'b1;
        we <= 0;
        if (arm) begin
            wptr <= 0;
            run <= cmd[26:25] != 2;
            full <= 0;
            mode <= cmd[26:25];
            dly <= cmd[24:16];
            pend <= 0;
            ncnt <= 0;
            miss <= 0;
        end else if (run) begin
            if (mode == 0) begin
                if (s2 != s3 || ts[25:0] == 0) begin
                    we <= 1;
                    wd <= {ts, s2};
                end
            end else begin
                if (s2[0] ^ s3[0]) begin
                    if (pend)
                        miss <= miss + 1'b1;
                    pend <= 1;
                    dcnt <= dly;
                end else if (pend) begin
                    if (dcnt == 0) begin
                        pend <= 0;
                        acc <= {s2[4:1], acc[31:4]};
                        ncnt <= ncnt + 1'b1;
                        if (ncnt == 7) begin
                            we <= 1;
                            wd <= {s2[4:1], acc[31:4]};
                        end
                    end else
                        dcnt <= dcnt - 1'b1;
                end
            end
        end
        if (we && run) begin
            mem[wptr[DEPTH_LOG2-1:0]] <= wd;
            wptr <= wptr + 1'b1;
            if (wptr == DEPTH - 1) begin
                run <= 0;
                full <= 1;
            end
        end
    end

    // ---- частотомер: фронты каждой линии за окно ----
    reg [WIN_LOG2-1:0] tmr = 0;
    reg [7:0] seq = 0;
    reg [24*5-1:0] cnt = 0, fcnt = 0;
    integer i;
    always @(posedge clk) begin
        tmr <= tmr + 1'b1;
        if (&tmr)
            seq <= seq + 1'b1;
        for (i = 0; i < 5; i = i + 1)
            if (&tmr) begin
                fcnt[24 * i +: 24] <= cnt[24 * i +: 24];
                cnt[24 * i +: 24] <= 0;
            end else if (s2[i] ^ s3[i] && ~&cnt[24 * i +: 24])
                cnt[24 * i +: 24] <= cnt[24 * i +: 24] + 1'b1;
    end

    // ---- режим 2: приём от TRACECLK ----
    wire tclk = ch[12];  // N9: GCLKT_2 — на глобальную сеть
    wire [3:0] dd, q0, q1;
    genvar g;
    generate
        for (g = 0; g < 4; g = g + 1) begin : ddr
            IODELAY #(.C_STATIC_DLY(0), .DYN_DLY_EN("TRUE"), .ADAPT_EN("FALSE")) dl (
                .DI(ch[8 + g]), .SDTAP(1'b0), .VALUE(1'b0), .DLYSTEP(dls[8 * g +: 8]),
                .DO(dd[g]), .DF());
            IDDR id (.D(dd[g]), .CLK(tclk), .Q0(q0[g]), .Q1(q1[g]));
        end
    endgenerate

    reg [2:0] arm2_s = 0;
    always @(posedge tclk) arm2_s <= {arm2_s[1:0], arm_t};
    wire arm2 = arm2_s[2] ^ arm2_s[1];
    reg [31:0] mem2 [0:DEPTH-1];
    reg [DEPTH_LOG2:0] wptr2 = 0;
    reg run2 = 0, full2 = 0;
    reg [1:0] bcnt = 0;
    reg [23:0] acc2 = 0;
    always @(posedge tclk) begin
        acc2 <= {q1, q0, acc2[23:8]};  // Q0 — выборка по фронту, Q1 — по следующему спаду
        bcnt <= bcnt + 1'b1;
        if (arm2) begin
            wptr2 <= 0;
            run2 <= cmd[26:25] == 2;
            full2 <= 0;
            bcnt <= 0;
        end else if (run2 && bcnt == 3) begin
            mem2[wptr2[DEPTH_LOG2-1:0]] <= {q1, q0, acc2};
            wptr2 <= wptr2 + 1'b1;
            if (wptr2 == DEPTH - 1) begin
                run2 <= 0;
                full2 <= 1;
            end
        end
    end

    // частотомер TRACECLK: OSCB его не оцифрует выше ~15 МГц — считаем такты в его
    // же домене и переносим код Грея
    reg [31:0] tc = 0, tg = 0;
    always @(posedge tclk) begin
        tc <= tc + 1'b1;
        tg <= tc ^ (tc >> 1);
    end
    reg [31:0] tg1 = 0, tg2 = 0, tlast = 0, tfreq = 0;
    reg [31:0] tbin;
    integer k;
    always @* begin
        tbin[31] = tg2[31];
        for (k = 30; k >= 0; k = k - 1)
            tbin[k] = tbin[k + 1] ^ tg2[k];
    end
    always @(posedge clk) begin
        {tg2, tg1} <= {tg1, tg};
        if (&tmr) begin
            tfreq <= tbin - tlast;
            tlast <= tbin;
        end
    end

    // ---- пользовательский JTAG ----
    wire tck, tdi, sh_cap, upd, en1, en2;
    reg [19:0] idx = 0;
    reg [31:0] sr = 0;
    wire [14:0] w = idx[19:5];
    wire [4:0] bi = idx[4:0];
    wire [19:0] idx1 = idx + 1'b1;
    wire [15:0] ra = cmd[15:0] + idx1[19:5] - H;
    reg [31:0] q = 0, q2 = 0;
    always @(negedge tck) q <= mem[ra[DEPTH_LOG2-1:0]];
    always @(negedge tck) q2 <= mem2[ra[DEPTH_LOG2-1:0]];
    wire m2 = cmd[26:25] == 2;

    reg [31:0] hw;
    always @* begin
        case (w)
            0: hw = 32'h414E4C52;
            1: hw = {seq, WL8, DL8, VER};
            2: hw = cmd;
            3: hw = m2 ? {full2, run2, 2'd2, {(27 - DEPTH_LOG2){1'b0}}, wptr2}
                       : {full, run, mode, {(27 - DEPTH_LOG2){1'b0}}, wptr};
            4: hw = miss;
            5: hw = {seq, fcnt[0 +: 24]};
            6: hw = {seq, fcnt[24 +: 24]};
            7: hw = {seq, fcnt[48 +: 24]};
            8: hw = {seq, fcnt[72 +: 24]};
            9: hw = {seq, fcnt[96 +: 24]};
            10: hw = tfreq;
            11: hw = dls;
            12: hw = sr;
            13: hw = {ucnt, scnt};
            default: hw = m2 ? q2 : q;
        endcase
    end
    wire tdo1 = hw[bi];

    GW_JTAG jtag (
        .tck_pad_i(tck_pad_i), .tms_pad_i(tms_pad_i), .tdi_pad_i(tdi_pad_i), .tdo_pad_o(tdo_pad_o),
        .tck_o(tck), .tdi_o(tdi), .test_logic_reset_o(),
        .run_test_idle_er1_o(), .run_test_idle_er2_o(),
        .shift_dr_capture_dr_o(sh_cap), .update_dr_o(upd), .pause_dr_o(),
        .enable_er1_o(en1), .enable_er2_o(en2),
        .tdo_er1_i(tdo1), .tdo_er2_i(sr[0]));

    // tck_o у GW_JTAG на GW5A инвертирован относительно TCK на выводе: его спад — это
    // фронт TCK, на котором TAP переходит и берёт TDI (адаптер меняет TDI по спаду
    // TCK). Проверено на железе перебором вариантов (журнал, шаг 2): вся логика —
    // по спаду tck_o, состояние TAP защёлкивается по фронту tck_o (середина такта),
    // поэтому на спаде k виден TAP между фронтами TCK k-1 и k, как и положено.
    // Работа по фронту tck_o — гонка с TAP: v1 повезло с разводкой, v3 терял бит.
    reg sh_q = 0, upd_q = 0, en1_q = 0, en2_q = 0;
    always @(posedge tck) {sh_q, upd_q, en1_q, en2_q} <= {sh_cap, upd, en1, en2};

    always @(negedge tck) begin
        idx <= en1_q & sh_q ? idx + 1'b1 : 20'd0;
        if (en2_q & sh_q)
            sr <= {tdi, sr[31:1]};
        if (en2_q & upd_q & (sr[31:28] == 4'hA)) begin
            cmd <= sr;
            if (sr[27])
                arm_t <= ~arm_t;
        end
    end
    // задержки линий
    reg [15:0] ucnt = 0, scnt = 0;
    always @(negedge tck) begin
        if (en2_q & sh_q) scnt <= scnt + 1'b1;
        if (en2_q & upd_q) ucnt <= ucnt + 1'b1;
    end
    wire setd = en2_q & upd_q & (sr[31:28] == 4'hB);
    always @(negedge tck) begin
        if (setd & (sr[26] | sr[25:24] == 2'd0)) dls[7:0] <= sr[7:0];
        if (setd & (sr[26] | sr[25:24] == 2'd1)) dls[15:8] <= sr[7:0];
        if (setd & (sr[26] | sr[25:24] == 2'd2)) dls[23:16] <= sr[7:0];
        if (setd & (sr[26] | sr[25:24] == 2'd3)) dls[31:24] <= sr[7:0];
    end
endmodule
