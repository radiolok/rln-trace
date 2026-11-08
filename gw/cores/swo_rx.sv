// SWO receiver, UART (NRZ) mode: 8N1, LSB first, any rate up to about CLK/8.
// The bit clock is a 32-bit phase accumulator, rate = step * CLK / 2**32, so
// the rate need not divide the clock. A start edge sets the phase to half a
// bit; every overflow samples a bit. Bytes go to a FIFO of 2**FLOG bytes; a
// byte that finds the FIFO full is lost and sets `overrun` until `clr`.
// Bytes with a bad stop bit are dropped and counted.
// Read: pulse rd while count != 0, rd_data is valid the next cycle.
//
// SPDX-License-Identifier: BSD-3-Clause

module swo_rx #(
    parameter int FLOG = 13             // 8 KB
) (
    input  logic            clk,
    input  logic            rst,
    input  logic            rx,         // asynchronous
    input  logic            en,
    input  logic [31:0]     step,
    input  logic            clr,        // empty the FIFO, clear overrun

    output logic [FLOG:0]   count,
    input  logic            rd,
    output logic [7:0]      rd_data,
    output logic            overrun,
    output logic [15:0]     frame_err
);
    logic [2:0]  rx_s;
    logic [31:0] ph;
    logic [3:0]  bits;                  // 0 idle, 10 start .. 1 stop
    logic [7:0]  sh;
    logic        got;
    logic [7:0]  byte_in;

    wire  [32:0] ph_n = {1'b0, ph} + {1'b0, step};

    always_ff @(posedge clk) begin
        rx_s <= {rx_s[1:0], rx};
        got  <= 1'b0;
        if (rst || !en) begin
            bits <= '0;
            if (rst) begin
                rx_s      <= '1;
                frame_err <= '0;
            end
        end else if (bits == 4'd0) begin
            if (rx_s[2] && !rx_s[1]) begin  // falling edge
                ph   <= 32'h8000_0000;
                bits <= 4'd10;
            end
        end else begin
            ph <= ph_n[31:0];
            if (ph_n[32]) begin
                bits <= bits - 4'd1;
                if (bits == 4'd10 && rx_s[1])
                    bits <= '0;             // glitch, not a start bit
                else if (bits == 4'd1) begin
                    if (rx_s[1]) begin
                        byte_in <= sh;
                        got     <= 1'b1;
                    end else
                        frame_err <= frame_err + 1'b1;
                end else if (bits != 4'd10)
                    sh <= {rx_s[1], sh[7:1]};
            end
        end
    end

    // ---------------------------------------------------------------- FIFO
    logic [7:0]      mem [1 << FLOG];
    logic [FLOG-1:0] wp, rp;

    always_ff @(posedge clk) begin
        if (got && count != (FLOG + 1)'(1 << FLOG))
            mem[wp] <= byte_in;
        rd_data <= mem[rp];
        if (clr || rst) begin
            wp      <= '0;
            rp      <= '0;
            count   <= '0;
            overrun <= 1'b0;
        end else begin
            if (got) begin
                if (count == (FLOG + 1)'(1 << FLOG))
                    overrun <= 1'b1;
                else
                    wp <= wp + 1'b1;
            end
            if (rd)
                rp <= rp + 1'b1;
            count <= count + (FLOG + 1)'(got && count != (FLOG + 1)'(1 << FLOG)) - (FLOG + 1)'(rd);
        end
    end
endmodule
