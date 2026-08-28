from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from test_ai_pipeline import make_settings

from alex_memory.database import connect
from alex_memory.models import LiveSyncState
from alex_memory.runtime_status import RuntimeStatusService
from alex_memory.ui.navigation import show_main_menu
from alex_memory.ui.runtime_status import show_status


class RuntimeStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self.directory.name))
        self.conn = connect(self.settings)
        self.service = RuntimeStatusService(self.conn, self.settings)
        self.now = datetime(2026, 8, 24, 12, tzinfo=UTC)

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def _live(
        self,
        *,
        phase: str = "HEALTHY",
        connected: bool = True,
        retry_scheduled: bool = False,
        writer: asyncio.Future | None = None,
        queue_size: int = 0,
    ) -> SimpleNamespace:
        queue: asyncio.Queue = asyncio.Queue()
        for index in range(queue_size):
            queue.put_nowait(("message", index))
        state = LiveSyncState(
            phase=phase,
            connected=connected,
            retry_scheduled=retry_scheduled,
            last_reconciliation_at="2026-08-24T12:00:00+00:00",
        )
        return SimpleNamespace(state=state, write_queue=queue, writer_task=writer)

    def _message(self, when: datetime) -> None:
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (1,'Direct','user')"
        )
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,date,text)
               VALUES (1,1,?, 'source')""",
            (when.isoformat(),),
        )

    def test_healthy_and_processing_snapshots_expose_live_work(self) -> None:
        writer = asyncio.new_event_loop().create_future()
        self.conn.execute(
            """INSERT INTO ai_jobs(lane,chat_id,first_message_id,last_message_id,message_count,
               analysis_version,selection_fingerprint,status,provider,model,created_at) VALUES
               ('daily',1,1,1,1,2,'fixture-running','running','gemini','flash','2026-08-24T12:00:00+00:00')"""
        )
        status = self.service.snapshot(
            self._live(writer=writer, queue_size=2), now=self.now
        )
        self.assertEqual("HEALTHY", status.phase)
        self.assertEqual("running", status.writer.state)
        self.assertEqual(2, status.telegram.queue_size)
        self.assertEqual(1, status.ai.running_jobs)
        self.assertEqual("gemini / flash", status.ai.current_route)

    def test_behind_startup_failure_retrying_offline_and_fatal_snapshots(self) -> None:
        writer = asyncio.new_event_loop().create_future()
        self._message(self.now - timedelta(hours=2))
        self.assertEqual(
            "DEGRADED",
            self.service.snapshot(self._live(writer=writer), now=self.now).phase,
        )

        startup = RuntimeStatusService(self.conn, self.settings)
        startup.mark_startup_failed(RuntimeError("bootstrap failed"))
        self.assertEqual("FAILED", startup.snapshot(None, now=self.now).phase)

        self.assertEqual(
            "RETRYING",
            self.service.snapshot(
                self._live(phase="RETRYING", retry_scheduled=True, writer=writer),
                now=self.now,
            ).phase,
        )
        self.service.mark_offline()
        self.assertEqual("OFFLINE", self.service.snapshot(None, now=self.now).phase)

        fatal = RuntimeStatusService(self.conn, self.settings)
        self.assertEqual(
            "FAILED",
            fatal.snapshot(
                self._live(phase="FAILED", writer=writer), now=self.now
            ).phase,
        )

    def test_rate_limit_quality_warning_and_writer_crash_are_visible(self) -> None:
        writer_loop = asyncio.new_event_loop()
        crashed_writer = writer_loop.create_future()
        crashed_writer.set_exception(RuntimeError("disk write failed"))
        self.conn.execute(
            """INSERT INTO ai_model_usage(
                   usage_date,model_key,provider,model,cooldown_until)
               VALUES (date('now'),'gemini','gemini','flash',datetime('now','+10 minutes'))"""
        )
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (2,'Direct 2','user')"
        )
        self.conn.execute(
            """INSERT INTO tasks(title,normalized_title,status,owner,details,confidence,created_at,updated_at)
               VALUES ('Follow up','follow up','open','me','',0.8,'now','now')"""
        )
        self.conn.execute(
            """INSERT INTO message_classifications(
                   chat_id,message_id,conversation_type,content_type,actionability,importance,
                   content_scope,information_scope,temporal_relevance,classifier_type,confidence,
                   classification_version,classified_at)
               VALUES (2,1,'direct','message','none','low','private','unknown','unknown','local',0.5,2,'now')"""
        )
        self.conn.execute(
            """INSERT INTO ai_message_state(chat_id,message_id,analysis_stale,analyzed_at)
               VALUES (2,1,1,'2026-08-20T12:00:00+00:00')"""
        )
        status = self.service.snapshot(self._live(writer=crashed_writer), now=self.now)
        self.assertEqual("FAILED", status.phase)
        self.assertTrue(status.ai.quota_limited)
        self.assertFalse(status.quality.context_fresh)
        self.assertIn("task-project links", status.quality.warnings)
        self.assertIn("classification unknowns", status.quality.warnings)
        self.assertIn("source identity", status.quality.warnings)
        self.assertTrue(
            any("writer: disk write failed" in error for error in status.recent_errors)
        )

    def test_pending_context_invalidation_is_not_reported_fresh(self) -> None:
        self.conn.execute(
            """INSERT INTO context_invalidations(
                   scope_type,scope_id,requested_revision,completed_revision,status,updated_at
               ) VALUES ('person',1,1,0,'pending','2026-08-24T10:00:00+00:00')"""
        )
        status = self.service.snapshot(self._live(), now=self.now)
        self.assertEqual(1, status.context.dirty_count)
        self.assertFalse(status.quality.context_fresh)
        self.assertEqual(7200, status.context.oldest_dirty_age_seconds)

    def test_home_and_status_screens_render_authoritative_snapshot(self) -> None:
        output = StringIO()
        console = Console(file=output, force_terminal=False, width=120)
        status = self.service.snapshot(None, now=self.now)
        show_main_menu(console, status)
        show_status(status, console)
        rendered = output.getvalue()
        self.assertIn("STARTING", rendered)
        self.assertIn("Data quality", rendered)
        self.assertIn("Source contact identity", rendered)
