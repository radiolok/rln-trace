// Sipeed SLogic16U3 (direction A): trace adapter top level. Skeleton: the
// pinout is final, the logic is not written yet.
//
// FPGA: GW5AT-LV15MG132C1/I0 (Arora V, MG132 package). Flash XT25F128F: the
// factory app at 0x000000, the golden DFU image at 0x800000 (both encrypted).
// Our bitstream must set multiboot to 0x800000 (gowin.tcl): the MODE button is
// RECONFIG_N and must still bring the DFU loader back.
//
// Input channels, mapped on the bench on 2026-10-25 (tools/slogic/jprobe,
// doc/slogic-pinmap-journal.md). All 16 are in bank 1, channels 2k and 2k+1
// share one differential pair:
//
//   ch    ball  pad      pin functions
//   ----  ----  -------  ------------------------------------
//   0     J14   IOB41B   DQS1
//   1     J13   IOB41A   DQS1
//   2     N14   IOB12B
//   3     P14   IOB12A
//   4     N13   IOB14B   D14
//   5     P13   IOB14A   D15
//   6     N12   IOB16A
//   7     P12   IOB16B
//   8     N11   IOB22A   GCLKT_3
//   9     P11   IOB22B   GCLKC_3
//   10    N10   IOB18B   D12
//   11    P10   IOB18A   D13
//   12    N9    IOB24A   GCLKT_2 / BPLL_T_IN0
//   13    P9    IOB24B   GCLKC_2 / BPLL_C_IN0
//   14    N8    IOB20A   DQS2
//   15    P8    IOB20B   DQS2
//
// Input front end: each channel goes through a divider of ~0.47 (3.0 V in ->
// 1.42 V at the ball; the analyser range is up to 10 V) with a speed-up
// capacitor. VCCIO1 is 3.3 V, so the LVCMOS33 threshold (~VCCIO/2) is above a
// 3.3 V signal after the divider: only edge overshoots get through. Use a
// low-threshold standard on a 3.3 V bank, LVCMOS15UD33 (~0.75 V), no pulls
// (slogic16u3.cst). For 1.8 V targets (~0.85 V at the ball) the margin is thin:
// LVCMOS12UD33 or a VREF input (internal VREF 0.6/0.75/0.9 V) - not yet tried.
//
// Trace port (2026-10-25: TPIU from STM32F407 received clean up to TRACECLK 3.96 MHz by
// oversampling at OSCB, tools/slogic/trace; not yet clocked from TRACECLK):
//   TRACECLK      ch[12]   N9, GCLKT_2 and BPLL_T_IN0: global clock and PLL input
//   TRACED0..3    ch[8..11]
//   the rest      event inputs (PPS, triggers)
// The CK0/CK1 header pins were not seen on any FPGA GPIO.
//
// Do not use: JTAG G2 G3 J3 J2 (debug header; GW_JTAG works with ports named
// tck_pad_i/tms_pad_i/tdi_pad_i/tdo_pad_o and no .cst lines), RECONFIG_N M3,
// DONE L3, READY M12, MODE1/0 N1 N2, flash L13 L14 M13 K14 K13 M14. Unknown
// lines (USB mux, LED, DC-DC) are among the remaining bank 1, 3 and 4 pins:
// keep every pin not listed here as Gowin's default (input).
//
// TODO: USB3 through the Q0 SerDes (Gowin IP), the VL162 orientation mux,
// clocking (OSCB is ~30 MHz on this die, not the nominal 52.5), trace_rx.
//
// SPDX-License-Identifier: BSD-3-Clause

module top_slogic16u3 (
    input  logic [15:0] ch                  // header CH0..CH15, see above
);
    localparam int CH_TRACECLK = 12;
    localparam int CH_TRACED0  = 8;          // TRACED0..3 = ch[8..11]

    /* verilator lint_off UNUSEDSIGNAL */
    logic       traceclk;
    logic [3:0] traced;
    logic [15:0] events;
    /* verilator lint_on UNUSEDSIGNAL */

    assign traceclk = ch[CH_TRACECLK];
    assign traced   = ch[CH_TRACED0 +: 4];
    assign events   = ch;
endmodule
