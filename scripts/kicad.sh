#!/usr/bin/env bash
# Run a command inside the KiCad 10 container with this repository at /work.
#
# Examples:
#   ./scripts/kicad.sh kicad-cli sch erc --severity-all hardware/rp2040_midi_bridge/rp2040_midi_bridge.kicad_sch
#   ./scripts/kicad.sh kicad-cli pcb drc --severity-all hardware/rp2040_midi_bridge/rp2040_midi_bridge.kicad_pcb
#   ./scripts/kicad.sh python3 hardware/rp2040_midi_bridge/scripts/gen_pcb.py
#
# Override the image with KICAD_IMAGE (default: kicad/kicad:10.0).  If the
# current user cannot write to the bind mount inside the container, fall back
# to root inside the container.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
IMAGE=${KICAD_IMAGE:-kicad/kicad:10.0}

if docker run --rm --user "$(id -u):$(id -g)" -v "$ROOT:/work" "$IMAGE" test -w /work >/dev/null 2>&1; then
  exec docker run --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -e PCB_PROTECT -e PCB_EXTRA_TARGETS -v "$ROOT:/work" -w /work "$IMAGE" "$@"
else
  exec docker run --rm --user 0:0 -e HOME=/tmp -e PCB_PROTECT -e PCB_EXTRA_TARGETS -v "$ROOT:/work" -w /work "$IMAGE" "$@"
fi
