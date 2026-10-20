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
TPIU_SRCS := cores/tpiu_align.sv cores/tpiu_deframer.sv cores/tpiu_idle.sv cores/tpiu_rx.sv

TOPS  := tpiu_rx
TESTS := tpiu

srcs_tpiu_rx := $(TPIU_SRCS)

# test -> top and testbench
top_tpiu := tpiu_rx
tb_tpiu  := test/tpiu/tb_tpiu.cpp

VFLAGS := -Wall --x-assign unique --x-initial unique
CXXFLAGS_TB := -std=c++17 -O1 -I$(CURDIR)/test/common -I$(CURDIR)/../fw/ch569/usbstream -I$(CURDIR)/../sw/usbstream

.SECONDEXPANSION:
.SECONDARY:

all: lint test synth

lint: $(addprefix lint-,$(TOPS))
lint-%:
	$(VERILATOR) --lint-only $(VFLAGS) --top-module $* $(srcs_$*)

test: $(addprefix test-,$(TESTS))
test-%: $(BUILD)/%/tb
	$<

$(BUILD)/%/tb: $$(srcs_$$(top_$$*)) $$(tb_$$*) $$(extra_$$*) test/common/sim.h
	@mkdir -p $(BUILD)/$*
	$(VERILATOR) --cc --exe --build -j $(JOBS) $(VFLAGS) -Wno-fatal \
	  --top-module $(top_$*) -Mdir $(BUILD)/$* -o tb \
	  -CFLAGS "$(CXXFLAGS_TB)" \
	  $(srcs_$(top_$*)) $(abspath $(tb_$*) $(extra_$*))

synth: $(addprefix synth-,$(TOPS))
synth-%:
	@mkdir -p $(BUILD)/synth
	$(YOSYS) -l $(BUILD)/synth/$*.log -p 'read_verilog -sv $(srcs_$*); synth_gowin -top $*; stat' > /dev/null
	@sed -n '/^=== $* ===/,/^$$/p;/Number of cells/p' $(BUILD)/synth/$*.log | tail -n 20

clean:
	rm -rf $(BUILD)

.PHONY: all lint test synth clean
