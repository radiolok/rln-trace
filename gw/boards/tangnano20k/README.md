# Tang Nano 20K — стенд, шаг 0

[`top_step0.sv`](top_step0.sv): ПЛИС → HSPI 8 бит → CH569 ([`fw/ch569/hspi2usb`](../../../fw/ch569/hspi2usb))
→ USB3 → [`sw/usbstream`](../../../sw/usbstream), и обратное направление CH569 → ПЛИС для замера CRC HSPI.

- 27 МГц → rPLL → `clk`, 60 МГц: HRCLK CH569 (через ODDR, в противофазе — CH569 защёлкивает HD по
  своему фронту посередине бита) и самотест: блоки PRBS31 по 4096 байт, пакет HSPI — блок, USDF 0x0525354.
- HTCLK CH569 тактирует `hspi_rx` в сыром режиме; принятые пакеты уходят в UART BL616 (115200 8N1)
  hex-строками — вход [`tools/hspi-crc/find_crc.py`](../../../tools/hspi-crc).
- Шина HD общая: пока CH569 держит HTREQ, новый пакет не начинается. HD отпущена (подтяжка вверх),
  пока ПЛИС не передаёт: HD0 низкий при включении CH569 — это его загрузчик.

| Кнопка, светодиод (горят нулём) | Что |
|---|---|
| S1 (88) | сброс |
| S2 (87) | самотест вкл/выкл (после сброса включён) |
| LED0 (15) | сердцебиение, ~1 Гц |
| LED1 (16) | PLL захвачен |
| LED2 (17) | самотест включён |
| LED3 (18) | пакеты HSPI уходят (бит 6 счётчика) |
| LED4 (19) | пакеты HSPI приходят от CH569 |
| LED5 (20) | был таймаут HTACK |

## Выводы

Гребёнки — по картинке Sipeed (`tang_nano_20k_pinlabel.png` на wiki.sipeed.com), встроенная
периферия — по примерам Sipeed. Ограничения — [`tangnano20k.cst`](tangnano20k.cst), частоты тактов —
[`clocks.py`](clocks.py). Переходник стенда разводится под эту таблицу.

| Сигнал | Вывод | Гребёнка | Сигнал CH569 EVT (P3) |
|---|---|---|---|
| HD0–HD7 | 56, 54, 51, 48, 55, 49, 53, 52 | правая, банк 3 | HD0–HD7 |
| HRCLK (выход) | 80 | правая | HRCLK |
| HRACT (выход, запрос) | 86 | правая | HRACT (на схеме зонда — `HSPI_HRACK`) |
| HRVLD (выход) | 72 | правая | HRVLD |
| HTACK (вход, готовность CH569) | 71 | правая | HTACK |
| HTCLK (вход, такт CH569) | 77 (GCLKT_1) | левая | HTCLK |
| HTREQ (вход) | 73 | левая | HTREQ |
| HTVLD (вход) | 74 | левая | HTVLD |
| HTRDY (выход) | 75 | левая | HTRDY |
| UART TX → BL616 | 69 | — | — |

77 — единственный вывод гребёнок для одиночного глобального такта (GCLKT); 76 и 79 — парные GCLKC.
На шаге 1 он понадобится TRACECLK: тогда HTCLK уйдёт на 76 через обычную трассировку или TRACECLK —
на 15 (LPLL2_T, нагружен светодиодом LED0). Решается вместе с переходником.

Выводы S1/S2: нажатая кнопка даёт 1 — так в примерах Sipeed, на плате не проверено.

## Сборка

```sh
make -C gw board-lint                    # Verilator, модели примитивов gw/platform/gowin/sim
make -C gw board-synth                   # Yosys synth_gowin (так и в CI)
make -C gw board-pnr OSS=~/.local/opt/oss-cad-suite/bin/   # nextpnr-himbaechel + gowin_pack -> .fs
openFPGALoader -b tangnano20k gw/build/tangnano20k/top_step0.fs    # в SRAM; -f — во флеш
make -C gw board-gowin                   # Gowin EDA под Windows из WSL (gw_sh.exe, GW_SH=...)
```

`board-gowin` копирует исходники, `tangnano20k.cst`, [`top_step0.sdc`](top_step0.sdc) и
[`gowin.tcl`](gowin.tcl) во временный каталог Windows, запускает `gw_sh` и забирает отчёты и
битстрим в `gw/build/tangnano20k/gowin/pnr/`. Нужна установленная Gowin EDA с действующей лицензией
(бесплатную выдаёт Gowin по запросу на сайте). Путь — переменная `GW_SH`.

| Дата | Тулчейн | LUT4 | ALU | DFF | BSRAM | Fmax clk / HTCLK |
|---|---|---|---|---|---|---|
| 2026-10-21 | Yosys 0.70 + nextpnr-himbaechel 0.11 (OSS CAD Suite 2026-10-20) | 1022 (4 %) | 354 | 539 | 1 | 135 / 149 МГц (нужно 60 / 120) |
| 2026-10-21 | Gowin EDA 1.9.12.04 | 572 LUT | 203 | 533 | 1 | 112 / 170 МГц |

Оценки Fmax у nextpnr заметно оптимистичнее, для подписи по таймингам надёжнее Gowin. Он же нашёл
узкое место HTCLK: свободное место FIFO `hspi_rx` (перевод указателя из кода Грея, вычитание,
сравнение) — 131 МГц при нужных 120; после регистра на `wfree` в `async_fifo` — 170 МГц.

Запас по `clk` позволяет поднять HRCLK до 96–99 МГц (`PLL_*`, расчёт — `gowin_pll` из OSS CAD Suite).
Сравнение с Gowin EDA — когда он будет поставлен.
