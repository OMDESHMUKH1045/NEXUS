# NEXUS Roadmap

This roadmap is intentionally incremental. Each phase must leave the
repository runnable, tested with small fixtures, and documented before the
next phase begins.

## Phase 0 — Architecture (current)

- [x] Inspect the empty repository and safe runtime environment.
- [x] Inspect available project skills.
- [x] Define component boundaries, data flow, lifecycle, storage, telemetry,
  OpenCL, and shutdown behavior.
- [x] Perform a simplification and resource-safety review.
- [x] Record architecture decisions and actionable tasks.
- [ ] Add the missing subsystem skills before those subsystems are built.

## Phase 1 — Skeleton and Developer Workflow

- [ ] Create the Python package and configuration model.
- [ ] Add structured logging and a lifecycle supervisor.
- [ ] Add CLI command routing and `nexus doctor`.
- [ ] Add dependency manifests with minimal, justified dependencies.
- [ ] Add test configuration and small-fixture conventions.

## Phase 2 — Linux Observatory

- [ ] Implement safe system, process, disk, memory, load, thermal, DRM, and
  capability readers.
- [ ] Represent unavailable metrics explicitly.
- [ ] Add bounded sampling, live events, batched persistence, and overhead
  measurements.
- [ ] Test with mocked `/proc` and `/sys` data plus missing-sensor cases.

## Phase 3 — Dataset Engine

- [ ] Add dataset registry, fingerprints, import validation, and metadata.
- [ ] Support CSV, JSON/JSONL, Parquet, SQLite, and sensible DuckDB sources.
- [ ] Add lazy profiling and memory estimates.
- [ ] Add incremental Parquet generators with resource sufficiency warnings.
- [ ] Test small representative fixtures.

## Phase 4 — Analysis Engine

- [ ] Implement deterministic statistics, correlations, outliers,
  aggregation, time-series operations, and transformations.
- [ ] Define operation input/output metadata and validation.
- [ ] Add correctness tests against trusted small references.

## Phase 5 — Scheduler

- [ ] Implement typed jobs, bounded queues, priorities, cancellation,
  timeouts, and worker failure handling.
- [ ] Add ECO, BALANCED, PERFORMANCE, and CUSTOM scheduling policies.
- [ ] Add graceful shutdown and child-process cleanup tests.
- [ ] Add measurement records without claiming speedups.

## Phase 6 — Pipeline DAG

- [ ] Implement DAG validation and lifecycle transitions.
- [ ] Schedule independent nodes without violating dependencies.
- [ ] Record node metrics and explicit downstream skip/cancel reasons.
- [ ] Test cycles, failures, cancellation, and concurrency bounds.

## Phase 7 — Storage

- [ ] Implement SQLite repositories and migrations.
- [ ] Add DuckDB/Parquet analytical access where justified.
- [ ] Batch telemetry writes and test recovery/error behavior.

## Phase 8 — Experiments

- [ ] Define reproducible experiment configuration and environment capture.
- [ ] Link datasets, pipelines, jobs, telemetry, decisions, and results.
- [ ] Add experiment listing and comparison based on measured fields.

## Phase 9 — FastAPI

- [ ] Add typed API models and endpoints for core resources.
- [ ] Add capability, system, job, dataset, experiment, and report routes.
- [ ] Add WebSocket or SSE event streaming with bounded fan-out.
- [ ] Test API behavior and failure responses.

## Phase 10 — React Dashboard

- [ ] Scaffold the TypeScript/Vite frontend when Node is available.
- [ ] Build overview, live system, jobs, datasets, experiments, and
  headroom views.
- [ ] Add accessible dark-first layout for 1920x1080.

## Phase 11 — Live Telemetry

- [ ] Connect the live stream to bounded frontend state.
- [ ] Display CPU, memory, disk, thermal, GPU, and observatory overhead data.
- [ ] Avoid aggressive polling and verify event frequency.

## Phase 12 — Compute Timeline

- [ ] Build job/backend timeline data and visualization.
- [ ] Add hover details from actual timestamps and measured metrics.
- [ ] Test overlapping and failed jobs.

## Phase 13 — Optional OpenCL

- [ ] Add the OpenCL skill and capability adapter.
- [ ] Implement one useful numerical operation with a CPU reference.
- [ ] Measure preparation, transfers, kernel, result transfer, and total time.
- [ ] Validate numerical equivalence and CPU fallback on absent/failed OpenCL.

## Phase 14 — Adaptive Scheduler

- [ ] Add explainable headroom policy inputs.
- [ ] Adjust desired future concurrency only.
- [ ] Persist decisions with measurements and reasons.
- [ ] Test load, memory, swap, thermal, and queue edge cases.

## Phase 15 — Resource Correlation

- [ ] Associate jobs with telemetry intervals.
- [ ] Compute factual CPU, RAM, disk, thermal, and GPU summaries.
- [ ] Expose measured headroom explanations and correlation API data.

## Phase 16 — Reports

- [ ] Generate self-contained factual HTML reports.
- [ ] Include metadata, profiles, results, timings, telemetry, decisions,
  OpenCL information, and timelines.
- [ ] Test report generation with unavailable metrics and failed jobs.

## Phase 17 — Integration and Polish

- [ ] Run the complete small-fixture test suite.
- [ ] Verify CPU-only operation and optional dependency behavior.
- [ ] Measure observatory overhead and representative pipeline behavior.
- [ ] Document performance findings in `docs/PERFORMANCE.md`.
- [ ] Improve operational documentation and UI polish.
