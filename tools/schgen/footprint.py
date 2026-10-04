"""Project footprint: GW2AR-18 QN88 (10x10 mm, 0.4 mm pitch, EP 6.74 mm, per Gowin UG229).
Land pattern is a nominal IPC-style estimate - verify against the UG229 package drawing."""
import os, uuid

NS = uuid.UUID('1b2c3d4e-0000-4000-8000-0123456789ab')


def u(*a):
    return str(uuid.uuid5(NS, '/'.join(map(str, a))))


def qfn88(path):
    n_side, pitch, body, ep = 22, 0.4, 10.0, 6.74
    pw, pl, pc = 0.22, 0.85, 4.875      # pad width, length, centre distance
    span = (n_side - 1) * pitch / 2
    L = ['(footprint "QFN-88-1EP_10x10mm_P0.4mm_EP6.74x6.74mm" (version 20241229) (generator "pcbnew") (generator_version "9.0")',
         '(layer "F.Cu")',
         '(descr "Gowin QN88 (GW2AR-18), 10x10 mm, 0.4 mm pitch, EP 6.74 mm. Nominal land pattern - verify vs UG229 drawing")',
         '(tags "QFN 0.4 Gowin QN88")',
         '(property "Reference" "REF**" (at 0 -6.8 0) (layer "F.SilkS") (uuid "%s") (effects (font (size 1 1) (thickness 0.15))))' % u('ref'),
         '(property "Value" "QFN-88-1EP_10x10mm_P0.4mm_EP6.74x6.74mm" (at 0 6.8 0) (layer "F.Fab") (uuid "%s") (effects (font (size 1 1) (thickness 0.15))))' % u('val'),
         '(attr smd)']
    h = body / 2
    for k, (x1, y1, x2, y2) in enumerate([(-h, -h, -3.9, -h), (-h, -h, -h, -3.9), (h, -h, 3.9, -h), (h, -h, h, -3.9),
                                         (-h, h, -3.9, h), (-h, h, -h, 3.9), (h, h, 3.9, h), (h, h, h, 3.9)]):
        L.append(f'(fp_line (start {x1} {y1}) (end {x2} {y2}) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid "{u("silk", k)}"))')
    L.append(f'(fp_circle (center -5.6 -4.6) (end -5.45 -4.6) (stroke (width 0.3) (type solid)) (fill solid) (layer "F.SilkS") (uuid "{u("dot")}"))')
    L.append(f'(fp_rect (start -{h} -{h}) (end {h} {h}) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab") (uuid "{u("fab")}"))')
    c = 5.75
    L.append(f'(fp_rect (start -{c} -{c}) (end {c} {c}) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd") (uuid "{u("crt")}"))')
    num = 1
    for side in range(4):
        for i in range(n_side):
            t = -span + i * pitch
            if side == 0:   x, y, w_, h_ = -pc, t, pl, pw          # left, top->bottom
            elif side == 1: x, y, w_, h_ = t, pc, pw, pl           # bottom, left->right
            elif side == 2: x, y, w_, h_ = pc, -t, pl, pw          # right, bottom->top
            else:           x, y, w_, h_ = -t, -pc, pw, pl         # top, right->left
            L.append(f'(pad "{num}" smd roundrect (at {x:.4f} {y:.4f}) (size {w_} {h_}) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25) (uuid "{u("pad", num)}"))')
            num += 1
    L.append(f'(pad "89" smd rect (at 0 0) (size {ep} {ep}) (layers "F.Cu" "F.Mask") (zone_connect 2) (uuid "{u("ep")}"))')
    s, g = 1.8, 2.2
    for ix in (-1, 0, 1):
        for iy in (-1, 0, 1):
            L.append(f'(pad "" smd roundrect (at {ix * g} {iy * g}) (size {s} {s}) (layers "F.Paste") (roundrect_rratio 0.15) (uuid "{u("paste", ix, iy)}"))')
    for ix in range(-2, 3):
        for iy in range(-2, 3):
            L.append(f'(pad "89" thru_hole circle (at {ix * 1.3} {iy * 1.3}) (size 0.6 0.6) (drill 0.3) (layers "*.Cu") (zone_connect 2) (uuid "{u("via", ix, iy)}"))')
    L.append('(embedded_fonts no))')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'w').write('\n'.join(L) + '\n')


if __name__ == '__main__':
    qfn88(os.path.join(os.path.dirname(os.path.abspath(__file__)), '../../hw/probe-b/kicad/probe.pretty/QFN-88-1EP_10x10mm_P0.4mm_EP6.74x6.74mm.kicad_mod'))
