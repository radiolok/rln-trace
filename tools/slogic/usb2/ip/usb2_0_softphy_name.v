// Настройки Gowin USB 2.0 SoftPHY (как пишет IP Core Generator, шаблон — в USBTwoSoftPHY.dll):
// UTMI, LVDS Single (без D_LVDS), RX Normal, TX Delay 1, Arora V — как в примере Sipeed для
// Tang Mega 138K Pro (usb2_soft/usb_cy_streamer). На Arora V fclk_i = 960 МГц, а не 480 (IPUG781).
`define module_name USB2_0_SoftPHY_Top
`define TX_DELAY_1_BIT
`define UTMI
`define DEFAULT_VENDOR_ID_HIGH 8'h00
`define DEFAULT_VENDOR_ID_LOW 8'h00
`define DEFAULT_PRODUCT_ID_HIGH 8'h00
`define DEFAULT_PRODUCT_ID_LOW 8'h00
`define GW5AT
