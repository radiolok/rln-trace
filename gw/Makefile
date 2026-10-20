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

TOPS  := tpiu_rx selftest_hspi
TESTS := tpiu hspi8 hspi16 hspi32 hspi16r

srcs_tpiu_rx       := $(TPIU_SRCS)
srcs_selftest_hspi := $(HSPI_SRCS)

# test -> top, testbench, extra sources, verilator -G and C++ -D for the build
top_tpiu := tpiu_rx
tb_tpiu  := test/tpiu/tb_tpiu.cpp

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

VFLAGS := -Wall --x-assign unique --x-initial unique
CXXFLAGS_TB := -std=c++17 -O1 -I$(CURDIR)/test/common -I$(CURDIR)/test/models \
               -I$(CURDIR)/../fw/ch569/usbstream -I$(CURDIR)/../sw/usbstream

.SECONDEXPANSION:
.SECONDARY:

all: lint test synth

lint: $(addprefix lint-,$(TOPS))
lint-%:
	$(VERILATOR) --lint-only $(VFLAGS) --top-module $* $(srcs_$*)

test: $(addprefix test-,$(TESTS))
test-%: $(BUILD)/%/tb
	$<

$(BUILD)/%/tb: $$(srcs_$$(top_$$*)) $$(tb_$$*) $$(extra_$$*) $$(deps_$$*) test/common/sim.h
	@mkdir -p $(BUILD)/$*
	$(VERILATOR) --cc --exe --build -j $(JOBS) $(VFLAGS) $(vflags_$*) -Wno-fatal \
	  --top-module $(top_$*) -Mdir $(BUILD)/$* -o tb \
	  -CFLAGS "$(CXXFLAGS_TB) $(cflags_$*)" \
	  $(srcs_$(top_$*)) $(abspath $(tb_$*) $(extra_$*))

synth: $(addprefix synth-,$(TOPS))
synth-%:
	@mkdir -p $(BUILD)/synth
	$(YOSYS) -l $(BUILD)/synth/$*.log -p 'read_verilog -sv $(srcs_$*); synth_gowin -top $*; stat' > /dev/null
	@echo "== $*"; tail -n 40 $(BUILD)/synth/$*.log | grep -E '^ +(Number of cells|LUT|ALU|DFF|MUX|BSRAM|SDP|DP)'

clean:
	rm -rf $(BUILD)

.PHONY: all lint test synth clean
