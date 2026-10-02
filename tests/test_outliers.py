import math
import sqlite3
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from nexus.analysis import (
    AnalysisLimitError,
    AnalysisLimits,
    ColumnSchema,
    InvalidAnalysisInputError,
    OutlierDetectionOperation,
    OutlierMethod,
    OutlierStatus,
    detect_outliers,
    from_rows,
    from_source,
)
from nexus.datasets.models import DatasetSource


def table(values: list[object]):
    return from_rows(
        (ColumnSchema("value", "number"),),
        lambda: ({"value": value} for value in values),
    )


@pytest.mark.parametrize(
    ("method", "value"),
    [
        (OutlierMethod.IQR, "iqr"),
        (OutlierMethod.Z_SCORE, "z_score"),
        (OutlierMethod.MODIFIED_Z_SCORE, "modified_z_score"),
    ],
)
def test_outlier_contract_exports_and_immutable_result(
    method: OutlierMethod, value: str
) -> None:
    assert method.value == value
    assert OutlierStatus.SUCCESS.value == "success"
    result = detect_outliers(table([1, 2, 3]), column="value", method=method)
    assert result.method is method
    assert result.column == "value"
    assert result.valid_count == 3
    assert result.skipped_count == 0
    assert isinstance(result.outlier_count, int)
    assert result.status is OutlierStatus.SUCCESS
    with pytest.raises(FrozenInstanceError):
        result.outlier_count = 2


def test_operation_metadata_and_execution() -> None:
    operation = OutlierDetectionOperation()
    assert operation.metadata.name == "outlier_detection"
    assert operation.metadata.exact is True
    result = operation.execute(table([1, 2, 3]), column="value", method=OutlierMethod.IQR)
    assert result.status is OutlierStatus.SUCCESS


def test_iqr_known_bounds_and_upper_outlier() -> None:
    result = detect_outliers(
        table([1, 2, 3, 4, 5, 100]), column="value", method=OutlierMethod.IQR
    )
    assert result.status is OutlierStatus.SUCCESS
    assert result.lower_bound == pytest.approx(-1.5)
    assert result.upper_bound == pytest.approx(8.5)
    assert result.outlier_count == 1


def test_iqr_lower_upper_and_fence_values() -> None:
    result = detect_outliers(
        table([-91, -37, 2, 14, 23, 25, 28, 67, 91]),
        column="value",
        method=OutlierMethod.IQR,
    )
    assert result.lower_bound == -37.0
    assert result.upper_bound == 67.0
    assert result.outlier_count == 2


def test_z_score_known_values_and_strict_boundary() -> None:
    result = detect_outliers(
        table([-1, 0, 1, 10]), column="value", method=OutlierMethod.Z_SCORE, threshold=1
    )
    assert result.status is OutlierStatus.SUCCESS
    assert result.lower_bound == pytest.approx(-1.8874821936960613)
    assert result.upper_bound == pytest.approx(6.887482193696061)
    assert result.outlier_count == 1
    boundary = detect_outliers(
        table([-1, 1]), column="value", method=OutlierMethod.Z_SCORE, threshold=1
    )
    assert boundary.lower_bound == -1.0
    assert boundary.upper_bound == 1.0
    assert boundary.outlier_count == 0


def test_z_score_large_offset_stability() -> None:
    result = detect_outliers(
        table([1_000_000_000_001, 1_000_000_000_002, 1_000_000_000_003]),
        column="value",
        method=OutlierMethod.Z_SCORE,
        threshold=2,
    )
    assert result.status is OutlierStatus.SUCCESS
    assert result.outlier_count == 0
    assert result.lower_bound is not None and math.isfinite(result.lower_bound)
    assert result.upper_bound is not None and math.isfinite(result.upper_bound)


def test_z_score_counts_both_tails() -> None:
    result = detect_outliers(
        table([-10, -1, 0, 1, 10]),
        column="value",
        method=OutlierMethod.Z_SCORE,
        threshold=1,
    )
    assert result.outlier_count == 2


def test_modified_z_score_known_values_and_boundary() -> None:
    scale = 0.6744897501960817
    result = detect_outliers(
        table([-1, 0, 1, 10]),
        column="value",
        method=OutlierMethod.MODIFIED_Z_SCORE,
        threshold=3.5,
    )
    assert result.status is OutlierStatus.SUCCESS
    assert result.lower_bound == pytest.approx(-4.689107764769607)
    assert result.upper_bound == pytest.approx(5.689107764769607)
    assert result.outlier_count == 1
    boundary = detect_outliers(
        table([-1, 0, 1]),
        column="value",
        method=OutlierMethod.MODIFIED_Z_SCORE,
        threshold=scale,
    )
    assert boundary.lower_bound == -1.0
    assert boundary.upper_bound == 1.0
    assert boundary.outlier_count == 0


def test_modified_z_score_counts_both_tails() -> None:
    result = detect_outliers(
        table([-100, -1, 0, 1, 100]),
        column="value",
        method=OutlierMethod.MODIFIED_Z_SCORE,
    )
    assert result.outlier_count == 2


@pytest.mark.parametrize("method", list(OutlierMethod))
def test_insufficient_missing_and_constant_data(method: OutlierMethod) -> None:
    insufficient = detect_outliers(table([None, 1]), column="value", method=method)
    assert insufficient.status is OutlierStatus.INSUFFICIENT_DATA
    assert insufficient.valid_count == 1
    assert insufficient.skipped_count == 1
    empty = detect_outliers(table([]), column="value", method=method)
    assert empty.status is OutlierStatus.INSUFFICIENT_DATA
    all_missing = detect_outliers(table([None, None]), column="value", method=method)
    assert all_missing.status is OutlierStatus.INSUFFICIENT_DATA
    assert all_missing.skipped_count == 2
    constant = detect_outliers(table([4, 4, 4]), column="value", method=method)
    assert constant.status is OutlierStatus.CONSTANT_COLUMN
    assert constant.outlier_count == 0


def test_modified_z_score_zero_mad_is_numerical_degeneracy() -> None:
    result = detect_outliers(
        table([0, 0, 0, 1]), column="value", method=OutlierMethod.MODIFIED_Z_SCORE
    )
    assert result.status is OutlierStatus.NUMERICAL_DEGENERACY
    assert result.lower_bound is None
    assert result.upper_bound is None


@pytest.mark.parametrize("threshold", [0, -1, True, math.inf, math.nan, "3"])
def test_invalid_thresholds_are_rejected(threshold: object) -> None:
    with pytest.raises(InvalidAnalysisInputError):
        detect_outliers(
            table([1, 2, 3]),
            column="value",
            method=OutlierMethod.Z_SCORE,
            threshold=threshold,
        )


def test_invalid_columns_methods_and_schemas_are_rejected() -> None:
    with pytest.raises(InvalidAnalysisInputError):
        detect_outliers(table([1, 2]), column="missing", method=OutlierMethod.IQR)
    with pytest.raises(InvalidAnalysisInputError):
        detect_outliers(table([1, 2]), column="value", method="iqr")
    for schema, value in [
        (ColumnSchema("value", "boolean"), True),
        (ColumnSchema("value", "string"), "1"),
    ]:
        source = from_rows((schema,), lambda value=value: ({"value": value},))
        with pytest.raises(InvalidAnalysisInputError):
            detect_outliers(source, column="value", method=OutlierMethod.IQR)


def test_nonfinite_and_invalid_row_values_are_rejected() -> None:
    source = from_rows(
        (ColumnSchema("value", "number"),), lambda: ({"value": math.inf},)
    )
    with pytest.raises(InvalidAnalysisInputError):
        detect_outliers(source, column="value", method=OutlierMethod.IQR)
    malformed = from_rows(
        (ColumnSchema("value", "number"),),
        lambda: ({"other": 1},),
    )
    with pytest.raises(InvalidAnalysisInputError):
        detect_outliers(malformed, column="value", method=OutlierMethod.IQR)


def test_limits_are_exact_and_missing_values_do_not_consume_materialization() -> None:
    source = table([None, 1, 2])
    result = detect_outliers(
        source,
        column="value",
        method=OutlierMethod.IQR,
        limits=AnalysisLimits(max_materialized_values=2),
    )
    assert result.valid_count == 2
    with pytest.raises(AnalysisLimitError):
        detect_outliers(
            table([1, 2, 3]),
            column="value",
            method=OutlierMethod.IQR,
            limits=AnalysisLimits(max_materialized_values=2),
        )
    with pytest.raises(AnalysisLimitError):
        detect_outliers(
            table([None, 1, 2]),
            column="value",
            method=OutlierMethod.IQR,
            limits=AnalysisLimits(max_rows=2),
        )
    exact = detect_outliers(
        table([1, 2]),
        column="value",
        method=OutlierMethod.IQR,
        limits=AnalysisLimits(max_rows=2),
    )
    assert exact.status is OutlierStatus.SUCCESS


def test_invalid_analysis_limits_are_rejected() -> None:
    with pytest.raises(InvalidAnalysisInputError):
        detect_outliers(
            table([1, 2]),
            column="value",
            method=OutlierMethod.IQR,
            limits=AnalysisLimits(max_rows=0),
        )


def test_repeated_execution_is_deterministic() -> None:
    source = table([1, 2, 3, 4, 100])
    first = detect_outliers(source, column="value", method=OutlierMethod.IQR)
    assert first == detect_outliers(source, column="value", method=OutlierMethod.IQR)


@pytest.mark.parametrize(
    ("suffix", "format_name", "payload"),
    [
        (".csv", "csv", "value\n1\n2\n3\n100\n"),
        (".jsonl", "jsonl", '{"value":1}\n{"value":2}\n{"value":3}\n{"value":100}\n'),
    ],
)
def test_csv_and_jsonl_source_integration(
    tmp_path: Path, suffix: str, format_name: str, payload: str
) -> None:
    path = tmp_path / f"values{suffix}"
    path.write_text(payload, encoding="utf-8")
    result = detect_outliers(
        from_source(DatasetSource(path, format_name)),
        column="value",
        method=OutlierMethod.IQR,
    )
    assert result.outlier_count == 1


def test_sqlite_source_is_read_only_and_no_output_is_written(tmp_path: Path) -> None:
    path = tmp_path / "values.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("create table records (value integer)")
        connection.executemany("insert into records values (?)", [(1,), (2,), (3,), (100,)])
    before = path.read_bytes()
    result = detect_outliers(
        from_source(DatasetSource(path, "sqlite", "records")),
        column="value",
        method=OutlierMethod.IQR,
    )
    assert result.outlier_count == 1
    assert path.read_bytes() == before
    assert sorted(item.name for item in tmp_path.iterdir()) == ["values.sqlite"]


def test_numeric_looking_json_strings_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "values.jsonl"
    path.write_text('{"value":"1"}\n{"value":"2"}\n', encoding="utf-8")
    with pytest.raises(InvalidAnalysisInputError):
        detect_outliers(
            from_source(DatasetSource(path, "jsonl")),
            column="value",
            method=OutlierMethod.IQR,
        )
