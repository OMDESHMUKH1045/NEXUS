"""Deterministic, bounded CPU outlier detection operations."""

from dataclasses import dataclass
from enum import Enum
import math

from .contracts import AnalysisLimits, AnalysisOperation, AnalysisTable, OperationMetadata
from .errors import AnalysisLimitError, InvalidAnalysisInputError


_MODIFIED_Z_SCALE = 0.6744897501960817


class OutlierMethod(str, Enum):
    IQR = "iqr"
    Z_SCORE = "z_score"
    MODIFIED_Z_SCORE = "modified_z_score"


class OutlierStatus(str, Enum):
    SUCCESS = "success"
    INSUFFICIENT_DATA = "insufficient_data"
    CONSTANT_COLUMN = "constant_column"
    NUMERICAL_DEGENERACY = "numerical_degeneracy"


@dataclass(frozen=True, slots=True)
class OutlierResult:
    method: OutlierMethod
    column: str
    valid_count: int
    skipped_count: int
    outlier_count: int
    lower_bound: float | None
    upper_bound: float | None
    status: OutlierStatus


@dataclass(frozen=True, slots=True)
class OutlierDetectionOperation:
    metadata: OperationMetadata = OperationMetadata(
        "outlier_detection", "Detect univariate outliers with an exact bounded method", True
    )

    def execute(
        self,
        table: AnalysisTable,
        *,
        column: str,
        method: OutlierMethod,
        threshold: float | None = None,
        limits: AnalysisLimits = AnalysisLimits(),
    ) -> OutlierResult:
        return detect_outliers(
            table,
            column=column,
            method=method,
            threshold=threshold,
            limits=limits,
        )


def detect_outliers(
    table: AnalysisTable,
    *,
    column: str,
    method: OutlierMethod,
    threshold: float | None = None,
    limits: AnalysisLimits = AnalysisLimits(),
) -> OutlierResult:
    _validate_inputs(table, column, method)
    threshold_value = _validate_threshold(method, threshold)
    values, skipped = _collect_values(table, column, limits)
    if len(values) < 2:
        return _result(
            method, column, len(values), skipped, 0, None, None, OutlierStatus.INSUFFICIENT_DATA
        )
    if all(value == values[0] for value in values[1:]):
        return _result(
            method, column, len(values), skipped, 0, None, None, OutlierStatus.CONSTANT_COLUMN
        )

    if method is OutlierMethod.IQR:
        lower, upper, status = _iqr_bounds(values, threshold_value)
    elif method is OutlierMethod.Z_SCORE:
        lower, upper, status = _z_score_bounds(values, threshold_value)
    else:
        lower, upper, status = _modified_z_score_bounds(values, threshold_value)
    if status is not OutlierStatus.SUCCESS:
        return _result(method, column, len(values), skipped, 0, None, None, status)
    assert lower is not None and upper is not None
    outlier_count = sum(value < lower or value > upper for value in values)
    return _result(
        method,
        column,
        len(values),
        skipped,
        outlier_count,
        lower,
        upper,
        OutlierStatus.SUCCESS,
    )


def _collect_values(
    table: AnalysisTable, column: str, limits: AnalysisLimits
) -> tuple[list[float], int]:
    values: list[float] = []
    skipped = 0
    processed = 0
    for row in table.rows():
        processed += 1
        if limits.max_rows is not None and processed > limits.max_rows:
            raise AnalysisLimitError("maximum rows processed exceeded")
        value = row[column]
        if value is None:
            skipped += 1
            continue
        if (
            limits.max_materialized_values is not None
            and len(values) >= limits.max_materialized_values
        ):
            raise AnalysisLimitError("maximum materialized values exceeded")
        values.append(float(value))
    return values, skipped


def _iqr_bounds(
    values: list[float], multiplier: float
) -> tuple[float | None, float | None, OutlierStatus]:
    ordered = sorted(values)
    q1 = _quantile(ordered, 0.25)
    q3 = _quantile(ordered, 0.75)
    spread = q3 - q1
    lower = q1 - multiplier * spread
    upper = q3 + multiplier * spread
    return _finite_bounds(lower, upper)


def _z_score_bounds(
    values: list[float], threshold: float
) -> tuple[float | None, float | None, OutlierStatus]:
    mean = 0.0
    m2 = 0.0
    for count, value in enumerate(values, 1):
        delta = value - mean
        mean += delta / count
        m2 += delta * (value - mean)
    variance = m2 / len(values)
    standard_deviation = math.sqrt(variance) if variance >= 0 else math.nan
    lower = mean - threshold * standard_deviation
    upper = mean + threshold * standard_deviation
    return _finite_bounds(lower, upper)


def _modified_z_score_bounds(
    values: list[float], threshold: float
) -> tuple[float | None, float | None, OutlierStatus]:
    ordered = sorted(values)
    median = _quantile(ordered, 0.5)
    deviations = sorted(abs(value - median) for value in values)
    mad = _quantile(deviations, 0.5)
    if mad == 0.0:
        return None, None, OutlierStatus.NUMERICAL_DEGENERACY
    scale = threshold / _MODIFIED_Z_SCALE
    lower = median - scale * mad
    upper = median + scale * mad
    return _finite_bounds(lower, upper)


def _quantile(ordered: list[float], q: float) -> float:
    position = q * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def _finite_bounds(
    lower: float, upper: float
) -> tuple[float | None, float | None, OutlierStatus]:
    if not math.isfinite(lower) or not math.isfinite(upper):
        return None, None, OutlierStatus.NUMERICAL_DEGENERACY
    return lower, upper, OutlierStatus.SUCCESS


def _result(
    method: OutlierMethod,
    column: str,
    valid_count: int,
    skipped_count: int,
    outlier_count: int,
    lower_bound: float | None,
    upper_bound: float | None,
    status: OutlierStatus,
) -> OutlierResult:
    return OutlierResult(
        method,
        column,
        valid_count,
        skipped_count,
        outlier_count,
        lower_bound,
        upper_bound,
        status,
    )


def _validate_inputs(table: AnalysisTable, column: str, method: OutlierMethod) -> None:
    if column not in table.column_names:
        raise InvalidAnalysisInputError(f"unknown analysis column: {column}")
    schema = next(item for item in table.columns if item.name == column)
    if schema.data_type not in {"integer", "number", "null"}:
        raise InvalidAnalysisInputError(f"column {column!r} is not numeric")
    if not isinstance(method, OutlierMethod):
        raise InvalidAnalysisInputError("method must be an OutlierMethod")


def _validate_threshold(method: OutlierMethod, threshold: float | None) -> float:
    default = {
        OutlierMethod.IQR: 1.5,
        OutlierMethod.Z_SCORE: 3.0,
        OutlierMethod.MODIFIED_Z_SCORE: 3.5,
    }[method]
    value = default if threshold is None else threshold
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidAnalysisInputError("threshold must be a finite positive number")
    value = float(value)
    if not math.isfinite(value) or value <= 0:
        raise InvalidAnalysisInputError("threshold must be a finite positive number")
    return value


__all__ = [
    "OutlierDetectionOperation",
    "OutlierMethod",
    "OutlierResult",
    "OutlierStatus",
    "detect_outliers",
]
