#!/usr/bin/env bash
# Route finishing pass: run DRC, close the remaining unconnected items.
#
# gen_pcb.py routes greedily and leaves a few pad connections open.  close_gaps
# adds a track or via for each pair that kicad-cli reports without ripping up
# existing copper; local_repair then rips a blocking net locally and re-routes
# it when the cheap repair cannot get through.  Run this inside the KiCad
# container:
#
#   make pcb
#   make finish
#
# The board and drc.rpt end up in the state of the last DRC run.
set -euo pipefail

HERE=$(cd "$(dirname "$0")/.." && pwd)
PCB="$HERE/rp2040_midi_bridge.kicad_pcb"
RPT="$HERE/drc.rpt"
LOG=$(mktemp)

count() {
  sed -n "s/^\*\* Found \([0-9]*\) $1 \*\*$/\1/p" "$RPT"
}

drc() {
  kicad-cli pcb drc --severity-all --output "$RPT" "$PCB" >"$LOG" 2>&1
}

report() {
  local v u
  v=$(count "DRC violations")
  u=$(count "unconnected pads")
  echo "  $v violations, $u unconnected"
}

for round in 1 2 3 4 5; do
  echo "round $round"
  drc
  report
  [ "$(count "unconnected pads")" -eq 0 ] && [ "$(count "DRC violations")" -eq 0 ] && exit 0

  if [ "$(count "unconnected pads")" -gt 0 ]; then
    python3 "$HERE/scripts/close_gaps.py" "$PCB" "$RPT" >"$LOG" 2>&1 || true
    tail -1 "$LOG"
    drc
    report
    [ "$(count "unconnected pads")" -eq 0 ] && [ "$(count "DRC violations")" -eq 0 ] && exit 0
  fi

  if [ "$(count "unconnected pads")" -gt 0 ]; then
    repaired="${PCB%.kicad_pcb}.repaired.kicad_pcb"
    rm -f "$repaired"
    python3 "$HERE/scripts/local_repair.py" "$PCB" "$RPT" >"$LOG" 2>&1 || true
    grep -E 'unconnected:|repaired nets|still unconnected' "$LOG" || tail -5 "$LOG"
    if [ ! -f "$repaired" ]; then
      echo "local_repair produced no board" >&2
      exit 1
    fi
    mv "$repaired" "$PCB"
    rm -f "${PCB%.kicad_pcb}.repaired.kicad_pro" "${PCB%.kicad_pcb}.repaired.kicad_prl"
  fi
done

echo "routing did not converge" >&2
exit 1
