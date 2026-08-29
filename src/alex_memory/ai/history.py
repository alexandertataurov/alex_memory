"""User-facing, resumable full-history orchestration.

Internal windows remain bounded for provider safety, but this module never
exposes them as product state. A run continues until all currently eligible
messages have committed classification and semantic analysis, or safely pauses
on a provider failure.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol, cast

from rich.console import Console, Group
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text

from ..classification import CLASSIFICATION_VERSION, classify_pending_messages
from ..config import Settings
from ..models import AIBatch
from ..ui.components import AppPanel as Panel
from ..ui.components import DataTable as Table
from ..ui.components import metric_strip, notice
from .repository import (
    claim_ai_jobs,
    ensure_history_jobs,
    fetch_unclassified_messages,
    history_coverage,
    refresh_conversation_analysis_state,
    save_ai_failure,
    save_ai_success,
)
from .router import AIRouter
from .routing import AIWorkload, RequestPriority
from .service import integrate_saved_batch, resume_saved_batches


@dataclass(frozen=True, slots=True)
class HistoryAnalysisReport:
    classified: int
    semantically_analyzed: int
    failures: int
    complete: bool
    coverage: dict[str, int]


class HistoryRouter(Protocol):
    requests: int
    fallbacks: int

    async def analyze(self, batch): ...


class FullHistoryAnalyzer:
    """Incrementally process all eligible Telegram history with durable progress."""

    def __init__(
        self,
        conn: sqlite3.Connection,
        settings: Settings,
        console: Console,
        router: HistoryRouter | None = None,
        should_continue: Callable[[], bool] | None = None,
    ):
        self.conn = conn
        self.settings = settings
        self.console = console
        self.router = router
        self.should_continue = should_continue

    async def analyze_all(self) -> HistoryAnalysisReport:
        if self.should_continue is not None and not self.should_continue():
            coverage = history_coverage(self.conn, self.settings)
            return HistoryAnalysisReport(0, 0, 0, False, coverage)
        classified = self._classify_all_pending()
        router: HistoryRouter = self.router or AIRouter(self.settings, conn=self.conn)
        owns_router = self.router is None

        async def finish(report: HistoryAnalysisReport) -> HistoryAnalysisReport:
            if owns_router:
                await cast(AIRouter, router).close()
            return report

        semantic = failures = 0
        consecutive_failures = 0
        last_error = "—"

        while True:
            await resume_saved_batches(self.conn, self.settings, lane="history")
            ensure_history_jobs(self.conn, self.settings)
            jobs = claim_ai_jobs(
                self.conn,
                "history",
                1,
                self.settings,
            )
            if not jobs:
                coverage = history_coverage(self.conn, self.settings)
                complete = coverage["semantic"] >= coverage["eligible"]
                self._show_progress(coverage, router, failures, complete)
                return await finish(
                    HistoryAnalysisReport(
                        classified, semantic, failures, complete, coverage
                    )
                )

            for position, (job_id, batch) in enumerate(jobs):
                if self.should_continue is not None and not self.should_continue():
                    self._release(job_id)
                    for pending_job_id, _ in jobs[position + 1 :]:
                        self._release(pending_job_id)
                    coverage = history_coverage(self.conn, self.settings)
                    self.console.print(
                        notice(
                            "New live activity has priority; history will resume when the queue is quiet.",
                            title="History analysis yielded safely",
                            tone="info",
                        )
                    )
                    return await finish(
                        HistoryAnalysisReport(
                            classified, semantic, failures, False, coverage
                        )
                    )
                saved = None
                try:
                    result = await self._analyze_with_live_monitor(
                        router, batch, semantic, position + 1, len(jobs), last_error
                    )
                    saved = save_ai_success(
                        self.conn,
                        batch,
                        result,
                        self.settings,
                        lane="history",
                        job_id=job_id,
                    )
                    if saved.batch_id is not None:
                        await integrate_saved_batch(
                            self.conn, saved.batch_id, self.settings
                        )
                        with self.conn:
                            refresh_conversation_analysis_state(
                                self.conn, batch.chat_id
                            )
                    semantic += len(batch.messages)
                    consecutive_failures = 0
                    self._show_activity(semantic, router)
                except (KeyboardInterrupt, asyncio.CancelledError):
                    self._release(job_id)
                    if owns_router:
                        await cast(AIRouter, router).close()
                    raise
                except Exception as error:
                    failures += 1
                    consecutive_failures += 1
                    last_error = f"{type(error).__name__}: {error}"
                    if saved is None:
                        save_ai_failure(
                            self.conn, batch, error, self.settings, "history", job_id
                        )
                    if consecutive_failures >= 3:
                        coverage = history_coverage(self.conn, self.settings)
                        self.console.print(
                            notice(
                                "Three provider failures recorded; history will resume after the queue clears.",
                                title="History analysis paused safely",
                                tone="warning",
                            )
                        )
                        return await finish(
                            HistoryAnalysisReport(
                                classified, semantic, failures, False, coverage
                            )
                        )
                    self.console.print(
                        notice(
                            "Provider retry scheduled; history continues with the next queued work.",
                            title="History analysis continuing",
                            tone="warning",
                        )
                    )

            coverage = history_coverage(self.conn, self.settings)
            self._show_progress(coverage, router, failures, False)

    def _classify_all_pending(self) -> int:
        total = 0
        while self.should_continue is None or self.should_continue():
            messages = fetch_unclassified_messages(
                self.conn, 500, self.settings, CLASSIFICATION_VERSION
            )
            if not messages:
                break
            with self.conn:
                total += classify_pending_messages(self.conn, messages)
                for chat_id in {message.chat_id for message in messages}:
                    refresh_conversation_analysis_state(self.conn, chat_id)
        return total

    async def _analyze_with_live_monitor(
        self,
        router: HistoryRouter,
        batch: object,
        committed: int,
        position: int,
        total: int,
        last_error: str,
    ):
        """Keep an animated request-status panel visible during provider latency."""
        started_at = asyncio.get_running_loop().time()
        with Live(
            self._live_request_panel(
                router, batch, committed, position, total, last_error, 0.0
            ),
            console=self.console,
            refresh_per_second=8,
            transient=False,
        ) as live:
            analysis = (
                router.analyze(
                    cast(AIBatch, batch),
                    workload=AIWorkload.CONTEXT_EXTRACTION,
                    priority=RequestPriority.BACKGROUND,
                )
                if isinstance(router, AIRouter)
                else router.analyze(batch)
            )
            request = asyncio.create_task(analysis)
            try:
                while not request.done():
                    elapsed = asyncio.get_running_loop().time() - started_at
                    live.update(
                        self._live_request_panel(
                            router,
                            batch,
                            committed,
                            position,
                            total,
                            last_error,
                            elapsed,
                        )
                    )
                    await asyncio.sleep(0.25)
                return await request
            except (KeyboardInterrupt, asyncio.CancelledError):
                request.cancel()
                # A blocking SDK call may report a loop-closure RuntimeError
                # while cancellation is unwinding. It is not a provider
                # failure and must not be persisted as one.
                with suppress(asyncio.CancelledError, RuntimeError):
                    await request
                raise

    def _live_request_panel(
        self,
        router: HistoryRouter,
        batch: object,
        committed: int,
        position: int,
        total: int,
        last_error: str,
        elapsed: float,
    ) -> Panel:
        chat_title = getattr(batch, "chat_title", "unknown chat")
        message_count = len(getattr(batch, "messages", ()))
        details = Table.grid(expand=True, padding=(0, 2))
        details.add_column(style="bold", width=15)
        details.add_column(ratio=1)
        details.add_row(
            "Current request",
            f"{position}/{total} · {chat_title} · {message_count} messages",
        )
        active_provider = getattr(router, "active_provider", None)
        active_model = getattr(router, "active_model", None)
        active_state = getattr(router, "active_state", "preparing request")
        retry_at = getattr(router, "retry_at", None)
        if retry_at is not None:
            remaining = max(0.0, retry_at - asyncio.get_running_loop().time())
            active_state = f"{active_state} · {remaining:.1f}s remaining"
        details.add_row(
            "Request state",
            f"{active_provider or 'router'} / {active_model or 'selecting'} · {active_state}",
        )
        details.add_row("Elapsed", f"{elapsed:.1f}s")
        if isinstance(router, AIRouter):
            snapshot = router.route_snapshot(
                AIWorkload.CONTEXT_EXTRACTION, RequestPriority.BACKGROUND
            )
            candidates = cast(tuple[str, ...], snapshot["candidates"])
            quota = cast(tuple[str, ...], snapshot["quota"])
            details.add_row("Eligible routes", " → ".join(candidates) or "none")
            details.add_row(
                "Session route", str(snapshot["session_model_key"] or "none")
            )
            details.add_row("Quota state", " · ".join(quota) or "none")
            details.add_row(
                "Last decision", str(snapshot["last_decision"] or "not selected")
            )
        else:
            details.add_row("Eligible routes", "external router")
        details.add_row(
            "This run",
            f"{committed:,} committed · {router.requests:,} requests · {router.fallbacks:,} fallbacks",
        )
        details.add_row(
            "Last error",
            Text(
                getattr(router, "last_error", None) or last_error,
                style="yellow"
                if (getattr(router, "last_error", None) or last_error) != "—"
                else "dim",
            ),
        )
        return Panel(
            Group(
                Spinner(
                    "dots",
                    text="Provider request in flight — elapsed time and route update live.",
                    style="bright_cyan",
                ),
                details,
            ),
            title="History AI monitor · LIVE",
            border_style="magenta",
        )

    def _release(self, job_id: int) -> None:
        with self.conn:
            self.conn.execute(
                """UPDATE ai_jobs SET status='pending',retry_after_at=NULL
                   WHERE job_id=? AND status='running'""",
                (job_id,),
            )

    def _show_progress(
        self,
        coverage: dict[str, int],
        router: HistoryRouter,
        failures: int,
        complete: bool,
    ) -> None:
        eligible = coverage["eligible"]
        classified = coverage["classified"]
        semantic = coverage["semantic"]
        self.console.print(
            metric_strip(
                [
                    ("Classification", _ratio(classified, eligible), "accent"),
                    ("Semantic analysis", _ratio(semantic, eligible), "info"),
                    (
                        "Remaining",
                        max(0, eligible - semantic),
                        "success" if complete else "warning",
                    ),
                    ("Provider failures", failures, "danger" if failures else "muted"),
                ]
            )
        )
        self.console.print(
            f"[dim]Private conversations: {coverage['private_semantic']:,}/{coverage['private_total']:,} semantic · "
            f"requests {router.requests:,} · fallbacks {router.fallbacks:,}[/dim]"
        )
        if complete:
            self.console.print(
                notice(
                    "Historical AI coverage is 100% for currently eligible messages.",
                    title="History analysis complete",
                    tone="success",
                )
            )

    def _show_activity(self, semantic: int, router: HistoryRouter) -> None:
        """Keep rate-limited history work visible between coverage reports."""
        self.console.print(
            metric_strip(
                [
                    ("Committed", semantic, "accent"),
                    ("Requests", router.requests, "info"),
                    (
                        "Fallbacks",
                        router.fallbacks,
                        "warning" if router.fallbacks else "success",
                    ),
                    (
                        "Gemini pace",
                        f"{self.settings.gemini_requests_per_minute:g} RPM",
                        "muted",
                    ),
                ]
            )
        )


def _ratio(part: int, whole: int) -> str:
    return "100.0%" if not whole else f"{part / whole * 100:.1f}%"
