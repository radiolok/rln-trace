# Стек USB 3.0 К. Иды (ciniml)

Файлы взяты без изменений из [ciniml/fpga_samples](https://github.com/ciniml/fpga_samples)
(К. Ида, Boost Software License 1.0 — [LICENSE-BSL-1.0](LICENSE-BSL-1.0)), коммит `41354eb`:

| Папка | Откуда | Что |
|---|---|---|
| `rtl/usb3/` | `rtl/usb3/` | стек USB 3.0 на [Veryl](https://veryl-lang.org): LTSSM, link, разбор и сборка пакетов, EP0 и EP1 (`usb3_device`), ПЗУ дескрипторов; тесты (`veryl test`, Verilator), заметки по спецификации `doc/spec_notes.md` |
| `board/top.v`, `pll_ref125.v`, `jtag_status.v`, `pins.cst`, `timing.sdc` | `eda/slogic16u3_usb3/src/slogic16u3/` | эталонный верх для SLogic16U3: EP1 петля / PRBS15, состояние в ER1 GW_JTAG |
| `board/serdes.csr` | `…/usb3_ln0/serdes.csr` | статическая настройка квада Q0 под USB 3.0 PHY (линия 0, QPLL0, REFCLK0 125 МГц) для `set_csr` |
| `board/serdes_gui.toml` | `…/usb3_ln0/serdes_tmp.toml` | toml, из которого GUI Gowin сделал этот csr (для справки: `serdes_toml_to_csr_15k.exe` его не принимает) |
| `board/README.ja.md` | `eda/slogic16u3_usb3/README.md` | описание образа и находки по PHY Gowin (японский) |

Зашифрованные IP Gowin (USB 3.0 PHY, арбитр upar) отсюда не взяты: `build.sh` генерирует их из установленной
Gowin EDA (`ip/`). SystemVerilog из `.veryl` делает `veryl build` при сборке, в git он не попадает.
