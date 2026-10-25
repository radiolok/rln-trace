// Слой UTMI для USB2-ядра Daisho вместо usb2_ulpi.v: тот же интерфейс к usb2_packet, снаружи —
// UTMI (Gowin USB 2.0 SoftPHY). Такт — 60 МГц PHY.
//
// Передача. usb2_packet рассчитан на ULPI: первый байт — TX_CMD {4'h4, PID}, байты уходят по nxt,
// stp — в такте после последнего принятого байта. Здесь: фронт pkt_in_latch → PID {~P, P} с
// txvalid; nxt = txready; txvalid снимается комбинационно по pkt_in_stp (регистр пакетного
// уровня), так что за последним байтом PHY не видит лишнего.
// Приём: act = rxactive, latch = rxactive & rxvalid.
//
// Шина (USB 2.0, 7.1.7.5; UTMI 1.05). FS: SE0 ≥ 4 мкс — сброс; если HS разрешён — чирп K 2 мс
// (XcvrSelect HS, TermSelect FS, OpMode 2, данные 00h), затем ждём от хоста K-J-K-J-K-J, каждый
// ≥ 2,5 мкс, по LineState → HS (TermSelect HS, OpMode 0). Нет чирпов 1,5 мс — FS. В HS: 3 мс без
// активности (rxactive или LineState ≠ SE0) → назад в FS, через 100 мкс LineState: SE0 — сброс,
// J — приостановка; из неё K (resume) → в прежнюю скорость. Пока шина в сбросе или идёт чирп,
// пакетный и протокольный уровни в сбросе (адрес обнуляется — у Daisho этого не было).
module usb2_utmi (
    input wire clk,
    input wire reset_n,
    input wire opt_disconnect,  // 1 — подтяжка снята, устройство отключено
    input wire opt_enable_hs,
    input wire opt_blind_hs,    // переходить в HS через 100 мкс после чирпа, не дожидаясь KJ хоста
    output wire reset_local,
    output reg stat_hs,
    output wire stat_suspend,
    output reg [3:0] stat_state,
    output reg [2:0] stat_chirps,  // чирпов хоста в последнем согласовании
    output reg bus_reset,          // импульс в начале сброса шины

    output wire [7:0] utmi_dataout,
    output wire utmi_txvalid,
    input wire utmi_txready,
    input wire [7:0] utmi_datain,
    input wire utmi_rxactive,
    input wire utmi_rxvalid,
    input wire [1:0] utmi_linestate,
    output reg [1:0] utmi_opmode,
    output reg [1:0] utmi_xcvrselect,
    output reg utmi_termselect,

    output wire pkt_out_act,
    output wire [7:0] pkt_out_byte,
    output wire pkt_out_latch,
    output wire pkt_in_cts,
    output wire pkt_in_nxt,
    input wire [7:0] pkt_in_byte,
    input wire pkt_in_latch,
    input wire pkt_in_stp
);
    localparam [3:0] ST_OFF = 0, ST_FS = 1, ST_FSRST = 2, ST_CHIRP_K = 3, ST_CHIRP_WAIT = 4,
        ST_HS = 5, ST_HS_REV = 6, ST_SUSP = 7, ST_RESUME = 8, ST_BUSRST = 9;
    localparam [1:0] LS_SE0 = 2'b00, LS_J = 2'b01, LS_K = 2'b10;
    // такты 60 МГц
    localparam T_SE0 = 240,          // 4 мкс SE0 — сброс шины
        T_FILT = 150,                // 2,5 мкс — чирп хоста
        T_CHIRP = 120000,            // 2 мс чирп K
        T_CHIRP_TO = 90000,          // 1,5 мс ждать чирпов хоста
        T_BLIND = 6000,              // 100 мкс
        T_IDLE = 180000,             // 3 мс без активности
        T_REV = 6000;                // 100 мкс после возврата в FS

    reg [1:0] rst_s = 0;
    reg [3:0] st = ST_OFF, st_q = ST_OFF;
    reg [17:0] t = 0;      // время в состоянии
    reg [17:0] ta = 0;     // время без активности / в J
    reg [7:0] se0 = 0;     // длительность SE0
    reg [7:0] filt = 0;    // длительность ожидаемого чирпа
    reg was_hs = 0;

    wire normal = st == ST_FS | st == ST_HS;
    assign reset_local = rst_s[1] & ~(st == ST_OFF | st == ST_BUSRST | st == ST_FSRST | st == ST_CHIRP_K |
        st == ST_CHIRP_WAIT);
    assign stat_suspend = st == ST_SUSP | st == ST_RESUME;

    // ---- передача ----
    reg tx_busy = 0, tx_pid_ph = 0, lat_q = 0;
    reg [3:0] tx_pid = 0;
    wire chirp_tx = st == ST_CHIRP_K;
    assign utmi_txvalid = chirp_tx | tx_busy & ~pkt_in_stp;
    assign utmi_dataout = chirp_tx ? 8'h00 : tx_pid_ph ? {~tx_pid, tx_pid} : pkt_in_byte;
    assign pkt_in_nxt = tx_busy & ~pkt_in_stp & utmi_txready;
    assign pkt_in_cts = normal & ~utmi_rxactive & ~tx_busy;
    always @(posedge clk) begin
        lat_q <= pkt_in_latch;
        if (~tx_busy) begin
            if (pkt_in_latch & ~lat_q & normal) begin
                tx_busy <= 1;
                tx_pid_ph <= 1;
                tx_pid <= pkt_in_byte[3:0];
            end
        end else begin
            if (utmi_txready & ~pkt_in_stp) tx_pid_ph <= 0;
            if (pkt_in_stp) tx_busy <= 0;
        end
        if (~normal) begin
            tx_busy <= 0;
            tx_pid_ph <= 0;
        end
    end

    // ---- приём ----
    assign pkt_out_act = utmi_rxactive;
    assign pkt_out_latch = utmi_rxactive & utmi_rxvalid;
    assign pkt_out_byte = utmi_datain;

    // ---- состояние шины ----
    // t — время в состоянии; в первом такте нового состояния t ещё от прежнего — сравнивать tt
    wire [17:0] tt = st == st_q ? t : 18'd0;
    always @(posedge clk) begin
        rst_s <= {rst_s[0], reset_n};
        st_q <= st;
        bus_reset <= 0;
        if (st != st_q) t <= 0;
        else if (~&t) t <= t + 1'b1;
        se0 <= utmi_linestate != LS_SE0 ? 8'd0 : ~&se0 ? se0 + 1'b1 : se0;
        stat_state <= st;
        case (st)
            ST_OFF: begin
                {utmi_xcvrselect, utmi_termselect, utmi_opmode} <= {2'b01, 1'b0, 2'b01};
                stat_hs <= 0;
                if (~opt_disconnect & tt >= 6000) st <= ST_FSRST;  // до J от подтяжки SE0 — не сброс
            end
            ST_FS: begin
                {utmi_xcvrselect, utmi_termselect, utmi_opmode} <= {2'b01, 1'b1, 2'b00};
                stat_hs <= 0;
                ta <= utmi_linestate == LS_J ? ta + 1'b1 : 18'd0;
                if (se0 >= T_SE0) st <= ST_BUSRST;
                else if (ta >= T_IDLE) begin
                    was_hs <= 0;
                    st <= ST_SUSP;
                end
            end
            ST_FSRST: begin  // в FS, сброс шины ещё идёт
                {utmi_xcvrselect, utmi_termselect, utmi_opmode} <= {2'b01, 1'b1, 2'b00};
                stat_hs <= 0;
                ta <= 0;
                if (utmi_linestate != LS_SE0) st <= ST_FS;
            end
            ST_CHIRP_K: begin
                {utmi_xcvrselect, utmi_termselect, utmi_opmode} <= {2'b00, 1'b1, 2'b10};
                if (tt >= T_CHIRP) st <= ST_CHIRP_WAIT;
            end
            ST_CHIRP_WAIT: begin
                {utmi_xcvrselect, utmi_termselect, utmi_opmode} <= {2'b00, 1'b1, 2'b10};
                // ожидаемый чирп: K при чётном счёте, J при нечётном
                if (utmi_linestate == (stat_chirps[0] ? LS_J : LS_K)) begin
                    filt <= filt + 1'b1;
                    if (filt == T_FILT) begin
                        filt <= 0;
                        stat_chirps <= stat_chirps + 1'b1;
                    end
                end else
                    filt <= 0;
                if (stat_chirps == 6 | opt_blind_hs & tt >= T_BLIND) begin
                    stat_hs <= 1;
                    ta <= 0;
                    st <= ST_HS;
                end else if (tt >= T_CHIRP_TO)
                    st <= ST_FSRST;
            end
            ST_HS: begin
                {utmi_xcvrselect, utmi_termselect, utmi_opmode} <= {2'b00, 1'b0, 2'b00};
                stat_hs <= 1;
                ta <= utmi_rxactive | utmi_linestate != LS_SE0 | tx_busy ? 18'd0 : ta + 1'b1;
                if (ta >= T_IDLE) st <= ST_HS_REV;
            end
            ST_HS_REV: begin
                {utmi_xcvrselect, utmi_termselect, utmi_opmode} <= {2'b01, 1'b1, 2'b00};
                if (tt >= T_REV) begin
                    if (utmi_linestate == LS_SE0) st <= ST_BUSRST;
                    else begin
                        was_hs <= 1;
                        st <= ST_SUSP;
                    end
                end
            end
            ST_SUSP: begin
                {utmi_xcvrselect, utmi_termselect, utmi_opmode} <= {2'b01, 1'b1, 2'b00};
                if (se0 >= T_SE0) st <= ST_BUSRST;
                else if (utmi_linestate == LS_K) st <= ST_RESUME;
            end
            ST_RESUME: begin  // K от хоста, ждём его конца (EOP)
                {utmi_xcvrselect, utmi_termselect, utmi_opmode} <= {2'b01, 1'b1, 2'b00};
                if (utmi_linestate != LS_K) begin
                    ta <= 0;
                    st <= was_hs ? ST_HS : ST_FS;
                end
            end
            ST_BUSRST: begin  // сброс шины: дальше чирп или FS
                bus_reset <= 1;
                stat_chirps <= 0;
                filt <= 0;
                st <= opt_enable_hs ? ST_CHIRP_K : ST_FSRST;
            end
            default: st <= ST_OFF;
        endcase
        if (opt_disconnect & st != ST_OFF) st <= ST_OFF;
        if (~rst_s[1]) st <= ST_OFF;
    end
endmodule
