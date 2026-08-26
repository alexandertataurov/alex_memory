"""Long-running local Telegram synchronization service."""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import Settings
from ..database import load_last_message_ids, load_sync_states
from ..models import DialogInfo, LiveSyncState, SyncState
from ..utils import utc_now
from ..ai.scheduler import BackgroundIntelligenceScheduler
from .inventory import collect_dialog_inventory
from .listener import TelegramEventListener
from .policy import eligible_dialogs
from .worker import sync_one_chat
from .writer import database_writer


class TelegramSyncService:
    """One Telegram lifecycle: bootstrap/catch-up, live events, reconciliation.

    Startup and later reconciliation use the same per-dialog planner.  The live
    listener starts first, so messages arriving during catch-up share the one
    queued SQLite durability boundary and are deduplicated there.
    """

    def __init__(
        self,
        client,
        conn: sqlite3.Connection,
        settings: Settings,
        *,
        background_scheduler: BackgroundIntelligenceScheduler | None = None,
        on_daily_brief=None,
    ):
        self.client, self.conn, self.settings = client, conn, settings
        self.background_scheduler = background_scheduler
        self.on_daily_brief = on_daily_brief
        self.state = LiveSyncState()
        self.stop_event = asyncio.Event()
        self.write_queue: asyncio.Queue | None = None
        self.writer_task: asyncio.Task | None = None
        self.listener: TelegramEventListener | None = None
        self.background_tasks: list[asyncio.Task] = []

    async def start(self, dialogs: list[DialogInfo]) -> int:
        self.state.phase = "STARTING"
        self.write_queue = asyncio.Queue(maxsize=self.settings.write_queue_size)
        self.writer_task = asyncio.create_task(
            database_writer(
                self.conn,
                self.write_queue,
                self.state,
                self.settings,
                self._messages_committed,
            )
        )
        self.listener = TelegramEventListener(self.client, self.write_queue, self.state)
        self.listener.install()
        self.state.connected = bool(self.client.is_connected())
        try:
            received = await self.sync(dialogs)
        except Exception:
            self.state.phase = "FAILED"
            raise
        if self.settings.tg_reconcile_enabled:
            self.background_tasks.append(
                asyncio.create_task(self._periodic_reconcile())
            )
        if self.background_scheduler is not None:
            self.background_scheduler.start()
        if self.settings.daily_brief_auto_generate and self.on_daily_brief:
            self.background_tasks.append(asyncio.create_task(self._periodic_brief()))
        self.state.phase = "HEALTHY"
        return received

    async def reconcile(self, dialogs=None) -> int:
        """Run the same policy-driven catch-up used during startup."""
        if dialogs is None:
            dialogs = await collect_dialog_inventory(self.client)
        return await self.sync(dialogs)

    async def sync(self, dialogs: list[DialogInfo]) -> int:
        """Bootstrap new chats and incrementally catch up known chats."""
        if not self.write_queue:
            return 0
        try:
            last_ids = load_last_message_ids(self.conn)
            sync_states = load_sync_states(self.conn)
            planning_state = SyncState(selected_count=len(eligible_dialogs(dialogs)))
            before = self.state.messages_saved
            for worker_id, info in enumerate(eligible_dialogs(dialogs), start=1):
                await sync_one_chat(
                    self.client,
                    info,
                    self.write_queue,
                    last_ids,
                    sync_states,
                    planning_state,
                    worker_id,
                    self.stop_event,
                    self.settings,
                )
            await self._drain_writer()
            received = self.state.messages_saved - before
            self.state.last_reconciliation_at = utc_now()
            self.state.connected = True
            self.state.reconnect_attempts = 0
            self.state.retry_scheduled = False
            self.state.phase = "HEALTHY"
            return received
        except Exception as error:
            self.state.connected = False
            self.state.last_error = f"reconcile: {type(error).__name__}: {error}"
            if not self.state.retry_scheduled:
                self.state.phase = "DEGRADED"
            raise

    async def _periodic_reconcile(self) -> None:
        delay = 2
        wait_seconds = self.settings.tg_reconcile_interval_minutes * 60
        while not self.stop_event.is_set():
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=wait_seconds)
                break
            except asyncio.TimeoutError:
                pass
            try:
                await self.reconcile()
                delay = 2
                wait_seconds = self.settings.tg_reconcile_interval_minutes * 60
            except Exception:
                self.state.reconnect_attempts += 1
                self.state.retry_scheduled = True
                self.state.phase = "RETRYING"
                await self._recover_connection(delay)
                delay = min(60, 5 if delay == 2 else delay * 2)
                wait_seconds = delay

    async def _recover_connection(self, delay: int) -> None:
        try:
            if self.client.is_connected():
                await self.client.disconnect()
            await asyncio.wait_for(self.stop_event.wait(), timeout=delay)
            return
        except asyncio.TimeoutError:
            pass
        try:
            await self.client.connect()
            self.state.connected = bool(self.client.is_connected())
            if self.state.connected:
                await self.reconcile()
        except Exception as error:
            self.state.last_error = f"reconnect: {type(error).__name__}: {error}"
            self.state.phase = "RETRYING"

    def _messages_committed(self, message_count: int) -> None:
        if self.background_scheduler is not None:
            self.background_scheduler.notify_committed_messages(message_count)

    async def _drain_writer(self) -> None:
        """Wait for queued writes without hiding a failed writer task."""
        assert self.write_queue is not None
        assert self.writer_task is not None
        if self.writer_task.done():
            await self.writer_task
            raise RuntimeError("Writer stopped before its queue drained")

        queue_join = asyncio.create_task(self.write_queue.join())
        done, _ = await asyncio.wait(
            {queue_join, self.writer_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if self.writer_task in done:
            if not queue_join.done():
                queue_join.cancel()
                await asyncio.gather(queue_join, return_exceptions=True)
            await self.writer_task
            raise RuntimeError("Writer stopped before its queue drained")
        await queue_join
        if self.writer_task.done():
            await self.writer_task
            raise RuntimeError("Writer stopped before its queue drained")

    async def _periodic_brief(self) -> None:
        timezone = ZoneInfo(self.settings.app_timezone)
        last_run: str | None = None
        while not self.stop_event.is_set():
            now = datetime.now(timezone)
            if (
                now.strftime("%H:%M") == self.settings.daily_brief_time
                and last_run != now.date().isoformat()
            ):
                last_run = now.date().isoformat()
                await self.on_daily_brief(now.date().isoformat())
            try:
                await asyncio.wait_for(self.stop_event.wait(), timeout=30)
            except asyncio.TimeoutError:
                pass

    async def close(self) -> None:
        self.stop_event.set()
        if self.background_scheduler is not None:
            await self.background_scheduler.close()
        if self.listener:
            self.listener.remove()
        for task in self.background_tasks:
            task.cancel()
        await asyncio.gather(*self.background_tasks, return_exceptions=True)
        if self.write_queue and self.writer_task:
            await self._drain_writer()
            await self.write_queue.put(None)
            await self.writer_task


# Import compatibility for extensions written before the consolidation.  Product
# code uses TelegramSyncService exclusively.
TelegramLiveService = TelegramSyncService
