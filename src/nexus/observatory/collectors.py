"""Bounded collectors for Linux procfs and sysfs interfaces."""

from dataclasses import dataclass
from datetime import datetime, timezone
import glob
import os
from pathlib import Path
import re
import time
from typing import Callable, Iterable, Mapping

from .models import (
    CpuTelemetry,
    DiskTelemetry,
    MemoryTelemetry,
    PressureTelemetry,
    ProcessSnapshot,
    TelemetrySample,
    ThermalSensor,
    unavailable_cpu,
)

ReadText = Callable[[Path], str | None]


def read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


@dataclass(frozen=True, slots=True)
class CpuCounters:
    name: str
    user: int
    system: int
    idle: int
    iowait: int


def parse_proc_stat(text: str) -> tuple[CpuCounters, ...]:
    counters: list[CpuCounters] = []
    for line in text.splitlines():
        fields = line.split()
        if not fields or fields[0] != "cpu" and not re.fullmatch(r"cpu\d+", fields[0]):
            continue
        try:
            values = [int(value) for value in fields[1:]]
            if len(values) < 4:
                continue
            counters.append(CpuCounters(fields[0], values[0], values[2], values[3], values[4] if len(values) > 4 else 0))
        except ValueError:
            continue
    return tuple(counters)


def _bounded_percent(value: float) -> float:
    return max(0.0, min(100.0, value))


class CpuCollector:
    def __init__(self, read: ReadText = read_text) -> None:
        self._read = read
        self._previous: dict[str, CpuCounters] = {}

    def collect_with_counters(self) -> CpuTelemetry:
        """Collect utilization and cumulative seconds from the same counter delta."""
        counters = parse_proc_stat(self._read(Path("/proc/stat")) or "")
        if not counters:
            return unavailable_cpu()
        previous = self._previous
        self._previous = {counter.name: counter for counter in counters}
        deltas: list[float | None] = []
        aggregate_delta_seconds: list[tuple[float, float, float, float] | None] = []
        for current in counters:
            old = previous.get(current.name)
            if old is None:
                deltas.append(None)
                aggregate_delta_seconds.append(None)
                continue
            values = [current.user - old.user, current.system - old.system, current.idle - old.idle, current.iowait - old.iowait]
            if any(value < 0 for value in values):
                deltas.append(None)
                aggregate_delta_seconds.append(None)
                continue
            total = sum(values)
            deltas.append(_bounded_percent((total - values[2]) * 100 / total) if total else None)
            aggregate_delta_seconds.append(tuple(value / os.sysconf("SC_CLK_TCK") for value in values))
        load = _load_average(self._read)
        frequencies = _frequencies()
        aggregate = aggregate_delta_seconds[0] if aggregate_delta_seconds else None
        return CpuTelemetry(
            deltas[0], tuple(deltas[1:]),
            aggregate[0] if aggregate else None,
            aggregate[1] if aggregate else None,
            aggregate[2] if aggregate else None,
            aggregate[3] if aggregate else None,
            *load, frequencies[0], frequencies[1],
        )


def _load_average(read: ReadText) -> tuple[float | None, float | None, float | None]:
    text = read(Path("/proc/loadavg"))
    if not text:
        return None, None, None
    try:
        values = text.split()[:3]
        if len(values) != 3:
            return None, None, None
        return float(values[0]), float(values[1]), float(values[2])
    except (TypeError, ValueError):
        return None, None, None


def _frequencies() -> tuple[float | None, tuple[float | None, ...]]:
    values: list[float | None] = []
    for path in sorted(glob.glob("/sys/devices/system/cpu/cpu[0-9]*/cpufreq/scaling_cur_freq")):
        try:
            values.append(float(Path(path).read_text().strip()) / 1000)
        except (OSError, ValueError):
            values.append(None)
    available = [value for value in values if value is not None]
    return (sum(available) / len(available) if available else None, tuple(values))


def parse_meminfo(text: str) -> Mapping[str, int]:
    values: dict[str, int] = {}
    for line in text.splitlines():
        key, separator, remainder = line.partition(":")
        if not separator:
            continue
        try:
            number, unit = (remainder.strip().split() + ["kB"])[:2]
            multiplier = {"kB": 1024, "MB": 1024**2, "GB": 1024**3}.get(unit, 1)
            values[key.strip()] = int(number) * multiplier
        except (TypeError, ValueError):
            continue
    return values


def collect_memory(read: ReadText = read_text) -> MemoryTelemetry:
    values = parse_meminfo(read(Path("/proc/meminfo")) or "")
    total, available = values.get("MemTotal"), values.get("MemAvailable")
    swap_total, swap_free = values.get("SwapTotal"), values.get("SwapFree")
    used = total - available if total is not None and available is not None else None
    swap_used = swap_total - swap_free if swap_total is not None and swap_free is not None else None
    return MemoryTelemetry(total, available, used, _ratio(used, total), swap_total, swap_free, swap_used, _ratio(swap_used, swap_total))


def _ratio(numerator: int | None, denominator: int | None) -> float | None:
    return _bounded_percent(numerator * 100 / denominator) if numerator is not None and denominator else None


def parse_pressure(text: str) -> PressureTelemetry:
    values: dict[str, float | int | None] = {key: None for key in ("some_avg10", "some_avg60", "some_avg300", "some_total_us", "full_avg10", "full_avg60", "full_avg300", "full_total_us")}
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        prefix = parts[0]
        if prefix not in {"some", "full"}:
            continue
        for item in parts[1:]:
            key, separator, value = item.partition("=")
            if not separator:
                continue
            field = f"{prefix}_{'total_us' if key == 'total' else key}"
            if field not in values:
                continue
            try:
                values[field] = float(value) if key != "total" else int(value)
            except ValueError:
                continue
    return PressureTelemetry(**values)


def collect_pressure(kind: str, read: ReadText = read_text) -> PressureTelemetry | None:
    text = read(Path(f"/proc/pressure/{kind}"))
    return parse_pressure(text) if text else None


def collect_thermals(read: ReadText = read_text, paths: Iterable[str] | None = None) -> tuple[ThermalSensor, ...]:
    candidates = (
        list(paths)
        if paths is not None
        else glob.glob("/sys/class/thermal/thermal_zone*/temp")
        + glob.glob("/sys/class/hwmon/hwmon*/temp*_input")
    )
    sensors: list[ThermalSensor] = []
    for raw_path in candidates:
        path = Path(raw_path)
        raw = read(path)
        try:
            raw_value = float(raw.strip()) if raw else None
            value = raw_value / 1000 if raw_value is not None else None
        except (TypeError, ValueError):
            continue
        if value is None or value < -100 or value > 200:
            continue
        if path.name == "temp":
            label_path = path.parent / "type"
            identifier = path.parent.name
        else:
            sensor_number = path.name.removesuffix("_input")
            label_path = path.parent / f"{sensor_number}_label"
            identifier = f"{path.parent.name}/{sensor_number}"
            fault = _hwmon_flag(read(path.parent / f"{sensor_number}_fault"))
            enabled = _hwmon_flag(read(path.parent / f"{sensor_number}_enable"))
            if fault is True or enabled is False:
                continue
            if raw_value == 0 and not (fault is False and enabled is True):
                continue
        label = read(label_path) or read(path.parent / "name")
        sensors.append(ThermalSensor(identifier, label.strip() if label else None, value))
    return tuple(sensors)


def _hwmon_flag(value: str | None) -> bool | None:
    """Parse an optional hwmon boolean status file.

    Missing or malformed metadata leaves the input usable; a valid fault or
    disabled flag is the kernel's evidence that the channel is unavailable.
    """
    if value is None:
        return None
    normalized = value.strip()
    if normalized == "0":
        return False
    if normalized == "1":
        return True
    return None


def parse_diskstats(text: str) -> tuple[DiskTelemetry, ...]:
    devices: list[DiskTelemetry] = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 11:
            continue
        try:
            devices.append(DiskTelemetry(fields[2], int(fields[5]) * 512, int(fields[9]) * 512))
        except ValueError:
            continue
    return tuple(devices)


def collect_disks(read: ReadText = read_text) -> tuple[DiskTelemetry, ...]:
    return parse_diskstats(read(Path("/proc/diskstats")) or "")


def process_snapshot(
    limit: int = 32,
    read: ReadText = read_text,
    paths: Iterable[str] | None = None,
) -> tuple[ProcessSnapshot, ...]:
    if limit < 1:
        raise ValueError("process limit must be at least 1")
    result: list[ProcessSnapshot] = []
    candidates = list(paths) if paths is not None else glob.glob("/proc/[0-9]*")
    for raw_path in sorted(candidates, key=lambda path: int(Path(path).name))[:limit]:
        pid = int(Path(raw_path).name)
        status = _proc_status(Path(raw_path), read)
        stat = read(Path(raw_path) / "stat")
        if not status and stat is None:
            continue
        result.append(ProcessSnapshot(pid, status.get("Name"), status.get("State"), _proc_cpu_seconds(stat), _proc_value(status, "VmRSS", 1024), _proc_value(status, "Threads", 1)))
    return tuple(result)


def _proc_status(path: Path, read: ReadText) -> dict[str, str]:
    text = read(path / "status") or ""
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key] = value.strip().split()[0] if value.strip() else ""
    return values


def _proc_value(values: Mapping[str, str], key: str, multiplier: int) -> int | None:
    try:
        return int(values[key]) * multiplier
    except (KeyError, TypeError, ValueError):
        return None


def _proc_cpu_seconds(stat: str | None) -> float | None:
    if not stat:
        return None
    closing = stat.rfind(")")
    fields = stat[closing + 2 :].split() if closing >= 0 else []
    try:
        return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")
    except (IndexError, TypeError, ValueError, OSError):
        return None


def collect_sample(cpu: CpuCollector, process_limit: int | None = None) -> TelemetrySample:
    monotonic = time.monotonic()
    return TelemetrySample(
        datetime.now(timezone.utc), monotonic, cpu.collect_with_counters(), collect_memory(),
        collect_pressure("cpu"), collect_pressure("memory"), collect_pressure("io"),
        collect_thermals(), collect_disks(), process_snapshot(process_limit) if process_limit is not None else None,
    )
