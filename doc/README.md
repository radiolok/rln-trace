# doc — документация

Заметки, результаты замеров, протоколы испытаний. Архитектура зонда — в [`../hw/README.md`](../hw/README.md).


| Документ | Что внутри |
|---|---|
| [bench.md](bench.md) | Отладочный стенд: Tang Nano 20K + CH569, ПК, USB-коммутатор, SLogic16U3, цель STM32F4-Discovery, FT2232H |
| [ch569-hspi.md](ch569-hspi.md) | HSPI CH569 по даташиту: линии, пакет, обмен, что придётся мерить на стенде (параметры CRC, задержки) |
| [ch32h417-uhsif.md](ch32h417-uhsif.md) | CH32H417 UHSIF: протокол шины со стороны ПЛИС, состав `libUHSIF.a`, карта регистров и дескрипторов по трассам spike |
| [uhsif-re-method.md](uhsif-re-method.md) | Методика вскрытия `libUHSIF.a`: перелинковка, Ghidra, опознание опкодов `xw2p2`, spike на Unicorn, грабли |
