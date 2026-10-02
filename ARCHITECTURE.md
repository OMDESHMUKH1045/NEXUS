# NEXUS Architecture

NEXUS is a local, Linux-native data-analysis application that measures the
resource behavior of useful analytical workloads. It is not a benchmark
generator or a hardware-management tool. CPU-only operation is the primary
execution path; OpenCL is an optional, measured backend.

## Phase 0 Scope and Constraints

This repository started empty apart from two project skills:

- `resource-safe-execution`
- `measure-dont-guess`

The current host inspection was non-privileged:

- Nobara Linux 44, Linux 7.2.6
- Intel Core i7-6600U, 2 physical cores / 4 logical CPUs
- 7.6 GiB RAM; swap is present and must not be intentionally driven
- Python 3.14.7
- Node.js and npm are not installed
- `clinfo` is installed; Rusticl exposes Intel HD Graphics 520 when
  `RUSTICL_ENABLE=iris` is set
- Python dependencies are not installed yet except NumPy and psutil

These observations are environment facts, not hardware-specific application
assumptions. Runtime decisions must use detected capabilities.

## Design Principles

1. **Useful work only.** Every workload produces analytical output.
2. **CPU first.** OpenCL absence, device failure, or numerical mismatch must
   never prevent ordinary operation.
3. **Bounded resources.** Worker pools, queues, in-flight chunks, caches,
   telemetry buffers, and retries have explicit limits.
4. **Desktop headroom.** Defaults leave at least one logical CPU available and
   consider available memory, load, swap activity, and existing workers.
5. **Measure before optimizing.** Equivalent outputs are validated before
   comparing wall time, CPU time, memory, I/O, or accelerator phases.
6. **Graceful failure.** A failed job or optional subsystem does not crash the
   application or silently produce downstream results.
7. **Local and unprivileged.** Normal operation uses local files and safe Linux
   interfaces without root or hardware-management changes.
8. **Small interfaces.** Components communicate through typed records and
   explicit service interfaces rather than a shared god object.

## Component Boundaries

### Dataset Engine

Owns source discovery, import validation, fingerprints, dataset metadata,
schema inspection, profiling, and incremental synthetic-data generation.
Uses lazy/streaming readers where possible and writes large generated data
incrementally to Parquet. It does not own job scheduling or UI concerns.

### Analysis Engine

Phase 4A and Phase 4B contain synchronous CPU operations over an explicit
`AnalysisTable`/`ColumnSchema` boundary. The Phase 3 CSV, JSONL, and SQLite
readers are adapted once into typed values; operations do not infer or
coerce source values. Descriptive statistics use bounded Welford
accumulation, exact quantiles use bounded materialization, Pearson uses
streaming covariance accumulation, and Spearman uses exact bounded
two-column ranking. Correlation results are typed and pairwise complete.
Phase 4C adds synchronous CPU-only IQR, Z-score, and modified Z-score
outlier summaries with exact bounded valid-value materialization. Outlier
results are typed; per-row transformations and persistence are not part of
the analysis boundary. Phase 4D adds synchronous bounded grouped aggregation
with one group key, one numeric measure, deterministic canonical ordering,
and immutable group summaries. Group state and output cardinality are
bounded by an explicit `max_groups` operation limit, whose conservative
100,000 default matches the existing analysis row/materialization defaults;
persistence and per-row output are not part of the analysis boundary.
Multi-key/multi-measure aggregation,
time-series operations, transformations, execution backends, and scheduling
remain deferred.

### Compute Backends

Expose a narrow backend interface for an analysis operation:

- `CPUBackend`: trusted baseline implementation.
- `PolarsBackend`: lazy/streaming table operations.
- `OpenCLBackend`: optional numerical kernels with explicit capability checks.

The OpenCL backend reports availability and phase timings; it does not become
a hidden fallback or a startup requirement. Accelerated results are compared
with the CPU result using operation-specific tolerances.

### Pipeline/DAG Engine

Stores nodes, dependencies, validation rules, and lifecycle state. It
determines readiness but delegates execution to the scheduler. A failed or
cancelled dependency causes downstream nodes to become `skipped` or
`cancelled`, never silently runnable.

### Job Scheduler

Runs finite jobs using bounded executors and explicit backpressure. It owns
priority, cancellation tokens, timeouts, worker failure conversion,
concurrency policy, and graceful shutdown. It records decisions but does not
terminate healthy work when headroom changes; adaptive scheduling only delays
future launches.

Execution modes are scheduling policies:

- `ECO`: conservative worker and in-flight limits.
- `BALANCED`: moderate limits with desktop headroom.
- `PERFORMANCE`: highest configured bounded limits.
- `CUSTOM`: validated explicit limits.

No mode changes CPU governors, clocks, thermal settings, fans, power limits,
or kernel scheduler settings.

### Experiment Manager

Combines a dataset fingerprint, pipeline definition, execution policy,
backend configuration, telemetry configuration, and software environment into
a reproducible run. It owns experiment lifecycle and links jobs, telemetry,
decisions, and results.

### Linux Observatory

Runs a low-overhead sampling service at a configurable 250 ms–5 s interval
(1 s default). It reads safe interfaces such as `/proc`, `/sys`, psutil, and
optional adapters for DRM/OpenCL utilities. Missing values are `null` with
availability metadata; telemetry is never fabricated.

The service maintains a bounded in-memory ring buffer and batches historical
writes. It must measure its own CPU, memory, and write overhead.

### Resource Correlation

Associates job/experiment intervals with telemetry samples by monotonic
timestamps. It computes factual summaries from observed deltas and
distributions; it must not infer activity from operation names alone.

### Results Store

Use SQLite for application metadata, lifecycle state, scheduler decisions,
telemetry indexes, and report references. Use DuckDB for analytical queries
over Parquet and exported result data when that provides a clear benefit.
This avoids forcing one database to perform both transactional metadata and
columnar analysis.

### Report Generator

Produces self-contained HTML from stored experiment metadata, results, job
timings, telemetry, scheduler decisions, and timeline data. Generated prose
contains measured statements with units and intervals, not subjective scores.

### Web API and Frontend

FastAPI exposes typed REST endpoints for datasets, analyses, pipelines,
experiments, jobs, reports, system state, and capability discovery. WebSocket
or SSE streams live telemetry and job events; aggressive polling is avoided.
React/TypeScript renders the dark-first dashboard, DAG, experiment history,
headroom measurements, and compute timeline. The backend remains functional
when no browser is connected.

## Data Flow

```text
source file / generator
        |
        v
Dataset registry + Parquet/SQLite/DuckDB metadata
        |
        v
Pipeline definition -> validated DAG -> bounded scheduler
                                      |
                        +-------------+-------------+
                        v                           v
                 CPU/Polars backend          optional OpenCL backend
                        |                           |
                        +-------------+-------------+
                                      v
                          results + job measurements
                                      |
                  Linux Observatory samples continuously
                                      |
                  correlation -> timeline -> HTML/API/dashboard
```

Large inputs should remain lazy or chunked until an operation genuinely
requires materialization. Metadata and result references are persisted;
large intermediate values are file-backed or bounded.

## Job Lifecycle

```text
created -> queued -> ready -> running -> completed
                         |       |
                         |       +-> failed
                         |       +-> cancelled
                         +-> skipped
```

Each job records monotonic and wall timestamps, backend, input/output
metadata, cancellation/error information, wall time, CPU time where
meaningful, memory observations, and resource correlation identifiers.

Submission is bounded by queue and in-flight limits. Cancellation prevents
new submissions, is checked between chunks, and performs executor/process
cleanup. Shutdown stops intake, drains or cancels pending work according to
policy, joins children, closes files/devices, and preserves terminal states.

## Pipeline Lifecycle

The DAG is validated before scheduling: node IDs are unique, dependencies
exist, cycles are rejected, and operation parameters are schema-checked.
`pending` nodes become `ready` only after all dependencies complete.
Independent ready nodes may run concurrently within scheduler limits.
Downstream nodes of failed/cancelled dependencies are explicitly skipped or
cancelled with a reason.

## Telemetry Architecture

The observatory samples system, process, worker, disk, memory, thermal, and
available GPU metrics using a monotonic clock. Each sample has a timestamp,
source, metric name, value or `null`, and availability/error detail.

The sampler publishes a bounded live stream and appends batches to storage.
Telemetry collection is isolated from analytical workers so a sensor or
database failure degrades observability without killing compute. A supervisor
records sampler failures and retries with bounded backoff.

## Database Architecture

SQLite is the system of record for:

- dataset, pipeline, experiment, job, and report metadata
- state transitions and errors
- scheduler decisions
- telemetry batch indexes and sampled records

DuckDB reads Parquet and analytical result files for profiling and reports.
Transactions are batched for telemetry; there is no transaction per metric.
Database access is isolated behind repositories so storage choices remain
replaceable and testable.

## OpenCL Abstraction

Startup capability discovery is lazy or bounded and records platform/device
properties without assuming a particular product. The application starts
with no OpenCL, with a CPU fallback. Each accelerated operation has:

1. CPU reference calculation
2. host preparation
3. optional host/device transfer
4. kernel execution
5. optional device/host transfer
6. numerical equivalence validation

These phases and total elapsed time are measured separately where possible.
Compilation, dispatch, transfer, and synchronization overhead are included
for small workloads.

## Failure Handling

- Malformed datasets are rejected with structured validation errors.
- A worker exception marks its job failed and leaves the scheduler alive.
- OpenCL initialization, kernel, or validation failure records the error and
  falls back to CPU when the operation permits it.
- Missing sensors/utilities produce unavailable metrics.
- Telemetry storage failure is logged and buffered within a fixed bound; it
  does not stop safe running analysis.
- API client disconnects do not cancel backend work unless explicitly
  requested.
- Report failures leave experiment results and diagnostic errors intact.

## Shutdown Behavior

One application supervisor owns service startup and shutdown ordering:

1. Stop accepting new API/CLI work.
2. Request telemetry sampler stop.
3. Stop scheduler intake and apply cancellation policy.
4. Await bounded worker/child cleanup.
5. Flush bounded telemetry and metadata batches.
6. Close database connections, files, and optional device resources.
7. Emit a final structured shutdown record.

Shutdown has a bounded timeout and surfaces incomplete cleanup rather than
pretending success.

## Architecture Review and Simplifications

The initial proposal was simplified in these ways:

- No microservices: local process boundaries are unnecessary before scale or
  deployment needs exist.
- No separate message broker: bounded in-process queues plus SQLite/DuckDB are
  sufficient for a single-user local application.
- No mandatory database duplication: SQLite metadata and DuckDB/Parquet
  analytics have distinct responsibilities.
- No generic plugin framework initially: typed backend and operation
  interfaces are enough; plugins can follow demonstrated extension needs.
- No adaptive worker preemption: only future scheduling is adjusted, avoiding
  disruption and orphan cleanup complexity.
- No fabricated single “performance score”: factual measurements remain
  comparable and explainable.

The architecture is independently testable at the repository, operation,
backend, scheduler, observatory, and API boundaries. Implementation should
start with the skeleton and observatory contracts, then add useful work
incrementally.
