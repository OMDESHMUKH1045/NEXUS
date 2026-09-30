"""Validation and streaming readers for the initial source formats."""

from contextlib import contextmanager
import csv
import json
from pathlib import Path
import sqlite3
from typing import Iterator, Mapping

from .models import DatasetSource


class DatasetError(ValueError):
    """An input source is invalid or cannot be safely profiled."""


def detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix in {".jsonl", ".ndjson"}:
        return "jsonl"
    if suffix in {".sqlite", ".sqlite3", ".db"}:
        return "sqlite"
    raise DatasetError(f"unsupported dataset format: {suffix or 'none'}")


def validate_source(source: DatasetSource) -> DatasetSource:
    path = source.path.expanduser()
    if not path.is_file():
        raise DatasetError(f"dataset is not a regular file: {path}")
    format_name = source.format if source.format != "auto" else detect_format(path)
    if format_name not in {"csv", "jsonl", "sqlite"}:
        raise DatasetError(f"unsupported dataset format: {format_name}")
    if format_name == "sqlite" and not source.table:
        raise DatasetError("SQLite profiling requires --table")
    if format_name != "sqlite" and source.table is not None:
        raise DatasetError("--table is only valid for SQLite sources")
    if format_name == "sqlite":
        _validate_table(path, source.table or "")
    return DatasetSource(path, format_name, source.table)


def _quote_identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise DatasetError("invalid SQLite table name")
    return '"' + value.replace('"', '""') + '"'


def _validate_table(path: Path, table: str) -> None:
    with sqlite3.connect(_readonly_uri(path), uri=True) as connection:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    if row is None:
        raise DatasetError(f"SQLite table not found: {table}")


def _readonly_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


@contextmanager
def rows(
    source: DatasetSource,
    fetch_size: int = 256,
    max_rows: int | None = None,
) -> Iterator[tuple[tuple[str, ...], Iterator[Mapping[str, object]]]]:
    if fetch_size < 1:
        raise ValueError("fetch_size must be at least 1")
    if max_rows is not None and max_rows < 1:
        raise ValueError("max_rows must be at least 1")
    if source.format == "csv":
        with source.path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None or any(not name for name in reader.fieldnames):
                raise DatasetError("CSV requires a non-empty header")
            if len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise DatasetError("CSV headers must be unique")
            def csv_rows() -> Iterator[Mapping[str, object]]:
                for row_number, row in enumerate(reader, 2):
                    if max_rows is not None and row_number > max_rows + 1:
                        return
                    if None in row:
                        raise DatasetError(f"CSV row {row_number} has too many fields")
                    if any(value is None for value in row.values()):
                        raise DatasetError(f"CSV row {row_number} has too few fields")
                    yield row
            yield tuple(reader.fieldnames), csv_rows()
        return
    if source.format == "jsonl":
        with source.path.open("r", encoding="utf-8") as handle:
            iterator = iter(handle)
            first = next(iterator, None)
            if first is None:
                raise DatasetError("JSONL source is empty")
            first_value = _json_object(first, 1)
            fields = tuple(first_value)
            if not fields:
                raise DatasetError("JSONL objects require fields")
            def json_rows() -> Iterator[Mapping[str, object]]:
                yield first_value
                for row_number, line in enumerate(iterator, 2):
                    if max_rows is not None and row_number > max_rows:
                        return
                    value = _json_object(line, row_number)
                    if tuple(value) != fields:
                        raise DatasetError(f"JSONL row {row_number} has inconsistent fields")
                    yield value
            yield fields, json_rows()
        return
    if source.format == "sqlite":
        connection = sqlite3.connect(_readonly_uri(source.path), uri=True)
        try:
            cursor = connection.execute(f"SELECT * FROM {_quote_identifier(source.table or '')}")
            fields = tuple(column[0] for column in cursor.description or ())
            if not fields or len(set(fields)) != len(fields):
                raise DatasetError("SQLite table must have unique columns")
            def sqlite_rows() -> Iterator[Mapping[str, object]]:
                yielded = 0
                while True:
                    remaining = fetch_size if max_rows is None else max_rows - yielded
                    if remaining <= 0:
                        return
                    batch = cursor.fetchmany(min(fetch_size, remaining))
                    if not batch:
                        return
                    for values in batch:
                        yielded += 1
                        yield dict(zip(fields, values, strict=True))
            yield fields, sqlite_rows()
        finally:
            connection.close()
        return
    raise DatasetError(f"unsupported dataset format: {source.format}")


def _json_object(line: str, row_number: int) -> Mapping[str, object]:
    try:
        value = json.loads(line)
    except json.JSONDecodeError as exc:
        raise DatasetError(f"JSONL row {row_number} is invalid: {exc.msg}") from exc
    if not isinstance(value, dict):
        raise DatasetError(f"JSONL row {row_number} must be an object")
    return value
