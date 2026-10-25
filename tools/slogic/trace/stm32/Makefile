# make; прошивка через OpenOCD (ST-LINK V2J14 встроенный в F4-Discovery, pyOCD его не берёт):
#   openocd -f board/stm32f4discovery.cfg -c "program trace.elf verify reset exit"
CC = $(HOME)/.local/opt/xpack-arm-none-eabi-gcc-15.2.1-1.1/bin/arm-none-eabi-gcc
CFLAGS = -mcpu=cortex-m4 -mthumb -Os -Wall -Wextra -ffreestanding -nostdlib

trace.elf: main.c link.ld
	$(CC) $(CFLAGS) -T link.ld -o $@ main.c

clean:
	rm -f trace.elf
