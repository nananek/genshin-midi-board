PYTHON ?= python3

.PHONY: all check test floorplan tables netlist kicad-shell erc drc kicad-check clean

all: check floorplan tables netlist

check:
	$(PYTHON) scripts/check_design.py
	$(PYTHON) scripts/check_kicad_pcb.py
	$(PYTHON) -m unittest discover -s tests -v

test: check

floorplan:
	$(PYTHON) scripts/gen_floorplan.py

tables:
	$(PYTHON) scripts/export_tables.py

netlist:
	$(PYTHON) scripts/gen_netlist.py

KICAD_SCH := hardware/rp2040_frisk/rp2040_frisk.kicad_sch
KICAD_PCB := hardware/rp2040_frisk/rp2040_frisk.kicad_pcb
KICAD := ./scripts/kicad.sh

kicad-shell:
	$(KICAD) bash

erc:
	$(KICAD) kicad-cli sch erc --severity-all --output hardware/rp2040_frisk/erc.rpt $(KICAD_SCH)

drc:
	$(KICAD) kicad-cli pcb drc --severity-all --output hardware/rp2040_frisk/drc.rpt $(KICAD_PCB)

kicad-check: erc drc
	$(PYTHON) scripts/check_kicad_pcb.py

clean:
	rm -f hardware/rp2040_frisk/floorplan.svg hardware/rp2040_frisk/erc.rpt hardware/rp2040_frisk/drc.rpt
