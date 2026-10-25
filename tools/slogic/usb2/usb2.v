// USB2 HS на SLogic16U3, шаг 1: перечисление и поток на хост. Gowin USB 2.0 SoftPHY (Single LVDS,
// выводы найдены образом uprobe) + USB 2.0 Device Controller, оба — нетлистами из ip/.
//
// Такт: генератор 125 МГц на REFCLK SerDes Q0 → CM1_LIFE_CLK 62,5 МГц (образ sdprobe) →
// PLL 62,5 × 16 / 25 = 40 МГц → PLL 40 × 24 = 960 МГц: /2 = 480 МГц (fclk SoftPHY), /16 = 60 МГц.
//
// EP1 IN (bulk): счётчик 32-битных слов, младший байт первым. Пакет повторяется с того же слова,
// пока контроллер не отчитался txpktfin — так хост видит разрыв счётчика только при потере.
// EP1 OUT (bulk): принимается всё, считаются байты.
//
// ER2 (0x43): [31:28] 0xA, [0] не отдавать данные (cork), [1] держать контроллер в сбросе,
//   [2] смена значения — журнал пакетов заново, [3] писать в журнал и SOF; [31:28] 0xB, [15:0] — адрес чтения журнала (слово).
// ER1 (0x42): 0 "RLNB", 1 [7:0] версия, [31:24] seq окна, 2 команда,
//   3 [0] PLL1, [1] PLL2, [2] сброс, [3] highspeed, [4] online, [5] suspend, [7:6] linestate,
//     [11:8] последняя активная точка
//   4 сбросов шины  5 SOF  6 SETUP  7 IN-транзакций EP1  8 txpktfin EP1  9 байт отдано EP1
//   10 байт принято EP1  11 rxpktval  12 тактов 60 МГц за окно  13 тактов 62,5 МГц за окно
//   14..22 тактов с dbg_*: rx_nak tx_nak tx_zlp rx_failed tx_failed token_failed token_valid
//     addr_mismatch endpt_val  23 [12:0] записей журнала, [31] журнал полон
//   24.. журнал с адреса чтения: на пакет UTMI два слова — {[31] передача, [30] rxerror,
//     [25:16] байт, [15:8] PID, [7:0] второй байт}, затем такт 60 МГц конца пакета
module top (
    inout wire usb_dxp_io, usb_dxn_io,
    input wire usb_rxdp_i, usb_rxdn_i,
    output wire usb_pullup_en_o,
    inout wire usb_term_dp_io, usb_term_dn_io,
    input wire tck_pad_i, tms_pad_i, tdi_pad_i,
    output wire tdo_pad_o
);
    localparam [7:0] VER = 3;
    localparam H = 24, LOG2 = 12;  // журнал: 4К пакетов
    localparam WIN_LOG2 = 24;

    wire osc;
    OSCB #(.FREQ_MODE("210"), .FREQ_DIV(4), .DYN_TRIM_EN("FALSE")) oscb (
        .OSCOUT(osc), .OSCREF(), .OSCEN(1'b1), .FMODE(1'b1),
        .RTRIM(8'd0), .RTCTRIM(6'd0));

    reg [31:0] cmd = 0;

    // ---- такты ----
    reg [19:0] por = 0;  // линия SerDes в сбросе первые ~35 мс
    always @(posedge osc) if (~&por) por <= por + 1'b1;
    wire [16:0] pr;
    Serdes_Top sd (
        .probe_o(pr),
        .USB3_0_PHY_Top_pclk(), .USB3_0_PHY_Top_PipeRxData(), .USB3_0_PHY_Top_PipeRxDataK(),
        .USB3_0_PHY_Top_PipeRxDataValid(), .USB3_0_PHY_Top_RxElecIdle(), .USB3_0_PHY_Top_RxStatus(),
        .USB3_0_PHY_Top_PhyStatus(), .USB3_0_PHY_Top_PowerPresent(),
        .USB3_0_PHY_Top_ref_clk(osc), .USB3_0_PHY_Top_phy_resetn(&por),
        .USB3_0_PHY_Top_PipeTxData(32'd0), .USB3_0_PHY_Top_PipeTxDataK(4'd0),
        .USB3_0_PHY_Top_TxDetectRx_loopback(1'b0), .USB3_0_PHY_Top_TxElecIdle(1'b1),
        .USB3_0_PHY_Top_RxPolarity(1'b0), .USB3_0_PHY_Top_RxEqTraining(1'b0),
        .USB3_0_PHY_Top_RxTermination(1'b0), .USB3_0_PHY_Top_TxOnesZeros(1'b0),
        .USB3_0_PHY_Top_PowerDown(2'd0), .USB3_0_PHY_Top_ElasticityBufferMode(1'b0));
    wire refclk62 = pr[10];  // CM1_LIFE_CLK

    wire clk40, lock1, fclk480, clk60, lock2;
    pll_40m p1 (.clkin(refclk62), .clkout0(clk40), .lock(lock1));
    pll_usb p2 (.clkin(clk40), .clkout0(fclk480), .clkout1(clk60), .lock(lock2));

    // сброс в домене 60 МГц: после захвата PLL2 и по команде
    reg [2:0] ls = 0;
    reg [7:0] rcnt = 0;
    always @(posedge clk60) begin
        ls <= {ls[1:0], lock2 & ~cmd[1]};
        if (~ls[2]) rcnt <= 0;
        else if (~&rcnt) rcnt <= rcnt + 1'b1;
    end
    wire rst = ~&rcnt;

    // ---- USB ----
    wire [7:0] phy_dout, phy_din;
    wire phy_txvalid, phy_txready, phy_rxvalid, phy_rxactive, phy_rxerror, phy_termsel;
    wire [1:0] phy_linestate, phy_opmode, phy_xcvrsel;

    wire usbrst, highspeed, suspend, online;
    wire [7:0] txdat, rxdat;
    wire [11:0] txlen;
    wire txcork, txpop, txact, txpktfin, rxval, rxact, rxpktval, setup, sof;
    wire [3:0] endpt;
    wire [8:0] dbg;

    wire [15:0] d_raddr;
    wire [7:0] d_rdata;
    wire [15:0] d_dev_a, d_dev_l, d_qual_a, d_qual_l, d_fs_a, d_fs_l, d_hs_a, d_hs_l, d_os_a,
        d_lang_a, d_ven_a, d_ven_l, d_prod_a, d_prod_l, d_ser_a, d_ser_l;
    usb_desc desc (
        .raddr(d_raddr), .rdata(d_rdata),
        .dev_addr(d_dev_a), .dev_len(d_dev_l), .qual_addr(d_qual_a), .qual_len(d_qual_l),
        .fscfg_addr(d_fs_a), .fscfg_len(d_fs_l), .hscfg_addr(d_hs_a), .hscfg_len(d_hs_l),
        .oscfg_addr(d_os_a), .strlang_addr(d_lang_a),
        .strvendor_addr(d_ven_a), .strvendor_len(d_ven_l),
        .strproduct_addr(d_prod_a), .strproduct_len(d_prod_l),
        .strserial_addr(d_ser_a), .strserial_len(d_ser_l));

    USB_Device_Controller_Top ctl (
        .clk_i(clk60), .reset_i(rst),
        .usbrst_o(usbrst), .highspeed_o(highspeed), .suspend_o(suspend), .online_o(online),
        .txdat_i(txdat), .txval_i(1'b0), .txdat_len_i(txlen), .txiso_pid_i(4'd0),
        .txcork_i(txcork), .txpop_o(txpop), .txact_o(txact), .txpktfin_o(txpktfin),
        .rxdat_o(rxdat), .rxval_o(rxval), .rxrdy_i(1'b1), .rxact_o(rxact), .rxpktval_o(rxpktval),
        .setup_o(setup), .endpt_o(endpt), .sof_o(sof),
        .dbg_rx_nak_o(dbg[0]), .dbg_tx_nak_o(dbg[1]), .dbg_tx_zlp_o(dbg[2]), .dbg_rx_failed_o(dbg[3]),
        .dbg_tx_failed_o(dbg[4]), .dbg_token_failed_o(dbg[5]), .dbg_token_valid_o(dbg[6]),
        .dbg_addr_mismatch_o(dbg[7]), .dbg_endpt_val_o(dbg[8]),
        .inf_alter_i(8'd0), .inf_alter_o(), .inf_sel_o(), .inf_set_o(),
        .descrom_raddr_o(d_raddr), .desc_index_o(), .desc_type_o(), .descrom_rdata_i(d_rdata),
        .desc_dev_addr_i(d_dev_a), .desc_dev_len_i(d_dev_l),
        .desc_qual_addr_i(d_qual_a), .desc_qual_len_i(d_qual_l),
        .desc_fscfg_addr_i(d_fs_a), .desc_fscfg_len_i(d_fs_l),
        .desc_hscfg_addr_i(d_hs_a), .desc_hscfg_len_i(d_hs_l),
        .desc_oscfg_addr_i(d_os_a),
        .desc_hidrpt_addr_i(16'd0), .desc_hidrpt_len_i(16'd0),
        .desc_bos_addr_i(16'd0), .desc_bos_len_i(16'd0),
        .desc_strlang_addr_i(d_lang_a),
        .desc_strvendor_addr_i(d_ven_a), .desc_strvendor_len_i(d_ven_l),
        .desc_strproduct_addr_i(d_prod_a), .desc_strproduct_len_i(d_prod_l),
        .desc_strserial_addr_i(d_ser_a), .desc_strserial_len_i(d_ser_l),
        .desc_have_strings_i(1'b1),
        .utmi_dataout_o(phy_dout), .utmi_txvalid_o(phy_txvalid), .utmi_txready_i(phy_txready),
        .utmi_datain_i(phy_din), .utmi_rxactive_i(phy_rxactive), .utmi_rxvalid_i(phy_rxvalid),
        .utmi_rxerror_i(phy_rxerror), .utmi_linestate_i(phy_linestate),
        .utmi_opmode_o(phy_opmode), .utmi_xcvrselect_o(phy_xcvrsel),
        .utmi_termselect_o(phy_termsel), .utmi_reset_o());

    USB2_0_SoftPHY_Top phy (
        .clk_i(clk60), .rst_i(rst), .fclk_i(fclk480), .pll_locked_i(lock2),
        .utmi_data_out_i(phy_dout), .utmi_txvalid_i(phy_txvalid), .utmi_op_mode_i(phy_opmode),
        .utmi_xcvrselect_i(phy_xcvrsel), .utmi_termselect_i(phy_termsel),
        .utmi_data_in_o(phy_din), .utmi_txready_o(phy_txready), .utmi_rxvalid_o(phy_rxvalid),
        .utmi_rxactive_o(phy_rxactive), .utmi_rxerror_o(phy_rxerror),
        .utmi_linestate_o(phy_linestate),
        .usb_dxp_io(usb_dxp_io), .usb_dxn_io(usb_dxn_io),
        .usb_rxdp_i(usb_rxdp_i), .usb_rxdn_i(usb_rxdn_i),
        .usb_pullup_en_o(usb_pullup_en_o),
        .usb_term_dp_io(usb_term_dp_io), .usb_term_dn_io(usb_term_dn_io));

    // ---- EP1 IN: счётчик слов ----
    wire ep1 = endpt == 4'd1;
    reg [31:0] word = 0, pkt_word = 0;
    reg [1:0] bsel = 0;
    reg txact_q = 0;
    assign txdat = word[8 * bsel +: 8];
    assign txlen = highspeed ? 12'd512 : 12'd64;
    // cork действует и на EP0: там ответы на стандартные запросы (дескрипторы) — не задерживать
    assign txcork = endpt == 4'd0 ? 1'b0 : ep1 ? cmd[0] : 1'b1;
    always @(posedge clk60) begin
        txact_q <= txact;
        if (rst | usbrst) begin
            word <= 0;
            pkt_word <= 0;
            bsel <= 0;
        end else if (ep1 & txact & ~txact_q) begin
            word <= pkt_word;  // начало IN-транзакции: пакет с начала
            bsel <= 0;
        end else if (ep1 & txpop) begin
            bsel <= bsel + 1'b1;
            if (&bsel)
                word <= word + 1'b1;
        end else if (ep1 & txpktfin)
            pkt_word <= word;
    end

    // ---- счётчики ----
    reg [31:0] n_rst = 0, n_sof = 0, n_setup = 0, n_in = 0, n_fin = 0, n_txb = 0, n_rxb = 0, n_rxpkt = 0;
    reg setup_q = 0, usbrst_q = 0;
    reg [3:0] last_ep = 0;
    always @(posedge clk60) begin
        setup_q <= setup;
        usbrst_q <= usbrst;
        if (usbrst & ~usbrst_q) n_rst <= n_rst + 1'b1;
        if (sof) n_sof <= n_sof + 1'b1;
        if (setup & ~setup_q) n_setup <= n_setup + 1'b1;
        if (ep1 & txact & ~txact_q) n_in <= n_in + 1'b1;
        if (ep1 & txpktfin) n_fin <= n_fin + 1'b1;
        if (ep1 & txpop) n_txb <= n_txb + 1'b1;
        if (ep1 & rxval) n_rxb <= n_rxb + 1'b1;
        if (rxpktval) n_rxpkt <= n_rxpkt + 1'b1;
        if (txact | rxact) last_ep <= endpt;
    end

    reg [32*9-1:0] n_dbg = 0;
    integer k;
    always @(posedge clk60)
        for (k = 0; k < 9; k = k + 1)
            if (dbg[k]) n_dbg[32 * k +: 32] <= n_dbg[32 * k +: 32] + 1'b1;

    // ---- журнал пакетов UTMI ----
    reg [31:0] ts = 0;
    reg [LOG2:0] lptr = 0;
    reg [2:0] larm = 0;
    reg rxa_q = 0, txv_q = 0, rx_err = 0;
    reg [9:0] rx_len = 0, tx_len = 0;
    reg [7:0] rx_pid = 0, rx_b1 = 0, tx_pid = 0, tx_b1 = 0;
    reg [31:0] loga [0:(1 << LOG2) - 1];
    reg [31:0] logb [0:(1 << LOG2) - 1];
    reg lwe = 0;
    reg [31:0] lwa = 0;
    always @(posedge clk60) begin
        ts <= ts + 1'b1;
        larm <= {larm[1:0], cmd[2]};
        rxa_q <= phy_rxactive;
        txv_q <= phy_txvalid;
        lwe <= 0;
        if (phy_rxactive & ~rxa_q) begin
            rx_len <= 0;
            rx_err <= 0;
        end else if (phy_rxactive) begin
            if (phy_rxvalid) begin
                if (rx_len == 0) rx_pid <= phy_din;
                if (rx_len == 1) rx_b1 <= phy_din;
                if (~&rx_len) rx_len <= rx_len + 1'b1;
            end
            if (phy_rxerror) rx_err <= 1;
        end
        if (phy_txvalid & ~txv_q)
            tx_len <= 0;
        if (phy_txvalid & phy_txready) begin
            if (tx_len == 0) tx_pid <= phy_dout;
            if (tx_len == 1) tx_b1 <= phy_dout;
            if (~&tx_len) tx_len <= tx_len + 1'b1;
        end
        if (~phy_rxactive & rxa_q) begin
            lwe <= rx_pid != 8'hA5 | cmd[3];
            lwa <= {1'b0, rx_err, 4'd0, rx_len, rx_pid, rx_b1};
        end else if (~phy_txvalid & txv_q) begin
            lwe <= 1;
            lwa <= {1'b1, 1'b0, 4'd0, tx_len, tx_pid, tx_b1};
        end
        if (larm[2] ^ larm[1])
            lptr <= 0;
        else if (lwe & ~lptr[LOG2]) begin
            loga[lptr[LOG2-1:0]] <= lwa;
            logb[lptr[LOG2-1:0]] <= ts;
            lptr <= lptr + 1'b1;
        end
    end

    // ---- окно и частотомеры ----
    reg [WIN_LOG2-1:0] tmr = 0;
    reg [7:0] seq = 0;
    always @(posedge osc) begin
        tmr <= tmr + 1'b1;
        if (&tmr) seq <= seq + 1'b1;
    end
    wire [31:0] f60, f62;
    fmeter m60 (.fclk(clk60), .clk(osc), .tick(&tmr), .cnt(f60));
    fmeter m62 (.fclk(refclk62), .clk(osc), .tick(&tmr), .cnt(f62));

    // ---- пользовательский JTAG ----
    wire tck, tdi, sh_cap, upd, en1, en2;
    reg [19:0] idx = 0;
    reg [31:0] sr = 0, raddr = 0;
    wire [14:0] w = idx[19:5];
    wire [4:0] bi = idx[4:0];
    wire [19:0] idx1 = idx + 1'b1;
    wire [15:0] ra = raddr[15:0] + idx1[19:5] - H;
    reg [31:0] qa = 0, qb = 0;
    reg qsel = 0;
    always @(negedge tck) begin
        qa <= loga[ra[LOG2:1]];
        qb <= logb[ra[LOG2:1]];
        qsel <= ra[0];
    end
    reg [31:0] hw;
    always @* begin
        case (w)
            0: hw = 32'h424E4C52;
            1: hw = {seq, 16'd0, VER};
            2: hw = cmd;
            3: hw = {20'd0, last_ep, phy_linestate, suspend, online, highspeed, rst, lock2, lock1};
            4: hw = n_rst;
            5: hw = n_sof;
            6: hw = n_setup;
            7: hw = n_in;
            8: hw = n_fin;
            9: hw = n_txb;
            10: hw = n_rxb;
            11: hw = n_rxpkt;
            12: hw = f60;
            13: hw = f62;
            14, 15, 16, 17, 18, 19, 20, 21, 22: hw = n_dbg[32 * (w - 14) +: 32];
            23: hw = {lptr[LOG2], {(30 - LOG2){1'b0}}, lptr};
            default: hw = qsel ? qb : qa;
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
        if (en2_q & upd_q & (sr[31:28] == 4'hB))
            raddr <= sr;
    end
endmodule
