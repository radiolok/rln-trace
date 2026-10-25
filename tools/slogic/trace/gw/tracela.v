// Приёмник трассы TPIU на SLogic16U3, шаг 1: пятиканальный логический анализатор
// с выдачей через JTAG (GW_JTAG, как tools/slogic/jprobe). Линии оцифровываются
// внутренним генератором OSCB (~30 МГц), поэтому годится до TRACECLK ~2–3 МГц —
// чтобы увидеть, что данные идут, и как они стоят относительно фронтов.
//
// Линии: l[0] = TRACECLK (CH12, N9), l[4:1] = TRACED0..3 (CH8..CH11).
//
// Режимы (задаются командой ER2):
//   0  смены уровней: слово {ts[26:0], l[4:0]} на каждую смену любой линии и
//      принудительно раз в 2^26 тактов (чтобы склеить переполнение ts)
//   1  выборка по фронту: через dly тактов после каждого фронта TRACECLK берётся
//      TRACED[3:0]; 8 полубайт на слово, первый — в [3:0]
// Запись идёт с команды «пуск» до заполнения буфера (2^DEPTH_LOG2 слов).
//
// ER2 (0x43), DR 32 бита на вход: [31:28] 0xA — метка, [27] пуск, [26:25] режим,
//   [24:16] dly, [15:0] адрес чтения (слово буфера).
// ER1 (0x42), DR на выход, первым по TDO идёт бит 0 слова 0:
//   0  "RLNA" (0x414E4C52)
//   1  [7:0] версия, [15:8] DEPTH_LOG2, [23:16] WIN_LOG2, [31:24] seq окна частотомера
//   2  последняя команда ER2 (эхо: проверка, что TDI дошёл без сдвига)
//   3  [16:0] записано слов, [29:28] режим записи, [30] идёт запись, [31] буфер полон
//   4  фронтов, пропущенных режимом 1 (новый фронт раньше выборки)
//   5..9  фронтов линии l[i] за окно 2^WIN_LOG2 тактов, [31:24] seq окна
//   10..  буфер с адреса чтения
module top #(
    parameter DEPTH_LOG2 = 14,
    parameter WIN_LOG2 = 24  // 2^24 тактов ≈ 0,56 с (OSCB ≈ 30 МГц)
) (
    input wire [15:0] ch,
    // JTAG: «волшебные» имена, в .cst их нет (см. jprobe.v)
    input wire tck_pad_i, tms_pad_i, tdi_pad_i,
    output wire tdo_pad_o
);
    localparam H = 10, DEPTH = 1 << DEPTH_LOG2;
    localparam [7:0] VER = 1, DL8 = DEPTH_LOG2, WL8 = WIN_LOG2;

    wire clk;
    OSCB #(.FREQ_MODE("210"), .FREQ_DIV(4), .DYN_TRIM_EN("FALSE")) osc (
        .OSCOUT(clk), .OSCREF(), .OSCEN(1'b1), .FMODE(1'b1),
        .RTRIM(8'd0), .RTCTRIM(6'd0));

    wire [4:0] l = {ch[11:8], ch[12]};
    reg [4:0] s1 = 0, s2 = 0, s3 = 0;
    always @(posedge clk) {s3, s2, s1} <= {s2, s1, l};

    // ---- команда из JTAG-домена ----
    reg [31:0] cmd = 0;
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
            run <= 1;
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

    // ---- пользовательский JTAG ----
    wire tck, tdi, sh_cap, upd, en1, en2;
    reg [19:0] idx = 0;
    reg [31:0] sr = 0;
    wire [14:0] w = idx[19:5];
    wire [4:0] bi = idx[4:0];
    wire [19:0] idx1 = idx + 1'b1;
    wire [15:0] ra = cmd[15:0] + idx1[19:5] - H;
    reg [31:0] q = 0;
    always @(posedge tck) q <= mem[ra[DEPTH_LOG2-1:0]];

    reg [31:0] hw;
    always @* begin
        case (w)
            0: hw = 32'h414E4C52;
            1: hw = {seq, WL8, DL8, VER};
            2: hw = cmd;
            3: hw = {full, run, mode, {(27 - DEPTH_LOG2){1'b0}}, wptr};
            4: hw = miss;
            5: hw = {seq, fcnt[0 +: 24]};
            6: hw = {seq, fcnt[24 +: 24]};
            7: hw = {seq, fcnt[48 +: 24]};
            8: hw = {seq, fcnt[72 +: 24]};
            9: hw = {seq, fcnt[96 +: 24]};
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

    always @(posedge tck) begin
        idx <= en1 & sh_cap ? idx + 1'b1 : 20'd0;
        if (en2 & sh_cap)
            sr <= {tdi, sr[31:1]};
        if (en2 & upd & sr[31:28] == 4'hA) begin
            cmd <= sr;
            if (sr[27])
                arm_t <= ~arm_t;
        end
    end
endmodule
