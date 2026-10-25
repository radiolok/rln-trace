// Общее для образов на SerDes Q0 SLogic16U3 (sdprobe, usb2): частотомер и заглушка
// протокольной части USB3_0_PHY_Top для Serdes_Top из serdes.v.

// Тактов fclk за окно: счёт в домене fclk, перенос кодом Грея, разность по tick.
module fmeter (input wire fclk, clk, tick, output reg [31:0] cnt = 0);
    reg [31:0] c = 0, gr = 0;
    always @(posedge fclk) begin
        c <= c + 1'b1;
        gr <= c ^ (c >> 1);
    end
    reg [31:0] g1 = 0, g2 = 0, last = 0;
    reg [31:0] b;
    integer k;
    always @* begin
        b[31] = g2[31];
        for (k = 30; k >= 0; k = k - 1)
            b[k] = b[k + 1] ^ g2[k];
    end
    always @(posedge clk) begin
        {g2, g1} <= {g1, gr};
        if (tick) begin
            cnt <= b - last;
            last <= b;
        end
    end
endmodule

// Заглушка протокольной части: сброс линии, такты FIFO = такты PCS, данных нет.
module USB3_0_PHY_Top (
    output pclk, output [31:0] PipeRxData, output [3:0] PipeRxDataK, output PipeRxDataValid,
    output RxElecIdle, output [2:0] RxStatus, output PhyStatus, output PowerPresent,
    output serdes_fabric_rstn_o, output serdes_fabric_tx_clk_o, output serdes_pcs_tx_rst_o,
    output serdes_fabric_tx_vld_o, output [79:0] serdes_txdata_o, output serdes_fabric_rx_clk_o,
    output serdes_pcs_rx_rst_o, output serdes_rxfifo_rd_en_o,
    input ref_clk, input phy_resetn, input [31:0] PipeTxData, input [3:0] PipeTxDataK,
    input TxDetectRx_loopback, input TxElecIdle, input RxPolarity, input RxEqTraining,
    input RxTermination, input TxOnesZeros, input [1:0] PowerDown, input ElasticityBufferMode,
    input serdes_q0_qpll0_ok_i, input serdes_q0_qpll1_ok_i, input serdes_q1_qpll0_ok_i,
    input serdes_q1_qpll1_ok_i, input serdes_cpll_ok_i, input serdes_pcs_tx_clk_i,
    input [4:0] serdes_tx_fifo_wrusewd_i, input serdes_pcs_rx_clk_i, input serdes_pma_rx_lock_i,
    input serdes_rxfifo_aempty_i, input [4:0] serdes_rx_fifo_rdusewd_i, input [87:0] serdes_rxdata_i,
    input serdes_rx_vld_i, input serdes_rxelecidle_i, input [5:0] serdes_astat_i
);
    assign pclk = serdes_pcs_tx_clk_i;
    assign {PipeRxData, PipeRxDataK, PipeRxDataValid, RxStatus, PhyStatus, PowerPresent} = 0;
    assign RxElecIdle = serdes_rxelecidle_i;
    assign serdes_fabric_rstn_o = phy_resetn;
    assign serdes_pcs_tx_rst_o = ~phy_resetn;
    assign serdes_pcs_rx_rst_o = ~phy_resetn;
    assign serdes_fabric_tx_clk_o = serdes_pcs_tx_clk_i;
    assign serdes_fabric_rx_clk_o = serdes_pcs_rx_clk_i;
    assign serdes_fabric_tx_vld_o = 1'b0;
    assign serdes_txdata_o = 80'd0;
    assign serdes_rxfifo_rd_en_o = 1'b0;
endmodule
