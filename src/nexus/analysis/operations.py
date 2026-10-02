"""Synchronous, CPU-only Phase 4A operations."""

from dataclasses import dataclass
import math
from typing import Any

from .contracts import AnalysisLimits, AnalysisTable, OperationMetadata
from .errors import AnalysisLimitError, InsufficientDataError, InvalidAnalysisInputError


@dataclass(frozen=True, slots=True)
class DescriptiveStatistics:
    count: int
    valid_count: int
    null_count: int
    minimum: float | None
    maximum: float | None
    mean: float | None
    population_variance: float | None
    population_standard_deviation: float | None
    sample_variance: float | None
    sample_standard_deviation: float | None


@dataclass(frozen=True, slots=True)
class DescriptiveStatisticsOperation:
    metadata: OperationMetadata = OperationMetadata(
        "descriptive_statistics", "Compute deterministic descriptive statistics", True
    )

    def execute(
        self, table: AnalysisTable, *, column: str, limits: AnalysisLimits = AnalysisLimits()
    ) -> DescriptiveStatistics:
        return descriptive_statistics(table, column=column, limits=limits)


@dataclass(frozen=True, slots=True)
class ExactQuantileOperation:
    metadata: OperationMetadata = OperationMetadata(
        "exact_quantile", "Compute an exact bounded quantile", True
    )

    def execute(
        self,
        table: AnalysisTable,
        *,
        column: str,
        q: float,
        limits: AnalysisLimits = AnalysisLimits(),
    ) -> float:
        return exact_quantile(table, column=column, q=q, limits=limits)


def descriptive_statistics(
    table: AnalysisTable, *, column: str, limits: AnalysisLimits = AnalysisLimits()
) -> DescriptiveStatistics:
    _validate_numeric_column(table, column)
    count = valid = nulls = 0
    minimum = maximum = mean = m2 = None
    for value in table.column_values(column):
        count += 1
        if limits.max_rows is not None and count > limits.max_rows:
            raise AnalysisLimitError("maximum rows processed exceeded")
        if value is None:
            nulls += 1
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidAnalysisInputError(f"column {column!r} is not numeric")
        number = float(value)
        if not math.isfinite(number):
            raise InvalidAnalysisInputError("non-finite numeric values are not supported")
        valid += 1
        minimum = number if minimum is None else min(minimum, number)
        maximum = number if maximum is None else max(maximum, number)
        delta = number - mean if mean is not None else number
        mean = number if mean is None else mean + delta / valid
        m2 = 0.0 if m2 is None else m2 + delta * (number - mean)
    population = None if valid == 0 else m2 / valid
    sample = None if valid < 2 else m2 / (valid - 1)
    return DescriptiveStatistics(
        count, valid, nulls, minimum, maximum, mean, population,
        None if population is None else math.sqrt(population),
        sample, None if sample is None else math.sqrt(sample),
    )


def exact_quantile(
    table: AnalysisTable,
    *,
    column: str,
    q: float,
    limits: AnalysisLimits = AnalysisLimits(),
) -> float:
    _validate_numeric_column(table, column)
    if isinstance(q, bool) or not isinstance(q, (int, float)) or not math.isfinite(float(q)):
        raise InvalidAnalysisInputError("q must be a finite number between 0 and 1")
    if not 0 <= q <= 1:
        raise InvalidAnalysisInputError("q must be between 0 and 1")
    values: list[float] = []
    processed = 0
    for value in table.column_values(column):
        processed += 1
        if limits.max_rows is not None and processed > limits.max_rows:
            raise AnalysisLimitError("maximum rows processed exceeded")
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidAnalysisInputError(f"column {column!r} is not numeric")
        number = float(value)
        if not math.isfinite(number):
            raise InvalidAnalysisInputError("non-finite numeric values are not supported")
        if limits.max_materialized_values is not None and len(values) >= limits.max_materialized_values:
            raise AnalysisLimitError("maximum materialized values exceeded")
        values.append(number)
    if not values:
        raise InsufficientDataError("quantile requires at least one valid value")
    values.sort()
    position = float(q) * (len(values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] + fraction * (values[upper] - values[lower])


def _validate_column(table: AnalysisTable, column: str) -> None:
    if column not in table.column_names:
        raise InvalidAnalysisInputError(f"unknown analysis column: {column}")


def _validate_numeric_column(table: AnalysisTable, column: str) -> None:
    _validate_column(table, column)
    schema = next(item for item in table.columns if item.name == column)
    if schema.data_type not in {"integer", "number", "null"}:
        raise InvalidAnalysisInputError(f"column {column!r} is not numeric")
