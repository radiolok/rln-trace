"""Минимальный генератор плоской схемы KiCad 10 из описания на Python.

Символы берутся из системных библиотек KiCad (/usr/share/kicad/symbols) и встраиваются
в лист как есть — номера и расположение выводов те же, что в библиотеке. Связи — метками:
у каждого вывода короткий провод и метка цепи (или символ земли). Проверка — kicad-cli sch erc.
"""
import math, os, re, uuid

SYMDIR = os.environ.get('KICAD_SYMBOL_DIR', '/usr/share/kicad/symbols')
NS = uuid.UUID('9b0c6a52-1f0e-4d6b-a1d5-2c5e3f7a8b90')


# ---------------------------------------------------------------- S-выражения
class Q(str):
    """Строка в кавычках (атомы без кавычек — обычный str)."""


def parse(text):
    tok = re.compile(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+')
    stack, cur = [], []
    for m in tok.finditer(text):
        t = m.group()
        if t == '(':
            stack.append(cur)
            cur = []
        elif t == ')':
            done, cur = cur, stack.pop()
            cur.append(done)
        elif t[0] == '"':
            cur.append(Q(re.sub(r'\\(.)', r'\1', t[1:-1])))
        else:
            cur.append(t)
    return cur[0]


def dump(x):
    if isinstance(x, list):
        return '(' + ' '.join(dump(e) for e in x) + ')'
    if isinstance(x, Q):
        return '"' + x.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    return str(x)


def q(s):
    return dump(Q(s))


def find(node, key):
    return [e for e in node if isinstance(e, list) and e and e[0] == key]


def first(node, key):
    r = find(node, key)
    return r[0] if r else None


def uid(*parts):
    return str(uuid.uuid5(NS, '/'.join(str(p) for p in parts)))


# ---------------------------------------------------------------- символы
_libs = {}


def _lib(name):
    if name not in _libs:
        _libs[name] = parse(open(os.path.join(SYMDIR, name + '.kicad_sym'), encoding='utf-8').read())
    return _libs[name]


class Pin:
    def __init__(self, num, name, etype, x, y, ang, unit):
        self.num, self.name, self.etype = num, name, etype
        self.x, self.y, self.ang, self.unit = x, y, ang, unit


class Symbol:
    def __init__(self, lib, name):
        self.lib, self.name = lib, name
        self.lib_id = f'{lib}:{name}'
        root = _lib(lib)
        syms = {e[1]: e for e in find(root, 'symbol')}
        node = syms[name]
        ext = first(node, 'extends')
        if ext:                                   # наследник: графика и выводы от базового
            base = syms[ext[1]]
            body = [e for e in base if isinstance(e, list) and e[0] == 'symbol']
            props = {p[1]: p for p in find(base, 'property')}
            props.update({p[1]: p for p in find(node, 'property')})
            head = [e for e in base[2:] if isinstance(e, list) and e[0] not in ('symbol', 'property')]
            src_name = ext[1]
        else:
            body = find(node, 'symbol')
            props = {p[1]: p for p in find(node, 'property')}
            head = [e for e in node[2:] if isinstance(e, list) and e[0] not in ('symbol', 'property', 'extends')]
            src_name = name
        units = []
        for sub in body:
            sub = list(sub)
            sub[1] = Q(name + sub[1][len(src_name):])
            units.append(sub)
        self.props = props
        self.node = ['symbol', Q(self.lib_id)] + head + list(props.values()) + units
        self.power = first(node, 'power') is not None or first(head, 'power') is not None
        self.pins = []
        for sub in units:
            u = int(sub[1].rsplit('_', 2)[1])
            for p in find(sub, 'pin'):
                at = first(p, 'at')
                self.pins.append(Pin(str(first(p, 'number')[1]), str(first(p, 'name')[1]), p[1],
                                     float(at[1]), float(at[2]), float(at[3]), u))

    def prop(self, key):
        p = self.props.get(key)
        return str(p[2]) if p else ''

    def pins_of(self, unit):
        return [p for p in self.pins if p.unit in (0, unit)]


_symcache = {}


def symbol(lib_id):
    if lib_id not in _symcache:
        lib, name = lib_id.split(':')
        _symcache[lib_id] = Symbol(lib, name)
    return _symcache[lib_id]


# ---------------------------------------------------------------- лист
def snap(v):
    return round(round(v / 1.27) * 1.27, 4)


def rot(vx, vy, deg):
    t = math.radians(deg)
    c, s = round(math.cos(t), 9), round(math.sin(t), 9)
    return vx * c - vy * s, vx * s + vy * c


class Part:
    def __init__(self, sym, ref, value, x, y, angle, unit, fp, dnp, fields):
        self.sym, self.ref, self.value = sym, ref, value
        self.x, self.y, self.angle, self.unit = x, y, angle, unit
        self.fp, self.dnp, self.fields = fp, dnp, fields
        self.uuid = uid('sym', ref, unit)

    def pin_pos(self, p):
        vx, vy = rot(p.x, p.y, self.angle)       # координаты символа: y вверх
        return snap(self.x + vx), snap(self.y - vy)

    def pin_out(self, p):
        """Единичный вектор наружу от корпуса, в координатах листа (y вниз)."""
        vx, vy = rot(-math.cos(math.radians(p.ang)), -math.sin(math.radians(p.ang)), self.angle)
        return round(vx), -round(vy)


class Sheet:
    GROUND = {'GND'}

    def __init__(self, name, title, rev, date, company, comments=(), paper='A3'):
        self.name, self.title, self.rev, self.date = name, title, rev, date
        self.company, self.comments, self.paper = company, comments, paper
        self.parts, self.wires, self.labels, self.ncs, self.texts, self.pwr = [], [], [], [], [], []
        self.uuid = uid('root', name)
        self.npwr = 0
        self.net_pins = {}                        # net -> [(ref, pin)]

    def place(self, lib_id, ref, value, x, y, angle=0, unit=1, nets=None, fp=None, dnp=False,
              stub=2.54, fields=None):
        sym = symbol(lib_id)
        part = Part(sym, ref, value, x, y, angle, unit,
                    fp if fp is not None else sym.prop('Footprint'), dnp, fields or {})
        self.parts.append(part)
        nets = dict(nets or {})
        seen = set()
        for p in sym.pins_of(unit):
            if p.num not in nets:
                if p.etype == 'no_connect':
                    continue
                raise KeyError(f'{ref}: вывод {p.num} ({p.name}) не назначен')
            net = nets.pop(p.num)
            pos = part.pin_pos(p)
            if pos in seen:                       # выводы друг на друге (земля TPD4E02B04)
                continue
            seen.add(pos)
            if net == 'NC':
                self.ncs.append(pos)
                continue
            self.net_pins.setdefault(net, []).append((ref, p.num))
            o = part.pin_out(p)
            end = (snap(pos[0] + o[0] * stub), snap(pos[1] + o[1] * stub))
            self.wires.append((pos, end))
            self.connect(end, net, o)
        if nets:
            raise KeyError(f'{ref}: нет выводов {list(nets)}')
        return part

    def connect(self, pos, net, o):
        if net in self.GROUND:
            self.npwr += 1
            r = {(0, 1): 0, (0, -1): 180, (1, 0): 90, (-1, 0): 270}[o]
            self.pwr.append((symbol('power:GND'), f'#PWR{self.npwr:03d}', pos, r))
        else:
            ang = {(1, 0): 0, (0, -1): 90, (-1, 0): 180, (0, 1): 270}[o]
            self.labels.append((net, pos, ang))

    def flag(self, net, x, y):
        """PWR_FLAG на цепи: флаг сверху, провод вниз к метке/земле."""
        self.npwr += 1
        self.pwr.append((symbol('power:PWR_FLAG'), f'#FLG{self.npwr:03d}', (x, y), 0))
        self.wires.append(((x, y), (x, y + 2.54)))
        self.connect((x, y + 2.54), net, (0, 1))

    def note(self, x, y, txt, size=1.27, bold=False):
        self.texts.append((x, y, txt, size, bold))

    # ------------------------------------------------------------------
    def sexpr(self):
        o = [f'(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0") '
             f'(uuid {q(self.uuid)}) (paper {q(self.paper)})']
        cm = ' '.join(f'(comment {i + 1} {q(c)})' for i, c in enumerate(self.comments))
        o.append(f'(title_block (title {q(self.title)}) (date {q(self.date)}) (rev {q(self.rev)}) '
                 f'(company {q(self.company)}) {cm})')
        used = {}
        for p in self.parts:
            used[p.sym.lib_id] = p.sym
        for s, _, _, _ in self.pwr:
            used[s.lib_id] = s
        o.append('(lib_symbols ' + ' '.join(dump(s.node) for s in used.values()) + ')')
        for (x, y, txt, size, bold) in self.texts:
            b = ' (bold yes)' if bold else ''
            o.append(f'(text {q(txt)} (exclude_from_sim no) (at {x} {y} 0) '
                     f'(effects (font (size {size} {size}){b}) (justify left top)) '
                     f'(uuid {q(uid("txt", x, y, txt))}))')
        for k, (a, b) in enumerate(self.wires):
            o.append(f'(wire (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]})) '
                     f'(stroke (width 0) (type default)) (uuid {q(uid("w", k, a, b))}))')
        for k, (x, y) in enumerate(self.ncs):
            o.append(f'(no_connect (at {x} {y}) (uuid {q(uid("nc", k, x, y))}))')
        for k, (net, (x, y), ang) in enumerate(self.labels):
            just = 'left' if ang in (0, 90) else 'right'
            o.append(f'(label {q(net)} (at {x} {y} {ang}) (fields_autoplaced yes) '
                     f'(effects (font (size 1.27 1.27)) (justify {just} bottom)) '
                     f'(uuid {q(uid("l", k, net, x, y))}))')
        for (sym, ref, (x, y), r) in self.pwr:
            o.append(self._inst(sym, ref, sym.prop('Value'), x, y, r, 1, '', False, {},
                                uid('pwr', ref), power=True))
        for p in self.parts:
            o.append(self._inst(p.sym, p.ref, p.value, p.x, p.y, p.angle, p.unit, p.fp, p.dnp,
                                p.fields, p.uuid, part=p))
        o.append('(sheet_instances (path "/" (page "1")))')
        o.append('(embedded_fonts no))')
        return '\n'.join(o) + '\n'

    def _inst(self, sym, ref, value, x, y, r, unit, fp, dnp, fields, u, power=False, part=None):
        if part is not None:
            xs = [part.pin_pos(p)[0] for p in sym.pins_of(unit)]
            ys = [part.pin_pos(p)[1] for p in sym.pins_of(unit)]
            if max(xs) - min(xs) < 1 and len(xs) <= 2:          # вертикальный двухвыводной
                rp, vp, j = (x + 2.54, y - 1.27), (x + 2.54, y + 1.27), 'left'
            elif max(ys) - min(ys) < 1 and len(xs) <= 2:        # горизонтальный двухвыводной
                rp, vp, j = (x, y - 2.54), (x, y + 2.54), 'center'
            else:
                rp, vp, j = (min(xs) + 2.54, min(ys) - 3.81), (min(xs) + 2.54, max(ys) + 3.81), 'left'
        else:
            rp, vp, j = (x, y - 3.81), (x, y + 3.81 if sym.name == 'GND' else y - 3.81), 'center'
        hide = ' (hide yes)' if power else ''
        just = '' if j == 'center' else f' (justify {j})'
        vhide = ' (hide yes)' if sym.name == 'PWR_FLAG' else ''
        props = [
            f'(property "Reference" {q(ref)} (at {rp[0]} {rp[1]} 0) (effects (font (size 1.27 1.27)){hide}{just}))',
            f'(property "Value" {q(value)} (at {vp[0]} {vp[1]} 0) (effects (font (size 1.27 1.27)){vhide}{just}))',
            f'(property "Footprint" {q(fp)} (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'(property "Datasheet" {q(sym.prop("Datasheet"))} (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'(property "Description" {q(sym.prop("Description"))} (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        ]
        for k, v in fields.items():
            props.append(f'(property {q(k)} {q(v)} (at {x} {y} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
        pins = ' '.join(f'(pin {q(p.num)} (uuid {q(uid(u, "pin", p.num))}))' for p in sym.pins_of(unit))
        bom = 'no' if power else 'yes'
        return (f'(symbol (lib_id {q(sym.lib_id)}) (at {x} {y} {r}) (unit {unit}) '
                f'(exclude_from_sim no) (in_bom {bom}) (on_board {bom}) (dnp {"yes" if dnp else "no"}) '
                f'(uuid {q(u)}) ' + ' '.join(props) + ' ' + pins +
                f' (instances (project {q(self.name)} (path {q("/" + self.uuid)} (reference {q(ref)}) (unit {unit})))))')

    def write(self, outdir):
        os.makedirs(outdir, exist_ok=True)
        open(os.path.join(outdir, self.name + '.kicad_sch'), 'w', encoding='utf-8').write(self.sexpr())
        pro = os.path.join(outdir, self.name + '.kicad_pro')
        if not os.path.exists(pro):                 # проект не трогаем: в нём настройки разводки
            import json
            open(pro, 'w').write(json.dumps({
                "meta": {"filename": self.name + ".kicad_pro", "version": 3},
                "sheets": [[self.uuid, "Root"]], "boards": [],
                "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
                "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
                "text_variables": {}}, indent=2) + '\n')

    def single_pin_nets(self):
        return {n: v for n, v in self.net_pins.items() if len(v) < 2 and n not in self.GROUND}
