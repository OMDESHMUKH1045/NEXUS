"""Explicit Phase 3 source to analysis-table adapters."""

from collections.abc import Mapping
import math
from decimal import Decimal, InvalidOperation
from typing import Callable, Iterable, Mapping

from nexus.datasets.models import DatasetSource
from nexus.datasets.sources import rows, validate_source

from .contracts import AnalysisLimits, AnalysisTable, ColumnSchema
from .errors import AnalysisLimitError, InvalidAnalysisInputError


def from_rows(
    columns: tuple[ColumnSchema, ...] | list[ColumnSchema],
    values: Callable[[], Iterable[Mapping[str, object]]],
) -> AnalysisTable:
    schemas = tuple(columns)
    expected = tuple(column.name for column in schemas)
    if not callable(values):
        raise InvalidAnalysisInputError("from_rows requires a callable row factory")

    def factory():
        for row in values():
            if not isinstance(row, Mapping) or set(row) != set(expected):
                raise InvalidAnalysisInputError("row fields do not match analysis schema")
            yield row

    return AnalysisTable(schemas, factory)


def from_source(source: DatasetSource, limits: AnalysisLimits = AnalysisLimits()) -> AnalysisTable:
    """Adapt CSV, JSONL, or SQLite using one deterministic typing policy.

    CSV values are typed per column: blank fields are missing, a column whose
    nonblank values are all finite decimal numbers is ``integer`` or
    ``number``, a column whose nonblank values are all ``true``/``false`` is
    boolean, and otherwise values remain strings. JSONL and SQLite preserve
    native values; JSON strings are never parsed as numbers. Non-finite
    numbers are rejected by the adapter.
    """
    checked = validate_source(source)
    fields, type_names = _infer_source_schema(checked, limits)
    schemas = tuple(
        ColumnSchema(field, type_name, nullable=True)
        for field, type_name in zip(fields, type_names, strict=True)
    )

    def factory():
        with rows(checked, max_rows=limits.max_rows) as (actual_fields, iterator):
            if actual_fields != fields:
                raise InvalidAnalysisInputError("source schema changed between adapter passes")
            for raw in iterator:
                yield {
                    field: _typed_value(raw[field], type_name, checked.format)
                    for field, type_name in zip(fields, type_names, strict=True)
                }

    return AnalysisTable(schemas, factory)


def _infer_source_schema(
    source: DatasetSource, limits: AnalysisLimits
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    observed: dict[str, dict[str, object]] = {}
    with rows(source, max_rows=_probe_rows_limit(limits)) as (fields, iterator):
        observed = {field: _new_inference_state() for field in fields}
        for row_number, raw in enumerate(iterator, 1):
            if limits.max_rows is not None and row_number > limits.max_rows:
                raise AnalysisLimitError("maximum rows processed exceeded")
            for field in fields:
                _observe(observed[field], raw[field], source.format)
    return tuple(observed), tuple(_infer_column_type(state, source.format) for state in observed.values())


def _new_inference_state() -> dict[str, object]:
    return {
        "nonmissing": 0,
        "all_numeric": True,
        "all_integer": True,
        "all_boolean": True,
        "all_native_boolean": True,
        "all_native_integer": True,
        "all_native_number": True,
        "all_string": True,
    }


def _observe(state: dict[str, object], value: object, format_name: str) -> None:
    if value is None or value == "":
        return
    state["nonmissing"] = int(state["nonmissing"]) + 1
    if isinstance(value, str) and _is_nonfinite_numeric_text(value):
        raise InvalidAnalysisInputError("non-finite numeric values are not supported")
    if format_name == "csv":
        number = _parse_decimal(value)
        if number is None and _is_nonfinite_numeric_text(value):
            raise InvalidAnalysisInputError("non-finite numeric values are not supported")
        state["all_numeric"] = bool(state["all_numeric"]) and number is not None
        state["all_integer"] = bool(state["all_integer"]) and number is not None and number.is_integer()
        state["all_boolean"] = bool(state["all_boolean"]) and str(value).lower() in {"true", "false"}
        return
    state["all_native_boolean"] = bool(state["all_native_boolean"]) and isinstance(value, bool)
    state["all_native_integer"] = bool(state["all_native_integer"]) and isinstance(value, int) and not isinstance(value, bool)
    state["all_native_number"] = bool(state["all_native_number"]) and isinstance(value, (int, float)) and not isinstance(value, bool)
    state["all_string"] = bool(state["all_string"]) and isinstance(value, str)
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidAnalysisInputError("non-finite numeric values are not supported")


def _infer_column_type(state: dict[str, object], format_name: str) -> str:
    if not state["nonmissing"]:
        return "null"
    if format_name == "csv":
        if state["all_numeric"]:
            return "integer" if state["all_integer"] else "number"
        if state["all_boolean"]:
            return "boolean"
        return "string"
    if state["all_native_boolean"]:
        return "boolean"
    if state["all_native_integer"]:
        return "integer"
    if state["all_native_number"]:
        return "number"
    if state["all_string"]:
        return "string"
    raise InvalidAnalysisInputError(
        "heterogeneous JSONL/SQLite column values are not supported; "
        "use a homogeneous native column or explicit missing values"
    )


def _parse_decimal(value: object) -> float | None:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _is_nonfinite_numeric_text(value: object) -> bool:
    text = str(value).strip()
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError):
        return False
    return not parsed.is_finite() or not math.isfinite(float(parsed))


def _probe_rows_limit(limits: AnalysisLimits) -> int | None:
    return None if limits.max_rows is None else limits.max_rows + 1


def _typed_value(value: object, type_name: str, format_name: str) -> object:
    if value is None or value == "":
        return None
    if isinstance(value, float) and not math.isfinite(value):
        raise InvalidAnalysisInputError("non-finite numeric values are not supported")
    if format_name == "csv":
        if type_name == "integer":
            return int(float(str(value)))
        if type_name == "number":
            number = _parse_decimal(value)
            if number is None:
                raise InvalidAnalysisInputError("CSV numeric column contains a non-finite value")
            return number
        if type_name == "boolean":
            return str(value).lower() == "true"
    return value
