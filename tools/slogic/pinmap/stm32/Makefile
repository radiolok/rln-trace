# make && make flash  (ST-LINK встроенный в F4-Discovery, pyOCD)
CC = $(HOME)/.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/bin/arm-none-eabi-gcc
CFLAGS = -mcpu=cortex-m4 -mthumb -Os -Wall -Wextra -ffreestanding -nostdlib

pattern.elf: main.c link.ld
	$(CC) $(CFLAGS) -T link.ld -o $@ main.c

flash: pattern.elf
	pyocd flash -t stm32f407vg $<

clean:
	rm -f pattern.elf
