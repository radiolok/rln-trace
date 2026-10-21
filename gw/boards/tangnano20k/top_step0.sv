// Tang Nano 20K, bench step 0: FPGA -> HSPI 8 bit -> CH569 (fw/ch569/hspi2usb)
// -> USB3 -> sw/usbstream, plus the CH569 -> FPGA direction for measuring the
// HSPI CRC: packets from the CH569 come out on the BL616 UART as hex lines for
// tools/hspi-crc/find_crc.py.
//
//   27 MHz -> rPLL -> clk (60 MHz by default; HRCLK of the CH569 and the
//   self-test). HTCLK of the CH569 clocks hspi_rx.
//
// Buttons: S1 reset, S2 self-test on/off (on after reset).
// LEDs (lit low): 0 heartbeat, 1 PLL lock, 2 self-test on, 3 HSPI packets out,
// 4 packets in, 5 HTACK timeout seen.
// The HD bus is the CH569's while it requests (HTREQ): no packet starts then.
// HD0 is the CH569 boot pin: the FPGA leaves HD released (pull-up) unless it
// sends. Pins: tangnano20k.cst, gw/boards/tangnano20k/README.md.
//
// SPDX-License-Identifier: BSD-3-Clause

module top_step0 #(
    parameter int PLL_IDIV  = 8,         // 27 MHz * 20 / 9 = 60 MHz (gowin_pll)
    parameter int PLL_FBDIV = 19,
    parameter int PLL_ODIV  = 16,
    parameter int UART_DIV  = 521        // 60 MHz / 115200
) (
    input  logic       clk27,
    input  logic       s1,
    input  logic       s2,
    output logic [5:0] led_n,
    output logic       uart_txd,

    inout  wire  [7:0] hd,
    output logic       hrclk,            // -> CH569 HRCLK
    output logic       hract,            // -> CH569 HRACT (request)
    output logic       hrvld,            // -> CH569 HRVLD
    input  logic       htack,            // <- CH569 HTACK (ready to receive)
    input  logic       htclk,            // <- CH569 HTCLK
    input  logic       htreq,            // <- CH569 HTREQ
    input  logic       htvld,            // <- CH569 HTVLD
    output logic       htrdy             // -> CH569 HTRDY
);
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

    // ---------------------------------------------------------------- S2: self-test on/off
    logic [19:0] tick;
    logic [2:0]  s2_s;
    logic        enable;
    always_ff @(posedge clk) begin
        if (rst) begin
            tick   <= '0;
            s2_s   <= '0;
            enable <= 1'b1;
        end else begin
            tick <= tick + 20'd1;
            if (tick == '0) begin                 // ~57 Hz sampling: no bounce
                s2_s <= {s2_s[1:0], s2};
                if (s2_s[1] && !s2_s[2]) enable <= !enable;
            end
        end
    end

    // ---------------------------------------------------------------- HD bus
    logic [7:0] hd_o, hd_i;
    logic       hd_oe;
    for (genvar i = 0; i < 8; i++) begin : g_hd
        IOBUF u_io (.O(hd_i[i]), .IO(hd[i]), .I(hd_o[i]), .OEN(!hd_oe));
    end

    // HRCLK: clk inverted, so the CH569 takes HD on its rising edge mid-bit
    ODDR u_hrclk (.D0(1'b0), .D1(1'b1), .TX(1'b0), .CLK(clk), .Q0(hrclk), .Q1());

    // ---------------------------------------------------------------- FPGA -> CH569
    logic [1:0]  htreq_s;
    logic [3:0]  tx_seq;
    logic [31:0] cnt_blocks, cnt_packets, cnt_ack_timeout;
    always_ff @(posedge clk) htreq_s <= {htreq_s[0], htreq};

    selftest_hspi #(.W(8)) u_selftest (
        .clk, .rst,
        .cfg_enable(enable), .cfg_kind(1'b1), .cfg_block_words(14'd1024),
        .cfg_usdf(26'h0525354), .cfg_hold(htreq_s[1]), .cfg_gap(8'd2), .cfg_ack_timeout(8'd64),
        .hspi_req(hract), .hspi_vld(hrvld), .hspi_data(hd_o), .hspi_oe(hd_oe), .hspi_ack(htack),
        .seq(tx_seq), .cnt_blocks, .cnt_packets, .cnt_ack_timeout
    );

    // ---------------------------------------------------------------- CH569 -> FPGA -> UART
    logic [31:0] rx_data;
    logic        rx_last, rx_good, rx_valid, rx_ready;
    logic [31:0] rx_packets, rx_bad;

    hspi_rx #(.W(8)) u_rx (
        .rx_clk(htclk), .rx_rst, .rx_req(htreq), .rx_vld(htvld), .rx_data(hd_i), .rx_rdy(htrdy),
        .cfg_raw(1'b1),
        .clk, .rst,
        .out_data(rx_data), .out_last(rx_last), .out_good(rx_good), .out_valid(rx_valid), .out_ready(rx_ready),
        .cnt_packets(rx_packets), .cnt_bad(rx_bad)
    );

    logic [7:0] ch;
    logic       ch_valid, ch_ready;

    uart_hex u_hex (
        .clk, .rst,
        .in_data(rx_data), .in_last(rx_last), .in_good(rx_good), .in_valid(rx_valid), .in_ready(rx_ready),
        .out_data(ch), .out_valid(ch_valid), .out_ready(ch_ready)
    );

    uart_tx #(.DIV(UART_DIV)) u_uart (
        .clk, .rst, .data(ch), .valid(ch_valid), .ready(ch_ready), .tx(uart_txd)
    );

    // ---------------------------------------------------------------- LEDs
    // rx_packets lives in the HTCLK domain: its bit 6 toggles slowly, two flops are enough
    logic [1:0]  rxp_s;
    logic        ack_to_seen;
    logic [25:0] hb;                      // heartbeat, ~1 Hz at 60 MHz
    always_ff @(posedge clk) begin
        hb    <= hb + 26'd1;
        rxp_s <= {rxp_s[0], rx_packets[6]};
        if (rst) ack_to_seen <= 1'b0;
        else if (cnt_ack_timeout != 32'd0) ack_to_seen <= 1'b1;
    end

    assign led_n = ~{ack_to_seen, rxp_s[1], cnt_packets[6], enable, lock, hb[25]};

    // not shown anywhere yet; kept for a CSR block
    logic unused;
    assign unused = ^{tx_seq, cnt_blocks, rx_bad, rx_packets[31:7], rx_packets[5:0],
                      cnt_packets[31:7], cnt_packets[5:0], tick[18:0], tick[19]};
endmodule
