"""Read-only, lightweight runtime diagnostics for the ``doctor`` command."""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from typing import Callable, Mapping


@dataclass(frozen=True, slots=True)
class SystemDiagnostics:
    operating_system: str
    distribution: str | None
    kernel: str
    architecture: str


@dataclass(frozen=True, slots=True)
class CpuDiagnostics:
    model: str | None
    physical_cores: int | None
    logical_cores: int | None


@dataclass(frozen=True, slots=True)
class MemoryDiagnostics:
    total_bytes: int | None
    available_bytes: int | None
    swap_total_bytes: int | None
    swap_used_bytes: int | None


@dataclass(frozen=True, slots=True)
class FilesystemDiagnostics:
    path: str
    capacity_bytes: int | None
    available_bytes: int | None


@dataclass(frozen=True, slots=True)
class CapabilityDiagnostics:
    clinfo_available: bool
    opencl_devices: tuple[str, ...] | None
    drm_present: bool
    hwmon_present: bool
    intel_gpu_top_available: bool


@dataclass(frozen=True, slots=True)
class NexusDiagnostics:
    package_version: str
    python_version: str
    workspace_path: str
    data_path: str


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    status: str
    system: SystemDiagnostics
    cpu: CpuDiagnostics
    memory: MemoryDiagnostics
    filesystem: FilesystemDiagnostics
    capabilities: CapabilityDiagnostics
    nexus: NexusDiagnostics

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def as_json(self) -> str:
        return json.dumps(self.as_dict(), sort_keys=True)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _linux_distribution() -> str | None:
    values: dict[str, str] = {}
    contents = _read_text(Path("/etc/os-release"))
    if contents is None:
        return None
    for line in contents.splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"PRETTY_NAME", "NAME"}:
            values[key] = value.strip().strip('"')
    return values.get("PRETTY_NAME") or values.get("NAME")


def _cpu_details() -> tuple[str | None, int | None]:
    contents = _read_text(Path("/proc/cpuinfo"))
    if contents is None:
        return None, None
    model: str | None = None
    physical_core_ids: set[tuple[str, str]] = set()
    record: dict[str, str] = {}
    for line in contents.splitlines() + [""]:
        key, separator, value = line.partition(":")
        if separator:
            record[key.strip()] = value.strip()
            continue
        if record:
            model = model or record.get("model name") or record.get("Hardware") or record.get("Processor")
            physical_id = record.get("physical id")
            core_id = record.get("core id")
            if physical_id is not None and core_id is not None:
                physical_core_ids.add((physical_id, core_id))
            record = {}
    return model, len(physical_core_ids) or None


def _meminfo() -> Mapping[str, int]:
    contents = _read_text(Path("/proc/meminfo"))
    if contents is None:
        return {}
    values: dict[str, int] = {}
    for line in contents.splitlines():
        key, separator, value = line.partition(":")
        if not separator:
            continue
        number = value.strip().split(maxsplit=1)[0]
        try:
            values[key] = int(number) * 1024
        except (TypeError, ValueError):
            continue
    return values


def _filesystem(path: Path) -> FilesystemDiagnostics:
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        return FilesystemDiagnostics(str(path), None, None)
    return FilesystemDiagnostics(str(path), usage.total, usage.free)


def _opencl_devices(
    clinfo_available: bool,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> tuple[str, ...] | None:
    if not clinfo_available:
        return None
    try:
        result = runner(
            ["clinfo", "--list"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    devices = tuple(line.strip() for line in result.stdout.splitlines() if line.strip())
    return devices


def collect_diagnostics(
    data_path: Path,
    workspace_path: Path | None = None,
    *,
    which: Callable[[str], str | None] = shutil.which,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> DiagnosticReport:
    """Collect diagnostics without requiring Linux, root, or optional tools."""
    workspace = (workspace_path or Path.cwd()).resolve()
    model, physical_cores = _cpu_details() if platform.system() == "Linux" else (None, None)
    memory = _meminfo() if platform.system() == "Linux" else {}
    clinfo = which("clinfo") is not None
    devices = _opencl_devices(clinfo, runner)
    system = SystemDiagnostics(
        operating_system=platform.system() or "unavailable",
        distribution=_linux_distribution() if platform.system() == "Linux" else None,
        kernel=platform.release() or "unavailable",
        architecture=platform.machine() or "unavailable",
    )
    return DiagnosticReport(
        status="collected",
        system=system,
        cpu=CpuDiagnostics(model, physical_cores, os.cpu_count()),
        memory=MemoryDiagnostics(
            memory.get("MemTotal"),
            memory.get("MemAvailable"),
            memory.get("SwapTotal"),
            (memory.get("SwapTotal", 0) - memory["SwapFree"]) if "SwapTotal" in memory and "SwapFree" in memory else None,
        ),
        filesystem=_filesystem(workspace),
        capabilities=CapabilityDiagnostics(
            clinfo_available=clinfo,
            opencl_devices=devices,
            drm_present=Path("/dev/dri").is_dir(),
            hwmon_present=Path("/sys/class/hwmon").is_dir(),
            intel_gpu_top_available=which("intel_gpu_top") is not None,
        ),
        nexus=NexusDiagnostics(
            package_version=__import__("nexus").__version__,
            python_version=platform.python_version(),
            workspace_path=str(workspace),
            data_path=str(data_path),
        ),
    )
