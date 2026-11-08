// CMSIS-DAP command processor: one request packet in, one response packet out,
// transport-agnostic (dap_uart frames packets over a UART; a USB bulk endpoint
// can feed it the same way). The transport writes the request through req_*,
// pulses req_go, then reads the response through resp_ra/resp_rd (one cycle
// latency) while resp_valid is high and pulses resp_ack.
//
// Commands (CMSIS-DAP v2.1): Info (capabilities, packet size and count,
// firmware version), HostStatus, Connect, Disconnect, ResetTarget (no-op),
// TransferConfigure, Transfer (SWD: posted AP reads, WAIT retries; no value
// match, match mask or timestamps), SWJ_Pins, SWJ_Clock, SWJ_Sequence,
// SWD_Configure, JTAG_Sequence, JTAG_Configure (IR lengths ignored),
// SWD_Sequence. Anything else answers 0xFF. Transfer in JTAG mode answers
// count 0: OpenOCD drives JTAG with JTAG_Sequence only.
//
// One bit on the wire: outputs set and TCK/SWCLK low for `half` cycles, the
// input sampled (through a 2-FF synchroniser, hence HALF_MIN), TCK high for
// `half` cycles. The SWD target drives SWDIO after the rising edge and JTAG TDO
// changes on the falling one: both are stable when sampled.
//
// SPDX-License-Identifier: BSD-3-Clause

module dap_core #(
    parameter int CLK_HZ   = 27000000,
    parameter int HALF_MIN = 4,         // TCK <= CLK_HZ / 8
    parameter int ALOG     = 9          // packet size 2**ALOG bytes
) (
    input  logic            clk,
    input  logic            rst,

    input  logic            req_we,
    input  logic [ALOG-1:0] req_wa,
    input  logic [7:0]      req_wd,
    input  logic            req_go,     // request complete

    output logic            resp_valid,
    output logic [ALOG:0]   resp_len,
    input  logic [ALOG-1:0] resp_ra,
    output logic [7:0]      resp_rd,
    input  logic            resp_ack,

    output logic            tck,        // TCK / SWCLK
    output logic            tms,        // TMS / SWDIO out
    output logic            tms_oe,
    input  logic            swdio,      // the TMS/SWDIO pin read back, asynchronous
    output logic            tdi,
    input  logic            tdo,        // asynchronous
    output logic            trst,       // asserted high
    output logic            srst        // asserted high
);
    localparam int PSIZE = 1 << ALOG;
    localparam int HDEF  = CLK_HZ / 2000000 > HALF_MIN ? CLK_HZ / 2000000 : HALF_MIN;  // 1 MHz

    // ---------------------------------------------------------------- buffers
    logic [7:0]      req_mem [PSIZE];
    logic [7:0]      resp_mem [PSIZE];
    logic [ALOG-1:0] rp, wa, x_endwa;
    logic [7:0]      cur, wd;
    logic            we;

    always_ff @(posedge clk) begin
        if (req_we)
            req_mem[req_wa] <= req_wd;
        cur <= req_mem[rp];
        if (we)
            resp_mem[wa] <= wd;
        resp_rd <= resp_mem[resp_ra];
    end

    logic [1:0] tdo_s, dio_s;
    always_ff @(posedge clk) begin
        tdo_s <= {tdo_s[0], tdo};
        dio_s <= {dio_s[0], swdio};
    end

    // ---------------------------------------------------------------- state
    typedef enum logic [6:0] {
        S_IDLE, S_CMDW, S_CMD, S_GETW, S_GET, S_GETN, S_PUT, S_DONE, S_WAITACK,
        S_SHL, S_SHH,
        S_INFO, S_HOST, S_CONN, S_XCFG, S_PINS, S_PINSR, S_CLK, S_DIV, S_SWDCFG,
        S_SEQ, S_SEQB, S_SEQD,
        S_JSEQ, S_JINFO, S_JBYTE, S_JDATA, S_JOUT, S_JCAP,
        S_JCFG, S_JCFGB,
        S_DSEQ, S_DINFO, S_DBYTE, S_DDATA, S_DOUT, S_DCAP,
        S_XFER, S_XREQ, S_XWD, S_XFLUSH, S_XFLUSHD, S_XOP, S_XOPD, S_XFIN, S_XFIND, S_XEND,
        S_XPATCH, S_XPATCH2, S_XPATCH3,
        S_OP, S_OPREQ, S_OPTRN, S_OPACK, S_OPDATA, S_OPRP, S_OPRT, S_OPWD, S_OPWP, S_OPWAIT, S_OPIDLE
    } st_t;
    st_t st, get_ret, put_ret, sh_ret, op_ret;

    /* verilator lint_off UNUSEDSIGNAL */
    logic [47:0] acc;           // GET: up to 6 bytes LSB first; commands use the low 32 bits
    /* verilator lint_on UNUSEDSIGNAL */
    logic [3:0]  get_n, get_i;
    logic [63:0] ob;            // PUT: bytes LSB first
    logic [3:0]  put_n;

    // shifter
    logic [31:0] sh_tms, sh_tdi, cap;
    logic [5:0]  sh_n, last_n;
    logic [1:0]  sh_cap;        // 0 none, 1 TDO, 2 SWDIO
    logic        sh_oe;
    logic [15:0] half, cnt;

    // settings
    logic        jtag_mode;
    logic [1:0]  trn;           // turnaround - 1
    logic [7:0]  idle_cyc;
    logic [15:0] wait_retry;

    // sequences
    logic [8:0]  bits;          // bits left
    logic [7:0]  nseq;
    logic        seq_tms, seq_cap;

    // transfer
    logic [7:0]  x_left, x_cnt;
    logic [3:0]  x_req;
    logic [31:0] x_wd;
    logic        pending;       // an AP read is posted, its data not sent yet
    logic [3:0]  x_ack;

    // one SWD access
    logic [3:0]  op_req;        // {A3, A2, RnW, APnDP}
    logic [31:0] op_wd, op_rd;
    logic [2:0]  op_ack;
    logic        op_perr;
    logic [15:0] op_retry;

    // SWJ_Clock: half = ceil(CLK_HZ / (2 * hz))
    logic [33:0] dv_n, dv_d;
    logic [32:0] dv_r;           // remainder < divisor <= 2**33
    logic [5:0]  dv_i;

    wire [5:0] nb = bits > 9'd8 ? 6'd8 : bits[5:0];     // bits in the next byte
    wire [7:0] cap_byte = 8'(cap >> (6'd32 - last_n));  // the last last_n bits, first one in bit 0
    wire [33:0] dv_t = {dv_r, dv_n[33]};

    always_ff @(posedge clk) begin
        we <= 1'b0;
        case (st)
            // ------------------------------------------------ packet
            S_IDLE: if (req_go) begin
                rp <= '0;
                st <= S_CMDW;
            end
            S_CMDW: st <= S_CMD;
            S_CMD: begin
                rp      <= rp + 1'b1;
                we      <= 1'b1;
                wa      <= '0;
                wd      <= cur;
                put_ret <= S_DONE;
                st      <= S_GETW;
                get_n   <= 4'd1;
                case (cur)
                    8'h00: get_ret <= S_INFO;
                    8'h01: begin get_n <= 4'd2; get_ret <= S_HOST; end
                    8'h02: get_ret <= S_CONN;
                    8'h03: begin ob <= '0; put_n <= 4'd1; st <= S_PUT; end
                    8'h0A: begin ob <= '0; put_n <= 4'd2; st <= S_PUT; end
                    8'h04: begin get_n <= 4'd5; get_ret <= S_XCFG; end
                    8'h05: begin get_n <= 4'd2; get_ret <= S_XFER; end
                    8'h10: begin get_n <= 4'd6; get_ret <= S_PINS; end
                    8'h11: begin get_n <= 4'd4; get_ret <= S_CLK; end
                    8'h12: get_ret <= S_SEQ;
                    8'h13: get_ret <= S_SWDCFG;
                    8'h14: get_ret <= S_JSEQ;
                    8'h15: get_ret <= S_JCFG;
                    8'h1D: get_ret <= S_DSEQ;
                    default: begin wd <= 8'hFF; st <= S_DONE; end
                endcase
            end

            // GET: get_n bytes into acc, then get_ret. cur is valid one cycle after rp settles.
            S_GETW: begin
                acc   <= '0;
                get_i <= '0;
                st    <= S_GET;
            end
            S_GET: begin
                acc[8 * get_i +: 8] <= cur;
                rp    <= rp + 1'b1;
                get_i <= get_i + 1'b1;
                st    <= get_i + 1'b1 == get_n ? get_ret : S_GETN;
            end
            S_GETN: st <= S_GET;
            // PUT: put_n bytes of ob after wa, then put_ret
            S_PUT: begin
                if (put_n == 0)
                    st <= put_ret;
                else begin
                    we    <= 1'b1;
                    wa    <= wa + 1'b1;
                    wd    <= ob[7:0];
                    ob    <= ob >> 8;
                    put_n <= put_n - 1'b1;
                end
            end
            S_DONE: begin
                resp_len   <= {1'b0, wa} + 1'b1;
                resp_valid <= 1'b1;
                st         <= S_WAITACK;
            end
            S_WAITACK: if (resp_ack) begin
                resp_valid <= 1'b0;
                st         <= S_IDLE;
            end

            // ------------------------------------------------ shifter: sh_n bits, then sh_ret
            S_SHL: begin
                tck    <= 1'b0;
                tms    <= sh_tms[0];
                tdi    <= sh_tdi[0];
                tms_oe <= sh_oe;
                if (cnt == half) begin
                    cnt <= 16'd1;
                    if (sh_cap != 2'd0)
                        cap <= {sh_cap == 2'd1 ? tdo_s[1] : dio_s[1], cap[31:1]};
                    st <= S_SHH;
                end else
                    cnt <= cnt + 1'b1;
            end
            S_SHH: begin
                tck <= 1'b1;
                if (cnt == half) begin
                    cnt    <= 16'd1;
                    sh_tms <= sh_tms >> 1;
                    sh_tdi <= sh_tdi >> 1;
                    sh_n   <= sh_n - 1'b1;
                    st     <= sh_n == 6'd1 ? sh_ret : S_SHL;
                end else
                    cnt <= cnt + 1'b1;
            end

            // ------------------------------------------------ simple commands
            S_INFO: begin
                st <= S_PUT;
                case (acc[7:0])
                    8'hF0: begin ob <= 64'h03_01; put_n <= 4'd2; end                    // SWD | JTAG
                    8'hFE: begin ob <= 64'h01_01; put_n <= 4'd2; end                    // packet count
                    8'hFF: begin ob <= {40'h0, 16'(PSIZE), 8'h02}; put_n <= 4'd3; end   // packet size
                    8'h04: begin ob <= 64'h00_30_2E_31_2E_32_06; put_n <= 4'd7; end     // "2.1.0"
                    default: begin ob <= '0; put_n <= 4'd1; end
                endcase
            end
            S_HOST: begin ob <= '0; put_n <= 4'd1; st <= S_PUT; end
            S_CONN: begin
                put_n  <= 4'd1;
                st     <= S_PUT;
                tms_oe <= 1'b1;
                if (acc[7:0] == 8'd2) begin
                    jtag_mode <= 1'b1;
                    ob        <= 64'h02;
                end else if (acc[7:0] <= 8'd1) begin
                    jtag_mode <= 1'b0;
                    ob        <= 64'h01;
                end else
                    ob <= '0;
            end
            S_XCFG: begin       // idle cycles, WAIT retries, match retries (unused)
                idle_cyc   <= acc[7:0];
                wait_retry <= acc[23:8];
                ob <= '0; put_n <= 4'd1; st <= S_PUT;
            end
            S_PINS: begin       // output, select, wait (unused)
                if (acc[8])  tck <= acc[0];
                if (acc[9])  begin tms <= acc[1]; tms_oe <= 1'b1; end
                if (acc[10]) tdi <= acc[2];
                if (acc[13]) trst <= !acc[5];
                if (acc[15]) srst <= !acc[7];
                st <= S_PINSR;
            end
            S_PINSR: begin
                ob <= {56'h0, !srst, 1'b0, !trst, 1'b0, tdo_s[1], tdi, dio_s[1], tck};
                put_n <= 4'd1; st <= S_PUT;
            end
            S_CLK: begin
                if (acc[31:0] == 32'd0) begin
                    ob <= 64'hFF; put_n <= 4'd1; st <= S_PUT;
                end else begin
                    dv_n <= 34'(CLK_HZ) + {1'b0, acc[31:0], 1'b0} - 34'd1;
                    dv_d <= {1'b0, acc[31:0], 1'b0};
                    dv_r <= '0;
                    dv_i <= 6'd34;
                    st   <= S_DIV;
                end
            end
            S_DIV: begin        // restoring division, the quotient replaces dv_n
                if (dv_i == 6'd0) begin
                    half <= dv_n < 34'(HALF_MIN) ? 16'(HALF_MIN) : dv_n > 34'hFFFF ? 16'hFFFF : dv_n[15:0];
                    ob <= '0; put_n <= 4'd1; st <= S_PUT;
                end else begin
                    dv_r <= 33'(dv_t >= dv_d ? dv_t - dv_d : dv_t);
                    dv_n <= {dv_n[32:0], dv_t >= dv_d};
                    dv_i <= dv_i - 1'b1;
                end
            end
            S_SWDCFG: begin
                trn <= acc[1:0];
                ob <= '0; put_n <= 4'd1; st <= S_PUT;
            end

            // ------------------------------------------------ SWJ_Sequence: count (0 = 256), TMS/SWDIO bits
            S_SEQ: begin
                bits <= acc[7:0] == 8'd0 ? 9'd256 : {1'b0, acc[7:0]};
                st   <= S_SEQB;
            end
            S_SEQB: begin
                if (bits == 9'd0) begin
                    ob <= '0; put_n <= 4'd1; st <= S_PUT;
                end else begin
                    get_n <= 4'd1; get_ret <= S_SEQD; st <= S_GETW;
                end
            end
            S_SEQD: begin
                sh_tms <= {24'h0, acc[7:0]};
                sh_tdi <= {32{tdi}};
                sh_n   <= nb;
                sh_cap <= 2'd0;
                sh_oe  <= 1'b1;
                bits   <= bits - 9'(nb);
                cnt    <= 16'd1;
                sh_ret <= S_SEQB;
                st     <= S_SHL;
            end

            // ------------------------------------------------ JTAG_Sequence: status, then the captured TDO bytes
            S_JSEQ: begin
                nseq <= acc[7:0];
                we <= 1'b1; wa <= wa + 1'b1; wd <= 8'h00;
                st <= S_JINFO;
            end
            S_JINFO: begin
                if (nseq == 8'd0)
                    st <= S_DONE;
                else begin
                    nseq <= nseq - 1'b1;
                    get_n <= 4'd1; get_ret <= S_JBYTE; st <= S_GETW;
                end
            end
            S_JBYTE: begin      // info: [5:0] TCK cycles (0 = 64), [6] TMS, [7] capture TDO
                bits    <= acc[5:0] == 6'd0 ? 9'd64 : {3'b0, acc[5:0]};
                seq_tms <= acc[6];
                seq_cap <= acc[7];
                st      <= S_JDATA;
            end
            S_JDATA: begin
                if (bits == 9'd0)
                    st <= S_JINFO;
                else begin
                    get_n <= 4'd1; get_ret <= S_JOUT; st <= S_GETW;
                end
            end
            S_JOUT: begin
                sh_tms <= {32{seq_tms}};
                sh_tdi <= {24'h0, acc[7:0]};
                sh_n   <= nb;
                last_n <= nb;
                sh_cap <= seq_cap ? 2'd1 : 2'd0;
                sh_oe  <= 1'b1;
                bits   <= bits - 9'(nb);
                cnt    <= 16'd1;
                sh_ret <= S_JCAP;
                st     <= S_SHL;
            end
            S_JCAP: begin
                if (seq_cap) begin
                    we <= 1'b1; wa <= wa + 1'b1; wd <= cap_byte;
                end
                st <= S_JDATA;
            end

            // ------------------------------------------------ JTAG_Configure: count, IR lengths (unused)
            S_JCFG: begin
                nseq <= acc[7:0];
                st   <= S_JCFGB;
            end
            S_JCFGB: begin
                if (nseq == 8'd0) begin
                    ob <= '0; put_n <= 4'd1; st <= S_PUT;
                end else begin
                    nseq <= nseq - 1'b1;
                    get_n <= 4'd1; get_ret <= S_JCFGB; st <= S_GETW;
                end
            end

            // ------------------------------------------------ SWD_Sequence: status, then the input bytes
            S_DSEQ: begin
                nseq <= acc[7:0];
                we <= 1'b1; wa <= wa + 1'b1; wd <= 8'h00;
                st <= S_DINFO;
            end
            S_DINFO: begin
                if (nseq == 8'd0)
                    st <= S_DONE;
                else begin
                    nseq <= nseq - 1'b1;
                    get_n <= 4'd1; get_ret <= S_DBYTE; st <= S_GETW;
                end
            end
            S_DBYTE: begin      // info: [5:0] cycles (0 = 64), [7] input
                bits    <= acc[5:0] == 6'd0 ? 9'd64 : {3'b0, acc[5:0]};
                seq_cap <= acc[7];
                st      <= S_DDATA;
            end
            S_DDATA: begin
                if (bits == 9'd0)
                    st <= S_DINFO;
                else if (seq_cap) begin
                    acc <= '0;
                    st  <= S_DOUT;
                end else begin
                    get_n <= 4'd1; get_ret <= S_DOUT; st <= S_GETW;
                end
            end
            S_DOUT: begin
                sh_tms <= {24'h0, acc[7:0]};
                sh_tdi <= {32{tdi}};
                sh_n   <= nb;
                last_n <= nb;
                sh_cap <= seq_cap ? 2'd2 : 2'd0;
                sh_oe  <= !seq_cap;
                bits   <= bits - 9'(nb);
                cnt    <= 16'd1;
                sh_ret <= S_DCAP;
                st     <= S_SHL;
            end
            S_DCAP: begin
                if (seq_cap) begin
                    we <= 1'b1; wa <= wa + 1'b1; wd <= cap_byte;
                end
                st <= S_DDATA;
            end

            // ------------------------------------------------ Transfer: 05, count, ack, read data
            S_XFER: begin       // acc = {count, DAP index}
                x_left  <= acc[15:8];
                x_cnt   <= 8'd0;
                x_ack   <= 4'd0;
                pending <= 1'b0;
                wa      <= ALOG'(2);    // read data from byte 3
                x_endwa <= ALOG'(2);
                st      <= jtag_mode ? S_XPATCH : S_XREQ;
            end
            S_XREQ: begin
                if (x_left == 8'd0)
                    st <= S_XFIN;
                else begin
                    x_left <= x_left - 1'b1;
                    get_n <= 4'd1; get_ret <= S_XWD; st <= S_GETW;
                end
            end
            S_XWD: begin        // acc = request: [0] APnDP, [1] RnW, [3:2] A, [4] match value, [5] match mask, [7] timestamp
                x_req <= acc[3:0];
                if (acc[4] || acc[5] || acc[7])
                    st <= S_XEND;
                else if (!acc[1]) begin
                    get_n <= 4'd4; get_ret <= S_XFLUSH; st <= S_GETW;
                end else
                    st <= S_XFLUSH;
            end
            S_XFLUSH: begin
                if (!x_req[1])
                    x_wd <= acc[31:0];
                if (pending && !(x_req[1] && x_req[0])) begin  // not an AP read: collect the posted one first
                    op_req <= 4'b1110;                      // DP read RDBUFF (A = 0xC)
                    op_ret <= S_XFLUSHD;
                    st     <= S_OP;
                end else
                    st <= S_XOP;
            end
            S_XFLUSHD: begin
                x_ack <= {op_perr, op_ack};
                if (op_ack != 3'd1 || op_perr)
                    st <= S_XEND;
                else begin
                    pending <= 1'b0;
                    x_cnt   <= x_cnt + 1'b1;
                    ob <= {32'h0, op_rd}; put_n <= 4'd4; put_ret <= S_XOP; st <= S_PUT;
                end
            end
            S_XOP: begin
                op_req <= x_req[3:0];
                op_wd  <= x_wd;
                op_ret <= S_XOPD;
                st     <= S_OP;
            end
            S_XOPD: begin
                x_ack   <= {op_perr, op_ack};
                put_ret <= S_XREQ;
                if (op_ack != 3'd1 || op_perr)
                    st <= S_XEND;
                else if (x_req[1] && x_req[0]) begin      // AP read: its data is the previous AP read's
                    pending <= 1'b1;
                    if (pending) begin
                        x_cnt <= x_cnt + 1'b1;
                        ob <= {32'h0, op_rd}; put_n <= 4'd4; st <= S_PUT;
                    end else
                        st <= S_XREQ;
                end else if (x_req[1]) begin              // DP read
                    x_cnt <= x_cnt + 1'b1;
                    ob <= {32'h0, op_rd}; put_n <= 4'd4; st <= S_PUT;
                end else begin                            // write
                    x_cnt <= x_cnt + 1'b1;
                    st    <= S_XREQ;
                end
            end
            S_XFIN: begin
                if (pending) begin
                    op_req <= 4'b1110;
                    op_ret <= S_XFIND;
                    st     <= S_OP;
                end else
                    st <= S_XEND;
            end
            S_XFIND: begin
                x_ack <= {op_perr, op_ack};
                if (op_ack == 3'd1 && !op_perr) begin
                    pending <= 1'b0;
                    x_cnt   <= x_cnt + 1'b1;
                    ob <= {32'h0, op_rd}; put_n <= 4'd4; put_ret <= S_XEND; st <= S_PUT;
                end else
                    st <= S_XEND;
            end
            S_XEND: begin       // 8 idle cycles, so the last write completes before the clock stops
                x_endwa <= wa;
                sh_tms <= '0; sh_tdi <= {32{tdi}}; sh_n <= 6'd8; sh_cap <= 2'd0; sh_oe <= 1'b1;
                cnt <= 16'd1; sh_ret <= S_XPATCH; st <= S_SHL;
            end
            S_XPATCH: begin
                we <= 1'b1; wa <= ALOG'(1); wd <= x_cnt;
                st <= S_XPATCH2;
            end
            S_XPATCH2: begin
                we <= 1'b1; wa <= ALOG'(2); wd <= {4'h0, x_ack};
                st <= S_XPATCH3;
            end
            S_XPATCH3: begin
                wa <= x_endwa;
                st <= S_DONE;
            end

            // ------------------------------------------------ one SWD access: op_req, op_wd -> op_ack, op_rd, op_perr
            S_OP: begin
                op_retry <= wait_retry;
                st       <= S_OPREQ;
            end
            S_OPREQ: begin      // start, APnDP, RnW, A2, A3, parity, stop, park
                sh_tms  <= {24'h0, 1'b1, 1'b0, ^op_req, op_req, 1'b1};
                sh_tdi  <= {32{tdi}}; sh_n <= 6'd8; sh_cap <= 2'd0; sh_oe <= 1'b1;
                op_perr <= 1'b0;
                cnt <= 16'd1; sh_ret <= S_OPTRN; st <= S_SHL;
            end
            S_OPTRN: begin
                sh_n <= 6'(trn) + 6'd1; sh_cap <= 2'd0; sh_oe <= 1'b0;
                cnt <= 16'd1; sh_ret <= S_OPACK; st <= S_SHL;
            end
            S_OPACK: begin
                sh_n <= 6'd3; sh_cap <= 2'd2; sh_oe <= 1'b0;
                cnt <= 16'd1; sh_ret <= S_OPDATA; st <= S_SHL;
            end
            S_OPDATA: begin     // cap[31:29] = ACK, first bit in 29
                op_ack <= cap[31:29];
                sh_oe  <= 1'b0;
                cnt    <= 16'd1;
                st     <= S_SHL;
                if (cap[31:29] == 3'd1) begin
                    if (op_req[1]) begin            // read: 32 data bits
                        sh_n <= 6'd32; sh_cap <= 2'd2; sh_ret <= S_OPRP;
                    end else begin                  // write: turnaround first
                        sh_n <= 6'(trn) + 6'd1; sh_cap <= 2'd0; sh_ret <= S_OPWD;
                    end
                end else if (cap[31:29] == 3'd2 || cap[31:29] == 3'd4) begin
                    sh_n <= 6'(trn) + 6'd1; sh_cap <= 2'd0; sh_ret <= S_OPWAIT;
                end else begin                      // no answer: clock through a possible data phase
                    sh_n <= 6'd33 + 6'(trn) + 6'd1; sh_cap <= 2'd0; sh_ret <= S_OPIDLE;
                end
            end
            S_OPRP: begin
                op_rd <= cap;
                sh_n <= 6'd1; sh_cap <= 2'd2; sh_oe <= 1'b0;
                cnt <= 16'd1; sh_ret <= S_OPRT; st <= S_SHL;
            end
            S_OPRT: begin
                op_perr <= cap[31] != ^op_rd;
                sh_n <= 6'(trn) + 6'd1; sh_cap <= 2'd0; sh_oe <= 1'b0;
                cnt <= 16'd1; sh_ret <= S_OPIDLE; st <= S_SHL;
            end
            S_OPWD: begin
                sh_tms <= op_wd; sh_n <= 6'd32; sh_cap <= 2'd0; sh_oe <= 1'b1;
                cnt <= 16'd1; sh_ret <= S_OPWP; st <= S_SHL;
            end
            S_OPWP: begin
                sh_tms <= {31'h0, ^op_wd}; sh_n <= 6'd1; sh_cap <= 2'd0; sh_oe <= 1'b1;
                cnt <= 16'd1; sh_ret <= S_OPIDLE; st <= S_SHL;
            end
            S_OPWAIT: begin
                if (op_ack == 3'd2 && op_retry != 16'd0) begin
                    op_retry <= op_retry - 1'b1;
                    st       <= S_OPREQ;
                end else
                    st <= S_OPIDLE;
            end
            S_OPIDLE: begin
                if (idle_cyc != 8'd0) begin
                    sh_tms <= '0; sh_n <= idle_cyc > 8'd32 ? 6'd32 : idle_cyc[5:0]; sh_cap <= 2'd0; sh_oe <= 1'b1;
                    cnt <= 16'd1; sh_ret <= op_ret; st <= S_SHL;
                end else
                    st <= op_ret;
            end

            default: st <= S_IDLE;
        endcase

        if (rst) begin
            st         <= S_IDLE;
            resp_valid <= 1'b0;
            resp_len   <= '0;
            tck        <= 1'b0;
            tms        <= 1'b1;
            tms_oe     <= 1'b1;
            tdi        <= 1'b0;
            trst       <= 1'b0;
            srst       <= 1'b0;
            half       <= 16'(HDEF);
            cnt        <= 16'd1;
            jtag_mode  <= 1'b0;
            trn        <= 2'd0;
            idle_cyc   <= 8'd0;
            wait_retry <= 16'd100;
        end
    end
endmodule
