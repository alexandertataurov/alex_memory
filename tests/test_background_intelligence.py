from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from alex_memory.ai.repository import ensure_daily_jobs
from alex_memory.ai.scheduler import BackgroundIntelligenceScheduler
from alex_memory.database import connect

from test_ai_pipeline import make_settings


async def _until(predicate, timeout: float = 1.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.001)


class BackgroundIntelligenceSchedulerTests(unittest.IsolatedAsyncioTestCase):
    async def test_startup_rechecks_durable_messages_without_an_in_memory_wakeup(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            self.addAsyncCleanup(_close, conn)
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Ilya','user')"
            )
            conn.execute(
                "INSERT INTO messages(chat_id,message_id,date,text) "
                "VALUES (1,1,'2026-08-24','Please send the invoice.')"
            )
            conn.commit()
            calls = 0

            async def run_daily() -> None:
                nonlocal calls
                calls += 1
                ensure_daily_jobs(conn, settings)

            scheduler = BackgroundIntelligenceScheduler(
                conn,
                settings,
                run_daily=run_daily,
                run_history=_unused_history,
                writer_busy=lambda: False,
                coalesce_seconds=0,
                maximum_delay_seconds=60,
            )
            scheduler.start()
            self.addAsyncCleanup(scheduler.close)

            await _until(lambda: calls == 1)
            self.assertEqual(
                1,
                conn.execute(
                    "SELECT COUNT(*) FROM ai_jobs WHERE lane = 'daily' AND status = 'pending'"
                ).fetchone()[0],
            )

    async def test_burst_wakeups_coalesce_into_one_daily_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            self.addAsyncCleanup(_close, conn)
            calls = 0

            async def run_daily() -> None:
                nonlocal calls
                calls += 1

            scheduler = BackgroundIntelligenceScheduler(
                conn,
                settings,
                run_daily=run_daily,
                run_history=_unused_history,
                writer_busy=lambda: False,
                coalesce_seconds=0.02,
                maximum_delay_seconds=60,
            )
            for _ in range(5):
                scheduler.notify_committed_messages(1)
            scheduler.start()
            self.addAsyncCleanup(scheduler.close)

            await _until(lambda: calls == 1)
            await asyncio.sleep(0.03)
            self.assertEqual(1, calls)

    async def test_busy_history_wakes_again_instead_of_losing_the_trigger(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(
                Path(directory),
                ai_auto_analyze_new_messages=False,
                history_auto_analyze=True,
            )
            conn = connect(settings)
            self.addAsyncCleanup(_close, conn)
            busy = True
            history_calls = 0

            async def run_history(_should_continue) -> None:
                nonlocal history_calls
                history_calls += 1

            scheduler = BackgroundIntelligenceScheduler(
                conn,
                settings,
                run_daily=_unused_daily,
                run_history=run_history,
                writer_busy=lambda: busy,
                coalesce_seconds=0,
                maximum_delay_seconds=60,
            )
            scheduler.start()
            self.addAsyncCleanup(scheduler.close)
            await asyncio.sleep(0.02)
            self.assertEqual(0, history_calls)

            busy = False
            scheduler.notify_committed_messages(1)
            await _until(lambda: history_calls == 1)

    async def test_live_pending_jobs_block_history_until_they_are_cleared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory), history_auto_analyze=True)
            conn = connect(settings)
            self.addAsyncCleanup(_close, conn)
            conn.execute(
                """INSERT INTO ai_jobs(
                    lane, chat_id, first_message_id, last_message_id, message_count,
                    analysis_version, selection_fingerprint, status, created_at
                ) VALUES ('daily', 1, 1, 1, 1, 2, 'fixture-live', 'pending', '2026-08-24')"""
            )
            conn.commit()
            history_calls = 0

            async def run_history(_should_continue) -> None:
                nonlocal history_calls
                history_calls += 1

            scheduler = BackgroundIntelligenceScheduler(
                conn,
                settings,
                run_daily=_unused_daily,
                run_history=run_history,
                writer_busy=lambda: False,
                coalesce_seconds=0,
                maximum_delay_seconds=60,
            )
            scheduler.start()
            self.addAsyncCleanup(scheduler.close)
            await asyncio.sleep(0.02)
            self.assertEqual(0, history_calls)

            conn.execute("UPDATE ai_jobs SET status = 'done' WHERE lane = 'daily'")
            conn.commit()
            scheduler.notify_committed_messages(1)
            await _until(lambda: history_calls == 1)

    async def test_provider_failure_is_reported_and_a_later_wakeup_retries(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            self.addAsyncCleanup(_close, conn)
            calls = 0
            errors: list[str] = []

            async def run_daily() -> None:
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise RuntimeError("provider unavailable")

            scheduler = BackgroundIntelligenceScheduler(
                conn,
                settings,
                run_daily=run_daily,
                run_history=_unused_history,
                writer_busy=lambda: False,
                on_error=lambda lane, error: errors.append(f"{lane}: {error}"),
                coalesce_seconds=0,
                maximum_delay_seconds=60,
            )
            scheduler.start()
            self.addAsyncCleanup(scheduler.close)
            await _until(lambda: len(errors) == 1)

            scheduler.notify_committed_messages(1)
            await _until(lambda: calls == 2)
            self.assertEqual(["daily analysis: provider unavailable"], errors)

    async def test_maximum_delay_rechecks_work_when_no_wakeup_arrives(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            self.addAsyncCleanup(_close, conn)
            calls = 0

            async def run_daily() -> None:
                nonlocal calls
                calls += 1

            scheduler = BackgroundIntelligenceScheduler(
                conn,
                settings,
                run_daily=run_daily,
                run_history=_unused_history,
                writer_busy=lambda: False,
                coalesce_seconds=0,
                maximum_delay_seconds=0.02,
            )
            scheduler.start()
            self.addAsyncCleanup(scheduler.close)
            await _until(lambda: calls >= 2)


async def _unused_daily() -> None:
    return None


async def _unused_history(_should_continue) -> None:
    return None


async def _close(conn) -> None:
    conn.close()
