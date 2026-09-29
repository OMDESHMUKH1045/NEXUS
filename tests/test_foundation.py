import logging
from pathlib import Path
import subprocess

import pytest

from nexus.config import NexusConfig
from nexus.diagnostics import _cpu_details, collect_diagnostics
from nexus.logging import StructuredFormatter


def test_config_rejects_unbounded_or_invalid_limits() -> None:
    with pytest.raises(ValueError, match="worker_limit"):
        NexusConfig(worker_limit=0)
    with pytest.raises(ValueError, match="queue_limit"):
        NexusConfig(queue_limit=0)


def test_structured_formatter_includes_context() -> None:
    record = logging.LogRecord(
        "nexus.test", logging.INFO, __file__, 1, "started", (), None
    )
    record.component = "cli"
    record.job_id = "job-1"
    output = StructuredFormatter().format(record)
    assert '"component": "cli"' in output
    assert '"job_id": "job-1"' in output
    assert '"message": "started"' in output


def test_diagnostics_collect_structured_sections(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("nexus.diagnostics.platform.system", lambda: "Other")
    report = collect_diagnostics(tmp_path, workspace_path=tmp_path, which=lambda _: None)
    assert report.status == "collected"
    assert report.system.distribution is None
    assert report.capabilities.opencl_devices is None
    assert report.filesystem.path == str(tmp_path.resolve())
    assert report.nexus.data_path == str(tmp_path)


def test_opencl_probe_is_bounded_and_tolerates_failure(tmp_path: Path) -> None:
    def failed_runner(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        assert kwargs["timeout"] == 2
        return subprocess.CompletedProcess(args[0], 1, "", "unavailable")

    report = collect_diagnostics(
        tmp_path,
        workspace_path=tmp_path,
        which=lambda name: "/usr/bin/clinfo" if name == "clinfo" else None,
        runner=failed_runner,
    )
    assert report.capabilities.clinfo_available is True
    assert report.capabilities.opencl_devices is None


def test_cpu_details_parse_linux_fixture(monkeypatch: pytest.MonkeyPatch) -> None:
    cpuinfo = """\
processor   : 0
model name  : Example CPU
physical id : 0
core id     : 0

processor   : 1
model name  : Example CPU
physical id : 0
core id     : 1

processor   : 2
model name  : Example CPU
physical id : 0
core id     : 0
"""
    monkeypatch.setattr("nexus.diagnostics._read_text", lambda _path: cpuinfo)
    assert _cpu_details() == ("Example CPU", 2)


def test_cpu_details_support_unusual_model_key_and_missing_topology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cpuinfo = """\
processor : 0
Hardware  : Example ARM

processor : 1
Hardware  : Example ARM
"""
    monkeypatch.setattr("nexus.diagnostics._read_text", lambda _path: cpuinfo)
    assert _cpu_details() == ("Example ARM", None)
