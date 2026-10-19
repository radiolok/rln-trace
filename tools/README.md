# tools — вспомогательные скрипты

| Папка | Что |
|---|---|
| [`schgen/`](schgen/) | Генератор схемы зонда B для KiCad 9, проверка связности, PNG-превью |
| [`uhsif-re/`](uhsif-re/) | Разбор `libUHSIF.a` (CH32H417): перелинковка, дизассемблер с Zb*/XW, spike на Unicorn с журналом MMIO, сверка открытого драйвера `fw/uhsif` с библиотекой (`compare.py`). Методика — [`doc/uhsif-re-method.md`](../doc/uhsif-re-method.md) |
| [`diagrams/`](diagrams/) | Структурные схемы для документации (SVG в `hw/img/`): `python3 tools/diagrams/make_diagrams.py`. Схемы CH32H417/UHSIF: `uhsif_diagrams.py` (временные диаграммы — WaveDrom, нужен Node.js для `npx wavedrom-cli`), оригиналы WCH для сверки рядом с картинками (`*.orig*.png`, не в git): `uhsif_originals.py` (PyMuPDF) |

Запуск генератора (нужны Python 3 и Pillow, а также библиотеки символов KiCad 5 —
из них берутся проверенные распиновки стандартных микросхем):

```sh
git clone --depth 1 https://github.com/KiCad/kicad-symbols ~/kicad-symbols
python3 tools/schgen/run.py     # перезапишет hw/probe-b/kicad
```

Свою папку с библиотеками можно указать переменной `KICAD5_SYMBOLS`.

Разбор `libUHSIF.a` (библиотека скачивается из openwch/ch32h417, результаты — в `tools/uhsif-re/build/`):

```sh
python3 -m venv ~/.venv/uhsif && ~/.venv/uhsif/bin/pip install -r tools/uhsif-re/requirements.txt
PY=~/.venv/uhsif/bin/python GHIDRA=~/ghidra_12.1.4_PUBLIC tools/uhsif-re/run.sh
```
