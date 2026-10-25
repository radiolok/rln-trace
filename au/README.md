# au — assembly units

Сторонние проекты, на которые опирается rln-trace, подключены сюда как git submodules.
Каждый подмодуль закреплён на конкретном коммите и сохраняет свою лицензию.

| Подмодуль | Что берём | Лицензия |
|---|---|---|
| [`orbtrace`](https://github.com/orbcode/orbtrace) | Референс приёма TPIU, USB-интерфейс трассы, CMSIS-DAP в ПЛИС | BSD-3-Clause |
| [`orbuculum`](https://github.com/orbcode/orbuculum) | Хост-инструменты трассы, протокол orbflow | BSD-3-Clause |
| [`opencsd`](https://github.com/Linaro/OpenCSD) | Декодер ETMv3.5 / ITM | BSD-3-Clause |
| [`free-dap`](https://github.com/ataradov/free-dap) | Протокольное ядро CMSIS-DAP для CH569 | BSD-3-Clause |
| [`hydrausb3_fw`](https://github.com/hydrausb3/hydrausb3_fw) | USB3 device и HSPI на CH569 | Apache-2.0 |
| [`ch32h417`](https://github.com/openwch/ch32h417) | Примеры WCH для CH32H417: StdPeriph, руководство по UHSIF, закрытая `libUHSIF.a` (сверка `fw/uhsif`, CI). Закреплён на той же ревизии, что `WCH_REF` в CI | не указана |
| [`nanoCH32H417`](https://github.com/wuxx/nanoCH32H417) | Схема MuseLab nanoCH32H417 v1.0 (`hardware/nanoCH32H417-v1.0.pdf`), примеры и готовые прошивки (USB3 CH372, ETH, SD, LCD). Плата для прошивки USB3 и проверки `fw/uhsif`; для стенда с ПЛИС UHSIF выведен не полностью, см. [`doc/ch32h417-uhsif.md`](../doc/ch32h417-uhsif.md#платы) | не указана |
| [`riscv-nexus-trace`](https://github.com/riscv-non-isa/riscv-nexus-trace) | Спецификации RISC-V N-Trace и Trace Control Interface (регистры `trTe*`/`trPib*`, протокол PIB, MSEO), эталонный кодер/декодер `refcode/c/NexRv*` — приём трассы BE-U1000, см. [`doc/beu1000-trace-journal.md`](../doc/beu1000-trace-journal.md) | спецификации CC-BY-4.0, `refcode` — ISC (IAR) |
| [`mcu-sdk`](https://gitflic.ru/project/baikalelectronics/mcu-sdk) | Baikal MCU SDK 2.4.0 для BE-U1000: OpenOCD (бинарник и скрипты `target/baikal`, `interface/baikal`) — им настраивается трассер, SVD, HAL, описание сборки. Компилятор, HAL, BASIS, FreeRTOS — вложенные подмодули (см. ниже) | BSD-3-Clause (код Байкала), GPL-2.0+ (OpenOCD, тулчейн), MIT (FreeRTOS, TinyUSB) |
| [`pico-usb-blaster`](https://github.com/thisiseth/pico-usb-blaster) | Протокол Altera USB-Blaster (FT245: bitbang и shift-режим), дескрипторы и EEPROM на tinyUSB — режим совместимости с Quartus | MIT |

Только как референс, без подмодуля: [Teensy_Blaster](https://github.com/Memotech-Bill/Teensy_Blaster) и
[usbd-blaster](https://github.com/sameer/usbd-blaster) (описание протокола USB-Blaster), [SucréLA](https://gitlab.com/yannsionneau/SucreLA) (LGPL-2.1),
[USB3.0 Device Controller IP от Gowin](https://github.com/GOWIN-FPGA/USB3.0-Device-Controller) (лицензия не указана).

Работа с подмодулями:

```sh
git submodule update --init --depth 1          # скачать все
git submodule update --remote au/orbtrace      # обновить один до свежего коммита
git submodule add --depth 1 <url> au/<имя>     # добавить новый
```

У `mcu-sdk` свои вложенные подмодули; для трассы нужен только OpenOCD, он лежит прямо в репозитории.
Компилятор в SDK закреплён на Windows-ветке, на Linux его надо переключить на тег `*_lin` той же версии:

```sh
git -C au/mcu-sdk submodule update --init --depth 1 Drivers/HAL Drivers/BASIS   # если нужен HAL
rmdir au/mcu-sdk/Tools/toolchain   # пустой каталог подмодуля (в SDK он на ветке Windows); клон — 1,7 ГБ
git clone --depth 1 -b 2.4.0_lin https://gitflic.ru/project/baikalelectronics/toolchain-riscv.git \
    au/mcu-sdk/Tools/toolchain     # у SDK для него ignore=all — git не считает это изменением
```

Без тулчейна прошивка `tools/slogic/trace/beu1000/fw` собирается компилятором из распакованного архива
SDK в `~/.local/opt/baikal-mcu-sdk-2.3.0`.

