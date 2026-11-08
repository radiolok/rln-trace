# Tang Nano 9K — источник сигналов стенда

[`top_gen.sv`](top_gen.sv): второй прибор стенда, генерирует то, что Tang Nano 20K принимает.

- **Трасса для петли (шаг 2):** [`tpiu_tx`](../../cores/tpiu_tx.sv) — поток форматтера TPIU с кадрами,
  которые вычисляются по номеру (байт 0 — смена ID на 1, байты 1/3/5/7 — номер кадра, остальное — из
  номера), полное синхрослово каждые 16 кадров. Порт 4/2/1 бит, TRACED0–3 через ODDR, первая выборка —
  по фронту такта. На приёмной стороне каждый кадр проверяется по номеру (тест `gw/test/loop`).
- **TRACECLK** — отдельный выход PLL со сдвигом `TRC_PHASE` × 22,5° (по умолчанию 90°, середина бита).
  Перебором фазы видно окно приёма 20K.
- **PPS:** 1 Гц, импульс 100 мкс. **Меандр** 1 кГц — на вход SMA2.
- `TRC_MHZ`: 12 (проводки, по умолчанию), 24 (STM32 на 48 МГц), 84 (STM32F407 на 168 МГц).

| Кнопка, светодиод (горят нулём) | Что |
|---|---|
| S1 (4) | сброс |
| S2 (3) | ширина порта 4 → 2 → 1 → 4 бита; смена ширины начинает поток заново с синхрослова |
| LED0 (10) | сердцебиение |
| LED1 (11) | PLL захвачен |
| LED2, LED3 (13, 14) | ширина: 4 бита — оба, 2 — LED3, 1 — LED2 |
| LED4 (15) | PPS |
| LED5 (16) | меандр |

UART BL702 (115200 8N1), раз в секунду: `# <кадров отправлено> <ширина> <TRC_MHZ>`, hex.

## Выводы и провода к Tang Nano 20K

Гребёнки — по схеме Sipeed `Tang_nano_9K_3674_schematics.pdf` (J5, J6). **Выводы 79–86 на J6 — банк
на 1,8 В**, вход 20K на 3,3 В их уровень надёжно не увидит; здесь используются только выводы на 3,3 В.
Ограничения — [`tangnano9k.cst`](tangnano9k.cst).

| Tang Nano 9K (J5) | Сигнал | Tang Nano 20K |
|---|---|---|
| 25 (J5-5) | TRACECLK | 77 (GCLKT_1) |
| 26 (J5-6) | TRACED0 | 15 |
| 27 (J5-7) | TRACED1 | 16 |
| 28 (J5-8) | TRACED2 | 27 |
| 29 (J5-9) | TRACED3 | 28 |
| 30 (J5-10) | PPS | 31 |
| 33 (J5-11) | меандр | 17 (SMA2) |
| GND (J6-23) | земля | GND |

Свободные выводы на 3,3 В для расширения: J5 — 34–42, 51, 53–57; J6 — 31, 32, 48, 49, 63, 76, 77.

## Сборка

```sh
make -C gw board9k-lint                  # Verilator, все три TRC_MHZ
make -C gw board9k-synth                 # Yosys (так и в CI)
make -C gw board9k-pnr OSS=~/.local/opt/oss-cad-suite/bin/ TN9K_MHZ=12
openFPGALoader -b tangnano9k gw/build/tangnano9k/top_gen.fs
```

| Дата | Тулчейн | TRC_MHZ | LUT4 | Fmax |
|---|---|---|---|---|
| 2026-10-21 | Yosys 0.70 + nextpnr-himbaechel 0.11 | 12 | 487 (6 %) | 91 МГц |
| 2026-10-21 | Yosys 0.70 + nextpnr-himbaechel 0.11 | 84 | 509 (6 %) | 98,6 МГц |

## JTAG-зонд для STM32F4-Discovery (`top_jtag`)

Второй образ этой же платы: первый кусок движка отладки, шаг 6 [стенда](../../../doc/bench.md#отладка-swdjtag).
OpenOCD работает с драйвером `remote_bitbang`. [`sw/rbb/rbb_bridge.py`](../../../sw/rbb/rbb_bridge.py) передаёт байты из TCP в
UART BL702 и обратно, а [`rbb_jtag`](../../cores/rbb_jtag.sv) ведёт выводы: один байт ASCII — одно состояние
TCK/TMS/TDI, `R` — ответ TDO. UART — 3 Мбод (27 МГц / 9), без PLL. Журнал — [`doc/jtag-journal.md`](../../../doc/jtag-journal.md).

| Tang Nano 9K (J5) | Сигнал | STM32F4-Discovery |
|---|---|---|
| 34 | TCK / SWCLK | PA14 |
| 40 | TMS / SWDIO | PA13 |
| 35 | TDI | PA15 |
| 41 | TDO (подтяжка в ПЛИС) | PB3 |
| 39 | nTRST | PB4 |
| 42 | nSRST, открытый сток | NRST |
| GND | земля | GND |

Перемычки CN3 на Discovery сняты, USB ST-LINK — только для питания. Выводы трассы 25–33 не заняты, обе
проводки могут стоять одновременно. Ограничения — [`tangnano9k_jtag.cst`](tangnano9k_jtag.cst).

Светодиоды (горят нулём): 0 — `B` от OpenOCD, 1 — байты по UART, 2 — srst, 3 — trst, 4 — уровень TDO,
5 — сердцебиение. S1 — сброс.

```sh
make -C gw board9k-jtag-pnr OSS=~/.local/opt/oss-cad-suite/bin/      # TN9K_DIV=27 — 1 Мбод
openFPGALoader -b tangnano9k -m gw/build/tangnano9k/top_jtag.fs
sw/rbb/rbb_bridge.py /dev/ttyUSB1 &                                   # канал B BL702
openocd -f sw/rbb/stm32f4-rbb.cfg                                     # JTAG
openocd -f sw/rbb/stm32f4-rbb-swd.cfg                                 # SWD, те же провода
```

| Дата | Тулчейн | UART | LUT4 | Fmax |
|---|---|---|---|---|
| 2026-11-08 | Yosys 0.70 + nextpnr-himbaechel 0.11 | 3 Мбод | 214 (2 %) | 128 МГц |
| 2026-11-08, + SWD | Yosys 0.70 + nextpnr-himbaechel 0.11 | 3 Мбод | 232 (2 %) | 132 МГц |
