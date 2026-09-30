"""Conservative source resource estimates."""

from .models import ResourceEstimate


def estimate(source, *, working_memory_bytes: int = 64 * 1024) -> ResourceEstimate:
    size = source.path.stat().st_size
    return ResourceEstimate(size, size, working_memory_bytes, 0)
