"""Minimal KiCad 9 hierarchical schematic writer + connectivity checker."""
import uuid, math, json, os
from sym import q, r2

NS = uuid.UUID('6f1c1b2e-4c1a-4f7a-9a51-0d0b7e2a6c11')
POWER_NETS = set()


def uid(*parts):
    return str(uuid.uuid5(NS, '/'.join(str(p) for p in parts)))


def rot_vec(vx, vy, deg):
    t = math.radians(deg)
    c, s = round(math.cos(t), 9), round(math.sin(t), 9)
    return vx * c + vy * s, -vx * s + vy * c


def dir_angle(vx, vy):
    if abs(vx) > abs(vy):
        return 0 if vx > 0 else 180
    return 90 if vy < 0 else 270


def snap(v):
    return round(round(v / 0.635) * 0.635, 4)


class Inst:
    def __init__(self, sheet, sym, ref, value, x, y, rot, unit, fp, dnp, fields):
        self.sheet, self.sym, self.ref, self.value = sheet, sym, ref, value
        self.x, self.y, self.rot, self.unit = x, y, rot, unit
        self.fp = fp if fp is not None else sym.footprint
        self.dnp, self.fields = dnp, fields or {}
        self.uuid = uid(sheet.file, 'sym', ref, unit)

    def pin_pos(self, p):
        vx, vy = rot_vec(p.x, -p.y, self.rot)
        return snap(self.x + vx), snap(self.y + vy)

    def pin_out(self, p):
        a = math.radians(p.ang + 180)
        vx, vy = math.cos(a), -math.sin(a)
        vx, vy = rot_vec(vx, vy, self.rot)
        return round(vx), round(vy)

    def screen_bbox(self):
        x0, y0, x1, y1 = self.sym.bbox(self.unit)
        pts = [rot_vec(x, -y, self.rot) for x, y in ((x0, y0), (x1, y1), (x0, y1), (x1, y0))]
        xs = [self.x + a for a, _ in pts]
        ys = [self.y + b for _, b in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def body_bbox(self):
        """bbox of graphics only (no pins)"""
        pts = []
        for u, _, b, _ in self.sym.gfx:
            if u in (0, self.unit):
                pts += b
        if not pts:
            return self.screen_bbox()
        sp = [rot_vec(x, -y, self.rot) for x, y in pts]
        xs = [self.x + a for a, _ in sp]
        ys = [self.y + b for _, b in sp]
        return min(xs), min(ys), max(xs), max(ys)


class Sheet:
    def __init__(self, proj, file, title, page):
        self.proj, self.file, self.title, self.page = proj, file, title, page
        self.insts, self.wires, self.labels, self.ncs, self.texts, self.pwr = [], [], [], [], [], []
        self.uuid = uid(file, 'sheet')
        self.npwr = 0
        self.sheet_syms = []      # for root
        self.rects = []

    # ------------------------------------------------------------------
    def place(self, symname, ref, value, x, y, rot=0, unit=1, fp=None, dnp=False,
              nets=None, stub=2.54, fields=None, pwr_stub=None, check=True):
        sym = self.proj.symbol(symname)
        inst = Inst(self, sym, ref, value, x, y, rot, unit, fp, dnp, fields)
        self.insts.append(inst)
        nets = dict(nets or {})
        seen_pos = {}
        for p in sym.pins_of_unit(unit):
            pos = inst.pin_pos(p)
            if p.hidden:
                continue
            if p.num not in nets:
                if p.etype == 'no_connect':
                    continue
                if check:
                    raise KeyError(f'{self.file}: {ref} pin {p.num} ({p.name}) not assigned')
                continue
            net = nets.pop(p.num)
            if pos in seen_pos:
                continue
            seen_pos[pos] = net
            if net is None:
                continue
            if net == 'NC':
                self.ncs.append(pos)
                continue
            o = inst.pin_out(p)
            st = stub
            if net in POWER_NETS and pwr_stub is not None:
                st = pwr_stub
            end = (snap(pos[0] + o[0] * st), snap(pos[1] + o[1] * st))
            if st:
                self.wires.append((pos, end))
            self.connect(end, net, dir_angle(*o))
        if nets:
            raise KeyError(f'{self.file}: {ref} unknown pins {list(nets)}')
        return inst

    def connect(self, pos, net, ang):
        if net in POWER_NETS:
            self.power(net, pos, ang)
        else:
            self.labels.append((net, pos, ang))

    def power(self, net, pos, ang):
        sym = self.proj.power_sym(net)
        down = sym._kind == 'down'
        if down:
            rot = {270: 0, 0: 90, 90: 180, 180: 270}[ang]
        else:
            rot = {90: 0, 180: 90, 270: 180, 0: 270}[ang]
        self.npwr += 1
        self.pwr.append((sym, f'#PWR{self.page:02d}{self.npwr:03d}', pos, rot))

    def flag(self, net, x, y):
        """PWR_FLAG + net connection at (x,y): flag pin and a power symbol / label."""
        self.npwr += 1
        self.pwr.append((self.proj.symbol('PWR_FLAG'), f'#FLG{self.page:02d}{self.npwr:03d}', (x, y), 0))
        self.wires.append(((x, y), (x, y + 2.54)))
        if net in POWER_NETS:
            self.power(net, (x, y + 2.54), 270 if self.proj.power_sym(net)._kind == 'down' else 90)
            if self.proj.power_sym(net)._kind != 'down':
                # up-type symbol pointing up would overlap flag: route to the side
                self.pwr.pop()
                self.npwr -= 1
                self.wires.pop()
                self.wires.append(((x, y), (x + 2.54, y)))
                self.power(net, (x + 2.54, y), 90)
        else:
            self.labels.append((net, (x, y + 2.54), 270))

    def nc(self, x, y):
        self.ncs.append((x, y))

    def note(self, x, y, txt, size=1.27, bold=False):
        self.texts.append((x, y, txt, size, bold))

    def frame(self, x0, y0, x1, y1, title=None):
        self.rects.append((x0, y0, x1, y1))
        if title:
            self.note(x0 + 1.27, y0 + 2.54, title, 2.0, True)

    def wire(self, a, b):
        self.wires.append((a, b))

    # ------------------------------------------------------------------
    def sexpr(self, global_nets, root_uuid, is_root=False):
        o = []
        o.append(f'(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0") '
                 f'(uuid {q(self.uuid)}) (paper "A3")')
        o.append(f'(title_block (title {q(self.title)}) (date "2026-10-03") (rev "0.1") '
                 f'(company "Open Debug+Trace probe") (comment 1 "GW2AR-18 QN88 + CH569W, MIPI20, USB3") '
                 f'(comment 2 "Draft for review - generated, verify before layout"))')
        used = {}
        for i in self.insts:
            used[i.sym.name] = i.sym
        for s, _, _, _ in self.pwr:
            used[s.name] = s
        o.append('(lib_symbols ' + ' '.join(s.sexpr('probe') for s in used.values()) + ')')
        path = f'/{root_uuid}' if is_root else f'/{root_uuid}/{self.uuid}'
        for (x0, y0, x1, y1) in self.rects:
            o.append(f'(rectangle (start {r2(x0)} {r2(y0)}) (end {r2(x1)} {r2(y1)}) '
                     f'(stroke (width 0.254) (type dash) (color 120 120 120 1)) (fill (type none)) '
                     f'(uuid {q(uid(self.file, "rect", x0, y0))}))')
        for (x, y, txt, size, bold) in self.texts:
            b = ' (bold yes)' if bold else ''
            o.append(f'(text {q(txt)} (exclude_from_sim no) (at {r2(x)} {r2(y)} 0) '
                     f'(effects (font (size {size} {size}){b}) (justify left top)) '
                     f'(uuid {q(uid(self.file, "txt", x, y, txt))}))')
        for k, (a, b) in enumerate(self.wires):
            o.append(f'(wire (pts (xy {r2(a[0])} {r2(a[1])}) (xy {r2(b[0])} {r2(b[1])})) '
                     f'(stroke (width 0) (type default)) (uuid {q(uid(self.file, "w", k, a, b))}))')
        for k, (x, y) in enumerate(self.ncs):
            o.append(f'(no_connect (at {r2(x)} {r2(y)}) (uuid {q(uid(self.file, "nc", k, x, y))}))')
        for k, (net, (x, y), ang) in enumerate(self.labels):
            just = 'left' if ang in (0, 90) else 'right'
            if net in global_nets:
                o.append(f'(global_label {q(net)} (shape bidirectional) (at {r2(x)} {r2(y)} {ang}) '
                         f'(fields_autoplaced yes) (effects (font (size 1.27 1.27)) (justify {just})) '
                         f'(uuid {q(uid(self.file, "gl", k, net))}) '
                         f'(property "Intersheetrefs" "${{INTERSHEET_REFS}}" (at {r2(x)} {r2(y)} 0) '
                         f'(effects (font (size 1.27 1.27)) (hide yes))))')
            else:
                o.append(f'(label {q(net)} (at {r2(x)} {r2(y)} {ang}) (fields_autoplaced yes) '
                         f'(effects (font (size 1.27 1.27)) (justify {just} bottom)) '
                         f'(uuid {q(uid(self.file, "l", k, net))}))')
        for (sym, ref, (x, y), rot) in self.pwr:
            o.append(self._inst_sexpr(sym, ref, sym.name, x, y, rot, 1, '', False, {}, path,
                                      uid(self.file, 'pwr', ref), power=True))
        for i in self.insts:
            o.append(self._inst_sexpr(i.sym, i.ref, i.value, i.x, i.y, i.rot, i.unit, i.fp, i.dnp,
                                      i.fields, path, i.uuid, inst=i))
        for ss in self.sheet_syms:
            o.append(ss)
        if is_root:
            o.append('(sheet_instances (path "/" (page "1")))')
        o.append('(embedded_fonts no))')
        return '\n'.join(o) + '\n'

    def _inst_sexpr(self, sym, ref, value, x, y, rot, unit, fp, dnp, fields, path, u,
                    power=False, inst=None):
        if inst is not None:
            bx0, by0, bx1, by1 = inst.body_bbox()
            if bx1 - bx0 < 6 and by1 - by0 > bx1 - bx0:      # small vertical part
                rp, vp, rj = (bx1 + 1.27, (by0 + by1) / 2 - 1.0), (bx1 + 1.27, (by0 + by1) / 2 + 1.6), 'left'
            elif by1 - by0 < 6:                              # small horizontal part
                rp, vp, rj = ((bx0 + bx1) / 2, by0 - 2.2), ((bx0 + bx1) / 2, by1 + 2.6), 'center'
            else:
                rp, vp, rj = (bx0, by0 - 1.6), (bx0, by1 + 2.4), 'left'
        else:
            rp, vp, rj = (x, y - 3.5 if not sym._kind == 'down' else y + 5.0), \
                         (x, y - 4.5 if not sym._kind == 'down' else y + 4.5), 'center'
            if sym.name == 'PWR_FLAG':
                vp = (x, y - 4.0)
        hide_ref = ' (hide yes)' if power else ''
        just = '' if rj == 'center' else f' (justify {rj})'
        props = [
            f'(property "Reference" {q(ref)} (at {r2(rp[0])} {r2(rp[1])} 0) (effects (font (size 1.27 1.27)){hide_ref}{just}))',
            f'(property "Value" {q(value)} (at {r2(vp[0])} {r2(vp[1])} 0) (effects (font (size 1.27 1.27)){just}))',
            f'(property "Footprint" {q(fp)} (at {r2(x)} {r2(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'(property "Datasheet" {q(sym.datasheet)} (at {r2(x)} {r2(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
            f'(property "Description" {q(sym.description)} (at {r2(x)} {r2(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))',
        ]
        for k, v in fields.items():
            props.append(f'(property {q(k)} {q(v)} (at {r2(x)} {r2(y)} 0) (effects (font (size 1.27 1.27)) (hide yes)))')
        pins = ' '.join(f'(pin {q(p.num)} (uuid {q(uid(u, "pin", p.num))}))'
                        for p in sym.pins_of_unit(unit))
        bom = 'no' if power else 'yes'
        return (f'(symbol (lib_id {q("probe:" + sym.name)}) (at {r2(x)} {r2(y)} {rot}) (unit {unit}) '
                f'(exclude_from_sim no) (in_bom {bom}) (on_board {bom}) (dnp {"yes" if dnp else "no"}) '
                f'(uuid {q(u)}) ' + ' '.join(props) + ' ' + pins +
                f' (instances (project "probe" (path {q(path)} (reference {q(ref)}) (unit {unit})))))')


class Project:
    def __init__(self, name):
        self.name = name
        self.syms = {}
        self.sheets = []
        self.root = Sheet(self, name + '.kicad_sch', 'Open Debug+Trace probe', 1)
        self.root.uuid = uid('root')

    def add_symbol(self, s):
        self.syms[s.name] = s
        if not hasattr(s, '_kind'):
            s._kind = None

    def symbol(self, name):
        return self.syms[name]

    def power_sym(self, net):
        return self.syms[net]

    def add_power(self, net, kind):
        from sym import power_symbol
        s = power_symbol(net, kind)
        s._kind = kind
        self.add_symbol(s)
        POWER_NETS.add(net)

    def sheet(self, file, title):
        s = Sheet(self, file, title, len(self.sheets) + 2)
        self.sheets.append(s)
        return s

    # ------------------------------------------------------------------
    def net_sheets(self):
        d = {}
        for sh in self.sheets + [self.root]:
            for net, _, _ in sh.labels:
                d.setdefault(net, set()).add(sh.file)
        return d

    def write(self, outdir):
        os.makedirs(outdir, exist_ok=True)
        ns = self.net_sheets()
        global_nets = {n for n, s in ns.items() if len(s) > 1}
        self.global_nets = global_nets
        # root sheet symbols
        x, y = 30.48, 50.8
        for i, sh in enumerate(self.sheets):
            sx = x + (i % 3) * 120.65
            sy = y + (i // 3) * 63.5
            w, h = 101.6, 38.1
            self.root.sheet_syms.append(
                f'(sheet (at {sx} {sy}) (size {w} {h}) (exclude_from_sim no) (in_bom yes) (on_board yes) '
                f'(dnp no) (fields_autoplaced yes) (stroke (width 0.1524) (type solid)) '
                f'(fill (color 0 0 0 0.0000)) (uuid {q(sh.uuid)}) '
                f'(property "Sheetname" {q(sh.title)} (at {sx} {sy - 0.7} 0) (effects (font (size 1.5 1.5)) (justify left bottom))) '
                f'(property "Sheetfile" {q(sh.file)} (at {sx} {r2(sy + h + 0.6)} 0) (effects (font (size 1.27 1.27)) (justify left top))) '
                f'(instances (project "probe" (path {q("/" + self.root.uuid)} (page {q(str(sh.page))})))))')
        for sh in self.sheets:
            open(os.path.join(outdir, sh.file), 'w').write(sh.sexpr(global_nets, self.root.uuid))
        open(os.path.join(outdir, self.root.file), 'w').write(
            self.root.sexpr(global_nets, self.root.uuid, is_root=True))
        # symbol library
        lib = ['(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor") (generator_version "9.0")']
        for s in self.syms.values():
            lib.append(s.sexpr())
        lib.append(')')
        open(os.path.join(outdir, 'probe.kicad_sym'), 'w').write('\n'.join(lib) + '\n')
        open(os.path.join(outdir, 'sym-lib-table'), 'w').write(
            '(sym_lib_table\n  (version 7)\n  (lib (name "probe")(type "KiCad")(uri "${KIPRJMOD}/probe.kicad_sym")(options "")(descr "Probe project symbols"))\n)\n')
        open(os.path.join(outdir, 'fp-lib-table'), 'w').write(
            '(fp_lib_table\n  (version 7)\n  (lib (name "probe")(type "KiCad")(uri "${KIPRJMOD}/probe.pretty")(options "")(descr "Probe project footprints"))\n)\n')
        pro = {"meta": {"filename": self.name + ".kicad_pro", "version": 3},
               "sheets": [[self.root.uuid, "Root"]] + [[s.uuid, s.title] for s in self.sheets],
               "boards": [], "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
               "schematic": {"legacy_lib_dir": "", "legacy_lib_list": []},
               "text_variables": {}}
        open(os.path.join(outdir, self.name + '.kicad_pro'), 'w').write(json.dumps(pro, indent=2) + '\n')

    # ------------------------------------------------------------------
    def check(self):
        """Approximate ERC: connectivity, single-pin nets, undriven power, unconnected pins."""
        parent = {}

        def find(a):
            while parent.setdefault(a, a) != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        pins = []   # (node, sheet, ref, pin)
        problems = []
        for sh in self.sheets:
            F = sh.file
            for a, b in sh.wires:
                union((F, a), (F, b))
            for net, pos, _ in sh.labels:
                key = ('G', net) if net in self.global_nets else ('L', F, net)
                union((F, pos), key)
            for sym, ref, pos, rot in sh.pwr:
                if sym.name == 'PWR_FLAG':
                    pins.append(((F, pos), F, ref, sym.pins[0]))
                else:
                    union((F, pos), ('G', sym.name))
            ncset = set(sh.ncs)
            for i in sh.insts:
                for p in i.sym.pins_of_unit(i.unit):
                    pos = i.pin_pos(p)
                    if pos in ncset:
                        if p.etype != 'no_connect':
                            pins.append((('NC', F, i.ref, p.num), F, i.ref, p))
                        continue
                    pins.append(((F, pos), F, i.ref, p))
            # dangling wire ends / labels: check below
        nets = {}
        for node, F, ref, p in pins:
            if node[0] == 'NC':
                continue
            nets.setdefault(find(node), []).append((F, ref, p))
        # names
        names = {}
        for k in list(parent):
            if k[0] in ('G', 'L'):
                names.setdefault(find(k), set()).add(k[-1])
        for root, lst in nets.items():
            nm = names.get(root, {'?'})
            if len(nm) > 1:
                problems.append(f'SHORT: names {sorted(nm)} joined')
            real = [x for x in lst if x[2].etype != 'no_connect']
            types = [x[2].etype for x in real if x[1] and not x[1].startswith('#')]
            all_types = [x[2].etype for x in real]
            if len([x for x in real if not x[1].startswith('#')]) < 2:
                for F, ref, p in real:
                    if not ref.startswith('#') and not p.hidden:
                        problems.append(f'SINGLE: {F} {ref}.{p.num} ({p.name}) net {sorted(nm)}')
            if 'power_in' in types and not any(t == 'power_out' for t in all_types):
                problems.append(f'UNDRIVEN POWER: net {sorted(nm)}')
            drivers = [x for x in real if x[2].etype in ('output', 'power_out')]
            if len([d for d in drivers if d[2].etype == 'output']) > 1:
                problems.append(f'MULTI-OUTPUT: net {sorted(nm)} ' +
                                ', '.join(f'{r}.{p.num}' for _, r, p in drivers))
            if len([d for d in drivers if d[2].etype == 'power_out']) > 1:
                problems.append(f'MULTI-PWR-OUT: net {sorted(nm)} ' +
                                ', '.join(f'{r}.{p.num}' for _, r, p in drivers))
        # labels that connect to nothing on their sheet
        for sh in self.sheets:
            F = sh.file
            pinpos = {(F, i.pin_pos(p)) for i in sh.insts for p in i.sym.pins_of_unit(i.unit)}
            pinpos |= {(F, pos) for _, _, pos, _ in sh.pwr}
            for a, b in sh.wires:
                ends = [(F, a), (F, b)]
                for e in ends:
                    deg = sum(1 for w in sh.wires for z in w if (F, z) == e)
                    lab = any((F, pos) == e for _, pos, _ in sh.labels)
                    pw = any((F, pos) == e for _, _, pos, _ in sh.pwr)
                    if deg == 1 and e not in pinpos and not lab and not pw:
                        problems.append(f'DANGLING wire end {F} {e[1]}')
        # global labels used once
        ns = self.net_sheets()
        cnt = {}
        for sh in self.sheets:
            for net, _, _ in sh.labels:
                cnt[net] = cnt.get(net, 0) + 1
        for n, c in cnt.items():
            if c == 1:
                problems.append(f'LABEL USED ONCE: {n} in {sorted(ns[n])}')
        return problems, nets, names
