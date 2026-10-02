import math
import sqlite3
from pathlib import Path

import pytest

from nexus.analysis import (
    AnalysisLimitError,
    AnalysisLimits,
    AnalysisTable,
    ColumnSchema,
    InsufficientDataError,
    InvalidAnalysisInputError,
    descriptive_statistics,
    exact_quantile,
    from_rows,
    from_source,
)
from nexus.datasets.models import DatasetSource


def numeric_table(values: list[object]) -> AnalysisTable:
    return from_rows(
        (ColumnSchema("value", "number"),),
        lambda: ({"value": value} for value in values),
    )


def test_statistics_are_stable_and_use_population_and_sample_semantics() -> None:
    table = numeric_table([1.0, -2.0, 3.0, None, 4.0])
    result = descriptive_statistics(table, column="value")
    assert result.count == 5
    assert result.valid_count == 4
    assert result.null_count == 1
    assert result.minimum == -2.0
    assert result.maximum == 4.0
    assert result.mean == 1.5
    assert result.population_variance == pytest.approx(5.25)
    assert result.sample_variance == pytest.approx(7.0)
    assert result == descriptive_statistics(table, column="value")


@pytest.mark.parametrize("values", [[], [None, None]])
def test_empty_and_all_null_statistics_are_explicit(values: list[object]) -> None:
    result = descriptive_statistics(numeric_table(values), column="value")
    assert result.valid_count == 0
    assert result.mean is None
    assert result.population_standard_deviation is None
    assert result.sample_standard_deviation is None


def test_single_value_and_bool_are_handled_explicitly() -> None:
    result = descriptive_statistics(numeric_table([7]), column="value")
    assert result.population_variance == 0.0
    assert result.sample_variance is None
    with pytest.raises(InvalidAnalysisInputError):
        descriptive_statistics(
            from_rows((ColumnSchema("value", "boolean"),), lambda: ({"value": True},)),
            column="value",
        )


def test_quantile_interpolates_exactly_and_is_bounded() -> None:
    table = numeric_table([4, 1, None, 2, 3])
    assert exact_quantile(table, column="value", q=0) == 1.0
    assert exact_quantile(table, column="value", q=1) == 4.0
    assert exact_quantile(table, column="value", q=0.5) == 2.5
    with pytest.raises(AnalysisLimitError):
        exact_quantile(
            table,
            column="value",
            q=0.5,
            limits=AnalysisLimits(max_materialized_values=3),
        )


def test_quantile_validates_parameters_and_data() -> None:
    with pytest.raises(InvalidAnalysisInputError):
        exact_quantile(numeric_table([1]), column="value", q=1.1)
    with pytest.raises(InsufficientDataError):
        exact_quantile(numeric_table([None]), column="value", q=0.5)
    with pytest.raises(InvalidAnalysisInputError):
        exact_quantile(numeric_table([math.inf]), column="value", q=0.5)


def test_csv_adapter_types_numeric_boolean_and_missing_values(tmp_path: Path) -> None:
    path = tmp_path / "values.csv"
    path.write_text("value,flag\n1,true\n2,false\n,\n", encoding="utf-8")
    table = from_source(DatasetSource(path, "csv"))
    assert table.columns[0].data_type == "integer"
    assert table.columns[1].data_type == "boolean"
    assert list(table.column_values("value")) == [1, 2, None]
    assert descriptive_statistics(table, column="value").mean == 1.5


def test_jsonl_strings_are_not_operation_coerced(tmp_path: Path) -> None:
    path = tmp_path / "values.jsonl"
    path.write_text('{"value":"1"}\n{"value":"2"}\n', encoding="utf-8")
    table = from_source(DatasetSource(path, "jsonl"))
    assert table.columns[0].data_type == "string"
    with pytest.raises(InvalidAnalysisInputError):
        descriptive_statistics(table, column="value")


def test_sqlite_native_numbers_and_read_only_source(tmp_path: Path) -> None:
    path = tmp_path / "values.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("create table records (value integer)")
        connection.executemany("insert into records values (?)", [(1,), (2,)])
    before = path.read_bytes()
    table = from_source(DatasetSource(path, "sqlite", "records"))
    assert table.columns[0].data_type == "integer"
    assert descriptive_statistics(table, column="value").mean == 1.5
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    ("payload", "data_type"),
    [
        ('{"value":1}\n{"value":2}\n', "integer"),
        ('{"value":true}\n{"value":false}\n', "boolean"),
        ('{"value":"one"}\n{"value":"two"}\n', "string"),
        ('{"value":1}\n{"value":null}\n{"value":2}\n', "integer"),
    ],
)
def test_jsonl_homogeneous_and_nullable_types(
    tmp_path: Path, payload: str, data_type: str
) -> None:
    path = tmp_path / "values.jsonl"
    path.write_text(payload, encoding="utf-8")
    table = from_source(DatasetSource(path, "jsonl"))
    assert table.columns[0].data_type == data_type
    assert list(table.column_values("value")) == list(table.column_values("value"))


def test_mixed_jsonl_types_are_rejected_deterministically(tmp_path: Path) -> None:
    path = tmp_path / "values.jsonl"
    path.write_text('{"value":1}\n{"value":"text"}\n', encoding="utf-8")
    with pytest.raises(InvalidAnalysisInputError, match="heterogeneous"):
        from_source(DatasetSource(path, "jsonl"))


def test_mixed_sqlite_types_are_rejected_deterministically(tmp_path: Path) -> None:
    path = tmp_path / "values.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("create table records (value)")
        connection.executemany("insert into records values (?)", [(1,), ("text",)])
    with pytest.raises(InvalidAnalysisInputError, match="heterogeneous"):
        from_source(DatasetSource(path, "sqlite", "records"))


def test_analysis_table_enforces_schema_and_nullability() -> None:
    valid = from_rows(
        (ColumnSchema("value", "number"),),
        lambda: ({"value": 1.5}, {"value": None}),
    )
    assert list(valid.column_values("value")) == [1.5, None]
    cases = [
        (ColumnSchema("value", "number"), {"value": True}),
        (ColumnSchema("value", "number"), {"value": "1"}),
        (ColumnSchema("value", "boolean"), {"value": 1}),
        (ColumnSchema("value", "boolean"), {"value": "true"}),
        (ColumnSchema("value", "string"), {"value": 1}),
        (ColumnSchema("value", "number", nullable=False), {"value": None}),
        (ColumnSchema("value", "number"), {"value": object()}),
    ]
    for schema, row in cases:
        with pytest.raises(InvalidAnalysisInputError):
            list(from_rows((schema,), lambda row=row: (row,)).rows())


def test_from_rows_requires_replayable_factory() -> None:
    with pytest.raises(InvalidAnalysisInputError, match="callable"):
        from_rows((ColumnSchema("value", "number"),), iter(({"value": 1},)))


def test_analysis_table_factory_is_replayable() -> None:
    table = from_rows(
        (ColumnSchema("value", "integer"),),
        lambda: ({"value": value} for value in (1, 2)),
    )
    assert list(table.column_values("value")) == [1, 2]
    assert list(table.column_values("value")) == [1, 2]


@pytest.mark.parametrize("token", ["NaN", "nan", "INF", "inf", "-INF", "-inf", "1e999"])
def test_csv_nonfinite_numeric_values_are_rejected(tmp_path: Path, token: str) -> None:
    path = tmp_path / "values.csv"
    path.write_text(f"value\n{token}\n", encoding="utf-8")
    with pytest.raises(InvalidAnalysisInputError, match="non-finite"):
        from_source(DatasetSource(path, "csv"))


def test_max_rows_is_exact_and_deterministic(tmp_path: Path) -> None:
    path = tmp_path / "values.csv"
    path.write_text("value\n1\n2\n", encoding="utf-8")
    exact = from_source(DatasetSource(path, "csv"), AnalysisLimits(max_rows=2))
    assert descriptive_statistics(exact, column="value").valid_count == 2
    with pytest.raises(AnalysisLimitError):
        from_source(DatasetSource(path, "csv"), AnalysisLimits(max_rows=1))


def test_operations_enforce_max_rows_without_partial_results() -> None:
    table = numeric_table([1, 2, 3])
    limits = AnalysisLimits(max_rows=2)
    with pytest.raises(AnalysisLimitError):
        descriptive_statistics(table, column="value", limits=limits)
    with pytest.raises(AnalysisLimitError):
        exact_quantile(table, column="value", q=0.5, limits=limits)
    bounded = numeric_table([1, 2])
    assert descriptive_statistics(bounded, column="value", limits=limits).valid_count == 2
    assert exact_quantile(bounded, column="value", q=0.5, limits=limits) == 1.5
