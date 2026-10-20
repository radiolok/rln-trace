# usbstream: CH569 streams self-test blocks over USB3 bulk EP2 IN, no FPGA needed.
#
# Toolchain: xPack riscv-none-elf-gcc 12.2.0-1 from hydrausb3 (understands
# interrupt("WCH-Interrupt-fast"); stock GCC builds a broken image).
#   make                  # build/usbstream.{elf,bin,hex}
#   make flash            # wchisp, board in bootloader (Download held at power-on)

CROSS    ?= riscv-none-elf-
CC       := $(CROSS)gcc
OBJCOPY  := $(CROSS)objcopy
SIZE     := $(CROSS)size

ROOT     := ../../..
HYDRA    := $(ROOT)/au/hydrausb3_fw
BSP      := $(HYDRA)/wch-ch56x-bsp
EXAMPLE  := $(HYDRA)/HydraUSB3_USB

# RAMX 96 KB to match the chip config (USER_MEM = RAMX 96KB + ROM 32KB)
LDSCRIPT := $(EXAMPLE)/.ld
# with that USER_MEM only 32 KB of code is executable
CODE_MAX ?= 32768

BUILD    := build
TARGET   := $(BUILD)/usbstream

SRCS := main.c stream.c \
        usb/CH56x_usb30_devbulk.c usb/CH56x_usb20_devbulk.c \
        $(BSP)/usb/usb_devbulk/CH56x_usb_devbulk_desc_cmd.c \
        $(EXAMPLE)/User/usb_cmd.c \
        $(wildcard $(BSP)/rvmsis/*.c) \
        $(wildcard $(BSP)/drv/*.c) \
        $(BSP)/board/hydrausb3_v1.c
ASRCS := $(BSP)/startup/startup_CH56x.S

INCLUDES := -I. -I$(BSP)/rvmsis -I$(BSP)/drv -I$(BSP)/board \
            -I$(BSP)/usb/usb_devbulk -I$(EXAMPLE)/User

ARCH    := -march=rv32imac_zicsr -mabi=ilp32 -msmall-data-limit=8
CFLAGS  := $(ARCH) -O3 -std=gnu99 -fmessage-length=0 -fsigned-char \
           -ffunction-sections -fdata-sections $(INCLUDES) -MMD -MP
LDFLAGS := $(ARCH) -T $(LDSCRIPT) -nostartfiles -Wl,--gc-sections \
           -Wl,--print-memory-usage -Wl,-Map,$(TARGET).map \
           --specs=nano.specs --specs=nosys.specs

# objects mirror source paths under build/, ../ becomes up/
obj = $(BUILD)/$(subst ../,up/,$(basename $(1))).o
OBJS := $(foreach s,$(SRCS) $(ASRCS),$(call obj,$(s)))

all: $(TARGET).bin $(TARGET).hex

define compile
$(call obj,$(1)): $(1)
	@mkdir -p $$(@D)
	$$(CC) $$(CFLAGS) $(2) -c -o $$@ $$<
endef
$(foreach s,$(SRCS),$(eval $(call compile,$(s),)))
$(foreach s,$(ASRCS),$(eval $(call compile,$(s),-x assembler-with-cpp)))

$(TARGET).elf: $(OBJS)
	$(CC) $(LDFLAGS) -o $@ $(OBJS)
	@$(SIZE) $@

$(TARGET).bin: $(TARGET).elf
	$(OBJCOPY) -O binary $< $@
	@n=$$(stat -c %s $@); echo "code image $$n of $(CODE_MAX) bytes"; \
	  if [ $$n -gt $(CODE_MAX) ]; then echo "code image does not fit"; rm -f $@; exit 1; fi

$(TARGET).hex: $(TARGET).elf
	$(OBJCOPY) -O ihex $< $@

flash: $(TARGET).bin
	wchisp flash $<

clean:
	rm -rf $(BUILD)

-include $(OBJS:.o=.d)

.PHONY: all flash clean
