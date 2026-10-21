# ch569 — прошивки CH569

Сборка опирается на BSP [`au/hydrausb3_fw`](../../au/hydrausb3_fw) (вложенный подмодуль
`wch-ch56x-bsp`, Apache-2.0):

```sh
git submodule update --init --recursive --depth 1 au/hydrausb3_fw
```

| Папка | Что |
|---|---|
| [`usbstream/`](usbstream/) | CH569 сам выдаёт поток самопроверки в USB3 bulk EP2 IN, без ПЛИС. Половина шага 0 [плана проверки](../../hw/README.md#9-план-проверки): потолок USB3 → ПК отдельно от HSPI |
| [`hspi2usb/`](hspi2usb/) | Мост HSPI → USB3 для шага 0: пакеты от ПЛИС (`gw/cores/selftest_hspi.sv`) в EP2 IN; внутренний источник для проверки без ПЛИС |
| [`common/`](common/) | Общее: форк стека USB из BSP с EP2 IN под приложение ([`ep2.h`](common/ep2.h)), запуск USB и светодиод статуса, слой платы, правила сборки [`app.mk`](common/app.mk) |

## Платы

`make BOARD=evt` (по умолчанию) или `make BOARD=hydrausb3`. Слой платы ([`common/board.h`](common/board.h))
даёт три логических светодиода: статус USB, активность, ошибка.

| Плата | Светодиоды | Кнопка |
|---|---|---|
| WCH CH569W EVT ([`board_evt.c`](common/board/board_evt.c), схема `EVT/PUB/CH569WSCH.pdf` в openwch/ch569) | LED0 зелёный PB24 — статус, LED1 синий PB22 — активность, LED2 жёлтый PB23 — ошибка; горят при низком уровне | нет на GPIO: Download — HD0/PA5 при включении |
| HydraUSB3 v1 ([`board_hydrausb3.c`](common/board/board_hydrausb3.c)) | ULED PB22 — статус | UBTN PB23 не используется |

Светодиод статуса горит постоянно до перечисления, затем мигает раз в 0,5 с на USB3 и раз в 1 с на USB2.

## Тулчейн

Нужен xPack riscv-none-elf-gcc 12.2.0-1 из
[hydrausb3/riscv-none-elf-gcc-xpack](https://github.com/hydrausb3/riscv-none-elf-gcc-xpack/releases).
Он понимает `__attribute__((interrupt("WCH-Interrupt-fast")))`: обработчик кончается `mret` без
сохранения регистров, их сохраняет аппаратный стек CH569. Штатный `riscv64-unknown-elf-gcc` такой
атрибут не знает, собирает образ, но обработчики прерываний в нём испорчены.

```sh
make -C fw/ch569/usbstream CROSS=~/.local/opt/xpack-riscv-none-elf-gcc-12.2.0-1/bin/riscv-none-elf-
```

## Прошивка

Загрузчик: зажать Download (HD0 на землю) и включить питание, появится `4348:55e0`. Без обращений он
выходит через 10 с. Шить через
[wch-ch56x-isp](https://github.com/hydrausb3/wch-ch56x-isp/releases):

```sh
wch-ch56x-isp -v -r -f fw/ch569/usbstream/build/usbstream.bin
```

wchisp 0.3.0 читает CH569 и стирает флеш, но запись падает с `isp_key checksum failed` (загрузчик 02.80).

Доступ без root — [`sw/udev/50-rln-trace.rules`](../../sw/udev/50-rln-trace.rules).

**WSL.** usbipd-win пробрасывает и загрузчик, и прошивку, в том числе на SuperSpeed. `bind` делается
один раз из PowerShell администратора при подключённом устройстве (`usbipd bind --hardware-id
4348:55e0 --force`, затем то же для `16c0:05dc`), дальше из WSL —
`usbipd.exe attach --wsl --hardware-id <VID:PID>`. Окно загрузчика короткое, поэтому attach и
прошивку удобно запускать в цикле, который ждёт устройство.

## Память

Конфигурация чипа на плате стенда (wchisp `info`): USER_MEM = RAMX 96 КБ + ROM 32 КБ, DEBUG_EN = 0,
RESET_EN = 0 (PB15 — GPIO, то есть HD14 свободна для HSPI 16 бит). При таком USER_MEM исполняемого
кода не больше 32 КБ, Makefile проверяет размер образа. Буферы DMA лежат в RAMX.
