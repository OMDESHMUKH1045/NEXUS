from datetime import datetime, timezone
from pathlib import Path
import time

import pytest

from nexus.observatory.collectors import (
    CpuCollector,
    collect_memory,
    collect_disks,
    collect_pressure,
    collect_thermals,
    parse_meminfo,
    parse_diskstats,
    parse_proc_stat,
    process_snapshot,
)
from nexus.observatory.models import (
    CpuTelemetry,
    MemoryTelemetry,
    PressureTelemetry,
    ThermalSensor,
    TelemetrySample,
)
from nexus.observatory.sampler import Sampler


def test_proc_stat_parsing_and_delta_utilization(monkeypatch: pytest.MonkeyPatch) -> None:
    readings = iter(
        (
            "cpu  10 0 10 80 0\ncpu0 5 0 5 40 0\n",
            "cpu  20 0 20 90 0\ncpu0 10 0 10 45 0\n",
        )
    )
    monkeypatch.setattr(
        "nexus.observatory.collectors._load_average",
        lambda _read: (1.0, 2.0, 3.0),
    )
    monkeypatch.setattr(
        "nexus.observatory.collectors._frequencies",
        lambda: (None, ()),
    )
    collector = CpuCollector(lambda _path: next(readings))
    assert collector.collect_with_counters().utilization_percent is None
    sample = collector.collect_with_counters()
    assert sample.utilization_percent == pytest.approx(66.6666667)
    assert sample.user_seconds == pytest.approx(0.1)
    assert sample.idle_seconds == pytest.approx(0.1)


def test_proc_stat_ignores_malformed_and_missing_fields() -> None:
    parsed = parse_proc_stat("cpu bad\ncpu1 1 2\ncpu2 1 2 3 4 5\n")
    assert parsed[0].name == "cpu2"
    assert parsed[0].iowait == 5


def test_memory_uses_mem_available_and_swap() -> None:
    values = parse_meminfo(
        "MemTotal: 100 kB\nMemAvailable: 40 kB\nSwapTotal: 80 kB\nSwapFree: 30 kB\n"
    )
    assert values["MemAvailable"] == 40 * 1024
    memory = collect_memory(lambda _path: "MemTotal: 100 kB\nMemAvailable: 40 kB\nSwapTotal: 80 kB\nSwapFree: 30 kB\n")
    assert memory.used_bytes == 60 * 1024
    assert memory.swap_used_bytes == 50 * 1024
    assert memory.utilization_percent == 60.0


def test_pressure_parser_allows_missing_full_record() -> None:
    pressure = collect_pressure(
        "cpu",
        lambda _path: (
            "some avg10=1.00 avg60=2.00 avg300=3.00 total=4\n"
            "full avg10=5.00 avg60=6.00 avg300=7.00 total=8\n"
        ),
    )
    assert pressure == PressureTelemetry(1.0, 2.0, 3.0, 4, 5.0, 6.0, 7.0, 8)


def test_pressure_parser_preserves_missing_full_record() -> None:
    pressure = collect_pressure(
        "cpu",
        lambda _path: "some avg10=1.00 avg60=2.00 avg300=3.00 total=4\n",
    )
    assert pressure is not None
    assert pressure.some_total_us == 4
    assert pressure.full_total_us is None


def test_thermal_parser_skips_invalid_and_missing_labels() -> None:
    values = {
        Path("/thermal_zone0/temp"): "42000",
        Path("/thermal_zone0/type"): "Package",
        Path("/thermal_zone1/temp"): "not-a-temperature",
    }
    sensors = collect_thermals(
        lambda path: values.get(path),
        ["/thermal_zone0/temp", "/thermal_zone1/temp"],
    )
    assert len(sensors) == 1
    assert sensors[0].label == "Package"
    assert sensors[0].celsius == 42.0


def test_thermal_parser_supports_hwmon_input_and_label() -> None:
    values = {
        Path("/sys/class/hwmon/hwmon0/temp1_input"): "39000",
        Path("/sys/class/hwmon/hwmon0/temp1_label"): "CPU",
        Path("/sys/class/hwmon/hwmon0/name"): "coretemp",
    }
    sensors = collect_thermals(
        lambda path: values.get(path),
        ["/sys/class/hwmon/hwmon0/temp1_input"],
    )
    assert sensors == (ThermalSensor("hwmon0/temp1", "CPU", 39.0),)


def test_thermal_parser_skips_faulted_or_disabled_hwmon_channels() -> None:
    values = {
        Path("/sys/class/hwmon/hwmon0/temp1_input"): "0",
        Path("/sys/class/hwmon/hwmon0/temp1_fault"): "1",
        Path("/sys/class/hwmon/hwmon0/temp2_input"): "0",
        Path("/sys/class/hwmon/hwmon0/temp2_enable"): "0",
    }
    sensors = collect_thermals(
        lambda path: values.get(path),
        [
            "/sys/class/hwmon/hwmon0/temp1_input",
            "/sys/class/hwmon/hwmon0/temp2_input",
        ],
    )
    assert sensors == ()


def test_thermal_parser_preserves_a_valid_zero_hwmon_temperature() -> None:
    values = {
        Path("/sys/class/hwmon/hwmon0/temp1_input"): "0",
        Path("/sys/class/hwmon/hwmon0/temp1_fault"): "0",
        Path("/sys/class/hwmon/hwmon0/temp1_enable"): "1",
    }
    sensors = collect_thermals(
        lambda path: values.get(path),
        ["/sys/class/hwmon/hwmon0/temp1_input"],
    )
    assert sensors == (ThermalSensor("hwmon0/temp1", None, 0.0),)


def test_thermal_parser_omits_ambiguous_zero_hwmon_temperature() -> None:
    sensors = collect_thermals(
        lambda path: "0" if path == Path("/sys/class/hwmon/hwmon0/temp1_input") else None,
        ["/sys/class/hwmon/hwmon0/temp1_input"],
    )
    assert sensors == ()


def _sample() -> TelemetrySample:
    return TelemetrySample(
        wall_timestamp=datetime.now(timezone.utc),
        monotonic_timestamp=time.monotonic(),
        cpu=CpuTelemetry(None, (), None, None, None, None, None, None, None, None, ()),
        memory=MemoryTelemetry(None, None, None, None, None, None, None, None),
        pressure_cpu=None,
        pressure_memory=None,
        pressure_io=None,
        thermal=(),
        disks=(),
    )


def test_sampler_history_is_bounded_and_failures_are_isolated() -> None:
    calls = 0

    def collector() -> TelemetrySample:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("fixture failure")
        return _sample()

    sampler = Sampler(0.25, history_capacity=2, collector=collector)
    assert sampler.collect_once() is not None
    assert sampler.collect_once() is None
    assert sampler.collect_once() is not None
    assert sampler.collect_once() is not None
    assert len(sampler.history) == 2
    assert sampler.stats.collection_errors == 1
    assert sampler.stats.evicted_samples == 1


def test_sampler_start_stop() -> None:
    sampler = Sampler(0.25, history_capacity=2, collector=_sample)
    sampler.start()
    time.sleep(0.01)
    sampler.stop()
    assert not sampler.running
    assert sampler.stats.samples_collected >= 1


def test_sampler_validates_safe_bounds() -> None:
    with pytest.raises(ValueError):
        Sampler(0.1)
    with pytest.raises(ValueError):
        Sampler(1.0, history_capacity=0)


def test_sampler_records_collection_overrun() -> None:
    def slow_sample() -> TelemetrySample:
        time.sleep(0.26)
        return _sample()

    sampler = Sampler(0.25, history_capacity=2, collector=slow_sample)
    sampler.start()
    time.sleep(0.28)
    sampler.stop()
    assert sampler.stats.overruns >= 1


def test_process_snapshot_enforces_limit_and_tolerates_malformed_data() -> None:
    paths = ["/proc/10", "/proc/20"]

    def read(path: Path) -> str | None:
        if path.name == "status" and path.parent.name == "10":
            return "Name:\tworker\nState:\tS (sleeping)\nVmRSS:\t10 kB\nThreads:\t2\n"
        if path.name == "stat" and path.parent.name == "10":
            return "10 (worker) S 0 0 0 0 0 0 0 0 0 0 3 4"
        return None

    snapshots = process_snapshot(1, read, paths)
    assert len(snapshots) == 1
    assert snapshots[0].pid == 10
    assert snapshots[0].resident_bytes == 10 * 1024
    assert process_snapshot(1, lambda _path: None, ["/proc/10"]) == ()


def test_diskstats_parser_rejects_malformed_rows() -> None:
    disks = parse_diskstats("8 0 sda 10 0 20 0 30 0 40 0 0 0 0\nbad row\n")
    assert disks[0].device == "sda"
    assert disks[0].read_bytes == 20 * 512
    assert collect_disks(lambda _path: "bad row") == ()
