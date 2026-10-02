import math
import sqlite3
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from nexus.analysis import (
    AggregateGroup,
    AggregationStatus,
    AnalysisLimitError,
    AnalysisLimits,
    ColumnSchema,
    GroupedAggregationOperation,
    InvalidAnalysisInputError,
    grouped_aggregation,
    from_rows,
    from_source,
)
from nexus.datasets.models import DatasetSource


def table(rows: list[dict[str, object]]):
    return from_rows(
        (
            ColumnSchema("group", "string"),
            ColumnSchema("value", "number"),
        ),
        lambda: (row for row in rows),
    )


def test_contract_metadata_exports_and_immutability() -> None:
    result = grouped_aggregation(
        table([{"group": "a", "value": 1}]),
        group_column="group",
        measure_column="value",
    )
    assert result.status is AggregationStatus.SUCCESS
    assert result.groups[0] == AggregateGroup("a", 1, 1, 0, 1.0, 1.0, 1.0, 1.0)
    with pytest.raises(FrozenInstanceError):
        result.groups = ()
    operation = GroupedAggregationOperation()
    assert operation.metadata.name == "grouped_aggregation"
    assert operation.metadata.exact is True
    assert operation.execute(
        table([{"group": "a", "value": 1}]),
        group_column="group",
        measure_column="value",
    ) == result


def test_multiple_groups_missing_values_and_deterministic_order() -> None:
    rows = [
        {"group": "b", "value": -2},
        {"group": "a", "value": 1.5},
        {"group": "b", "value": None},
        {"group": "a", "value": 2.5},
        {"group": "c", "value": None},
        {"group": "a", "value": -1},
    ]
    result = grouped_aggregation(table(rows), group_column="group", measure_column="value")
    assert [group.key for group in result.groups] == ["a", "b", "c"]
    assert result.groups[0] == AggregateGroup("a", 3, 3, 0, 3.0, 1.0, -1.0, 2.5)
    assert result.groups[1] == AggregateGroup("b", 2, 1, 1, -2.0, -2.0, -2.0, -2.0)
    assert result.groups[2] == AggregateGroup("c", 1, 0, 1, None, None, None, None)
    assert result == grouped_aggregation(
        table(list(reversed(rows))), group_column="group", measure_column="value"
    )


def test_missing_group_key_and_empty_input() -> None:
    source = from_rows(
        (ColumnSchema("group", "string"), ColumnSchema("value", "number")),
        lambda: ({"group": None, "value": 2}, {"group": "a", "value": 3}),
    )
    result = grouped_aggregation(source, group_column="group", measure_column="value")
    assert [group.key for group in result.groups] == [None, "a"]
    empty = grouped_aggregation(
        table([]), group_column="group", measure_column="value"
    )
    assert empty.status is AggregationStatus.INSUFFICIENT_DATA
    assert empty.groups == ()


def test_type_aware_group_ordering() -> None:
    source = from_rows(
        (ColumnSchema("group", "boolean"), ColumnSchema("value", "number")),
        lambda: (
            {"group": True, "value": 1},
            {"group": False, "value": 2},
            {"group": None, "value": 3},
        ),
    )
    result = grouped_aggregation(source, group_column="group", measure_column="value")
    assert [group.key for group in result.groups] == [None, False, True]


def test_compensated_sum_and_large_offsets() -> None:
    result = grouped_aggregation(
        table(
            [
                {"group": "a", "value": 1e16},
                {"group": "a", "value": 1},
                {"group": "a", "value": -1e16},
                {"group": "a", "value": 3},
            ]
        ),
        group_column="group",
        measure_column="value",
    )
    group = result.groups[0]
    assert group.total == pytest.approx(4.0)
    assert group.mean == pytest.approx(1.0)
    assert math.isfinite(group.total)
    assert math.isfinite(group.mean)


@pytest.mark.parametrize("schema", ["boolean", "string"])
def test_invalid_measure_schema(schema: str) -> None:
    source = from_rows(
        (ColumnSchema("group", "string"), ColumnSchema("value", schema)),
        lambda: ({"group": "a", "value": True if schema == "boolean" else "1"},),
    )
    with pytest.raises(InvalidAnalysisInputError):
        grouped_aggregation(source, group_column="group", measure_column="value")


def test_invalid_columns_rows_values_and_parameters() -> None:
    source = table([{"group": "a", "value": 1}])
    for group_column, measure_column in [
        ("missing", "value"),
        ("group", "missing"),
        ("group", "group"),
    ]:
        with pytest.raises(InvalidAnalysisInputError):
            grouped_aggregation(
                source, group_column=group_column, measure_column=measure_column
            )
    for max_groups in [0, -1, True, 1.5]:
        with pytest.raises(InvalidAnalysisInputError):
            grouped_aggregation(
                source,
                group_column="group",
                measure_column="value",
                max_groups=max_groups,
            )
    malformed = from_rows(
        (ColumnSchema("group", "string"), ColumnSchema("value", "number")),
        lambda: ({"other": "a", "value": 1},),
    )
    with pytest.raises(InvalidAnalysisInputError):
        grouped_aggregation(malformed, group_column="group", measure_column="value")
    nonfinite = from_rows(
        (ColumnSchema("group", "string"), ColumnSchema("value", "number")),
        lambda: ({"group": "a", "value": math.inf},),
    )
    with pytest.raises(InvalidAnalysisInputError):
        grouped_aggregation(nonfinite, group_column="group", measure_column="value")


def test_limits_are_exact_and_materialization_limit_is_not_repurposed() -> None:
    source = table(
        [
            {"group": "a", "value": 1},
            {"group": "a", "value": 2},
            {"group": "b", "value": 3},
        ]
    )
    assert grouped_aggregation(
        source,
        group_column="group",
        measure_column="value",
        limits=AnalysisLimits(max_rows=3, max_materialized_values=1),
        max_groups=2,
    ).status is AggregationStatus.SUCCESS
    with pytest.raises(AnalysisLimitError):
        grouped_aggregation(
            source,
            group_column="group",
            measure_column="value",
            limits=AnalysisLimits(max_rows=2),
        )
    with pytest.raises(AnalysisLimitError):
        grouped_aggregation(
            source,
            group_column="group",
            measure_column="value",
            max_groups=1,
        )
    existing = table(
        [{"group": "a", "value": 1}, {"group": "a", "value": 2}]
    )
    assert len(
        grouped_aggregation(
            existing,
            group_column="group",
            measure_column="value",
            max_groups=1,
        ).groups
    ) == 1


@pytest.mark.parametrize(
    ("suffix", "format_name", "payload"),
    [
        (".csv", "csv", "group,value\na,1\na,2\nb,3\n"),
        (".jsonl", "jsonl", '{"group":"a","value":1}\n{"group":"b","value":2}\n'),
    ],
)
def test_csv_and_jsonl_integration(
    tmp_path: Path, suffix: str, format_name: str, payload: str
) -> None:
    path = tmp_path / f"values{suffix}"
    path.write_text(payload, encoding="utf-8")
    result = grouped_aggregation(
        from_source(DatasetSource(path, format_name)),
        group_column="group",
        measure_column="value",
    )
    assert result.status is AggregationStatus.SUCCESS
    assert result.groups[0].total == (3.0 if format_name == "csv" else 1.0)


def test_numeric_looking_json_measure_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "values.jsonl"
    path.write_text('{"group":"a","value":"1"}\n', encoding="utf-8")
    with pytest.raises(InvalidAnalysisInputError):
        grouped_aggregation(
            from_source(DatasetSource(path, "jsonl")),
            group_column="group",
            measure_column="value",
        )


def test_sqlite_is_read_only_and_no_output_file_is_created(tmp_path: Path) -> None:
    path = tmp_path / "values.sqlite"
    with sqlite3.connect(path) as connection:
        connection.execute("create table records (group_name text, value integer)")
        connection.executemany(
            "insert into records values (?, ?)", [("a", 1), ("b", 2)]
        )
    before = path.read_bytes()
    result = grouped_aggregation(
        from_source(DatasetSource(path, "sqlite", "records")),
        group_column="group_name",
        measure_column="value",
    )
    assert result.groups[1].total == 2.0
    assert path.read_bytes() == before
    assert sorted(item.name for item in tmp_path.iterdir()) == ["values.sqlite"]
