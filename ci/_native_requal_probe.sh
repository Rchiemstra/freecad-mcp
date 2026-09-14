#!/bin/bash
set -euo pipefail
ROOT="${MCP_ROOT:-/mcp}"
cd "$ROOT"
out="${1:-/mcp/native_requal_probe.tsv}"
echo -e "op\trc\tsummary" >"$out"
ops=(
  chamfer_feature boolean_union boolean_intersection snapshot
  loft_feature revolve_feature sweep_feature helical_sweep_feature
  pad_feature sketch_attach bounding_box create_assembly
)
limit="${NATIVE_OP_TIMEOUT:-90}"
for op in "${ops[@]}"; do
  echo "===== PROBE $op ====="
  log="/tmp/${op}.probe.log"
  set +e
  timeout --signal=KILL "$limit" python3 "ci/qualify_${op}.py" --native >"$log" 2>&1
  rc=$?
  set -e
  if [[ "$rc" -eq 0 ]]; then
    summary="$(grep -E 'passed|skipped' "$log" | tail -1 | tr '\t' ' ')"
    echo -e "${op}\t0\t${summary}" | tee -a "$out"
  else
    if [[ "$rc" -eq 124 || "$rc" -eq 137 ]]; then
      summary="TIMEOUT after ${limit}s"
    else
      summary="$(grep -E 'FAILED|Error|passed|AssertionError|error_code' "$log" | tail -8 | tr '\n' '|' | tr '\t' ' ')"
    fi
    echo -e "${op}\t${rc}\t${summary}" | tee -a "$out"
    tail -40 "$log" || true
  fi
done
echo "===== PROBE DONE ====="
cat "$out"
