# SLogic16U3 — направление A

Скелет верхнего модуля адаптера трассы на Sipeed SLogic16U3 (GW5AT-LV15MG132C1/I0). Логики пока нет:
зафиксированы выводы и настройки входов, найденные прозвонкой 2026-10-25
([журнал](../../../doc/slogic-pinmap-journal.md), [`tools/slogic/jprobe`](../../../tools/slogic/jprobe/)).

| Файл | Что |
|---|---|
| [`top.sv`](top.sv) | `top_slogic16u3`: входы `ch[15:0]`, в шапке — распиновка, входной каскад, предложенный порт трассы, запретные выводы |
| [`slogic16u3.cst`](slogic16u3.cst) | шарики CH0–CH15, `LVCMOS15UD33`, без подтяжек |
| [`gowin.tcl`](gowin.tcl) | сборка в Gowin EDA, multiboot на 0x800000 (кнопка MODE возвращает DFU) |

```sh
verilator --lint-only -Wall -Wno-DECLFILENAME --top-module top_slogic16u3 gw/boards/slogic16u3/top.sv
B=/mnt/c/Users/Public/rln-slogic16u3; rm -rf $B; mkdir -p $B; cp gw/boards/slogic16u3/* $B/
(cd $B && /mnt/c/Gowin/Gowin_V1.9.12.04_x64/IDE/bin/gw_sh.exe gowin.tcl)
```

Опытные образы — только в SRAM (`openFPGALoader -c ft2232 -m`), во флеш — через
`tools/slogic/slogic_dfu.py write` с бэкапом.
