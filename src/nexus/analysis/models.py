"""Compatibility module for the immutable Phase 4A contracts."""

from .contracts import AnalysisLimits, AnalysisOperation, AnalysisTable, ColumnSchema, OperationMetadata
from .errors import AnalysisError, AnalysisLimitError, InsufficientDataError, InvalidAnalysisInputError
from .operations import DescriptiveStatistics

__all__ = [
    "AnalysisError",
    "AnalysisLimitError",
    "AnalysisLimits",
    "AnalysisOperation",
    "AnalysisTable",
    "ColumnSchema",
    "DescriptiveStatistics",
    "InsufficientDataError",
    "InvalidAnalysisInputError",
    "OperationMetadata",
]
