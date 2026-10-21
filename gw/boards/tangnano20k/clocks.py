# nextpnr pre-pack script: per-clock targets for top_step0 (MHz).
# clk: the PLL output (HRCLK of the CH569, the self-test); HTCLK of the CH569 runs
# at its Fsys, up to 120 MHz. After synthesis a net may carry the name of a port
# it drives, so each clock is looked up under every name it may have.
CLOCKS = {
    ("clk",): 60,
    ("htclk", "u_rx.rx_clk"): 120,
}
names = {name for name, _ in ctx.nets}
for aliases, mhz in CLOCKS.items():
    found = [n for n in aliases if n in names]
    if not found:
        raise RuntimeError("clock net not found: %s" % "/".join(aliases))
    for name in found:          # the pad net and the buffered net both get it
        ctx.addClock(name, mhz)
