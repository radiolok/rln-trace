"""Переходник SLogic16U3 (гребёнка 2×12, 2,54 мм) → MIPI20 (Cortex Debug+ETM / RISC-V Trace).

Запуск: python3 slogic_mipi20.py → hw/slogic-mipi20/slogic-mipi20.kicad_sch, затем ERC и
список цепей через kicad-cli (см. hw/slogic-mipi20/README.md).
"""
import os, sys
from kisch import Sheet

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '../../hw/slogic-mipi20')

R0402 = 'Resistor_SMD:R_0402_1005Metric'
C0402 = 'Capacitor_SMD:C_0402_1005Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
SOT5 = 'Package_TO_SOT_SMD:SOT-23-5'

sh = Sheet('slogic-mipi20', 'SLogic16U3 -> MIPI20 adapter', '0.1', '2026-10-27', 'rln-trace',
           ('Каналы анализатора: делитель 72k||C1 / 64k до ПЛИС, защиты нет',
            'Цель rev 0.1: VREF 3,3 В (буферы работают от 0,8/1,65 до 3,6 В)'))


def r(ref, val, x, y, a, b, fp=R0402, dnp=False, horiz=False):
    sh.place('Device:R', ref, val, x, y, 90 if horiz else 0, nets={'1': a, '2': b}, fp=fp, dnp=dnp)


def c(ref, val, x, y, a, b='GND', fp=C0402, dnp=False):
    sh.place('Device:C', ref, val, x, y, nets={'1': a, '2': b}, fp=fp, dnp=dnp)


# ------------------------------------------------------------ J1: гребёнка анализатора
# Нумерация: вывод 2k-1 — верхний ряд, 2k — нижний, k = 1..12 слева направо на виде
# сзади прибора (картинка Sipeed): верх VCC G 14 12 10 8 VCC G 6 4 2 0, низ CK G 15 13 11 9 CK G 7 5 3 1.
LA = {
    1: 'NC', 2: 'NC',                       # VCC 3,3 В прибора, CK (не реализован) — не используем
    3: 'GND', 4: 'GND',
    5: 'LA_VREF',      6: 'LA_AUX',         # CH14, CH15
    7: 'LA_TRACECLK',  8: 'LA_SWDIO_OE',    # CH12 (GCLKT_2), CH13
    9: 'LA_TD2',      10: 'LA_TD3',         # CH10, CH11
    11: 'LA_TD0',     12: 'LA_TD1',         # CH8, CH9
    13: 'NC', 14: 'NC',
    15: 'GND', 16: 'GND',
    17: 'LA_NRST',    18: 'LA_EN',          # CH6, CH7
    19: 'LA_TDI',     20: 'LA_NRST_IN',     # CH4, CH5
    21: 'LA_TMS',     22: 'LA_SWDIO_IN',    # CH2, CH3
    23: 'LA_TCK',     24: 'LA_TDO',         # CH0, CH1
}
sh.note(20.32, 22.86, 'SLogic16U3: гребёнка 2×12, 2,54 мм', 2.0, True)
sh.place('Connector_Generic:Conn_02x12_Odd_Even', 'J1', 'SLogic16U3', 45.72, 63.5,
         nets={str(k): v for k, v in LA.items()},
         fp='Connector_PinHeader_2.54mm:PinHeader_2x12_P2.54mm_Horizontal')
sh.note(20.32, 88.9,
        'Вид сзади прибора (раскладка Sipeed):\n'
        '  верх: VCC  G  14 12 10  8  VCC  G   6  4  2  0\n'
        '  низ:   CK  G  15 13 11  9   CK  G   7  5  3  1\n'
        'Вывод 2k-1 = верх, 2k = низ, k = 1..12 слева направо.\n'
        'Сверить зеркальность с посадкой при разводке!\n\n'
        'CH0 TCK вых.       CH1 TDO/SWO вх.\n'
        'CH2 TMS/SWDIO вых. CH3 SWDIO вх.\n'
        'CH4 TDI вых.       CH5 nRESET вх.\n'
        'CH6 nRESET вых. (1 = сброс)  CH7 EN вых. (TCK, TDI)\n'
        'CH8..11 TRACED0..3  CH12 TRACECLK\n'
        'CH13 SWDIO_OE вых.  CH14 VREF есть  CH15 AUX вх.\n'
        'VCC (3,3 В прибора) и CK не подключены.')

# ------------------------------------------------------------ выходы в цель
sh.note(96.52, 22.86, 'Выходы в цель: буферы от VREF, вход — слабый источник 72 кОм || C1', 2.0, True)
gates = [
    # ref, символ, MPN, вход, OE, выход, вывод MIPI, Rl, Cl
    ('U4', '74xGxx:74AUP1G126', 'SN74AUP1G126DBVR', 'LA_TCK', 'LA_EN', 'TCK_B', 'T_TCK'),
    ('U5', '74xGxx:74AUP1G126', 'SN74AUP1G126DBVR', 'LA_TMS', 'LA_SWDIO_OE', 'TMS_B', 'T_TMS'),
    ('U6', '74xGxx:74AUP1G126', 'SN74AUP1G126DBVR', 'LA_TDI', 'LA_EN', 'TDI_B', 'T_TDI'),
]
x0, y0 = 129.54, 50.8
for k, (ref, lib, mpn, a, oe, y, t) in enumerate(gates):
    x = x0 + k * 63.5
    sh.place(lib, ref, '74AUP1G126', x, y0, fp=SOT5, fields={'MPN': mpn},
             nets={'1': oe, '2': a, '3': 'GND', '4': y, '5': 'VREF'})
    r(f'R{1 + k}', '33', x + 25.4, y0 + 10.16, y, t)                       # последовательный
    r(f'R{4 + k}', '330k', x - 30.48, y0 + 22.86, a, 'GND')               # Rl
    c(f'C{1 + k}', 'подбор', x - 20.32, y0 + 22.86, a, dnp=True)           # Cl
    c(f'C{5 + k}', '100n', x + 7.62, y0 + 22.86, 'VREF')                   # развязка
x = x0 + 3 * 63.5
sh.place('74xGxx:74LVC1G06', 'U7', '74LVC1G06', x, y0, fp=SOT5, fields={'MPN': 'SN74LVC1G06DBVR'},
         nets={'2': 'LA_NRST', '3': 'GND', '4': 'T_NRST', '5': 'VREF'})
r('R9', '1M', x - 30.48, y0 + 22.86, 'LA_NRST', 'GND')
c('C8', '100n', x + 7.62, y0 + 22.86, 'VREF')
# OE-цепи: EN — медленная, SWDIO_OE переключается на каждом повороте шины SWD
r('R7', '330k', x0 - 30.48, y0 + 50.8, 'LA_SWDIO_OE', 'GND')
c('C4', 'подбор', x0 - 20.32, y0 + 50.8, 'LA_SWDIO_OE', dnp=True)
r('R8', '1M', x0 - 5.08, y0 + 50.8, 'LA_EN', 'GND')

sh.note(96.52, 116.84,
        'Канал анализатора на выход: ПЛИС → R1≈72 кОм || C1 (ускоряющий) → разъём, R2≈64 кОм к земле.\n'
        'Rl + Cl на входе буфера — обратный компенсированный делитель: фронт без хвоста при Rl·Cl = 72k·C1.\n'
        'Пост. уровень = 3,3·Rl/(72k+Rl): 330k → 2,7 В (VIH AUP 2,0 В при VCC 3,3 В).\n'
        'Если C1 > Cвх: уменьшать Rl (Rl = 72k·C1/Cвх, Cвх ≈ 1,5 пФ AUP + дорожка). Если C1 < Cвх: Cl не ставить, искать подбором.\n'
        'По умолчанию все выходы в Hi-Z: пока ПЛИС не управляет, R2 и Rl держат EN, SWDIO_OE и nRESET в 0.\n'
        'U7: открытый сток, 1 на LA_NRST = сброс цели. U4..U7 питаются от VREF; при VREF = 0 — Ioff, цель не запитывается.\n'
        'AUP1G126 ↔ LVC1G126 — одна посадка (у LVC сильнее выход, но вход 3,5 пФ против 1,5).')

# ------------------------------------------------------------ MIPI20
sh.note(20.32, 157.48, 'MIPI20 (Cortex Debug+ETM / RISC-V Trace)', 2.0, True)
MIPI = {1: 'VREF', 2: 'T_TMS', 3: 'GND', 4: 'T_TCK', 5: 'GND', 6: 'T_TDO', 7: 'NC', 8: 'T_TDI',
        9: 'GND', 10: 'T_NRST', 11: 'GND', 12: 'T_TRACECLK', 13: 'GND', 14: 'T_TD0', 15: 'GND',
        16: 'T_TD1', 17: 'GND', 18: 'T_TD2', 19: 'GND', 20: 'T_TD3'}
sh.place('Connector_Generic:Conn_02x10_Odd_Even', 'J2', 'MIPI20', 45.72, 190.5,
         nets={str(k): v for k, v in MIPI.items()},
         fp='Connector_PinHeader_1.27mm:PinHeader_2x10_P1.27mm_Vertical_SMD',
         fields={'MPN': 'Samtec FTSH-110-01-L-DV-K (вывод 7 удалён — ключ)'})
sh.note(20.32, 215.9, '7 — ключ. 9 GNDDetect, 11/13 — земля (без TgtPwr).')

# ESD у разъёма MIPI20
sh.note(96.52, 157.48, 'ESD у разъёма (прибор без защиты)', 2.0, True)
tvs = [('U1', ['T_TCK', 'T_TMS', 'T_TDI', 'T_TDO']),
       ('U2', ['T_NRST', 'T_TRACECLK', 'T_TD0', 'T_TD1']),
       ('U3', ['T_TD2', 'T_TD3', 'VREF', 'AUX'])]
for k, (ref, io) in enumerate(tvs):
    sh.place('Power_Protection:TPD4E02B04DQA', ref, 'TPD4E02B04', 114.3 + k * 40.64, 185.42,
             fields={'MPN': 'TPD4E02B04DQAR'},
             nets={'1': io[0], '2': io[1], '4': io[2], '5': io[3], '3': 'GND', '8': 'GND',
                   '6': 'NC', '7': 'NC', '9': 'NC', '10': 'NC'})

# ------------------------------------------------------------ линии из цели в анализатор
sh.note(238.76, 157.48, 'Из цели в анализатор: напрямую через 33 Ом', 2.0, True)
reads = [('R10', 'T_TRACECLK', 'LA_TRACECLK', '33'), ('R11', 'T_TD0', 'LA_TD0', '33'),
         ('R12', 'T_TD1', 'LA_TD1', '33'), ('R13', 'T_TD2', 'LA_TD2', '33'),
         ('R14', 'T_TD3', 'LA_TD3', '33'), ('R15', 'T_TDO', 'LA_TDO', '33'),
         ('R16', 'T_TMS', 'LA_SWDIO_IN', '33'), ('R17', 'T_NRST', 'LA_NRST_IN', '33'),
         ('R18', 'VREF', 'LA_VREF', '1k'), ('R19', 'AUX', 'LA_AUX', '100')]
for k, (ref, a, b, v) in enumerate(reads):
    r(ref, v, 248.92 + k * 15.24, 182.88, a, b)
sh.note(238.76, 200.66,
        'После ESD-диода резистор вместе с C1 прибора гасит остаток разряда на шарике ПЛИС.\n'
        '33 Ом × ~15 пФ = 0,5 нс — для 84 МГц DDR (6 нс на бит) не мешает; номинал 0..47 Ом — подбор на стенде.\n'
        'R16: SWDIO читается с контакта 2 MIPI20 (после R2 33 Ом выхода).\n'
        'R18: CH14 видит наличие VREF (через делитель прибора — уровень 1).')

# AUX: свободный вход анализатора (PPS и т. п.)
sh.place('Connector_Generic:Conn_01x02', 'J3', 'AUX', 284.48, 243.84, nets={'1': 'AUX', '2': 'GND'},
         fp='Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical')

# ------------------------------------------------------------ питание VREF
sh.note(20.32, 233.68, 'VREF от цели питает буферы', 2.0, True)
c('C9', '4.7u', 66.04, 251.46, 'VREF', fp=C0603)
sh.flag('VREF', 30.48, 243.84)
sh.flag('GND', 45.72, 243.84)

sh.write(OUT)
bad = sh.single_pin_nets()
print('цепей:', len(sh.net_pins), ' цепей из одного вывода:', bad or 'нет')
sys.exit(1 if bad else 0)
