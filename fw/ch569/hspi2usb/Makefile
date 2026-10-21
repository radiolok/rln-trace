# hspi2usb: packets from the FPGA over HSPI -> USB3 bulk EP2 IN.
# Build rules, boards and the toolchain: ../common/app.mk.
#   make HSPI_WIDTH=16      # bus width, 8 on the bench (default), 16 on probe B

APP        := hspi2usb
HSPI_WIDTH ?= 8
APP_SRCS   := main.c bridge.c usb_cmd.c ../common/app_usb.c
APP_DEFS   := -DBRIDGE_HSPI_WIDTH=$(HSPI_WIDTH) -I../usbstream

include ../common/app.mk
