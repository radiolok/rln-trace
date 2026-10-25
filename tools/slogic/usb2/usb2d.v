// USB2 HS на SLogic16U3, открытый стек: USB2-ядро Daisho (daisho/, BSD-2) поверх Gowin USB 2.0
// SoftPHY через свой слой UTMI (usb2_utmi.v вместо ULPI). Такты, SerDes, выводы и JTAG — как в
// usb2.v (там же — почему такт с tx_pcs_clkout и fclk 960 МГц).
//
// EP1 IN (bulk): счётчик 32-битных слов, младший байт первым; пакет пишется в двойной буфер Daisho
// и освобождается только по ACK хоста — разрыв счётчика у хоста = потеря.
// EP2 OUT (bulk): принимается всё, считаются пакеты и байты.
//
// ER2 (0x43): [31:28] 0xA, [0] не отдавать данные EP1 (cork), [1] отключиться от шины (снять
//   подтяжку), [2] смена значения — журнал заново, [3] писать в журнал и SOF, [5:4] данные EP1 IN:
//   0 счётчик, 1 байты 0x00, 2 0xFF, 3 0x7E, [6] не писать в журнал события шины, [7] только FS,
//   [15:8] длина пакета EP1 IN в словах (0 — 512 байт в HS, 64 в FS; больше 128 — 128),
//   [16] HS вслепую (не ждать чирпов хоста);
//   [31:28] 0xB, [15:0] — адрес чтения журнала (слово).
// ER1 (0x42): 0 "RLND", 1 [7:0] версия, [31:24] seq окна, 2 команда,
//   3 [0] PLL1, [1] PLL2, [2] сброс, [3] HS, [4] configured, [5] suspend, [7:6] linestate,
//     [11:8] состояние шины (usb2_utmi), [14:12] чирпов хоста, [16:15] opmode, [18:17] xcvrselect,
//     [19] termselect
//   4 сбросов шины  5 SOF  6 vendor-запросов  7 пакетов EP1 IN записано  8 байт EP1 IN записано
//   9 пакетов EP2 OUT  10 байт EP2 OUT  11 err_crc_pid  12 тактов 60 МГц за окно
//   13 тактов 125 МГц за окно  14 err_crc_tok  15 err_crc_pkt  16 err_pid_out_of_seq
//   17 err_setup_pkt (14..17 — фронтов)  18 [10:0] номер кадра  19 [7:0] последний vendor-запрос,
//   [31:16] его wValue  20..22 0  23 [12:0] записей журнала, [31] журнал полон
//   24.. журнал с адреса чтения, по два слова на запись, второе — такт 60 МГц:
//     пакет UTMI {[31] передача, [30] rxerror, [29] 0, [25:16] байт, [15:8] PID, [7:0] второй байт};
//     событие шины {[29] 1, [15:12] состояние, [11:10] linestate, [9:8] opmode, [7:6] xcvrselect,
//     [5] termselect, [2:0] чирпов} — смена состояния, а вне FS/HS — и смена linestate
module top (
    inout wire usb_dxp_io, usb_dxn_io,
    input wire usb_rxdp_i, usb_rxdn_i,
    output wire usb_pullup_en_o,
    output wire xo_en_o,  // D14: разрешение генератора 125 МГц
    inout wire usb_term_dp_io, usb_term_dn_io,
    input wire tck_pad_i, tms_pad_i, tdi_pad_i,
    output wire tdo_pad_o
);
    localparam [7:0] VER = 1;
    localparam H = 24, LOG2 = 12;  // журнал: 4К записей
    localparam WIN_LOG2 = 24;

    assign xo_en_o = 1'b1;

    wire osc;
    OSCB #(.FREQ_MODE("210"), .FREQ_DIV(4), .DYN_TRIM_EN("FALSE")) oscb (
        .OSCOUT(osc), .OSCREF(), .OSCEN(1'b1), .FMODE(1'b1),
        .RTRIM(8'd0), .RTCTRIM(6'd0));

    reg [31:0] cmd = 0;

    // ---- такты (как в usb2.v) ----
    reg [21:0] sdseq = 0;
    always @(posedge osc) if (~sdseq[21]) sdseq <= sdseq + 1'b1;
    wire pma_rstn = sdseq[20], pll_rst = ~sdseq[21];
    wire sd_rxclk, sd_txclk;
    SerDes_Top sd (
        .Customized_PHY_Top_q0_ln0_rx_pcs_clkout_o(sd_rxclk),
        .Customized_PHY_Top_q0_ln0_rx_data_o(), .Customized_PHY_Top_q0_ln0_rx_fifo_rdusewd_o(),
        .Customized_PHY_Top_q0_ln0_rx_fifo_aempty_o(), .Customized_PHY_Top_q0_ln0_rx_fifo_empty_o(),
        .Customized_PHY_Top_q0_ln0_rx_valid_o(),
        .Customized_PHY_Top_q0_ln0_tx_pcs_clkout_o(sd_txclk),
        .Customized_PHY_Top_q0_ln0_tx_fifo_wrusewd_o(), .Customized_PHY_Top_q0_ln0_tx_fifo_afull_o(),
        .Customized_PHY_Top_q0_ln0_tx_fifo_full_o(),
        .Customized_PHY_Top_q0_ln0_refclk_o(), .Customized_PHY_Top_q0_ln0_signal_detect_o(),
        .Customized_PHY_Top_q0_ln0_rx_cdr_lock_o(), .Customized_PHY_Top_q0_ln0_pll_lock_o(),
        .Customized_PHY_Top_q0_ln0_ready_o(),
        .Customized_PHY_Top_q0_ln0_rx_clk_i(sd_rxclk), .Customized_PHY_Top_q0_ln0_rx_fifo_rden_i(1'b0),
        .Customized_PHY_Top_q0_ln0_tx_clk_i(sd_txclk), .Customized_PHY_Top_q0_ln0_tx_data_i(80'd0),
        .Customized_PHY_Top_q0_ln0_tx_fifo_wren_i(1'b0),
        .Customized_PHY_Top_q0_ln0_pma_rstn_i(pma_rstn),
        .Customized_PHY_Top_q0_ln0_pcs_rx_rst_i(~pma_rstn),
        .Customized_PHY_Top_q0_ln0_pcs_tx_rst_i(~pma_rstn));

    wire clk60a, lock1, fclk960, clk60, lock2;
    pll_60m p1 (.clkin(sd_txclk), .reset(pll_rst), .clkout0(clk60a), .lock(lock1));
    pll_usb p2 (.clkin(clk60a), .reset(~lock1), .clkout0(fclk960), .clkout1(clk60), .lock(lock2));

    reg [2:0] ls = 0;
    reg [7:0] rcnt = 0;
    always @(posedge clk60) begin
        ls <= {ls[1:0], lock2};
        if (~ls[2]) rcnt <= 0;
        else if (~&rcnt) rcnt <= rcnt + 1'b1;
    end
    wire rst = ~&rcnt;

    // ---- USB ----
    wire [7:0] phy_dout, phy_din;
    wire phy_txvalid, phy_txready, phy_rxvalid, phy_rxactive, phy_rxerror, phy_termsel;
    wire [1:0] phy_linestate, phy_opmode, phy_xcvrsel;

    wire usb_rstn, hs, suspend, configured, bus_reset;
    wire [3:0] ust;
    wire [2:0] chirps;
    wire [8:0] in_addr;
    wire [7:0] in_data;
    wire in_wren, in_ready, in_commit_ack;
    reg in_commit = 0;
    reg [9:0] in_len = 0;
    wire [7:0] out_q;
    wire [9:0] out_len;
    wire out_hasdata, out_arm_ack;
    reg out_arm = 0;
    wire vend_act;
    wire [7:0] vend_req;
    wire [15:0] vend_val;
    wire [4:0] err;
    wire [10:0] frame_num;

    usb2_top usb (
        .ext_clk(clk60), .reset_n(~rst), .reset_n_out(usb_rstn),
        .phy_clk(clk60),
        .utmi_dataout(phy_dout), .utmi_txvalid(phy_txvalid), .utmi_txready(phy_txready),
        .utmi_datain(phy_din), .utmi_rxactive(phy_rxactive), .utmi_rxvalid(phy_rxvalid),
        .utmi_linestate(phy_linestate), .utmi_opmode(phy_opmode), .utmi_xcvrselect(phy_xcvrsel),
        .utmi_termselect(phy_termsel),
        .opt_disconnect(cmd[1]), .opt_enable_hs(~cmd[7]), .opt_blind_hs(cmd[16]),
        .stat_hs(hs), .stat_suspend(suspend), .stat_state(ust), .stat_chirps(chirps),
        .stat_bus_reset(bus_reset), .stat_configured(configured),
        .buf_in_addr(in_addr), .buf_in_data(in_data), .buf_in_wren(in_wren), .buf_in_ready(in_ready),
        .buf_in_commit(in_commit), .buf_in_commit_len(in_len), .buf_in_commit_ack(in_commit_ack),
        .buf_out_addr(9'd0), .buf_out_q(out_q), .buf_out_len(out_len), .buf_out_hasdata(out_hasdata),
        .buf_out_arm(out_arm), .buf_out_arm_ack(out_arm_ack),
        .vend_req_act(vend_act), .vend_req_request(vend_req), .vend_req_val(vend_val),
        .err_crc_pid(err[0]), .err_crc_tok(err[1]), .err_crc_pkt(err[2]), .err_pid_out_of_seq(err[3]),
        .err_setup_pkt(err[4]),
        .dbg_frame_num(frame_num));

    USB2_0_SoftPHY_Top phy (
        .clk_i(clk60), .rst_i(rst), .fclk_i(fclk960), .pll_locked_i(lock2),
        .utmi_data_out_i(phy_dout), .utmi_txvalid_i(phy_txvalid), .utmi_op_mode_i(phy_opmode),
        .utmi_xcvrselect_i(phy_xcvrsel), .utmi_termselect_i(phy_termsel),
        .utmi_data_in_o(phy_din), .utmi_txready_o(phy_txready), .utmi_rxvalid_o(phy_rxvalid),
        .utmi_rxactive_o(phy_rxactive), .utmi_rxerror_o(phy_rxerror),
        .utmi_linestate_o(phy_linestate),
        .usb_dxp_io(usb_dxp_io), .usb_dxn_io(usb_dxn_io),
        .usb_rxdp_i(usb_rxdp_i), .usb_rxdn_i(usb_rxdn_i),
        .usb_pullup_en_o(usb_pullup_en_o),
        .usb_term_dp_io(usb_term_dp_io), .usb_term_dn_io(usb_term_dn_io));

    // ---- EP1 IN: пакет счётчика в свободный буфер, затем commit ----
    localparam [1:0] F_IDLE = 0, F_FILL = 1, F_COMMIT = 2, F_DONE = 3;
    reg [1:0] fst = F_IDLE;
    reg [9:0] fa = 0;
    reg [31:0] word = 0;
    wire [9:0] plen = cmd[15:8] == 0 ? (hs ? 10'd512 : 10'd64) : cmd[15:8] > 8'd128 ? 10'd512 :
        {cmd[15:8], 2'b00};
    assign in_addr = fa[8:0];
    assign in_data = cmd[5:4] == 2'd0 ? word[8 * fa[1:0] +: 8] : cmd[5:4] == 2'd1 ? 8'h00 :
        cmd[5:4] == 2'd2 ? 8'hFF : 8'h7E;
    assign in_wren = fst == F_FILL;
    always @(posedge clk60) begin
        case (fst)
            F_IDLE: begin
                fa <= 0;
                if (in_ready & configured & ~cmd[0]) begin
                    in_len <= plen;
                    fst <= F_FILL;
                end
            end
            F_FILL: begin
                fa <= fa + 1'b1;
                if (&fa[1:0]) word <= word + 1'b1;
                if (fa == in_len - 1'b1) begin
                    in_commit <= 1;
                    fst <= F_COMMIT;
                end
            end
            F_COMMIT: if (in_commit_ack) begin
                in_commit <= 0;
                fst <= F_DONE;
            end
            F_DONE: if (~in_commit_ack) fst <= F_IDLE;
        endcase
        if (~usb_rstn) begin
            fst <= F_IDLE;
            in_commit <= 0;
            word <= 0;
        end
    end

    // ---- EP2 OUT: принять и освободить ----
    reg [1:0] dst = 0;
    reg [31:0] n_opkt = 0, n_ob = 0;
    always @(posedge clk60) begin
        case (dst)
            0: if (out_hasdata) begin
                n_opkt <= n_opkt + 1'b1;
                n_ob <= n_ob + out_len;
                out_arm <= 1;
                dst <= 1;
            end
            1: if (out_arm_ack) begin
                out_arm <= 0;
                dst <= 2;
            end
            default: if (~out_arm_ack) dst <= 0;
        endcase
        if (~usb_rstn) begin
            dst <= 0;
            out_arm <= 0;
        end
    end

    // ---- счётчики ----
    reg [31:0] n_rst = 0, n_sof = 0, n_vend = 0, n_ipkt = 0, n_ib = 0;
    reg [32*5-1:0] n_err = 0;
    reg [4:0] err_q = 0;
    reg vend_q = 0;
    reg [10:0] frame_q = 0;
    reg [7:0] last_req = 0;
    reg [15:0] last_val = 0;
    integer k;
    always @(posedge clk60) begin
        vend_q <= vend_act;
        frame_q <= frame_num;
        err_q <= err;
        if (bus_reset) n_rst <= n_rst + 1'b1;
        if (frame_num != frame_q) n_sof <= n_sof + 1'b1;
        if (vend_act & ~vend_q) begin
            n_vend <= n_vend + 1'b1;
            last_req <= vend_req;
            last_val <= vend_val;
        end
        if (fst == F_COMMIT & in_commit_ack) begin
            n_ipkt <= n_ipkt + 1'b1;
            n_ib <= n_ib + in_len;
        end
        for (k = 0; k < 5; k = k + 1)
            if (err[k] & ~err_q[k]) n_err[32 * k +: 32] <= n_err[32 * k +: 32] + 1'b1;
    end

    // ---- журнал: пакеты UTMI и события шины ----
    reg [31:0] ts = 0;
    reg [LOG2:0] lptr = 0;
    reg [2:0] larm = 0;
    reg rxa_q = 0, txv_q = 0, rx_err = 0;
    reg [9:0] rx_len = 0, tx_len = 0;
    reg [7:0] rx_pid = 0, rx_b1 = 0, tx_pid = 0, tx_b1 = 0;
    reg [31:0] loga [0:(1 << LOG2) - 1];
    reg [31:0] logb [0:(1 << LOG2) - 1];
    reg lwe = 0, ev_pend = 0;
    reg [31:0] lwa = 0, lwt = 0, ev = 0, ev_t = 0;
    wire [9:0] evs = {ust, phy_linestate, phy_opmode, phy_xcvrsel};
    reg [10:0] evs_q = 0;
    wire line_ev = ust != 4'd1 & ust != 4'd5;  // вне FS и HS linestate тоже в журнал
    wire ev_now = ({evs, phy_termsel} != evs_q) & (ust != evs_q[10:7] | line_ev);
    always @(posedge clk60) begin
        ts <= ts + 1'b1;
        larm <= {larm[1:0], cmd[2]};
        rxa_q <= phy_rxactive;
        txv_q <= phy_txvalid;
        evs_q <= {evs, phy_termsel};
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
        if (ev_now & ~cmd[6]) begin
            ev_pend <= 1;
            ev <= {3'b001, 13'd0, ust, phy_linestate, phy_opmode, phy_xcvrsel, phy_termsel, 2'd0, chirps};
            ev_t <= ts;
        end
        if (~phy_rxactive & rxa_q) begin
            lwe <= rx_pid != 8'hA5 | cmd[3];
            lwa <= {1'b0, rx_err, 4'd0, rx_len, rx_pid, rx_b1};
            lwt <= ts;
        end else if (~phy_txvalid & txv_q & ust != 4'd3) begin  // чирп K — не пакет
            lwe <= 1;
            lwa <= {1'b1, 1'b0, 4'd0, tx_len, tx_pid, tx_b1};
            lwt <= ts;
        end else if (ev_pend & ~ev_now) begin
            lwe <= 1;
            lwa <= ev;
            lwt <= ev_t;
            ev_pend <= 0;
        end
        if (larm[2] ^ larm[1])
            lptr <= 0;
        else if (lwe & ~lptr[LOG2]) begin
            loga[lptr[LOG2-1:0]] <= lwa;
            logb[lptr[LOG2-1:0]] <= lwt;
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
    wire [31:0] f60, f125;
    fmeter m60 (.fclk(clk60), .clk(osc), .tick(&tmr), .cnt(f60));
    fmeter m125 (.fclk(sd_txclk), .clk(osc), .tick(&tmr), .cnt(f125));

    // ---- пользовательский JTAG (как в usb2.v) ----
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
            0: hw = 32'h444E4C52;
            1: hw = {seq, 16'd0, VER};
            2: hw = cmd;
            3: hw = {12'd0, phy_termsel, phy_xcvrsel, phy_opmode, chirps, ust, phy_linestate, suspend,
                configured, hs, rst, lock2, lock1};
            4: hw = n_rst;
            5: hw = n_sof;
            6: hw = n_vend;
            7: hw = n_ipkt;
            8: hw = n_ib;
            9: hw = n_opkt;
            10: hw = n_ob;
            11: hw = n_err[0 +: 32];
            12: hw = f60;
            13: hw = f125;
            14, 15, 16, 17: hw = n_err[32 * (w - 13) +: 32];
            18: hw = {21'd0, frame_num};
            19: hw = {last_val, 8'd0, last_req};
            20, 21, 22: hw = 0;
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
