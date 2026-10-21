# Shared build rules for the rln-trace CH569 firmware. An application Makefile
# sets APP and APP_SRCS (and optionally APP_DEFS), then includes this file.
#
# Toolchain: xPack riscv-none-elf-gcc 12.2.0-1 from hydrausb3 (understands
# interrupt("WCH-Interrupt-fast"); stock GCC builds a broken image).
#   make                    # build/$(APP).{elf,bin,hex}, board WCH EVT
#   make BOARD=hydrausb3    # HydraUSB3 v1
#   make flash              # wch-ch56x-isp, board in bootloader (Download held at power-on)

CROSS    ?= riscv-none-elf-
CC       := $(CROSS)gcc
OBJCOPY  := $(CROSS)objcopy
SIZE     := $(CROSS)size

COMMON   := $(dir $(lastword $(MAKEFILE_LIST)))
ROOT     := $(COMMON)../../..
HYDRA    := $(ROOT)/au/hydrausb3_fw
BSP      := $(HYDRA)/wch-ch56x-bsp
EXAMPLE  := $(HYDRA)/HydraUSB3_USB

BOARD    ?= evt
BOARD_SRCS_evt       := $(COMMON)board/board_evt.c
BOARD_SRCS_hydrausb3 := $(COMMON)board/board_hydrausb3.c $(BSP)/board/hydrausb3_v1.c
ifeq ($(BOARD_SRCS_$(BOARD)),)
    $(error BOARD must be evt or hydrausb3)
endif

# RAMX 96 KB to match the chip config (USER_MEM = RAMX 96KB + ROM 32KB)
LDSCRIPT := $(EXAMPLE)/.ld
# with that USER_MEM only 32 KB of code is executable
CODE_MAX ?= 32768

BUILD    := build
TARGET   := $(BUILD)/$(APP)

SRCS := $(APP_SRCS) $(BOARD_SRCS_$(BOARD)) \
        $(COMMON)usb/CH56x_usb30_devbulk.c $(COMMON)usb/CH56x_usb20_devbulk.c \
        $(BSP)/usb/usb_devbulk/CH56x_usb_devbulk_desc_cmd.c \
        $(wildcard $(BSP)/rvmsis/*.c) \
        $(wildcard $(BSP)/drv/*.c)
ASRCS := $(BSP)/startup/startup_CH56x.S

INCLUDES := -I. -I$(COMMON) -I$(BSP)/rvmsis -I$(BSP)/drv -I$(BSP)/board \
            -I$(BSP)/usb/usb_devbulk -I$(EXAMPLE)/User

ARCH    := -march=rv32imac_zicsr -mabi=ilp32 -msmall-data-limit=8
CFLAGS  := $(ARCH) -O3 -std=gnu99 -fmessage-length=0 -fsigned-char \
           -ffunction-sections -fdata-sections $(INCLUDES) $(APP_DEFS) -MMD -MP
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
	wch-ch56x-isp -v -r -f $<

clean:
	rm -rf $(BUILD)

-include $(OBJS:.o=.d)

.PHONY: all flash clean
