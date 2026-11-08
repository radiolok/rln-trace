#!/usr/bin/env python3
"""TCP <-> UART bridge for OpenOCD remote_bitbang: OpenOCD connects to the TCP
port, every byte goes to the serial port as is and back. The JTAG engine on the
other side is gw/cores/rbb_jtag.sv (Tang Nano 9K, gw/boards/tangnano9k/top_jtag.sv).

    rbb_bridge.py /dev/ttyUSB1
    openocd -f sw/rbb/stm32f4-rbb.cfg

SPDX-License-Identifier: BSD-3-Clause
"""
import argparse
import socket
import sys
import threading

import serial


def uart_to_tcp(ser, conn, stop):
    while not stop.is_set():
        data = ser.read(ser.in_waiting or 1)
        if data:
            try:
                conn.sendall(data)
            except OSError:
                break


def open_checked(port, baud, tries=3):
    """The BL702 sometimes ignores the rate on the first open after the FPGA is
    loaded: ask rbb_jtag for TDO ('R') and reopen until it answers."""
    for _ in range(tries):
        ser = serial.Serial(port, baud, timeout=0.2)
        ser.reset_input_buffer()
        ser.write(b"R")
        if ser.read(1) in (b"0", b"1"):
            ser.timeout = 0.01
            return ser
        ser.close()
    sys.exit(f"{port} @ {baud}: no answer from rbb_jtag (top_jtag loaded? right port and rate?)")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("port", help="serial port of the BL702, e.g. /dev/ttyUSB1")
    ap.add_argument("-b", "--baud", type=int, default=3000000, help="27 MHz / DIV of top_jtag (default 3000000)")
    ap.add_argument("-p", "--tcp", type=int, default=3335, help="TCP port for OpenOCD (default 3335)")
    a = ap.parse_args()

    ser = open_checked(a.port, a.baud)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", a.tcp))
    srv.listen(1)
    print(f"{a.port} @ {a.baud}, waiting for OpenOCD on 127.0.0.1:{a.tcp}", file=sys.stderr)
    while True:
        conn, peer = srv.accept()
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        print(f"connected {peer[0]}:{peer[1]}", file=sys.stderr)
        ser.reset_input_buffer()
        stop = threading.Event()
        t = threading.Thread(target=uart_to_tcp, args=(ser, conn, stop), daemon=True)
        t.start()
        n = 0
        try:
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                ser.write(data)
                n += len(data)
        except OSError:
            pass
        stop.set()
        t.join()
        conn.close()
        print(f"disconnected, {n} bytes sent", file=sys.stderr)


if __name__ == "__main__":
    main()
