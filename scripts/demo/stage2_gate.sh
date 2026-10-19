#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
free -m
available=$(free -m | awk '/Mem:/ {print $7}')
(( available >= 1500 )) || { echo 'Need 1500 MB available'; exit 1; }
if ps -C FreeCAD -o pid= | rg -q '[0-9]'; then echo 'A FreeCAD process is already running'; exit 1; fi
mkdir -p demo-out/stage2 demo-out/stills2 demo-out/files
cp scripts/demo/stage2_bootstrap.FCMacro demo-out/stage2/bootstrap.FCMacro
docker run --rm --name strawberry-stage2 --memory=2g --memory-swap=2g \
 -v /home/msi/FreeCAD:/workspace:ro -v /home/msi/mcp-wt-demofix:/mcpfix:ro \
 -v "$PWD":/demo -w /demo 127.0.0.1:5001/freecad-ci-mcp-fem:24.04 \
 bash scripts/demo/stage2_inside.sh &
container_job=$!
trap 'touch demo-out/stage2/stop; wait "$container_job" || true' EXIT
for attempt in $(seq 1 120); do
 if docker exec strawberry-stage2 test -f demo-out/stage2/ready 2>/dev/null; then break; fi
 sleep 1
done
for phase in init wiring_fix realism attachment_checks checks; do
 docker exec strawberry-stage2 python3 scripts/demo/stage2_job.py "$phase" > "demo-out/stage2/$phase.log" 2>&1
done
free -m > demo-out/stage2/before-fem-memory.txt
available=$(free -m | awk '/Mem:/ {print $7}')
(( available >= 1500 )) || { echo 'Need 1500 MB available before FEM'; exit 1; }
docker exec strawberry-stage2 python3 scripts/demo/stage2_fem.py > demo-out/stage2/fem.log 2>&1
for phase in baseline_archive stills parts_view fem_still exports finish save_evidence; do
 docker exec strawberry-stage2 python3 scripts/demo/stage2_job.py "$phase" > "demo-out/stage2/$phase.log" 2>&1
done
python3 scripts/demo/stage2_notes.py
python3 scripts/demo/stage2_verify.py
