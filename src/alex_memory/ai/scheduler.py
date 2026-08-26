"""Durable-work scheduler for automatic background intelligence."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from collections.abc import Awaitable, Callable

from ..config import Settings
from .repository import ensure_daily_jobs


class BackgroundIntelligenceScheduler:
    """Coalesce committed-evidence wakeups around one live-first worker.

    SQLite evidence and ``ai_jobs`` are the durable source of truth.  The event
    only reduces latency after a commit; startup and the maximum-delay timeout
    both recheck that durable state, so an in-memory wakeup can never be the
    only record of work.
    """

    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings,
        *,
        run_daily: Callable[[], Awaitable[None]],
        run_history: Callable[[Callable[[], bool]], Awaitable[None]],
        writer_busy: Callable[[], bool],
        on_error: Callable[[str, Exception], None] | None = None,
        coalesce_seconds: float = 2.0,
        maximum_delay_seconds: float | None = None,
        history_interval_seconds: float | None = None,
    ):
        self.conn = conn
        self.settings = settings
        self.run_daily = run_daily
        self.run_history = run_history
        self.writer_busy = writer_busy
        self.on_error = on_error
        self.coalesce_seconds = coalesce_seconds
        self.maximum_delay_seconds = (
            maximum_delay_seconds
            if maximum_delay_seconds is not None
            else settings.ai_auto_analyze_interval_minutes * 60
        )
        self.history_interval_seconds = (
            history_interval_seconds
            if history_interval_seconds is not None
            else settings.history_auto_analyze_interval_minutes * 60
        )
        self._next_history_at = 0.0
        self._stop_event = asyncio.Event()
        self._wake_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Start one owner and immediately recheck durable pending work."""
        if self._task is not None:
            return
        self._wake_event.set()
        self._task = asyncio.create_task(self._run())

    def notify_committed_messages(self, message_count: int) -> None:
        """Wake after useful evidence is committed, never before durability."""
        if message_count > 0:
            self._wake_event.set()

    async def close(self) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            woke = await self._wait_for_wake()
            if self._stop_event.is_set():
                return
            if woke:
                await self._coalesce_wakeups()
            await self._run_available_work()

    async def _wait_for_wake(self) -> bool:
        try:
            await asyncio.wait_for(
                self._wake_event.wait(), timeout=self.maximum_delay_seconds
            )
            self._wake_event.clear()
            return True
        except asyncio.TimeoutError:
            return False

    async def _coalesce_wakeups(self) -> None:
        if self.coalesce_seconds <= 0:
            return
        try:
            await asyncio.wait_for(
                self._stop_event.wait(), timeout=self.coalesce_seconds
            )
        except asyncio.TimeoutError:
            self._wake_event.clear()

    async def _run_available_work(self) -> None:
        if self.settings.ai_auto_analyze_new_messages:
            try:
                await self.run_daily()
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self._report_error("daily analysis", error)
                return

        if (
            not self.settings.history_auto_analyze
            or time.monotonic() < self._next_history_at
            or not self._history_can_continue()
        ):
            return
        self._next_history_at = time.monotonic() + self.history_interval_seconds
        try:
            await self.run_history(self._history_can_continue)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self._report_error("history analysis", error)

    def _history_can_continue(self) -> bool:
        """Yield history before a provider call whenever live work is durable."""
        if self._stop_event.is_set() or self.writer_busy():
            return False
        if not self.settings.ai_auto_analyze_new_messages:
            return True
        ensure_daily_jobs(self.conn, self.settings)
        return not bool(
            self.conn.execute(
                """
                SELECT 1 FROM ai_jobs
                WHERE lane = 'daily' AND status IN ('pending', 'running', 'failed')
                LIMIT 1
                """
            ).fetchone()
        )

    def _report_error(self, lane: str, error: Exception) -> None:
        if self.on_error is not None:
            self.on_error(lane, error)
