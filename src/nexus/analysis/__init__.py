"""Foundational CPU analysis contracts and operations."""

from .adapters import from_rows, from_source
from .aggregation import (
    AggregateGroup,
    AggregationResult,
    AggregationStatus,
    GroupedAggregationOperation,
    grouped_aggregation,
)
from .contracts import (
    AnalysisLimits,
    AnalysisOperation,
    AnalysisTable,
    ColumnSchema,
    OperationMetadata,
)
from .correlations import (
    CorrelationMethod,
    CorrelationResult,
    CorrelationStatus,
    PearsonCorrelationOperation,
    SpearmanCorrelationOperation,
    pearson_correlation,
    spearman_correlation,
)
from .errors import AnalysisError, AnalysisLimitError, InsufficientDataError, InvalidAnalysisInputError
from .operations import (
    DescriptiveStatistics,
    DescriptiveStatisticsOperation,
    ExactQuantileOperation,
    descriptive_statistics,
    exact_quantile,
)
from .outliers import (
    OutlierDetectionOperation,
    OutlierMethod,
    OutlierResult,
    OutlierStatus,
    detect_outliers,
)

__all__ = [
    "AnalysisError",
    "AnalysisLimitError",
    "AnalysisLimits",
    "AnalysisOperation",
    "AnalysisTable",
    "ColumnSchema",
    "AggregateGroup",
    "AggregationResult",
    "AggregationStatus",
    "CorrelationMethod",
    "CorrelationResult",
    "CorrelationStatus",
    "DescriptiveStatistics",
    "DescriptiveStatisticsOperation",
    "ExactQuantileOperation",
    "GroupedAggregationOperation",
    "InsufficientDataError",
    "InvalidAnalysisInputError",
    "OperationMetadata",
    "OutlierDetectionOperation",
    "OutlierMethod",
    "OutlierResult",
    "OutlierStatus",
    "PearsonCorrelationOperation",
    "SpearmanCorrelationOperation",
    "descriptive_statistics",
    "exact_quantile",
    "from_rows",
    "from_source",
    "pearson_correlation",
    "spearman_correlation",
    "detect_outliers",
    "grouped_aggregation",
]
