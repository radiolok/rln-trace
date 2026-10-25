# Трассер BE-U1000 по SBA: такт, выводы, PIB, кодер. Подключается после openocd.cfg.
# Адреса и поля — BE-U1000 Reference Manual v1.3.0, гл. 5 (CRU) и 16 (Tracer).

set CRU_CLKSEL  0x14000000
set CRU_PLLSET  0x14000004
set CRU_IOAFCR2 0x14000044
set CRU_IODSCR1 0x14000058
set CRU_CLKCR1  0x14000084
set TR_TE       0x15104000
set TR_RAM      0x15105000
set TR_PIB      0x15106000
set TRACE_SEL   0x4000A014

proc rd {a} { return [read_memory $a 32 1] }
proc wr {a v} { write_memory $a 32 $v }
proc rmw {a clr set} { wr $a [expr {([rd $a] & ~$clr) | $set}] }

# Ждать, пока поле прочитается как записано (tr??Active «может занять сколько угодно»).
proc wait_bits {a mask val} {
	for {set i 0} {$i < 100} {incr i} {
		if {([rd $a] & $mask) == $val} { return }
		sleep 1
	}
	error [format "регистр %#x: ждали %#x под маской %#x, читается %#x" $a $val $mask [rd $a]]
}

# PLL от CLKI 25 МГц: Fout = 25 * nf / (nr * od), VCO = 25 * nf / nr. Как QSPI_clk_init в SDK,
# но такты ядер и периферии не трогаем — PLL нужен только делителю tclk.
proc pll {nr nf od} {
	global CRU_CLKSEL CRU_PLLSET
	rmw $CRU_CLKSEL 0x1 0x0                ;# REFCLKSEL = C0 (CLKI)
	rmw $CRU_PLLSET 0x400000 0             ;# BYPASS = 0
	rmw $CRU_PLLSET 0 0x1000000            ;# RESET = 1
	rmw $CRU_PLLSET 0xFFFFF [expr {0x200000 | ($nf - 1) << 14 | ($od - 1) << 10 | ($nf - 1) << 4 | ($nr - 1)}]
	rmw $CRU_PLLSET 0x1000000 0            ;# RESET = 0
	sleep 1
}

# Ядра на PLL / cdiv, шина и периферия (hclk, pclk0..2) — на PLL / pdiv; таймерные 1 МГц — под них.
# Как QSPI_clk_init в SDK, но без перезапуска PLL (он уже настроен procedure pll).
proc core {cdiv pdiv} {
	global CRU_CLKDIV_DIV1 CRU_CLK_SRC_PLL
	set cc [expr {$cdiv == 1 ? 0 : ($cdiv - 1) << 1}]
	set pc [expr {$pdiv == 1 ? 0 : ($pdiv - 1) << 1}]
	foreach p {PCLK0 PCLK1 PCLK2 HCLK} {
		___CRU_Set${p}Prescaler $pc; ___CRU_${p}Prescaler_Enable; ___CRU_Set${p}Source 1
	}
	___CRU_SetCCLKPrescaler $cc; ___CRU_CCLKPrescaler_Enable; ___CRU_SetCCLKSource 1
	set f [expr {200 / $cdiv}]
	___CRU_SetCCLK1MHzPrescaler [expr {$f - 1}]
	___CRU_SetHCLK1MHzPrescaler [expr {200 / $pdiv - 1}]
}

# tclk — такт трассера (макс. 100 МГц). src: 0 sys_clk, 1 PLL / div, 2 alt_clk.
# div: целое 1..16 или дробное n.5 (1.5..15.5), как поле TCLKDIV.
proc tclk {src {div 1}} {
	global CRU_CLKSEL CRU_CLKCR1
	if {$div == 1} {
		set code 0
	} elseif {$div == int($div)} {
		set code [expr {(int($div) - 1) << 1}]
	} else {
		set code [expr {(int($div - 1.5) << 1) | 1}]
	}
	rmw $CRU_CLKCR1 0x3F [expr {0x20 | $code}]
	rmw $CRU_CLKSEL 0x1800 [expr {$src << 11}]
}

# PB0..PB3 = PIB_D[0..3], PB4 = PIB_CLK (АФ4); ds — крутизна 0..3 (4,5..18 мА).
proc pins {{ds 0}} {
	global CRU_IOAFCR2 CRU_IODSCR1
	rmw $CRU_IOAFCR2 0xFFFFF 0xCCCCC
	set m 0; set v 0
	for {set i 0} {$i < 5} {incr i} {
		set m [expr {$m | 3 << 2 * $i}]
		set v [expr {$v | $ds << 2 * $i}]
	}
	rmw $CRU_IODSCR1 $m $v
}

# Порядок по Trace Control Interface: сброс → Active → Enable (приёмники до кодера).
proc pib_on {} {
	global TR_PIB
	wr $TR_PIB 0; wait_bits $TR_PIB 1 0
	wr $TR_PIB 1; wait_bits $TR_PIB 1 1
	wr $TR_PIB 3; wait_bits $TR_PIB 2 2
}

# mode: 3 branch trace (BTM), 6 branch history (HTM) — как в спецификации; RM v1.3.0 пишет 3/2,
# но 2 не держится (WARL: 0..2 → 0, 3..5 → 3, 6..7 → 6).
# sync: 0 выкл, 1 по сообщениям, 2 по тактам ядра, 3 по полусловам; период 2^(syncmax+4).
# trig = 1: trTeInstTracing включают и выключают триггеры отладочного модуля (trig_set), сам
# Tracing не ставится.
proc te_on {{mode 3} {sync 1} {syncmax 4} {stall 0} {trig 0}} {
	global TR_TE
	wr $TR_TE 0; wait_bits $TR_TE 1 0
	wr $TR_TE 1; wait_bits $TR_TE 1 1
	set c [expr {1 | $mode << 4 | $trig << 11 | $stall << 13 | $sync << 16 | $syncmax << 20}]
	wr $TR_TE $c
	wr $TR_TE [expr {$c | 2}]; wait_bits $TR_TE 2 2
	if {!$trig} { wr $TR_TE [expr {$c | 6}] }
}

# Триггер ядра 0 (Debug Spec, mcontrol): по выполнению адреса в M-режиме — действие act:
# 2 trace-on, 3 trace-off, 4 trace-notify. Ядро на время записи CSR останавливается.
proc trig_set {idx addr act} {
	set run [expr {[CORE_0 curstate] eq "running"}]
	if {$run} { halt }
	reg tselect $idx
	reg tdata1 0
	reg tdata2 $addr
	reg tdata1 [format 0x%x [expr {2 << 28 | $act << 12 | 1 << 6 | 1 << 2}]]
	puts "trigger $idx: tdata1 [lindex [reg tdata1] end] tdata2 [lindex [reg tdata2] end]"
	if {$run} { resume }
}

proc trig_clear {} {
	set run [expr {[CORE_0 curstate] eq "running"}]
	if {$run} { halt }
	for {set i 0} {$i < 4} {incr i} { reg tselect $i; reg tdata1 0 }
	if {$run} { resume }
}

proc te_off {} {
	global TR_TE
	rmw $TR_TE 0x6 0
	wait_bits $TR_TE 0xA 0x8
}

# Открытие по Trace Control Interface: каждое слово компонента — записать все единицы, прочитать,
# вернуть прежнее. Печатает только слова, где что-то читается или держится. Кодер на время — Active,
# без Enable. base: $TR_TE, $TR_PIB, $TR_RAM; from/to — смещения.
proc discover {base {from 0} {to 0xFFC}} {
	set ctl [rd $base]
	wr $base 1
	for {set off $from} {$off <= $to} {incr off 4} {
		set a [expr {$base + $off}]
		set old [rd $a]
		if {$off != 0} { wr $a 0xFFFFFFFF }
		set ones [rd $a]
		if {$off != 0} { wr $a $old }
		if {$old != 0 || $ones != 0} {
			puts [format "  +%#05x: было %#010x, после записи единиц %#010x" $off $old $ones]
		}
	}
	wr $base $ctl
}

proc tr_status {} {
	global CRU_CLKSEL CRU_PLLSET CRU_CLKCR1 CRU_IOAFCR2 CRU_IODSCR1 TR_TE TR_PIB TR_RAM
	puts [format "CLKSEL %#x PLLSET %#x CLKCR1 %#x IOAFCR2 %#x IODSCR1 %#x" \
		[rd $CRU_CLKSEL] [rd $CRU_PLLSET] [rd $CRU_CLKCR1] [rd $CRU_IOAFCR2] [rd $CRU_IODSCR1]]
	puts [format "TE %#x IMPL %#x FEAT %#x  PIB %#x  RAM %#x" \
		[rd $TR_TE] [rd [expr {$TR_TE + 4}]] [rd [expr {$TR_TE + 8}]] [rd $TR_PIB] [rd $TR_RAM]]
}
return
