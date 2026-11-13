# BE-U1000 probes: the same memory map, CSR and trigger checks on the QEMU model and on silicon.
#   make qemu QEMU=~/qemu-beu1000/build/qemu-system-riscv32   - model (machine evu-ba)
#   make hw   RLN_BEU_USB=1-1                                 - board via the persistent OpenOCD (../ocd.py)
# Toolchain as in ../fw: au/mcu-sdk submodule or the SDK 2.3.0 archive.
SUB := $(abspath ../../../../../au/mcu-sdk/Tools/toolchain/bin)
ARC := $(HOME)/.local/opt/baikal-mcu-sdk-2.3.0/Tools/toolchain/riscv32-none-elf/bin
TCBIN ?= $(if $(wildcard $(SUB)/riscv32-none-elf-gcc),$(SUB),$(ARC))
CROSS = $(TCBIN)/riscv32-none-elf-
AFLAGS = -march=rv32ima_zicsr -mabi=ilp32 -nostdlib -nostartfiles
QEMU ?= qemu-system-riscv32
OCD = python3 ../ocd.py

all: qemu.elf core0.bin core2.bin

qemu.elf: qemu.S
	$(CROSS)gcc $(AFLAGS) -Wl,-Ttext=0xa0000000 -o $@ $<    # eFLASH, model reset vector

core0.elf: core0.S
	$(CROSS)gcc $(AFLAGS) -Wl,-Ttext=0x40010000 -o $@ $<    # TCMA Core 0

core2.elf: core2.S
	$(CROSS)gcc $(AFLAGS) -Wl,-Ttext=0x40008000 -o $@ $<    # Core 2 TCMB (its own address)

%.bin: %.elf
	$(CROSS)objcopy -O binary $< $@

qemu: qemu.elf
	(sleep 3; echo 'xp /16wx 0x70000000'; echo 'xp /40wx 0x70000100'; echo 'xp /16wx 0x70000300'; echo quit) | \
	$(QEMU) -M evu-ba -display none -serial null -monitor stdio -device loader,file=qemu.elf \
		-d int,unimp,guest_errors -D qemu.log | grep '^7000'

# Core 0: code in TCMA, results in SRAM. Core 2: code in its TCMB via the Core 0 window (0x70010000);
# SYSCR0: TCM arbiter and logic first (bits 5, 6), then the vector in SYSCR2 and the core (bit 4);
# the debugger holds Core 2 at its vector, so resume it via targets CORE_2.
# Core 2 must still be in reset: rerun only after a fresh OpenOCD (../ocd.py --stop resets the board).
hw: core0.bin core2.bin
	$(OCD) "halt; write_memory 0x70000000 32 [lrepeat 1024 0]; load_image $(CURDIR)/core0.bin 0x40010000 bin; \
		resume 0x40010000; sleep 500; halt; \
		puts \"core0 [read_memory 0x70000000 32 32]\"; puts \"fault0 [read_memory 0x700000e0 32 3]\"; \
		puts \"probe0 [read_memory 0x70000100 32 36]\"; \
		set s0 [read_memory 0x14000018 32 1]; write_memory 0x14000018 32 [expr {(\$$s0 & ~0x10) | 0x60}]; \
		write_memory 0x7000F800 32 [lrepeat 64 0]; load_image $(CURDIR)/core2.bin 0x70010000 bin; \
		write_memory 0x14000020 32 0x40008000; write_memory 0x14000018 32 [expr {\$$s0 | 0x70}]; \
		catch {CORE_2 arp_examine}; targets CORE_2; halt; resume; sleep 300; halt; targets CORE_0; \
		puts \"core2 [read_memory 0x7000F800 32 28]\""

clean:
	rm -f *.elf *.bin qemu.log

.PHONY: all qemu hw clean
