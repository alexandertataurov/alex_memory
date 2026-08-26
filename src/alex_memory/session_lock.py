"""Process-level guard: a Telegram session must have one local owner."""

from __future__ import annotations

import fcntl
from pathlib import Path
from typing import TextIO


class SessionLock:
    def __init__(self, path: Path):
        self.path = path
        self._handle: TextIO | None = None

    def acquire(self) -> None:
        self._handle = self.path.open("a+")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self._handle.close()
            self._handle = None
            raise RuntimeError(
                "Another Alex Memory process is already using this Telegram session. "
                "Stop it before starting a second instance."
            ) from error

    def release(self) -> None:
        if self._handle is not None:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
            self._handle.close()
            self._handle = None
