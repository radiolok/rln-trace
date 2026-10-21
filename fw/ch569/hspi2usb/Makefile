# hspi2usb: packets from the FPGA over HSPI -> USB3 bulk EP2 IN.
# Build rules, boards and the toolchain: ../common/app.mk.
#   make HSPI_WIDTH=8       # bus width: 16 on the bench and probe B (default), 8 or 32

APP        := hspi2usb
HSPI_WIDTH ?= 16
APP_SRCS   := main.c bridge.c usb_cmd.c ../common/app_usb.c
APP_DEFS   := -DBRIDGE_HSPI_WIDTH=$(HSPI_WIDTH) -I../usbstream

include ../common/app.mk
