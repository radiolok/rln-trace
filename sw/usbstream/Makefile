# usbstream: host receiver for fw/ch569/usbstream.
#   make            # ./usbstream
#   make test       # parser test, no device needed
# Without libusb-1.0-0-dev pass the paths by hand:
#   make LIBUSB_CFLAGS=-I<dir with libusb.h> LIBUSB_LIBS=/usr/lib/x86_64-linux-gnu/libusb-1.0.so.0

CC      ?= cc
CFLAGS  ?= -O2 -g
# required flags stay separate so that CFLAGS can be overridden on the command line
REQ     := -std=c11 -D_POSIX_C_SOURCE=200809L -Wall -Wextra -Werror -I../../fw/ch569/usbstream

LIBUSB_CFLAGS ?= $(shell pkg-config --cflags libusb-1.0)
LIBUSB_LIBS   ?= $(shell pkg-config --libs libusb-1.0)

all: usbstream

usbstream: usbstream.c check.c check.h ../../fw/ch569/usbstream/stream.h
	$(CC) $(REQ) $(CFLAGS) $(LIBUSB_CFLAGS) -o $@ usbstream.c check.c $(LIBUSB_LIBS)

test_check: test_check.c check.c check.h ../../fw/ch569/usbstream/stream.h
	$(CC) $(REQ) $(CFLAGS) -o $@ test_check.c check.c

test: test_check
	./test_check

clean:
	rm -f usbstream test_check

.PHONY: all test clean
