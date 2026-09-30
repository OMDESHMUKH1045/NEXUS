"""Streaming, bounded dataset profiling."""

from collections.abc import Iterable, Mapping
import math
from typing import Any

from .models import ColumnProfile, ProfileResult
from .sources import DatasetError, rows


def profile(
    source,
    *,
    max_rows: int | None = None,
    inference_rows: int = 100,
    sample_values: int = 5,
    distinct_values: int = 32,
    max_errors: int = 16,
    fetch_size: int = 256,
) -> ProfileResult:
    if max_rows is not None and max_rows < 1:
        raise ValueError("max_rows must be at least 1")
    if not 1 <= inference_rows <= 100_000:
        raise ValueError("inference_rows must be between 1 and 100000")
    if not 0 <= sample_values <= 1000 or not 1 <= distinct_values <= 100_000:
        raise ValueError("profile value limits are out of range")
    if not 1 <= max_errors <= 1000:
        raise ValueError("max_errors must be between 1 and 1000")
    state: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    truncated_errors = False
    row_count = 0
    with rows(source, fetch_size, max_rows) as (fields, iterator):
        state = {field: _new_state() for field in fields}
        for values in iterator:
            row_count += 1
            for field in fields:
                _update(state[field], values.get(field), sample_values, distinct_values, row_count <= inference_rows)
    columns: list[ColumnProfile] = []
    for field, item in state.items():
        inferred_type = _infer_type(item["types"])
        columns.append(
            ColumnProfile(
                field,
                inferred_type,
                item["null_count"] > 0,
                item["null_count"],
                item["numeric_count"],
                item["numeric_minimum"] if inferred_type == "number" else item["text_minimum"],
                item["numeric_maximum"] if inferred_type == "number" else item["text_maximum"],
                item["numeric_sum"] / item["numeric_count"] if inferred_type == "number" and item["numeric_count"] else None,
                tuple(item["samples"]),
                tuple(item["distinct"]),
                item["distinct_truncated"],
            )
        )
    return ProfileResult(row_count, max_rows is None, tuple(columns), tuple(errors), truncated_errors)


def _new_state() -> dict[str, Any]:
    return {
        "types": [],
        "null_count": 0,
        "numeric_count": 0,
        "numeric_sum": 0.0,
        "numeric_minimum": None,
        "numeric_maximum": None,
        "text_minimum": None,
        "text_maximum": None,
        "samples": [],
        "distinct": [],
        "distinct_truncated": False,
    }


def _update(state: dict[str, Any], value: object, sample_limit: int, distinct_limit: int, infer: bool) -> None:
    if value is None or value == "":
        state["null_count"] += 1
        if infer:
            state["types"].append("null")
        return
    if infer:
        state["types"].append(_value_type(value))
    if len(state["samples"]) < sample_limit and value not in state["samples"]:
        state["samples"].append(value)
    if value not in state["distinct"]:
        if len(state["distinct"]) < distinct_limit:
            state["distinct"].append(value)
        else:
            state["distinct_truncated"] = True
    number = _number(value)
    if number is not None:
        state["numeric_count"] += 1
        state["numeric_sum"] += number
        state["numeric_minimum"] = number if state["numeric_minimum"] is None else min(state["numeric_minimum"], number)
        state["numeric_maximum"] = number if state["numeric_maximum"] is None else max(state["numeric_maximum"], number)
    text = str(value)
    state["text_minimum"] = text if state["text_minimum"] is None else min(state["text_minimum"], text)
    state["text_maximum"] = text if state["text_maximum"] is None else max(state["text_maximum"], text)


def _value_type(value: object) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    text = str(value)
    try:
        float(text)
        return "number"
    except ValueError:
        return "string"


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(float(value)) else None
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _infer_type(types: Iterable[str]) -> str:
    values = set(types)
    if not values or values == {"null"}:
        return "null"
    if values <= {"null", "number"}:
        return "number"
    if values <= {"null", "boolean"}:
        return "boolean"
    return "string"
