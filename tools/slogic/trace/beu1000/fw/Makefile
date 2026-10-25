# Тулчейн — из Baikal MCU SDK 2.3.0.
SDK ?= $(HOME)/.local/opt/baikal-mcu-sdk-2.3.0
CROSS = $(SDK)/Tools/toolchain/riscv32-none-elf/bin/riscv32-none-elf-
CFLAGS = -march=rv32imac_zicsr -mabi=ilp32 -O2 -g -ffreestanding -nostdlib -Wall

trace.elf: start.S main.c link.ld
	$(CROSS)gcc $(CFLAGS) -T link.ld -o $@ start.S main.c
	$(CROSS)objdump -d $@ > trace.lst
	$(CROSS)size $@

clean:
	rm -f trace.elf trace.lst
