#!/usr/bin/env python3
"""Команды трассеру BE-U1000 через постоянный OpenOCD (Tcl-порт 6668).

Каждый запуск OpenOCD сбрасывает BE-U1000 (FTDI платы дёргает nSRST при входе в MPSSE),
поэтому сервер поднимается один раз и живёт в фоне; настройки трассера переживают только так.

  beu1000/ocd.py "pll 1 48 6; tclk 1 4; pins; pib_on; tr_status"
  beu1000/ocd.py --stop
Адаптер платы — RLN_BEU_USB (место на шине USB, например 1-1).
"""
import os
import socket
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SDK = os.path.join(os.environ.get("BAIKAL_SDK", os.path.expanduser("~/.local/opt/baikal-mcu-sdk-2.3.0")),
                   "Tools", "OpenOCD")
PORT = 6668
LOG = os.path.join(HERE, "openocd.log")


def connect():
    try:
        return socket.create_connection(("127.0.0.1", PORT), timeout=60)
    except OSError:
        return None


def start():
    subprocess.Popen([os.path.join(SDK, "bin", "openocd"), "-s", os.path.join(SDK, "share", "openocd", "scripts"),
                      "-f", os.path.join(HERE, "openocd.cfg"), "-f", os.path.join(HERE, "trace.tcl")],
                     stdout=open(LOG, "w"), stderr=subprocess.STDOUT, start_new_session=True)
    for _ in range(50):
        time.sleep(0.2)
        s = connect()
        if s:
            return s
    sys.exit("OpenOCD не поднялся:\n" + open(LOG).read()[-1500:])


def cmd(s, c):
    s.sendall(c.encode() + b"\x1a")
    buf = b""
    while not buf.endswith(b"\x1a"):
        chunk = s.recv(65536)
        if not chunk:
            sys.exit("OpenOCD закрыл соединение")
        buf += chunk
    return buf[:-1].decode()


def run(script):
    """Выполнить Tcl в сервере, вернуть вывод puts и результат."""
    s = connect() or start()
    pos = os.path.getsize(LOG)
    out = cmd(s, "capture {" + script + "}")
    s.close()
    with open(LOG) as f:  # puts и сообщения OpenOCD идут в лог, а не в ответ
        f.seek(pos)
        log = "".join(l for l in f if not l.startswith(("Error: [CORE_1]", "Error: [CORE_2]")))
    return log + out


if __name__ == "__main__":
    if sys.argv[1:] == ["--stop"]:
        s = connect()
        if s:
            s.sendall(b"shutdown\x1a")
        sys.exit(0)
    print(run(" ".join(sys.argv[1:])), end="")
