"""Typed records for dataset sources, profiles, and workload results."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class DatasetSource:
    path: Path
    format: str
    table: str | None = None


@dataclass(frozen=True, slots=True)
class DatasetFingerprint:
    algorithm: str
    digest: str
    size_bytes: int
    modified_ns: int


@dataclass(frozen=True, slots=True)
class ResourceEstimate:
    source_size_bytes: int
    estimated_scan_bytes: int
    working_memory_bytes: int
    temporary_storage_bytes: int


@dataclass(frozen=True, slots=True)
class ColumnProfile:
    name: str
    inferred_type: str
    nullable: bool
    null_count: int
    numeric_count: int
    minimum: float | str | None
    maximum: float | str | None
    mean: float | None
    sample_values: tuple[Any, ...]
    distinct_values: tuple[Any, ...]
    distinct_truncated: bool


@dataclass(frozen=True, slots=True)
class ProfileResult:
    row_count: int
    complete: bool
    columns: tuple[ColumnProfile, ...]
    validation_errors: tuple[str, ...]
    validation_errors_truncated: bool


@dataclass(frozen=True, slots=True)
class TelemetrySummary:
    enabled: bool
    sample_count: int
    coverage: str
    cpu_utilization_percent: tuple[float, ...]
    memory_utilization_percent: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class WorkloadTiming:
    wall_start: str
    wall_end: str
    monotonic_start: float
    monotonic_end: float
    elapsed_seconds: float
    cpu_seconds: float | None


@dataclass(frozen=True, slots=True)
class WorkloadResult:
    status: str
    operation: str
    source: DatasetSource
    fingerprint: DatasetFingerprint | None
    estimate: ResourceEstimate | None
    profile: ProfileResult | None
    timing: WorkloadTiming | None
    telemetry: TelemetrySummary
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        from dataclasses import asdict

        result = asdict(self)
        result["source"]["path"] = str(self.source.path)
        return result
