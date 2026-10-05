"""Sketches of the bench adapters: top view + exploded isometric view.
Run: python3 tools/diagrams/bench_adapters.py  ->  doc/img/adapter-*.svg
All dimensions are in mm and are PLACEHOLDERS until the real boards are measured."""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_diagrams import D, DOC_IMG, INK, QUIET  # noqa: E402

C30 = math.cos(math.radians(30))

# colours: (top, stroke)
COL = {
    'evt':    '#2F6FB5',   # CH569 EVT board
    'disco':  '#E9EDF2',   # F4-Discovery
    'afpga':  '#1E3A8A',   # FPGA adapter (dark blue soldermask)
    'atgt':   '#9A3412',   # target adapter (dark orange)
    'tang':   '#1F2937',   # Tang Nano 20K
    'ft':     '#166534',   # FT2232H breakout
    'chip':   '#111827',
    'hdr':    '#0F0F10',
    'pin':    '#D4A72C',
    'mipi':   '#3F3F46',
    'sma':    '#D4A72C',
    'usb':    '#B8BCC4',
    'jack':   '#27272A',
    'part':   '#52525B',
    'test':   '#F59E0B',
}


def shade(hexc, k):
    h = hexc.lstrip('#')
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return '#%02X%02X%02X' % (int(r * k), int(g * k), int(b * k))


class Iso:
    def __init__(self, d, ox, oy, s):
        self.d, self.ox, self.oy, self.s = d, ox, oy, s
        self.items = []

    def p(self, x, y, z):
        return (self.ox + (x - y) * C30 * self.s, self.oy + (x + y) * 0.5 * self.s - z * self.s)

    def box(self, x, y, z, w, dp, h, col, layer=None):
        self.items.append((z if layer is None else layer, x + w / 2 + y + dp / 2, (x, y, z, w, dp, h, col)))

    def draw(self):
        for _, _, (x, y, z, w, dp, h, col) in sorted(self.items, key=lambda t: (t[0], t[1])):
            P = self.p
            top = [P(x, y, z + h), P(x + w, y, z + h), P(x + w, y + dp, z + h), P(x, y + dp, z + h)]
            right = [P(x + w, y, z), P(x + w, y + dp, z), P(x + w, y + dp, z + h), P(x + w, y, z + h)]
            left = [P(x, y + dp, z), P(x + w, y + dp, z), P(x + w, y + dp, z + h), P(x, y + dp, z + h)]
            for poly, k in ((left, 0.62), (right, 0.8), (top, 1.0)):
                pts = ' '.join(f'{a:.1f},{b:.1f}' for a, b in poly)
                self.d.o.append(f'<polygon points="{pts}" fill="{shade(col, k)}" stroke="{shade(col, 0.45)}" '
                                f'stroke-width="0.6" stroke-linejoin="round"/>')

    def guide(self, pts3):
        a, b = self.p(*pts3[0]), self.p(*pts3[1])
        self.d.o.append(f'<path d="M{a[0]:.1f} {a[1]:.1f} L{b[0]:.1f} {b[1]:.1f}" stroke="#9CA3AF" '
                        f'stroke-width="1" stroke-dasharray="4 4"/>')

    LX, RX = 0, 0

    def label(self, xyz, side, ty, text, color=INK):
        ax, ay = self.p(*xyz)
        tx, anchor = (self.LX, 'end') if side == 'L' else (self.RX, 'start')
        kx = tx + (14 if side == 'L' else -14)
        self.d.o.append(f'<circle cx="{ax:.1f}" cy="{ay:.1f}" r="2.8" fill="{color}" stroke="#fff" stroke-width="1"/>')
        self.d.o.append(f'<path d="M{ax:.1f} {ay:.1f} L{kx} {ty - 4} L{tx} {ty - 4}" fill="none" stroke="{color}" '
                        f'stroke-width="1"/>')
        self.d.o.append(f'<text x="{tx + (4 if side == "R" else -4)}" y="{ty}" font-size="12" font-weight="600" '
                        f'fill="{color}" text-anchor="{anchor}" stroke="#fff" stroke-width="4" '
                        f'paint-order="stroke">{text}</text>')


class Top:
    """Top-view sketch: origin at (ox, oy), scale s px/mm."""

    def __init__(self, d, ox, oy, s):
        self.d, self.ox, self.oy, self.s = d, ox, oy, s

    def r(self, x, y, w, h, fill, stroke, dash=False, rx=1.5, sw=1.4, op=1.0):
        da = ' stroke-dasharray="5 4"' if dash else ''
        self.d.o.append(f'<rect x="{self.ox + x * self.s:.1f}" y="{self.oy + y * self.s:.1f}" '
                        f'width="{w * self.s:.1f}" height="{h * self.s:.1f}" rx="{rx * self.s:.1f}" fill="{fill}" '
                        f'fill-opacity="{op}" stroke="{stroke}" stroke-width="{sw}"{da}/>')

    def t(self, x, y, s, size=11, weight=500, color=INK, anchor='middle'):
        self.d.text(round(self.ox + x * self.s, 1), round(self.oy + y * self.s, 1), s, size, weight, color, anchor)

    def ln(self, pts, color, width=2.5, dash=False):
        d = 'M' + ' L'.join(f'{self.ox + x * self.s:.1f} {self.oy + y * self.s:.1f}' for x, y in pts)
        da = ' stroke-dasharray="5 4"' if dash else ''
        self.d.o.append(f'<path d="{d}" fill="none" stroke="{color}" stroke-width="{width}"{da} '
                        f'stroke-linecap="round" stroke-linejoin="round"/>')

    def dim(self, x0, y0, x1, y1, text, off=6):
        s = self.s
        if y0 == y1:  # horizontal
            yy = self.oy + (y0 - off) * s
            a, b = self.ox + x0 * s, self.ox + x1 * s
            self.d.o.append(f'<path d="M{a:.1f} {yy:.1f} L{b:.1f} {yy:.1f} M{a:.1f} {yy - 5:.1f} L{a:.1f} {yy + 5:.1f} '
                            f'M{b:.1f} {yy - 5:.1f} L{b:.1f} {yy + 5:.1f}" stroke="{QUIET}" stroke-width="1"/>')
            self.d.text(round((a + b) / 2, 1), round(yy - 5, 1), text, 11, 500, QUIET, 'middle')
        else:
            xx = self.ox + (x0 - off) * s
            a, b = self.oy + y0 * s, self.oy + y1 * s
            self.d.o.append(f'<path d="M{xx:.1f} {a:.1f} L{xx:.1f} {b:.1f} M{xx - 5:.1f} {a:.1f} L{xx + 5:.1f} {a:.1f} '
                            f'M{xx - 5:.1f} {b:.1f} L{xx + 5:.1f} {b:.1f}" stroke="{QUIET}" stroke-width="1"/>')
            mid = (a + b) / 2
            self.d.o.append(f'<text x="{xx - 6:.1f}" y="{mid:.1f}" font-size="11" fill="{QUIET}" text-anchor="middle" '
                            f'transform="rotate(-90 {xx - 6:.1f} {mid:.1f})">{text}</text>')


ORANGE, BLUE, TEAL, PURPLE, GREY = '#E8590C', '#1C64F2', '#0B8EA0', '#7C3AED', '#6B7280'


def legend(d, x, y, items):
    cx = x
    for color, dash, label in items:
        da = ' stroke-dasharray="5 4"' if dash else ''
        d.o.append(f'<path d="M{cx} {y - 4} L{cx + 26} {y - 4}" stroke="{color}" stroke-width="2.5"{da}/>')
        d.text(cx + 32, y + 1, label, 12, 400, QUIET)
        cx += 46 + len(label) * 7.2


# --------------------------------------------------------------------------- FPGA adapter
# coordinates in mm, board origin = top-left corner of the CH569 EVT board (placeholder 80 x 60)
FW, FH = 80, 60
EVT_HDR = [(14.6, 2.5, 50.8, 5.1), (14.6, 52.4, 50.8, 5.1)]       # 2x20 rows of the EVT board (to measure)
TANG = (4, 18.75, 54, 22.5)                                       # Tang Nano 20K, USB-C at x = 4
TANG_ROWS = [(6, 19.5, 50.8, 2.5), (6, 38.5, 50.8, 2.5)]          # 1x20 sockets
MIPI = (62, 22, 5.8, 16)                                          # 2x10 1.27 mm shrouded
SMA = [(72, 9, 8, 7), (72, 44, 8, 7)]
PROBE = (8, 44.5, 25.4, 5.1)                                      # 2x10 probe header (G-S pairs)


def fpga():
    d = D(1500, 760, 'Адаптер ПЛИС: плата-переходник на гребёнки WCH CH569 EVT, Tang Nano 20K сверху по центру',
          'Эскиз. Размеры условные (мм) — уточнить по реальным платам. HSPI проходит вниз сквозь гребёнки EVT, '
          'трасса с MIPI20 — к соседним выводам Tang Nano.')
    # ---- top view
    t = Top(d, 70, 150, 5.2)
    t.r(0, 0, FW, FH, '#EEF2FF', COL['afpga'], sw=2.2)
    t.t(FW / 2, -10, 'вид сверху: адаптер (Tang Nano показана контуром)', 12, 700, INK)
    for x, y, w, h in EVT_HDR:
        t.r(x, y, w, h, '#FFFFFF', GREY, dash=True, rx=0.5)
    t.t(FW / 2, 5.9, 'гнёзда на гребёнку EVT (снизу): HSPI, питание, земля', 10, 500, QUIET)
    t.t(FW / 2, 55.8, 'гнёзда на вторую гребёнку EVT (снизу)', 10, 500, QUIET)
    x, y, w, h = TANG
    t.r(x, y, w, h, '#E5E7EB', COL['tang'], sw=1.6, op=0.55)
    for rx_, ry, rw, rh in TANG_ROWS:
        t.r(rx_, ry, rw, rh, '#111827', '#111827', rx=0.4)
    t.t(x + w / 2, y + h / 2 + 1.3, 'Tang Nano 20K (на гнёздах 1×20)', 11, 700)
    t.r(x - 1.5, y + h / 2 - 4.5, 7.5, 9, '#B8BCC4', '#71717A', rx=1)
    t.t(x + 9, y + h / 2 + 7.5, 'USB-C', 9, 500, QUIET, 'start')
    t.r(*MIPI, '#3F3F46', '#18181B', rx=0.6)
    t.t(MIPI[0] + 2.9, MIPI[1] - 1.5, 'MIPI20', 11, 700)
    for sx, sy, sw_, sh in SMA:
        t.r(sx, sy, sw_, sh, '#F5D77A', '#A16207', rx=0.6)
    t.t(70.5, 8.5, 'SMA1 (PPS)', 10, 600, TEAL, 'end')
    t.t(70.5, 48.5, 'SMA2', 10, 600, TEAL, 'end')
    t.r(*PROBE, '#FEF3C7', '#B45309', rx=0.5)
    t.t(PROBE[0] + PROBE[2] / 2, PROBE[1] + 3.6, 'щупы SLogic: S/G пары', 9, 600, '#92400E')
    # routes
    for i in range(5):
        yy = 25 + i * 2.5
        t.ln([(MIPI[0], yy), (58, yy), (55.5, 39.7 if i < 3 else 20.7)], ORANGE, 1.6)
    t.ln([(72, 12.5), (60, 12.5), (54, 20.7)], TEAL, 1.6)
    for i in range(4):
        xx = 18 + i * 9
        t.ln([(xx, 21.5), (xx, 7.6)], BLUE, 1.6, dash=True)
    t.ln([(20, 38.5), (20, 44.5)], '#B45309', 1.4)
    t.dim(0, 0, FW, 0, '≈ 80', off=4)
    t.dim(0, 0, 0, FH, '≈ 60', off=4)
    # notes under the top view
    notes = ['• Снизу — гнёзда на обе гребёнки EVT: механика и HSPI + питание 3,3 В + земля.',
             '• Tang Nano 20K вдоль длинной стороны, USB-C к краю — кабель не упирается в EVT.',
             '• MIPI20 вплотную к выводам Tang Nano, дорожки трассы ≤ 15 мм, выровнены.',
             '• Нижний слой — сплошная земля, переходные с землёй рядом с каждым сигналом.',
             '• Пары S/G для щупов SLogic16U3 на HSPI и трассе, SMA как у зонда B.']
    for i, s in enumerate(notes):
        d.text(50, 520 + i * 21, s, 12.5, 400, QUIET)
    legend(d, 50, 640, [(ORANGE, False, 'трасса'), (BLUE, True, 'HSPI вниз на EVT'), (TEAL, False, 'PPS / SMA'),
                        ('#B45309', False, 'щупы')])

    # ---- isometric, exploded
    iso = Iso(d, 1090, 330, 4.0)
    iso.LX, iso.RX = 900, 1330
    zA, zT = 30, 56  # exploded heights of the adapter and Tang Nano (real: ~11 and ~22)
    # EVT board
    iso.box(0, 0, 0, FW, FH, 1.6, COL['evt'])
    iso.box(30, 22, 1.6, 10, 10, 1.2, COL['chip'])                     # CH569
    iso.box(22, FH - 9, 1.6, 12, 12, 6, COL['usb'])                     # USB3 connector (side to measure)
    iso.box(45, 25, 1.6, 6, 4, 1, COL['part'])
    iso.box(55, 30, 1.6, 4, 4, 2.5, '#D4D4D8')                          # crystal
    for x, y, w, h in EVT_HDR:
        iso.box(x, y, 1.6, w, h, 2.5, COL['hdr'])
        iso.box(x + 0.6, y + 0.9, 4.1, w - 1.2, h - 1.8, 6, COL['pin'])
    # adapter: bottom sockets, plate, parts
    for x, y, w, h in EVT_HDR:
        iso.box(x, y, zA - 8.5, w, h, 8.5, COL['hdr'])
    iso.box(0, 0, zA, FW, FH, 1.6, COL['afpga'])
    top = zA + 1.6
    for x, y, w, h in TANG_ROWS:
        iso.box(x, y, top, w, h, 8.5, COL['hdr'])
    iso.box(*MIPI[:2], top, MIPI[2], MIPI[3], 5, COL['mipi'])
    for sx, sy, sw_, sh in SMA:
        iso.box(sx, sy, top, sw_, sh, 6.5, COL['sma'])
        iso.box(sx + sw_, sy + 1.5, top + 1.5, 6, 4, 4, COL['sma'])
    iso.box(*PROBE[:2], top, PROBE[2], PROBE[3], 2.5, COL['hdr'])
    iso.box(PROBE[0] + 0.6, PROBE[1] + 0.9, top + 2.5, PROBE[2] - 1.2, PROBE[3] - 1.8, 6, COL['pin'])
    # Tang Nano 20K with its pins
    x, y, w, h = TANG
    for rx_, ry, rw, rh in TANG_ROWS:
        iso.box(rx_ + 0.6, ry + 0.6, zT - 7, rw - 1.2, rh - 1.2, 7, COL['pin'])
    iso.box(x, y, zT, w, h, 1.6, COL['tang'])
    iso.box(24, 24, zT + 1.6, 12, 12, 1.4, '#000000')                   # GW2AR-18
    iso.box(x - 1, y + 7, zT + 1.6, 7.5, 9, 3.2, COL['usb'])            # USB-C
    iso.box(42, 22, zT + 1.6, 6, 6, 1, COL['part'])                     # BL616
    iso.box(10, 37, zT + 1.6, 3, 3, 1.5, '#E5E7EB')
    iso.draw()
    # assembly guides
    for gx, gy in ((0, FH), (FW, FH), (FW, 0)):
        iso.guide([(gx, gy, 1.6), (gx, gy, zA)])
    for gx, gy in ((x, y + h), (x + w, y + h)):
        iso.guide([(gx, gy, top), (gx, gy, zT)])
    # ribbon to the target
    a = iso.p(MIPI[0] + 2.9, MIPI[1] + MIPI[3], top + 5)
    d.o.append(f'<path d="M{a[0]:.1f} {a[1]:.1f} C {a[0] + 40:.1f} {a[1] + 40:.1f}, {a[0] + 60:.1f} {a[1] + 70:.1f}, '
               f'{a[0] + 120:.1f} {a[1] + 150:.1f}" fill="none" stroke="#A1A1AA" stroke-width="9" stroke-linecap="round"/>')
    d.text(round(a[0] + 132), round(a[1] + 160), 'шлейф MIPI20', 12, 600, QUIET, 'start')
    d.text(round(a[0] + 132), round(a[1] + 176), 'к адаптеру цели', 12, 600, QUIET, 'start')
    iso.label((x + w / 2, y, zT + 1.6), 'L', 110, 'Tang Nano 20K')
    iso.label((x + 2, y + 11, zT + 4.8), 'L', 150, 'USB-C → коммутатор')
    iso.label((4, FH, zA + 1.6), 'L', 330, 'адаптер ПЛИС (2 слоя)')
    iso.label((PROBE[0] + 3, PROBE[1] + 2.5, top + 8.5), 'L', 260, 'щупы SLogic16U3')
    iso.label((6, FH, 1.6), 'L', 470, 'WCH CH569 EVT')
    iso.label((28, FH + 3, 7.6), 'L', 560, 'USB3 → ПК (сторону уточнить)')
    iso.label((MIPI[0] + 2.9, MIPI[1] + 2, top + 5), 'R', 250, 'MIPI20: трасса + SWD/JTAG')
    iso.label((76, 12, top + 6.5), 'R', 300, 'SMA1 PPS, SMA2')
    d.text(1090, 735, 'разнесённый вид; в сборке адаптер лежит на гребёнке EVT, Tang Nano — на его гнёздах',
           12, 400, QUIET, 'middle')
    d.save('adapter-fpga.svg', DOC_IMG)


# --------------------------------------------------------------------------- target adapter
DW, DH = 97, 66                                   # STM32F4-Discovery (MB997)
P_HDR = [(16.75, 2.0, 63.5, 5.1), (16.75, 58.9, 63.5, 5.1)]   # P1 (top), P2 (bottom), 2x25
AX0, AW = 13.5, 70                                # adapter spans x 13.5..83.5, USB ends stay free
WIN = (24, 18, 32, 32)                            # window over the MCU / LEDs / buttons
FTM = (60, 13, 22, 42)                            # FT2232H breakout (placeholder 22 x 42)
FT_ROWS = [(61, 14, 2.5, 40), (78.5, 14, 2.5, 40)]
TMIPI = (22, 9.5, 16, 5.8)
TJMP = (41, 9.8, 12.7, 5.1)                       # 2x5 jumpers: trace source FT2232H
UJMP = (55, 44, 5.1, 5.1)                         # 2x2 jumpers: UART
TSMA = (13.5, 46, 7, 8)


def target():
    d = D(1500, 760, 'Адаптер цели: надевается сверху на STM32F4-Discovery, на нём MIPI20 и модуль FT2232H',
          'Эскиз. Размеры условные (мм): ширина Discovery ≈ 97 × 66, выводы PE2–PE6 и SWD/JTAG — уточнить по схеме MB997.')
    t = Top(d, 60, 150, 4.6)
    t.r(0, 0, DW, DH, '#F8FAFC', '#94A3B8', dash=True, sw=1.4)
    t.t(DW / 2, -10, 'вид сверху: адаптер поверх Discovery (контур платы — пунктир)', 12, 700, INK)
    t.r(-2, 26, 6, 8, '#E5E7EB', '#71717A', rx=0.8)
    t.r(DW - 4, 28, 6, 8, '#E5E7EB', '#71717A', rx=0.8)
    t.t(1, 40, 'USB', 9, 500, QUIET)
    t.t(DW - 1, 42, 'USB', 9, 500, QUIET)
    # adapter outline with window
    t.r(AX0, 0, AW, DH, '#FFF4ED', COL['atgt'], sw=2.2)
    t.r(*WIN, '#FFFFFF', COL['atgt'], sw=1.6)
    t.t(WIN[0] + WIN[2] / 2, WIN[1] + WIN[3] / 2, 'окно: MCU,', 10, 500, QUIET)
    t.t(WIN[0] + WIN[2] / 2, WIN[1] + WIN[3] / 2 + 3, 'кнопки, светодиоды', 10, 500, QUIET)
    for x, y, w, h in P_HDR:
        t.r(x, y, w, h, '#FFFFFF', GREY, dash=True, rx=0.5)
    t.t(48.5, 66 + 3.5, 'гнёзда на P2 (снизу): PA13/14/15, PB3/4, NRST — уточнить', 10, 500, QUIET)
    t.r(*TMIPI, '#3F3F46', '#18181B', rx=0.6)
    t.t(TMIPI[0] - 1, TMIPI[1] + 4.2, 'MIPI20', 11, 700, INK, 'end')
    t.r(*TJMP, '#111827', '#111827', rx=0.4)
    t.t(TJMP[0] + 6.3, TJMP[1] + 7.6, 'TRACE ← FT', 9, 600, ORANGE)
    t.r(*FTM, '#DCFCE7', COL['ft'], sw=1.6, op=0.85)
    for x, y, w, h in FT_ROWS:
        t.r(x, y, w, h, '#111827', '#111827', rx=0.4)
    t.t(FTM[0] + FTM[2] / 2, 33, 'FT2232H', 11, 700)
    t.t(FTM[0] + FTM[2] / 2, 37, 'breakout', 10, 500, QUIET)
    t.r(*UJMP, '#111827', '#111827', rx=0.4)
    t.t(UJMP[0] + 2.5, UJMP[1] + 8.5, 'UART', 9, 600, PURPLE)
    t.r(*TSMA, '#F5D77A', '#A16207', rx=0.6)
    t.t(TSMA[0] + 3.5, TSMA[1] + 11.5, 'SMA PPS', 9, 600, TEAL)
    # routes
    for i in range(5):
        xx = 24 + i * 3
        t.ln([(xx, 6.5), (xx, 9.5)], ORANGE, 1.8)
    for i in range(5):
        xx = 42.3 + i * 2.54
        t.ln([(xx, 9.8), (xx, 8), (38, 8)], ORANGE, 1.2, dash=True)
    t.ln([(53.7, 12.3), (61, 16)], ORANGE, 1.2, dash=True)
    t.ln([(30, 15.3), (30, 17), (20, 17), (20, 58.9)], PURPLE, 1.6)
    t.ln([(57.5, 49.1), (57.5, 56), (40, 56), (40, 58.9)], PURPLE, 1.4)
    t.ln([(20.5, 50), (22, 56), (26, 58.9)], TEAL, 1.6)
    t.dim(AX0, 0, AX0 + AW, 0, '≈ 70', off=4)
    t.dim(0, 0, 0, DH, '≈ 66', off=5)
    notes = ['• Гнёзда снизу на P1 и P2 Discovery; концы платы с USB остаются открытыми.',
             '• У выводов PE2–PE6 — 33 Ом, дальше ≤ 15 мм до MIPI20; SWD/JTAG и NRST тоже на MIPI20.',
             '• FT2232H на гнёздах; канал A подключается к линиям трассы перемычками 2×5 (STM32 в Hi-Z).',
             '• Канал B ↔ USART2 (PA2/PA3) через перемычки 2×2; PPS с таймера на SMA.',
             '• Окно над MCU: видны светодиоды, доступны кнопки RESET и USER.']
    for i, s in enumerate(notes):
        d.text(50, 520 + i * 21, s, 12.5, 400, QUIET)
    legend(d, 50, 640, [(ORANGE, False, 'трасса'), (ORANGE, True, 'трасса от FT2232H'), (PURPLE, False, 'SWD/JTAG, UART'),
                        (TEAL, False, 'PPS')])

    # ---- isometric
    iso = Iso(d, 1010, 320, 3.6)
    iso.LX, iso.RX = 830, 1270
    zA, zF = 28, 50
    iso.box(0, 0, 0, DW, DH, 1.6, COL['disco'])
    iso.box(38, 27, 1.6, 14, 14, 1.4, COL['chip'])                    # STM32F407
    iso.box(84, 15, 1.6, 7, 7, 1.2, COL['chip'])                      # ST-LINK MCU
    iso.box(DW - 6, 28, 1.6, 8, 8, 4, COL['usb'])                     # mini-USB ST-LINK
    iso.box(-2, 26, 1.6, 6, 8, 3, COL['usb'])                         # micro-USB OTG
    iso.box(10, 48, 1.6, 7, 12, 5.5, COL['jack'])                     # audio jack
    iso.box(30, 22, 1.6, 4, 4, 1, COL['part'])                        # accelerometer
    iso.box(26, 42, 1.6, 6, 6, 3, '#1D4ED8')                          # USER button
    for i, c in enumerate(('#22C55E', '#F97316', '#EF4444', '#3B82F6')):
        iso.box(46 + i * 3, 46, 1.6, 1.6, 1, 0.8, c)
    for x, y, w, h in P_HDR:
        iso.box(x, y, 1.6, w, h, 2.5, COL['hdr'])
        iso.box(x + 0.6, y + 0.9, 4.1, w - 1.2, h - 1.8, 6, COL['pin'])
    for x, y, w, h in P_HDR:
        iso.box(x, y, zA - 8.5, w, h, 8.5, COL['hdr'])
    # adapter plate with window: four bars
    wx, wy, ww, wh = WIN
    for bx, by, bw, bh in ((AX0, 0, AW, wy), (AX0, wy + wh, AW, DH - wy - wh),
                           (AX0, wy, wx - AX0, wh), (wx + ww, wy, AX0 + AW - wx - ww, wh)):
        iso.box(bx, by, zA, bw, bh, 1.6, COL['atgt'], layer=zA)
    top = zA + 1.6
    iso.box(*TMIPI[:2], top, TMIPI[2], TMIPI[3], 5, COL['mipi'])
    iso.box(*TJMP[:2], top, TJMP[2], TJMP[3], 2.5, COL['hdr'])
    iso.box(*UJMP[:2], top, UJMP[2], UJMP[3], 2.5, COL['hdr'])
    iso.box(*TSMA[:2], top, TSMA[2], TSMA[3], 6.5, COL['sma'])
    iso.box(TSMA[0] - 6, TSMA[1] + 2, top + 1.5, 6, 4, 4, COL['sma'])
    for x, y, w, h in FT_ROWS:
        iso.box(x, y, top, w, h, 8.5, COL['hdr'])
    for i in range(5):
        iso.box(24 + i * 3, 5.5, top, 1.6, 0.8, 0.6, '#E5E7EB')       # 33 Ohm
    # FT2232H breakout
    for x, y, w, h in FT_ROWS:
        iso.box(x + 0.6, y + 0.6, zF - 7, w - 1.2, h - 1.2, 7, COL['pin'])
    iso.box(*FTM[:2], zF, FTM[2], FTM[3], 1.6, COL['ft'])
    iso.box(65, 28, zF + 1.6, 10, 10, 1.4, COL['chip'])
    iso.box(67, FTM[1] + FTM[3] - 6, zF + 1.6, 8, 7, 3.5, COL['usb'])
    iso.box(66, 18, zF + 1.6, 4, 4, 1, COL['part'])
    iso.draw()
    for gx, gy in ((AX0, DH), (AX0 + AW, DH), (AX0 + AW, 0)):
        iso.guide([(gx, gy, 1.6), (gx, gy, zA)])
    for gx, gy in ((FTM[0], FTM[1] + FTM[3]), (FTM[0] + FTM[2], FTM[1] + FTM[3])):
        iso.guide([(gx, gy, top), (gx, gy, zF)])
    a = iso.p(TMIPI[0] + 8, TMIPI[1], top + 5)
    d.o.append(f'<path d="M{a[0]:.1f} {a[1]:.1f} C {a[0] + 10:.1f} {a[1] - 50:.1f}, {a[0] - 40:.1f} {a[1] - 60:.1f}, '
               f'{a[0] - 90:.1f} {a[1] - 110:.1f}" fill="none" stroke="#A1A1AA" stroke-width="9" stroke-linecap="round"/>')
    d.text(round(a[0] - 95), round(a[1] - 122), 'шлейф MIPI20 к адаптеру ПЛИС', 12, 600, QUIET, 'end')
    iso.label((TMIPI[0] + 8, TMIPI[1] + 3, top + 5), 'L', 200, 'MIPI20')
    iso.label((TSMA[0] - 3, TSMA[1] + 4, top + 5.5), 'L', 330, 'SMA PPS')
    iso.label((AX0 + 20, DH, zA + 1.6), 'L', 420, 'адаптер цели (2 слоя, окно над MCU)')
    iso.label((30, DH, 1.6), 'L', 520, 'STM32F4-Discovery')
    iso.label((FTM[0] + 11, FTM[1] + 20, zF + 1.6), 'R', 200, 'FT2232H breakout')
    iso.label((71, FTM[1] + FTM[3] - 2, zF + 5), 'R', 250, 'USB → коммутатор')
    iso.label((DW - 2, 32, 5.6), 'R', 500, 'ST-LINK → коммутатор')
    d.text(1010, 735, 'разнесённый вид; в сборке адаптер лежит на гребёнках P1/P2, FT2232H — на его гнёздах',
           12, 400, QUIET, 'middle')
    d.save('adapter-target.svg', DOC_IMG)


if __name__ == '__main__':
    fpga()
    target()
    print('written to', os.path.abspath(DOC_IMG))
