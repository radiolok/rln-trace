# Тулчейн Baikal: из подмодуля au/mcu-sdk, если в нём развёрнут Tools/toolchain (Linux-тег, см.
# au/README.md; компилятор там в bin/), иначе — из распакованного архива SDK 2.3.0 в ~/.local/opt.
SUB := $(abspath ../../../../../au/mcu-sdk/Tools/toolchain/bin)
ARC := $(HOME)/.local/opt/baikal-mcu-sdk-2.3.0/Tools/toolchain/riscv32-none-elf/bin
TCBIN ?= $(if $(wildcard $(SUB)/riscv32-none-elf-gcc),$(SUB),$(ARC))
CROSS = $(TCBIN)/riscv32-none-elf-
CFLAGS = -march=rv32imac_zicsr -mabi=ilp32 -O2 -g -ffreestanding -nostdlib -Wall

trace.elf: start.S main.c link.ld
	$(CROSS)gcc $(CFLAGS) -T link.ld -o $@ start.S main.c
	$(CROSS)objdump -d $@ > trace.lst
	$(CROSS)size $@

clean:
	rm -f trace.elf trace.lst
