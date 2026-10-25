"""Стенд трассы BE-U1000 — та же раскладка, что у стенда прозвонки SLogic16U3 (doc/img/slogic-pinmap-bench.svg),
другие подписи. Run: python3 tools/diagrams/beu1000_bench.py  ->  doc/img/beu1000-trace-bench.svg"""
import os
import re
from xml.sax.saxutils import escape

IMG = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../doc/img')
SRC, DST = 'slogic-pinmap-bench.svg', 'beu1000-trace-bench.svg'
TITLE = 'Стенд трассы BE-U1000'

# номер подписи в шаблоне (порядок <text>) -> новая подпись
TEXT = {
    0: 'Стенд трассы BE-U1000: N-Trace через PIB, приём SLogic16U3, чтение через JTAG',
    1: 'Образ tracela грузится только в SRAM ПЛИС; трассер BE-U1000 настраивается по SBA из OpenOCD Baikal MCU SDK.',
    4: 'OpenOCD Baikal (au/mcu-sdk), openFPGALoader',
    6: 'EVU-BA-2.5 (BE-U1000)',
    7: 'ядро 0: fw/ в TCMA, 25…200 МГц',
    8: 'PIB 4 бита, TRC_CLK = tclk ≤ 50 МГц',
    9: 'PB0 … PB3', 11: 'CH8 … CH11',
    12: 'PB4', 14: 'CH12',
    15: 'XP10: 1, 2, 3, 19', 17: 'PIB_D[0..3]',
    18: 'XP10: 6', 20: 'PIB_CLK',
    21: 'GND (XP10: 4, 20)', 23: 'GND',
    24: 'R5 снят: QSPI-флеш DD1 отрезана',
    25: 'от PB0 (её S#); XP10 — после 0 Ом',
    26: 'FTDI DD7 (JTAG + UART0) — на борту',
    29: 'CH8 … CH11', 30: 'CH12 — такт', 31: 'GND',
    33: 'штатный жгут', 34: '~10 см,', 35: 'как у STM32',
    46: 'CH12 → N9 (GCLK)',
    47: 'данные: IODELAY → IDDR',
    48: 'IODELAY 224 (≈ 2,8 нс)',
    52: 'буфер 8 Кслов × 32',
    57: 'питание прибора; со своим',
    58: 'образом USB нет (Windows: 0000:0002)',
    59: 'Образ tracela (SRAM)',
    60: 'режим 2: IDDR от TRACECLK',
    61: 'частотомер всех пяти линий',
    62: '65 536 полубайт за запись',
    63: 'буфер → ER1 GW_JTAG (IR 0x42)',
    64: 'команды → ER2 (IR 0x43)',
    66: 'запись — trace.py, разбор — ntrace.py',
    67: 'трассер — ocd.py (tcl 6668)',
    73: '4 + 1',
    75: 'USB: FTDI DD7 (XS2)',
    78: 'Порядок: openFPGALoader -m tracela.fs → ocd.py: load_image fw, pins 3, pll, tclk, pib_on, te_on → ntrace.py cal → ntrace.py cap, table.',
    79: 'Итог: BTM и HTM чисто на TRC_CLK 25 и 50 МГц; ядро 200 МГц — BTM переполняет PIB, HTM нет; путь программы — по ELF.',
}


def main():
    s = open(os.path.join(IMG, SRC), encoding='utf-8').read()
    n = [0]

    def sub(m):
        i = n[0]
        n[0] += 1
        return f'<text {m[1]}>{escape(TEXT[i])}</text>' if i in TEXT else m[0]

    s = re.sub(r'<text ([^>]*)>([^<]*)</text>', sub, s)
    s = re.sub(r'<title>[^<]*</title>', f'<title>{TITLE}</title>', s, count=1)
    open(os.path.join(IMG, DST), 'w', encoding='utf-8').write(s)
    print('written', os.path.abspath(os.path.join(IMG, DST)), f'({n[0]} подписей в шаблоне)')


if __name__ == '__main__':
    main()
