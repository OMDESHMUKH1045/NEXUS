"""Typed application configuration with conservative resource defaults."""

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True, slots=True)
class NexusConfig:
    data_dir: Path = Path("~/.local/share/nexus").expanduser()
    log_level: str = "INFO"
    worker_limit: int = 1
    queue_limit: int = 32
    shutdown_timeout_seconds: float = 10.0
    telemetry_interval_seconds: float = 1.0
    telemetry_history_capacity: int = 300
    telemetry_process_limit: int = 32
    fingerprint_chunk_size: int = 1024 * 1024
    profile_inference_rows: int = 100
    profile_sample_values: int = 5
    profile_distinct_values: int = 32

    def __post_init__(self) -> None:
        if self.worker_limit < 1:
            raise ValueError("worker_limit must be at least 1")
        if self.queue_limit < 1:
            raise ValueError("queue_limit must be at least 1")
        if self.shutdown_timeout_seconds <= 0:
            raise ValueError("shutdown_timeout_seconds must be positive")
        if self.telemetry_interval_seconds <= 0:
            raise ValueError("telemetry_interval_seconds must be positive")
        if not 0.25 <= self.telemetry_interval_seconds <= 5.0:
            raise ValueError("telemetry_interval_seconds must be between 0.25 and 5.0")
        if not 1 <= self.telemetry_history_capacity <= 100_000:
            raise ValueError("telemetry_history_capacity must be between 1 and 100000")
        if not 1 <= self.telemetry_process_limit <= 1000:
            raise ValueError("telemetry_process_limit must be between 1 and 1000")
        if not 1 <= self.fingerprint_chunk_size <= 16 * 1024 * 1024:
            raise ValueError("fingerprint_chunk_size is out of bounds")
        if not 1 <= self.profile_inference_rows <= 100_000:
            raise ValueError("profile_inference_rows is out of bounds")
        if not 0 <= self.profile_sample_values <= 1000:
            raise ValueError("profile_sample_values is out of bounds")
        if not 1 <= self.profile_distinct_values <= 100_000:
            raise ValueError("profile_distinct_values is out of bounds")

    @classmethod
    def from_environment(cls) -> "NexusConfig":
        """Load supported overrides, failing explicitly for invalid values."""
        values: dict[str, object] = {}
        if value := os.getenv("NEXUS_DATA_DIR"):
            values["data_dir"] = Path(value).expanduser()
        if value := os.getenv("NEXUS_LOG_LEVEL"):
            values["log_level"] = value.upper()
        for name, field, converter in (
            ("NEXUS_WORKER_LIMIT", "worker_limit", int),
            ("NEXUS_QUEUE_LIMIT", "queue_limit", int),
            ("NEXUS_SHUTDOWN_TIMEOUT", "shutdown_timeout_seconds", float),
            ("NEXUS_TELEMETRY_INTERVAL", "telemetry_interval_seconds", float),
            ("NEXUS_TELEMETRY_HISTORY", "telemetry_history_capacity", int),
            ("NEXUS_TELEMETRY_PROCESS_LIMIT", "telemetry_process_limit", int),
            ("NEXUS_FINGERPRINT_CHUNK_SIZE", "fingerprint_chunk_size", int),
            ("NEXUS_PROFILE_INFERENCE_ROWS", "profile_inference_rows", int),
            ("NEXUS_PROFILE_SAMPLE_VALUES", "profile_sample_values", int),
            ("NEXUS_PROFILE_DISTINCT_VALUES", "profile_distinct_values", int),
        ):
            if value := os.getenv(name):
                try:
                    values[field] = converter(value)
                except ValueError as exc:
                    raise ValueError(f"{name} must be a valid {converter.__name__}") from exc
        return cls(**values)
