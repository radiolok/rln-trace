// JTAG pins driven by the OpenOCD remote_bitbang protocol, one ASCII byte per
// command (openocd doc/manual/jtag/drivers/remote_bitbang.txt):
//   '0'..'7'  set {tck, tms, tdi} = byte - '0'
//   'R'       answer the sampled TDO as '0' or '1'
//   'r'..'u'  set {trst, srst} = byte - 'r' (1 = asserted, the pin goes low)
//   'B', 'b'  LED on, off
// Everything else ('Q', sleeps 'Z' 'z', SWD commands) is ignored. Answers wait
// in a small queue for the transmitter, so 'R' never blocks the input.
//
// SPDX-License-Identifier: BSD-3-Clause

module rbb_jtag #(
    parameter int QLOG = 4              // answer queue: 2**QLOG bits
) (
    input  logic       clk,
    input  logic       rst,

    input  logic [7:0] cmd,
    input  logic       cmd_valid,

    output logic [7:0] ans,
    output logic       ans_valid,
    input  logic       ans_ready,

    output logic       tck,
    output logic       tms,
    output logic       tdi,
    input  logic       tdo,             // asynchronous
    output logic       trst,            // asserted high
    output logic       srst,            // asserted high
    output logic       led
);
    logic [1:0] tdo_s;
    logic [(1 << QLOG) - 1:0] q;
    logic [QLOG:0] wp, rp;

    wire q_empty = wp == rp;
    wire pop     = ans_valid && ans_ready;

    assign ans_valid = !q_empty;
    assign ans       = {7'h18, q[rp[QLOG-1:0]]};    // '0' = 0x30

    always_ff @(posedge clk) begin
        tdo_s <= {tdo_s[0], tdo};
        if (pop)
            rp <= rp + 1'b1;
        if (cmd_valid) begin
            case (cmd)
                "0", "1", "2", "3", "4", "5", "6", "7": {tck, tms, tdi} <= cmd[2:0];
                "r", "s", "t", "u": {trst, srst} <= cmd[1:0] - 2'd2;  // 'r' = 0x72
                "B": led <= 1'b1;
                "b": led <= 1'b0;
                "R": begin
                    q[wp[QLOG-1:0]] <= tdo_s[1];
                    wp <= wp + 1'b1;
                end
                default: ;
            endcase
        end
        if (rst) begin
            {tck, tms, tdi} <= 3'b010;
            {trst, srst}    <= 2'b00;
            led <= 1'b0;
            wp  <= '0;
            rp  <= '0;
        end
    end
endmodule
