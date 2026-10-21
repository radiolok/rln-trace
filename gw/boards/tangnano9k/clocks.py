# nextpnr pre-pack script for top_gen: clk at TRC_MHZ from the environment
# (make passes TN9K_MHZ). The phase-shifted copy for the TRACECLK pin only
# drives an ODDR.
import os

ctx.addClock("clk", float(os.environ.get("TRC_MHZ", "12")))
