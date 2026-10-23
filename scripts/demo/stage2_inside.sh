#!/bin/bash
set -euo pipefail
cd /demo
rm -f demo-out/stage2/stop demo-out/stage2/ready demo-out/stage2/exit.json demo-out/stage2/render-command.json
export APPDATA=/tmp/stage2-normal-profile
export FREECAD_MCP_PROFILE_DIR=/demo/demo-out/stage2-profile
export FREECAD_MCP_ISOLATED_FREECAD=/workspace/build/debug/bin/FreeCAD
export QT_QPA_PLATFORM=xcb PYTHONDONTWRITEBYTECODE=1 DISPLAY=:99
export PYTHONPATH=/mcpfix/src
python3 scripts/demo/stage2_runtime.py setup --port 19878 > demo-out/stage2/setup.log 2>&1
Xvfb :99 -screen 0 1600x1000x24 > demo-out/stage2/xvfb.log 2>&1 &
xpid=$!
trap 'kill -TERM "$xpid" 2>/dev/null || true' EXIT
python3 scripts/demo/stage2_runtime.py launch --exit-status-file /demo/demo-out/stage2/exit.json --log-file /demo/demo-out/stage2/freecad.log /demo/demo-out/stage2/bootstrap.FCMacro > demo-out/stage2/launcher.log 2>&1 &
lpid=$!
for attempt in $(seq 1 120); do
 if test -f demo-out/stage2/ready && test -f demo-out/stage2/exit.json; then break; fi
 kill -0 "$lpid" 2>/dev/null || { tail -25 demo-out/stage2/launcher.log; exit 1; }
 sleep 1
done
test -f demo-out/stage2/ready
while ! test -f demo-out/stage2/stop; do sleep 2; done
pid=$(python3 -c 'import json; print(json.load(open("demo-out/stage2/exit.json"))["pid"])')
kill -TERM "$pid" 2>/dev/null || true
wait "$lpid" || true
