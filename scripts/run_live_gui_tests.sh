#!/bin/sh
# Run the live FreeCAD GUI + MCP stress tests (tests/live_gui), under Xvfb when
# no display is available.
#
#   FREECAD_MCP_ISOLATED_FREECAD=/path/to/build/bin/FreeCAD scripts/run_live_gui_tests.sh [pytest args]
#
# A skipped or empty run fails: skipped live tests never touched FreeCAD.
set -eu
cd "$(dirname "$0")/.."
: "${FREECAD_MCP_ISOLATED_FREECAD:?set to an absolute FreeCAD GUI executable}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"
export PYTHONUNBUFFERED=1
report="${LIVE_GUI_JUNIT:-results_live_gui.xml}"
rm -f "$report"

set -- python3 -m pytest -m live_gui tests/live_gui -p no:cacheprovider \
	--junitxml="$report" "$@"
rc=0
if [ -n "${DISPLAY:-}" ]; then
	"$@" || rc=$?
else
	xvfb-run -a -s "-screen 0 1600x1000x24" "$@" || rc=$?
fi

python3 - "$report" <<'EOF'
import sys
import xml.etree.ElementTree as ET

root = ET.parse(sys.argv[1]).getroot()
suite = root if root.tag == "testsuite" else root.find("testsuite")
tests = int(suite.get("tests", 0))
skipped = int(suite.get("skipped", 0))
if tests == 0 or skipped:
    sys.exit(f"live GUI tests: {tests} collected, {skipped} skipped; treating as failure")
EOF
exit "$rc"
