"""Deterministic, bounded CPU correlation operations."""

from dataclasses import dataclass
from enum import Enum
import math

from .contracts import AnalysisLimits, AnalysisOperation, AnalysisTable, OperationMetadata
from .errors import AnalysisLimitError, InvalidAnalysisInputError


class CorrelationMethod(str, Enum):
    PEARSON = "pearson"
    SPEARMAN = "spearman"


class CorrelationStatus(str, Enum):
    SUCCESS = "success"
    INSUFFICIENT_DATA = "insufficient_data"
    CONSTANT_COLUMN = "constant_column"
    NUMERICAL_DEGENERACY = "numerical_degeneracy"


@dataclass(frozen=True, slots=True)
class CorrelationResult:
    method: CorrelationMethod
    left_column: str
    right_column: str
    valid_pair_count: int
    skipped_pair_count: int
    coefficient: float | None
    status: CorrelationStatus


@dataclass(frozen=True, slots=True)
class PearsonCorrelationOperation:
    metadata: OperationMetadata = OperationMetadata(
        "pearson_correlation", "Compute pairwise Pearson correlation", True
    )

    def execute(
        self,
        table: AnalysisTable,
        *,
        left_column: str,
        right_column: str,
        limits: AnalysisLimits = AnalysisLimits(),
    ) -> CorrelationResult:
        return pearson_correlation(
            table, left_column=left_column, right_column=right_column, limits=limits
        )


@dataclass(frozen=True, slots=True)
class SpearmanCorrelationOperation:
    metadata: OperationMetadata = OperationMetadata(
        "spearman_correlation", "Compute exact pairwise Spearman correlation", True
    )

    def execute(
        self,
        table: AnalysisTable,
        *,
        left_column: str,
        right_column: str,
        limits: AnalysisLimits = AnalysisLimits(),
    ) -> CorrelationResult:
        return spearman_correlation(
            table, left_column=left_column, right_column=right_column, limits=limits
        )


def pearson_correlation(
    table: AnalysisTable,
    *,
    left_column: str,
    right_column: str,
    limits: AnalysisLimits = AnalysisLimits(),
) -> CorrelationResult:
    _validate_inputs(table, left_column, right_column)
    state = _Accumulator()
    skipped = 0
    processed = 0
    for row in table.rows():
        processed += 1
        _check_row_limit(processed, limits)
        left = row[left_column]
        right = row[right_column]
        if left is None or right is None:
            skipped += 1
            continue
        state.add(float(left), float(right))
    status, coefficient = state.result()
    if state.count < 2:
        status, coefficient = CorrelationStatus.INSUFFICIENT_DATA, None
    return CorrelationResult(
        CorrelationMethod.PEARSON,
        left_column,
        right_column,
        state.count,
        skipped,
        coefficient,
        status,
    )


def spearman_correlation(
    table: AnalysisTable,
    *,
    left_column: str,
    right_column: str,
    limits: AnalysisLimits = AnalysisLimits(),
) -> CorrelationResult:
    _validate_inputs(table, left_column, right_column)
    pairs: list[tuple[float, float]] = []
    skipped = 0
    processed = 0
    for row in table.rows():
        processed += 1
        _check_row_limit(processed, limits)
        left = row[left_column]
        right = row[right_column]
        if left is None or right is None:
            skipped += 1
            continue
        if (
            limits.max_materialized_values is not None
            and (len(pairs) + 1) * 2 > limits.max_materialized_values
        ):
            raise AnalysisLimitError("maximum materialized values exceeded")
        pairs.append((float(left), float(right)))

    left_ranks = _average_ranks([pair[0] for pair in pairs])
    right_ranks = _average_ranks([pair[1] for pair in pairs])
    state = _Accumulator()
    for left, right in zip(left_ranks, right_ranks, strict=True):
        state.add(left, right)
    status, coefficient = state.result()
    if state.count < 2:
        status, coefficient = CorrelationStatus.INSUFFICIENT_DATA, None
    return CorrelationResult(
        CorrelationMethod.SPEARMAN,
        left_column,
        right_column,
        state.count,
        skipped,
        coefficient,
        status,
    )


class _Accumulator:
    __slots__ = (
        "count",
        "mean_left",
        "mean_right",
        "sum_left_left",
        "sum_right_right",
        "sum_cross",
        "left_constant",
        "right_constant",
        "_first_left",
        "_first_right",
    )

    def __init__(self) -> None:
        self.count = 0
        self.mean_left = 0.0
        self.mean_right = 0.0
        self.sum_left_left = 0.0
        self.sum_right_right = 0.0
        self.sum_cross = 0.0
        self.left_constant = True
        self.right_constant = True
        self._first_left = None
        self._first_right = None

    def add(self, left: float, right: float) -> None:
        if not math.isfinite(left) or not math.isfinite(right):
            raise InvalidAnalysisInputError("non-finite numeric values are not supported")
        if self.count == 0:
            self._first_left = left
            self._first_right = right
        else:
            self.left_constant &= left == self._first_left
            self.right_constant &= right == self._first_right
        self.count += 1
        delta_left = left - self.mean_left
        delta_right = right - self.mean_right
        self.mean_left += delta_left / self.count
        self.mean_right += delta_right / self.count
        self.sum_left_left += delta_left * (left - self.mean_left)
        self.sum_right_right += delta_right * (right - self.mean_right)
        self.sum_cross += delta_left * (right - self.mean_right)

    def result(self) -> tuple[CorrelationStatus, float | None]:
        if self.left_constant or self.right_constant:
            return CorrelationStatus.CONSTANT_COLUMN, None
        if not all(
            math.isfinite(value)
            for value in (
                self.sum_left_left,
                self.sum_right_right,
                self.sum_cross,
            )
        ):
            return CorrelationStatus.NUMERICAL_DEGENERACY, None
        denominator = math.sqrt(self.sum_left_left * self.sum_right_right)
        if not math.isfinite(denominator) or denominator <= 0:
            return CorrelationStatus.NUMERICAL_DEGENERACY, None
        coefficient = self.sum_cross / denominator
        if not math.isfinite(coefficient):
            return CorrelationStatus.NUMERICAL_DEGENERACY, None
        return CorrelationStatus.SUCCESS, max(-1.0, min(1.0, coefficient))


def _average_ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [0.0] * len(values)
    position = 0
    while position < len(ordered):
        end = position + 1
        value = ordered[position][1]
        while end < len(ordered) and ordered[end][1] == value:
            end += 1
        average = (position + 1 + end) / 2.0
        for index, _ in ordered[position:end]:
            ranks[index] = average
        position = end
    return ranks


def _validate_inputs(table: AnalysisTable, left_column: str, right_column: str) -> None:
    numeric_types = {"integer", "number", "null"}
    names = table.column_names
    for column in (left_column, right_column):
        if column not in names:
            raise InvalidAnalysisInputError(f"unknown analysis column: {column}")
        schema = next(item for item in table.columns if item.name == column)
        if schema.data_type not in numeric_types:
            raise InvalidAnalysisInputError(f"column {column!r} is not numeric")


def _check_row_limit(processed: int, limits: AnalysisLimits) -> None:
    if limits.max_rows is not None and processed > limits.max_rows:
        raise AnalysisLimitError("maximum rows processed exceeded")
