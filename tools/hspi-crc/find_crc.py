#!/usr/bin/env python3
"""Find the CRC parameters of CH569 HSPI packets captured on the bus.

The datasheet gives only the polynomials (CRC16 0x8005 for 8/16-bit buses,
CRC32 0x04C11DB7 for 32 bits). This tool takes whole packets as they went over
the bus -- header, payload, CRC, e.g. from gw/cores/hspi_rx.sv in raw mode or a
logic analyser -- and searches:

  - CRC width (16 or 32) from the packet tail,
  - which bytes are covered: header + payload (as the datasheet says) or
    payload only,
  - input and output reflection,
  - byte order of the CRC on the bus,
  - init: every value for CRC16, 0 and all ones for CRC32,
  - output XOR: solved from one packet, checked on the rest.

Give packets of at least two different lengths, otherwise init and output XOR
cannot be told apart.

Input: one packet per line, hex bytes (spaces and 0x are ignored), '#' starts a
comment. Usage:

    find_crc.py packets.txt
    find_crc.py --selftest
"""
import argparse
import random
import sys

POLY = {16: 0x8005, 32: 0x04C11DB7}


def reflect(v, n):
    r = 0
    for i in range(n):
        if v >> i & 1:
            r |= 1 << (n - 1 - i)
    return r


def crc_raw(data, width, init, refin):
    """CRC register after the data, before output reflection and XOR."""
    poly, top, mask = POLY[width], 1 << (width - 1), (1 << width) - 1
    c = init
    for byte in data:
        if refin:
            byte = reflect(byte, 8)
        c ^= byte << (width - 8)
        for _ in range(8):
            c = ((c << 1) ^ poly) & mask if c & top else (c << 1) & mask
    return c


def crc(data, width, init, refin, refout, xorout):
    c = crc_raw(data, width, init, refin)
    if refout:
        c = reflect(c, width)
    return c ^ xorout


def parse(lines):
    packets = []
    for line in lines:
        line = line.split('#', 1)[0].replace('0x', '').replace(',', ' ')
        hexs = ''.join(line.split())
        if hexs:
            packets.append(bytes.fromhex(hexs))
    return packets


def search(packets):
    """Yield every parameter set that fits all packets."""
    for width in (16, 32):
        n = width // 8
        if any(len(p) < 4 + n + 1 for p in packets):
            continue
        inits = range(1 << 16) if width == 16 else (0, 0xFFFFFFFF)
        for cover in ('header+payload', 'payload'):
            for order in ('little', 'big'):
                bodies, wanted = [], []
                for p in packets:
                    body = p[:-n] if cover == 'header+payload' else p[4:-n]
                    bodies.append(body)
                    wanted.append(int.from_bytes(p[-n:], order))
                for refin in (False, True):
                    for refout in (False, True):
                        # init 0 first: the pair test below does not depend on init
                        base = [crc(b, width, 0, refin, refout, 0) for b in bodies]
                        if not pairs_fit(bodies, base, wanted):
                            continue
                        # the CRC is linear in init: crc(init, d) = crc(0, d) ^ crc(init, zeros),
                        # so per length the init part is a XOR of basis values
                        basis = {}
                        for b in bodies:
                            if len(b) not in basis:
                                zeros = bytes(len(b))
                                basis[len(b)] = [crc(zeros, width, 1 << i, refin, refout, 0) ^
                                                 crc(zeros, width, 0, refin, refout, 0) for i in range(width)]
                        for init in inits:
                            got = []
                            for b, c in zip(bodies, base):
                                for i, v in enumerate(basis[len(b)]):
                                    if init >> i & 1:
                                        c ^= v
                                got.append(c)
                            xorout = got[0] ^ wanted[0]
                            if all(g ^ xorout == w for g, w in zip(got, wanted)):
                                yield dict(width=width, cover=cover, order=order, init=init,
                                           refin=refin, refout=refout, xorout=xorout)


def pairs_fit(bodies, base, wanted):
    """For packets of equal length CRC differences do not depend on init or xorout."""
    by_len = {}
    for b, c, w in zip(bodies, base, wanted):
        by_len.setdefault(len(b), []).append((c, w))
    for group in by_len.values():
        c0, w0 = group[0]
        if any(c ^ c0 != w ^ w0 for c, w in group[1:]):
            return False
    return True


def fmt(p):
    w = 4 if p['width'] == 16 else 8
    return (f"CRC{p['width']} over {p['cover']}, CRC bytes {p['order']}-endian, "
            f"init 0x{p['init']:0{w}X}, refin {int(p['refin'])}, refout {int(p['refout'])}, "
            f"xorout 0x{p['xorout']:0{w}X}")


def selftest():
    rnd = random.Random(1)
    cases = [
        dict(width=16, cover='header+payload', order='little', init=0, refin=False, refout=False, xorout=0),
        dict(width=16, cover='header+payload', order='little', init=0xFFFF, refin=True, refout=True, xorout=0xFFFF),
        dict(width=16, cover='payload', order='big', init=0x1D0F, refin=False, refout=False, xorout=0),
        dict(width=32, cover='header+payload', order='little', init=0xFFFFFFFF, refin=True, refout=True,
             xorout=0xFFFFFFFF),
        dict(width=32, cover='header+payload', order='little', init=0, refin=False, refout=False, xorout=0),
    ]
    # catalogue check values of "123456789"
    m = b'123456789'
    assert crc(m, 16, 0, False, False, 0) == 0xFEE8          # CRC-16/UMTS
    assert crc(m, 16, 0, True, True, 0) == 0xBB3D            # CRC-16/ARC
    assert crc(m, 16, 0xFFFF, True, True, 0xFFFF) == 0xB4C8  # CRC-16/USB
    assert crc(m, 32, 0xFFFFFFFF, True, True, 0xFFFFFFFF) == 0xCBF43926  # CRC-32
    assert crc(m, 32, 0xFFFFFFFF, False, False, 0) == 0x0376E6E7         # CRC-32/MPEG-2
    ok = True
    for case in cases:
        n = case['width'] // 8
        packets = []
        for length in (8, 8, 20, 64):
            body = bytes(rnd.randrange(256) for _ in range(4 + length))
            covered = body if case['cover'] == 'header+payload' else body[4:]
            c = crc(covered, case['width'], case['init'], case['refin'], case['refout'], case['xorout'])
            packets.append(body + c.to_bytes(n, case['order']))
        found = list(search(packets))
        hit = case in found
        print(('ok   ' if hit else 'FAIL ') + fmt(case) + f'  ({len(found)} candidates)')
        ok &= hit
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('file', nargs='?', help='packets, one per line in hex; - for stdin')
    ap.add_argument('--selftest', action='store_true', help='check the search on generated packets')
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if not a.file:
        ap.error('no packets')
    lines = sys.stdin if a.file == '-' else open(a.file)
    packets = parse(lines)
    if len({len(p) for p in packets}) < 2:
        print('warning: all packets have the same length, init and xorout are not separable', file=sys.stderr)
    found = list(search(packets))
    for p in found:
        print(fmt(p))
    if not found:
        print('no parameter set fits all packets', file=sys.stderr)
    sys.exit(0 if found else 1)


if __name__ == '__main__':
    main()
