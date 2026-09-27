---
name: resource-safe-execution
description: Use when developing or reviewing computationally intensive Linux applications on resource-constrained laptops, especially concurrency, multiprocessing, large-data, numerical, OpenCL, or background-job code.
---

# Resource-Safe Execution

Design computational work to preserve desktop responsiveness and remain bounded on Linux laptops with limited CPU, memory, and thermal headroom.

## When to Apply

Invoke this skill whenever a change introduces or modifies:

- Threads, processes, task queues, executors, or background jobs
- Large-data ingestion, transformation, or storage
- CPU-intensive numerical or image/audio/video processing
- OpenCL or other accelerator workloads
- Performance modes, batching, or parallel algorithms
- Tests or benchmarks for any of the above

## Core Requirements

1. Perform useful application work only. Never add artificial CPU/GPU stress, infinite compute loops, or workloads whose purpose is to consume resources.
2. Bound every thread pool, process pool, queue, batch, retry policy, and cache. Never create an unbounded pool or producer.
3. Estimate memory before large allocations. Prefer streaming, chunking, lazy evaluation, iterators, and memory mapping; avoid intentionally exhausting RAM or triggering swapping.
4. Make worker counts configurable. The default should leave at least one logical CPU available for the desktop, and should account for current CPU load, available RAM, and existing workers before increasing concurrency.
5. Support cancellation and graceful shutdown. Propagate cancellation, stop accepting new work, join or await children, close resources, and clean up child processes on success, cancellation, and failure.
6. Avoid requiring root privileges. Do not alter CPU governors, clocks, thermal limits, fan controls, or other hardware-management settings.
7. Measure resource consumption rather than manipulating hardware management. Record useful measurements such as elapsed time, peak RSS, queue depth, CPU utilization, and accelerator memory where available.
8. Performance modes may use more resources, but must remain bounded and must not compromise desktop responsiveness.
9. Tests must use small, representative workloads. Do not use brute force or stress-only loops to validate correctness.
10. Optimize from measurements: establish a baseline, change one relevant factor, measure again, and retain an optimization only when the result is demonstrably useful.

## Implementation Checklist

Before implementing:

- Identify the largest data structures and estimate their peak memory footprint.
- Determine whether the work can be streamed or processed in bounded chunks.
- Choose a bounded concurrency limit and document how it is derived.
- Define cancellation, shutdown, timeout, and child-process cleanup behavior.
- Decide which resource metrics are needed to validate the change.

While implementing:

- Use a bounded executor or queue with explicit backpressure.
- Prefer `min(configured_workers, max(1, logical_cpus - 1))` as a starting point, then consider memory and current load.
- Check cancellation between chunks and before submitting additional work.
- Ensure worker exceptions and cancellation are visible to the caller; do not silently return partial success.
- Release mappings, buffers, file descriptors, GPU/OpenCL objects, and temporary files promptly.
- Keep privileged operations out of the design.

Before completing:

- Test cancellation and shutdown, including an exception path.
- Verify that child processes and threads do not remain alive after the operation.
- Measure peak memory and CPU behavior on a small representative input.
- Confirm that defaults leave desktop capacity and that configured performance modes remain bounded.

## Examples

### Bounded, cancellable processing

```python
workers = min(config.workers, max(1, os.cpu_count() - 1))
with ProcessPoolExecutor(max_workers=workers) as pool:
    for chunk in bounded_chunks(input_stream, config.chunk_size):
        cancellation.raise_if_cancelled()
        pending.append(pool.submit(process_chunk, chunk))
        if len(pending) >= config.max_in_flight:
            yield pending.pop(0).result()
```

The input is streamed, in-flight work is capped, and cancellation is checked before more work is submitted.

### Unsafe pattern to reject

```python
while True:
    executor.submit(expensive_function)
```

This creates unbounded work and resource consumption. Replace it with finite useful work, bounded submission, backpressure, cancellation, and explicit shutdown.

### Review guidance

When reviewing code, explicitly identify violations of these principles. Report the affected file and behavior, such as an unbounded queue, an allocation made without a memory estimate, a default worker count that consumes every logical CPU, missing child cleanup, or a benchmark that exists only to create load. Distinguish measured regressions from unmeasured performance claims.
