"""Regenerate hw/probe-b/kicad from design.py, run the connectivity check and render PNG previews."""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import design
from render import render
from footprint import qfn88

OUT = os.path.join(HERE, '../../hw/probe-b/kicad')
PREV = os.path.join(HERE, 'preview')

p = design.proj
p.write(OUT)
qfn88(os.path.join(OUT, 'probe.pretty/QFN-88-1EP_10x10mm_P0.4mm_EP6.74x6.74mm.kicad_mod'))
problems, nets, names = p.check()
print(f'nets: {len(nets)}  problems: {len(problems)}')
for x in problems:
    print('  ', x)
os.makedirs(PREV, exist_ok=True)
for sh in p.sheets:
    render(sh, os.path.join(PREV, sh.file[:-10] + '.png'), p.global_nets)
render(p.root, os.path.join(PREV, 'root.png'), p.global_nets)
