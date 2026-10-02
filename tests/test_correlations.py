import math
import sqlite3
from pathlib import Path
from dataclasses import FrozenInstanceError

import pytest

from nexus.analysis import (
    AnalysisLimitError,
    AnalysisLimits,
    AnalysisTable,
    ColumnSchema,
    CorrelationMethod,
    CorrelationStatus,
    PearsonCorrelationOperation,
    SpearmanCorrelationOperation,
    InvalidAnalysisInputError,
    from_rows,
    from_source,
    pearson_correlation,
    spearman_correlation,
)
from nexus.datasets.models import DatasetSource


def table(left: list[object], right: list[object]) -> AnalysisTable:
    return from_rows(
        (ColumnSchema("left", "number"), ColumnSchema("right", "number")),
        lambda: (
            {"left": x, "right": y}
            for x, y in zip(left, right, strict=True)
        ),
    )


def test_correlation_contract_and_exports() -> None:
    result = pearson_correlation(table([1, 2], [2, 4]), left_column="left", right_column="right")
    assert result.method is CorrelationMethod.PEARSON
    assert result.status is CorrelationStatus.SUCCESS
    assert result.coefficient == 1.0
    with pytest.raises(FrozenInstanceError):
        result.coefficient = 0.0


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ([1, 2, 3], [2, 4, 6], 1.0),
        ([1, 2, 3], [6, 4, 2], -1.0),
        ([1, 2, 4], [2, 5, 3], 1 / 7),
    ],
)
def test_pearson_known_values(left: list[int], right: list[int], expected: float) -> None:
    result = pearson_correlation(table(left, right), left_column="left", right_column="right")
    assert result.status is CorrelationStatus.SUCCESS
    assert result.coefficient == pytest.approx(expected)
    assert -1.0 <= result.coefficient <= 1.0


def test_pearson_missingness_and_repeated_execution() -> None:
    source = table([1, None, 3, None], [2, 4, None, None])
    first = pearson_correlation(source, left_column="left", right_column="right")
    assert first.valid_pair_count == 1
    assert first.skipped_pair_count == 3
    assert first.status is CorrelationStatus.INSUFFICIENT_DATA
    assert first == pearson_correlation(source, left_column="left", right_column="right")


@pytest.mark.parametrize(
    ("left", "right"),
    [([1, 1, 1], [1, 2, 3]), ([1, 2, 3], [2, 2, 2])],
)
def test_pearson_constant_columns(left: list[int], right: list[int]) -> None:
    result = pearson_correlation(table(left, right), left_column="left", right_column="right")
    assert result.status is CorrelationStatus.CONSTANT_COLUMN
    assert result.coefficient is None


def test_pearson_numerical_degeneracy_is_distinct() -> None:
    result = pearson_correlation(
        table([1e308, -1e308], [1e308, -1e308]),
        left_column="left",
        right_column="right",
    )
    assert result.status is CorrelationStatus.NUMERICAL_DEGENERACY
    assert result.coefficient is None


def test_pearson_stable_accumulation_with_large_offsets() -> None:
    result = pearson_correlation(
        table(
            [1_000_000_000_001, 1_000_000_000_002, 1_000_000_000_004, 1_000_000_000_008],
            [1, 2, 3, 5],
        ),
        left_column="left",
        right_column="right",
    )
    assert result.status is CorrelationStatus.SUCCESS
    # Reference value is computed from the small centered offsets [1, 2, 4, 8].
    assert result.coefficient == pytest.approx(0.9930191118612668, abs=2e-6)


def test_pearson_limits_and_invalid_schema() -> None:
    source = table([1, 2], [2, 4])
    assert pearson_correlation(
        source, left_column="left", right_column="right", limits=AnalysisLimits(max_rows=2)
    ).status is CorrelationStatus.SUCCESS
    with pytest.raises(AnalysisLimitError):
        pearson_correlation(
            table([1, 2, 3], [2, 4, 6]),
            left_column="left",
            right_column="right",
            limits=AnalysisLimits(max_rows=2),
        )
    strings = from_rows(
        (ColumnSchema("left", "string"), ColumnSchema("right", "number")),
        lambda: ({"left": "1", "right": 2},),
    )
    with pytest.raises(InvalidAnalysisInputError):
        pearson_correlation(strings, left_column="left", right_column="right")


@pytest.mark.parametrize("operation", [pearson_correlation, spearman_correlation])
@pytest.mark.parametrize("left_column, right_column", [("missing", "right"), ("left", "missing")])
def test_correlations_reject_missing_columns(
    operation, left_column: str, right_column: str
) -> None:
    with pytest.raises(InvalidAnalysisInputError):
        operation(table([1, 2], [2, 4]), left_column=left_column, right_column=right_column)


@pytest.mark.parametrize("operation", [pearson_correlation, spearman_correlation])
@pytest.mark.parametrize("boolean_column", ["left", "right"])
def test_correlations_reject_boolean_columns(operation, boolean_column: str) -> None:
    columns = (
        ColumnSchema("left", "boolean")
        if boolean_column == "left"
        else ColumnSchema("left", "number")
    )
    other = (
        ColumnSchema("right", "number")
        if boolean_column == "left"
        else ColumnSchema("right", "boolean")
    )
    source = from_rows(
        (columns, other),
        lambda: (
            {"left": True, "right": 1}
            if boolean_column == "left"
            else {"left": 1, "right": True},
        ),
    )
    with pytest.raises(InvalidAnalysisInputError):
        operation(source, left_column="left", right_column="right")


def test_correlation_operation_metadata_and_execution() -> None:
    pearson = PearsonCorrelationOperation()
    spearman = SpearmanCorrelationOperation()
    assert pearson.metadata.name == "pearson_correlation"
    assert pearson.metadata.description == "Compute pairwise Pearson correlation"
    assert pearson.metadata.exact is True
    assert spearman.metadata.name == "spearman_correlation"
    assert spearman.metadata.description == "Compute exact pairwise Spearman correlation"
    assert spearman.metadata.exact is True
    assert pearson.execute(
        table([1, 2], [2, 4]), left_column="left", right_column="right"
    ).coefficient == 1.0
    assert spearman.execute(
        table([1, 2], [2, 4]), left_column="left", right_column="right"
    ).coefficient == 1.0


@pytest.mark.parametrize(
    "kwargs",
    [{"max_rows": 0}, {"max_materialized_values": 0}],
)
def test_correlation_rejects_invalid_limits(kwargs: dict[str, int]) -> None:
    with pytest.raises(InvalidAnalysisInputError):
        pearson_correlation(
            table([1, 2], [2, 4]),
            left_column="left",
            right_column="right",
            limits=AnalysisLimits(**kwargs),
        )


@pytest.mark.parametrize(
    ("left", "right", "expected"),
    [
        ([1, 2, 3], [10, 20, 30], 1.0),
        ([1, 2, 3], [30, 20, 10], -1.0),
        ([1, 2, 3, 4], [10, 30, 20, 40], 0.8),
    ],
)
def test_spearman_known_values(left: list[int], right: list[int], expected: float) -> None:
    result = spearman_correlation(table(left, right), left_column="left", right_column="right")
    assert result.status is CorrelationStatus.SUCCESS
    assert result.coefficient == pytest.approx(expected)


def test_spearman_average_ties_and_determinism() -> None:
    source = table([1, 1, 2, 3], [1, 2, 2, 3])
    first = spearman_correlation(source, left_column="left", right_column="right")
    assert first.status is CorrelationStatus.SUCCESS
    assert first.coefficient == pytest.approx(0.8333333333333334)
    assert first == spearman_correlation(source, left_column="left", right_column="right")


def test_spearman_missingness_constant_and_insufficient_data() -> None:
    result = spearman_correlation(
        table([1, None, 3, None], [2, 4, None, None]),
        left_column="left",
        right_column="right",
    )
    assert result.valid_pair_count == 1
    assert result.skipped_pair_count == 3
    assert result.status is CorrelationStatus.INSUFFICIENT_DATA
    constant = spearman_correlation(
        table([1, 1, 1], [1, 2, 3]), left_column="left", right_column="right"
    )
    assert constant.status is CorrelationStatus.CONSTANT_COLUMN


def test_spearman_materialization_and_row_limits() -> None:
    source = table([1, 2], [2, 1])
    assert spearman_correlation(
        source,
        left_column="left",
        right_column="right",
        limits=AnalysisLimits(max_materialized_values=4),
    ).coefficient == -1.0
    with pytest.raises(AnalysisLimitError):
        spearman_correlation(
            source,
            left_column="left",
            right_column="right",
            limits=AnalysisLimits(max_materialized_values=3),
        )
    with pytest.raises(AnalysisLimitError):
        spearman_correlation(
            table([1, 2, 3], [3, 2, 1]),
            left_column="left",
            right_column="right",
            limits=AnalysisLimits(max_rows=2),
        )


def test_spearman_exact_max_rows_boundary_succeeds() -> None:
    source = table([1, 2], [2, 1])
    result = spearman_correlation(
        source,
        left_column="left",
        right_column="right",
        limits=AnalysisLimits(max_rows=2),
    )
    assert result.status is CorrelationStatus.SUCCESS
    assert result.valid_pair_count == 2
    with pytest.raises(AnalysisLimitError):
        spearman_correlation(
            table([1, 2, 3], [2, 1, 3]),
            left_column="left",
            right_column="right",
            limits=AnalysisLimits(max_rows=2),
        )


def test_spearman_missing_values_do_not_consume_materialization_budget() -> None:
    result = spearman_correlation(
        table([1, None, 2], [2, 3, 4]),
        left_column="left",
        right_column="right",
        limits=AnalysisLimits(max_materialized_values=4),
    )
    assert result.valid_pair_count == 2
    assert result.skipped_pair_count == 1
    assert result.coefficient == 1.0


@pytest.mark.parametrize(
    ("suffix", "content", "format_name", "table_name"),
    [
        (".csv", "left,right\n1,2\n2,4\n3,6\n", "csv", None),
        (".jsonl", '{"left":1,"right":2}\n{"left":2,"right":4}\n', "jsonl", None),
    ],
)
def test_source_adapters_feed_correlations(
    tmp_path: Path, suffix: str, content: str, format_name: str, table_name: str | None
) -> None:
    path = tmp_path / f"values{suffix}"
    path.write_text(content, encoding="utf-8")
    result = pearson_correlation(
        from_source(DatasetSource(path, format_name, table_name)),
        left_column="left",
        right_column="right",
    )
    assert result.coefficient == 1.0


def test_sqlite_correlation_is_read_only(tmp_path: Path) -> None:
    path = tmp_path / "values.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("create table records (left integer, right integer)")
        connection.executemany("insert into records values (?, ?)", [(1, 2), (2, 4)])
    before = path.read_bytes()
    result = pearson_correlation(
        from_source(DatasetSource(path, "sqlite", "records")),
        left_column="left",
        right_column="right",
    )
    assert result.coefficient == 1.0
    assert path.read_bytes() == before


def test_numeric_looking_json_strings_are_rejected() -> None:
    source = from_rows(
        (ColumnSchema("left", "string"), ColumnSchema("right", "number")),
        lambda: ({"left": "1", "right": 2},),
    )
    with pytest.raises(InvalidAnalysisInputError):
        spearman_correlation(source, left_column="left", right_column="right")


def test_json_numeric_looking_strings_are_rejected_at_adapter_boundary(tmp_path: Path) -> None:
    path = tmp_path / "values.jsonl"
    path.write_text('{"left":"1","right":2}\n{"left":"2","right":4}\n', encoding="utf-8")
    source = from_source(DatasetSource(path, "jsonl"))
    with pytest.raises(InvalidAnalysisInputError):
        pearson_correlation(source, left_column="left", right_column="right")


def test_nonfinite_values_are_rejected() -> None:
    source = from_rows(
        (ColumnSchema("left", "number"), ColumnSchema("right", "number")),
        lambda: ({"left": math.inf, "right": 1.0},),
    )
    with pytest.raises(InvalidAnalysisInputError):
        pearson_correlation(source, left_column="left", right_column="right")
