# Gateware: SystemVerilog cores, Verilator testbenches, Yosys synthesis check.
#   make lint     # verilator --lint-only -Wall on every top
#   make test     # build and run every testbench
#   make synth    # yosys synth_gowin, resource report per top in build/synth/
#   make          # all of the above

VERILATOR ?= verilator
YOSYS     ?= yosys
BUILD     := build
JOBS      ?= $(shell nproc 2>/dev/null || echo 4)

# top -> sources
TPIU_SRCS  := cores/tpiu_align.sv cores/tpiu_deframer.sv cores/tpiu_idle.sv cores/tpiu_rx.sv
HSPI_SRCS  := cores/selftest_gen.sv cores/hspi_tx.sv cores/selftest_hspi.sv
TRACE_SRCS := $(TPIU_SRCS) cores/trace_capture.sv cores/async_fifo.sv cores/trace_rx.sv
HSPIRX_SRCS := cores/async_fifo.sv cores/hspi_rx.sv
UART_SRCS  := cores/uart_tx.sv cores/uart_hex.sv
STEP0_SRCS := $(HSPI_SRCS) $(HSPIRX_SRCS) $(UART_SRCS) boards/tangnano20k/top_step0.sv
GOWIN_SIM  := platform/gowin/sim/gowin_prims.sv

TOPS  := tpiu_rx trace_rx selftest_hspi hspi_rx
TESTS := tpiu trace hspi8 hspi16 hspi32 hspi16r hspirx8 hspirx16 hspirx32 hspirx16r uart

srcs_tpiu_rx       := $(TPIU_SRCS)
srcs_selftest_hspi := $(HSPI_SRCS)
srcs_trace_rx      := $(TRACE_SRCS)
srcs_hspi_rx       := $(HSPIRX_SRCS)
srcs_uart_hex_top  := $(UART_SRCS) test/uart/uart_hex_top.sv

# test -> top, testbench, extra sources, verilator -G and C++ -D for the build
top_tpiu := tpiu_rx
tb_tpiu  := test/tpiu/tb_tpiu.cpp
top_trace := trace_rx
tb_trace  := test/trace/tb_trace.cpp
top_uart  := uart_hex_top
tb_uart   := test/uart/tb_uart.cpp

define hspi_test
top_$(1)    := selftest_hspi
tb_$(1)     := test/hspi/tb_hspi.cpp
extra_$(1)  := ../sw/usbstream/check.c
deps_$(1)   := test/models/ch569_hspi.h ../sw/usbstream/check.h ../fw/ch569/usbstream/stream.h
vflags_$(1) := -GW=$(2) $(if $(3),-GCRC_INIT=$(3) -GCRC_REFLECT=1 -GCRC_XOROUT=$(3))
cflags_$(1) := -DHSPI_W=$(2) $(if $(3),-DHSPI_CRC_INIT=$(3) -DHSPI_CRC_REFLECT=1 -DHSPI_CRC_XOROUT=$(3))
endef
$(eval $(call hspi_test,hspi8,8))
$(eval $(call hspi_test,hspi16,16))
$(eval $(call hspi_test,hspi32,32))
$(eval $(call hspi_test,hspi16r,16,65535))

define hspirx_test
top_$(1)    := hspi_rx
tb_$(1)     := test/hspi/tb_hspi_rx.cpp
deps_$(1)   := test/models/ch569_hspi.h test/models/ch569_hspi_tx.h
vflags_$(1) := -GW=$(2) $(if $(3),-GCRC_INIT=$(3) -GCRC_REFLECT=1 -GCRC_XOROUT=$(3))
cflags_$(1) := -DHSPI_W=$(2) $(if $(3),-DHSPI_CRC_INIT=$(3) -DHSPI_CRC_REFLECT=1 -DHSPI_CRC_XOROUT=$(3))
endef
$(eval $(call hspirx_test,hspirx8,8))
$(eval $(call hspirx_test,hspirx16,16))
$(eval $(call hspirx_test,hspirx32,32))
$(eval $(call hspirx_test,hspirx16r,16,65535))

VFLAGS := -Wall --x-assign unique --x-initial unique
CXXFLAGS_TB := -std=c++17 -O1 -I$(CURDIR)/test/common -I$(CURDIR)/test/models \
               -I$(CURDIR)/../fw/ch569/usbstream -I$(CURDIR)/../sw/usbstream

.SECONDEXPANSION:
.SECONDARY:

all: lint test crc-check synth board-lint board-synth

lint: $(addprefix lint-,$(TOPS))
lint-%:
	$(VERILATOR) --lint-only $(VFLAGS) --top-module $* $(srcs_$*)

test: $(addprefix test-,$(TESTS))
test-%: $(BUILD)/%/tb
	$<

$(BUILD)/%/tb: $$(srcs_$$(top_$$*)) $$(tb_$$*) $$(extra_$$*) $$(deps_$$*) $(wildcard test/common/*.h)
	@mkdir -p $(BUILD)/$*
	$(VERILATOR) --cc --exe --build -j $(JOBS) $(VFLAGS) $(vflags_$*) -Wno-fatal \
	  --top-module $(top_$*) -Mdir $(BUILD)/$* -o tb \
	  -CFLAGS "$(CXXFLAGS_TB) $(cflags_$*)" \
	  $(srcs_$(top_$*)) $(abspath $(tb_$*) $(extra_$*))

# Step 0 rehearsal: raw packets from hspi_rx -> tools/hspi-crc finds the CRC the
# CH569 model was built with (16 bit, init/xorout 0xFFFF, reflected)
crc-check: $(BUILD)/hspirx16r/tb
	HSPI_RAW_DUMP=$(BUILD)/hspirx16r/raw.txt $< > /dev/null
	python3 ../tools/hspi-crc/find_crc.py $(BUILD)/hspirx16r/raw.txt | tee $(BUILD)/hspirx16r/crc.txt
	grep -q 'CRC16 over header+payload, CRC bytes little-endian, init 0xFFFF, refin 1, refout 1, xorout 0xFFFF' $(BUILD)/hspirx16r/crc.txt

# resource lines of `stat`, old (Yosys 0.3x) and new (0.5x+) layouts
STAT_RE := (cells|ALU|DFF|LUT[0-9]|MUX2|SDP|DPB|rPLL|ODDR|IOBUF)

synth: $(addprefix synth-,$(TOPS))
synth-%:
	@mkdir -p $(BUILD)/synth
	$(YOSYS) -l $(BUILD)/synth/$*.log -p 'read_verilog -sv $(srcs_$*); synth_gowin -top $*; stat' > /dev/null
	@echo "== $*"; tail -n 45 $(BUILD)/synth/$*.log | grep -E '$(STAT_RE)' || true

# ---------------------------------------------------------------- boards
# Tang Nano 20K, bench step 0. board-synth needs only Yosys (CI); board-pnr needs
# nextpnr-himbaechel and gowin_pack (OSS CAD Suite: make board-pnr OSS=<dir>/bin/).
OSS        ?=
NEXTPNR    ?= $(OSS)nextpnr-himbaechel
GOWIN_PACK ?= $(OSS)gowin_pack
BOARD_YOSYS ?= $(if $(OSS),$(OSS)yosys,$(YOSYS))
TN20K      := boards/tangnano20k
TN20K_OUT  := $(BUILD)/tangnano20k

board-lint:
	$(VERILATOR) --lint-only $(VFLAGS) -Wno-PINCONNECTEMPTY -Wno-DECLFILENAME \
	  --top-module top_step0 $(GOWIN_SIM) $(STEP0_SRCS)

board-synth: $(TN20K_OUT)/top_step0.json
$(TN20K_OUT)/top_step0.json: $(STEP0_SRCS)
	@mkdir -p $(TN20K_OUT)
	$(BOARD_YOSYS) -l $(TN20K_OUT)/synth.log -p 'read_verilog -sv $(STEP0_SRCS); synth_gowin -top top_step0 -json $@; stat' > /dev/null
	@echo "== top_step0"; tail -n 45 $(TN20K_OUT)/synth.log | grep -E '$(STAT_RE)' || true

board-pnr: $(TN20K_OUT)/top_step0.fs
$(TN20K_OUT)/top_step0.fs: $(TN20K_OUT)/top_step0.json $(TN20K)/tangnano20k.cst $(TN20K)/clocks.py
	$(NEXTPNR) --json $< --write $(TN20K_OUT)/top_step0_pnr.json \
	  --device GW2AR-LV18QN88C8/I7 --vopt family=GW2A-18C --vopt cst=$(TN20K)/tangnano20k.cst \
	  --pre-pack $(TN20K)/clocks.py --report $(TN20K_OUT)/report.json -l $(TN20K_OUT)/pnr.log > /dev/null 2>&1 \
	  || { tail -n 30 $(TN20K_OUT)/pnr.log; exit 1; }
	$(GOWIN_PACK) -d GW2A-18C -o $@ $(TN20K_OUT)/top_step0_pnr.json
	@grep -E 'Max frequency' $(TN20K_OUT)/pnr.log | tail -n 2
	@grep -P '^Info: \t +(LUT4|ALU|DFF|BSRAM|IOB|rPLL|IOLOGICO):' $(TN20K_OUT)/pnr.log

# Gowin EDA on the Windows side of WSL (gw_sh.exe): a copy of the sources in a
# Windows temp folder, reports and the bitstream back to $(TN20K_OUT)/gowin.
GW_SH      ?= /mnt/c/gowin/Gowin_V1.9.12.04_x64/IDE/bin/gw_sh.exe
GOWIN_WORK ?= $(shell wslpath -u "$$(cmd.exe /c 'echo %TEMP%' 2>/dev/null | tr -d '\r')" 2>/dev/null)/rln-trace-gowin

board-gowin: $(STEP0_SRCS) $(TN20K)/tangnano20k.cst $(TN20K)/top_step0.sdc $(TN20K)/gowin.tcl
	@test -x "$(GW_SH)" || { echo "no Gowin EDA at $(GW_SH)"; exit 1; }
	rm -rf "$(GOWIN_WORK)" && mkdir -p "$(GOWIN_WORK)/src"
	cp $(STEP0_SRCS) $(TN20K)/tangnano20k.cst $(TN20K)/top_step0.sdc "$(GOWIN_WORK)/src/"
	cp $(TN20K)/gowin.tcl "$(GOWIN_WORK)/"
	cd "$(GOWIN_WORK)" && "$(GW_SH)" gowin.tcl > gw_sh.log 2>&1; tail -n 5 "$(GOWIN_WORK)/gw_sh.log"
	@mkdir -p $(TN20K_OUT)/gowin
	cp "$(GOWIN_WORK)/gw_sh.log" $(TN20K_OUT)/gowin/
	cp -r "$(GOWIN_WORK)/impl/." $(TN20K_OUT)/gowin/ 2>/dev/null || true
	@test -f $(TN20K_OUT)/gowin/pnr/top_step0.fs || { echo "Gowin: no bitstream, see $(TN20K_OUT)/gowin/gw_sh.log"; exit 1; }

clean:
	rm -rf $(BUILD)

.PHONY: all lint test crc-check synth board-lint board-synth board-pnr board-gowin clean
