#!/usr/bin/env python3
"""Состояние образа usb3ref (ciniml/board/top.v) по JTAG ER1: LTSSM, история состояний, счётчики.
Через нашу FT2232H и OpenOCD (tools/slogic/uprobe). Раскладка полей ER1 — из host/usb3_status.py ciniml (BSL-1.0).

    RLN_FPGA_USB=1-2 python3 u3status.py          # один кадр
    RLN_FPGA_USB=1-2 python3 u3status.py -w 1     # кадр раз в секунду
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "uprobe"))
import uprobe as u  # noqa: E402

OSC_HZ = 51.66e6  # OSCB образа (счётчик pclk и аптайм — по нему, точность ~1 %)
MAGIC = 0x5B31
NBITS = 448       # 432 бита ER1 + запас на сдвиг (первым идёт лишний бит, кадр ищется по метке)
STATES = ["PhyWait", "Disabled", "Inactive", "RxDetReset", "RxDetActive", "RxDetQuiet", "PollLfps", "PollRxEq",
          "PollActive", "PollConfig", "PollIdle", "U0", "U3", "U3Wake", "RecActive", "RecConfig", "RecIdle",
          "HotRstActive", "HotRstExit"]


def st(n):
    return STATES[n] if n < len(STATES) else f"?{n}"


def read():
    out = u.openocd(["irscan gw5a.tap 0x42", f'puts "DR [drscan gw5a.tap {NBITS} 0]"'])
    m = re.search(r"^DR (\S+)$", out, re.M)
    if not m:
        sys.exit("OpenOCD не вернул данные:\n" + out[-1500:])
    raw = int(m[1], 16)
    for off in range(8):
        v = raw >> off
        if v & 0xFFFF == MAGIC:
            break
    else:
        sys.exit(f"нет метки 0x{MAGIC:04x} в ER1: образ usb3 не загружен?")

    def f(lo, w):
        return (v >> lo) & ((1 << w) - 1)
    return {
        "ref_lock": f(16, 1), "phy_resetn": f(17, 1), "pclk": f(24, 20) * 16 * OSC_HZ / (1 << 22),
        "prst": f(44, 1), "in_u0": f(45, 1), "link_cfg": f(46, 1), "dev_cfg": f(47, 1),
        "tx_detrx": f(51, 1), "tx_eidle": f(52, 1), "pd": f(53, 2), "state": f(56, 5), "st_max": f(64, 5),
        "rx_status": f(72, 3), "rx_eidle": f(76, 1), "power_present": f(77, 1),
        "addr": f(80, 7), "trans": f(88, 8), "u0": f(112, 16), "hp": f(128, 16), "resets": f(144, 16),
        "dpp_err": f(160, 16), "physt": f(176, 16), "lfps": f(192, 16), "seen": f(208, 32),
        "trace": [f(240 + 5 * i, 5) for i in range(16)], "up": f(352, 32) * 65536 / OSC_HZ,
        "com": f(384, 16), "dec_err": f(400, 16), "disp_err": f(416, 16),
    }


def show(s):
    print(f"аптайм {s['up']:.1f} с, ref_lock {s['ref_lock']}, phy_resetn {s['phy_resetn']}, pclk {s['pclk'] / 1e6:.2f} МГц, "
          f"power_present {s['power_present']}, PhyStatus {s['physt']}")
    print("история:", " > ".join(st(x) for x in reversed(s["trace"])))
    print(f"{st(s['state'])} (дальше всех — {st(s['st_max'])}): U0 {s['in_u0']}, link_cfg {s['link_cfg']}, "
          f"dev_cfg {s['dev_cfg']}, адрес {s['addr']}, P{s['pd']}, TxElecIdle {s['tx_eidle']}, "
          f"TxDetectRx {s['tx_detrx']}, RxElecIdle {s['rx_eidle']}, RxStatus {s['rx_status']}")
    print(f"входов в U0 {s['u0']}, заголовков {s['hp']}, сбросов {s['resets']}, ошибок DPP {s['dpp_err']}, "
          f"LFPS {s['lfps']}, переходов {s['trans']}; приём: COM {s['com']}, ошибок 8b10b {s['dec_err']}, "
          f"чётности {s['disp_err']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-w", type=float, metavar="СЕК", help="читать с периодом")
    a = ap.parse_args()
    while True:
        show(read())
        if not a.w:
            break
        time.sleep(a.w)
        print()


if __name__ == "__main__":
    main()
