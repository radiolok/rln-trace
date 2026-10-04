# tools — вспомогательные скрипты

| Папка | Что |
|---|---|
| [`schgen/`](schgen/) | Генератор схемы зонда B для KiCad 9, проверка связности, PNG-превью |

Запуск генератора (нужны Python 3 и Pillow, а также библиотеки символов KiCad 5 —
из них берутся проверенные распиновки стандартных микросхем):

```sh
git clone --depth 1 https://github.com/KiCad/kicad-symbols ~/kicad-symbols
python3 tools/schgen/run.py     # перезапишет hw/probe-b/kicad
```

Свою папку с библиотеками можно указать переменной `KICAD5_SYMBOLS`.
