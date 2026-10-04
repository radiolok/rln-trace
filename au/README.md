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

Только как референс, без подмодуля: [SucréLA](https://gitlab.com/yannsionneau/SucreLA) (LGPL-2.1),
[USB3.0 Device Controller IP от Gowin](https://github.com/GOWIN-FPGA/USB3.0-Device-Controller) (лицензия не указана).

Работа с подмодулями:

```sh
git submodule update --init --depth 1          # скачать все
git submodule update --remote au/orbtrace      # обновить один до свежего коммита
git submodule add --depth 1 <url> au/<имя>     # добавить новый
```
