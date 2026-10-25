// Поиск линий USB2 (D+/D−) SLogic16U3 по JTAG: 22 свободных GPIO GW5AT-15 MG132 (все, кроме
// каналов CH0..CH15, JTAG, флеш, RECONFIG_N, DONE, READY, MODE). Каждый вывод — IOBUF: по команде
// вход (Z), 0 или 1 (DRIVE=4 в .cst). Кто сидит на одной цепи с ведущим выводом — идёт за ним;
// если на цепи D+, хост видит подключение и начинает сброс — смены уровней пишутся в буфер.
// Порядок p[i] — в uprobe.cst, его же берёт uprobe.py. JTAG — как в trace/gw/tracela.v.
//
// ER2 (0x43), DR 32 бита, [31:28] — метка:
//   0xC  oe[NP-1:0] = [NP-1:0] — 1: вывод ведётся
//   0xD  val[NP-1:0] = [NP-1:0] — уровень ведомых выводов
//   0xA  [27] пуск записи, [15:0] адрес чтения буфера
// ER1 (0x42), DR на выход, первым идёт бит 0 слова 0:
//   0  "RLNU" (0x554E4C52)
//   1  [7:0] версия, [15:8] DEPTH_LOG2, [23:16] WIN_LOG2, [31:24] seq окна
//   2  последняя команда 0xA (эхо)
//   3  oe        4  val        5  уровни сейчас
//   6  [DEPTH_LOG2:0] записано слов, [30] идёт запись, [31] буфер полон
//   7..17  фронтов за окно: p[2k] в [15:0], p[2k+1] в [31:16] (насыщение 0xFFFF)
//   18 был 1 за окно   19 был 0 за окно
//   20 тактов G13 (p[8], на нём чей-то генератор) за окно — счётчик в его домене, код Грея
//   21.. буфер с адреса чтения: {dt[9:0], p[21:0]}, слово на каждую смену уровней;
//        dt — тактов OSCB от прошлой записи, 1023 = «1023 и больше»
module top #(
    parameter NP = 22,
    parameter DEPTH_LOG2 = 14,  // 16 Кслов × 32 = 32 из 35 BSRAM
    parameter WIN_LOG2 = 24  // 2^24 тактов ≈ 0,56 с (OSCB ≈ 30 МГц)
) (
    inout wire [NP-1:0] p,
    input wire tck_pad_i, tms_pad_i, tdi_pad_i,
    output wire tdo_pad_o
);
    localparam H = 22, DEPTH = 1 << DEPTH_LOG2;
    localparam [7:0] VER = 2, DL8 = DEPTH_LOG2, WL8 = WIN_LOG2;

    wire clk;
    OSCB #(.FREQ_MODE("210"), .FREQ_DIV(4), .DYN_TRIM_EN("FALSE")) osc (
        .OSCOUT(clk), .OSCREF(), .OSCEN(1'b1), .FMODE(1'b1),
        .RTRIM(8'd0), .RTCTRIM(6'd0));

    reg [31:0] oe = 0, val = 0;  // из JTAG-домена, квазистатика
    wire [NP-1:0] pin;
    genvar g;
    generate
        for (g = 0; g < NP; g = g + 1) begin : io
            IOBUF b (.O(pin[g]), .IO(p[g]), .I(val[g]), .OEN(~oe[g]));
        end
    endgenerate

    reg [NP-1:0] s1 = 0, s2 = 0, s3 = 0;
    always @(posedge clk) {s3, s2, s1} <= {s2, s1, pin};

    // ---- запись смен уровней ----
    reg [31:0] cmd = 0;
    reg arm_t = 0;
    reg [2:0] arm_s = 0;
    always @(posedge clk) arm_s <= {arm_s[1:0], arm_t};
    wire arm = arm_s[2] ^ arm_s[1];

    reg [31:0] mem [0:DEPTH-1];
    reg [DEPTH_LOG2:0] wptr = 0;
    reg run = 0, full = 0;
    reg [9:0] dt = 0;
    always @(posedge clk) begin
        if (~&dt)
            dt <= dt + 1'b1;
        if (arm) begin
            wptr <= 0;
            run <= 1;
            full <= 0;
            dt <= 0;
        end else if (run && (s2 != s3 || wptr == 0)) begin
            mem[wptr[DEPTH_LOG2-1:0]] <= {dt, s2};
            wptr <= wptr + 1'b1;
            dt <= 0;
            if (wptr == DEPTH - 1) begin
                run <= 0;
                full <= 1;
            end
        end
    end

    // ---- окно: фронты и уровни ----
    reg [WIN_LOG2-1:0] tmr = 0;
    reg [7:0] seq = 0;
    reg [16*NP-1:0] cnt = 0, fcnt = 0;
    reg [NP-1:0] w1 = 0, w0 = 0, fw1 = 0, fw0 = 0;
    integer i;
    always @(posedge clk) begin
        tmr <= tmr + 1'b1;
        if (&tmr) begin
            seq <= seq + 1'b1;
            fw1 <= w1 | s2;
            fw0 <= w0 | ~s2;
            w1 <= 0;
            w0 <= 0;
        end else begin
            w1 <= w1 | s2;
            w0 <= w0 | ~s2;
        end
        for (i = 0; i < NP; i = i + 1)
            if (&tmr) begin
                fcnt[16 * i +: 16] <= cnt[16 * i +: 16];
                cnt[16 * i +: 16] <= 0;
            end else if (s2[i] ^ s3[i] && ~&cnt[16 * i +: 16])
                cnt[16 * i +: 16] <= cnt[16 * i +: 16] + 1'b1;
    end

    // ---- частотомер G13: такт выше половины OSCB, считаем в его домене ----
    wire gclk = pin[8];
    reg [31:0] gc = 0, gg = 0;
    always @(posedge gclk) begin
        gc <= gc + 1'b1;
        gg <= gc ^ (gc >> 1);
    end
    reg [31:0] gg1 = 0, gg2 = 0, glast = 0, gfreq = 0;
    reg [31:0] gbin;
    integer k;
    always @* begin
        gbin[31] = gg2[31];
        for (k = 30; k >= 0; k = k - 1)
            gbin[k] = gbin[k + 1] ^ gg2[k];
    end
    always @(posedge clk) begin
        {gg2, gg1} <= {gg1, gg};
        if (&tmr) begin
            gfreq <= gbin - glast;
            glast <= gbin;
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
    reg [31:0] q = 0;
    always @(negedge tck) q <= mem[ra[DEPTH_LOG2-1:0]];

    wire [16*24-1:0] fc = fcnt;  // до 24 выводов, лишнее — нули
    reg [31:0] hw;
    always @* begin
        case (w)
            0: hw = 32'h554E4C52;
            1: hw = {seq, WL8, DL8, VER};
            2: hw = cmd;
            3: hw = oe;
            4: hw = val;
            5: hw = s2;
            6: hw = {full, run, {(29 - DEPTH_LOG2){1'b0}}, wptr};
            7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17: hw = fc[32 * (w - 7) +: 32];
            18: hw = fw1;
            19: hw = fw0;
            20: hw = gfreq;
            21: hw = 0;
            default: hw = q;
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

    // tck_o на GW5A инвертирован: логика по спаду, состояние TAP — по фронту (см. tracela.v)
    reg sh_q = 0, upd_q = 0, en1_q = 0, en2_q = 0;
    always @(posedge tck) {sh_q, upd_q, en1_q, en2_q} <= {sh_cap, upd, en1, en2};

    always @(negedge tck) begin
        idx <= en1_q & sh_q ? idx + 1'b1 : 20'd0;
        if (en2_q & sh_q)
            sr <= {tdi, sr[31:1]};
        if (en2_q & upd_q) begin
            if (sr[31:28] == 4'hA) begin
                cmd <= sr;
                if (sr[27])
                    arm_t <= ~arm_t;
            end
            if (sr[31:28] == 4'hC)
                oe <= sr[NP-1:0];
            if (sr[31:28] == 4'hD)
                val <= sr[NP-1:0];
        end
    end
endmodule
