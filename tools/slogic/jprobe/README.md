# tools/slogic/jprobe — прозвонка SLogic16U3 через JTAG

Образ для SRAM GW5AT-15 (корпус MG132): 36 выводов-кандидатов — только входы без подтяжки, выходов
нет. Результат читается пользовательским регистром JTAG, поэтому флеш не нужна, а прибор
возвращается к заводскому приложению передёргиванием питания. Методика — [`doc/slogic-pinmap-method.md`](../../../doc/slogic-pinmap-method.md),
журнал опытов — [`doc/slogic-pinmap-journal.md`](../../../doc/slogic-pinmap-journal.md).

| Файл | Что |
|---|---|
| [`jprobe.v`](jprobe.v) | окна по 2^26 тактов OSCB подряд (2,24 с: OSCB на деле ~30 МГц, а не 52,5); на каждом входе — счёт фронтов «как есть» и после фильтра помех (16 тактов), уровни. Кадр — в ER1 (`0x42`), константа `0x12345678` — в ER2 (`0x43`) |
| [`jprobe.cst`](jprobe.cst) | кандидаты MG132 из `IDE/data/device/GW5AT-15B/MBGA132.json`, входы `LVCMOS15UD33` (низкий порог на банке 3,3 В — после делителей прибора сигнал 3 В даёт 1,42 В); K3/K2 не влезли в лимит I/O — для них заменить ими H3/H2 |
| [`gowin.tcl`](gowin.tcl) | `gw_sh gowin.tcl` в копии папки на диске C: (Gowin EDA 1.9.12.04) |
| [`tb.v`](tb.v) | симуляция с заглушками `OSCB` и `GW_JTAG`: `iverilog -g2012 -o tb tb.v jprobe.v && vvp tb` |
| [`jprobe.py`](jprobe.py) | чтение кадра через OpenOCD + FT2232H, опознание каналов по частоте |
| [`bench.py`](bench.py) | опыты с источником через постоянный OpenOCD на ST-LINK (`tcl_port 6667`): `window`, `gate PD0 …`, `static`, `hold 0/1`, `run` |
| `jprobe.fs` | готовый образ, v2, входы `LVCMOS15UD33` (sha256 `019b9445…0a3c`) |

```sh
O=~/.local/opt/oss-cad-suite/bin
$O/openFPGALoader -c ft2232 -m tools/slogic/jprobe/jprobe.fs   # только SRAM
python3 tools/slogic/jprobe/jprobe.py --er2                    # канал JTAG: 12345678
python3 tools/slogic/jprobe/jprobe.py -n 2                     # первый кадр после загрузки — переходный
```

Окружение, схема стенда и порядок сеанса — в [журнале](../../../doc/slogic-pinmap-journal.md#пререквизиты).

FT2232H канал A — JTAG разъёма (TCK ADBUS0, TDI ADBUS1, TDO ADBUS2, TMS ADBUS3).

## GW_JTAG в Gowin EDA

- Порты верхнего уровня `tck_pad_i`, `tms_pad_i`, `tdi_pad_i`, `tdo_pad_o` подключены к одноимённым
  выводам примитива и **не** описаны в `.cst`: размещение само ставит их на JTAG (G2 G3 J3 J2).
  Без них синтез выкидывает примитив вместе со всей логикой.
- Эти 4 порта идут в лимит 40 обычных I/O.
- На железе кадр приходит с одним лишним битом впереди; `jprobe.py` ищет метку `RLNJ`.
- `drscan` с несколькими полями в OpenOCD 0.12+dev возвращает только первое — кадр читается одним полем.
