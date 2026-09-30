"""Immutable, reusable telemetry records."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class CpuTelemetry:
    utilization_percent: float | None
    per_cpu_utilization_percent: tuple[float | None, ...]
    user_seconds: float | None
    system_seconds: float | None
    idle_seconds: float | None
    iowait_seconds: float | None
    load_1m: float | None
    load_5m: float | None
    load_15m: float | None
    frequency_mhz: float | None
    per_cpu_frequency_mhz: tuple[float | None, ...]


@dataclass(frozen=True, slots=True)
class MemoryTelemetry:
    total_bytes: int | None
    available_bytes: int | None
    used_bytes: int | None
    utilization_percent: float | None
    swap_total_bytes: int | None
    swap_free_bytes: int | None
    swap_used_bytes: int | None
    swap_utilization_percent: float | None


@dataclass(frozen=True, slots=True)
class PressureTelemetry:
    some_avg10: float | None
    some_avg60: float | None
    some_avg300: float | None
    some_total_us: int | None
    full_avg10: float | None
    full_avg60: float | None
    full_avg300: float | None
    full_total_us: int | None


@dataclass(frozen=True, slots=True)
class ThermalSensor:
    identifier: str
    label: str | None
    celsius: float | None


@dataclass(frozen=True, slots=True)
class DiskTelemetry:
    device: str
    read_bytes: int | None
    write_bytes: int | None


@dataclass(frozen=True, slots=True)
class ProcessSnapshot:
    pid: int
    name: str | None
    state: str | None
    cpu_time_seconds: float | None
    resident_bytes: int | None
    thread_count: int | None


@dataclass(frozen=True, slots=True)
class TelemetrySample:
    wall_timestamp: datetime
    monotonic_timestamp: float
    cpu: CpuTelemetry
    memory: MemoryTelemetry
    pressure_cpu: PressureTelemetry | None
    pressure_memory: PressureTelemetry | None
    pressure_io: PressureTelemetry | None
    thermal: tuple[ThermalSensor, ...]
    disks: tuple[DiskTelemetry, ...]
    processes: tuple[ProcessSnapshot, ...] | None = None


def unavailable_cpu() -> CpuTelemetry:
    return CpuTelemetry(None, (), None, None, None, None, None, None, None, None, ())


def unavailable_memory() -> MemoryTelemetry:
    return MemoryTelemetry(None, None, None, None, None, None, None, None)
