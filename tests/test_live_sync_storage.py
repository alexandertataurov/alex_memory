from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path

from alex_memory.database import connect
from alex_memory.ai.repository import ensure_history_jobs
from alex_memory.models import SyncState
from alex_memory.models import DialogInfo
from alex_memory.telegram.normalize import is_archive_eligible, normalize_chat
from alex_memory.telegram.policy import SyncPlan
from alex_memory.telegram.worker import sync_streaming_plan
from alex_memory.telegram.worker import sync_one_chat
from alex_memory.telegram.writer import database_writer
from alex_memory.telegram.live import TelegramSyncService

from test_ai_pipeline import make_settings


class _Group:
    title = "Project group"
    username = None
    megagroup = True
    bot = False


class _Message:
    id = 1
    sender_id = 2
    date = None
    raw_text = "Fast fetch"
    reply_to = None
    out = False
    media = None


class _Client:
    def __init__(self):
        self.kwargs = None

    async def iter_messages(self, _entity, **kwargs):
        self.kwargs = kwargs
        yield _Message()


class _LifecycleClient(_Client):
    def __init__(self):
        super().__init__()
        self.handlers = []

    def is_connected(self):
        return True

    def add_event_handler(self, callback, _event):
        self.handlers.append(callback)

    def remove_event_handler(self, callback):
        self.handlers.remove(callback)


class _UpToDateDialog:
    entity = object()
    message = type("Latest", (), {"id": 10})()


class LiveStorageTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_commit_does_not_report_messages_as_saved_or_committed(self):
        class FailingCommitConnection:
            def __init__(self, conn):
                self.conn = conn

            def execute(self, *args, **kwargs):
                return self.conn.execute(*args, **kwargs)

            def commit(self):
                raise sqlite3.OperationalError("commit failed")

        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory), commit_every=50)
            conn = connect(settings)
            self.addAsyncCleanup(conn.close)
            queue: asyncio.Queue = asyncio.Queue()
            state = SyncState(selected_count=0)
            notifications: list[int] = []
            writer = asyncio.create_task(
                database_writer(
                    FailingCommitConnection(conn),
                    queue,
                    state,
                    settings,
                    notifications.append,
                )
            )
            await queue.put(
                (
                    "message",
                    (100, 1, 2, "2026-08-24T10:00:00+00:00", "New work", None, 0, 0),
                )
            )

            with self.assertRaisesRegex(sqlite3.OperationalError, "commit failed"):
                await writer
            self.assertEqual(0, state.messages_saved)
            self.assertEqual([], notifications)

    async def test_sync_and_close_propagate_a_failed_writer_with_queued_work(self):
        async def fail_writer():
            raise RuntimeError("writer failed")

        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            conn = connect(settings)
            self.addAsyncCleanup(conn.close)
            service = TelegramSyncService(_LifecycleClient(), conn, settings)
            service.write_queue = asyncio.Queue()
            await service.write_queue.put(
                ("chat", (100, "Ilya", "ilya", "user", 0, "now"))
            )
            service.writer_task = asyncio.create_task(fail_writer())
            await asyncio.sleep(0)

            with self.assertRaisesRegex(RuntimeError, "writer failed"):
                await service.sync([])
            with self.assertRaisesRegex(RuntimeError, "writer failed"):
                await service.close()

    async def test_queued_edit_and_deletion_preserve_audit_history(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory), commit_every=1)
            conn = connect(settings)
            queue: asyncio.Queue = asyncio.Queue()
            state = SyncState(selected_count=0)
            writer = asyncio.create_task(database_writer(conn, queue, state, settings))
            await queue.put(("chat", (100, "Ilya", "ilya", "user", 0, "now")))
            await queue.put(
                (
                    "message",
                    (100, 1, 2, "2026-08-22T10:00:00+00:00", "Original", None, 0, 0),
                )
            )
            await queue.put(
                ("message_edit", (100, 1, "Edited", "2026-08-22T10:05:00+00:00"))
            )
            await queue.put(("message_delete", (100, 1, "2026-08-22T10:06:00+00:00")))
            await queue.join()
            await queue.put(None)
            await writer
            self.assertEqual(
                ("Edited", 1),
                conn.execute(
                    "SELECT text, is_deleted FROM messages WHERE chat_id=100 AND message_id=1"
                ).fetchone(),
            )
            self.assertEqual(
                ["initial", "edited", "deleted"],
                [
                    r[0]
                    for r in conn.execute(
                        "SELECT reason FROM message_versions ORDER BY version_id"
                    )
                ],
            )

    async def test_source_mutations_mark_existing_interpretation_stale(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory), commit_every=1)
            conn = connect(settings)
            queue: asyncio.Queue = asyncio.Queue()
            writer = asyncio.create_task(
                database_writer(conn, queue, SyncState(selected_count=0), settings)
            )
            conn.execute(
                "INSERT INTO chats(chat_id,title,chat_type) VALUES (100,'Ilya','user')"
            )
            conn.execute(
                "INSERT INTO messages(chat_id,message_id,text) VALUES (100,1,'Original')"
            )
            conn.execute(
                "INSERT INTO ai_message_state(chat_id,message_id,analyzed_at) VALUES (100,1,'now')"
            )
            conn.execute(
                """INSERT INTO message_classifications(
                       chat_id,message_id,conversation_type,content_type,actionability,
                       importance,content_scope,information_scope,temporal_relevance,
                       potential_state_change,is_forwarded,topic_json,classifier_type,
                       confidence,classification_version,context_version,classified_at
                   ) VALUES (100,1,'direct','message','none','normal','private',
                             'private','unknown',0,0,'[]','test',1.0,2,1,'now')"""
            )
            conn.commit()

            await queue.put(
                ("message_edit", (100, 1, "Edited", "2026-08-22T10:05:00+00:00"))
            )
            await queue.join()
            self.assertEqual(
                (1, 1),
                conn.execute(
                    """SELECT a.analysis_stale,mc.context_stale
                       FROM ai_message_state AS a
                       JOIN message_classifications AS mc
                         ON mc.chat_id=a.chat_id AND mc.message_id=a.message_id
                       WHERE a.chat_id=100 AND a.message_id=1"""
                ).fetchone(),
            )
            self.assertEqual(1, ensure_history_jobs(conn, settings))
            self.assertEqual(
                [(100, 1)],
                conn.execute(
                    "SELECT chat_id,message_id FROM ai_job_messages ORDER BY ordinal"
                ).fetchall(),
            )
            await queue.put(("message_delete", (100, 1, "2026-08-22T10:06:00+00:00")))
            await queue.put(("message_delete", (100, 1, "2026-08-22T10:07:00+00:00")))
            await queue.join()
            await queue.put(None)
            await writer
            self.assertEqual(
                1,
                conn.execute(
                    """SELECT COUNT(*) FROM message_versions
                       WHERE chat_id=100 AND message_id=1 AND reason='deleted'"""
                ).fetchone()[0],
            )

    async def test_message_wakeup_follows_the_writer_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory), commit_every=50)
            conn = connect(settings)
            self.addAsyncCleanup(conn.close)
            queue: asyncio.Queue = asyncio.Queue()
            notifications: list[int] = []
            writer = asyncio.create_task(
                database_writer(
                    conn,
                    queue,
                    SyncState(selected_count=0),
                    settings,
                    notifications.append,
                )
            )
            await queue.put(("chat", (100, "Ilya", "ilya", "user", 0, "now")))
            await queue.put(
                (
                    "message",
                    (100, 1, 2, "2026-08-24T10:00:00+00:00", "New work", None, 0, 0),
                )
            )
            await queue.join()
            self.assertEqual([1], notifications)
            self.assertEqual(
                1,
                conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
            )
            await queue.put(None)
            await writer

    async def test_normalized_group_metadata_remains_archive_eligible(self) -> None:
        chat = normalize_chat(100, _Group())
        self.assertEqual("group", chat[3])
        self.assertTrue(is_archive_eligible(chat))

    async def test_history_fetch_disables_telethon_default_page_delay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            client, queue, state, stop = (
                _Client(),
                asyncio.Queue(),
                SyncState(1),
                asyncio.Event(),
            )
            info = DialogInfo(
                type("Dialog", (), {"entity": object()})(),
                100,
                "Ilya",
                None,
                "user",
                False,
                None,
            )
            completed = await sync_streaming_plan(
                client,
                info,
                SyncPlan("incremental", "incremental"),
                queue,
                state,
                1,
                stop,
                settings,
            )
            self.assertTrue(completed)
            self.assertEqual(0.0, client.kwargs["wait_time"])

    async def test_bootstrapped_dialog_with_matching_latest_id_skips_fetch_rpc(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            client, queue, state, stop = (
                _Client(),
                asyncio.Queue(),
                SyncState(1),
                asyncio.Event(),
            )
            info = DialogInfo(_UpToDateDialog(), 100, "Ilya", None, "user", False, None)
            await sync_one_chat(
                client,
                info,
                queue,
                {100: 10},
                {100: {"bootstrap_complete": True}},
                state,
                1,
                stop,
                settings,
            )
            self.assertIsNone(client.kwargs)
            self.assertEqual("up to date", state.active[1]["status"])

    async def test_startup_uses_the_same_bootstrap_planner_as_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory), commit_every=1)
            conn = connect(settings)
            client = _LifecycleClient()
            info = DialogInfo(
                type("Dialog", (), {"entity": object(), "message": None})(),
                100,
                "Ilya",
                None,
                "user",
                False,
                None,
            )
            service = TelegramSyncService(client, conn, settings)
            await service.start([info])
            self.assertEqual(0, client.kwargs["min_id"])
            self.assertEqual(
                "personal_full",
                conn.execute(
                    "SELECT bootstrap_mode FROM sync_state WHERE chat_id=100"
                ).fetchone()[0],
            )
            await service.close()
