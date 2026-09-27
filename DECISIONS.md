# NEXUS Architecture Decisions

This file records lightweight Architecture Decision Records. Decisions are
based on the Phase 0 architecture review and may be superseded by a later
record with a reason.

## ADR-0001: CPU-First Optional Acceleration

- **Status:** Accepted
- **Decision:** CPU execution is the trusted baseline and OpenCL is an
  optional capability/backend.
- **Reason:** NEXUS must work on Linux systems without OpenCL or Intel GPUs.
  Integrated GPU acceleration may lose to CPU execution after transfer and
  dispatch overhead.
- **Consequence:** Every accelerated operation needs a CPU implementation,
  numerical equivalence validation, capability discovery, and phase-level
  measurements.

## ADR-0002: SQLite Metadata with DuckDB/Parquet Analytics

- **Status:** Accepted
- **Decision:** Use SQLite for transactional application metadata and
  lifecycle state; use DuckDB over Parquet/result files for analytical scans
  where useful.
- **Reason:** These workloads have different access patterns. SQLite is a
  small reliable local system of record; DuckDB and Parquet avoid forcing
  analytical scans through an OLTP schema.
- **Consequence:** Storage access goes through repository/query boundaries.
  Telemetry writes are batched and migrations are explicit.

## ADR-0003: One Local Process Initially

- **Status:** Accepted
- **Decision:** Start with one locally managed application process rather than
  microservices or a message broker.
- **Reason:** NEXUS is a single-user local observatory. Extra deployment and
  failure boundaries would add complexity before scale or remote operation is
  required.
- **Consequence:** Internal interfaces must still be explicit and typed so
  components can be isolated in tests and separated later if evidence
  warrants it.

## ADR-0004: Bounded In-Process Scheduling

- **Status:** Accepted
- **Decision:** Use bounded queues and conservatively sized thread/process
  executors with configurable limits.
- **Reason:** Resource-safe execution and desktop responsiveness are
  non-negotiable. `os.cpu_count()` must not be used blindly, and unlimited
  producers can exhaust memory or leave orphaned work.
- **Consequence:** Queue depth, in-flight chunks, worker limits, retries, and
  shutdown timeouts are configuration values with safe defaults. Cancellation
  is cooperative and child cleanup is tested.

## ADR-0005: Adaptive Scheduling Does Not Preempt Healthy Work

- **Status:** Accepted
- **Decision:** Adaptive mode adjusts desired future concurrency and delays
  new launches; it does not terminate healthy running jobs solely because
  utilization rises.
- **Reason:** Preemption would risk partial analytical results, complex
  cleanup, and misleading measurements. Headroom changes are better handled
  at scheduling boundaries.
- **Consequence:** Decisions record prior/new desired concurrency, reason, and
  measurements. The UI explains held work factually.

## ADR-0006: Monotonic Correlation Clock

- **Status:** Accepted
- **Decision:** Use monotonic timestamps for job/telemetry interval correlation,
  while retaining wall-clock timestamps for user-facing records.
- **Reason:** Wall-clock adjustments can make intervals negative or overlap
  incorrectly. Monotonic time provides stable elapsed durations.
- **Consequence:** Records carry both clocks where available; reports use
  wall time for presentation and monotonic deltas for measurements.

## ADR-0007: Bounded Live Telemetry and Batched Persistence

- **Status:** Accepted
- **Decision:** Maintain a bounded in-memory ring buffer, stream live updates
  through WebSocket or SSE, and batch historical database writes.
- **Reason:** A transaction per metric or unbounded event history would make
  the observatory distort the workload it observes.
- **Consequence:** Old live samples may be evicted by policy; persisted
  batches have explicit failure handling and the observatory overhead is
  measured.

## ADR-0008: No Hardware-Management Side Effects

- **Status:** Accepted
- **Decision:** NEXUS only observes Linux and hardware capabilities; it never
  changes governors, clocks, power/thermal limits, fan behavior, kernel
  parameters, or thermal protections.
- **Reason:** The mission is to observe realistic workload behavior while
  preserving safety and user control. Ordinary operation must not require
  root.
- **Consequence:** ECO/BALANCED/PERFORMANCE/CUSTOM are bounded scheduling
  policies, not power modes. Measurements must report actual conditions.

## ADR-0009: Measurement Before Optimization

- **Status:** Accepted
- **Decision:** Establish a baseline, validate equivalent outputs, measure
  wall/CPU/resource behavior, identify the bottleneck, then optimize and
  repeat the same measurement.
- **Reason:** Threads, multiprocessing, SIMD, asynchronous code, and GPU
  execution do not establish a speedup by themselves.
- **Consequence:** Performance claims include input size, units, repetitions,
  environment, variability, and trade-offs. Unsupported conclusions are
  explicitly reported as insufficient evidence.

## ADR-0010: Skills Are Engineering Policy

- **Status:** Accepted
- **Decision:** Relevant project skills must be read before implementing a
  governed subsystem, and intentional deviations must be documented and
  tested.
- **Reason:** Resource safety and measurement constraints are cross-cutting
  correctness requirements, not optional style guidance.
- **Consequence:** Missing skills are tracked as Phase 0/Phase 1 work. The
  currently available skills are `resource-safe-execution` and
  `measure-dont-guess`.
