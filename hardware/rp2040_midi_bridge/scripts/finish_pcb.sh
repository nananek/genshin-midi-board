#!/usr/bin/env bash
# Route finishing pass: run DRC and close the remaining unconnected items.
#
# gen_pcb.py routes greedily and leaves a few pad connections open.  close_gaps
# adds a track or via for each pair that kicad-cli reports, without ripping up
# existing copper.  Run this inside the KiCad container, e.g.
#
#   make pcb
#   make finish
#
# The board and drc.rpt end up in the state of the last DRC run.
set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
PCB="$HERE/rp2040_midi_bridge.kicad_pcb"
RPT="$HERE/drc.rpt"

count() {
  sed -n "s/^\*\* Found \([0-9]*\) $1 \*\*$/\1/p" "$RPT"
}

for round in 1 2 3 4; do
  kicad-cli pcb drc --severity-all --output "$RPT" "$PCB"
  unconnected=$(count "unconnected pads")
  violations=$(count "DRC violations")
  echo "round $round: $violations violations, $unconnected unconnected"
  if [ "$unconnected" -eq 0 ] && [ "$violations" -eq 0 ]; then
    exit 0
  fi
  if [ "$unconnected" -eq 0 ]; then
    echo "unconnected is 0 but DRC violations remain" >&2
    exit 1
  fi
  python3 "$HERE/scripts/close_gaps.py" "$PCB" "$RPT"
done

echo "unconnected items remain after 4 rounds" >&2
exit 1
