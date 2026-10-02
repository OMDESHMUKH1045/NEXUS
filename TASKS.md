# NEXUS Tasks

Tasks are grouped by dependency order. Checkboxes describe deliverable work,
not speculative features.

## Phase 0 — Architecture

- [x] Inspect repository, environment, and available skills.
- [x] Create `ARCHITECTURE.md`.
- [x] Create `ROADMAP.md`.
- [x] Create `TASKS.md`.
- [x] Create `DECISIONS.md`.
- [ ] Create or obtain missing project skills before implementing governed
  subsystems.

## Foundation (Phase 1 complete)

- [x] Choose package layout and Python build metadata.
- [x] Define typed configuration for paths, limits, intervals, and execution
  modes.
- [x] Define structured log schema with component, experiment, and job fields.
- [x] Define application supervisor and shutdown contracts.
- [x] Add CLI entry point and structured, read-only `doctor` diagnostics.
- [x] Add dependency manifest and test extra without installing system packages.
- [x] Create project-local `.venv`, install test dependencies, and pass the
  Phase 1 verification gate.

## Observatory (Phase 2 complete; verification passed)

- [x] Define metric sample and availability models.
- [x] Implement direct `/proc` and `/sys` CPU/load/memory/process readers.
- [x] Implement read-only `/proc/diskstats` counters.
- [x] Implement thermal discovery by labels.
- [x] Preserve optional DRM/OpenCL capability adapters from Phase 1.
- [x] Add bounded in-memory ring buffer; persistence is deferred.
- [ ] Add observatory-overhead measurement (deferred; no overhead claim is
  made in Phase 2).
- [x] Test absent and changing sensors.

## Datasets (Phase 3 complete; verification passed)

- [x] Define dataset metadata and fingerprint models.
- [x] Implement streaming adapters for CSV, JSONL, and read-only SQLite.
- [x] Implement bounded schema/profile collection.
- [x] Implement conservative memory and disk requirement estimates.
- [ ] Implement incremental e-commerce generator (out of scope for Phase 3).
- [ ] Add other generator families (out of scope for Phase 3).
- [x] Test malformed input and small fixtures.
- [x] Add the finite `nexus profile` workload with Phase 2 telemetry
  integration.
- [x] Complete Phase 3 verification gate.

## Analysis

- [x] Define operation interface and result metadata (Phase 4A).
- [x] Implement descriptive statistics and quantiles (Phase 4A).
- [x] Define the explicit Phase 3 to analysis-table typing boundary (Phase 4A).
- [x] Add focused Phase 4A correctness and contract tests.
- [x] Define correlation result/status contracts (Phase 4B).
- [x] Implement Pearson/Spearman correlation (Phase 4B).
- [x] Add bounded correlation and CSV/JSONL/SQLite integration tests (Phase 4B).
- [x] Define typed IQR, Z-score, and modified Z-score outlier contracts (Phase 4C).
- [x] Implement bounded IQR, Z-score, and modified Z-score summaries (Phase 4C).
- [x] Add outlier numerical, limit, and CSV/JSONL/SQLite integration tests (Phase 4C).
- [ ] Implement group and multi-column aggregation.
- [ ] Implement time-series resampling and rolling operations.
- [ ] Implement transformations with deterministic behavior.
- [ ] Add trusted correctness fixtures.

## Scheduler and Pipelines

- [ ] Define job states, events, cancellation token, and error model.
- [ ] Implement bounded thread execution.
- [ ] Implement bounded process execution only where useful.
- [ ] Implement priority, timeout, cancellation, and graceful shutdown.
- [ ] Define scheduling policies and desktop-headroom defaults.
- [ ] Define DAG node/dependency models and cycle validation.
- [ ] Implement ready-node scheduling and downstream failure propagation.
- [ ] Record wall/CPU/memory metrics without unverified performance claims.
- [ ] Test worker failures, cancellation, child cleanup, and bounds.

## Storage and Experiments

- [ ] Define SQLite schema and migration strategy.
- [ ] Implement repositories for metadata and state transitions.
- [ ] Add DuckDB/Parquet query boundary.
- [ ] Define experiment configuration and environment snapshot.
- [ ] Link experiments to jobs, telemetry, results, and decisions.
- [ ] Test batched telemetry writes and database failures.

## API and UI

- [ ] Add FastAPI application factory and typed routes.
- [ ] Add capability/system/job/dataset/experiment/report endpoints.
- [ ] Add bounded WebSocket or SSE event stream.
- [ ] Scaffold React/Vite frontend once Node is available.
- [ ] Build overview, live system, jobs, datasets, experiments, and headroom.
- [ ] Build pipeline DAG and compute timeline views.
- [ ] Verify frontend event frequency and disconnect behavior.

## Compute and Measurement

- [ ] Define CPU/Polars/OpenCL backend interface.
- [ ] Add CPU reference implementation for each accelerated operation.
- [ ] Add optional OpenCL discovery and graceful fallback.
- [ ] Measure host preparation, transfers, kernel, and total elapsed time.
- [ ] Validate equivalent outputs within documented tolerances.
- [ ] Establish reproducible baseline measurement procedure.
- [ ] Record significant findings in `docs/PERFORMANCE.md`.

## Adaptive Scheduling and Correlation

- [ ] Define headroom observations and explainable decision records.
- [ ] Adjust desired future concurrency without preempting healthy work.
- [ ] Correlate monotonic job intervals with telemetry samples.
- [ ] Produce factual timeline summaries and scheduler explanations.
- [ ] Test unavailable metrics and changing system conditions.

## Reporting and Release Readiness

- [ ] Generate self-contained HTML reports.
- [ ] Include measured experiment metadata, results, jobs, telemetry, and
  decisions.
- [ ] Add CPU-only integration tests.
- [ ] Add optional-OpenCL absence/fallback tests.
- [ ] Run all relevant tests and inspect failures.
- [ ] Verify bounded resources and clean shutdown.
- [ ] Document setup, run, doctor, and operational troubleshooting.
