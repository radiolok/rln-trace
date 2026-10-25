// Настройки Gowin USB 2.0 SoftPHY (как пишет IP Core Generator, шаблон — в USBTwoSoftPHY.dll):
// UTMI, LVDS Single (без D_LVDS), RX Advance (V_120: приём на 120 МГц — для Arora V; в Normal
// приём HS на SLogic16U3 разваливался), TX Delay 0, Arora V.
`define module_name USB2_0_SoftPHY_Top
`define TX_DELAY_0_BIT
`define UTMI
`define V_120
`define DEFAULT_VENDOR_ID_HIGH 8'h00
`define DEFAULT_VENDOR_ID_LOW 8'h00
`define DEFAULT_PRODUCT_ID_HIGH 8'h00
`define DEFAULT_PRODUCT_ID_LOW 8'h00
`define GW5AT
