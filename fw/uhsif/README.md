# uhsif — открытый драйвер UHSIF для CH32H417

Замена закрытой `libUHSIF.a` из примеров WCH: те же функции (`UHSIF_GPIO_Init`, `UHSIF_Cfg`,
`UHSIF_Line_Cfg`, `UHSIF_Start`, `UHSIF_Trans_Cfg`, `UHSIF_Reg_Cfg`, `UHSIF_IRQHandler`), та же
структура `UHSIF_Para`, те же коды ошибок и колбэки `UHSIF_LineN_IN/OUT_Callback`. Пример WCH
(`ch32h417_uhsif.c`) собирается с ним без изменений: вместо `libUHSIF.a` подключаются `uhsif.c` и
сгенерированный `uhsif_tables.c`.

Как восстановлено поведение и что значат регистры — [`doc/ch32h417-uhsif.md`](../../doc/ch32h417-uhsif.md),
методика — [`doc/uhsif-re-method.md`](../../doc/uhsif-re-method.md).

## Таблицы

76 слов начальной настройки и микрокод генератора временных диаграмм — данные WCH, в
репозитории их нет. Их извлекает из вашей копии библиотеки
[`tools/uhsif-re/extract_tables.py`](../../tools/uhsif-re/extract_tables.py):

```sh
ar x libUHSIF.a                      # → lib.o
python3 -I tools/uhsif-re/extract_tables.py lib.o > uhsif_tables.c
```

## Проверка

`tools/uhsif-re/run.sh` собирает драйвер под RV32IMAC (`zig cc`) и прогоняет его и `libUHSIF.a`
в одном эмуляторе по одним сценариям (`compare.py`). Совпадают все обращения к периферии по
порядку, адресу и значению, коды возврата, колбэки с аргументами, итоговый режим каждого вывода и
содержимое DMA-дескрипторов. Сценарии: все сочетания режима, ремапов и ширины для
`UHSIF_GPIO_Init`; пример WCH; четыре канала в разных направлениях на 16 битах; первый и
повторный круг `UHSIF_Trans_Cfg`; все комбинации флагов в обработчике прерывания; ошибки
аргументов.

На железе драйвер ещё не проверен.

CI ([`.github/workflows/uhsif.yml`](../../.github/workflows/uhsif.yml)) на каждое изменение
`fw/uhsif` и `tools/uhsif-re`:

- собирает драйвер штатными тулчейнами — GCC `rv32imac`, GCC `rv32imac` + Zba/Zbb/Zbs, clang — в
  двух вариантах: тестовом (`-DUHSIF_NO_STDPERIPH`) и против заголовков StdPeriph WCH, с `-Werror`;
- прогоняет `run.sh`: скачивает `libUHSIF.a`, собирает драйвер и сравнивает его с библиотекой в
  spike. Любое расхождение роняет сборку.

Ревизия openwch/ch32h417 закреплена в workflow (`WCH_REF`). Ручной запуск с `wch_ref: main`
проверяет, не поменяла ли WCH библиотеку.

## Отличия от библиотеки

Только на неверных аргументах:

- `UHSIF_Line_Cfg` не принимает `line_num = 4` (библиотека принимает 0…4 и пишет за пределы `Stu[]`);
- `UHSIF_Trans_Cfg` проверяет `line_num` и возвращает `DEF_UHSIF_DATA_OVER_ERR` при
  `trans_size > Socket_Size`. Библиотека в первом круге молча оставляет прежнюю длину, а потом
  переполняет поле длины в дескрипторе.

Странности библиотеки на верных аргументах сохранены намеренно, пока их не проверим на железе:
OR в регистр канала поверх старого значения, взвод сокета 0 в каждом `UHSIF_Line_Cfg`, 16 `nop`
в начале `UHSIF_Start`, AF# как вход с подтяжкой.

## Сборка в прошивке

Нужны StdPeriph WCH (`ch32h417.h`, `GPIO_Init`, `RCC_*`) и тулчейн с поддержкой
`__attribute__((interrupt("WCH-Interrupt-fast")))` (GCC MounRiver). Без StdPeriph, для
тестов, — `-DUHSIF_NO_STDPERIPH`: тогда объявления берутся из самого `uhsif.c`, а обработчик
объявлен как обычное машинное прерывание.

DMA-дескрипторы `uhsif_dscr_in/out` должны лежать в `0x20000000…0x201FFFFF`: блок адресует их
16 битами по 32 байта.
