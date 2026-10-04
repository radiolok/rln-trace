"""Symbol model: load KiCad-5 .lib symbols (verified KiCad library pinouts),
build custom symbols, and emit KiCad 9 S-expressions."""
import re, glob, math, os

MIL = 0.0254
# KiCad 5 symbol libraries (git clone https://github.com/KiCad/kicad-symbols)
KSYM = os.environ.get('KICAD5_SYMBOLS', os.path.expanduser('~/kicad-symbols'))

ETYPE = {'I': 'input', 'O': 'output', 'B': 'bidirectional', 'T': 'tri_state',
         'P': 'passive', 'U': 'unspecified', 'W': 'power_in', 'w': 'power_out',
         'C': 'open_collector', 'E': 'open_emitter', 'N': 'no_connect'}
SHAPE = {'': 'line', 'I': 'inverted', 'C': 'clock', 'CI': 'inverted_clock',
         'L': 'input_low', 'CL': 'clock_low', 'V': 'output_low',
         'F': 'edge_clock_high', 'X': 'non_logic'}
ORIENT = {'R': 0, 'U': 90, 'L': 180, 'D': 270}


def r2(v):
    return round(v + 0.0, 4)


def kname(n):
    """KiCad5 '~' toggles overbar -> KiCad6+ '~{...}' syntax."""
    if n == '~':
        return ''
    out, on = '', False
    for ch in n:
        if ch == '~':
            out += '}' if on else '~{'
            on = not on
        else:
            out += ch
    if on:
        out += '}'
    return out


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


class Pin:
    def __init__(self, name, num, x, y, length, ang, etype, shape='line',
                 hidden=False, unit=1):
        self.name, self.num = name, str(num)
        self.x, self.y, self.length, self.ang = x, y, length, ang
        self.etype, self.shape, self.hidden, self.unit = etype, shape, hidden, unit

    def sexpr(self):
        hide = ' (hide yes)' if self.hidden else ''
        return (f'(pin {self.etype} {self.shape} (at {r2(self.x)} {r2(self.y)} {self.ang}) '
                f'(length {r2(self.length)}){hide} '
                f'(name {q(self.name)} (effects (font (size 1.27 1.27)))) '
                f'(number {q(self.num)} (effects (font (size 1.27 1.27)))))')


class Symbol:
    def __init__(self, name, ref='U', units=1, power=False):
        self.name, self.ref, self.units, self.power = name, ref, units, power
        self.pins = []
        self.gfx = []          # (unit, sexpr_string, bbox points)
        self.pin_name_offset = 0.508
        self.show_pin_numbers = True
        self.show_pin_names = True
        self.footprint = ''
        self.datasheet = '~'
        self.description = ''
        self.unit_names = {}

    # ---- geometry helpers -------------------------------------------------
    def rect(self, x1, y1, x2, y2, unit=1, fill='background'):
        self.gfx.append((unit, f'(rectangle (start {r2(x1)} {r2(y1)}) (end {r2(x2)} {r2(y2)}) '
                               f'(stroke (width 0.254) (type default)) (fill (type {fill})))',
                         [(x1, y1), (x2, y2)], ('rect', x1, y1, x2, y2, fill)))

    def poly(self, pts, unit=1, fill='none', width=0.254):
        p = ' '.join(f'(xy {r2(x)} {r2(y)})' for x, y in pts)
        self.gfx.append((unit, f'(polyline (pts {p}) (stroke (width {width}) (type default)) '
                               f'(fill (type {fill})))', pts, ('poly', pts, fill)))

    def circle(self, x, y, r, unit=1, fill='none'):
        self.gfx.append((unit, f'(circle (center {r2(x)} {r2(y)}) (radius {r2(r)}) '
                               f'(stroke (width 0.254) (type default)) (fill (type {fill})))',
                         [(x - r, y - r), (x + r, y + r)], ('circle', x, y, r, fill)))

    def arc(self, s, m, e, unit=1):
        self.gfx.append((unit, f'(arc (start {r2(s[0])} {r2(s[1])}) (mid {r2(m[0])} {r2(m[1])}) '
                               f'(end {r2(e[0])} {r2(e[1])}) (stroke (width 0.254) (type default)) '
                               f'(fill (type none)))', [s, m, e], ('arc', s, m, e)))

    def text(self, x, y, txt, unit=1, size=1.27):
        self.gfx.append((unit, f'(text {q(txt)} (at {r2(x)} {r2(y)} 0) '
                               f'(effects (font (size {size} {size}))))', [(x, y)],
                         ('text', x, y, txt, size)))

    def add_pin(self, *a, **k):
        p = Pin(*a, **k)
        self.pins.append(p)
        return p

    def pins_of_unit(self, unit):
        return [p for p in self.pins if p.unit in (0, unit)]

    def bbox(self, unit):
        pts = []
        for u, _, b, _ in self.gfx:
            if u in (0, unit):
                pts += b
        for p in self.pins_of_unit(unit):
            pts.append((p.x, p.y))
        if not pts:
            return (0, 0, 0, 0)
        xs = [a for a, _ in pts]
        ys = [b for _, b in pts]
        return min(xs), min(ys), max(xs), max(ys)

    # ---- output ------------------------------------------------------------
    def sexpr(self, libname=None, value=None):
        nm = f'{libname}:{self.name}' if libname else self.name
        out = [f'(symbol {q(nm)}']
        if self.power:
            out.append('(power)')
        pn = f'(pin_names (offset {self.pin_name_offset})'
        if not self.show_pin_names:
            pn += ' (hide yes)'
        out.append(pn + ')')
        if not self.show_pin_numbers:
            out.append('(pin_numbers (hide yes))')
        out.append('(exclude_from_sim no) (in_bom {}) (on_board {})'.format(
            'no' if self.power else 'yes', 'no' if self.power else 'yes'))
        x0, y0, x1, y1 = self.bbox(1)
        rh = 'yes' if self.power else 'no'
        out.append(f'(property "Reference" {q(self.ref)} (at 0 {r2(y1 + 1.27)} 0) '
                   f'(effects (font (size 1.27 1.27)) (hide {rh})))')
        out.append(f'(property "Value" {q(value or self.name)} (at 0 {r2(y0 - 1.27)} 0) '
                   f'(effects (font (size 1.27 1.27))))')
        out.append(f'(property "Footprint" {q(self.footprint)} (at 0 0 0) '
                   f'(effects (font (size 1.27 1.27)) (hide yes)))')
        out.append(f'(property "Datasheet" {q(self.datasheet)} (at 0 0 0) '
                   f'(effects (font (size 1.27 1.27)) (hide yes)))')
        out.append(f'(property "Description" {q(self.description)} (at 0 0 0) '
                   f'(effects (font (size 1.27 1.27)) (hide yes)))')
        for unit in range(0, self.units + 1):
            g = [s for u, s, _, _ in self.gfx if u == unit]
            p = [pp.sexpr() for pp in self.pins if pp.unit == unit]
            if not g and not p:
                continue
            sub = f'(symbol {q(self.name + "_" + str(unit) + "_1")}'
            if unit in self.unit_names:
                sub += f' (unit_name {q(self.unit_names[unit])})'
            out.append(sub + ' ' + ' '.join(g + p) + ')')
        out.append('(embedded_fonts no))')
        return ' '.join(out)


# ---------------------------------------------------------------------------
# KiCad 5 library import
_cache = {}


def _load_libs():
    if _cache:
        return _cache
    for f in glob.glob(KSYM + '/*.lib'):
        txt = open(f, encoding='latin1').read()
        for m in re.finditer(r'^DEF (\S+) .*?^ENDDEF', txt, re.S | re.M):
            blk = m.group(0)
            nm = m.group(1).lstrip('~')
            al = re.findall(r'^ALIAS (.*)$', blk, re.M)
            for n in [nm] + (al[0].split() if al else []):
                _cache.setdefault(n, (f, blk))
    return _cache


def from_kicad5(name, newname=None, unhide_power=False):
    libs = _load_libs()
    f, blk = libs[name]
    lines = blk.split('\n')
    d = lines[0].split()
    # DEF name ref unused text_offset draw_pinnumber draw_pinname unit_count locked flag
    s = Symbol(newname or name, ref=d[2], units=int(d[7]), power=(d[9] == 'P'))
    s.pin_name_offset = int(d[4]) * MIL
    s.show_pin_numbers = d[5] == 'Y'
    s.show_pin_names = d[6] == 'Y'
    fp = re.findall(r'^F2 "([^"]*)"', blk, re.M)
    s.footprint = fp[0] if fp else ''
    ds = re.findall(r'^F3 "([^"]*)"', blk, re.M)
    s.datasheet = ds[0] if ds and ds[0] else '~'
    indraw = False
    for ln in lines:
        t = ln.split()
        if not t:
            continue
        if t[0] == 'DRAW':
            indraw = True
            continue
        if t[0] == 'ENDDRAW':
            indraw = False
            continue
        if not indraw:
            continue
        k = t[0]
        if k == 'X':
            pname, num = t[1], t[2]
            x, y, ln_, o = int(t[3]) * MIL, int(t[4]) * MIL, int(t[5]) * MIL, t[6]
            unit, conv, et = int(t[9]), int(t[10]), t[11]
            if conv == 2:
                continue
            shp = t[12] if len(t) > 12 else ''
            hidden = 'N' in shp
            shp = shp.replace('N', '')
            etype = ETYPE[et]
            if unhide_power and hidden and etype in ('power_in', 'passive'):
                pass  # stacked pins stay hidden (same coordinate as visible one)
            s.add_pin(kname(pname), num, x, y, ln_, ORIENT[o], etype,
                      SHAPE.get(shp, 'line'), hidden, unit)
        elif k == 'S':
            x1, y1, x2, y2 = [int(v) * MIL for v in t[1:5]]
            unit, conv = int(t[5]), int(t[6])
            if conv == 2:
                continue
            fill = {'F': 'outline', 'f': 'background'}.get(t[8] if len(t) > 8 else 'N', 'none')
            s.rect(x1, y1, x2, y2, unit, fill)
        elif k == 'P':
            n = int(t[1]); unit, conv = int(t[2]), int(t[3])
            if conv == 2:
                continue
            pts = [(int(t[5 + 2 * i]) * MIL, int(t[6 + 2 * i]) * MIL) for i in range(n)]
            fill = {'F': 'outline', 'f': 'background'}.get(t[5 + 2 * n] if len(t) > 5 + 2 * n else 'N', 'none')
            s.poly(pts, unit, fill)
        elif k == 'C':
            x, y, r = [int(v) * MIL for v in t[1:4]]
            unit, conv = int(t[4]), int(t[5])
            if conv == 2:
                continue
            fill = {'F': 'outline', 'f': 'background'}.get(t[7] if len(t) > 7 else 'N', 'none')
            s.circle(x, y, r, unit, fill)
        elif k == 'A':
            x, y, r = [int(v) * MIL for v in t[1:4]]
            a1, a2 = int(t[4]) / 10.0, int(t[5]) / 10.0
            unit, conv = int(t[6]), int(t[7])
            if conv == 2:
                continue
            xs, ys, xe, ye = [int(v) * MIL for v in t[10:14]]
            # mid point on the shorter arc between start/end around centre
            sa = math.atan2(ys - y, xs - x)
            ea = math.atan2(ye - y, xe - x)
            da = (ea - sa)
            while da > math.pi:
                da -= 2 * math.pi
            while da < -math.pi:
                da += 2 * math.pi
            ma = sa + da / 2
            s.arc((xs, ys), (x + r * math.cos(ma), y + r * math.sin(ma)), (xe, ye), unit)
        elif k == 'T':
            pass
    return s


# ---------------------------------------------------------------------------
# Custom IC symbol builder (pins left/right of a box)
def box_symbol(name, ref, units, footprint, datasheet='', description='', plen=3.81,
               min_w=20.32):
    """units: list of dicts {name:, left:[(num,name,etype)|None], right:[...]}
    None = spacer row. Pins on a 2.54 mm grid."""
    s = Symbol(name, ref=ref, units=len(units))
    s.footprint, s.datasheet, s.description = footprint, datasheet or '~', description
    for ui, u in enumerate(units, start=1):
        L, R = u.get('left', []), u.get('right', [])
        rows = max(len(L), len(R))
        lw = max([len(p[1]) for p in L if p] + [1])
        rw = max([len(p[1]) for p in R if p] + [1])
        w = max(min_w, (lw + rw) * 1.0 + 6)
        w = math.ceil(w / 5.08) * 5.08
        h = (rows + 1) * 2.54
        top = (rows - 1) * 2.54 / 2
        top = math.ceil(top / 2.54) * 2.54
        x0, x1 = -w / 2, w / 2
        s.rect(x0, top + 2.54, x1, top - rows * 2.54, ui, 'background')
        for i, p in enumerate(L):
            if p:
                s.add_pin(p[1], p[0], x0 - plen, top - i * 2.54, plen, 0, p[2], unit=ui)
        for i, p in enumerate(R):
            if p:
                s.add_pin(p[1], p[0], x1 + plen, top - i * 2.54, plen, 180, p[2], unit=ui)
        s.unit_names[ui] = u['name']
    return s


def power_symbol(net, kind='up'):
    """KiCad-style global power symbol. kind: up (+V) / down (GND)."""
    s = Symbol(net, ref='#PWR', power=True)
    s.show_pin_numbers = False
    s.show_pin_names = False
    s.pin_name_offset = 0
    s.description = f'Power symbol creates a global label with name "{net}"'
    if kind == 'down':
        s.poly([(0, 0), (0, -1.27), (1.27, -1.27), (0, -2.54), (-1.27, -1.27), (0, -1.27)], 0)
        s.add_pin(net, 1, 0, 0, 0, 270, 'power_in', hidden=True, unit=1)
    else:
        s.poly([(-0.762, 1.27), (0, 2.54)], 0)
        s.poly([(0, 0), (0, 2.54)], 0)
        s.poly([(0, 2.54), (0.762, 1.27)], 0)
        s.add_pin(net, 1, 0, 0, 0, 90, 'power_in', hidden=True, unit=1)
    return s


def pwr_flag():
    s = Symbol('PWR_FLAG', ref='#FLG', power=True)
    s.show_pin_numbers = False
    s.show_pin_names = False
    s.pin_name_offset = 0
    s.description = 'Special symbol for telling ERC where power comes from'
    s.poly([(0, 0), (0, 1.27), (-1.016, 1.905), (0, 2.54), (1.016, 1.905), (0, 1.27)], 0)
    s.add_pin('pwr', 1, 0, 0, 0, 90, 'power_out', unit=1)
    return s
