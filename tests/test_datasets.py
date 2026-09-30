import json
from pathlib import Path
import sqlite3
from datetime import datetime, timezone

import pytest

from nexus.cli import main
from nexus.config import NexusConfig
from nexus.datasets.fingerprints import fingerprint
from nexus.datasets.models import (
    DatasetFingerprint,
    DatasetSource,
    ProfileResult,
    ResourceEstimate,
)
from nexus.observatory.models import CpuTelemetry, MemoryTelemetry, TelemetrySample
from nexus.datasets.profiling import profile
from nexus.datasets.sources import DatasetError, validate_source
from nexus.datasets.workloads import profile_dataset


def write_csv(path: Path) -> None:
    path.write_text("name,value\nalpha,1\nbeta,2\n", encoding="utf-8")


def test_csv_profile_is_streaming_and_bounded(tmp_path: Path) -> None:
    path = tmp_path / "records.csv"
    write_csv(path)
    source = validate_source(DatasetSource(path, "auto"))
    result = profile(source, max_rows=1)
    assert result.row_count == 1
    assert result.complete is False
    assert [column.name for column in result.columns] == ["name", "value"]
    assert result.columns[1].mean == 1.0


def test_jsonl_profile_and_malformed_input(tmp_path: Path) -> None:
    path = tmp_path / "records.jsonl"
    path.write_text('{"name":"alpha","value":1}\n{"name":"beta","value":2}\n', encoding="utf-8")
    result = profile(validate_source(DatasetSource(path, "auto")))
    assert result.row_count == 2
    assert result.columns[1].inferred_type == "number"
    path.write_text('{"name":"alpha"}\nnot-json\n', encoding="utf-8")
    with pytest.raises(DatasetError, match="row 2"):
        profile(validate_source(DatasetSource(path, "auto")))


def test_csv_malformed_row_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "records.csv"
    path.write_text("name,value\nalpha,1,extra\n", encoding="utf-8")
    with pytest.raises(DatasetError, match="row 2"):
        profile(validate_source(DatasetSource(path, "auto")))


def test_max_rows_does_not_parse_following_malformed_csv_row(tmp_path: Path) -> None:
    path = tmp_path / "records.csv"
    path.write_text("name,value\nalpha,1\nbad,2,extra\n", encoding="utf-8")
    result = profile(validate_source(DatasetSource(path, "auto")), max_rows=1)
    assert result.row_count == 1
    assert result.complete is False


def test_mixed_type_statistics_are_order_independent(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("value\n2\ntext\n", encoding="utf-8")
    second.write_text("value\ntext\n2\n", encoding="utf-8")
    first_profile = profile(validate_source(DatasetSource(first, "auto")))
    second_profile = profile(validate_source(DatasetSource(second, "auto")))
    assert first_profile.columns[0].inferred_type == "string"
    assert first_profile.columns[0].minimum == second_profile.columns[0].minimum == "2"
    assert first_profile.columns[0].maximum == second_profile.columns[0].maximum == "text"
    assert first_profile.columns[0].mean is None
    assert second_profile.columns[0].mean is None


def test_sqlite_profile_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "records.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("create table records (name text, value integer)")
        connection.executemany("insert into records values (?, ?)", [("alpha", 1), ("beta", 2)])
    before = path.read_bytes()
    result = profile(validate_source(DatasetSource(path, "auto", "records")))
    assert result.row_count == 2
    assert result.columns[1].maximum == 2.0
    assert path.read_bytes() == before


def test_sqlite_uri_escapes_literal_uri_characters(tmp_path: Path) -> None:
    path = tmp_path / "records?#.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("create table records (value integer)")
        connection.execute("insert into records values (1)")
    result = profile(validate_source(DatasetSource(path, "auto", "records")))
    assert result.row_count == 1


def test_fingerprint_is_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "records.csv"
    write_csv(path)
    assert fingerprint(path) == fingerprint(path)


def test_workload_telemetry_enabled_and_disabled(tmp_path: Path) -> None:
    path = tmp_path / "records.csv"
    write_csv(path)
    enabled = profile_dataset(DatasetSource(path, "csv"), telemetry=True)
    disabled = profile_dataset(DatasetSource(path, "csv"), telemetry=False)
    assert enabled.status == "completed"
    assert enabled.telemetry.enabled is True
    assert disabled.telemetry.enabled is False
    assert enabled.timing is not None
    assert enabled.timing.elapsed_seconds >= 0


def test_workload_telemetry_filters_to_complete_monotonic_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "records.csv"
    write_csv(path)
    sample = TelemetrySample(
        datetime.now(timezone.utc),
        15.0,
        CpuTelemetry(25.0, (), None, None, None, None, None, None, None, None, ()),
        MemoryTelemetry(100, 50, 50, 50.0, 0, 0, 0, 0.0),
        None,
        None,
        None,
        (),
        (),
    )
    outside_before = sample.__class__(
        sample.wall_timestamp, 9.0, sample.cpu, sample.memory, None, None, None, (), ()
    )
    outside_after = sample.__class__(
        sample.wall_timestamp, 21.0, sample.cpu, sample.memory, None, None, None, (), ()
    )

    class FakeSampler:
        history = (outside_before, sample, outside_after)

        def __init__(self, *_args: object) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    monotonic = iter((10.0, 20.0))
    monkeypatch.setattr("nexus.datasets.workloads.time.monotonic", lambda: next(monotonic))
    result = profile_dataset(DatasetSource(path, "csv"), sampler_factory=FakeSampler)
    assert result.telemetry.sample_count == 1
    assert result.telemetry.coverage == "insufficient"
    assert result.telemetry.cpu_utilization_percent == (25.0,)


def test_workload_timing_covers_validation_through_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = DatasetSource(Path("synthetic.csv"), "csv")
    monkeypatch.setattr("nexus.datasets.workloads.time.monotonic", iter((10.0, 20.0)).__next__)
    monkeypatch.setattr("nexus.datasets.workloads.validate_source", lambda value: value)
    monkeypatch.setattr(
        "nexus.datasets.workloads.fingerprint",
        lambda *_args: DatasetFingerprint("sha256", "digest", 1, 1),
    )
    monkeypatch.setattr(
        "nexus.datasets.requirements.estimate",
        lambda *_args: ResourceEstimate(1, 1, 1, 0),
    )
    monkeypatch.setattr(
        "nexus.datasets.workloads.profile",
        lambda *_args, **_kwargs: ProfileResult(0, True, (), (), False),
    )
    result = profile_dataset(source, telemetry=False)
    assert result.timing.monotonic_start == 10.0
    assert result.timing.monotonic_end == 20.0
    assert result.timing.elapsed_seconds == 10.0


def test_cli_profile_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "records.csv"
    write_csv(path)
    assert main(["profile", str(path), "--json", "--max-rows", "100"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "completed"
    assert output["profile"]["row_count"] == 2


def test_source_validation_rejects_missing_sqlite_table(tmp_path: Path) -> None:
    path = tmp_path / "records.sqlite"
    sqlite3.connect(path).close()
    with pytest.raises(DatasetError, match="table"):
        validate_source(DatasetSource(path, "sqlite", "missing"))


def test_workload_stops_telemetry_on_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "records.csv"
    write_csv(path)
    state = {"started": False, "stopped": False}

    class FakeSampler:
        history = ()

        def __init__(self, *_args: object) -> None:
            pass

        def start(self) -> None:
            state["started"] = True

        def stop(self) -> None:
            state["stopped"] = True

    def cancelled(*_args: object, **_kwargs: object) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("nexus.datasets.workloads.profile", cancelled)
    result = profile_dataset(
        DatasetSource(path, "csv"),
        sampler_factory=FakeSampler,
    )
    assert result.status == "cancelled"
    assert state == {"started": True, "stopped": True}


def test_workload_stops_telemetry_on_profile_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "records.csv"
    path.write_text("name,value\nalpha,1,extra\n", encoding="utf-8")
    state = {"stopped": False}

    class FakeSampler:
        history = ()

        def __init__(self, *_args: object) -> None:
            pass

        def start(self) -> None:
            pass

        def stop(self) -> None:
            state["stopped"] = True

    result = profile_dataset(
        DatasetSource(path, "csv"),
        sampler_factory=FakeSampler,
    )
    assert result.status == "failed"
    assert state["stopped"] is True


def test_profile_configuration_limits_are_validated() -> None:
    with pytest.raises(ValueError):
        NexusConfig(profile_sample_values=-1)
    with pytest.raises(ValueError):
        NexusConfig(profile_distinct_values=0)
