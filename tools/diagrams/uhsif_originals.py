"""Original WCH figures next to our redrawn UHSIF / CH32H417 diagrams, for checking by eye.

The PNGs (*.orig*.png) are WCH material and are git-ignored; this script regenerates them.
Needs PyMuPDF (pip install pymupdf) and the au/ch32h417 submodule; the datasheet is not in
that repository and is downloaded to tools/diagrams/build/.

Run: python3 tools/diagrams/uhsif_originals.py
"""
import os
import urllib.request

import pymupdf

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '../..'))
MANUAL = os.path.join(ROOT, 'au/ch32h417/EVT/EXAM/UHSIF/CH32H417 UHSIF Development Reference Manual-EN.pdf')
DS_URL = 'https://atta.szlcsc.com/upload/public/pdf/source/20260518/A332D0233125C0DE3BEB32D7A2C6A50E.pdf'
DS = os.path.join(HERE, 'build/CH32H417DS0_V1.8.pdf')
UHSIF_IMG = os.path.join(ROOT, 'doc/img/uhsif')
MCU_IMG = os.path.join(ROOT, 'hw/img/ch32h417')

# (output, pdf, page locator, clip height below the caption in points or None for the whole page)
# page locator: 1-based page number, or text that appears on the page (first match)
FIGURES = [
    (f'{UHSIF_IMG}/01-write.orig.png', MANUAL, 'Figure 4-2', 120),
    (f'{UHSIF_IMG}/02-zlp.orig.png', MANUAL, 'Figure 4-3', 160),
    (f'{UHSIF_IMG}/03-read.orig.png', MANUAL, 'Figure 4-4', 150),
    (f'{UHSIF_IMG}/04-io-timing.orig.png', MANUAL, '7. Electrical Characteristics', 260),
    (f'{UHSIF_IMG}/05-lines.orig.png', MANUAL, 'Figure 4-1', 212),
    (f'{MCU_IMG}/09-clock.orig.png', DS, '图1-3', None),
    (f'{MCU_IMG}/10-pins.orig.png', MANUAL, 'Figure 3-1', 560),
    (f'{MCU_IMG}/10-pins.orig-2.png', DS, '表 2-2-16', None),
    (f'{MCU_IMG}/10-pins.orig-3.png', DS, 70, None),   # table 2-2-16 continues (datasheet V1.8 page numbers),
    (f'{MCU_IMG}/10-pins.orig-4.png', DS, 71, None),
    (f'{MCU_IMG}/11-power.orig.png', DS, '图3-1-1', None),
    (f'{MCU_IMG}/11-power.orig-2.png', DS, '图3-1-2', None),
    (f'{MCU_IMG}/11-power.orig-3.png', DS, 'RHSEXO_ext', None),
    (f'{MCU_IMG}/12-block.orig.png', DS, '图1-1-1', None),
]


def find(doc, loc):
    if isinstance(loc, int):
        return doc[loc - 1], None
    key = loc.replace(' ', '')
    for page in doc:
        if key in page.get_text().replace(' ', ''):
            hits = page.search_for(loc)
            return page, (hits[0] if hits else None)
    raise SystemExit(f'not found: {loc}')


def main():
    if not os.path.exists(DS):
        os.makedirs(os.path.dirname(DS), exist_ok=True)
        print('downloading datasheet ...')
        urllib.request.urlretrieve(DS_URL, DS)
    docs = {}
    for out, pdf, loc, height in FIGURES:
        doc = docs.setdefault(pdf, pymupdf.open(pdf))
        page, hit = find(doc, loc)
        clip = None
        if height and hit is not None:
            r = page.rect
            clip = pymupdf.Rect(r.x0 + 30, hit.y0 - 6, r.x1 - 30, min(r.y1, hit.y0 + height))
        os.makedirs(os.path.dirname(out), exist_ok=True)
        page.get_pixmap(dpi=150, clip=clip).save(out)
        print(os.path.relpath(out, ROOT), f'(p{page.number + 1})')


if __name__ == '__main__':
    main()
