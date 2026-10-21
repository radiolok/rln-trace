// Tang Nano 20K, bench step 0: FPGA -> HSPI 16 bit -> CH569 (fw/ch569/hspi2usb)
// -> USB3 -> sw/usbstream, plus the CH569 -> FPGA direction for measuring the
// HSPI CRC: packets from the CH569 come out on the BL616 UART as hex lines for
// tools/hspi-crc/find_crc.py.
//
//   27 MHz -> rPLL -> clk, CLK_MHZ (15 for jumper wires, up to 96): HRCLK of the
//   CH569 and the self-test. HTCLK of the CH569 clocks hspi_rx.
//
// Buttons: S1 reset, S2 self-test on/off (on after reset). The board LEDs are
// gone (their resistors removed, pins 15-20 are bench signals); once a second a
// status line goes to the UART instead:
//   # <HSPI packets out> <packets in> <bad packets in> <HTACK timeouts> <flags>
//   flags: bit 0 self-test on, bit 1 PLL locked, bits 15:8 CLK_MHZ
// The HD bus is the CH569's while it requests (HTREQ): no packet starts then.
// HD0 is the CH569 boot pin: the FPGA leaves HD released (pull-up) unless it
// sends. Pins: tangnano20k.cst, README.md.
//
// SPDX-License-Identifier: BSD-3-Clause

module top_step0 #(
    parameter int CLK_MHZ = 15           // 15, 30, 60 or 96
) (
    input  logic        clk27,
    input  logic        s1,
    input  logic        s2,
    output logic        uart_txd,

    inout  wire  [15:0] hd,
    output logic        hrclk,           // -> CH569 HRCLK
    output logic        hract,           // -> CH569 HRACT (request)
    output logic        hrvld,           // -> CH569 HRVLD
    input  logic        htack,           // <- CH569 HTACK (ready to receive)
    input  logic        htclk,           // <- CH569 HTCLK
    input  logic        htreq,           // <- CH569 HTREQ
    input  logic        htvld,           // <- CH569 HTVLD
    output logic        htrdy            // -> CH569 HTRDY
);
    // 27 MHz * (FBDIV + 1) / (IDIV + 1), VCO = out * ODIV in 500..1250 MHz (gowin_pll)
    localparam int PLL_IDIV  = 8;
    localparam int PLL_FBDIV = CLK_MHZ == 96 ? 31 : CLK_MHZ == 60 ? 19 : CLK_MHZ == 30 ? 9 : 4;
    localparam int PLL_ODIV  = CLK_MHZ == 96 ? 8  : CLK_MHZ == 60 ? 16 : CLK_MHZ == 30 ? 32 : 48;
    localparam int UART_DIV  = (CLK_MHZ * 1000000 + 57600) / 115200;
    localparam int SECOND    = CLK_MHZ * 1000000;

    // ---------------------------------------------------------------- clocks, resets
    logic clk, lock;

    rPLL #(
        .FCLKIN("27.0"), .IDIV_SEL(PLL_IDIV), .FBDIV_SEL(PLL_FBDIV), .ODIV_SEL(PLL_ODIV),
        .DEVICE("GW2AR-18C")
    ) u_pll (
        .CLKOUT(clk), .CLKOUTP(), .CLKOUTD(), .CLKOUTD3(), .LOCK(lock),
        .CLKIN(clk27), .CLKFB(1'b0), .RESET(1'b0), .RESET_P(1'b0),
        .FBDSEL(6'd0), .IDSEL(6'd0), .ODSEL(6'd0), .PSDA(4'd0), .DUTYDA(4'd0), .FDLY(4'd0)
    );

    logic [2:0] rst_s, rst_r;
    logic       rst, rx_rst;
    always_ff @(posedge clk or negedge lock) begin
        if (!lock) rst_s <= '1;
        else       rst_s <= {rst_s[1:0], s1};
    end
    assign rst = rst_s[2];
    always_ff @(posedge htclk) rst_r <= {rst_r[1:0], rst};
    assign rx_rst = rst_r[2];

    // ---------------------------------------------------------------- 1 s tick, S2
    logic [26:0] sec_cnt;
    logic        sec;
    logic [2:0]  s2_s;
    logic        enable;
    always_ff @(posedge clk) begin
        if (rst) begin
            sec_cnt <= '0;
            sec     <= 1'b0;
            s2_s    <= '0;
            enable  <= 1'b1;
        end else begin
            sec <= sec_cnt == 27'(SECOND - 1);
            sec_cnt <= sec ? '0 : sec_cnt + 27'd1;
            if (sec_cnt[13:0] == '0) begin       // sampled every ~1 ms at 15 MHz: no bounce
                s2_s <= {s2_s[1:0], s2};
                if (s2_s[1] && !s2_s[2]) enable <= !enable;
            end
        end
    end

    // ---------------------------------------------------------------- HD bus
    logic [15:0] hd_o, hd_i;
    logic        hd_oe;
    for (genvar i = 0; i < 16; i++) begin : g_hd
        IOBUF u_io (.O(hd_i[i]), .IO(hd[i]), .I(hd_o[i]), .OEN(!hd_oe));
    end

    // HRCLK: clk inverted, so the CH569 takes HD on its rising edge mid-bit
    ODDR u_hrclk (.D0(1'b0), .D1(1'b1), .TX(1'b0), .CLK(clk), .Q0(hrclk), .Q1());

    // ---------------------------------------------------------------- FPGA -> CH569
    logic [1:0]  htreq_s;
    logic [3:0]  tx_seq;
    logic [31:0] cnt_blocks, cnt_packets, cnt_ack_timeout;
    always_ff @(posedge clk) htreq_s <= {htreq_s[0], htreq};

    selftest_hspi #(.W(16)) u_selftest (
        .clk, .rst,
        .cfg_enable(enable), .cfg_kind(1'b1), .cfg_block_words(14'd1024),
        .cfg_usdf(26'h0525354), .cfg_hold(htreq_s[1]), .cfg_gap(8'd2), .cfg_ack_timeout(8'd64),
        .hspi_req(hract), .hspi_vld(hrvld), .hspi_data(hd_o), .hspi_oe(hd_oe), .hspi_ack(htack),
        .seq(tx_seq), .cnt_blocks, .cnt_packets, .cnt_ack_timeout
    );

    // ---------------------------------------------------------------- CH569 -> FPGA -> UART
    logic [31:0] rx_data;
    logic        rx_last, rx_good, rx_valid, rx_ready;
    logic [31:0] rx_packets_rx, rx_bad_rx;   // HTCLK domain, not used here

    hspi_rx #(.W(16)) u_rx (
        .rx_clk(htclk), .rx_rst, .rx_req(htreq), .rx_vld(htvld), .rx_data(hd_i), .rx_rdy(htrdy),
        .cfg_raw(1'b1),
        .clk, .rst,
        .out_data(rx_data), .out_last(rx_last), .out_good(rx_good), .out_valid(rx_valid), .out_ready(rx_ready),
        .cnt_packets(rx_packets_rx), .cnt_bad(rx_bad_rx)
    );

    // packets in, counted on the sys side by their closing words
    logic [31:0] rx_packets, rx_bad;
    always_ff @(posedge clk) begin
        if (rst) begin
            rx_packets <= '0;
            rx_bad     <= '0;
        end else if (rx_valid && rx_ready && rx_last) begin
            rx_packets <= rx_packets + 32'd1;
            if (!rx_good) rx_bad <= rx_bad + 32'd1;
        end
    end

    logic [7:0] hex_c, st_c, ch;
    logic       hex_v, hex_r, st_v, st_r, ch_v, ch_r, st_busy;

    uart_hex u_hex (
        .clk, .rst,
        .in_data(rx_data), .in_last(rx_last), .in_good(rx_good), .in_valid(rx_valid), .in_ready(rx_ready),
        .out_data(hex_c), .out_valid(hex_v), .out_ready(hex_r)
    );

    uart_status #(.N(5)) u_status (
        .clk, .rst,
        .words({16'd0, 8'(CLK_MHZ), 6'd0, lock, enable,
                cnt_ack_timeout, rx_bad, rx_packets, cnt_packets}),
        .start(sec && !st_busy), .busy(st_busy),
        .out_data(st_c), .out_valid(st_v), .out_ready(st_r)
    );

    uart_mux u_mux (
        .clk, .rst,
        .a_data(hex_c), .a_valid(hex_v), .a_ready(hex_r),
        .b_data(st_c), .b_valid(st_v), .b_ready(st_r),
        .out_data(ch), .out_valid(ch_v), .out_ready(ch_r)
    );

    uart_tx #(.DIV(UART_DIV)) u_uart (
        .clk, .rst, .data(ch), .valid(ch_v), .ready(ch_r), .tx(uart_txd)
    );

    // kept for a CSR block
    logic unused;
    assign unused = ^{tx_seq, cnt_blocks, rx_packets_rx, rx_bad_rx};
endmodule
