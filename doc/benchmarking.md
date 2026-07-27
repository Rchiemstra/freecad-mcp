# Benchmarking

The benchmark catalog contains the required 20 task workflows, immutable task
metadata, validators, KPI calculation, baseline comparison, and quality gates.
Run the authoritative container:

```bash
docker compose run --rm benchmark
```

It generates `benchmark-results.json` and `benchmark-report.md`. Set
`FREECAD_MCP_BENCHMARK_BASELINE` in a reporting integration to load a previous
JSON result; the report logic flags material KPI regressions. The Compose
service mounts the checkout at `/results`, so both reports remain available in
the checkout after the container exits.

KPIs include task/first-attempt/tool/completed-response success, protected and
false-positive rejections, argument/tool-selection validity, recovery, safe
failure, rollback, health/unrelated mutation, timeout stage, latency
percentiles, calls per success, and public/generated/typed execution shares.
Token metrics remain `null` unless the MCP client supplies them; bytes are not
misrepresented as tokens.

Expected policy rejections are successful safe tasks, not excluded failures.
The initial gates are encoded in `benchmarks.runner.evaluate_quality_gates`;
the suite fails if any gate fails. Runtime-created `.FCStd` fixtures ensure the
active FreeCAD build writes and reopens its own archive format.
