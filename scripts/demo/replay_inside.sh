#!/bin/bash
set -euo pipefail
cd /demo
python3 - <<'PY_CLEAN'
from pathlib import Path
import time
trash=Path('demo-out/trash')/('runtime-'+str(time.time_ns()));trash.mkdir(parents=True)
for name in ['stop','ready','exit.json','render-command.json','ui-command.json','ui-ready']:
 p=Path('demo-out/stage3')/name
 if p.exists():p.rename(trash/name)
PY_CLEAN
export APPDATA=/tmp/strawberry-normal-profile
export FREECAD_MCP_PROFILE_DIR=/demo/demo-out/stage3-profile
export FREECAD_MCP_ISOLATED_FREECAD=/workspace/build/debug/bin/FreeCAD
export QT_QPA_PLATFORM=xcb PYTHONDONTWRITEBYTECODE=1 DISPLAY=:99
export PYTHONPATH=/mcpfix/src DEMO_STAGE=stage3
export FREECAD_MCP_FFMPEG=/demo/scripts/demo/ffmpeg-bounded.sh
if ! command -v ffmpeg >/dev/null; then
 apt-get update -qq
 apt-get install -y -qq ffmpeg fonts-dejavu-core > /tmp/strawberry-apt.log 2>&1
fi
python3 scripts/demo/stage2_runtime.py setup --port 19879 > demo-out/stage3/setup.log 2>&1
Xvfb :99 -screen 0 1600x1000x24 > demo-out/stage3/xvfb.log 2>&1 &
xpid=$!
python3 scripts/demo/stage2_runtime.py launch --exit-status-file /demo/demo-out/stage3/exit.json --log-file /demo/demo-out/stage3/freecad.log /demo/scripts/demo/replay_bootstrap.FCMacro > demo-out/stage3/launcher.log 2>&1 &
lpid=$!
cleanup() {
 if test -f demo-out/stage3/exit.json; then
  gui_pid=$(python3 -c 'import json; print(json.load(open("demo-out/stage3/exit.json"))["pid"])')
  kill -TERM "$gui_pid" 2>/dev/null || true
 fi
 wait "$lpid" || true
 kill -TERM "$xpid" 2>/dev/null || true
}
trap cleanup EXIT
for attempt in $(seq 1 120); do
 if test -f demo-out/stage3/ready && test -f demo-out/stage3/exit.json; then break; fi
 kill -0 "$lpid" 2>/dev/null || { tail -25 demo-out/stage3/launcher.log; exit 1; }
 sleep 1
done
test -f demo-out/stage3/ready
if test "${DEMO_AUTORUN:-0}" = 1; then
 python3 scripts/demo/polish_stills.py > demo-out/stage3/stills.log 2>&1
 python3 scripts/demo/replay_driver.py > demo-out/stage3/replay.log 2>&1
 python3 scripts/demo/inspect_exports.py > demo-out/stage3/export-inspection.log 2>&1
 python3 scripts/demo/reference_checkpoint.py > demo-out/stage3/reference-checkpoint.log 2>&1
 cleanup
 trap - EXIT
 python3 scripts/demo/postproduce.py > demo-out/stage3/postproduce.log 2>&1
 python3 scripts/demo/package_demo.py
 python3 scripts/demo/verify_delivery.py
else
 while ! test -f demo-out/stage3/stop; do sleep 2; done
fi
