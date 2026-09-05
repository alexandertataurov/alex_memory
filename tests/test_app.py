from __future__ import annotations

import asyncio
import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import AsyncMock, patch

from rich.console import Console

from alex_memory.app import AlexMemoryApp
from alex_memory.ai.routing import RequestPriority
from alex_memory.database import connect
from alex_memory.models import LiveSyncState
from alex_memory.runtime_status import RuntimeStatusService
from test_ai_pipeline import make_settings


class AppLifecycleTests(unittest.TestCase):
    def test_manual_daily_analysis_uses_interactive_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            app = AlexMemoryApp(settings, Console(file=StringIO(), width=100))
            app.conn = connect(settings)
            app.live_sync = object()
            app.dialogs_cache = []
            app._run_daily_analysis = AsyncMock()

            asyncio.run(app.analyze_daily())

            app._run_daily_analysis.assert_awaited_once_with()
            app.conn.close()

    def test_scheduled_daily_analysis_uses_background_priority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            app = AlexMemoryApp(settings, Console(file=StringIO(), width=100))
            app.conn = connect(settings)
            app._run_daily_analysis = AsyncMock()

            asyncio.run(app._scheduled_daily_analysis())

            app._run_daily_analysis.assert_awaited_once_with(
                priority=RequestPriority.BACKGROUND
            )
            app.conn.close()

    def test_daemon_does_not_announce_active_after_local_mode_startup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            app = AlexMemoryApp(
                make_settings(Path(directory)), Console(file=output, width=100)
            )
            app.start = AsyncMock()
            app.close = AsyncMock(return_value=None)

            self.assertEqual(1, asyncio.run(app.run_daemon()))
            self.assertNotIn("Daemon active", output.getvalue())

    def test_scheduled_brief_skips_stale_data_after_reconcile_failure(self) -> None:
        class FailedReconcile:
            def __init__(self) -> None:
                self.state = LiveSyncState()

            async def reconcile(self) -> None:
                raise RuntimeError("archive unavailable")

        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            output = StringIO()
            app = AlexMemoryApp(settings, Console(file=output, width=100))
            app.conn = connect(settings)
            app.live_sync = FailedReconcile()
            app._run_daily_analysis = AsyncMock()

            asyncio.run(app._auto_daily_brief("2026-08-26"))

            self.assertIn(
                "scheduled brief reconciliation", app.live_sync.state.last_error
            )
            app._run_daily_analysis.assert_not_awaited()
            self.assertEqual(
                0,
                app.conn.execute("SELECT COUNT(*) FROM daily_briefs").fetchone()[0],
            )
            self.assertIn("Scheduled brief unavailable", output.getvalue())
            app.conn.close()

    def test_close_reports_commit_failure_without_clean_shutdown_message(self) -> None:
        class FailingConnection:
            def commit(self) -> None:
                raise RuntimeError("commit failed")

            def close(self) -> None:
                pass

        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            app = AlexMemoryApp(
                make_settings(Path(directory)), Console(file=output, width=100)
            )
            app.conn = FailingConnection()
            with patch.object(app.session_lock, "release"):
                error = asyncio.run(app.close())

            self.assertIsNotNone(error)
            self.assertEqual("commit failed", str(error))
            self.assertIn("Shutdown incomplete", output.getvalue())
            self.assertNotIn("closed cleanly", output.getvalue())

    def test_close_records_disconnect_failure(self) -> None:
        class FailingClient:
            def is_connected(self) -> bool:
                return True

            async def disconnect(self) -> None:
                raise RuntimeError("disconnect failed")

        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            app = AlexMemoryApp(
                make_settings(Path(directory)), Console(file=output, width=100)
            )
            app.client = FailingClient()
            with patch.object(app.session_lock, "release"):
                error = asyncio.run(app.close())

            self.assertIsNotNone(error)
            self.assertEqual("disconnect failed", str(error))
            self.assertIn("Shutdown incomplete", output.getvalue())

    def test_run_retains_the_original_fatal_error_when_cleanup_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            app = AlexMemoryApp(
                make_settings(Path(directory)), Console(file=output, width=100)
            )
            app.start = AsyncMock(side_effect=RuntimeError("startup failed"))
            app.close = AsyncMock(return_value=RuntimeError("cleanup failed"))

            self.assertEqual(1, asyncio.run(app.run()))
            self.assertIn("startup failed", output.getvalue())

    def test_action_search_hides_maintenance_until_explicitly_requested(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            app = AlexMemoryApp(make_settings(Path(directory)), Console(file=output))
            with patch("alex_memory.app.Prompt.ask", side_effect=["", "1"]):
                self.assertEqual("review", app._command_search())
            self.assertNotIn("Maintenance", output.getvalue())

    def test_task_workflow_prompts_for_id_then_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = make_settings(Path(directory))
            app = AlexMemoryApp(settings, Console(file=StringIO(), width=100))
            app.conn = connect(settings)
            app.runtime_status = RuntimeStatusService(app.conn, settings)
            with patch(
                "alex_memory.app.Prompt.ask",
                side_effect=[
                    "/",
                    "maintenance",
                    "1",
                    "tasks",
                    "current",
                    "1",
                    "back",
                    "/",
                    "quit",
                    "1",
                ],
            ) as ask:
                asyncio.run(app.menu_loop())
            app.conn.close()
        prompts = [str(call.args[0]) for call in ask.call_args_list]
        self.assertIn("Task ID [dim](blank to return)[/dim]", prompts)
        self.assertIn("Task action", prompts)

    def test_telegram_start_failure_keeps_local_terminal_available(self) -> None:
        class FailingClient:
            def __init__(self, *args, **kwargs) -> None:
                pass

            async def start(self) -> None:
                raise OSError("network unavailable")

            def is_connected(self) -> bool:
                return False

        async def verify() -> str:
            with tempfile.TemporaryDirectory() as directory:
                output = StringIO()
                app = AlexMemoryApp(
                    make_settings(Path(directory)),
                    Console(file=output, force_terminal=False, width=100),
                )
                with patch("alex_memory.app.TelegramClient", FailingClient):
                    await app.start()
                    assert app.startup_sync_task is not None
                    await app.startup_sync_task
                self.assertIsNotNone(app.conn)
                self.assertEqual("FAILED", app.runtime_status.snapshot(None).phase)
                app._show_menu()
                await app.close()
                return output.getvalue()

        rendered = asyncio.run(verify())
        self.assertIn("Telegram unavailable", rendered)
        self.assertIn("People", rendered)
