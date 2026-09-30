"""Synchronous profiling workload with optional Phase 2 telemetry."""

from datetime import datetime, timezone
import time

from ..observatory import Sampler
from .fingerprints import fingerprint
from .models import TelemetrySummary, WorkloadResult, WorkloadTiming
from .profiling import profile
from .sources import DatasetError, validate_source


def profile_dataset(
    source,
    *,
    max_rows: int | None = None,
    telemetry: bool = True,
    interval_seconds: float = 1.0,
    history_capacity: int = 16,
    fingerprint_chunk_size: int = 1024 * 1024,
    inference_rows: int = 100,
    sample_values: int = 5,
    distinct_values: int = 32,
    sampler_factory=None,
) -> WorkloadResult:
    from .requirements import estimate

    requested_source = source
    make_sampler = sampler_factory or Sampler
    wall_start = datetime.now(timezone.utc)
    monotonic_start = time.monotonic()
    cpu_start = time.process_time()
    sampler = make_sampler(interval_seconds, history_capacity) if telemetry else None
    if sampler:
        sampler.start()
    source = requested_source
    digest = None
    resource_estimate = None
    result = None
    try:
        source = validate_source(requested_source)
        digest = fingerprint(source.path, fingerprint_chunk_size)
        resource_estimate = estimate(source)
        result = profile(
            source,
            max_rows=max_rows,
            inference_rows=inference_rows,
            sample_values=sample_values,
            distinct_values=distinct_values,
        )
        status = "completed"
        error = None
    except KeyboardInterrupt:
        status = "cancelled"
        result = None
        error = "profile cancelled"
    except (DatasetError, OSError, ValueError) as exc:
        status = "failed"
        result = None
        error = str(exc)
    finally:
        monotonic_end = time.monotonic()
        wall_end = datetime.now(timezone.utc)
        cpu_end = time.process_time()
        if sampler:
            sampler.stop()
    samples = (
        tuple(
            sample
            for sample in sampler.history
            if monotonic_start <= sample.monotonic_timestamp <= monotonic_end
        )
        if sampler
        else ()
    )
    cpu_values = tuple(sample.cpu.utilization_percent for sample in samples if sample.cpu.utilization_percent is not None)
    memory_values = tuple(sample.memory.utilization_percent for sample in samples if sample.memory.utilization_percent is not None)
    coverage = "sufficient" if len(samples) >= 2 else "insufficient"
    return WorkloadResult(
        status,
        "profile",
        source,
        digest,
        resource_estimate,
        result,
        WorkloadTiming(
            wall_start.isoformat(),
            wall_end.isoformat(),
            monotonic_start,
            monotonic_end,
            monotonic_end - monotonic_start,
            cpu_end - cpu_start,
        ),
        TelemetrySummary(telemetry, len(samples), coverage, cpu_values, memory_values),
        error,
    )
