"""Streaming source fingerprints."""

from hashlib import sha256
from pathlib import Path

from .models import DatasetFingerprint


def fingerprint(path: Path, chunk_size: int = 1024 * 1024) -> DatasetFingerprint:
    if chunk_size < 1 or chunk_size > 16 * 1024 * 1024:
        raise ValueError("fingerprint chunk_size must be between 1 and 16777216")
    stat = path.stat()
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return DatasetFingerprint("sha256", digest.hexdigest(), stat.st_size, stat.st_mtime_ns)
