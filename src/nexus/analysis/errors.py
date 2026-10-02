"""Typed failures for the Phase 4A analysis boundary."""


class AnalysisError(ValueError):
    """Base class for invalid or unsupported analysis requests."""


class InvalidAnalysisInputError(AnalysisError):
    """The table, column, value, or operation parameter is invalid."""


class AnalysisLimitError(AnalysisError):
    """An explicit analysis bound cannot be satisfied exactly."""


class InsufficientDataError(AnalysisError):
    """An operation requires more valid data than the table provides."""
