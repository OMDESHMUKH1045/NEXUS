"""Application lifecycle and graceful shutdown contracts."""

from contextlib import AbstractContextManager
import logging
import signal
from threading import Event
from types import FrameType

LOGGER = logging.getLogger("nexus.lifecycle")


class Supervisor(AbstractContextManager["Supervisor"]):
    """Owns the stop signal and restores signal handlers on exit."""

    def __init__(self) -> None:
        self.stop_event = Event()
        self._previous: dict[int, signal.Handlers] = {}

    def request_stop(self, signum: int | None = None) -> None:
        LOGGER.info("shutdown requested", extra={"component": "supervisor", "signal": signum})
        self.stop_event.set()

    def _handle_signal(self, signum: int, _frame: FrameType | None) -> None:
        self.request_stop(signum)

    def __enter__(self) -> "Supervisor":
        for signum in (signal.SIGINT, signal.SIGTERM):
            self._previous[signum] = signal.getsignal(signum)
            signal.signal(signum, self._handle_signal)
        return self

    def __exit__(self, *_exc_info: object) -> None:
        for signum, previous in self._previous.items():
            signal.signal(signum, previous)
        self._previous.clear()

