"""Deterministic, bounded CPU grouped aggregation."""

from dataclasses import dataclass
from enum import Enum
import math

from .contracts import AnalysisLimits, AnalysisOperation, AnalysisTable, OperationMetadata
from .errors import AnalysisLimitError, InvalidAnalysisInputError


class AggregationStatus(str, Enum):
    SUCCESS = "success"
    INSUFFICIENT_DATA = "insufficient_data"
    NUMERICAL_DEGENERACY = "numerical_degeneracy"


@dataclass(frozen=True, slots=True)
class AggregateGroup:
    key: object
    row_count: int
    valid_count: int
    missing_count: int
    total: float | None
    mean: float | None
    minimum: float | None
    maximum: float | None


@dataclass(frozen=True, slots=True)
class AggregationResult:
    group_column: str
    measure_column: str
    groups: tuple[AggregateGroup, ...]
    status: AggregationStatus


@dataclass(frozen=True, slots=True)
class GroupedAggregationOperation:
    metadata: OperationMetadata = OperationMetadata(
        "grouped_aggregation",
        "Compute bounded grouped numeric summaries",
        True,
    )

    def execute(
        self,
        table: AnalysisTable,
        *,
        group_column: str,
        measure_column: str,
        limits: AnalysisLimits = AnalysisLimits(),
        max_groups: int = 100_000,
    ) -> AggregationResult:
        return grouped_aggregation(
            table,
            group_column=group_column,
            measure_column=measure_column,
            limits=limits,
            max_groups=max_groups,
        )


class _GroupState:
    __slots__ = (
        "key",
        "row_count",
        "valid_count",
        "missing_count",
        "total",
        "compensation",
        "minimum",
        "maximum",
    )

    def __init__(self, key: object) -> None:
        self.key = key
        self.row_count = 0
        self.valid_count = 0
        self.missing_count = 0
        self.total = 0.0
        self.compensation = 0.0
        self.minimum = None
        self.maximum = None

    def add(self, value: object) -> bool:
        self.row_count += 1
        if value is None:
            self.missing_count += 1
            return True
        number = float(value)
        self.valid_count += 1
        updated = self.total + number
        if abs(self.total) >= abs(number):
            self.compensation += (self.total - updated) + number
        else:
            self.compensation += (number - updated) + self.total
        self.total = updated
        minimum = number if self.minimum is None else min(self.minimum, number)
        maximum = number if self.maximum is None else max(self.maximum, number)
        self.minimum = minimum
        self.maximum = maximum
        corrected_total = self.total + self.compensation
        mean = corrected_total / self.valid_count
        return all(
            math.isfinite(item)
            for item in (self.total, self.compensation, corrected_total, mean, minimum, maximum)
        )

    def result(self) -> AggregateGroup:
        corrected_total = self.total + self.compensation
        mean = None if self.valid_count == 0 else corrected_total / self.valid_count
        return AggregateGroup(
            self.key,
            self.row_count,
            self.valid_count,
            self.missing_count,
            None if self.valid_count == 0 else corrected_total,
            mean,
            self.minimum,
            self.maximum,
        )


def grouped_aggregation(
    table: AnalysisTable,
    *,
    group_column: str,
    measure_column: str,
    limits: AnalysisLimits = AnalysisLimits(),
    max_groups: int = 100_000,
) -> AggregationResult:
    group_type = _validate_inputs(table, group_column, measure_column, max_groups)
    states: dict[object, _GroupState] = {}
    processed = 0
    degenerate = False
    for row in table.rows():
        processed += 1
        if limits.max_rows is not None and processed > limits.max_rows:
            raise AnalysisLimitError("maximum rows processed exceeded")
        key = row[group_column]
        state = states.get(key)
        if state is None:
            if len(states) >= max_groups:
                raise AnalysisLimitError("maximum groups exceeded")
            state = _GroupState(key)
            states[key] = state
        if not state.add(row[measure_column]):
            degenerate = True
    if degenerate:
        return AggregationResult(group_column, measure_column, (), AggregationStatus.NUMERICAL_DEGENERACY)
    ordered = sorted(states.values(), key=lambda state: _group_sort_key(state.key, group_type))
    groups = tuple(state.result() for state in ordered)
    status = AggregationStatus.SUCCESS if groups else AggregationStatus.INSUFFICIENT_DATA
    return AggregationResult(group_column, measure_column, groups, status)


def _validate_inputs(
    table: AnalysisTable, group_column: str, measure_column: str, max_groups: int
) -> str:
    if group_column not in table.column_names:
        raise InvalidAnalysisInputError(f"unknown analysis column: {group_column}")
    if measure_column not in table.column_names:
        raise InvalidAnalysisInputError(f"unknown analysis column: {measure_column}")
    if group_column == measure_column:
        raise InvalidAnalysisInputError("group and measure columns must differ")
    if isinstance(max_groups, bool) or not isinstance(max_groups, int) or max_groups < 1:
        raise InvalidAnalysisInputError("max_groups must be a positive integer")
    schemas = {schema.name: schema.data_type for schema in table.columns}
    measure_type = schemas[measure_column]
    if measure_type not in {"integer", "number", "null"}:
        raise InvalidAnalysisInputError(f"column {measure_column!r} is not numeric")
    return schemas[group_column]


def _group_sort_key(key: object, data_type: str) -> tuple[int, object]:
    if key is None:
        return (0, 0)
    if data_type == "boolean":
        return (1, bool(key))
    if data_type in {"integer", "number"}:
        return (1, float(key))
    return (1, str(key))


__all__ = [
    "AggregateGroup",
    "AggregationResult",
    "AggregationStatus",
    "GroupedAggregationOperation",
    "grouped_aggregation",
]
