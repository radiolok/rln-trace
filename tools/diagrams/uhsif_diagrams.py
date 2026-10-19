"""CH32H417 / UHSIF diagrams (SVG), redrawn from the WCH documents plus what the libUHSIF.a
teardown found (doc/ch32h417-uhsif.md). Run: python3 tools/diagrams/uhsif_diagrams.py
Output: doc/img/uhsif/*.svg (bus and driver), hw/img/ch32h417/*.svg (the MCU).
Originals for checking by eye: tools/diagrams/uhsif_originals.py (*.orig*.png, git-ignored)."""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_diagrams import D, PAL, INK, QUIET, LINE  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
UHSIF = os.path.join(HERE, '../../doc/img/uhsif')
MCU = os.path.join(HERE, '../../hw/img/ch32h417')

FPGA_C, MCU_C, ACC, TEAL = '#1C64F2', '#13924F', '#D6336C', '#0B8EA0'


# =========================================================================== WaveDrom
WAVEDROM = 'wavedrom-cli@3.2.0'
WAVE_SRC = os.path.join(HERE, 'wavedrom')


def render(name, spec, outdir):
    """Write WaveJSON next to the other sources and render it with the reference WaveDrom CLI."""
    os.makedirs(WAVE_SRC, exist_ok=True)
    src = os.path.join(WAVE_SRC, name + '.json')
    with open(src, 'w') as f:
        json.dump(spec, f, ensure_ascii=False, indent=1)
        f.write('\n')
    os.makedirs(outdir, exist_ok=True)
    subprocess.run(['npx', '-y', WAVEDROM, '-i', src, '-s', os.path.join(outdir, name + '.svg')], check=True)


def gap(lanes, at):
    """WaveDrom gap mark at one time cell in every lane that is only continuing there."""
    for lane in lanes:
        if isinstance(lane, list):
            gap(lane[1:], at)
        elif isinstance(lane, dict) and lane.get('wave', '')[at:at + 1] == '.':
            w = lane['wave']
            lane['wave'] = w[:at] + '|' + w[at + 1:]


# Data colours: 5 = driven by the FPGA (master), 7 = driven by CH32H417 (slave), 2 = line number.
# Annotations live in node-only lanes (uppercase node names are not printed).
def at(n, marks):
    cells = ['.'] * n
    for i, name in marks:
        cells[i] = name
    return ''.join(cells)


def write():
    n = 26
    lanes = [
        {'name': 'PCLK', 'wave': 'p' + '.' * (n - 1)},
        ['ПЛИС → МК',
         {'name': 'CS#', 'wave': '1.0...1......0........1...'},
         {'name': 'WR#', 'wave': '1.0...1......0........1...', 'node': at(n, [(6, 'A'), (22, 'C')])},
         {'name': 'EOP#', 'wave': '1....01..............01...'},
         {'name': 'DATA', 'wave': 'z.5555z......555555555z...',
          'data': ['W0', 'W1', 'W2', 'W3'] + [f'W{i}' for i in range(9)]},
         {'name': 'SEL[1:0]', 'wave': '2.2...2......2........2...',
          'data': ['Line 0', 'Line 1', 'Line 0', 'Line 1', 'Line 0']}],
        ['МК → ПЛИС',
         {'name': 'WRNF', 'wave': '1.......0...1...........0.', 'node': at(n, [(8, 'B'), (24, 'D')])},
         {'name': 'AF#', 'wave': '1.................0.....1.'},
         {'node': at(n, [(18, 'E'), (24, 'F')])}],
    ]
    gap(lanes, 10)
    render('01-write', {
        'signal': lanes,
        'edge': ['A~>B 2 такта', 'C~>D 2 такта', 'E<->F water_mark_value'],
        'head': {'text': 'UHSIF: ПЛИС пишет в CH32H417 (ведомый FPGA). По рис. 4-2 руководства WCH', 'tick': 0},
        'foot': {'text': 'Первый пакет короче буфера; второй упирается в порог AF#'},
        'config': {'hscale': 1},
    }, UHSIF)


def zlp():
    n = 14
    render('02-zlp', {
        'signal': [
            {'name': 'PCLK', 'wave': 'p' + '.' * (n - 1)},
            ['ПЛИС → МК',
             {'name': 'CS#', 'wave': '1....0....1...'},
             {'name': 'WR#', 'wave': '1.............'},
             {'name': 'EOP#', 'wave': '1....01.......', 'node': at(n, [(6, 'A')])},
             {'name': 'DATA', 'wave': 'z.............'},
             {'name': 'SEL[1:0]', 'wave': 'x....2x.......', 'data': ['Line n']}],
            ['МК → ПЛИС',
             {'name': 'WRNF', 'wave': '1.......0.....', 'node': at(n, [(8, 'B')])}],
        ],
        'edge': ['A~>B 2 такта'],
        'head': {'text': 'UHSIF: пакет нулевой длины. По рис. 4-3 руководства WCH', 'tick': 0},
        'foot': {'text': 'CS# и EOP# вместе при WR# = 1'},
        'config': {'hscale': 2},
    }, UHSIF)


def read():
    n = 26
    lanes = [
        {'name': 'PCLK', 'wave': 'p' + '.' * (n - 1)},
        ['ПЛИС → МК',
         {'name': 'CS#', 'wave': '1.0......1...0..........1.'},
         {'name': 'OE#', 'wave': '1.0......1...0..........1.'},
         {'name': 'RD#', 'wave': '1..0..1.......0.....1.....', 'node': at(n, [(3, 'A'), (6, 'C'), (14, 'I'), (20, 'E')])},
         {'name': 'SEL[1:0]', 'wave': 'x.2......x...2..........x.', 'data': ['Line 0', 'Line 0']}],
        ['МК → ПЛИС',
         {'name': 'DATA', 'wave': 'z.x..777xz...x..777777x.z.',
          'data': ['R0', 'R1', 'R2'] + [f'R{i}' for i in range(6)], 'node': at(n, [(5, 'B'), (16, 'J')])},
         {'name': 'RDNE', 'wave': '1.......0...1.........0...', 'node': at(n, [(8, 'D'), (22, 'F')])},
         {'name': 'AE#', 'wave': '1................0....1...'},
         {'node': at(n, [(17, 'G'), (22, 'H')])}],
    ]
    gap(lanes, 11)
    render('03-read', {
        'signal': lanes,
        'edge': ['A~>B 2 такта', 'I~>J 2 такта', 'C~>D 2 такта', 'E~>F 2 такта',
                 'G<->H water_mark_value'],
        'head': {'text': 'UHSIF: ПЛИС читает из CH32H417 (ведомый FPGA). По рис. 4-4 руководства WCH', 'tick': 0},
        'foot': {'text': 'У WCH рис. 4-4 ошибочно подписан как чтение пакета нулевой длины'},
        'config': {'hscale': 1},
    }, UHSIF)


def io_timing():
    """0.5 ns per cell, 0..18 ns; tpd = 1 ns of board delay each way; exact numbers in the labels."""
    R, T = 0.5, 18
    N = int(T / R)

    def c(t):
        return max(0, min(N, round(t / R)))

    def lane(segs, default):
        """segs: (t0, t1, char) in ns -> wave string; every segment of a data char starts a new value."""
        cells, starts = [default] * N, set()
        for t0, t1, ch in segs:
            for i in range(c(t0), c(t1)):
                cells[i] = ch
            starts.add(c(t0))
        out = []
        for i, ch in enumerate(cells):
            same = i and ch == cells[i - 1] and not (ch in '57' and i in starts)
            out.append('.' if same else ch)
        return ''.join(out)

    def clock(shift):
        return lane([(shift + 8 * k, shift + 8 * k + 4, 'h') for k in range(-1, 3)] +
                    [(shift + 8 * k + 4, shift + 8 * k + 8, 'l') for k in range(-1, 3)], 'l')

    def nodes(marks):
        return at(N, [(c(t), name) for t, name in marks])

    render('04-io-timing', {
        'signal': [
            {'name': 'PCLK у ПЛИС', 'wave': clock(0)},
            {'node': nodes([(0, 'K'), (8, 'L')])},
            {'name': 'PCLK у МК', 'wave': clock(1)},
            ['ПЛИС → МК',
             {'name': 'вход МК', 'wave': lane([(5, 13, '5'), (13, 18, '5')], '5'), 'data': ['D0', 'D1', 'D2']},
             {'node': nodes([(8.5, 'A'), (9, 'B'), (10.5, 'C')])}],
            ['МК → ПЛИС',
             {'name': 'выход у МК', 'wave': lane([(1, 7.2, '7'), (7.2, 9, 'x'), (9, 15.2, '7'), (15.2, 17, 'x'),
                                                  (17, 18, '7')], '7'),
              'data': ['', 'Q(k−1)', 'Q(k)', 'Q(k+1)']},
             {'node': nodes([(1, 'D'), (7.2, 'E')])},
             {'node': nodes([(1, 'F'), (9, 'G')])},
             {'name': 'выход у ПЛИС', 'wave': lane([(2, 8.2, '7'), (8.2, 10, 'x'), (10, 16.2, '7'), (16.2, 18, 'x')], '7'),
              'data': ['', 'Q(k−1)', 'Q(k)']},
             {'node': nodes([(10, 'H'), (12, 'I'), (16.2, 'J')])},
             {'name': 'захват по спаду', 'wave': lane([(12, 12.5, 'h')], 'l')}],
        ],
        'edge': ['K<->L tCK = 8 нс', 'A<->B tIS', 'B<->C tIH 1,5', 'D<->E tOD min 6,2 нс', 'F<->G tOD max 8 нс',
                 'H<->I 2,0 нс', 'I<->J 4,2 нс'],
        'head': {'text': 'UHSIF при 125 МГц: окно захвата на стороне ПЛИС. Тайминги ведомого — раздел 7 руководства WCH'},
        'foot': {'text': 'Сетка 0,5 нс; tpd = 1 нс (~15 см) в каждую сторону; tIS = 0,5 нс'},
        'config': {'hscale': 1},
    }, UHSIF)


def notes(d, y, lines, size=12):
    for i, ln in enumerate(lines):
        d.text(24, y + i * 18, ln, size, 400, QUIET)


def diamond(d, cx, cy, w, h, title, lines=(), kind='front'):
    fill, stroke = PAL[kind]
    pts = [(cx, cy - h / 2), (cx + w / 2, cy), (cx, cy + h / 2), (cx - w / 2, cy)]
    d.o.append('<path d="M' + ' L'.join(f'{x} {y}' for x, y in pts) + f'Z" fill="{fill}" stroke="{stroke}" '
               'stroke-width="1.6"/>')
    d.text(cx, cy - 2 - 8 * len(lines), title, 13, 700, INK, 'middle')
    for i, ln in enumerate(lines):
        d.text(cx, cy + 14 + i * 15 - 8 * len(lines), ln, 11, 400, QUIET, 'middle')


# =========================================================================== 5. lines, sockets, descriptors
def lines():
    d = D(1420, 640, 'Каналы, сокеты, дескрипторы и буферы UHSIF',
          'Восстановлено по libUHSIF.a (у WCH только рис. 4-1: 4 канала × 8 буферов). Пример: канал 0 — IN, канал 1 — OUT, по 8 буферов.')
    # FPGA and lines
    d.box(24, 110, 130, 330, 'ПЛИС', ['SEL[1:0]', 'выбирает', 'канал'], 'fpga')
    kinds = ['usb', 'accent', 'neutral', 'neutral']
    names = ['IN', 'OUT', '—', '—']
    for n in range(4):
        y = 110 + n * 84
        d.box(194, y, 170, 70, f'Line {n}  {names[n]}', [f'UHSIF+0x{0xFC + 4 * n:03X}', 'текущий сокет [4:0]'],
              kinds[n])
        d.arrow([(154, y + 35), (194, y + 35)], color=FPGA_C)
    # socket grid
    gx, gy, cw, ch = 420, 120, 56, 60
    d.text(gx, 100, 'Сокеты: s = buf·4 + line, регистры по 0x4003_9000 + s·0x40', 13, 700)
    for buf in range(8):
        d.text(gx + buf * cw + cw / 2 - 4, gy + 4 * ch + 26, f'buf {buf}', 11, 400, QUIET, 'middle')
        for line in range(4):
            s = buf * 4 + line
            kind = kinds[line] if line < 2 else 'neutral'
            hl = (line == 1 and buf == 2)
            fill, stroke = PAL['accent'] if hl else PAL[kind]
            d.o.append(f'<rect x="{gx + buf * cw}" y="{gy + line * ch + 8}" width="{cw - 6}" height="{ch - 14}" rx="6" '
                       f'fill="{fill}" stroke="{stroke}" stroke-width="{2.4 if hl else 1.2}"/>')
            d.text(gx + buf * cw + (cw - 6) / 2, gy + line * ch + 36, f'{s}', 13, 700 if hl else 400, INK, 'middle')
    for n in range(4):
        d.line([(364, 145 + n * 84), (gx - 6, gy + n * ch + 31)], QUIET, dash=True, width=1)
    d.arrow([(gx + 20, gy + 4 * ch + 40), (gx + 7 * cw - 10, gy + 4 * ch + 40)], color=QUIET,
            label='после прерывания канал переходит к сокету s + 4 (следующий буфер)', lpos=(gx + 4 * cw - 30, gy + 4 * ch + 58))
    # socket registers
    rx = 1010
    d.box(rx, 110, 386, 170, 'Регистры сокета 9 (0x4003_9240)', [
        '+0x00  адрес дескриптора >> 5  (| 0x0601_0000)', '+0x04  размер буфера (0x4000)',
        '+0x08  передано байт', '+0x0C  режим: бит 31 взведён, бит 30 перевзвод',
        '+0x10  флаги событий (сброс записью 1)', '+0x14  разрешения прерываний'], 'accent')
    d.arrow([(gx + 2 * cw + cw / 2 - 3, gy + 2 * ch - 6), (gx + 2 * cw + cw / 2 - 3, gy + 2 * ch + 1),
             (rx - 30, gy + 2 * ch + 1), (rx - 30, 195), (rx, 195)], color=ACC, width=2)
    # descriptors
    d.box(rx, 310, 386, 132, 'Дескриптор OUT[10] = OUT[line·8 + buf]', [
        'слово 0  адрес буфера', 'слово 1  направление: 0 IN, 1 OUT', 'слово 2  свой адрес >> 5 (кольцо из 1)',
        'слово 3  [31:16] длина, [15:0] 0x4000'], 'accent')
    d.arrow([(rx + 193, 280), (rx + 193, 310)], color=ACC, width=2, label='S+0x00', lpos=(rx + 201, 300),
            lanchor='start')
    d.box(rx, 472, 386, 76, 'Буфер: pbuf + buf·16 КБ', ['канал 1, буфер 2: pbuf₁ + 0x8000',
                                                         'в примере WCH — буфер конечной точки USB'], 'usb')
    d.arrow([(rx + 193, 442), (rx + 193, 472)], color=ACC, width=2, label='слово 0', lpos=(rx + 201, 462),
            lanchor='start')
    d.box(420, 470, 500, 78, 'Таблицы дескрипторов в RAM', ['IN[32] и OUT[32] по 32 байта, индекс line·8 + buf',
                                                            'обязаны лежать в 0x2000_0000…0x201F_FFFF'], 'neutral')
    d.legend(24, 610, [('usb', 'канал IN (ПЛИС → МК)'), ('accent', 'канал OUT и путь примера'),
                       ('neutral', 'не используется'), ('fpga', 'ПЛИС')])
    d.save('05-lines.svg', UHSIF)


# =========================================================================== 6. address map
def addr_map():
    d = D(1280, 690, 'Карта адресов UHSIF и связанных регистров',
          'Не в масштабе. Названия наши: у WCH определения UHSIF_TypeDef нет, только UHSIF_BASE = 0x4003_8000.')
    x, w = 24, 560
    rows = [
        ('0x4003_8000', '+0x000…0x12F  настройка: 76 слов из таблицы WCH', 'fpga', [
            '+0x000 CTRL: [31] пуск, [4], [3] полярность PCLK', '+0x004 BUS: [20] фронт выдачи, [3:2] ширина',
            '+0x014 флаги прерываний: [11+n] канал n', '+0x024 записывается после таблицы, по режиму',
            '+0x0FC…0x108 регистры каналов 0…3', '+0x118, +0x11C общие разрешения (UHSIF_Start)'], 170),
        ('0x4003_8180', '+0x180…0x1A0  таблица переходов автомата', 'front', [
            'по слову на переход, значимы 16 бит; 7 / 8 / 9 записей (FPGA / SOC / Master)'], 64),
        ('0x4003_9000', '+0x1000…0x17FF  сокеты: 32 × 0x40', 'usb', [
            's = buf·4 + line; +0x00 дескриптор, +0x04 размер, +0x08 счётчик,',
            '+0x0C режим, +0x10 флаги, +0x14 разрешения'], 82),
        ('0x4003_A000', '+0x2000…  микрокод, банк A', 'accent', [
            'по 16 байт на шаг, 3 слова; 199 / 198 / 11 шагов'], 64),
        ('0x4003_B000', '+0x3000…  микрокод, банк B', 'accent', ['вторые 3 слова каждого шага'], 64),
    ]
    y = 90
    for addr, title, kind, lines, h in rows:
        d.text(x, y + 18, addr, 12, 700, QUIET)
        d.box(x + 110, y, w, h - 10, title, lines, kind)
        y += h
    d.text(x + 110, y + 14, 'Пустоты между блоками — не описаны, библиотека туда не обращается.', 12, 400, QUIET)
    ox = 740
    d.text(ox, 102, 'Вне блока', 14, 700)
    others = [
        ('0x4001_0000', 'AFIO_PCFR1', ['[9:8] UHSIF_PORT_RM, [7:6] UHSIF_CLK_RM'], 'neutral'),
        ('0x4002_1018', 'RCC_HBPCENR', ['[18] UHSIFEN — тактирование блока'], 'neutral'),
        ('0x4002_1030', 'RCC_CFGR2', ['[7:6] UHSIFSRC, [5:0] UHSIFDIV'], 'neutral'),
        ('0xE000_E110', 'PFIC IENR4 / IRER4 (+0x80)', ['бит 17 — прерывание 145 (UHSIF)'], 'neutral'),
        ('0x2000_0000', 'RAM: окно дескрипторов', ['0x2000_0000…0x201F_FFFF, указатель 16 бит × 32 байта',
                                                  'покрывает всю внутреннюю RAM (до 0x2018_0000)'], 'ext'),
    ]
    y = 116
    for addr, title, lines, kind in others:
        d.text(ox, y + 18, addr, 12, 700, QUIET)
        d.box(ox + 110, y, 400, 46 + 17 * len(lines), title, lines, kind)
        y += 60 + 17 * len(lines)
    d.legend(24, 664, [('fpga', 'настройка'), ('front', 'автомат'), ('usb', 'сокеты'), ('accent', 'микрокод'),
                       ('neutral', 'системные регистры'), ('ext', 'RAM')])
    d.save('06-address-map.svg', UHSIF)


# =========================================================================== 7. driver flow and interrupt
def driver_flow():
    d = D(1340, 826, 'Драйвер UHSIF: порядок вызовов и обработчик прерывания',
          'Одинаково для libUHSIF.a и fw/uhsif (сверено в spike обращение в обращение).')
    x, w, h = 24, 420, 74
    steps = [
        ('UHSIF_GPIO_Init(mode, port_rm, clk_rm, div, width)', ['выводы, AFIO_PCFR1; у ведущего — UHSIFDIV'], 'neutral'),
        ('UHSIF_Cfg()', ['76 слов настройки + полярности и ширина,', '+0x024, микрокод, таблица переходов'], 'fpga'),
        ('UHSIF_Line_Cfg(line, dir, count, pbuf, wm) × N', ['дескрипторы, регистры сокетов,', 'регистр канала'], 'fpga'),
        ('UHSIF_Start(ENABLE)', ['+0x118/+0x11C, пуск CTRL, сокет 0 |= 0x1C1,', 'IRQ 145'], 'usb'),
    ]
    y = 96
    for title, lines, kind in steps:
        d.box(x, y, w, h, title, lines, kind)
        if y > 96:
            d.arrow([(x + w / 2, y - 22), (x + w / 2, y)])
        y += h + 22
    d.box(x, y + 20, w, h, 'UHSIF_Trans_Cfg(line, buf, n)', ['взвести или перевзвести буфер', 'см. «Перевзвод сокета»'],
          'usb')
    d.arrow([(x + w / 2, y - 22), (x + w / 2, y + 20)])
    d.box(x, y + 140, w, 60, 'UHSIF_Start(DISABLE)', ['IRQ выкл, сброс блока, такт выкл'], 'neutral')
    ix = 540
    d.arrow([(x + w, y + 50), (x + w + 30, y + 50), (x + w + 30, 160), (ix, 160)], color=ACC, dash=True,
            label='прерывание', lpos=(x + w + 36, 300), lanchor='start', lcolor=ACC)
    d.arrow([(ix + 400, 724), (ix + 400, 760), (x + w + 50, 760), (x + w + 50, y + 80), (x + w, y + 80)],
            color=ACC, dash=True, label='из колбэка', lpos=(x + w + 56, 750), lanchor='start', lcolor=ACC)
    # interrupt handler
    d.frame(ix - 16, 100, 800, 640, 'UHSIF_IRQHandler')
    d.box(ix, 130, 330, 60, 'f = UHSIF+0x014', ['канал n — первый бит из 11…14'], 'neutral')
    d.box(ix + 400, 130, 360, 60, 'флагов нет', ['всё равно обслуживается канал 0, сокет 0, как IN'], 'neutral')
    d.arrow([(ix + 330, 160), (ix + 400, 160)], dash=True)
    d.box(ix, 216, 330, 60, 's = LINE(n)[4:0], st = S(s)+0x10', ['текущий сокет и его флаги'], 'neutral')
    d.arrow([(ix + 165, 190), (ix + 165, 216)])
    diamond(d, ix + 165, 330, 230, 76, 'st & 0x01 ?')
    d.arrow([(ix + 165, 276), (ix + 165, 292)])
    d.box(ix + 400, 300, 360, 64, 'LINE(n) = вкл | dir | wm | !dir | 0x400 | (s + 4)',
          ['канал переходит к следующему буферу'], 'fpga')
    d.arrow([(ix + 280, 330), (ix + 400, 330)], label='нет', lpos=(ix + 340, 322))
    d.text(ix + 175, 386, 'да: остаться на этом буфере', 11, 400, QUIET)
    diamond(d, ix + 165, 440, 230, 70, 'st & 0x80 ?')
    d.arrow([(ix + 165, 368), (ix + 165, 405)])
    d.line([(ix + 580, 364), (ix + 580, 392), (ix + 165, 392)], LINE)
    d.box(ix + 400, 416, 170, 48, 'сбросить 0x80', [], 'accent', center=True)
    d.arrow([(ix + 280, 440), (ix + 400, 440)], label='да', lpos=(ix + 340, 432))
    diamond(d, ix + 165, 530, 230, 70, 'st & 0x40 ?')
    d.arrow([(ix + 165, 475), (ix + 165, 495)], label='нет', lpos=(ix + 180, 490), lanchor='start')
    d.box(ix + 400, 506, 360, 48, 'сбросить 0x40 (и 0x01, если стоял)', [], 'accent', center=True)
    d.arrow([(ix + 280, 530), (ix + 400, 530)], label='да', lpos=(ix + 340, 522))
    diamond(d, ix + 165, 616, 230, 70, 'st & 0x100 ?')
    d.arrow([(ix + 165, 565), (ix + 165, 581)], label='нет', lpos=(ix + 180, 578), lanchor='start')
    d.box(ix + 400, 592, 170, 48, 'сбросить 0x100', [], 'accent', center=True)
    d.arrow([(ix + 280, 616), (ix + 400, 616)], label='да', lpos=(ix + 340, 608))
    d.box(ix + 400, 660, 360, 64, 'dir = IN: LineN_IN_Callback(S(s)+0x08)', ['dir = OUT: LineN_OUT_Callback()'], 'usb')
    d.arrow([(ix + 165, 651), (ix + 165, 692), (ix + 400, 692)])
    d.line([(ix + 570, 440), (ix + 780, 440)], LINE)
    d.line([(ix + 760, 530), (ix + 780, 530)], LINE)
    d.line([(ix + 570, 616), (ix + 780, 616)], LINE)
    d.line([(ix + 780, 440), (ix + 780, 692)], LINE)
    d.arrow([(ix + 780, 692), (ix + 760, 692)])
    d.text(24, 812, 'Флаги разбираются по приоритету 0x80 → 0x40 → 0x100, за прерывание сбрасывается один.', 12, 400, QUIET)
    d.save('07-driver-flow.svg', UHSIF)


# =========================================================================== 8. socket re-arm
def rearm():
    d = D(1420, 560, 'Перевзвод сокета: первый круг по буферам и все следующие',
          'UHSIF_Trans_Cfg, восстановлено по libUHSIF.a. S = регистры сокета, dscr = его дескриптор, size = 16 КБ.')
    lanes = [
        ('OUT (МК → ПЛИС)', 'accent', [
            ('UHSIF_Line_Cfg', ['S+0x0C |= 0x0500_0000', 'dscr.len = size<<16 | size'], 'neutral'),
            ('Trans_Cfg, первый круг', ['count вызовов; n < size:', 'dscr.len = n<<16 | size; S+0x0C бит 31 = 1'], 'accent'),
            ('передача, прерывание', ['LineN_OUT_Callback()'], 'neutral'),
            ('Trans_Cfg, дальше', ['S+0x08 = 0; dscr.len = n<<16 | size', 'S+0x0C бит 30: 1 → 0'], 'accent'),
        ]),
        ('IN (ПЛИС → МК)', 'usb', [
            ('UHSIF_Line_Cfg + Start', ['S+0x0C |= 0x8C00_0000', 'сокет 0: S+0x10 |= 0x1C1'], 'neutral'),
            ('приём, прерывание', ['LineN_IN_Callback(S+0x08)', 'S+0x08 — принятая длина'], 'neutral'),
            ('Trans_Cfg(line, buf, 0)', ['S+0x08 < size: dscr.len = size<<16|size', 'адрес dscr — из S+0x00'], 'usb'),
            ('', ['S+0x08 = 0', 'S+0x0C бит 30: 1 → 0'], 'usb'),
        ]),
    ]
    y = 96
    for title, kind, steps in lanes:
        d.text(24, y + 40, title, 14, 700)
        x = 200
        for i, (t, lines, k) in enumerate(steps):
            d.box(x, y, 270, 86, t or 'затем', lines, k)
            if i:
                d.arrow([(x - 30, y + 43), (x, y + 43)])
            x += 300
        y += 130
    d.arrow([(200 + 300 * 3 + 135, 182), (200 + 300 * 3 + 135, 200), (200 + 300 * 2 + 135, 200),
             (200 + 300 * 2 + 135, 182)], color=QUIET, dash=True, label='по кругу', lpos=(200 + 300 * 2 + 285, 214))
    d.box(200, 372, 600, 98, 'Ловушка: n > 16 КБ', [
        'в первом круге длина молча остаётся прежней, дальше n<<16 переполняет поле;',
        'длина ровно 16 КБ в первом круге работает только потому, что Line_Cfg', 'уже записал 0x4000. fw/uhsif возвращает 0xA9.'],
          'accent', bold=True)
    d.box(830, 372, 540, 98, 'Бит 31 и бит 30 в S+0x0C', [
        'бит 31 ставится один раз, при первом взводе;', 'дальше перевзвод — импульс бита 30 (записать 1, затем 0).',
        'Названия по поведению, на железе не проверено.'], 'neutral')
    d.text(24, 510, 'Для IN первый буфер взводит UHSIF_Start; дальше приложение вызывает Trans_Cfg на каждый освобождённый буфер.', 12, 400, QUIET)
    d.save('08-rearm.svg', UHSIF)


# =========================================================================== 9. clock
def clock():
    d = D(1160, 420, 'Такт UHSIF в CH32H417',
          'По тактовому дереву даташита V1.8 (рис. 1-3) и ch32h417_rcc.h. Нужен только ведущему: ведомый берёт PCLK от ПЛИС.')
    srcs = [('SYSCLK', '0, по умолчанию'), ('PLL_CLK', '1'), ('USBHS_PLL_CLK', '2'), ('ETH_PLL_CLK', '3')]
    for i, (s, code) in enumerate(srcs):
        d.box(24, 92 + i * 62, 200, 50, s, [f'UHSIFSRC = {code}'], 'neutral')
        d.arrow([(224, 117 + i * 62), (300, 117 + i * 62)])
    d.o.append('<path d="M300 92 L360 122 L360 278 L300 308 Z" fill="#FFF8DB" stroke="#E09400" stroke-width="1.6"/>')
    d.text(330, 205, 'MUX', 12, 700, INK, 'middle')
    d.text(300, 330, 'RCC_CFGR2[7:6]', 12, 700, QUIET)
    d.text(300, 346, 'RCC_UHSIFCLKConfig()', 11, 400, QUIET)
    d.box(420, 168, 220, 74, 'UHSIFDIV  /1…/64', ['RCC_CFGR2[5:0]', '= clk_div в UHSIF_GPIO_Init'], 'front')
    d.arrow([(360, 205), (420, 205)])
    d.box(690, 150, 230, 110, 'UHSIF', ['RCC_HBPCENR[18] (UHSIFEN)', 'ведущий: PCLK наружу', '≤ 125 МГц'], 'usb', bold=True)
    d.arrow([(640, 205), (690, 205)])
    d.box(960, 120, 176, 70, 'Ведущий', ['PCLK → внешнее', 'ведомое устройство'], 'usb')
    d.box(960, 220, 176, 70, 'Ведомый', ['PCLK ← ПЛИС', '(вход UHSIF_CLK)'], 'fpga')
    d.arrow([(920, 180), (960, 155)], color=MCU_C)
    d.arrow([(960, 255), (920, 230)], color=FPGA_C)
    notes(d, 380, ['На рисунке даташита у мультиплексора три входа (ETH_PLL, USBHS_PLL, PLL); в заголовке WCH их четыре, код 0 — SYSCLK.',
                  'libUHSIF.a источник не выбирает (остаётся сброшенное значение), делитель пишет только в режиме ведущего.'])
    d.save('09-clock.svg', MCU)


# =========================================================================== 10. pins
def pins():
    d = D(1240, 760, 'Выводы UHSIF: сигнал → UHSIF_PORT → вывод корпуса',
          'Руководство WCH (рис. 3-1, табл. 3-2) + даташит V1.8 (табл. 2-2-16) + раскладка, которую ставит libUHSIF.a (pinmap.py).')
    # path strip
    d.box(24, 86, 300, 50, 'Сигналы UHSIF', ['PCLK, управление, SEL, DATA'], 'usb', center=False)
    d.box(394, 86, 320, 50, 'UHSIF_CLK + UHSIF_PORT[47:0]', ['раскладка по табл. 3-2 (библиотека)'], 'front')
    d.box(784, 86, 432, 50, 'Выводы GPIO, домен VIO18', ['AFIO_PCFR1: [9:8] PORT_RM, [7:6] CLK_RM'], 'neutral')
    d.arrow([(324, 111), (394, 111)])
    d.arrow([(714, 111), (784, 111)])
    cols = [('Сигнал', 120), ('PORT', 70), ('RM=00, QFN128', 190), ('RM=01, QFN56/68', 190), ('RM=1x, QFN88', 190),
            ('ведомый', 200), ('ведущий', 160)]
    rows = [
        ('SEL0', '3', 'PE8', 'PC1', 'PB0', 'вход ↓', 'выход'),
        ('SEL1', '4', 'PE9', 'PC2', 'PB1', 'вход ↓', 'выход'),
        ('AF#', '5', 'PE10', 'PC3', 'PE10', 'выход (GPIO: вход ↑ !)', 'вход ↑'),
        ('AE#', '7', 'PE12', 'PB1', 'PE12', 'выход', 'вход ↓'),
        ('EOP#', '8', 'PE13', 'PE13', 'PE13', 'вход ↑', 'выход'),
        ('WRNF', '9', 'PE14', 'PE14', 'PE14', 'выход', 'вход ↓'),
        ('RDNE', '11', 'PB10', 'PB10', 'PB10', 'выход', 'вход ↓'),
        ('RD#', '12', 'PB11', 'PB11', 'PB11', 'вход ↑', 'выход'),
        ('OE#', '13', 'PB12', 'PB12', 'PB12', 'вход ↑', 'выход'),
        ('WR#', '14', 'PB13', 'PB13', 'PB13', 'вход ↑', 'выход'),
        ('CS#', '15', 'PB14', 'PB14', 'PB14', 'вход ↑', 'выход'),
        ('DATA[7:0]', '16…23', 'PD10…PD15, PF0, PF1', '', '', 'AF', 'AF'),
        ('DATA[15:8]', '24…31', 'PF2, PC6…PC9, PA13…PA15', '', '', 'AF', 'AF'),
        ('DATA[23:16]', '32…39', 'PC10…PC12, PD0…PD4', '', '', 'AF', 'AF'),
        ('DATA[31:24]', '40…47', 'PD5…PD7, PF3…PF5, PE0, PE1', '', '', 'AF', 'AF'),
    ]
    x0, y0, rh = 24, 170, 30
    x = x0
    for name, w in cols:
        d.o.append(f'<rect x="{x}" y="{y0}" width="{w}" height="{rh}" fill="#F4F4F5" stroke="#D4D4D8"/>')
        d.text(x + 8, y0 + 20, name, 12, 700)
        x += w
    for r, row in enumerate(rows):
        y = y0 + rh * (r + 1)
        x = x0
        shared = row[3] == '' and row[4] == ''
        for c, (val, (name, w)) in enumerate(zip(row, cols)):
            if shared and c in (3, 4):
                continue
            cw = w + (cols[3][1] + cols[4][1] if shared and c == 2 else 0)
            moved = c in (2, 3, 4) and not shared and len(set(row[2:5])) > 1
            fill = '#FDE8EC' if moved else ('#E6F6EC' if r >= 11 else '#FFFFFF')
            d.o.append(f'<rect x="{x}" y="{y}" width="{cw}" height="{rh}" fill="{fill}" stroke="#E4E4E7"/>')
            warn = '!' in val
            d.text(x + 8, y + 20, val, 12, 700 if (c == 0 or warn) else 400, ACC if warn else INK)
            x += cw
    y = y0 + rh * (len(rows) + 1) + 24
    d.text(24, y, 'PCLK (UHSIF_CLK): CLK_RM = 0 → PF11, 1 → PC0, 2 → PF14, 3 → PD9. Ведомый: вход ↓, ведущий: выход.', 13, 700)
    notes(d, y + 26, [
        'Розовые ячейки — PORT0…7, их меняет UHSIF_PORT_RM; управляющие PORT8…15 и данные PORT16…47 от ремапа не зависят.',
        '«Вход ↑/↓» — режим GPIO с подтяжкой, который ставит библиотека. У ведущего такт и стробы оставлены обычными GPIO-выходами,',
        'значит, направление выводов задаёт сам блок UHSIF. AF# везде настроен как вход с подтяжкой — даже там, где это выход ведомого.',
        'Для 16 бит нужны DATA[15:0] + 11 управляющих + PCLK = 28 сигналов (без SEL1, если каналов два, — 27). SDI отладки — PB8/PB9.'])
    d.save('10-pins.svg', MCU)


# =========================================================================== 11. power domains
def power():
    d = D(1200, 620, 'Питание выводов CH32H417: VDD33, VDDIO и VIO18',
          'По даташиту V1.8 (разделы 1.4 и 3, табл. 3-2). Все выводы UHSIF — в домене VIO18.')
    d.box(24, 96, 220, 92, 'VDD33', ['3,3 В', 'PA9…PA12, PC13…PC15,', 'PE3…PE6'], 'neutral')
    d.box(304, 96, 260, 92, 'VDDIO', ['1,65…3,6 В, не выше VDD33', 'PA0…PA8, PB2…PB7, PB15, PC4,', 'PC5, PD8, PE2, PF6…PF10'], 'neutral')
    d.box(624, 96, 180, 92, 'I/O LDO', ['встроенный', 'регулятор'], 'front')
    d.box(864, 96, 312, 150, 'VIO18 — выводы UHSIF', ['1,2 / 1,8 / 2,5 / 3,3 В или выкл,', 'PWR_CTLR[12:9] (CH32H417RM)',
                                                        'PA13…15, PB0…1, PB10…14, PC0…3,', 'PC6…12, PD0…7, PD9…15,',
                                                        'PE0…1, PE7…15, PF0…5, PF11…14'], 'usb', bold=True)
    d.arrow([(244, 142), (304, 142)])
    d.arrow([(564, 142), (624, 142)])
    d.arrow([(804, 142), (864, 142)])
    d.arrow([(434, 188), (434, 226), (864, 226)], dash=True, color=QUIET,
            label='или замкнуть VIO18 на VDDIO', lpos=(650, 218))
    d.text(24, 220, 'VDD33 ≥ VDD33A ≥ VDDIO ≥ VIO18', 14, 700)
    d.box(24, 300, 600, 150, 'Напряжение VIO18 после включения: резистор с XO на землю', [
        '60…110 кОм (тип. 82)  → 1,2 В', '220…400 кОм (тип. 300) → 2,5 В', '≥ 1,2 МОм или ничего → 1,8 В',
        '3,3 В при включении не выбрать: только программно или замкнуть на VDDIO', 'XO — вывод кварца HSE'], 'front')
    d.box(654, 300, 522, 150, 'Для нашей ПЛИС', [
        'GW2AR-18: банк к UHSIF на 3,3 В или на 1,8 В.', 'Банк на 3,3 В: VIO18 замкнуть на VDDIO = 3,3 В. Иначе до старта',
        'прошивки выводы МК при 1,8 В, а ПЛИС уже выдаёт 3,3 В в них.', 'Банк на 1,8 В: XO оставить без резистора, VIO18 = 1,8 В —',
        'и 125 МГц в таблице WCH указаны именно при 1,8 В.'], 'accent', bold=True)
    notes(d, 490, ['VIO18 = 1,1…3,6 В по таблице условий; переключать можно на ходу, но при подъёме напряжения ёмкость на VDDIO должна',
                  'быть намного больше ёмкости на VIO18 (просадка VDDIO). На VIO18 — 0,1 мкФ у каждого вывода и 2,2 мкФ у главного.',
                  'Выбор 3,3 В против 1,8 В для UHSIF — решение для схемы адаптера; на плате проверить уровни до подключения ПЛИС.'])
    d.legend(24, 596, [('usb', 'домен выводов UHSIF'), ('front', 'регулятор и выбор напряжения'), ('accent', 'вывод для стенда')])
    d.save('11-power.svg', MCU)


# =========================================================================== 12. block diagram
def block():
    d = D(1240, 600, 'CH32H417 как USB3-мост: путь данных ПЛИС → ПК',
          'Упрощено по рис. 1-1-1 даташита V1.8. Цветом — то, что участвует в мосте, серым — остальное.')
    d.box(24, 220, 150, 110, 'ПЛИС', ['ведущий UHSIF', 'PCLK, 16/32 бита'], 'fpga')
    d.frame(204, 84, 820, 470, 'CH32H417 (QFN128) / CH32H416 (QFN88)')
    d.box(234, 220, 190, 110, 'UHSIF', ['4 канала × 8 буферов', 'DMA по дескрипторам', 'IRQ 145'], 'usb', bold=True)
    d.box(464, 120, 270, 90, 'Ядра', ['RISC-V V5F и V3F', 'RV32IMAFBC + XW', 'ITCM 128 КБ, DTCM 256 КБ'], 'neutral')
    d.box(464, 240, 270, 90, 'RAM (общая SRAM 512 КБ)', ['буферы 16 КБ = буферы', 'конечной точки USB (без копий)'], 'ext', bold=True)
    d.box(774, 220, 220, 110, 'USB 3.2 Gen1', ['контроллер + SS PHY', 'EP1 bulk IN/OUT', 'USBHS — запасной путь'], 'usb', bold=True)
    d.box(474, 360, 250, 60, 'Шина HB, DMA1/2', ['матрица шин'], 'neutral')
    d.box(234, 450, 190, 80, 'RCC, AFIO, GPIO', ['такт, ремап,', 'VIO18'], 'neutral')
    d.box(474, 450, 520, 80, 'Остальное', ['Ethernet 10/100 + PHY, SerDes, USB PD, SDMMC, DVP, LTDC,',
                                           'таймеры, USART, SPI, I²C, I3C, CAN, ADC/HSADC, DAC, PIOC…'], 'neutral')
    d.box(1064, 220, 150, 110, 'ПК', ['USB3 SS', 'rln-trace'], 'host')
    d.arrow([(174, 275), (234, 275)], color=FPGA_C, width=3, both=True, label='UHSIF', lpos=(204, 265), lcolor=FPGA_C)
    d.arrow([(424, 275), (474, 285)], color=ACC, width=3)
    d.arrow([(724, 285), (774, 275)], color=ACC, width=3)
    d.arrow([(994, 275), (1064, 275)], color=MCU_C, width=3, both=True, label='USB3', lpos=(1029, 265), lcolor=MCU_C)
    d.arrow([(599, 210), (599, 240)], both=True)
    d.arrow([(599, 330), (599, 360)], both=True)
    d.text(234, 360, 'В примере WCH UHSIF пишет', 12, 400, QUIET)
    d.text(234, 376, 'прямо в USBSS_EP1_Tx_Buf,', 12, 400, QUIET)
    d.text(234, 392, 'а USB забирает оттуда же.', 12, 400, QUIET)
    d.legend(24, 580, [('fpga', 'ПЛИС'), ('usb', 'интерфейсы моста'), ('ext', 'буферы'), ('host', 'ПК'), ('neutral', 'прочее')])
    d.save('12-block.svg', MCU)


if __name__ == '__main__':
    write(); zlp(); read(); io_timing(); lines(); addr_map(); driver_flow(); rearm()
    clock(); pins(); power(); block()
    print('written to', os.path.abspath(UHSIF), 'and', os.path.abspath(MCU))
