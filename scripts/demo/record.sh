#!/usr/bin/env bash
# One bounded container, one real GUI, no builds and no git mutations.
set -euo pipefail
cd "$(dirname "$0")/../.."
free -m
available=$(free -m | awk '/Mem:/ {print $7}')
(( available >= 1500 )) || { echo 'Need at least 1500 MB available'; exit 1; }
if ps -C FreeCAD -o pid= | rg -q '[0-9]'; then echo 'A FreeCAD process is already running'; exit 1; fi
if docker container inspect strawberry-replay >/dev/null 2>&1; then echo 'The replay container already exists'; exit 1; fi
mkdir -p demo-out/stage2 demo-out/stage3 demo-out/stills3 demo-out/files
python3 - <<'PY'
from pathlib import Path
import shutil
root=Path('examples/strawberry-picker')
shutil.copyfile(root/'strawberry-head.FCStd','demo-out/strawberry-head-v2.FCStd')
shutil.copyfile(root/'evidence/jaw-fem.FCStd','demo-out/stage2/fem.FCStd')
for src,dst in [('stage2-checks.json','checks.json'),('design-manifest.json','design-manifest.json'),('fem.json','fem.json')]:
 for stage in ['stage2','stage3']:shutil.copyfile(root/'evidence'/src,Path('demo-out')/stage/dst)
Path('demo-out/stills2').mkdir(exist_ok=True)
shutil.copyfile(root/'evidence/design-notes.md','demo-out/stills2/design-notes.md')
for p in (root/'parts').iterdir():shutil.copyfile(p,Path('demo-out/files')/(p.stem+'-v2'+p.suffix))
PY
docker run --rm --name strawberry-replay --memory=2g --memory-swap=2g \
 -e DEMO_AUTORUN=1 \
 -v /home/msi/FreeCAD:/workspace:ro -v /home/msi/mcp-wt-demofix:/mcpfix:ro \
 -v "$PWD":/demo -w /demo 127.0.0.1:5001/freecad-ci-mcp-fem:24.04 \
 bash scripts/demo/replay_inside.sh

cp demo-out/stage3/handoff/strawberry-demo-paths.txt /tmp/strawberry-demo-paths.txt
cp demo-out/stage3/handoff/strawberry-demo-commit-msg.txt /tmp/strawberry-demo-commit-msg.txt
