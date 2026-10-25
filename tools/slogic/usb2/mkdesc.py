#!/usr/bin/env python3
"""Дескрипторы USB для образа usb2 → usb_desc.v (комбинационное ПЗУ + адреса и длины).

Раскладка как у usb_serial Й. ван Рантвейка, на котором построен Gowin USB 2.0 Device
Controller: адрес ПЗУ контроллер защёлкивает сам, байт нужен в следующем такте — ПЗУ без
регистра. desc_oscfg_addr указывает на байт 0x07: им подменяется bDescriptorType при запросе
other_speed_configuration.

    python3 mkdesc.py > usb_desc.v
"""

VID, PID, BCD = 0x1209, 0x0001, 0x0100  # pid.codes: тестовый PID, только для своих опытов
STRINGS = ["rln-trace", "SLogic16U3 trace", "0001"]


def le16(x):
    return [x & 0xFF, x >> 8]


def config(mps):
    """Конфигурация: один интерфейс vendor, EP1 IN и EP1 OUT bulk."""
    intf = [9, 4, 0, 0, 2, 0xFF, 0x00, 0x00, 0]
    ep_in = [7, 5, 0x81, 2] + le16(mps) + [0]
    ep_out = [7, 5, 0x01, 2] + le16(mps) + [0]
    body = intf + ep_in + ep_out
    return [9, 2] + le16(9 + len(body)) + [1, 1, 0, 0x80, 250] + body  # от шины, 500 мА


def string(s):
    b = [2 + 2 * len(s), 3]
    for c in s:
        b += [ord(c), 0]
    return b


dev = [18, 1] + le16(0x0200) + [0, 0, 0, 64] + le16(VID) + le16(PID) + le16(BCD) + [1, 2, 3, 1]
qual = [10, 6] + le16(0x0200) + [0, 0, 0, 64, 1, 0]
parts = [("DEV", dev), ("QUAL", qual), ("FSCFG", config(64)), ("HSCFG", config(512)),
         ("OSCFG", [0x07]), ("STRLANG", [4, 3, 0x09, 0x04])]
parts += [(n, string(s)) for n, s in zip(("STRVENDOR", "STRPRODUCT", "STRSERIAL"), STRINGS)]

rom, addr = [], {}
for name, b in parts:
    addr[name] = (len(rom), len(b))
    rom += b

print(f"""// Сгенерировано mkdesc.py — не править руками. VID:PID {VID:04x}:{PID:04x}, {len(rom)} байт.
module usb_desc (
    input wire [15:0] raddr,
    output reg [7:0] rdata,""")
outs = []
for name, (a, n) in addr.items():
    outs.append(f"    output wire [15:0] {name.lower()}_addr")
    if name not in ("OSCFG", "STRLANG"):
        outs.append(f"    output wire [15:0] {name.lower()}_len")
print(",\n".join(outs))
print(");")
for name, (a, n) in addr.items():
    print(f"    assign {name.lower()}_addr = 16'd{a};")
    if name not in ("OSCFG", "STRLANG"):
        print(f"    assign {name.lower()}_len = 16'd{n};")
print("    always @*\n        case (raddr)")
for i, b in enumerate(rom):
    print(f"            {i}: rdata = 8'h{b:02x};")
print("            default: rdata = 8'h00;\n        endcase\nendmodule")
