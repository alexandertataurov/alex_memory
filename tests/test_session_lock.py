from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alex_memory.session_lock import SessionLock


class SessionLockTests(unittest.TestCase):
    def test_second_owner_is_rejected_until_first_releases(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "session.lock"
            first, second = SessionLock(path), SessionLock(path)
            first.acquire()
            with self.assertRaises(RuntimeError):
                second.acquire()
            first.release()
            second.acquire()
            second.release()
