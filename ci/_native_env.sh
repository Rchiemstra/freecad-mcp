#!/bin/bash
set -euo pipefail

ROOT="${MCP_ROOT:-/mcp}"
BUILD="${FREECAD_BUILD:-/hostbuild/debug}"
cd "$ROOT"

pip install --no-build-isolation --no-deps -e . >/tmp/mcp-editable.log

export PYTHONPATH="${ROOT}:${ROOT}/src:${BUILD}/lib:${BUILD}/Mod${PYTHONPATH:+:$PYTHONPATH}"
SO_DIRS="$(find "$BUILD" -name '*.so' -printf '%h\n' | sort -u | paste -sd: -)"
export LD_LIBRARY_PATH="${SO_DIRS}${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

echo "PYTHONPATH=$PYTHONPATH"
echo "LD_LIBRARY_PATH=$LD_LIBRARY_PATH"
exec "$@"
