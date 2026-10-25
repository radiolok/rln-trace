#!/usr/bin/env python3
"""Кадр образа sdprobe: детекторы REFCLK, CMU_OK и частоты тактов SerDes Q0 SLogic16U3.

    openFPGALoader -c ft2232 --busdev-num … -m sdprobe.fs
    RLN_FPGA_USB=1-2 python3 sdprobe.py            # кадр
    RLN_FPGA_USB=1-2 python3 sdprobe.py --reset 1  # держать линию 0 в сбросе (0 — отпустить)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "uprobe"))
import uprobe as u  # noqa: E402  OpenOCD, ER1/ER2

MAGIC = 0x534E4C52  # "RLNS"
NW = 14
FLAGS = ["REFCLK_DET CM0", "REFCLK_DET CM1", "REFCLK_DET CM2", "REFCLK_DET CM3", "CMU_OK (QPLL0)",
         "CMU1_OK (QPLL1)", "PMA_RX_LOCK ln0"]
CLKS = ["CMU_CK_REF", "CMU1_CK_REF", "CM_LIFE_CLK", "CM1_LIFE_CLK", "PCS_TX ln0", "PCS_RX ln0",
        "LANE0_CMU_CK_REF", "QUAD_CLK_RX", "CMU0_CLK", "CMU1_CLK"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", type=int, choices=(0, 1))
    a = ap.parse_args()
    u.MAGIC = MAGIC
    cmds = u.er2(0xA << 28 | a.reset) if a.reset is not None else []
    w = u.parse(u.openocd(cmds + u.er1("", NW)), NW)[""]
    t = 2 ** (w[1] >> 16 & 0xFF) / u.F_OSC
    print(f"v{w[1] & 0xFF}, окно {t:.2f} с, seq {w[1] >> 24}, команда {w[2]:#x}")
    st = w[3]
    for i, n in enumerate(FLAGS):
        seen = ("1" if st >> (8 + i) & 1 else "") + ("0" if st >> (16 + i) & 1 else "")
        print(f"  {n:18} {st >> i & 1}  был {seen}")
    for i, n in enumerate(CLKS):
        print(f"  {n:18} {w[4 + i] / t / 1e6:10.3f} МГц")


if __name__ == "__main__":
    main()
