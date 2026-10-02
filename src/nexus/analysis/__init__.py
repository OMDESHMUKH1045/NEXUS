"""Foundational CPU analysis contracts and operations."""

from .adapters import from_rows, from_source
from .contracts import (
    AnalysisLimits,
    AnalysisOperation,
    AnalysisTable,
    ColumnSchema,
    OperationMetadata,
)
from .errors import AnalysisError, AnalysisLimitError, InsufficientDataError, InvalidAnalysisInputError
from .operations import (
    DescriptiveStatistics,
    DescriptiveStatisticsOperation,
    ExactQuantileOperation,
    descriptive_statistics,
    exact_quantile,
)

__all__ = [
    "AnalysisError",
    "AnalysisLimitError",
    "AnalysisLimits",
    "AnalysisOperation",
    "AnalysisTable",
    "ColumnSchema",
    "DescriptiveStatistics",
    "DescriptiveStatisticsOperation",
    "ExactQuantileOperation",
    "InsufficientDataError",
    "InvalidAnalysisInputError",
    "OperationMetadata",
    "descriptive_statistics",
    "exact_quantile",
    "from_rows",
    "from_source",
]
