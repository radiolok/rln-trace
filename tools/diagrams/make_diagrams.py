"""Architecture diagrams for rln-trace (SVG). Run: python3 tools/diagrams/make_diagrams.py
Output: hw/img/*.svg"""
import os
from xml.sax.saxutils import escape

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../hw/img')

# kind -> (fill, stroke)
PAL = {
    'target':   ('#FFF1E6', '#E8590C'),
    'front':    ('#FFF8DB', '#E09400'),
    'fpga':     ('#E8F0FF', '#1C64F2'),
    'usb':      ('#E6F6EC', '#13924F'),
    'host':     ('#F3EBFF', '#7C3AED'),
    'ext':      ('#E2F7F8', '#0B8EA0'),
    'neutral':  ('#F4F4F5', '#71717A'),
    'trc':      ('#FFF1E6', '#E8590C'),
    'sys':      ('#E8F0FF', '#1C64F2'),
    'ts':       ('#E2F7F8', '#0B8EA0'),
    'accent':   ('#FDE8EC', '#D6336C'),
}
INK, QUIET, LINE = '#111827', '#4B5563', '#6B7280'
FONT = "font-family=\"'Segoe UI','DejaVu Sans',Helvetica,Arial,sans-serif\""


class D:
    def __init__(self, w, h, title, subtitle=None):
        self.w, self.h = w, h
        self.o = []
        self.o.append(f'<rect x="0" y="0" width="{w}" height="{h}" rx="14" fill="#FFFFFF"/>')
        self.text(24, 34, title, 18, 700)
        if subtitle:
            self.text(24, 56, subtitle, 13, 400, QUIET)
        self.markers = set()

    def text(self, x, y, s, size=13, weight=400, color=INK, anchor='start'):
        self.o.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
                      f'fill="{color}" text-anchor="{anchor}">{escape(s)}</text>')

    def box(self, x, y, w, h, title, lines=(), kind='neutral', bold=False, center=False):
        fill, stroke = PAL[kind]
        sw = 2.5 if bold else 1.6
        self.o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" '
                      f'stroke="{stroke}" stroke-width="{sw}"/>')
        if center:
            ty = y + h / 2 - (len(lines) * 8) + 5
            self.text(x + w / 2, ty, title, 14, 700, INK, 'middle')
            for i, ln in enumerate(lines):
                self.text(x + w / 2, ty + 19 + i * 17, ln, 12, 400, QUIET, 'middle')
        else:
            self.text(x + 12, y + 23, title, 14, 700)
            for i, ln in enumerate(lines):
                self.text(x + 12, y + 42 + i * 17, ln, 12, 400, QUIET)

    def frame(self, x, y, w, h, label, color='#9CA3AF'):
        self.o.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="none" '
                      f'stroke="{color}" stroke-width="1.5" stroke-dasharray="6 5"/>')
        self.text(x + 14, y + 20, label, 13, 700, QUIET)

    def _marker(self, color):
        mid = 'a' + color.strip('#')
        if mid not in self.markers:
            self.markers.add(mid)
            self.o.insert(0, f'<defs><marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" '
                             f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
                             f'<path d="M0 0L10 5L0 10z" fill="{color}"/></marker></defs>')
        return mid

    def arrow(self, pts, color=LINE, both=False, dash=False, width=1.8, label=None, lpos=None,
              lanchor='middle', lcolor=None):
        mid = self._marker(color)
        d = 'M' + ' L'.join(f'{x} {y}' for x, y in pts)
        extra = f' marker-start="url(#{mid})"' if both else ''
        da = ' stroke-dasharray="5 4"' if dash else ''
        self.o.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{da} '
                      f'marker-end="url(#{mid})"{extra}/>')
        if label:
            lx, ly = lpos
            self.text(lx, ly, label, 12, 600, lcolor or color, lanchor)

    def line(self, pts, color=LINE, dash=False, width=1.5):
        d = 'M' + ' L'.join(f'{x} {y}' for x, y in pts)
        da = ' stroke-dasharray="5 4"' if dash else ''
        self.o.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{da}/>')

    def legend(self, x, y, items):
        cx = x
        for kind, label in items:
            fill, stroke = PAL[kind]
            self.o.append(f'<rect x="{cx}" y="{y - 11}" width="14" height="14" rx="3" fill="{fill}" '
                          f'stroke="{stroke}" stroke-width="1.6"/>')
            self.text(cx + 20, y + 1, label, 12, 400, QUIET)
            cx += 34 + len(label) * 7.4

    def save(self, name):
        os.makedirs(OUT, exist_ok=True)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {self.w} {self.h}" '
               f'width="{self.w}" height="{self.h}" {FONT} role="img">' + ''.join(self.o) + '</svg>\n')
        open(os.path.join(OUT, name), 'w').write(svg)


# --------------------------------------------------------------------------- system overview
def system():
    d = D(1140, 510, 'rln-trace: трасса, события и отладка идут на ПК по одному USB3',
          'Зонд B (своя плата). Направление A — SLogic16U3 с нашей прошивкой — заменяет блоки в рамке, кроме отладки и питания цели.')
    y, h = 120, 150
    d.frame(214, 84, 710, 356, 'Зонд B')
    d.box(24, y, 150, h, 'Цель', ['STM32F407', 'ETM → TPIU', 'RISC-V: PIB', 'SWD / JTAG'], 'target')
    d.box(234, y, 180, h, 'Входной каскад', ['MIPI20', 'ESD, 33 Ом', 'трансляторы AVC', 'VREF 1,2–3,6 В',
                                             'TgtPwr + INA219'], 'front')
    d.box(454, y, 220, h, 'ПЛИС GW2AR-18', ['приём трассы (IDDR)', 'деформатор TPIU', 'метки времени',
                                            'движок SWD/JTAG', 'кольцо в SDRAM 8 МБ'], 'fpga', bold=True)
    d.box(724, y, 180, h, 'CH569W', ['USB 3.0 SS device', 'трасса как у ORBTrace', 'CMSIS-DAP v2',
                                     'CDC, DFU', 'загрузка ПЛИС'], 'usb')
    d.box(974, y, 150, h, 'ПК', ['утилита rln-trace', 'Orbuculum', 'OpenCSD', 'Perfetto', 'OpenOCD'], 'host')
    d.box(454, 330, 220, 84, 'SMA1, SMA2', ['PPS, 10 МГц TTL, триггеры', 'вход или выход'], 'ext')
    cy = y + h / 2
    d.arrow([(174, cy), (234, cy)], both=True, label='MIPI20', lpos=(204, cy - 10))
    d.arrow([(414, cy), (454, cy)], both=True)
    d.arrow([(674, cy), (724, cy)], both=True, label='HSPI', lpos=(699, cy - 10))
    d.arrow([(904, cy), (974, cy)], both=True, label='USB3', lpos=(939, cy - 10))
    d.arrow([(564, 330), (564, y + h)], both=True)
    d.legend(24, 478, [('target', 'цель'), ('front', 'защита и уровни'), ('fpga', 'ПЛИС'),
                       ('usb', 'USB-мост'), ('host', 'ПК'), ('ext', 'внешние сигналы')])
    d.save('system.svg')


# --------------------------------------------------------------------------- front end
def frontend():
    d = D(1080, 600, 'Входной каскад: защита, затем транслятор с питанием стороны цели от VREF',
          'По умолчанию трансляторы выключены (OE = 1); прошивка включает их, только когда VREF в окне 1,2–3,6 В.')
    T = 120
    d.box(24, T, 150, 220, 'MIPI20', ['1  VREF', '2  TMS / SWDIO', '4  TCK / SWCLK', '6  TDO / SWO',
                                      '8  TDI', '10 nRESET', '12 TRC_CLK', '14–20 TRC_DATA[0..3]',
                                      '11/13 GND / TgtPwr'], 'target')
    d.box(214, T, 150, 330, 'Защита', ['TPD4E02B04 ×3', '(~0,5 пФ на линию)', '', 'затем 33 Ом',
                                       'последовательно', '(подбор на макете)'], 'front')
    d.box(404, T, 230, 110, 'SN74AVC8T245 (приём)', ['DIR = 0: цель → ПЛИС', 'TRC_CLK, TRC_DATA[0..3]',
                                                     'TDO / SWO, контроль nRESET'], 'front')
    d.box(404, T + 126, 230, 92, 'SN74AVC4T245', ['гр. 1: SWDIO, DIR от ПЛИС', 'гр. 2: SWCLK, TDI → цель'], 'front')
    d.box(404, T + 234, 230, 96, 'nRESET: 2N7002', ['открытый сток,', 'читается через AVC8T245'], 'front')
    d.box(674, T, 170, 330, 'ПЛИС', ['банк 6: трасса', '  TRC_CLK на GCLKT_6', '  IDDR + IODELAY', '',
                                     'банк 0: отладка', '  SWDIO, DIR', '  SWCLK, TDI', '  NRST_DRV', '',
                                     'OE трансляторов'], 'fpga')
    d.arrow([(174, T + 110), (214, T + 110)], both=True)
    d.arrow([(364, T + 55), (404, T + 55)])
    d.arrow([(364, T + 172), (404, T + 172)], both=True)
    d.arrow([(364, T + 282), (404, T + 282)], both=True)
    d.arrow([(634, T + 55), (674, T + 55)])
    d.arrow([(634, T + 172), (674, T + 172)], both=True)
    d.arrow([(674, T + 282), (634, T + 282)])
    # VREF path
    d.box(214, 488, 200, 84, 'VREF → VREF_F', ['10 Ом + 1 мкФ', 'питает VCCB трансляторов'], 'ext')
    d.box(454, 488, 180, 84, 'ADS1115 (I²C)', ['VREF/2, TgtPwr/2,', '5V/2, 3V3/2'], 'ext')
    d.arrow([(99, T + 220), (99, 530), (214, 530)], color='#0B8EA0', label='VREF', lpos=(106, 520),
            lanchor='start', lcolor='#0B8EA0')
    d.arrow([(414, 530), (454, 530)], color='#0B8EA0')
    # target power
    d.box(884, T, 172, 190, 'Питание цели', ['+5 В → AP2161', '  (ограничение тока)', 'шунт 0,1 Ом', '  + INA219',
                                             'JP1: контакты 11/13', '  GND или TgtPwr', '10 пФ у контактов'], 'usb')
    d.arrow([(970, T), (970, 92), (60, 92), (60, T)], color='#13924F', dash=True,
            label='TgtPwr → контакты 11/13', lpos=(520, 108), lcolor='#13924F')
    d.legend(674, 540, [('target', 'разъём'), ('front', 'защита и уровни'), ('fpga', 'ПЛИС')])
    d.legend(674, 566, [('ext', 'VREF и измерения'), ('usb', 'питание цели')])
    d.save('frontend.svg')


# --------------------------------------------------------------------------- gateware
def gateware():
    d = D(1080, 530, 'Гейтвар: трасса, события и команды сходятся в мосте HSPI',
          'Цвет блока — домен тактирования. Переходы между доменами — асинхронные FIFO.')
    W, H = 220, 92
    xs = [24, 290, 556, 822]
    y1, y2, y3 = 90, 250, 380
    d.box(xs[0], y1, W, H, 'IDDR + IODELAY', ['2 ниббла за такт TRC_CLK', 'задержка на каждую линию'], 'trc')
    d.box(xs[1], y1, W, H, 'Сборка слов', ['32 бита', 'async FIFO: TRC_CLK → sys'], 'trc')
    d.box(xs[2], y1, W, H, 'Деформатор TPIU', ['синхронизация, кадры 16 Б', 'выброс idle, номер кадра'], 'sys', bold=True)
    d.box(xs[3], y1, W, H, 'Пакетизатор', ['ответы > события > трасса', 'заголовок 4 Б + данные'], 'sys')
    d.box(xs[0], y2, W, H, 'Самотест', ['PRBS и синтетические', 'кадры TPIU'], 'sys')
    d.box(xs[1], y2, W, H, 'Счётчик 64 бита', ['PLL 200–250 МГц', 'опора: SMA1 или генератор'], 'ts')
    d.box(xs[2], y2, W, H, 'Захват событий', ['фронты SMA1/SMA2, PPS', 'служебные метки кадров'], 'ts')
    d.box(xs[3], y2, W, H, 'Кольцо в SDRAM', ['64 Мбит в корпусе ПЛИС', '~100 мс на пике 84 МБ/с'], 'sys')
    d.box(xs[1], y3, W, H, 'Движок SWD/JTAG', ['целые транзакции', 'ACK, WAIT, чётность'], 'sys')
    d.box(xs[2], y3, W, H, 'Регистры CSR', ['настройка всех блоков', 'счётчики ошибок'], 'sys')
    d.box(xs[3], y3, W, H, 'Мост HSPI → CH569', ['16 бит (макет: 8 бит)', 'трасса, события, команды'], 'usb', bold=True)
    cy1, cy2, cy3 = y1 + H / 2, y2 + H / 2, y3 + H / 2
    d.arrow([(xs[0] + W, cy1), (xs[1], cy1)])
    d.arrow([(xs[1] + W, cy1), (xs[2], cy1)])
    d.arrow([(xs[2] + W, cy1), (xs[3], cy1)])
    d.arrow([(xs[0] + W / 2, y2), (xs[0] + W / 2, y1 + H + 22), (xs[2] + 40, y1 + H + 22), (xs[2] + 40, y1 + H)],
            dash=True, label='вместо входа', lpos=(xs[1] + W / 2, y1 + H + 16))
    d.arrow([(xs[1] + W, cy2), (xs[2], cy2)], color='#0B8EA0')
    d.arrow([(xs[2] + W - 20, y2), (xs[2] + W - 20, y1 + H + 26), (xs[3] + 30, y1 + H + 26), (xs[3] + 30, y1 + H)],
            color='#0B8EA0', label='события', lpos=(xs[3] + 20, y1 + H + 20), lanchor='end', lcolor='#0B8EA0')
    d.arrow([(xs[2] + 130, y1 + H), (xs[2] + 130, y2)], color='#E8590C', dash=True,
            label='frameStrobe', lpos=(xs[2] + 124, y1 + H + 46), lanchor='end', lcolor='#E8590C')
    d.arrow([(xs[3] + 150, y1 + H), (xs[3] + 150, y2)], label='трасса', lpos=(xs[3] + 156, y1 + H + 46),
            lanchor='start')
    d.arrow([(xs[3] + W / 2 + 40, y2 + H), (xs[3] + W / 2 + 40, y3)])
    d.arrow([(xs[3], cy3), (xs[2] + W, cy3)], both=True)
    d.arrow([(xs[2], cy3), (xs[1] + W, cy3)])
    d.arrow([(xs[1], cy3), (xs[0] + W, cy3)])
    d.box(xs[0], y3 + 23, W, 46, 'MIPI20 (трансляторы)', [], 'target', center=True)
    d.legend(24, 510, [('trc', 'домен TRC_CLK (такт цели)'), ('sys', 'домен sys'), ('ts', 'домен ts (метки времени)'),
                       ('usb', 'выход к CH569')])
    d.save('gateware.svg')


# --------------------------------------------------------------------------- deformatter FSM
def fsm():
    d = D(1000, 400, 'Деформатор: кадры идут на выход только после двух синхрослов на границе кадра',
          'Синхрослово TPIU — 0x7FFFFFFF. Период синхрослов задаёт цель (TPIU_FSCR), N и таймаут — регистры CSR.')
    W, H = 200, 84
    s = [(40, 140), (400, 140), (760, 140)]
    d.box(*s[0], W, H, 'ПОИСК', ['окно 32 бита', 'сдвиг по нибблу'], 'neutral', center=True)
    d.box(*s[1], W, H, 'ПРОВЕРКА', ['ждём синхрослово', 'через k×16 байт'], 'front', center=True)
    d.box(*s[2], W, H, 'ЗАХВАТ', ['счёт байт по mod 16', 'синхрослова вырезаются'], 'fpga', bold=True, center=True)
    d.arrow([(240, 165), (400, 165)], label='найдено 0x7FFFFFFF', lpos=(320, 156))
    d.arrow([(600, 165), (760, 165)], label='синхрослово на границе', lpos=(680, 156))
    d.arrow([(400, 205), (240, 205)], label='не на границе', lpos=(320, 224))
    d.arrow([(820, 140), (820, 104), (900, 104), (900, 140)], label='кадр или синхрослово на границе',
            lpos=(860, 96))
    d.arrow([(820, 224), (820, 280), (140, 280), (140, 224)], color='#D6336C',
            label='синхрослово не на границе N раз подряд', lpos=(480, 272), lcolor='#D6336C')
    d.box(40, 310, 220, 60, 'Счётчики ошибок', ['ресинхронизации → CSR'], 'neutral')
    d.box(740, 310, 240, 60, 'Выход', ['кадр 16 байт + номер кадра'], 'sys')
    d.line([(150, 280), (150, 310)], dash=True)
    d.arrow([(860, 224), (860, 310)], color='#1C64F2')
    d.save('fsm.svg')


# --------------------------------------------------------------------------- frames and events
def events():
    d = D(1000, 270, 'Событие привязано к номеру кадра трассы, а не только ко времени',
          'Номер кадра режет поток на интервалы PPS–PPS с точностью до 16 байт; служебные метки пересчитывают время внутри.')
    x0, y = 200, 100
    for i, lab in enumerate(['N', 'N+1', 'N+2', 'N+3', 'N+4', 'N+5', 'N+6']):
        d.box(x0 + i * 110, y, 96, 44, lab, [], 'sys', center=True)
    d.text(24, y + 20, 'Кадры TPIU', 14, 700)
    d.text(24, y + 38, 'поток трассы', 12, 400, QUIET)
    yl = 220
    d.line([(x0, yl), (x0 + 7 * 110 - 14, yl)], color='#9CA3AF', width=2)
    d.text(24, yl - 4, 'Журнал событий', 14, 700)
    d.text(24, yl + 14, 'поток событий', 12, 400, QUIET)
    # service mark
    sx = x0 + 48
    d.line([(sx, y + 44), (sx, yl - 7)], color='#9CA3AF', dash=True)
    d.o.append(f'<circle cx="{sx}" cy="{yl}" r="7" fill="#FFFFFF" stroke="#0B8EA0" stroke-width="2"/>')
    d.text(sx + 12, yl + 30, 'служебная метка: кадр N пришёл в T0', 12, 400, QUIET)
    # PPS
    px = x0 + 3 * 110 - 7
    d.line([(px, 80), (px, yl - 8)], color='#D6336C', dash=True, width=2)
    d.o.append(f'<circle cx="{px}" cy="{yl}" r="8" fill="#D6336C"/>')
    d.text(px + 14, 82, 'PPS↑: время T, позиция = кадр N+3', 13, 700, '#D6336C')
    sx2 = x0 + 6 * 110 + 48
    d.line([(sx2, y + 44), (sx2, yl - 7)], color='#9CA3AF', dash=True)
    d.o.append(f'<circle cx="{sx2}" cy="{yl}" r="7" fill="#FFFFFF" stroke="#0B8EA0" stroke-width="2"/>')
    d.text(sx2 - 4, yl + 30, 'кадр N+6 в T1', 12, 400, QUIET, 'end')
    d.save('events.svg')


if __name__ == '__main__':
    system(); frontend(); gateware(); fsm(); events()
    print('written to', os.path.abspath(OUT))
