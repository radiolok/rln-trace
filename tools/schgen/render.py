"""Quick PNG preview of generated sheets (approximation of eeschema look)."""
import math
from PIL import Image, ImageDraw, ImageFont
from sch import rot_vec

S = 6  # px per mm
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'


def font(sz):
    return ImageFont.truetype(FONT, max(8, int(sz * S * 1.0)))


def render(sheet, path, global_nets):
    W, H = int(420 * S), int(297 * S)
    im = Image.new('RGB', (W, H), 'white')
    d = ImageDraw.Draw(im)
    P = lambda x, y: (x * S, y * S)
    d.rectangle([P(10, 10), P(410, 287)], outline=(150, 0, 0))
    for (x0, y0, x1, y1) in sheet.rects:
        d.rectangle([P(x0, y0), P(x1, y1)], outline=(150, 150, 150))
    for (x, y, txt, size, bold) in sheet.texts:
        d.multiline_text(P(x, y), txt, fill=(0, 0, 120), font=font(size))

    def tr(inst_x, inst_y, rot, x, y):
        vx, vy = rot_vec(x, -y, rot)
        return P(inst_x + vx, inst_y + vy)

    def draw_sym(sym, unit, ix, iy, rot, col=(132, 0, 0)):
        for u, _, _, g in sym.gfx:
            if u not in (0, unit):
                continue
            if g[0] == 'rect':
                _, x1, y1, x2, y2, fill = g
                pts = [tr(ix, iy, rot, a, b) for a, b in ((x1, y1), (x2, y1), (x2, y2), (x1, y2))]
                d.polygon(pts, outline=col, fill=(255, 255, 194) if fill == 'background' else None)
            elif g[0] == 'poly':
                pts = [tr(ix, iy, rot, a, b) for a, b in g[1]]
                if g[2] in ('outline', 'background') and len(pts) > 2:
                    d.polygon(pts, outline=col, fill=col if g[2] == 'outline' else (255, 255, 194))
                else:
                    d.line(pts, fill=col, width=2)
            elif g[0] == 'circle':
                _, x, y, r, fill = g
                c = tr(ix, iy, rot, x, y)
                d.ellipse([c[0] - r * S, c[1] - r * S, c[0] + r * S, c[1] + r * S], outline=col)
            elif g[0] == 'arc':
                pts = [tr(ix, iy, rot, a, b) for a, b in g[1:]]
                d.line(pts, fill=col, width=2)

    for i in sheet.insts:
        draw_sym(i.sym, i.unit, i.x, i.y, i.rot)
        for p in i.sym.pins_of_unit(i.unit):
            if p.hidden:
                continue
            a = math.radians(p.ang)
            ex, ey = p.x + p.length * math.cos(a), p.y + p.length * math.sin(a)
            p0 = tr(i.x, i.y, i.rot, p.x, p.y)
            p1 = tr(i.x, i.y, i.rot, ex, ey)
            d.line([p0, p1], fill=(132, 0, 0), width=2)
            if i.sym.show_pin_names and p.name and len(i.sym.pins) > 3:
                # name inside the body
                off = i.sym.pin_name_offset + 0.3
                nx, ny = ex + off * math.cos(a), ey + off * math.sin(a)
                q_ = tr(i.x, i.y, i.rot, nx, ny)
                f = font(1.0)
                tw = d.textlength(p.name, font=f)
                dx = q_[0] - p1[0]
                if dx > 1:
                    d.text((q_[0], q_[1] - 0.6 * S), p.name, fill=(0, 100, 100), font=f)
                elif dx < -1:
                    d.text((q_[0] - tw, q_[1] - 0.6 * S), p.name, fill=(0, 100, 100), font=f)
                else:
                    d.text((q_[0] - tw / 2, q_[1] + (2 if q_[1] > p1[1] else -2 - 1.0 * S)), p.name,
                           fill=(0, 100, 100), font=f)
            if i.sym.show_pin_numbers and len(i.sym.pins) > 3:
                m = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2)
                d.text((m[0] - 2, m[1] - 1.4 * S), p.num, fill=(132, 0, 0), font=font(0.9))
        bx0, by0, bx1, by1 = i.body_bbox()
        if bx1 - bx0 < 6 and by1 - by0 > bx1 - bx0:
            rp, vp = (bx1 + 1.27, (by0 + by1) / 2 - 1.0), (bx1 + 1.27, (by0 + by1) / 2 + 1.6)
            d.text(P(rp[0], rp[1] - 1.2), i.ref, fill=(0, 100, 100), font=font(1.2))
            d.text(P(vp[0], vp[1] - 1.2), i.value, fill=(0, 100, 100), font=font(1.2))
        elif by1 - by0 < 6:
            f = font(1.2)
            cx = (bx0 + bx1) / 2 * S
            d.text((cx - d.textlength(i.ref, font=f) / 2, (by0 - 2.2 - 1.2) * S), i.ref, fill=(0, 100, 100), font=f)
            d.text((cx - d.textlength(i.value, font=f) / 2, (by1 + 2.6 - 1.2) * S), i.value, fill=(0, 100, 100), font=f)
        else:
            d.text(P(bx0, by0 - 1.6 - 1.2), i.ref, fill=(0, 100, 100), font=font(1.2))
            d.text(P(bx0, by1 + 2.4 - 1.2), i.value, fill=(0, 100, 100), font=font(1.2))
    for (sym, ref, (x, y), rot) in sheet.pwr:
        draw_sym(sym, 1, x, y, rot, col=(0, 0, 160))
        txt = sym.name if sym.name != 'PWR_FLAG' else 'PWR_FLAG'
        down = getattr(sym, '_kind', None) == 'down'
        vx, vy = rot_vec(0, (-3.5 if not down else 4.0), rot)
        f = font(1.1)
        tw = d.textlength(txt, font=f)
        d.text(((x + vx) * S - tw / 2, (y + vy) * S - 0.6 * S), txt, fill=(0, 0, 160), font=f)
    for a, b in sheet.wires:
        d.line([P(*a), P(*b)], fill=(0, 140, 0), width=2)
    for (x, y) in sheet.ncs:
        c = P(x, y)
        r = 0.6 * S
        d.line([c[0] - r, c[1] - r, c[0] + r, c[1] + r], fill=(0, 0, 200), width=2)
        d.line([c[0] - r, c[1] + r, c[0] + r, c[1] - r], fill=(0, 0, 200), width=2)
    for net, (x, y), ang in sheet.labels:
        f = font(1.2)
        tw = d.textlength(net, font=f)
        g = net in global_nets
        col = (160, 80, 0) if g else (0, 0, 0)
        if ang == 0:
            box = [x * S, y * S - 0.9 * S, x * S + tw + 6, y * S + 0.9 * S]
            pos = (x * S + 3, y * S - 0.8 * S)
        elif ang == 180:
            box = [x * S - tw - 6, y * S - 0.9 * S, x * S, y * S + 0.9 * S]
            pos = (x * S - tw - 3, y * S - 0.8 * S)
        else:
            timg = Image.new('RGBA', (int(tw) + 6, int(1.8 * S)), (255, 255, 255, 0))
            ImageDraw.Draw(timg).text((3, 0), net, fill=col, font=f)
            timg = timg.rotate(90, expand=True)
            if ang == 90:
                im.paste(timg, (int(x * S - 0.9 * S), int(y * S - timg.size[1])), timg)
            else:
                im.paste(timg, (int(x * S - 0.9 * S), int(y * S)), timg)
            continue
        if g:
            d.rectangle(box, outline=col)
        d.text(pos, net, fill=col, font=f)
    im.save(path)
