// Asynchronous FIFO, Gray-coded pointers through two-flop synchronisers.
// First-word-fall-through read side with a registered memory read, so the
// memory maps to block RAM (or registered distributed RAM when small): every
// cycle the word at the next read pointer is fetched. A written word becomes
// visible to the reader only through the two-flop synchroniser, so the fetch
// that raises rvalid always sees it.
//
// Each side has its own synchronous reset; reset both together.
//
// SPDX-License-Identifier: BSD-3-Clause

module async_fifo #(
    parameter int DW = 32,
    parameter int AW = 4            // depth 2**AW
) (
    input  logic          wclk,
    input  logic          wrst,
    input  logic [DW-1:0] wdata,
    input  logic          wen,      // ignored while wfull
    output logic          wfull,
    output logic [AW:0]   wfree,    // free entries as seen by the writer, registered (lags, never overstates)

    input  logic          rclk,
    input  logic          rrst,
    output logic [DW-1:0] rdata,
    output logic          rvalid,
    input  logic          rready
);
    logic [DW-1:0] mem [2**AW];

    logic [AW:0] wbin, wgray, rbin, rgray;
    logic [AW:0] wgray_r1, wgray_r2;   // write pointer in the read domain
    logic [AW:0] rgray_w1, rgray_w2;   // read pointer in the write domain

    function automatic logic [AW:0] bin2gray(input logic [AW:0] b);
        bin2gray = b ^ (b >> 1);
    endfunction

    function automatic logic [AW:0] gray2bin(input logic [AW:0] g);
        for (int i = 0; i <= AW; i++) gray2bin[i] = ^(g >> i);
    endfunction

    // write side
    logic [AW:0] wbin_n;
    logic        wfire;
    assign wfire  = wen && !wfull;
    assign wbin_n = wbin + (AW+1)'(wfire);

    always_ff @(posedge wclk) begin
        if (wfire) mem[wbin[AW-1:0]] <= wdata;
    end

    always_ff @(posedge wclk) begin
        if (wrst) begin
            wbin     <= '0;
            wgray    <= '0;
            wfull    <= 1'b0;
            wfree    <= (AW+1)'(2**AW);
            rgray_w1 <= '0;
            rgray_w2 <= '0;
        end else begin
            wbin     <= wbin_n;
            wgray    <= bin2gray(wbin_n);
            wfull    <= bin2gray(wbin_n) == {~rgray_w2[AW:AW-1], rgray_w2[AW-2:0]};
            wfree    <= (AW+1)'(2**AW) - (wbin_n - gray2bin(rgray_w2));
            rgray_w1 <= rgray;
            rgray_w2 <= rgray_w1;
        end
    end

    // read side
    logic [AW:0] rbin_n;
    logic        rfire;
    assign rfire  = rvalid && rready;
    assign rbin_n = rbin + (AW+1)'(rfire);
    always_ff @(posedge rclk) begin
        rdata <= mem[rbin_n[AW-1:0]];
    end

    always_ff @(posedge rclk) begin
        if (rrst) begin
            rbin     <= '0;
            rgray    <= '0;
            rvalid   <= 1'b0;
            wgray_r1 <= '0;
            wgray_r2 <= '0;
        end else begin
            rbin     <= rbin_n;
            rgray    <= bin2gray(rbin_n);
            rvalid   <= bin2gray(rbin_n) != wgray_r2;
            wgray_r1 <= wgray;
            wgray_r2 <= wgray_r1;
        end
    end
endmodule
