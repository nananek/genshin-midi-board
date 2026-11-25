PYTHON ?= python3

VERSION ?= v0.1.0
COMMIT ?= $(shell git rev-parse HEAD)

.PHONY: all check test floorplan tables netlist sch pcb finish silk kicad-shell erc drc kicad-check case-template fab clean

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

case-template:
	$(PYTHON) scripts/gen_case_template.py
	rsvg-convert -f pdf -o docs/case_muji_m_template.pdf docs/case_muji_m_template.svg

KICAD_SCH := hardware/rp2040_midi_bridge/rp2040_midi_bridge.kicad_sch
KICAD_PCB := hardware/rp2040_midi_bridge/rp2040_midi_bridge.kicad_pcb
KICAD := ./scripts/kicad.sh

PCB_GEN := hardware/rp2040_midi_bridge/scripts/gen_pcb.py

sch:
	$(KICAD) python3 hardware/rp2040_midi_bridge/scripts/gen_sch.py

pcb:
	$(KICAD) python3 -u $(PCB_GEN)

finish:
	$(KICAD) bash hardware/rp2040_midi_bridge/scripts/finish_pcb.sh

silk:
	$(KICAD) python3 hardware/rp2040_midi_bridge/scripts/update_silk.py

kicad-shell:
	$(KICAD) bash

erc:
	$(KICAD) kicad-cli sch erc --severity-all --output hardware/rp2040_midi_bridge/erc.rpt $(KICAD_SCH)

drc:
	$(KICAD) kicad-cli pcb drc --severity-all --output hardware/rp2040_midi_bridge/drc.rpt $(KICAD_PCB)

kicad-check: erc drc
	$(PYTHON) scripts/check_kicad_pcb.py

fab:
	@test -z "$$(git status --porcelain)" || { \
		echo "working tree is dirty; commit before building release data" >&2; \
		exit 1; \
	}
	$(KICAD) python3 scripts/make_fab.py --version $(VERSION) --commit $(COMMIT)

clean:
	rm -f hardware/rp2040_midi_bridge/floorplan.svg hardware/rp2040_midi_bridge/erc.rpt hardware/rp2040_midi_bridge/drc.rpt
