# USB2-ядро Daisho

Пакетный и протокольный уровни USB 2.0 device из проекта [Daisho](https://github.com/enjoy-digital/daisho)
(Marshall H., Great Scott Gadgets, 2012–2013, упрощённая BSD — `LICENSE.txt`). Взято с коммита
`27bc20c3` зеркала enjoy-digital, папка `core/usb2`. Слой ULPI (`usb2_ulpi.v`) не взят, вместо него
`../usb2_utmi.v`: Gowin SoftPHY отдаёт UTMI. ПЗУ дескрипторов (`usb2_descrip_rom.v`) и смещения
(`usb_descrip.vh`) генерирует `../mkdesc.py daisho`.

Правки помечены `// rln:`:

| Файл | Что |
|---|---|
| `usb2_top.v` | ULPI → UTMI (`usb2_utmi`); наружу — состояние шины, число чирпов хоста, импульс сброса шины |
| `usb2_ep0.v` | разбирать только SETUP (8 байт): ZLP стадии статуса заново исполнял прошлый запрос; GET_STATUS → два нулевых байта; неизвестные запросы → ZLP вместо вечного NAK; SET_CONFIGURATION, SET_INTERFACE, CLEAR_FEATURE сбрасывают data toggle EP1/EP2 |
| `usb2_ep0.v`, `usb2_protocol.v`, `usb2_top.v` | vendor-запросы: наружу `wIndex`; запрос к хосту отвечает стадией данных IN — одним пакетом до 64 байт из внешнего порта `vend_rd_addr`/`vend_rd_data` (задержка в такт, как у ПЗУ) |
| `usb2_ep.v`, `usb2_protocol.v` | вход `toggle_rst` |
| `usb2_packet.v` | сброс `out_byte_crc`, `out_byte_buf`, `out_latch` (в симуляции X в первом ответе) |
| `usb2_ep0in_ram.v` | чтение `<=` вместо `=` (гонка в симуляции, синтез тот же) |
| все | объявления перенесены до использования (Quartus терпел, iverilog — нет) |

Сброс шины теперь обнуляет адрес устройства (пакетный и протокольный уровни в сбросе, пока идёт сброс
и чирп). В оригинале адрес сбрасывался только при пропадании VBUS.

Ограничения ядра, которые остались: ответ EP0 — один пакет (дескрипторы до 63 байт, vendor IN до 64);
стадии данных OUT у vendor-запросов нет — значение передаётся в wValue/wIndex; STALL нет; OUT-точка не следит за data
toggle; конфигурация одна, bulk по 512 (в FS Linux поправит до 64 с предупреждением).
