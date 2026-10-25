#!/usr/bin/env python3
"""Дескрипторы USB для образа usb2 → usb_desc.v (комбинационное ПЗУ + адреса и длины).

Раскладка как у usb_serial Й. ван Рантвейка, на котором построен Gowin USB 2.0 Device
Controller: адрес ПЗУ контроллер защёлкивает сам, байт нужен в следующем такте — ПЗУ без
регистра. desc_oscfg_addr указывает на байт 0x07: им подменяется bDescriptorType при запросе
other_speed_configuration.

    python3 mkdesc.py > usb_desc.v
    python3 mkdesc.py daisho      # → daisho/usb_descrip.vh, daisho/usb2_descrip_rom.v

Для Daisho (usb2d.v): ПЗУ на 256 байт с задержкой чтения в такт, смещения — параметрами
usb_descrip.vh; длина ответа — первый байт дескриптора (у конфигурации — DESCR_USB2_CONFIG_LEN).
Конфигурация одна — HS (bulk по 512): EP1 IN и EP2 OUT, как в usb2_protocol.v.
"""
import os
import sys

VID, PID, BCD = 0x1209, 0x0001, 0x0100  # pid.codes: тестовый PID, только для своих опытов
STRINGS = ["rln-trace", "SLogic16U3 trace", "0001"]


def le16(x):
    return [x & 0xFF, x >> 8]


def config(mps, ep_out_addr=0x01):
    """Конфигурация: один интерфейс vendor, EP1 IN и EP1 OUT (у Daisho — EP2 OUT) bulk."""
    intf = [9, 4, 0, 0, 2, 0xFF, 0x00, 0x00, 0]
    ep_in = [7, 5, 0x81, 2] + le16(mps) + [0]
    ep_out = [7, 5, ep_out_addr, 2] + le16(mps) + [0]
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



def daisho():
    d = [("DEVICE", dev), ("DEVICE_QUAL", qual), ("CONFIG", config(512, 0x02)),
         ("STRING0", [4, 3, 0x09, 0x04])]
    d += [(f"STRING{i + 1}", string(s)) for i, s in enumerate(STRINGS)]
    d += [("CONFUNSET", [0]), ("CONFSET", [1]), ("ZERO2", [0, 0])]
    rom, vh = [], [f"// Сгенерировано mkdesc.py daisho — не править руками. VID:PID {VID:04x}:{PID:04x}"]
    for name, b in d:
        vh.append(f"parameter [7:0] DESCR_USB2_{name} = 8'd{len(rom)};")
        if name == "CONFIG":
            vh.append(f"parameter [7:0] DESCR_USB2_CONFIG_LEN = 8'd{len(b)};")
        rom += b
    assert len(rom) <= 256 and max(len(b) for _, b in d) < 64  # desired_out_len в usb2_ep0 — 6 бит
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daisho")
    open(os.path.join(here, "usb_descrip.vh"), "w").write("\n".join(vh) + "\n")
    v = [f"// Сгенерировано mkdesc.py daisho — не править руками. {len(rom)} байт, чтение с задержкой в такт.",
         "module usb2_descrip_rom (", "    input wire clk,", "    input wire [7:0] adr,", "    output reg [7:0] dat_r",
         ");", "    reg [7:0] a = 0;", "    always @(posedge clk) a <= adr;", "    always @*", "        case (a)"]
    v += [f"            {i}: dat_r = 8'h{b:02x};" for i, b in enumerate(rom)]
    v += ["            default: dat_r = 8'h00;", "        endcase", "endmodule"]
    open(os.path.join(here, "usb2_descrip_rom.v"), "w").write("\n".join(v) + "\n")


if sys.argv[1:] == ["daisho"]:
    daisho()
    sys.exit()

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
