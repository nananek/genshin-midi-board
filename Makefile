PYTHON ?= python3

.PHONY: all check test floorplan tables clean

all: check floorplan tables

check:
	$(PYTHON) scripts/check_design.py
	$(PYTHON) -m unittest discover -s tests -v

test: check

floorplan:
	$(PYTHON) scripts/gen_floorplan.py

tables:
	$(PYTHON) scripts/export_tables.py

clean:
	rm -f hardware/rp2040_frisk/floorplan.svg
