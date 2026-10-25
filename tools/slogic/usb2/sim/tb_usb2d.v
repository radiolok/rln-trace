// Стенд ядра Daisho + usb2_utmi без PHY: модель UTMI и хоста. Сброс шины, чирп и KJ хоста (HS)
// или FS, перечисление, IN EP1 (счётчик, повтор без ACK), OUT EP2, PING, GET_STATUS.
//   sh sim/run.sh           # HS
//   sh sim/run.sh -DFS      # FS: байт раз в 40 тактов, без чирпа
`timescale 1ns / 1ps
module tb;
`ifdef FS
    localparam BYTE_T = 40, HSMODE = 0;
`else
    localparam BYTE_T = 1, HSMODE = 1;
`endif
    reg clk = 0;
    always #8.333 clk = ~clk;
    reg rstn = 0;

    wire [7:0] dout;
    wire txvalid;
    reg txready = 0;
    reg [7:0] din = 0;
    reg rxactive = 0, rxvalid = 0;
    reg [1:0] ls_host = 2'b00;  // SE0, пока подтяжка не включена
    wire [1:0] opmode, xcvr;
    wire term;
    wire [1:0] linestate = txvalid & opmode == 2'b10 ? 2'b10 : ls_host;
    wire hs, susp, cfg, busrst, rstn_out;
    wire [3:0] ust;
    wire [2:0] chirps;

    // источник EP1 IN: как в usb2d.v — счётчик слов, пакет 512 (HS) / 64 (FS)
    reg [9:0] fa = 0;
    reg [31:0] word = 0;
    reg [1:0] fst = 0;
    reg commit = 0;
    wire in_ready, commit_ack, out_hasdata, out_ack;
    wire [9:0] out_len;
    reg out_arm = 0;
    wire [9:0] plen = hs ? 10'd512 : 10'd64;
    always @(posedge clk) begin
        case (fst)
            0: begin fa <= 0; if (in_ready & cfg) fst <= 1; end
            1: begin
                fa <= fa + 1'b1;
                if (&fa[1:0]) word <= word + 1'b1;
                if (fa == plen - 1) begin commit <= 1; fst <= 2; end
            end
            2: if (commit_ack) begin commit <= 0; fst <= 3; end
            3: if (~commit_ack) fst <= 0;
        endcase
        if (~rstn_out) begin fst <= 0; commit <= 0; word <= 0; end
    end
    reg [1:0] dst = 0;
    integer n_out = 0;
    always @(posedge clk) begin
        case (dst)
            0: if (out_hasdata) begin n_out = n_out + out_len; out_arm <= 1; dst <= 1; end
            1: if (out_ack) begin out_arm <= 0; dst <= 2; end
            default: if (~out_ack) dst <= 0;
        endcase
    end

    usb2_top dut (
        .ext_clk(clk), .reset_n(rstn), .reset_n_out(rstn_out), .phy_clk(clk),
        .utmi_dataout(dout), .utmi_txvalid(txvalid), .utmi_txready(txready),
        .utmi_datain(din), .utmi_rxactive(rxactive), .utmi_rxvalid(rxvalid),
        .utmi_linestate(linestate), .utmi_opmode(opmode), .utmi_xcvrselect(xcvr),
        .utmi_termselect(term),
        .opt_disconnect(1'b0), .opt_enable_hs(HSMODE[0]), .opt_blind_hs(1'b0),
        .stat_hs(hs), .stat_suspend(susp), .stat_state(ust), .stat_chirps(chirps),
        .stat_bus_reset(busrst), .stat_configured(cfg),
        .buf_in_addr(fa[8:0]), .buf_in_data(word[8 * fa[1:0] +: 8]), .buf_in_wren(fst == 1),
        .buf_in_ready(in_ready), .buf_in_commit(commit), .buf_in_commit_len(plen),
        .buf_in_commit_ack(commit_ack),
        .buf_out_addr(9'd0), .buf_out_q(), .buf_out_len(out_len), .buf_out_hasdata(out_hasdata),
        .buf_out_arm(out_arm), .buf_out_arm_ack(out_ack),
        .vend_req_act(), .vend_req_request(), .vend_req_val(),
        .err_crc_pid(), .err_crc_tok(), .err_crc_pkt(), .err_pid_out_of_seq(), .err_setup_pkt(),
        .dbg_frame_num());

    // ---- PHY: txready ----
    integer tc = 0;
    always @(posedge clk) begin
        if (~txvalid) begin tc <= 0; txready <= 0; end
        else begin
            tc <= tc + 1;
            // HS: ~4 такта на SYNC, дальше без пауз; FS: байт раз в BYTE_T
            txready <= HSMODE ? tc >= 3 : (tc % BYTE_T) == BYTE_T - 2;
        end
    end

    // ---- CRC ----
    function [4:0] crc5(input [10:0] d);
        integer i;
        reg [4:0] c;
        reg b;
        begin
            c = 5'h1f;
            for (i = 0; i < 11; i = i + 1) begin
                b = d[i] ^ c[4];
                c = {c[3:0], 1'b0} ^ (b ? 5'h05 : 5'h00);
            end
            crc5 = ~c;
        end
    endfunction
    reg [15:0] crc;
    task crc16_byte(input [7:0] x);
        integer i;
        reg b;
        begin
            for (i = 0; i < 8; i = i + 1) begin
                b = x[i] ^ crc[15];
                crc = {crc[14:0], 1'b0} ^ (b ? 16'h8005 : 16'h0000);
            end
        end
    endtask
    function [15:0] rev16(input [15:0] x);
        integer i;
        for (i = 0; i < 16; i = i + 1) rev16[i] = x[15 - i];
    endfunction
    function [4:0] rev5(input [4:0] x);
        rev5 = {x[0], x[1], x[2], x[3], x[4]};
    endfunction

    // ---- хост: передача ----
    reg [7:0] pkt [0:1023];
    integer plen_h;
    task send_pkt;  // pkt[0..plen_h-1]
        integer i;
        begin
            @(posedge clk) rxactive <= 1;
            repeat (2) @(posedge clk);
            for (i = 0; i < plen_h; i = i + 1) begin
                din <= pkt[i];
                rxvalid <= 1;
                @(posedge clk) rxvalid <= 0;
                repeat (BYTE_T - 1) @(posedge clk);
            end
            repeat (2) @(posedge clk);
            rxactive <= 0;
            repeat (2) @(posedge clk);
        end
    endtask
    task token(input [7:0] pid, input [6:0] addr, input [3:0] ep);
        reg [10:0] v;
        reg [15:0] w;
        begin
            v = {ep, addr};
            w = {rev5(crc5(v)), v};
            pkt[0] = pid; pkt[1] = w[7:0]; pkt[2] = w[15:8];
            plen_h = 3;
            send_pkt;
        end
    endtask
    reg [7:0] dat [0:1023];
    task data(input [7:0] pid, input integer n);  // dat[0..n-1]
        integer i;
        reg [15:0] c;
        begin
            crc = 16'hffff;
            pkt[0] = pid;
            for (i = 0; i < n; i = i + 1) begin
                pkt[1 + i] = dat[i];
                crc16_byte(dat[i]);
            end
            c = rev16(~crc);
            pkt[1 + n] = c[7:0];
            pkt[2 + n] = c[15:8];
            plen_h = n + 3;
            send_pkt;
        end
    endtask
    task hand(input [7:0] pid);
        begin pkt[0] = pid; plen_h = 1; send_pkt; end
    endtask

    // ---- хост: приём ----
    reg [7:0] rx [0:1023];
    integer rxn, gap, gap_max = 0, crc_bad = 0;
    task recv;  // rxn = 0 — нет ответа
        integer t;
        begin
            rxn = 0;
            t = 0;
            while (~txvalid & t < 400) begin @(posedge clk); t = t + 1; end
            gap = t;
            if (t > gap_max & txvalid) gap_max = t;
            while (txvalid) begin
                @(posedge clk);
                if (txvalid & txready) begin rx[rxn] = dout; rxn = rxn + 1; end
            end
            if (rxn > 3 | rxn == 3 & (rx[0] == 8'hC3 | rx[0] == 8'h4B)) begin  // DATA: CRC
                crc = 16'hffff;
                for (t = 1; t < rxn - 2; t = t + 1) crc16_byte(rx[t]);
                if (rev16(~crc) != {rx[rxn - 1], rx[rxn - 2]}) begin
                    crc_bad = crc_bad + 1;
                    $display("  ОШИБКА CRC16 ответа");
                end
            end
            repeat (4) @(posedge clk);
        end
    endtask

    integer errors = 0;
    task expect_pid(input [7:0] pid, input integer n);  // n — байт данных, -1 — не проверять
        begin
            recv;
            if (rxn == 0 | rx[0] != pid | n >= 0 & rxn != (n + (pid == 8'hD2 | pid == 8'h5A ? 1 : 3))) begin
                $display("  ОШИБКА: ждали %h (%0d), пришло %h, %0d байт", pid, n, rxn ? rx[0] : 8'hxx, rxn);
                errors = errors + 1;
            end
        end
    endtask
    task setup(input [6:0] addr, input [63:0] s);  // s — байты SETUP, первый — старший
        integer i;
        begin
            token(8'h2D, addr, 0);
            for (i = 0; i < 8; i = i + 1) dat[i] = s[63 - 8 * i -: 8];
            data(8'hC3, 8);
            expect_pid(8'hD2, 0);
        end
    endtask

    // ---- сценарий ----
    integer i, k, j;
    reg [31:0] w0;
    reg [7:0] tog;
    initial begin
        $dumpfile("sim/tb_usb2d.vcd");
        $dumpvars(0, tb);
        repeat (20) @(posedge clk);
        rstn <= 1;
        // подключение: ждём FS с подтяжкой, затем сброс шины (SE0)
        wait (term);
        repeat (600) @(posedge clk);  // 10 мкс SE0 до подъёма линии — не сброс шины
        ls_host <= 2'b01;
        wait (ust == 1);
        if (dut.ia.stat_chirps | busrst) errors = errors + 1;
        repeat (1000) @(posedge clk);
        ls_host <= 2'b00;
        if (HSMODE) begin
            wait (ust == 4);  // чирп K устройства закончился
            $display("%0t: чирп K устройства закончен", $time);
            repeat (600) @(posedge clk);  // 10 мкс
            for (i = 0; i < 8; i = i + 1) begin
                ls_host <= i[0] ? 2'b01 : 2'b10;
                repeat (2400) @(posedge clk);  // 40 мкс
            end
            ls_host <= 2'b00;
            if (ust != 5) begin $display("ОШИБКА: не HS, состояние %0d, чирпов %0d", ust, chirps); $finish; end
            $display("%0t: HS, чирпов %0d", $time, chirps);
        end else begin
            repeat (30000) @(posedge clk);  // 0,5 мс SE0
            ls_host <= 2'b01;
            repeat (100) @(posedge clk);
            if (ust != 1) begin $display("ОШИБКА: не FS, состояние %0d", ust); $finish; end
        end
        repeat (200) @(posedge clk);

        token(8'hA5, 7'h3A, 0);  // SOF
        // GET_DESCRIPTOR device, 64
        setup(0, 64'h8006000100004000);
        token(8'h69, 0, 0);
        expect_pid(8'h4B, 18);
        $display("дескриптор устройства: %h %h ... VID %h%h PID %h%h", rx[1], rx[2], rx[10], rx[9], rx[12], rx[11]);
        hand(8'hD2);
        token(8'hE1, 0, 0);
        data(8'h4B, 0);
        expect_pid(8'hD2, 0);
        // SET_ADDRESS 5
        setup(0, 64'h0005050000000000);
        token(8'h69, 0, 0);
        expect_pid(8'h4B, 0);
        hand(8'hD2);
        // GET_DESCRIPTOR config 255 по новому адресу
        setup(5, 64'h800600020000FF00);
        token(8'h69, 5, 0);
        expect_pid(8'h4B, 32);
        $display("конфигурация: %0d байт, wTotalLength %0d, EP %h %h", rxn - 3, rx[3], rx[21], rx[28]);
        hand(8'hD2);
        token(8'hE1, 5, 0);
        data(8'h4B, 0);
        expect_pid(8'hD2, 0);
        // старый адрес не отвечает
        token(8'h69, 0, 0);
        recv;
        if (rxn) begin $display("  ОШИБКА: ответ на адрес 0"); errors = errors + 1; end
        // строка 2
        setup(5, 64'h800602030904FF00);
        token(8'h69, 5, 0);
        expect_pid(8'h4B, -1);
        $write("строка: ");
        for (i = 3; i < rxn - 2; i = i + 2) $write("%c", rx[i]);
        $display("");
        hand(8'hD2);
        token(8'hE1, 5, 0);
        data(8'h4B, 0);
        expect_pid(8'hD2, 0);
        // GET_STATUS
        setup(5, 64'h8000000000000200);
        token(8'h69, 5, 0);
        expect_pid(8'h4B, 2);
        hand(8'hD2);
        token(8'hE1, 5, 0);
        data(8'h4B, 0);
        expect_pid(8'hD2, 0);
        // CLEAR_FEATURE(ENDPOINT_HALT, 0x81) — без стадии данных, статус ZLP (раньше — вечный NAK)
        setup(5, 64'h0201000081000000);
        token(8'h69, 5, 0);
        expect_pid(8'h4B, 0);
        hand(8'hD2);
        // SET_CONFIGURATION 1
        setup(5, 64'h0009010000000000);
        token(8'h69, 5, 0);
        expect_pid(8'h4B, 0);
        hand(8'hD2);
        repeat (2000) @(posedge clk);
        if (~cfg) begin $display("ОШИБКА: не configured"); errors = errors + 1; end

        // EP1 IN: 6 пакетов, третий без ACK — должен прийти повтором
        k = 0;
        tog = 8'hC3;
        for (j = 0; j < 6; j = j + 1) begin
            token(8'h69, 5, 1);
            expect_pid(tog, HSMODE ? 512 : 64);
            w0 = {rx[4], rx[3], rx[2], rx[1]};
            if (w0 != k) begin $display("  ОШИБКА: пакет %0d с слова %0d, ждали %0d", j, w0, k); errors = errors + 1; end
            for (i = 0; i < rxn - 3; i = i + 1)
                if (rx[1 + i] != ((k + i / 4) >> (8 * (i % 4)) & 8'hFF)) begin
                    if (errors < 20) $display("  ОШИБКА: байт %0d = %h", i, rx[1 + i]);
                    errors = errors + 1;
                end
            if (j == 2) $display("пакет %0d %h без ACK", j, rx[0]);
            else begin
                hand(8'hD2);
                k = k + (rxn - 3) / 4;
                tog = tog == 8'hC3 ? 8'h4B : 8'hC3;
            end
        end
        $display("EP1 IN: %0d слов подряд", k);
        // EP2 OUT: PING (HS), затем 2 пакета
        if (HSMODE) begin
            token(8'hB4, 5, 2);
            expect_pid(8'hD2, 0);
        end
        for (j = 0; j < 2; j = j + 1) begin
            token(8'hE1, 5, 2);
            for (i = 0; i < (HSMODE ? 512 : 64); i = i + 1) dat[i] = i;
            data(j ? 8'h4B : 8'hC3, HSMODE ? 512 : 64);
            expect_pid(8'hD2, 0);
            repeat (100) @(posedge clk);
        end
        $display("EP2 OUT: принято %0d байт", n_out);
        if (n_out != (HSMODE ? 1024 : 128)) errors = errors + 1;
        $display("пауза конец пакета хоста → txvalid: до %0d тактов", gap_max);

        if (HSMODE) begin
            // 3 мс без активности в HS → FS; SE0 → сброс шины, чирп заново, адрес 0
            repeat (190000) @(posedge clk);
            wait (ust == 4 | ust == 7);
            $display("%0t: после 3 мс тишины: состояние %0d (4 — чирп после сброса)", $time, ust);
            if (ust != 4) errors = errors + 1;
        end
        if (errors | crc_bad) $display("ИТОГ: ошибок %0d, CRC %0d", errors, crc_bad);
        else $display("ИТОГ: всё сошлось");
        $finish;
    end
    initial begin
        #60_000_000;
        $display("ТАЙМ-АУТ, состояние %0d", ust);
        $finish;
    end
endmodule
