"""Переходник SLogic16U3 (гребёнка 2×12, 2,54 мм) → MIPI20 (угловая вилка 2×10, 2,54 мм), rev 0.2.

Плата односторонняя (медь снизу, верх — сплошная земля): раскладка каналов подобрана так, чтобы сигналы
шли от J1 к J2 параллельными полосами без пересечений; по питанию — одна проволочная перемычка (R19).
Запуск: python3 slogic_mipi20.py → hw/slogic-mipi20/slogic-mipi20.kicad_sch, затем ERC через kicad-cli
(см. hw/slogic-mipi20/README.md).
"""
import os, sys
from kisch import Sheet

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '../../hw/slogic-mipi20')

R0805 = 'Resistor_SMD:R_0805_2012Metric_Pad1.20x1.40mm_HandSolder'
C0805 = 'Capacitor_SMD:C_0805_2012Metric_Pad1.18x1.45mm_HandSolder'
SOT5 = 'Package_TO_SOT_SMD:SOT-23-5'
WIRE = 'Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal'

sh = Sheet('slogic-mipi20', 'SLogic16U3 -> MIPI20 adapter', '0.2', '2026-11-08', 'rln-trace',
           ('Односторонняя плата: каналы разложены под разводку без пересечений',
            'Каналы анализатора: делитель 72k||C1 / 64k до ПЛИС, защиты нет; цель — VREF 3,3 В'))


def r(ref, val, x, y, a, b, fp=R0805, dnp=False):
    sh.place('Device:R', ref, val, x, y, nets={'1': a, '2': b}, fp=fp, dnp=dnp)


def c(ref, val, x, y, a, b='GND', fp=C0805, dnp=False):
    sh.place('Device:C', ref, val, x, y, nets={'1': a, '2': b}, fp=fp, dnp=dnp)


# ------------------------------------------------------------ J1: гребёнка анализатора
# Вывод 2k-1 — верхний ряд, 2k — нижний, k = 1..12 слева направо на виде сзади прибора (картинка Sipeed):
# верх VCC G 14 12 10 8 VCC G 6 4 2 0, низ CK G 15 13 11 9 CK G 7 5 3 1.
# Порядок полос с запада на восток (вид на плату сверху, J1 на севере): AUX D3 D2 D1 D0 TRACECLK nRESET_IN |
# nRESET TDI TDO TCK VREF SWDIO_OE TMS SWDIO_IN — тот же, что у контактов MIPI20 на J2.
LA = {
    1: 'NC', 2: 'NC',                       # VCC 3,3 В прибора, CK (не реализован)
    3: 'GND', 4: 'GND',
    5: 'LA_TD3',       6: 'LA_AUX',         # CH14, CH15
    7: 'LA_TD1',       8: 'LA_TD2',         # CH12, CH13
    9: 'LA_TD0',      10: 'NC',             # CH10, CH11 (свободен)
    11: 'LA_TRACECLK', 12: 'LA_NRST_IN',    # CH8 (N11, GCLKT_3), CH9
    13: 'NC', 14: 'NC',
    15: 'GND', 16: 'GND',
    17: 'LA_NRST',    18: 'LA_TDI',         # CH6, CH7
    19: 'LA_TDO',     20: 'LA_TCK',         # CH4, CH5
    21: 'LA_VREF',    22: 'LA_SWDIO_OE',    # CH2, CH3
    23: 'LA_TMS',     24: 'LA_SWDIO_IN',    # CH0, CH1
}
sh.note(20.32, 22.86, 'SLogic16U3: 2×12 (2×PMOD)', 2.0, True)
sh.place('Connector_Generic:Conn_02x12_Odd_Even', 'J1', 'SLogic16U3', 45.72, 63.5,
         nets={str(k): v for k, v in LA.items()},
         fp='Connector_PinHeader_2.54mm:PinHeader_2x12_P2.54mm_Horizontal')
sh.note(20.32, 88.9,
        'Вид сзади прибора (раскладка Sipeed):\n'
        '  верх: VCC  G  14 12 10  8  VCC  G   6  4  2  0\n'
        '  низ:   CK  G  15 13 11  9   CK  G   7  5  3  1\n'
        'Вывод 2k-1 = верх (дальний от края платы ряд угловой вилки),\n'
        '2k = низ, k = 1..12 слева направо. VCC прибора и CK не подключены.\n\n'
        'CH0 TMS/SWDIO вых.   CH1 SWDIO вх.\n'
        'CH2 VREF есть        CH3 SWDIO_OE вых.\n'
        'CH4 TDO/SWO вх.      CH5 TCK вых.\n'
        'CH6 nRESET вых. (1 = сброс)  CH7 TDI вых.\n'
        'CH8 TRACECLK (GCLKT_3)  CH9 nRESET вх.\n'
        'CH10 TRACED0  CH12 TRACED1  CH13 TRACED2  CH14 TRACED3\n'
        'CH11 свободен  CH15 AUX вх.')

# ------------------------------------------------------------ выходы в цель
sh.note(96.52, 22.86, 'Выходы в цель: буферы от VREF, вход — слабый источник 72 кОм || C1', 2.0, True)
gates = [
    # ref, вход, OE, выход, вывод MIPI, питание
    ('U7', 'LA_TCK', 'VREF', 'TCK_B', 'T_TCK', 'VREF'),
    ('U8', 'LA_TMS', 'LA_SWDIO_OE', 'TMS_B', 'T_TMS', 'VREF'),
    ('U9', 'LA_TDI', 'VREF_B', 'TDI_B', 'T_TDI', 'VREF_B'),
]
x0, y0 = 129.54, 50.8
for k, (ref, a, oe, y, t, vcc) in enumerate(gates):
    x = x0 + k * 63.5
    sh.place('74xGxx:74AUP1G126', ref, '74AUP1G126', x, y0, fp=SOT5, fields={'MPN': 'SN74AUP1G126DBVR'},
             nets={'1': oe, '2': a, '3': 'GND', '4': y, '5': vcc})
    r(f'R{1 + k}', '33', x + 25.4, y0 + 10.16, y, t)                       # последовательный
    r(f'R{4 + k}', '330k', x - 30.48, y0 + 22.86, a, 'GND')               # Rl
    c(f'C{1 + k}', 'подбор', x - 20.32, y0 + 22.86, a, dnp=True)           # Cl
    c(f'C{5 + k}', '100n', x + 7.62, y0 + 22.86, vcc)                      # развязка
x = x0 + 3 * 63.5
sh.place('74xGxx:74LVC1G06', 'U10', '74LVC1G06', x, y0, fp=SOT5, fields={'MPN': 'SN74LVC1G06DBVR'},
         nets={'2': 'LA_NRST', '3': 'GND', '4': 'T_NRST', '5': 'VREF_B'})
r('R8', '1M', x - 30.48, y0 + 22.86, 'LA_NRST', 'GND')
c('C8', '100n', x + 7.62, y0 + 22.86, 'VREF_B')
# SWDIO_OE переключается на каждом повороте шины SWD — та же компенсация, что у данных
r('R7', '330k', x0 - 30.48, y0 + 50.8, 'LA_SWDIO_OE', 'GND')
c('C4', 'подбор', x0 - 20.32, y0 + 50.8, 'LA_SWDIO_OE', dnp=True)

sh.note(96.52, 116.84,
        'Канал анализатора на выход: ПЛИС → R1≈72 кОм || C1 (ускоряющий) → разъём, R2≈64 кОм к земле.\n'
        'Rl + Cl на входе буфера — обратный компенсированный делитель: фронт без хвоста при Rl·Cl = 72k·C1.\n'
        'Пост. уровень = 3,3·Rl/(72k+Rl): 330k → 2,7 В (VIH AUP 2,0 В при VCC 3,3 В).\n'
        'Если C1 > Cвх: уменьшать Rl (Rl = 72k·C1/Cвх, Cвх ≈ 1,5 пФ AUP + дорожка). Если C1 < Cвх: Cl не ставить, искать подбором.\n'
        'TCK и TDI включены, пока есть VREF (OE = VREF): без ПЛИС на них 0 — TAP цели держит TMS (Hi-Z, подтяжка цели).\n'
        'TMS/SWDIO — Hi-Z, пока ПЛИС не выставит SWDIO_OE. U10: открытый сток, 1 на LA_NRST = сброс цели.\n'
        'AUP1G126 ↔ LVC1G126 — одна посадка (у LVC сильнее выход, но вход 3,5 пФ против 1,5).')

# ------------------------------------------------------------ MIPI20
sh.note(20.32, 157.48, 'MIPI20 на угловой вилке 2×10, 2,54 мм', 2.0, True)
MIPI = {1: 'VREF', 2: 'T_TMS', 3: 'GND', 4: 'T_TCK', 5: 'GND', 6: 'T_TDO', 7: 'NC', 8: 'T_TDI',
        9: 'GND', 10: 'T_NRST', 11: 'GND', 12: 'T_TRACECLK', 13: 'GND', 14: 'T_TD0', 15: 'GND',
        16: 'T_TD1', 17: 'GND', 18: 'T_TD2', 19: 'GND', 20: 'T_TD3'}
sh.place('Connector_Generic:Conn_02x10_Odd_Even', 'J2', 'MIPI20', 45.72, 190.5,
         nets={str(k): v for k, v in MIPI.items()},
         fp='Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Horizontal')
sh.note(20.32, 215.9, 'Нумерация MIPI20 1:1 — шлейф 2,54 мм и переходники\n'
                      'на 1,27 мм / 10 контактов. 7 — ключ (NC).\n'
                      '9 GNDDetect, 11/13 — земля (без TgtPwr).')

# ESD у разъёма MIPI20: по две полосы на корпус (I/O1 и I/O4 — с разных сторон SOT-23-6)
sh.note(96.52, 157.48, 'ESD у разъёма (прибор без защиты): по 2 линии на корпус', 2.0, True)
tvs = [('U1', 'AUX', 'T_TD3', 'NC'), ('U2', 'T_TD2', 'T_TD1', 'NC'), ('U3', 'T_TD0', 'T_TRACECLK', 'NC'),
       ('U4', 'T_NRST', 'T_TDI', 'NC'), ('U5', 'T_TDO', 'T_TCK', 'NC'), ('U6', 'T_TMS', 'NC', 'VREF')]
for k, (ref, io1, io4, vbus) in enumerate(tvs):
    sh.place('Power_Protection:USBLC6-4SC6', ref, 'USBLC6-4SC6', 114.3 + k * 25.4, 187.96,
             fields={'MPN': 'USBLC6-4SC6'},
             nets={'1': io1, '6': io4, '3': 'NC', '4': 'NC', '2': 'GND', '5': vbus})
sh.note(96.52, 205.74, 'VBUS не подключён: верхние диоды заряжают узел, разряд гасит стабилитрон VBUS–GND.\n'
                       'У U6 VBUS на VREF — заодно защита VREF.')

# ------------------------------------------------------------ линии из цели в анализатор
sh.note(266.7, 157.48, 'Из цели в анализатор: напрямую через 33 Ом', 2.0, True)
reads = [('R9', 'T_TRACECLK', 'LA_TRACECLK', '33'), ('R10', 'T_TD0', 'LA_TD0', '33'),
         ('R11', 'T_TD1', 'LA_TD1', '33'), ('R12', 'T_TD2', 'LA_TD2', '33'),
         ('R13', 'T_TD3', 'LA_TD3', '33'), ('R14', 'T_TDO', 'LA_TDO', '33'),
         ('R15', 'T_TMS', 'LA_SWDIO_IN', '33'), ('R16', 'T_NRST', 'LA_NRST_IN', '33'),
         ('R17', 'VREF', 'LA_VREF', '1k'), ('R18', 'AUX', 'LA_AUX', '100')]
for k, (ref, a, b, v) in enumerate(reads):
    r(ref, v, 271.78 + k * 13.97, 182.88, a, b)
sh.note(266.7, 200.66,
        'После ESD резистор вместе с C1 прибора гасит остаток разряда на шарике ПЛИС.\n'
        '33 Ом × ~15 пФ = 0,5 нс — для 84 МГц DDR не мешает; номинал 0..47 Ом — подбор на стенде.\n'
        'R15: SWDIO читается с контакта 2 MIPI20. R16: nRESET — с контакта 10.\n'
        'R17: CH2 видит наличие VREF (через делитель прибора — уровень 1).')

# AUX: свободный вход анализатора (PPS и т. п.)
sh.place('Connector_Generic:Conn_01x02', 'J3', 'AUX', 284.48, 243.84, nets={'1': 'AUX', '2': 'GND'},
         fp='Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical')

# ------------------------------------------------------------ питание VREF
sh.note(20.32, 233.68, 'VREF от цели питает буферы', 2.0, True)
c('C9', '4.7u', 81.28, 251.46, 'VREF')
r('R19', 'перемычка', 101.6, 251.46, 'VREF', 'VREF_B', fp=WIRE)
sh.note(111.76, 243.84, 'R19 — проволочная перемычка: VREF к U9/U10\n'
                        'через полосы TCK, TDO, TDI (единственное пересечение).')
sh.flag('VREF', 30.48, 243.84)
sh.flag('GND', 45.72, 243.84)
sh.flag('VREF_B', 60.96, 243.84)

sh.write(OUT)
bad = sh.single_pin_nets()
print('цепей:', len(sh.net_pins), ' цепей из одного вывода:', bad or 'нет')
sys.exit(1 if bad else 0)
