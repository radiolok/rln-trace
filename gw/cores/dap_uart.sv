// CMSIS-DAP over a UART: frames [length, 2 bytes LE][packet] both ways,
// uart_rx -> dap_core -> uart_tx. The host sends one request and waits for the
// response (packet count 1), so the UART needs no flow control. A frame that
// stalls for TIMEOUT cycles is dropped and the receiver resynchronises; a
// length of 0 or above the packet size is dropped too.
//
// SPDX-License-Identifier: BSD-3-Clause

module dap_uart #(
    parameter int CLK_HZ  = 27000000,
    parameter int DIV     = 9,          // 27 MHz / 3 Mbaud
    parameter int ALOG    = 9,
    parameter int TIMEOUT = CLK_HZ / 100
) (
    input  logic clk,
    input  logic rst,
    input  logic rxd,
    output logic txd,
    output logic rx_strobe,

    output logic tck,
    output logic tms,
    output logic tms_oe,
    input  logic swdio,
    output logic tdi,
    input  logic tdo,
    output logic trst,
    output logic srst
);
    logic [7:0] rx_data;

    uart_rx #(.DIV(DIV)) u_rx (.clk, .rst, .rx(rxd), .data(rx_data), .valid(rx_strobe));

    // ---------------------------------------------------------------- request
    typedef enum logic [1:0] {R_L0, R_L1, R_DATA, R_BUSY} rs_t;
    rs_t rs;
    logic [15:0]     rlen;
    logic [ALOG:0]   ri;
    logic [$clog2(TIMEOUT + 1)-1:0] tmo;
    logic            req_we, req_go;
    logic [ALOG-1:0] req_wa;
    logic [7:0]      req_wd;

    logic            resp_valid, resp_ack;
    logic [ALOG:0]   resp_len;
    logic [ALOG-1:0] resp_ra;
    logic [7:0]      resp_rd;

    always_ff @(posedge clk) begin
        req_we <= 1'b0;
        req_go <= 1'b0;
        if (rs == R_L0 || rx_strobe)
            tmo <= '0;
        else if (rs != R_BUSY)
            tmo <= tmo + 1'b1;
        case (rs)
            R_L0: if (rx_strobe) begin
                rlen[7:0] <= rx_data;
                rs        <= R_L1;
            end
            R_L1: if (rx_strobe) begin
                rlen[15:8] <= rx_data;
                ri         <= '0;
                rs         <= {rx_data, rlen[7:0]} == 16'd0 || {rx_data, rlen[7:0]} > 16'(1 << ALOG) ? R_L0 : R_DATA;
            end
            R_DATA: if (rx_strobe) begin
                req_we <= 1'b1;
                req_wa <= ri[ALOG-1:0];
                req_wd <= rx_data;
                ri     <= ri + 1'b1;
                if (16'(ri) + 16'd1 == rlen) begin
                    req_go <= 1'b1;
                    rs     <= R_BUSY;
                end
            end
            R_BUSY: if (resp_ack)
                rs <= R_L0;
        endcase
        if (rs != R_L0 && rs != R_BUSY && tmo == ($clog2(TIMEOUT + 1))'(TIMEOUT))
            rs <= R_L0;
        if (rst) begin
            rs  <= R_L0;
            tmo <= '0;
        end
    end

    dap_core #(.CLK_HZ(CLK_HZ), .ALOG(ALOG)) u_core (
        .clk, .rst,
        .req_we, .req_wa, .req_wd, .req_go,
        .resp_valid, .resp_len, .resp_ra, .resp_rd, .resp_ack,
        .tck, .tms, .tms_oe, .swdio, .tdi, .tdo, .trst, .srst
    );

    // ---------------------------------------------------------------- response
    typedef enum logic [2:0] {T_IDLE, T_L0, T_L1, T_RD, T_DATA, T_ACK} ts_t;
    ts_t ts;
    logic [ALOG:0] ti;
    logic [7:0]    tx_data;
    logic          tx_valid, tx_ready;

    always_ff @(posedge clk) begin
        resp_ack <= 1'b0;
        tx_valid <= 1'b0;
        case (ts)
            T_IDLE: if (resp_valid && !resp_ack) begin
                ti      <= '0;
                resp_ra <= '0;
                ts      <= T_L0;
            end
            T_L0: if (tx_ready && !tx_valid) begin
                tx_data  <= 8'(resp_len);
                tx_valid <= 1'b1;
                ts       <= T_L1;
            end
            T_L1: if (tx_ready && !tx_valid) begin
                tx_data  <= 8'(resp_len >> 8);
                tx_valid <= 1'b1;
                ts       <= T_RD;
            end
            T_RD: ts <= T_DATA;     // resp_rd follows resp_ra one cycle later
            T_DATA: if (tx_ready && !tx_valid) begin
                tx_data  <= resp_rd;
                tx_valid <= 1'b1;
                ti       <= ti + 1'b1;
                resp_ra  <= resp_ra + 1'b1;
                ts       <= ti + 1'b1 == resp_len ? T_ACK : T_RD;
            end
            T_ACK: begin
                resp_ack <= 1'b1;
                ts       <= T_IDLE;
            end
            default: ts <= T_IDLE;
        endcase
        if (rst)
            ts <= T_IDLE;
    end

    uart_tx #(.DIV(DIV)) u_tx (.clk, .rst, .data(tx_data), .valid(tx_valid), .ready(tx_ready), .tx(txd));
endmodule
