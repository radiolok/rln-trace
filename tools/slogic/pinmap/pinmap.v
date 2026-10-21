// Прозвонка выводов SLogic16U3 (GW5AT-15, CS130). Все свободные выводы
// ПЛИС — только входы; за окно ~5 с на каждом считаются фронты, затем отчёт
// пишется страницей в SPI-флеш по 0x7F0000. Наружу идут лишь линии MSPI к
// флеш. Читает отчёт pinmap.py в режиме DFU.
//
// Порядок: пауза ~0,6 с → окно 2^28 тактов → выход флеш из continuous read
// и сброс → JEDEC ID (не 0b4018 — ничего не пишем) → стирание сектора 4 КиБ →
// запись 256 байт.
//
// Слово вывода i (little endian, со смещения 16 + 4i):
//   [31] был 1, [30] был 0, [29] уровень в конце окна, [28:0] фронтов.
module top #(
    parameter NP = 40,
    parameter WIN_LOG2 = 28,  // окно 2^28 тактов ≈ 5,1 с
    parameter POR_LOG2 = 25   // пауза после загрузки ≈ 0,64 с
) (
    input  wire [NP-1:0] p,
    output reg           f_cs_n = 1'b1,
    output reg           f_sck = 1'b0,
    output reg           f_mosi = 1'b1,
    input  wire          f_miso
);
    localparam [23:0] ADDR = 24'h7F0000;
    localparam [23:0] JEDEC = 24'h0B4018;

    // 210 МГц / 4 = 52,5 МГц, точность внутреннего генератора — единицы процентов
    wire clk;
    OSCB #(.FREQ_MODE("210"), .FREQ_DIV(4), .DYN_TRIM_EN("FALSE")) osc (
        .OSCOUT(clk), .OSCREF(), .OSCEN(1'b1), .FMODE(1'b1),
        .RTRIM(8'd0), .RTCTRIM(6'd0));

    // ---- счёт фронтов ----
    reg [NP-1:0] s1 = 0, s2 = 0, s3 = 0;
    reg [NP-1:0] seen0 = 0, seen1 = 0, last = 0;
    reg [28:0] cnt [0:NP-1];
    reg meas = 1'b0;

    always @(posedge clk) {s3, s2, s1} <= {s2, s1, p};

    genvar g;
    generate for (g = 0; g < NP; g = g + 1) begin : ch
        initial cnt[g] = 0;
        always @(posedge clk)
            if (meas && s2[g] ^ s3[g] && ~&cnt[g]) cnt[g] <= cnt[g] + 1'b1;
    end endgenerate

    always @(posedge clk) if (meas) begin
        seen1 <= seen1 | s2;
        seen0 <= seen0 | ~s2;
        last <= s2;
    end

    // ---- автомат и страница отчёта ----
    localparam T_EXIT = 0, T_RSTEN = 1, T_RST = 2, T_JEDEC = 3, T_WREN1 = 4,
               T_ERASE = 5, T_POLL1 = 6, T_WREN2 = 7, T_PROG = 8, T_POLL2 = 9;
    localparam S_POR = 0, S_MEAS = 1, S_START = 2, S_BIT = 3, S_END = 4,
               S_NEXT = 5, S_DELAY = 6, S_DONE = 7, S_FAIL = 8;

    reg [3:0] st = S_POR;
    reg [3:0] txn = T_EXIT;
    reg [31:0] tmr = 0;
    reg [8:0] bi = 0;
    reg [2:0] bitn = 0, ph = 0;
    reg [7:0] sh = 0, rx = 0;
    reg [1:0] miso_s = 0;

    reg [23:0] jid = 0;
    reg [7:0] pb;
    wire [8:0] pi = bi - 9'd4;
    wire [6:0] wi = pi[7:2] - 6'd4;
    wire [31:0] word = {seen1[wi], seen0[wi], last[wi], cnt[wi]};
    always @* begin
        pb = 8'hFF;
        if (pi < 16) case (pi[3:0])
            0: pb = "R"; 1: pb = "L"; 2: pb = "N"; 3: pb = "P";
            4: pb = 8'd1;                       // версия
            5: pb = NP;
            6: pb = jid[23:16]; 7: pb = jid[15:8]; 8: pb = jid[7:0];
            9: pb = WIN_LOG2;
            default: pb = 8'h00;
        endcase
        else if (pi < 16 + 4 * NP) pb = word[8 * pi[1:0] +: 8];
    end

    // ---- SPI к флеш, режим 0, SCK = clk/8 ----
    always @(posedge clk) miso_s <= {miso_s[0], f_miso};

    reg [8:0] len;
    reg [7:0] txb;
    always @* begin
        case (txn)
            T_EXIT:  len = 4;
            T_JEDEC, T_ERASE: len = 4;
            T_POLL1, T_POLL2: len = 2;
            T_PROG:  len = 260;
            default: len = 1;
        endcase
        txb = 8'h00;
        case (txn)
            T_EXIT:  txb = 8'hFF;
            T_RSTEN: txb = 8'h66;
            T_RST:   txb = 8'h99;
            T_JEDEC: txb = bi == 0 ? 8'h9F : 8'h00;
            T_WREN1, T_WREN2: txb = 8'h06;
            T_POLL1, T_POLL2: txb = bi == 0 ? 8'h05 : 8'h00;
            T_ERASE, T_PROG: case (bi)
                0: txb = txn == T_ERASE ? 8'h20 : 8'h02;
                1: txb = ADDR[23:16];
                2: txb = ADDR[15:8];
                3: txb = ADDR[7:0];
                default: txb = pb;
            endcase
            default: txb = 8'h00;
        endcase
    end

    always @(posedge clk) begin
        tmr <= tmr + 1'b1;
        case (st)
        S_POR: if (tmr[POR_LOG2]) begin tmr <= 0; meas <= 1'b1; st <= S_MEAS; end
        S_MEAS: if (tmr[WIN_LOG2]) begin meas <= 1'b0; txn <= T_EXIT; tmr <= 0; st <= S_START; end
        S_START: begin
            f_cs_n <= 1'b0;
            if (tmr[2]) begin bi <= 0; bitn <= 0; ph <= 0; st <= S_BIT; end
        end
        S_BIT: begin
            ph <= ph + 1'b1;
            if (ph == 0) begin
                if (bitn == 0) begin f_mosi <= txb[7]; sh <= {txb[6:0], 1'b0}; end
                else begin f_mosi <= sh[7]; sh <= {sh[6:0], 1'b0}; end
            end
            if (ph == 4) f_sck <= 1'b1;
            if (ph == 7) begin
                f_sck <= 1'b0;
                rx <= {rx[6:0], miso_s[1]};
                bitn <= bitn + 1'b1;
                if (bitn == 7) begin
                    if (txn == T_JEDEC) jid <= {jid[15:0], rx[6:0], miso_s[1]};
                    if (bi == len - 1) begin tmr <= 0; st <= S_END; end
                    else bi <= bi + 1'b1;
                end
            end
        end
        S_END: begin
            f_cs_n <= 1'b1;
            f_mosi <= 1'b1;
            if (tmr[4]) st <= S_NEXT;
        end
        S_NEXT: begin
            tmr <= 0;
            st <= S_START;
            case (txn)
                T_EXIT:  txn <= T_RSTEN;
                T_RSTEN: txn <= T_RST;
                T_RST:   begin txn <= T_JEDEC; st <= S_DELAY; end
                T_JEDEC: if (jid == JEDEC) txn <= T_WREN1; else st <= S_FAIL;
                T_WREN1: txn <= T_ERASE;
                T_ERASE: txn <= T_POLL1;
                T_POLL1: if (!rx[0]) txn <= T_WREN2;
                T_WREN2: txn <= T_PROG;
                T_PROG:  txn <= T_POLL2;
                T_POLL2: if (rx[0]) txn <= T_POLL2; else st <= S_DONE;
                default: st <= S_FAIL;
            endcase
        end
        S_DELAY: if (tmr[16]) begin tmr <= 0; st <= S_START; end  // ~1,2 мс после сброса флеш
        default: ;  // S_DONE, S_FAIL: CS высокий, флеш больше не трогаем
        endcase
    end
endmodule
