// Где на SLogic16U3 генератор 125 МГц: SerDes Q0 GW5AT-15 по CSR из serdes.toml (QPLL1 5 ГГц от
// 125 МГц, линия 0 на 5 Гбит/с, ширина 20, шестерня 1:2), наружу — детекторы REFCLK, CMU_OK и такты
// квада. Частоты считаются в домене каждого такта и через код Грея переносятся в OSCB. JTAG — как в
// uprobe.v.
//
// serdes.v — Serdes_Top из GowinModGen (serdes.mod) с добавленным выходом probe_o:
//   [0..3] REFCLK_DET CM0..CM3, [4] CMU_OK (QPLL0), [5] CMU1_OK (QPLL1), [6] PMA_RX_LOCK линии 0,
//   [7] CMU_CK_REF, [8] CMU1_CK_REF, [9] CM_LIFE_CLK, [10] CM1_LIFE_CLK, [11] PCS_TX линии 0,
//   [12] PCS_RX линии 0, [13] LANE0_CMU_CK_REF, [14] QUAD_CLK_RX, [15] CMU0_CLK, [16] CMU1_CLK.
// USB3_0_PHY_Top — заглушка из sdlib.v: сброс линии и такты FIFO.
//
// ER2 (0x43): [31:28] 0xA, [0] держать линию в сбросе.
// ER1 (0x42): 0 "RLNS", 1 [7:0] версия, [23:16] WIN_LOG2, [31:24] seq, 2 команда,
//   3 [6:0] флаги сейчас, [14:8] был 1 за окно, [22:16] был 0 за окно,
//   4..13 тактов probe_o[7..16] за окно 2^WIN_LOG2 тактов OSCB.
module top #(
    parameter WIN_LOG2 = 24
) (
    input wire tck_pad_i, tms_pad_i, tdi_pad_i,
    output wire tdo_pad_o
);
    localparam NC = 10;
    localparam [7:0] VER = 1, WL8 = WIN_LOG2;

    wire clk;
    OSCB #(.FREQ_MODE("210"), .FREQ_DIV(4), .DYN_TRIM_EN("FALSE")) osc (
        .OSCOUT(clk), .OSCREF(), .OSCEN(1'b1), .FMODE(1'b1),
        .RTRIM(8'd0), .RTCTRIM(6'd0));

    reg [31:0] cmd = 0;
    reg [19:0] por = 0;  // сброс линии первые ~35 мс после загрузки
    always @(posedge clk) if (~&por) por <= por + 1'b1;
    wire rstn = &por & ~cmd[0];

    wire [16:0] pr;
    Serdes_Top sd (
        .probe_o(pr),
        .USB3_0_PHY_Top_pclk(), .USB3_0_PHY_Top_PipeRxData(), .USB3_0_PHY_Top_PipeRxDataK(),
        .USB3_0_PHY_Top_PipeRxDataValid(), .USB3_0_PHY_Top_RxElecIdle(), .USB3_0_PHY_Top_RxStatus(),
        .USB3_0_PHY_Top_PhyStatus(), .USB3_0_PHY_Top_PowerPresent(),
        .USB3_0_PHY_Top_ref_clk(clk), .USB3_0_PHY_Top_phy_resetn(rstn),
        .USB3_0_PHY_Top_PipeTxData(32'd0), .USB3_0_PHY_Top_PipeTxDataK(4'd0),
        .USB3_0_PHY_Top_TxDetectRx_loopback(1'b0), .USB3_0_PHY_Top_TxElecIdle(1'b1),
        .USB3_0_PHY_Top_RxPolarity(1'b0), .USB3_0_PHY_Top_RxEqTraining(1'b0),
        .USB3_0_PHY_Top_RxTermination(1'b0), .USB3_0_PHY_Top_TxOnesZeros(1'b0),
        .USB3_0_PHY_Top_PowerDown(2'd0), .USB3_0_PHY_Top_ElasticityBufferMode(1'b0));

    // ---- окно ----
    reg [WIN_LOG2-1:0] tmr = 0;
    reg [7:0] seq = 0;
    always @(posedge clk) begin
        tmr <= tmr + 1'b1;
        if (&tmr) seq <= seq + 1'b1;
    end

    reg [6:0] f1 = 0, f2 = 0, w1 = 0, w0 = 0, fw1 = 0, fw0 = 0;
    always @(posedge clk) begin
        {f2, f1} <= {f1, pr[6:0]};
        if (&tmr) begin
            fw1 <= w1 | f2; fw0 <= w0 | ~f2; w1 <= 0; w0 <= 0;
        end else begin
            w1 <= w1 | f2; w0 <= w0 | ~f2;
        end
    end

    // ---- частотомеры ----
    wire [32*NC-1:0] cnt;
    genvar g;
    generate
        for (g = 0; g < NC; g = g + 1) begin : fm
            fmeter m (.fclk(pr[7 + g]), .clk(clk), .tick(&tmr), .cnt(cnt[32 * g +: 32]));
        end
    endgenerate

    // ---- пользовательский JTAG ----
    wire tck, tdi, sh_cap, upd, en1, en2;
    reg [19:0] idx = 0;
    reg [31:0] sr = 0;
    wire [14:0] w = idx[19:5];
    wire [4:0] bi = idx[4:0];
    reg [31:0] hw;
    always @* begin
        case (w)
            0: hw = 32'h534E4C52;
            1: hw = {seq, WL8, 8'd0, VER};
            2: hw = cmd;
            3: hw = {9'd0, fw0, 1'b0, fw1, 1'b0, f2};
            4, 5, 6, 7, 8, 9, 10, 11, 12, 13: hw = cnt[32 * (w - 4) +: 32];
            default: hw = 0;
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
        if (en2_q & upd_q & (sr[31:28] == 4'hA))
            cmd <= sr;
    end
endmodule
