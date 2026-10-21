// Tang Nano 9K on the bench: signal source for the Tang Nano 20K. A synthetic
// TPIU trace port (tpiu_tx) for the step 2 loopback, a PPS pulse and a square
// wave for the event inputs.
//
//   27 MHz -> rPLL -> clk = TRACECLK rate, TRC_MHZ (12 for jumper wires, 24, 84);
//   CLKOUTP is the same clock shifted by TRC_PHASE * 22.5 deg and drives the
//   TRACECLK pin, so the receiver's sampling point can be moved against the data.
//   TRACED0..3 leave through ODDR: first sample with the rising edge of clk.
//
// S1 (pin 4) reset, S2 (pin 3) port width 4 -> 2 -> 1 -> 4 bits; both low when pressed.
// LEDs (lit low): 0 heartbeat, 1 PLL lock, 2..3 width (4 bits: both, 2: LED3, 1: LED2), 4 PPS, 5 square wave.
// UART (BL702, 115200): once a second "# <frames sent> <width> <TRC_MHZ>".
// Every pin used here is 3.3 V; header pins 79..86 are a 1.8 V bank, not for the 20K.
//
// SPDX-License-Identifier: BSD-3-Clause

module top_gen #(
    parameter int TRC_MHZ   = 12,        // 12, 24 or 84
    parameter int TRC_PHASE = 4          // TRACECLK delay, 22.5 deg steps: 4 = 90 deg
) (
    input  logic       clk27,
    input  logic       s1_n,
    input  logic       s2_n,
    output logic [5:0] led_n,
    output logic       uart_txd,

    output logic       traceclk,
    output logic [3:0] traced,
    output logic       pps,
    output logic       sq
);
    // 27 MHz * (FBDIV + 1) / (IDIV + 1), VCO = out * ODIV in 400..1200 MHz (gowin_pll)
    localparam int PLL_IDIV  = 8;
    localparam int PLL_FBDIV = TRC_MHZ == 84 ? 27 : TRC_MHZ == 24 ? 7 : 3;
    localparam int PLL_ODIV  = TRC_MHZ == 84 ? 8 : TRC_MHZ == 24 ? 32 : 64;
    localparam int UART_DIV  = (TRC_MHZ * 1000000 + 57600) / 115200;
    localparam int SECOND    = TRC_MHZ * 1000000;
    localparam int PPS_WIDTH = TRC_MHZ * 100;          // 100 us
    localparam int SQ_HALF   = TRC_MHZ * 500;          // 1 kHz

    // PSDA_SEL is a string of four binary digits
    localparam PSDA = TRC_PHASE == 1  ? "0001" : TRC_PHASE == 2  ? "0010" : TRC_PHASE == 3  ? "0011" :
                      TRC_PHASE == 4  ? "0100" : TRC_PHASE == 5  ? "0101" : TRC_PHASE == 6  ? "0110" :
                      TRC_PHASE == 7  ? "0111" : TRC_PHASE == 8  ? "1000" : TRC_PHASE == 9  ? "1001" :
                      TRC_PHASE == 10 ? "1010" : TRC_PHASE == 11 ? "1011" : TRC_PHASE == 12 ? "1100" :
                      TRC_PHASE == 13 ? "1101" : TRC_PHASE == 14 ? "1110" : TRC_PHASE == 15 ? "1111" : "0000";

    logic clk, clkp, lock;

    rPLL #(
        .FCLKIN("27"), .IDIV_SEL(PLL_IDIV), .FBDIV_SEL(PLL_FBDIV), .ODIV_SEL(PLL_ODIV),
        .PSDA_SEL(PSDA),
        .DEVICE("GW1NR-9C")
    ) u_pll (
        .CLKOUT(clk), .CLKOUTP(clkp), .CLKOUTD(), .CLKOUTD3(), .LOCK(lock),
        .CLKIN(clk27), .CLKFB(1'b0), .RESET(1'b0), .RESET_P(1'b0),
        .FBDSEL(6'd0), .IDSEL(6'd0), .ODSEL(6'd0), .PSDA(4'd0), .DUTYDA(4'd0), .FDLY(4'd0)
    );

    logic [2:0] rst_s;
    logic       rst;
    always_ff @(posedge clk or negedge lock) begin
        if (!lock) rst_s <= '1;
        else       rst_s <= {rst_s[1:0], !s1_n};
    end
    assign rst = rst_s[2];

    // ---------------------------------------------------------------- 1 s tick, S2, PPS, square
    logic [26:0] sec_cnt;
    logic [19:0] sq_cnt;
    logic        sec, sq_r, pps_r;
    logic [2:0]  s2_s;
    logic [1:0]  width;
    always_ff @(posedge clk) begin
        if (rst) begin
            sec_cnt <= '0;
            sq_cnt  <= '0;
            sec     <= 1'b0;
            sq_r    <= 1'b0;
            pps_r   <= 1'b0;
            s2_s    <= '1;
            width   <= 2'd2;
        end else begin
            sec     <= sec_cnt == 27'(SECOND - 1);
            sec_cnt <= sec ? '0 : sec_cnt + 27'd1;
            pps_r   <= sec_cnt < 27'(PPS_WIDTH);
            if (sq_cnt == 20'(SQ_HALF - 1)) begin
                sq_cnt <= '0;
                sq_r   <= !sq_r;
            end else begin
                sq_cnt <= sq_cnt + 20'd1;
            end
            if (sec_cnt[13:0] == '0) begin          // ~1 ms at 12 MHz: no bounce
                s2_s <= {s2_s[1:0], s2_n};
                if (!s2_s[1] && s2_s[2]) width <= (width == 2'd0) ? 2'd2 : width - 2'd1;
            end
        end
    end
    assign pps = pps_r;
    assign sq  = sq_r;

    // ---------------------------------------------------------------- trace port
    logic [3:0]  first, second;
    logic [31:0] frames;
    logic [1:0]  width_d;
    logic        rst_tx;

    // a width change restarts the stream with a sync
    always_ff @(posedge clk) width_d <= width;
    assign rst_tx = rst || (width != width_d);

    tpiu_tx u_tx (
        .clk, .rst(rst_tx),
        .cfg_enable(1'b1), .cfg_width(width), .cfg_sync_every(8'd16), .cfg_hsync(1'b0),
        .out_first(first), .out_second(second), .frames
    );

    for (genvar i = 0; i < 4; i++) begin : g_d
        ODDR u_d (.D0(first[i]), .D1(second[i]), .TX(1'b0), .CLK(clk), .Q0(traced[i]), .Q1());
    end
    ODDR u_clk (.D0(1'b1), .D1(1'b0), .TX(1'b0), .CLK(clkp), .Q0(traceclk), .Q1());

    // ---------------------------------------------------------------- status
    logic [7:0] ch;
    logic       ch_v, ch_r, st_busy;

    uart_status #(.N(3)) u_status (
        .clk, .rst,
        .words({32'(TRC_MHZ), 32'(width == 2'd2 ? 4 : width == 2'd1 ? 2 : 1), frames}),
        .start(sec && !st_busy), .busy(st_busy),
        .out_data(ch), .out_valid(ch_v), .out_ready(ch_r)
    );

    uart_tx #(.DIV(UART_DIV)) u_uart (.clk, .rst, .data(ch), .valid(ch_v), .ready(ch_r), .tx(uart_txd));

    logic [24:0] hb;
    always_ff @(posedge clk) hb <= hb + 25'd1;

    assign led_n = ~{sq_r, pps_r, width == 2'd0 || width == 2'd2, width == 2'd1 || width == 2'd2, lock, hb[24]};
endmodule
