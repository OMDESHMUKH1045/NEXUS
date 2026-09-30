"""NEXUS command-line entry point."""

import argparse
import json
from pathlib import Path
import sys
import time

from . import __version__
from .config import NexusConfig
from .diagnostics import DiagnosticReport, collect_diagnostics
from .logging import configure_logging
from .observatory import Sampler
from .datasets import DatasetSource
from .datasets.sources import DatasetError, detect_format
from .datasets.workloads import profile_dataset


def _print_diagnostics(report: DiagnosticReport) -> None:
    report_values = report.as_dict()

    def emit(section: str) -> None:
        print(f"{section}:")
        values = report_values[section]
        assert isinstance(values, dict)
        for key, value in values.items():
            print(f"  {key}: {value}")

    for section in ("system", "cpu", "memory", "filesystem", "capabilities", "nexus"):
        emit(section)
    print(f"status: {report.status}")


def _doctor(config: NexusConfig) -> int:
    _print_diagnostics(collect_diagnostics(config.data_dir))
    return 0


def _format_percent(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.1f}%"


def _observe(config: NexusConfig, interval: float, samples: int) -> int:
    sampler = Sampler(interval, config.telemetry_history_capacity)
    try:
        for index in range(samples):
            sample = sampler.collect_once()
            if sample is None:
                print("telemetry: unavailable")
            else:
                load = (sample.cpu.load_1m, sample.cpu.load_5m, sample.cpu.load_15m)
                temperatures = ", ".join(
                    f"{sensor.label or sensor.identifier}={sensor.celsius:.1f}C"
                    for sensor in sample.thermal
                ) or "unavailable"
                pressure = sample.pressure_cpu.some_avg10 if sample.pressure_cpu else None
                print(
                    f"{sample.wall_timestamp.isoformat()} "
                    f"cpu={_format_percent(sample.cpu.utilization_percent)} "
                    f"load={load} memory={_format_percent(sample.memory.utilization_percent)} "
                    f"swap={_format_percent(sample.memory.swap_utilization_percent)} "
                    f"psi_cpu_some10={pressure!r} thermal={temperatures}"
                )
            if index < samples - 1:
                time.sleep(interval)
    except KeyboardInterrupt:
        return 130
    return 0


def _profile(config: NexusConfig, path: str, table: str | None, max_rows: int | None, as_json: bool) -> int:
    source_path = Path(path).expanduser()
    format_name = detect_format(source_path)
    result = profile_dataset(
        DatasetSource(source_path, format_name, table),
        max_rows=max_rows,
        telemetry=True,
        fingerprint_chunk_size=config.fingerprint_chunk_size,
        inference_rows=config.profile_inference_rows,
        sample_values=config.profile_sample_values,
        distinct_values=config.profile_distinct_values,
    )
    if as_json:
        print(json.dumps(result.as_dict(), sort_keys=True))
    else:
        print(f"{result.status}: {result.operation} {result.source.path}")
        if result.error:
            print(f"error: {result.error}")
    return 0 if result.status == "completed" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexus", description="Local Compute and Data Observatory")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("doctor", help="report local runtime diagnostics")
    observe = subparsers.add_parser("observe", help="run a finite live telemetry session")
    observe.add_argument("--interval", type=float, default=None)
    observe.add_argument("--samples", type=int, default=5)
    profile_parser = subparsers.add_parser("profile", help="profile a local dataset")
    profile_parser.add_argument("path")
    profile_parser.add_argument("--table")
    profile_parser.add_argument("--max-rows", type=int)
    profile_parser.add_argument("--json", action="store_true", dest="as_json")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = NexusConfig.from_environment()
        configure_logging(config.log_level)
    except ValueError as exc:
        parser.error(str(exc))
    if args.command == "doctor":
        return _doctor(config)
    if args.command == "observe":
        interval = config.telemetry_interval_seconds if args.interval is None else args.interval
        if not 0.25 <= interval <= 5.0:
            parser.error("--interval must be between 0.25 and 5.0 seconds")
        if not 1 <= args.samples <= 1000:
            parser.error("--samples must be between 1 and 1000")
        return _observe(config, interval, args.samples)
    if args.command == "profile":
        if args.max_rows is not None and args.max_rows < 1:
            parser.error("--max-rows must be at least 1")
        try:
            return _profile(config, args.path, args.table, args.max_rows, args.as_json)
        except (DatasetError, OSError, ValueError) as exc:
            parser.error(str(exc))
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
