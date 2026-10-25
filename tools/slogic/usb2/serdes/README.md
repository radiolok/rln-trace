# SerDes Q0 для такта 125 МГц

Файлы взяты без изменений из [ciniml/fpga_samples](https://github.com/ciniml/fpga_samples)
(К. Ида, Boost Software License 1.0 — [LICENSE-BSL-1.0](LICENSE-BSL-1.0)), коммит `41354eb`,
папка `eda/slogic16u3_usb2/src/slogic16u3/serdes/`:

| Файл | Что |
|---|---|
| `serdes.v` | `SerDes_Top` из GowinModGen: Customized PHY, квад Q0, линия 0 |
| `customized_phy.v` | нетлист `Customized_PHY_Top` |
| `serdes.csr` | статическая настройка квада для `set_csr` |

Линия 0 на 1,25 Гбит/с: REFCLK0 (генератор 125 МГц, разрешение — D14) → CPLL0 → `tx_pcs_clkout`
125 МГц. Данные линии не используются — она нужна только ради такта, привязанного к генератору.
`CM*_LIFE_CLK` квада с генератором не связан (см. `doc/slogic-usb-journal.md`).
