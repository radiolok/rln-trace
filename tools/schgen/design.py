"""Open Debug+Trace probe (direction B): GW2AR-18 QN88 + CH569W, MIPI20, USB3, 2x SMA."""
import sch, parts

R0402 = 'Resistor_SMD:R_0402_1005Metric'
R0805 = 'Resistor_SMD:R_0805_2012Metric'
C0402 = 'Capacitor_SMD:C_0402_1005Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
C0805 = 'Capacitor_SMD:C_0805_2012Metric'
LED = 'LED_SMD:LED_0603_1608Metric'
L1210 = 'Inductor_SMD:L_1210_3225Metric'
FB0603 = 'Inductor_SMD:L_0603_1608Metric'

proj = sch.Project('probe')
parts.build(proj)

_n = {'U': 2, 'J': 4, 'JP': 3}


def ref(prefix):
    _n[prefix] = _n.get(prefix, 0) + 1
    return f'{prefix}{_n[prefix]}'


# --------------------------------------------------------------------------- helpers
def RV(sh, val, x, y, top, bot, fp=R0402, r=None, sym='R', dnp=False, fields=None):
    """vertical 2-pin passive: pin1 top, pin2 bottom"""
    r = r or ref({'R': 'R', 'C': 'C', 'L': 'L', 'FerriteBead_Small': 'FB', 'Fuse': 'F'}[sym])
    return sh.place(sym, r, val, x, y, 0, fp=fp, nets={'1': top, '2': bot}, pwr_stub=0,
                    dnp=dnp, fields=fields)


def RH(sh, val, x, y, left, right, fp=R0402, r=None, sym='R', dnp=False):
    """horizontal 2-pin passive: pin1 left, pin2 right"""
    r = r or ref({'R': 'R', 'C': 'C', 'L': 'L', 'FerriteBead_Small': 'FB', 'Fuse': 'F'}[sym])
    return sh.place(sym, r, val, x, y, 90, fp=fp, nets={'1': left, '2': right}, pwr_stub=0, dnp=dnp)


def CV(sh, val, x, y, top='+3V3', bot='GND', fp=C0402):
    return RV(sh, val, x, y, top, bot, fp=fp, sym='C')


def caps(sh, x, y, specs, top, bot='GND', step=7.62):
    for k, (val, fp) in enumerate(specs):
        CV(sh, val, x + k * step, y, top, bot, fp)


def led(sh, x, y, net, color, rv='1k'):
    """net -> R -> LED -> GND, horizontal"""
    mid = f'{net}_A'
    RH(sh, rv, x, y, net, mid)
    sh.place('LED', ref('D'), color, x + 15.24, y, 180, fp=LED, nets={'2': mid, '1': 'GND'}, pwr_stub=0)


# =========================================================================== sheet: USB + power
S = proj.sheet('usb_power.kicad_sch', 'USB-C, USB3 mux, power')
S.frame(12.7, 12.7, 228.6, 182.88, 'USB-C 3.2 Gen1 receptacle, SS orientation mux, ESD')
S.frame(233.68, 12.7, 406.4, 182.88, 'Power: VBUS -> 5V -> 3V3 / 1V0 (TLV62569)')
S.frame(12.7, 187.96, 228.6, 254.0, 'CC orientation detect (UFP, Rd = 5.1k)')
S.frame(233.68, 187.96, 330.2, 254.0, 'Power flags, indication')

J = S.place('USB_C_Receptacle', 'J1', 'USB_C_Receptacle_USB3', 38.1, 96.52,
            fp='Connector_USB:USB_C_Receptacle_Amphenol_12401610E4-2A',
            nets={'A4': 'VBUS', 'A5': 'CC1', 'B5': 'CC2', 'A6': 'USB_DP', 'B6': 'USB_DP',
                  'A7': 'USB_DM', 'B7': 'USB_DM', 'A8': 'NC', 'B8': 'NC',
                  'A2': 'TX1_P', 'A3': 'TX1_N', 'B11': 'RX1_P', 'B10': 'RX1_N',
                  'B2': 'TX2_P', 'B3': 'TX2_N', 'A11': 'RX2_P', 'A10': 'RX2_N',
                  'A1': 'GND', 'S1': 'USB_SHIELD'}, pwr_stub=2.54)
RV(S, '1M', 22.86, 157.48, 'USB_SHIELD', 'GND')
CV(S, '4.7n/250V', 30.48, 157.48, 'USB_SHIELD', 'GND')
S.note(17.78, 165.1, 'Shield: 1M || 4.7nF to GND', 1.27)

# ESD on the connector side
S.place('USBLC6-2SC6', ref('U'), 'USBLC6-2SC6', 101.6, 38.1,
        nets={'1': 'USB_DP', '6': 'USB_DP', '3': 'USB_DM', '4': 'USB_DM', '5': 'VBUS', '2': 'GND'},
        pwr_stub=2.54)
S.place('TPD4EUSB30', ref('U'), 'TPD4EUSB30', 101.6, 78.74,
        nets={'1': 'TX1_P', '2': 'TX1_N', '4': 'RX1_P', '5': 'RX1_N', '3': 'GND'})
S.place('TPD4EUSB30', ref('U'), 'TPD4EUSB30', 101.6, 114.3,
        nets={'1': 'TX2_P', '2': 'TX2_N', '4': 'RX2_P', '5': 'RX2_N', '3': 'GND'})

# SS mux
S.place('CBTL02043A', ref('U'), 'CBTL02043A', 175.26, 104.14,
        nets={'1': '+3V3', '5': 'GND', '3': 'SSTX_P_AC', '4': 'SSTX_N_AC', '7': 'SSRX_P',
              '8': 'SSRX_N', '9': 'USB_FLIP', '2': 'GND',
              '19': 'TX1_P', '18': 'TX1_N', '17': 'RX1_P', '16': 'RX1_N',
              '15': 'TX2_P', '14': 'TX2_N', '13': 'RX2_P', '12': 'RX2_N'}, pwr_stub=2.54)
CV(S, '100n', 195.58, 76.2)
CV(S, '100n', 203.2, 76.2)
RH(S, '100n', 137.16, 86.36, 'SSTX_P', 'SSTX_P_AC', fp='Capacitor_SMD:C_0201_0603Metric', sym='C')
RH(S, '100n', 137.16, 93.98, 'SSTX_N', 'SSTX_N_AC', fp='Capacitor_SMD:C_0201_0603Metric', sym='C')
S.note(124.46, 132.08, 'SSTX AC coupling 100nF (0201) at device side.\n'
       'Mux: SEL=0 -> A<->B (TX1/RX1), SEL=1 -> A<->C (TX2/RX2).\n'
       'USB_FLIP=0 when CC1 is the active CC line.\n'
       'Diff pairs: 90 Ohm, length-matched; mux next to J1.', 1.27)

# CC detection
RV(S, '5.1k', 30.48, 213.36, 'CC1', 'GND')
RV(S, '5.1k', 40.64, 213.36, 'CC2', 'GND')
RV(S, '200k', 63.5, 205.74, '+3V3', 'CC_REF')
RV(S, '10k', 63.5, 226.06, 'CC_REF', 'GND')
S.place('TLV7031DBV', ref('U'), 'TLV7031DBV', 116.84, 215.9,
        nets={'5': '+3V3', '2': 'GND', '3': 'CC_REF', '4': 'CC1', '1': 'USB_FLIP'}, pwr_stub=2.54)
CV(S, '100n', 144.78, 213.36)
S.note(152.4, 205.74, 'Comparator: OUT = (CC_REF 0.157V > CC1)\n'
       'CC1 active (0.25..2.04V) -> USB_FLIP=0 -> TX1/RX1\n'
       'CC2 active (CC1 ~ 0V)    -> USB_FLIP=1 -> TX2/RX2\n'
       'USB_FLIP also read by CH569 PB3.', 1.27)

# power: fuse, bucks
RV(S, '1.5A PTC', 248.92, 45.72, 'VBUS', '+5V', fp='Fuse:Fuse_1206_3216Metric', sym='Fuse')
CV(S, '10u', 259.08, 45.72, 'VBUS', 'GND', C0805)
CV(S, '10u', 266.7, 45.72, '+5V', 'GND', C0805)

# 3V3 buck
S.place('TLV62569DDC', ref('U'), 'TLV62569DDC', 299.72, 63.5,
        nets={'4': '+5V', '1': '+5V', '2': 'GND', '3': 'SW_3V3', '6': 'FB_3V3', '5': 'PG_3V3'},
        pwr_stub=2.54)
CV(S, '10u', 266.7, 76.2, '+5V', 'GND', C0805)
RH(S, '2.2u', 332.74, 50.8, 'SW_3V3', '+3V3', fp=L1210, sym='L')
RV(S, '150k', 355.6, 66.04, '+3V3', 'FB_3V3')
CV(S, '22p', 363.22, 66.04, '+3V3', 'FB_3V3')
RV(S, '33.2k', 355.6, 83.82, 'FB_3V3', 'GND')
CV(S, '22u', 375.92, 66.04, '+3V3', 'GND', C0805)
CV(S, '22u', 383.54, 66.04, '+3V3', 'GND', C0805)
RH(S, '100k', 332.74, 91.44, 'PG_3V3', '+3V3')
S.note(320.04, 101.6, '3V3: Vout = 0.6 * (1 + 150k/33.2k) = 3.31 V, 2 A\n'
       'L = 2.2 uH, Isat >= 3 A', 1.27)

# 1V0 buck (enabled by PG of 3V3)
S.place('TLV62569DDC', ref('U'), 'TLV62569DDC', 299.72, 137.16,
        nets={'4': '+5V', '1': 'PG_3V3', '2': 'GND', '3': 'SW_1V0', '6': 'FB_1V0', '5': 'NC'},
        pwr_stub=2.54)
CV(S, '10u', 266.7, 149.86, '+5V', 'GND', C0805)
RH(S, '2.2u', 332.74, 124.46, 'SW_1V0', '+1V0', fp=L1210, sym='L')
RV(S, '100k', 355.6, 139.7, '+1V0', 'FB_1V0')
CV(S, '22p', 363.22, 139.7, '+1V0', 'FB_1V0')
RV(S, '150k', 355.6, 157.48, 'FB_1V0', 'GND')
CV(S, '22u', 375.92, 139.7, '+1V0', 'GND', C0805)
CV(S, '22u', 383.54, 139.7, '+1V0', 'GND', C0805)
S.note(320.04, 165.1, '1V0 (GW2AR VCC/VCCPLL): Vout = 0.6 * (1 + 100k/150k) = 1.00 V\n'
       'EN <- PG_3V3: core rail starts after 3V3', 1.27)

for k, net in enumerate(['VBUS', '+5V', '+3V3', '+1V0', 'GND']):
    S.flag(net, 248.92 + k * 12.7, 203.2)
led(S, 248.92, 233.68, '+3V3', 'green')

# =========================================================================== sheet: CH569W
M = proj.sheet('mcu.kicad_sch', 'CH569W USB3 bridge')
M.frame(12.7, 12.7, 200.66, 254.0, 'CH569W: USB3 SS device, HSPI 16 bit to FPGA')
M.frame(205.74, 12.7, 406.4, 120.65, 'Power decoupling (per WCH CH569W-R0 reference)')
M.frame(205.74, 125.73, 406.4, 254.0, 'Clock, boot, UART, FPGA-flash access, I2C, expansion')

hspi_l = {}
for k, pin in enumerate([15, 17, 53, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31]):
    hspi_l[str(pin)] = f'HSPI_D{k}'
hspi_l.update({'56': 'HSPI_HTCLK', '54': 'HSPI_HTREQ', '55': 'HSPI_HTACK', '52': 'HSPI_HTVLD',
               '18': 'HSPI_HTRDY', '10': 'HSPI_HRCLK', '11': 'HSPI_HRACK', '14': 'HSPI_HRVLD'})
mcu_r = {'1': 'USB_DP', '2': 'USB_DM', '4': 'SSTX_P', '5': 'SSTX_N', '7': 'SSRX_P', '8': 'SSRX_N',
         '65': 'NC', '66': 'NC', '68': 'XTAL_I', '67': 'XTAL_O', '12': 'UART_TX', '13': 'UART_RX',
         '57': 'CH_SPI_CS', '58': 'CH_SPI_CLK', '59': 'CH_SPI_MOSI', '60': 'CH_SPI_MISO',
         '40': 'NC', '35': 'NC', '32': 'TPWR_EN_N', '33': 'TPWR_FLT_N', '34': 'LED_CH',
         '36': 'USB_FLIP', '37': 'ADC_ALERT', '38': 'NC', '39': 'NC', '41': 'NC', '43': 'NC',
         '44': 'NC', '46': 'CH_PB10', '48': 'CH_PB11', '50': 'CH_PB12', '51': 'CH_PB13',
         '45': 'I2C_SCL', '47': 'I2C_SDA', '49': 'FPGA_RECONFIG_N'}
M.place('CH569W', 'U2', 'CH569W', 104.14, 129.54, unit=1, nets={**hspi_l, **mcu_r})
M.note(20.32, 241.3, 'PB15 = HD14 is also RST#: disable the RST# function in the CH569 config\n'
       '(WCH ISP tool) before the FPGA drives HSPI_D14. 10k pull-up keeps it inactive.\n'
       'HD0 low at power-up = USB ISP bootloader (BOOT button).', 1.27)

M.place('CH569W', 'U2', 'CH569W', 248.92, 45.72, unit=2,
        nets={'16': '+3V3', '42': '+3V3', '61': '+3V3', '62': '+3V3', '64': '+3V3', '3': '+3V3',
              '63': '+1V2_CH', '9': '+1V2_CH', '6': '+1V2_CH', '69': 'GND'}, pwr_stub=2.54)
caps(M, 297.18, 33.02, [('100n', C0402)] * 6 + [('3.3u', C0603)], '+3V3')
M.note(297.18, 45.72, 'VDDIO x3, V33LDO, V33GX, V33USB: 100n each + 3.3u at V33LDO', 1.27)
caps(M, 297.18, 66.04, [('100n', C0402)] * 3 + [('3.3u', C0603)], '+1V2_CH')
M.note(297.18, 78.74, '+1V2_CH = internal LDO output (V12CORE pin 63):\n'
       '100n at pins 9, 63, 6 + 3.3u at pin 63. Do not load externally.', 1.27)

# crystal 30 MHz
M.place('Crystal_GND24', ref('Y'), '30MHz', 236.22, 152.4, fp='Crystal:Crystal_SMD_3225-4Pin_3.2x2.5mm',
        nets={'1': 'XTAL_I', '3': 'XTAL_O', '2': 'GND', '4': 'GND'}, pwr_stub=2.54)
CV(M, '20p', 220.98, 172.72, 'XTAL_I', 'GND')
CV(M, '20p', 251.46, 172.72, 'XTAL_O', 'GND')

# BOOT button on HD0
RH(M, '1k', 279.4, 142.24, 'HSPI_D0', 'BOOT_N')
M.place('SW_Push', ref('SW'), 'BOOT', 299.72, 142.24, fp='Button_Switch_SMD:SW_SPST_PTS810',
        nets={'1': 'BOOT_N', '2': 'GND'}, pwr_stub=2.54)
RH(M, '10k', 279.4, 152.4, 'HSPI_D14', '+3V3')

# UART header
M.place('Conn_01x04', ref('J'), 'UART', 350.52, 147.32, 180,
        fp='Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical',
        nets={'1': 'GND', '2': 'UART_TX', '3': 'UART_RX', '4': '+3V3'}, pwr_stub=2.54)
M.note(340.36, 160.02, 'UART1: 1 GND, 2 TX (out), 3 RX (in), 4 3V3', 1.27)

# FPGA flash access (shared MSPI flash, FPGA held in RECONFIG_N=0 while CH569 writes)
for k, (a, b) in enumerate([('CH_SPI_CS', 'FL_CS'), ('CH_SPI_CLK', 'FL_CLK'),
                            ('CH_SPI_MOSI', 'FL_DI'), ('CH_SPI_MISO', 'FL_DO')]):
    RH(M, '33', 233.68, 193.04 + k * 10.16, a, b)
M.note(213.36, 236.22, 'CH569 SPI0 -> FPGA config flash (update path).\n'
       'CH569 drives only while FPGA_RECONFIG_N = 0;\n'
       'otherwise SPI0 pins stay inputs (Hi-Z).', 1.27)

# I2C pull-ups, LED
RH(M, '4.7k', 289.56, 195.58, 'I2C_SCL', '+3V3')
RH(M, '4.7k', 289.56, 205.74, 'I2C_SDA', '+3V3')
led(M, 287.02, 218.44, 'LED_CH', 'blue')

# expansion header: FPGA spares + CH569 spares
M.place('Conn_02x05_Odd_Even', ref('J'), 'EXP', 365.76, 210.82,
        fp='Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical_SMD',
        nets={'1': '+3V3', '2': 'GND', '3': 'FPGA_IO35', '4': 'CH_PB10', '5': 'FPGA_IO36',
              '6': 'CH_PB11', '7': 'FPGA_IO76', '8': 'CH_PB12', '9': 'FPGA_IO51', '10': 'CH_PB13'},
        pwr_stub=2.54)
M.note(342.9, 228.6, 'EXP: spare FPGA + CH569 GPIO (debug, test)', 1.27)

# =========================================================================== sheet: FPGA
F = proj.sheet('fpga.kicad_sch', 'GW2AR-18 QN88 FPGA')
F.frame(12.7, 12.7, 190.5, 254.0, 'GW2AR-LV18QN88C8/I7 I/O banks (all VCCIO = 3.3 V)')
F.frame(195.58, 12.7, 406.4, 116.84, 'Power and decoupling (UG115: pins 3/12/64 = VCCX/VCCIO2/6/7)')
F.frame(195.58, 121.92, 406.4, 254.0, 'Configuration (MSPI flash), JTAG, clock, LEDs')

F.place('GW2AR-18_QN88', 'U1', 'GW2AR-LV18QN88C8/I7', 101.6, 45.72, unit=1,
        nets={'69': 'HSPI_HRCLK', '70': 'HSPI_HRVLD', '71': 'HSPI_HRACK', '72': 'HSPI_HTVLD',
              '73': 'HSPI_HTREQ', '74': 'HSPI_HTACK', '75': 'HSPI_HTRDY', '76': 'FPGA_IO76',
              '77': 'HSPI_HTCLK',
              '86': 'F_SWDIO', '85': 'F_SWDIO_DIR', '84': 'F_SWCLK', '83': 'F_TDI',
              '82': 'NRST_DRV', '81': 'DBG_OE_N', '80': 'LED_G', '79': 'LED_R'})
b45 = {str(p): f'HSPI_D{k}' for k, p in enumerate(range(25, 35))}
b45.update({str(p): f'HSPI_D{10 + k}' for k, p in enumerate(range(37, 43))})
b45.update({'35': 'FPGA_IO35', '36': 'FPGA_IO36'})
F.place('GW2AR-18_QN88', 'U1', 'GW2AR-LV18QN88C8/I7', 101.6, 104.14, unit=2, nets=b45)
F.place('GW2AR-18_QN88', 'U1', 'GW2AR-LV18QN88C8/I7', 101.6, 190.5, unit=3,
        nets={'10': 'F_TRCCLK', '11': 'F_TDO', '13': 'SMA1_F', '15': 'F_NRST_SENSE',
              '16': 'TRACE_OE_N', '17': 'F_TRC_D0', '18': 'F_TRC_D1', '19': 'F_TRC_D2',
              '20': 'F_TRC_D3', '4': 'CLK_50M',
              '9': 'FPGA_RECONFIG_N', '48': 'SMA1_DIR', '49': 'SMA2_DIR', '51': 'FPGA_IO51',
              '52': 'NC', '53': 'NC', '54': 'NC', '55': 'NC', '56': 'NC', '57': 'FASTRD_N',
              '59': 'FL_CLK', '60': 'FL_CS', '61': 'FL_DI', '62': 'FL_DO', '63': 'SMA2_F',
              '87': 'MODE1', '88': 'MODE0',
              '5': 'FPGA_TMS', '6': 'FPGA_TCK', '7': 'FPGA_TDI', '8': 'FPGA_TDO'})
F.note(20.32, 236.22, 'Trace port on bank 6: TRC_CLK on GCLKT_6 (pin 10), data on 17..20 (IDDR + IODELAY).\n'
       'Timestamp ref: SMA1 on LPLL2_T_in (13), local 50 MHz on LPLL1_T_in (4).\n'
       'HSPI: data on banks 5/4, CH569 HTCLK on GCLKT_1 (77).', 1.27)

F.place('GW2AR-18_QN88', 'U1', 'GW2AR-LV18QN88C8/I7', 233.68, 60.96, unit=4,
        nets={'1': '+1V0', '22': '+1V0', '45': '+1V0', '66': '+1V0',
              '3': '+3V3', '12': '+3V3', '64': '+3V3',
              '78': '+3V3', '67': '+3V3', '58': '+3V3', '44': '+3V3', '23': '+3V3',
              '14': '+1V0_PLL', '50': '+1V0_PLL',
              '2': 'GND', '21': 'GND', '24': 'GND', '43': 'GND', '46': 'GND', '65': 'GND',
              '68': 'GND', '89': 'GND', '47': 'EXTR'}, pwr_stub=2.54)
RV(F, '10k 1%', 271.78, 86.36, 'EXTR', 'GND')
caps(F, 287.02, 30.48, [('100n', C0402)] * 4 + [('10u', C0805)], '+1V0')
F.note(287.02, 40.64, 'VCC (1,22,45,66): 4x100n + 10u', 1.27)
caps(F, 287.02, 58.42, [('100n', C0402)] * 3 + [('10u', C0805)] + [('100n', C0402)] * 5, '+3V3')
F.note(287.02, 68.58, 'VCCX/VCCIO2/6/7 (3,12,64): 3x100n + 10u; VCCIO0/1/3/4/5: 100n each', 1.27)
F.place('FerriteBead_Small', ref('FB'), '600R@100MHz', 297.18, 88.9, 90, fp=FB0603,
        nets={'1': '+1V0', '2': '+1V0_PLL'}, pwr_stub=2.54)
caps(F, 317.5, 86.36, [('100n', C0402)] * 2 + [('10u', C0805)], '+1V0_PLL')
F.flag('+1V0_PLL', 345.44, 81.28)
F.note(287.02, 99.06, 'VCCPLLL1 (14), VCCPLLR1 (50): 1.0 V via ferrite. EXTR (47): 10k 1% to GND (UG115).', 1.27)

# MSPI flash
F.place('W25Q128JVS', ref('U'), 'W25Q128JVSIQ', 236.22, 157.48, fp='Package_SO:SOIC-8_5.23x5.23mm_P1.27mm',
        nets={'1': 'FL_CS', '2': 'FL_DO', '3': 'FL_IO2', '4': 'GND', '5': 'FL_DI', '6': 'FL_CLK',
              '7': 'FL_IO3', '8': '+3V3'}, pwr_stub=2.54)
CV(F, '100n', 266.7, 142.24)
RH(F, '10k', 284.48, 139.7, 'FL_CS', '+3V3')
RH(F, '10k', 284.48, 149.86, 'FL_IO2', '+3V3')
RH(F, '10k', 284.48, 160.02, 'FL_IO3', '+3V3')
RH(F, '10k', 284.48, 170.18, 'FASTRD_N', '+3V3')
RH(F, '4.7k', 284.48, 180.34, 'MODE0', 'GND')
RH(F, '4.7k', 284.48, 190.5, 'MODE1', 'GND')
F.note(205.74, 200.66, 'MODE[2:0] = 000 -> MSPI autoboot (MODE2 internally GND in QN88).\n'
       'Verify with Gowin UG290 Table 5-2 before ordering.', 1.27)

# RECONFIG_N
RH(F, '10k', 325.12, 139.7, 'FPGA_RECONFIG_N', '+3V3')
F.place('SW_Push', ref('SW'), 'RECONFIG', 340.36, 152.4, fp='Button_Switch_SMD:SW_SPST_PTS810',
        nets={'1': 'FPGA_RECONFIG_N', '2': 'GND'}, pwr_stub=2.54)

# JTAG (ARM 10-pin 1.27 layout, works with FT2232H adapters)
F.place('Conn_02x05_Odd_Even', ref('J'), 'FPGA_JTAG', 373.38, 167.64,
        fp='Connector_PinHeader_1.27mm:PinHeader_2x05_P1.27mm_Vertical_SMD',
        nets={'1': '+3V3', '2': 'FPGA_TMS', '3': 'GND', '4': 'FPGA_TCK', '5': 'GND',
              '6': 'FPGA_TDO', '7': 'NC', '8': 'FPGA_TDI', '9': 'GND', '10': 'FPGA_RECONFIG_N'},
        pwr_stub=2.54)
RH(F, '4.7k', 320.04, 187.96, 'FPGA_TCK', 'GND')

# 50 MHz oscillator
F.place('ASE-xxxMHz', ref('X'), '50MHz', 236.22, 220.98,
        nets={'1': '+3V3', '2': 'GND', '3': 'OSC_OUT', '4': '+3V3'}, pwr_stub=2.54)
CV(F, '100n', 256.54, 205.74)
RH(F, '22', 269.24, 220.98, 'OSC_OUT', 'CLK_50M')

# LEDs
led(F, 309.88, 210.82, 'LED_G', 'green')
led(F, 309.88, 220.98, 'LED_R', 'red')

# =========================================================================== sheet: target connector
T = proj.sheet('target.kicad_sch', 'MIPI20 target interface')
T.frame(12.7, 12.7, 157.48, 175.26, 'MIPI20 (RISC-V Trace Connectors 1.0 = Cortex Debug+ETM)')
T.frame(162.56, 12.7, 406.4, 175.26, 'Level translation (VREF 1.2..3.6 V), nRESET')
T.frame(12.7, 180.34, 406.4, 254.0, 'Target power (pins 11/13), measurement')

T.place('Conn_02x10_Odd_Even', 'J2', 'MIPI20', 63.5, 60.96,
        fp='Connector_PinHeader_1.27mm:PinHeader_2x10_P1.27mm_Vertical_SMD',
        nets={'1': 'VREF_T', '3': 'GND', '5': 'GND', '7': 'GND', '9': 'GND', '11': 'P11_13',
              '13': 'P11_13', '15': 'GND', '17': 'GND', '19': 'GND',
              '2': 'T_SWDIO', '4': 'T_SWCLK', '6': 'T_TDO', '8': 'T_TDI', '10': 'T_NRST',
              '12': 'T_TRCCLK', '14': 'T_D0', '16': 'T_D1', '18': 'T_D2', '20': 'T_D3'},
        pwr_stub=2.54)
T.note(20.32, 86.36, 'Pin 1 VREF, 2 TMS/SWDIO, 4 TCK/SWCLK, 6 TDO/SWO, 8 TDI, 10 nRESET,\n'
       '12 TRC_CLK, 14/16/18/20 TRC_DATA[0..3], 9 GNDDetect = GND on probe,\n'
       '11/13 GND or TgtPwr+Cap (JP1), 7 key/GND.', 1.27)
for k, nets in enumerate([['T_SWDIO', 'T_SWCLK', 'T_TDO', 'T_TDI'],
                          ['T_NRST', 'T_TRCCLK', 'T_D0', 'T_D1'],
                          ['T_D2', 'T_D3', 'VREF_T', 'NC']]):
    T.place('TPD4E02B04DQA', ref('U'), 'TPD4E02B04DQA', 33.02 + k * 40.64, 124.46,
            nets={'1': nets[0], '2': nets[1], '4': nets[2], '5': nets[3], '3': 'GND'}, pwr_stub=2.54)
T.note(20.32, 144.78, 'ESD array at the connector, then series R (33 Ohm, tune on prototype).', 1.27)

ser = [('T_SWDIO', 'B_SWDIO'), ('T_SWCLK', 'B_SWCLK'), ('T_TDO', 'B_TDO'), ('T_TDI', 'B_TDI'),
       ('T_NRST', 'B_NRST'), ('T_TRCCLK', 'B_TRCCLK'), ('T_D0', 'B_D0'), ('T_D1', 'B_D1'),
       ('T_D2', 'B_D2'), ('T_D3', 'B_D3')]
for k, (a, b) in enumerate(ser):
    RH(T, '33', 119.38, 30.48 + k * 10.16, a, b)

# input translator: target -> FPGA (DIR=0: B->A)
T.place('SN74AVC8T245PW', ref('U'), 'SN74AVC8T245PW', 220.98, 58.42,
        nets={'1': '+3V3', '23': 'VREF_F', '24': 'VREF_F', '11': 'GND', '2': 'GND',
              '22': 'TRACE_OE_N',
              '3': 'F_TRCCLK', '4': 'F_TRC_D0', '5': 'F_TRC_D1', '6': 'F_TRC_D2', '7': 'F_TRC_D3',
              '8': 'F_TDO', '9': 'F_NRST_SENSE', '10': 'NC',
              '21': 'B_TRCCLK', '20': 'B_D0', '19': 'B_D1', '18': 'B_D2', '17': 'B_D3',
              '16': 'B_TDO', '15': 'B_NRST', '14': 'GND'}, pwr_stub=2.54)
# debug translator: SWDIO bidir, SWCLK/TDI out
T.place('SN74AVC4T245PW', ref('U'), 'SN74AVC4T245PW', 220.98, 132.08,
        nets={'1': '+3V3', '16': 'VREF_F', '8': 'GND', '15': 'DBG_OE_N', '14': 'DBG_OE_N',
              '2': 'F_SWDIO_DIR', '3': '+3V3', '4': 'F_SWDIO', '5': 'DBG_SPA', '6': 'F_SWCLK',
              '7': 'F_TDI', '13': 'B_SWDIO', '12': 'DBG_SPB', '11': 'B_SWCLK', '10': 'B_TDI'},
        pwr_stub=2.54)
caps(T, 254.0, 99.06, [('100n', C0402)], '+3V3')
caps(T, 261.62, 99.06, [('100n', C0402)] * 2, 'VREF_F')
RH(T, '10k', 274.32, 30.48, 'TRACE_OE_N', '+3V3')
RH(T, '10k', 274.32, 40.64, 'DBG_OE_N', '+3V3')
RH(T, '10k', 274.32, 50.8, 'F_SWDIO_DIR', 'GND')
RH(T, '10k', 274.32, 60.96, 'DBG_SPA', 'GND')
RH(T, '10k', 274.32, 71.12, 'DBG_SPB', 'GND')
T.note(259.08, 83.82, 'Default after power-up: both translators disabled (OE pulled high),\n'
       'SWDIO direction = target->FPGA. Firmware enables OE only when\n'
       'VREF is within 1.2..3.6 V (ADS1115 AIN0).\n'
       'AVC: Ioff + VCC isolation -> Hi-Z when VREF = 0.\n'
       'TRC_DATA[2] as TRIGIN output is not supported in rev 0.1.', 1.27)

# nRESET open drain
T.place('2N7002', ref('Q'), '2N7002', 330.2, 137.16, fp='Package_TO_SOT_SMD:SOT-23',
        nets={'1': 'NRST_DRV', '2': 'GND', '3': 'B_NRST'}, pwr_stub=2.54)
RV(T, '100k', 312.42, 152.4, 'NRST_DRV', 'GND')
T.note(312.42, 162.56, 'nRESET: open drain (2N7002), state read back via U(AVC8) B7.', 1.27)

# VREF filter + divider
RH(T, '10', 345.44, 30.48, 'VREF_T', 'VREF_F')
caps(T, 365.76, 38.1, [('1u', C0603), ('100n', C0402)], 'VREF_F')
T.flag('VREF_T', 345.44, 50.8)
T.flag('VREF_F', 365.76, 50.8)
RV(T, '100k', 391.16, 81.28, 'VREF_T', 'ADC_VREF')
RV(T, '100k', 391.16, 99.06, 'ADC_VREF', 'GND')

# target power
T.place('AP2161W', ref('U'), 'AP2161W', 50.8, 213.36,
        nets={'5': '+5V', '1': 'TPWR_SW', '2': 'GND', '3': 'TPWR_FLT_N', '4': 'TPWR_EN_N'},
        pwr_stub=2.54)
CV(T, '1u', 25.4, 236.22, '+5V', 'GND', C0603)
RH(T, '100k', 30.48, 193.04, 'TPWR_EN_N', '+3V3')
RH(T, '10k', 30.48, 203.2, 'TPWR_FLT_N', '+3V3')
RH(T, '0.1 1%', 101.6, 210.82, 'TPWR_SW', 'TPWR_OUT', fp=R0805)
T.place('INA219AxD', ref('U'), 'INA219AxD', 147.32, 218.44,
        nets={'8': 'TPWR_SW', '7': 'TPWR_OUT', '5': '+3V3', '6': 'GND', '3': 'I2C_SDA',
              '4': 'I2C_SCL', '1': 'GND', '2': 'GND'}, pwr_stub=2.54)
CV(T, '100n', 170.18, 200.66)
CV(T, '1u', 119.38, 236.22, 'TPWR_OUT', 'GND', C0603)
RV(T, '10k', 127.0, 236.22, 'TPWR_OUT', 'GND')
T.place('SolderJumper_3_Bridged12', 'JP1', 'P11/13: GND | TgtPwr', 203.2, 213.36,
        fp='Jumper:SolderJumper-3_P1.3mm_Bridged12_RoundedPad1.0x1.5mm',
        nets={'1': 'GND', '2': 'P11_13', '3': 'TPWR_OUT'}, pwr_stub=2.54)
CV(T, '10p', 220.98, 233.68, 'P11_13', 'GND')
T.note(190.5, 238.76, 'JP1 default 1-2 (pins 11/13 = GND).\n'
       'TgtPwr: 5 V, current-limited by AP2161 (FLG -> CH569),\n'
       'current via INA219 (0x40), 10p at the pins per spec.', 1.27)

# ADC
T.place('ADS1115IDGS', ref('U'), 'ADS1115IDGS', 314.96, 218.44, fp='Package_SO:VSSOP-10_3x3mm_P0.5mm',
        nets={'4': 'ADC_VREF', '5': 'ADC_TPWR', '6': 'ADC_5V', '7': 'ADC_3V3', '1': 'GND',
              '2': 'ADC_ALERT', '3': 'GND', '8': '+3V3', '9': 'I2C_SDA', '10': 'I2C_SCL'},
        pwr_stub=2.54)
CV(T, '100n', 337.82, 200.66)
RH(T, '10k', 360.68, 208.28, 'ADC_ALERT', '+3V3')
RV(T, '100k', 254.0, 203.2, 'TPWR_OUT', 'ADC_TPWR')
RV(T, '100k', 254.0, 220.98, 'ADC_TPWR', 'GND')
RV(T, '100k', 264.16, 203.2, '+5V', 'ADC_5V')
RV(T, '100k', 264.16, 220.98, 'ADC_5V', 'GND')
RV(T, '100k', 274.32, 203.2, '+3V3', 'ADC_3V3')
RV(T, '100k', 274.32, 220.98, 'ADC_3V3', 'GND')
T.note(345.44, 220.98, 'ADS1115 @0x48:\nAIN0 VREF/2, AIN1 TgtPwr/2,\nAIN2 5V/2, AIN3 3V3/2', 1.27)

# =========================================================================== sheet: SMA triggers
G = proj.sheet('sma.kicad_sch', 'SMA triggers / reference')
G.frame(12.7, 12.7, 406.4, 254.0, 'SMA1 / SMA2: bidirectional 3.3 V LVCMOS (default input)')
for k in (1, 2):
    y = 60.96 + (k - 1) * 101.6
    G.place('Conn_Coaxial', f'J{2 + k}', f'SMA{k}', 40.64, y, 180,
            fp='Connector_Coaxial:SMA_Amphenol_132289_EdgeMount',
            nets={'1': f'SMA{k}_C', '2': 'GND'}, pwr_stub=2.54)
    G.place('D_TVS', ref('D'), 'PESD3V3S1BB', 76.2, y + 12.7, 90, fp='Diode_SMD:D_SOD-523',
            nets={'1': 'GND', '2': f'SMA{k}_C'}, pwr_stub=2.54)
    G.place('SolderJumper_2_Open', f'JP{k + 1}', '50R term', 101.6, y + 12.7,
            fp='Jumper:SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm',
            nets={'1': f'SMA{k}_C', '2': f'SMA{k}_T'})
    RV(G, '49.9', 121.92, y + 22.86, f'SMA{k}_T', 'GND')
    RH(G, '33', 101.6, y, f'SMA{k}_C', f'SMA{k}_B')
    G.place('SN74LVC1T45DBV', ref('U'), 'SN74LVC1T45DBV', 165.1, y,
            nets={'1': '+3V3', '6': '+3V3', '2': 'GND', '3': f'SMA{k}_F', '4': f'SMA{k}_B',
                  '5': f'SMA{k}_DIR'}, pwr_stub=2.54)
    CV(G, '100n', 195.58, y - 12.7)
    RH(G, '10k', 147.32, y + 30.48, f'SMA{k}_DIR', 'GND')
G.note(228.6, 50.8, 'SMA1 -> FPGA LPLL2_T_in (pin 13): 10 MHz TTL reference from DOROGO\n'
       '        or trigger/PPS input; can also drive a trigger out.\n'
       'SMA2 -> FPGA GCLKT_3 (pin 63): PPS / trigger in or out.\n\n'
       'DIR = 0 (default, 10k pull-down): SMA -> FPGA. DIR = 1: FPGA -> SMA.\n'
       '33 Ohm series + buffer Rout ~ 50 Ohm source termination.\n'
       'JPx closed: 50 Ohm load for long coax inputs (keep open when driving).\n'
       'Input level: 3.3 V LVCMOS/TTL only; sine reference is not accepted.', 1.27)

# =========================================================================== root notes
Rt = proj.root
Rt.note(30.48, 20.32, 'Open Debug + Trace probe, rev 0.1 (direction B)', 3.0, True)
Rt.note(30.48, 30.48, 'GW2AR-18 QN88 (trace capture, timestamps, SWD/JTAG engine, 64 Mbit SDRAM buffer)\n'
        '+ CH569W (USB3 SS device: ORBTrace-compatible trace IF, events IF, CMSIS-DAP v2, CDC, DFU).\n'
        'Target: MIPI20, VREF 1.2..3.6 V. Triggers: 2x SMA. Spec: see design document.', 1.5)
Rt.note(30.48, 185.42, 'Sources of pinouts: GW2AR-18 - Gowin UG115E v1.7.2 (QN88, SDRAM); CH569W - WCH reference\n'
        'schematic CH569W-R0-1v0; other ICs - KiCad library symbols. Footprints marked probe: are project-local.\n'
        'Open items before layout: CH569 EP size (datasheet), QN88 land pattern (UG229 drawing), CBTL02043A SEL\n'
        'polarity, USB-C part, MODE straps (UG290), PB15 RST# config.', 1.27)
