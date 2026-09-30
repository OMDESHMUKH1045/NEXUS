"""Bounded repeated telemetry sampling."""

from collections import deque
from dataclasses import dataclass
import logging
from threading import Event, Lock, Thread
import time
from typing import Callable

from .collectors import CpuCollector, collect_sample
from .models import TelemetrySample

LOGGER = logging.getLogger("nexus.observatory")


@dataclass(frozen=True, slots=True)
class SamplerStats:
    samples_collected: int
    collection_errors: int
    overruns: int
    evicted_samples: int


class Sampler:
    def __init__(
        self,
        interval_seconds: float = 1.0,
        history_capacity: int = 300,
        process_limit: int | None = None,
        collector: Callable[[], TelemetrySample] | None = None,
    ) -> None:
        if not 0.25 <= interval_seconds <= 5.0:
            raise ValueError("interval_seconds must be between 0.25 and 5.0")
        if not 1 <= history_capacity <= 100_000:
            raise ValueError("history_capacity must be between 1 and 100000")
        if process_limit is not None and process_limit < 1:
            raise ValueError("process_limit must be at least 1")
        self.interval_seconds = interval_seconds
        self._history: deque[TelemetrySample] = deque(maxlen=history_capacity)
        self._process_limit = process_limit
        self._collector = collector or self._default_collector()
        self._stop = Event()
        self._thread: Thread | None = None
        self._lock = Lock()
        self._samples = self._errors = self._overruns = self._evictions = 0

    def _default_collector(self) -> Callable[[], TelemetrySample]:
        cpu = CpuCollector()
        return lambda: collect_sample(cpu, self._process_limit)

    @property
    def history(self) -> tuple[TelemetrySample, ...]:
        with self._lock:
            return tuple(self._history)

    @property
    def capacity(self) -> int:
        return self._history.maxlen or 0

    @property
    def stats(self) -> SamplerStats:
        with self._lock:
            return SamplerStats(self._samples, self._errors, self._overruns, self._evictions)

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name="nexus-telemetry", daemon=True)
        self._thread.start()
        LOGGER.info("telemetry sampler started", extra={"component": "observatory"})

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
            if thread.is_alive():
                raise TimeoutError("telemetry sampler did not stop before timeout")
        self._thread = None
        LOGGER.info("telemetry sampler stopped", extra={"component": "observatory"})

    def collect_once(self) -> TelemetrySample | None:
        try:
            sample = self._collector()
        except (OSError, ValueError):
            with self._lock:
                self._errors += 1
            LOGGER.exception("telemetry collection failed", extra={"component": "observatory"})
            return None
        with self._lock:
            if len(self._history) == self.capacity:
                self._evictions += 1
            self._history.append(sample)
            self._samples += 1
        return sample

    def _run(self) -> None:
        deadline = time.monotonic()
        while not self._stop.is_set():
            self.collect_once()
            deadline += self.interval_seconds
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                with self._lock:
                    self._overruns += 1
                deadline = time.monotonic()
                continue
            self._stop.wait(remaining)
