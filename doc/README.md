# doc — документация

Заметки, результаты замеров, протоколы испытаний. Архитектура зонда — в [`../hw/README.md`](../hw/README.md).


| Документ | Что внутри |
|---|---|
| [bench.md](bench.md) | Отладочный стенд: Tang Nano 20K + CH569, ПК, USB-коммутатор, SLogic16U3, цель STM32F4-Discovery, FT2232H |
| [debug-plan.md](debug-plan.md) | План отладочной части: JTAG, SWD, SWO, cJTAG и Spy-Bi-Wire по этапам D0–D7 — стенд Tang Nano 20K, CH569, SLogic16U3 |
| [ch569-hspi.md](ch569-hspi.md) | HSPI CH569 по даташиту: линии, пакет, обмен, что придётся мерить на стенде (параметры CRC, задержки) |
| [ch32h417-uhsif.md](ch32h417-uhsif.md) | CH32H417 UHSIF: протокол шины со стороны ПЛИС, состав `libUHSIF.a`, карта регистров и дескрипторов по трассам spike |
| [slogic-pinmap-method.md](slogic-pinmap-method.md) | SLogic16U3: методика прозвонки входов на стенде (STM32 → SLogic → FT2232H), правила безопасности, этапы |
| [slogic-pinmap-journal.md](slogic-pinmap-journal.md) | SLogic16U3: журнал прозвонки — попытки, данные, распиновка CH1–CH14, заметки для статьи |
| [slogic-trace-journal.md](slogic-trace-journal.md) | SLogic16U3: журнал приёма трассы STM32F407 (TPIU, ITM, ETM) до 57 МГц TRACECLK |
| [beu1000-trace-journal.md](beu1000-trace-journal.md) | BE-U1000 (RISC-V, EVU-BA-2.5): журнал приёма трассы N-Trace через PIB — регистры трассера, выбор выводов, протокол MSEO |
| [uhsif-re-method.md](uhsif-re-method.md) | Методика вскрытия `libUHSIF.a`: перелинковка, Ghidra, опознание опкодов `xw2p2`, spike на Unicorn, грабли |
