"""Symbols used by the probe: verified KiCad library pinouts + custom GW2AR-18 / CH569W."""
from sym import from_kicad5, box_symbol, pwr_flag

B, I, O, P, W, w = 'bidirectional', 'input', 'output', 'passive', 'power_in', 'power_out'

# ---------------------------------------------------------------------------
# GW2AR-18 QN88 (embedded SDRAM) - pin numbers/names from Gowin UG115E v1.7.2 (QN88[1] column)
GW_BANK0 = [(86, 'IOT4A'), (85, 'IOT4B'), (84, 'IOT6A'), (83, 'IOT6B'), (82, 'IOT17A'),
            (81, 'IOT17B'), (80, 'IOT27A/GCLKT_0'), (79, 'IOT27B/GCLKC_0')]
GW_BANK1 = [(69, 'IOT50A'), (70, 'IOT44B'), (71, 'IOT44A'), (72, 'IOT40B'), (73, 'IOT40A'),
            (74, 'IOT34B'), (75, 'IOT34A'), (76, 'IOT30B/GCLKC_1'), (77, 'IOT30A/GCLKT_1')]
GW_BANK2 = [(5, 'IOR25B/TMS'), (6, 'IOR26A/TCK'), (7, 'IOR26B/TDI'), (8, 'IOR25A/TDO')]
GW_BANK3 = [(9, 'IOR31B/RECONFIG_N'), (48, 'IOR49B'), (49, 'IOR49A'), (51, 'IOR45A/RPLL2_T_in'),
            (52, 'IOR39A/SCLK'), (53, 'IOR38B/DOUT/WE_N'), (54, 'IOR38A/DIN/CLKHOLD_N'),
            (55, 'IOR36B/SSPI_CS_N/D0'), (56, 'IOR36A/SO/D1'), (57, 'IOR35A/FASTRD_N/D3'),
            (59, 'IOR34B/MCLK/D4'), (60, 'IOR34A/MCS_N/D5'), (61, 'IOR33B/MO/D6'),
            (62, 'IOR33A/MI/D7'), (63, 'IOR29A/GCLKT_3'), (87, 'IOR30B/MODE1'), (88, 'IOR30A/MODE0')]
GW_BANK4 = [(35, 'IOB30A/GCLKT_4'), (36, 'IOB30B/GCLKC_4'), (37, 'IOB34A'), (38, 'IOB34B'),
            (39, 'IOB40A'), (40, 'IOB40B'), (41, 'IOB43A'), (42, 'IOB42B')]
GW_BANK5 = [(25, 'IOB6A'), (26, 'IOB6B'), (27, 'IOB8A'), (28, 'IOB8B'), (29, 'IOB14A'),
            (30, 'IOB14B'), (31, 'IOB18A'), (32, 'IOB18B'), (33, 'IOB24A'), (34, 'IOB24B')]
GW_BANK6 = [(10, 'IOL29A/GCLKT_6'), (11, 'IOL29B/GCLKC_6'), (13, 'IOL45A/LPLL2_T_in'),
            (15, 'IOL47A/LPLL2_T_fb'), (16, 'IOL47B/LPLL2_C_fb'), (17, 'IOL49A'), (18, 'IOL49B'),
            (19, 'IOL51A'), (20, 'IOL51B')]
GW_BANK7 = [(4, 'IOL7A/LPLL1_T_in')]


def _io(lst):
    return [(n, nm, B) for n, nm in lst]


def gw2ar18():
    pwr_l = [(1, 'VCC', W), (22, 'VCC', W), (45, 'VCC', W), (66, 'VCC', W), None,
             (3, 'VCCX/VCCIO2/6/7', W), (12, 'VCCX/VCCIO2/6/7', W), (64, 'VCCX/VCCIO2/6/7', W), None,
             (78, 'VCCIO0', W), (67, 'VCCIO1', W), (58, 'VCCIO3', W), (44, 'VCCIO4', W),
             (23, 'VCCIO5', W), None, (14, 'VCCPLLL1', W), (50, 'VCCPLLR1', W)]
    pwr_r = [(2, 'VSS', W), (21, 'VSS', W), (24, 'VSS', W), (43, 'VSS', W), (46, 'VSS', W),
             (65, 'VSS', W), (68, 'VSS', W), (89, 'EPAD', W), None, (47, 'EXTR', P)]
    units = [
        dict(name='Bank0/1', left=_io(GW_BANK1), right=_io(GW_BANK0)),
        dict(name='Bank4/5', left=_io(GW_BANK5), right=_io(GW_BANK4)),
        dict(name='Bank2/3/6/7', left=_io(GW_BANK6) + [None] + _io(GW_BANK7),
             right=_io(GW_BANK3) + [None] + _io(GW_BANK2)),
        dict(name='Power', left=pwr_l, right=pwr_r),
    ]
    s = box_symbol('GW2AR-18_QN88', 'U', units,
                   'probe:QFN-88-1EP_10x10mm_P0.4mm_EP6.74x6.74mm',
                   'https://cdn.gowinsemi.com.cn/UG115E.pdf',
                   'Gowin GW2AR-LV18QN88C8/I7, 20k LUT4, 64 Mbit SDR SDRAM in package', min_w=30.48)
    return s


# ---------------------------------------------------------------------------
# CH569W QFN68 - from WCH reference schematic CH569W-R0-1v0 (openwch/ch569 SCHPCB)
def ch569w():
    L = [(15, 'PA5/HD0', B), (17, 'PA4/HD1', B), (53, 'PA22/HD2', B), (19, 'PA3/HD3', B),
         (20, 'PA2/HD4', B), (21, 'PA1/HD5', B), (22, 'PA0/HD6', B), (23, 'PB21/HD7', B),
         (24, 'PB20/HD8', B), (25, 'PB19/HD9', B), (26, 'PB18/HD10', B), (27, 'PB17/HD11', B),
         (28, 'PA17/HD12', B), (29, 'PB16/HD13', B), (30, 'PB15/RST#/HD14', B), (31, 'PB14/HD15', B),
         None,
         (56, 'PA11/HTCLK', B), (54, 'PA9/HTREQ', B), (55, 'PA10/HTACK', B), (52, 'PA21/HTVLD', B),
         (18, 'PA23/HTRDY', B), (10, 'PA19/HRCLK', B), (11, 'PA18/HRACK', B), (14, 'PA6/HRVLD', B)]
    R = [(1, 'UD+', B), (2, 'UD-', B), (4, 'SSTX+', O), (5, 'SSTX-', O), (7, 'SSRX+', I),
         (8, 'SSRX-', I), (65, 'GXM', P), (66, 'GXP', P), (68, 'XI', I), (67, 'XO', O), None,
         (12, 'PA8/TXD1', B), (13, 'PA7/RXD1', B), (57, 'PA12/SCS', B), (58, 'PA13/SCK', B),
         (59, 'PA14/MOSI', B), (60, 'PA15/MISO', B), (40, 'PA16', B), (35, 'PA20', B),
         (32, 'PB0', B), (33, 'PB1', B), (34, 'PB2', B), (36, 'PB3', B), (37, 'PB4', B),
         (38, 'PB5', B), (39, 'PB6', B), (41, 'PB7', B), (43, 'PB8', B), (44, 'PB9', B),
         (46, 'PB10', B), (48, 'PB11', B), (50, 'PB12', B), (51, 'PB13', B), (45, 'PB22', B),
         (47, 'PB23', B), (49, 'PB24', B)]
    PL = [(16, 'VDDIO', W), (42, 'VDDIO', W), (61, 'VDDIO', W), (62, 'V33LDO', W),
          (64, 'V33GX', W), (3, 'V33USB', W)]
    PR = [(63, 'V12CORE', w), (9, 'V12CORE', P), (6, 'V12USB', W), None, (69, 'GND(EP)', W)]
    units = [dict(name='Signals', left=L, right=R), dict(name='Power', left=PL, right=PR)]
    return box_symbol('CH569W', 'U', units, 'Package_DFN_QFN:QFN-68-1EP_8x8mm_P0.4mm_EP5.2x5.2mm',
                      'http://www.wch-ic.com/downloads/CH569DS1_PDF.html',
                      'WCH CH569W RISC-V MCU, USB3.0 SS device, HSPI', min_w=30.48)


KICAD_PARTS = ['R', 'C', 'L', 'LED', 'Crystal_GND24', 'FerriteBead_Small', 'Fuse', 'D_TVS',
               'USB_C_Receptacle', 'Conn_Coaxial', 'Conn_02x10_Odd_Even', 'Conn_02x05_Odd_Even',
               'Conn_01x04', 'SW_Push', '2N7002', 'ASE-xxxMHz', 'TLV62569DDC', 'AP2161W',
               'INA219AxD', 'ADS1115IDGS', 'TLV7031DBV', 'W25Q128JVS', 'SN74AVC8T245PW',
               'SN74AVC4T245PW', 'SN74LVC1T45DBV', 'CBTL02043A', 'TPD4EUSB30', 'USBLC6-2SC6',
               'TPD4E02B04DQA', 'SolderJumper_2_Open', 'SolderJumper_3_Bridged12']

POWER_UP = ['+5V', 'VBUS', '+3V3', '+1V0', '+1V0_PLL', '+1V2_CH', 'VREF_T', 'VREF_F']
POWER_DOWN = ['GND']


def build(proj):
    for n in KICAD_PARTS:
        s = from_kicad5(n)
        proj.add_symbol(s)
    proj.add_symbol(gw2ar18())
    proj.add_symbol(ch569w())
    proj.add_symbol(pwr_flag())
    for n in POWER_UP:
        proj.add_power(n, 'up')
    for n in POWER_DOWN:
        proj.add_power(n, 'down')
