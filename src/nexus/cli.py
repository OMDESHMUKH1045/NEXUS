"""NEXUS command-line entry point."""

import argparse
import sys

from . import __version__
from .config import NexusConfig
from .diagnostics import DiagnosticReport, collect_diagnostics
from .logging import configure_logging


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nexus", description="Local Compute and Data Observatory")
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("doctor", help="report local runtime diagnostics")
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
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
