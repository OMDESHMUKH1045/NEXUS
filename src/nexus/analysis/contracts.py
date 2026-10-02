"""Immutable contracts shared by CPU analysis operations."""

from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass
import math
from typing import Any, Protocol

from .errors import InvalidAnalysisInputError


_TYPES = frozenset({"null", "boolean", "integer", "number", "string"})


@dataclass(frozen=True, slots=True)
class ColumnSchema:
    name: str
    data_type: str
    nullable: bool = True

    def __post_init__(self) -> None:
        if not self.name:
            raise InvalidAnalysisInputError("column name must not be empty")
        if self.data_type not in _TYPES:
            raise InvalidAnalysisInputError(f"unsupported column type: {self.data_type}")
        if self.data_type == "null" and not self.nullable:
            raise InvalidAnalysisInputError("null columns must be nullable")


@dataclass(frozen=True, slots=True)
class AnalysisLimits:
    max_rows: int | None = 100_000
    max_materialized_values: int | None = 100_000

    def __post_init__(self) -> None:
        if self.max_rows is not None and self.max_rows < 1:
            raise InvalidAnalysisInputError("max_rows must be at least 1 or None")
        if self.max_materialized_values is not None and self.max_materialized_values < 1:
            raise InvalidAnalysisInputError(
                "max_materialized_values must be at least 1 or None"
            )


@dataclass(frozen=True, slots=True)
class OperationMetadata:
    name: str
    description: str
    exact: bool = True

    def __post_init__(self) -> None:
        if not self.name or not self.description:
            raise InvalidAnalysisInputError("operation metadata requires name and description")


class AnalysisOperation(Protocol):
    metadata: OperationMetadata

    def execute(self, table: "AnalysisTable", **kwargs: Any) -> Any:
        ...


class AnalysisTable:
    """A typed, replayable row boundary; rows are not materialized by default."""

    __slots__ = ("_columns", "_row_factory")

    def __init__(
        self,
        columns: Iterable[ColumnSchema],
        row_factory: Callable[[], Iterable[Mapping[str, object]]],
    ) -> None:
        schemas = tuple(columns)
        if not schemas or len({column.name for column in schemas}) != len(schemas):
            raise InvalidAnalysisInputError("analysis table requires unique columns")
        if not callable(row_factory):
            raise InvalidAnalysisInputError("row_factory must be callable")
        self._columns = schemas
        self._row_factory = row_factory

    @property
    def columns(self) -> tuple[ColumnSchema, ...]:
        return self._columns

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self._columns)

    def rows(self) -> Iterator[Mapping[str, object]]:
        for row in self._row_factory():
            if not isinstance(row, Mapping):
                raise InvalidAnalysisInputError("analysis rows must be mappings")
            if set(row) != set(self.column_names):
                raise InvalidAnalysisInputError("analysis row fields do not match schema")
            for schema in self._columns:
                _validate_value(schema, row[schema.name])
            yield row

    def column_values(self, name: str) -> Iterator[object]:
        if name not in self.column_names:
            raise InvalidAnalysisInputError(f"unknown analysis column: {name}")
        return (row[name] for row in self.rows())


def _validate_value(schema: ColumnSchema, value: object) -> None:
    if value is None:
        if not schema.nullable:
            raise InvalidAnalysisInputError(f"column {schema.name!r} does not allow missing values")
        return
    valid = (
        schema.data_type == "boolean" and isinstance(value, bool)
    ) or (
        schema.data_type == "integer"
        and isinstance(value, int)
        and not isinstance(value, bool)
    ) or (
        schema.data_type == "number"
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ) or (
        schema.data_type == "string" and isinstance(value, str)
    )
    if valid and schema.data_type in {"integer", "number"}:
        valid = math.isfinite(float(value))
    if not valid:
        raise InvalidAnalysisInputError(
            f"value does not conform to {schema.data_type} column {schema.name!r}"
        )
