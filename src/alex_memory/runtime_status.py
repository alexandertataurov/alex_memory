"""One bounded, read-only runtime and data-quality status snapshot."""

from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .ai.repository import history_coverage
from .context import graph_diagnostics
from .schema_support import fts_index_health

if TYPE_CHECKING:
    from .config import Settings
    from .telegram.live import TelegramSyncService


_PHASES = {"STARTING", "HEALTHY", "DEGRADED", "RETRYING", "FAILED", "OFFLINE"}
_PROJECT_STATUSES = {"active", "waiting", "stale", "critical", "completed", "archived"}


@dataclass(frozen=True, slots=True)
class TelegramRuntimeStatus:
    connected: bool
    archive_lag_seconds: int | None
    queue_size: int
    last_reconciliation_at: str | None
    retry_scheduled: bool


@dataclass(frozen=True, slots=True)
class WriterRuntimeStatus:
    state: str
    error: str | None


@dataclass(frozen=True, slots=True)
class AIRuntimeStatus:
    pending_jobs: int
    running_jobs: int
    failed_jobs: int
    current_route: str | None
    quota_limited: bool


@dataclass(frozen=True, slots=True)
class ContextRuntimeStatus:
    dirty_count: int
    oldest_dirty_age_seconds: int | None


@dataclass(frozen=True, slots=True)
class DataQualityStatus:
    fts_healthy: bool | None
    task_project_linked: int
    task_total: int
    actionable_tasks: int
    valid_projects: int
    project_total: int
    unknown_classifications: int
    classified_messages: int
    source_identified_chats: int
    direct_chats: int
    context_fresh: bool
    warnings: tuple[str, ...]

    @property
    def task_project_coverage(self) -> float:
        return self.task_project_linked / self.task_total if self.task_total else 1.0

    @property
    def project_health_validity(self) -> float:
        return self.valid_projects / self.project_total if self.project_total else 1.0

    @property
    def classification_unknown_rate(self) -> float:
        return (
            self.unknown_classifications / self.classified_messages
            if self.classified_messages
            else 0.0
        )

    @property
    def source_identity_coverage(self) -> float:
        return (
            self.source_identified_chats / self.direct_chats
            if self.direct_chats
            else 1.0
        )


@dataclass(frozen=True, slots=True)
class RuntimeStatus:
    phase: str
    telegram: TelegramRuntimeStatus
    writer: WriterRuntimeStatus
    ai: AIRuntimeStatus
    context: ContextRuntimeStatus
    graph: dict[str, int | float]
    history: dict[str, int]
    review_count: int
    quality: DataQualityStatus
    recent_errors: tuple[str, ...]


class RuntimeStatusService:
    """Build a snapshot without taking ownership of runtime workers or data."""

    def __init__(self, conn: sqlite3.Connection, settings: Settings):
        self.conn = conn
        self.settings = settings
        self._offline = False
        self._startup_error: str | None = None

    def mark_starting(self) -> None:
        self._offline = False
        self._startup_error = None

    def mark_startup_failed(self, error: Exception) -> None:
        self._startup_error = _brief_error(error)

    def mark_offline(self) -> None:
        self._offline = True

    def snapshot(
        self,
        live_sync: TelegramSyncService | None,
        *,
        now: datetime | None = None,
    ) -> RuntimeStatus:
        now = now or datetime.now(UTC)
        telegram, writer = self._telegram_and_writer(live_sync, now)
        ai = self._ai_status()
        context = self._context_status(now)
        graph = graph_diagnostics(self.conn)
        history = history_coverage(self.conn, self.settings)
        quality = self._quality_status(context)
        phase = self._phase(live_sync, telegram, writer)
        errors = self._recent_errors(live_sync, writer)
        return RuntimeStatus(
            phase=phase,
            telegram=telegram,
            writer=writer,
            ai=ai,
            context=context,
            graph=graph,
            history=history,
            review_count=int(
                self.conn.execute(
                    "SELECT COUNT(*) FROM review_queue WHERE status='pending'"
                ).fetchone()[0]
                or 0
            ),
            quality=quality,
            recent_errors=errors,
        )

    def _telegram_and_writer(
        self,
        live_sync: TelegramSyncService | None,
        now: datetime,
    ) -> tuple[TelegramRuntimeStatus, WriterRuntimeStatus]:
        latest_message = self.conn.execute("SELECT MAX(date) FROM messages").fetchone()[
            0
        ]
        archive_lag = _age_seconds(latest_message, now)
        if live_sync is None:
            return (
                TelegramRuntimeStatus(False, archive_lag, 0, None, False),
                WriterRuntimeStatus("unavailable", None),
            )

        state = live_sync.state
        queue = live_sync.write_queue
        writer_task = live_sync.writer_task
        writer_state, writer_error = _writer_state(writer_task)
        return (
            TelegramRuntimeStatus(
                connected=bool(state.connected),
                archive_lag_seconds=archive_lag,
                queue_size=queue.qsize() if queue is not None else 0,
                last_reconciliation_at=state.last_reconciliation_at,
                retry_scheduled=bool(state.retry_scheduled),
            ),
            WriterRuntimeStatus(writer_state, writer_error),
        )

    def _ai_status(self) -> AIRuntimeStatus:
        pending, running, failed = self.conn.execute(
            """SELECT
                   SUM(CASE WHEN status='pending' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN status='running' THEN 1 ELSE 0 END),
                   SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END)
               FROM ai_jobs"""
        ).fetchone()
        route = self.conn.execute(
            """SELECT provider, model FROM ai_jobs
               WHERE status='running' ORDER BY started_at DESC LIMIT 1"""
        ).fetchone()
        if route is None:
            route = self.conn.execute(
                """SELECT provider, model FROM ai_route_events
                   ORDER BY event_id DESC LIMIT 1"""
            ).fetchone()
        quota_limited = bool(
            self.conn.execute(
                """SELECT 1 FROM ai_model_usage
                   WHERE usage_date=date('now')
                     AND cooldown_until IS NOT NULL
                     AND julianday(cooldown_until) > julianday('now')
                   LIMIT 1"""
            ).fetchone()
        )
        current_route = (
            f"{route[0]} / {route[1] or 'selecting'}" if route is not None else None
        )
        return AIRuntimeStatus(
            int(pending or 0),
            int(running or 0),
            int(failed or 0),
            current_route,
            quota_limited,
        )

    def _context_status(self, now: datetime) -> ContextRuntimeStatus:
        dirty_rows = self.conn.execute(
            """SELECT COUNT(*), MIN(COALESCE(m.date, a.analyzed_at))
               FROM ai_message_state AS a
               LEFT JOIN messages AS m ON m.chat_id=a.chat_id AND m.message_id=a.message_id
               WHERE a.analysis_stale=1
               UNION ALL
               SELECT COUNT(*), MIN(COALESCE(m.date, mc.classified_at))
               FROM message_classifications AS mc
               LEFT JOIN messages AS m ON m.chat_id=mc.chat_id AND m.message_id=mc.message_id
               WHERE mc.context_stale=1
               UNION ALL
               SELECT COUNT(*), MIN(updated_at)
               FROM context_invalidations
               WHERE status IN ('pending','running','failed')"""
        ).fetchall()
        dirty_count = sum(int(row[0] or 0) for row in dirty_rows)
        dirty_dates = [str(row[1]) for row in dirty_rows if row[1]]
        oldest_dirty = min(dirty_dates) if dirty_dates else None
        return ContextRuntimeStatus(dirty_count, _age_seconds(oldest_dirty, now))

    def _quality_status(self, context: ContextRuntimeStatus) -> DataQualityStatus:
        fts = fts_index_health(self.conn)
        fts_healthy = bool(fts["healthy"]) if fts["available"] else None
        linked, task_total, actionable = self.conn.execute(
            """SELECT
                   SUM(CASE WHEN related_project_id IS NOT NULL THEN 1 ELSE 0 END),
                   COUNT(*),
                   SUM(CASE WHEN status IN ('open','waiting') THEN 1 ELSE 0 END)
               FROM tasks"""
        ).fetchone()
        valid_projects, project_total = self.conn.execute(
            """SELECT
                   SUM(CASE WHEN status IN ('active','waiting','stale','critical','completed','archived')
                            AND (health_score IS NULL OR health_score BETWEEN 0 AND 100)
                       THEN 1 ELSE 0 END),
                   COUNT(*)
               FROM projects"""
        ).fetchone()
        unknown, classified = self.conn.execute(
            """SELECT
                   SUM(CASE WHEN information_scope='unknown' THEN 1 ELSE 0 END),
                   COUNT(*)
               FROM message_classifications"""
        ).fetchone()
        source_identified, direct_chats = self.conn.execute(
            """SELECT
                   COUNT(DISTINCT CASE WHEN p.telegram_user_id IS NOT NULL THEN c.chat_id END),
                   COUNT(DISTINCT c.chat_id)
               FROM chats AS c
               LEFT JOIN current_conversation_context AS cc ON cc.chat_id=c.chat_id
               LEFT JOIN people AS p ON p.person_id=cc.person_id
               WHERE c.chat_type='user'"""
        ).fetchone()
        linked, task_total, actionable = (
            int(linked or 0),
            int(task_total or 0),
            int(actionable or 0),
        )
        valid_projects, project_total = (
            int(valid_projects or 0),
            int(project_total or 0),
        )
        unknown, classified = int(unknown or 0), int(classified or 0)
        source_identified, direct_chats = (
            int(source_identified or 0),
            int(direct_chats or 0),
        )
        warnings = []
        if fts_healthy is False:
            warnings.append("FTS coverage")
        if task_total and linked < task_total:
            warnings.append("task-project links")
        if project_total and valid_projects < project_total:
            warnings.append("project health")
        if classified and unknown:
            warnings.append("classification unknowns")
        if direct_chats and source_identified < direct_chats:
            warnings.append("source identity")
        if context.dirty_count:
            warnings.append("context freshness")
        return DataQualityStatus(
            fts_healthy,
            linked,
            task_total,
            actionable,
            valid_projects,
            project_total,
            unknown,
            classified,
            source_identified,
            direct_chats,
            context.dirty_count == 0,
            tuple(warnings),
        )

    def _phase(
        self,
        live_sync: TelegramSyncService | None,
        telegram: TelegramRuntimeStatus,
        writer: WriterRuntimeStatus,
    ) -> str:
        if self._offline:
            return "OFFLINE"
        if writer.state == "failed":
            return "FAILED"
        if live_sync is None:
            return "FAILED" if self._startup_error else "STARTING"
        phase = str(live_sync.state.phase).upper()
        if phase not in _PHASES:
            phase = "DEGRADED"
        if phase == "RETRYING" and not telegram.retry_scheduled:
            phase = "DEGRADED"
        if phase == "HEALTHY" and (
            not telegram.connected
            or _archive_is_behind(telegram.archive_lag_seconds, self.settings)
        ):
            return "DEGRADED"
        return phase

    def _recent_errors(
        self,
        live_sync: TelegramSyncService | None,
        writer: WriterRuntimeStatus,
    ) -> tuple[str, ...]:
        errors: list[str] = []
        if self._startup_error:
            errors.append(f"startup: {self._startup_error}")
        if live_sync is not None and live_sync.state.last_error:
            errors.append(_brief_error(live_sync.state.last_error))
        if writer.error:
            errors.append(f"writer: {writer.error}")
        rows = self.conn.execute(
            """SELECT error FROM ai_batches WHERE error IS NOT NULL
               ORDER BY batch_id DESC LIMIT 3"""
        ).fetchall()
        errors.extend(_brief_error(row[0]) for row in rows if row[0])
        return tuple(dict.fromkeys(errors))[:5]


def _writer_state(task: asyncio.Task | None) -> tuple[str, str | None]:
    if task is None:
        return "unavailable", None
    if task.cancelled():
        return "stopped", "cancelled"
    if not task.done():
        return "running", None
    error = task.exception()
    if error is not None:
        return "failed", _brief_error(error)
    return "stopped", None


def _age_seconds(value: object, now: datetime) -> int | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0, int((now - parsed).total_seconds()))


def _archive_is_behind(lag_seconds: int | None, settings: Settings) -> bool:
    return lag_seconds is not None and lag_seconds > max(
        300, settings.tg_reconcile_interval_minutes * 120
    )


def _brief_error(value: object) -> str:
    return " ".join(str(value).split())[:180]
