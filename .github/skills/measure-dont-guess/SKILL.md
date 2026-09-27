---
name: measure-dont-guess
description: Use when optimizing, profiling, benchmarking, comparing implementations, investigating system performance, or diagnosing resource usage.
---

# Measure, Don't Guess

## Core Rule

**Measure before optimizing.** Do not infer performance from how an implementation looks or from the presence of concurrency, vectorization, asynchronous code, multiprocessing, OpenCL, or GPU execution.

## Performance Investigation Procedure

For every investigation:

1. Establish a baseline using the current or reference implementation.
2. Record wall-clock execution time.
3. Record process CPU time where meaningful.
4. Record CPU utilization.
5. Record peak or working memory where possible.
6. Record disk I/O for data-heavy operations.
7. Record the input size and relevant workload characteristics.
8. Repeat measurements when variability could affect the result.
9. Verify correctness and compare equivalent outputs before comparing speed.
10. Report actual measurements with units.

Use the same environment, input, warm-up policy, measurement boundaries, and output validation for baseline and candidate runs. Preserve raw measurements when practical so results can be reproduced.

## Find the Bottleneck

Classify the dominant limitation before changing code:

- CPU-bound
- Memory-bandwidth-bound
- Allocation-bound
- Disk-I/O-bound
- Synchronization-bound
- GPU-transfer-bound

Profile first, identify the dominant bottleneck, and modify only after evidence supports the change. Do not optimize code merely because it appears inefficient.

## CPU and OpenCL Comparisons

When comparing CPU and OpenCL implementations, measure these phases separately where applicable:

1. Host preparation
2. Host-to-device transfer
3. Kernel execution
4. Device-to-host transfer
5. Total elapsed time

Verify CPU and accelerated outputs against each other within an appropriate numerical tolerance before treating a timing comparison as valid. For small workloads, explicitly account for setup, dispatch, compilation, synchronization, and transfer overhead; acceleration may not offset those fixed costs.

## Measurement Quality

- Never generate arbitrary benchmark scores or report invented measurements.
- State the tool, units, input size, number of repetitions, and aggregation method.
- Include variability such as minimum/median/mean and spread when repeated runs are useful.
- Separate cold-start and warmed-up measurements when initialization affects results.
- Call out confounding factors such as background load, thermal throttling, cache state, filesystem cache, device frequency changes, or different compiler settings.
- If evidence is insufficient to support a conclusion, say so and collect additional measurements instead of guessing.

## After an Optimization

1. Rerun correctness tests.
2. Rerun the exact same measurement procedure.
3. Compare the candidate against the baseline.
4. Confirm that output quality, resource usage, and relevant behavior remain acceptable.
5. Document the measured result, workload, environment, and any trade-offs.

An optimization is supported only when the measured comparison is valid and the outputs are equivalent within the required tolerance. More threads, multiprocessing, SIMD/vectorization, OpenCL/GPU execution, or asynchronous code are implementation techniques—not evidence of a speedup.

## Example Report

```text
Workload: 256 MiB input, 10 repetitions after 2 warm-ups
Environment: 8 logical CPUs, 16 GiB RAM, compiler X.Y

Metric                  Baseline        Candidate
Total wall time         1.84 s          1.21 s
Process CPU time        1.79 s          2.96 s
Peak RSS                410 MiB         690 MiB
Disk read               256 MiB         256 MiB
Output validation       pass            pass

Conclusion: candidate reduced wall time by 34%, but increased CPU time and
peak memory. The result is workload-specific and does not establish a
general speedup.
```
