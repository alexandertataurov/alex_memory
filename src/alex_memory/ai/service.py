from __future__ import annotations

import asyncio
import sqlite3
import time
from collections.abc import Callable
from contextlib import nullcontext

from rich.console import Console
from rich.live import Live

from ..config import Settings
from ..context.refresh import refresh_pending_context
from ..models import AIBatch, AIBatchReport, AISaveResult
from ..operational import process_ai_batch
from ..ui.ai import render_ai_progress, show_ai_run_report
from ..ui.components import metric_strip, notice, safe_text
from .repository import (
    claim_ai_jobs,
    ensure_daily_jobs,
    get_ai_counts,
    release_ai_job,
    save_ai_failure,
    save_ai_success,
)
from .router import AIRouter
from .routing import AIWorkload, RequestPriority


async def analyze_new_messages(
    conn: sqlite3.Connection, settings: Settings, console: Console
) -> None:
    """Backward-compatible entry point for the Daily lane."""
    await analyze_daily_messages(conn, settings, console)


async def analyze_daily_messages(
    conn: sqlite3.Connection,
    settings: Settings,
    console: Console,
    *,
    priority: RequestPriority = RequestPriority.INTERACTIVE,
) -> None:
    created = ensure_daily_jobs(conn, settings)
    jobs = claim_ai_jobs(conn, "daily", settings.ai_daily_max_messages, settings)
    await _run_lane(conn, settings, console, "daily", jobs, created, priority=priority)


async def analyze_history_messages(
    conn: sqlite3.Connection,
    settings: Settings,
    console: Console,
    should_continue: Callable[[], bool] | None = None,
) -> None:
    from .history import FullHistoryAnalyzer

    try:
        await FullHistoryAnalyzer(
            conn, settings, console, should_continue=should_continue
        ).analyze_all()
    except (KeyboardInterrupt, asyncio.CancelledError):
        console.print(
            notice(
                "Committed history work is retained; unfinished work will resume next time.",
                title="History analysis stopped safely",
                tone="warning",
            )
        )


async def _run_lane(
    conn: sqlite3.Connection,
    settings: Settings,
    console: Console,
    lane: str,
    jobs: list[tuple[int, AIBatch]],
    created: int,
    *,
    render_console: bool = True,
    on_progress: Callable[[], None] | None = None,
    priority: RequestPriority = RequestPriority.INTERACTIVE,
) -> None:
    if not jobs:
        if render_console:
            console.print(
                notice(
                    f"No {lane} AI work is queued.",
                    title="Analysis up to date",
                    tone="success",
                )
            )
        return

    router = AIRouter(settings, conn=conn)
    started = time.monotonic()
    reports: list[AIBatchReport] = []
    saved = errors = processed = 0
    total_messages = sum(len(batch.messages) for _, batch in jobs)

    try:
        progress = (
            Live(
                render_ai_progress(
                    len(jobs), 0, total_messages, 0, 0, 0, started, settings, lane=lane
                ),
                console=console,
                refresh_per_second=6,
                transient=False,
            )
            if render_console
            else nullcontext()
        )
        with progress as live:
            if on_progress:
                on_progress()
            for completed, (job_id, batch) in enumerate(jobs, start=1):
                try:
                    result = await router.analyze(
                        batch,
                        workload=AIWorkload.CONTEXT_EXTRACTION,
                        priority=priority,
                    )
                    save_result = save_ai_success(
                        conn, batch, result, settings, lane=lane, job_id=job_id
                    )
                    if save_result.batch_id is not None:
                        process_ai_batch(conn, save_result.batch_id, settings)
                        await refresh_pending_context(conn, settings)
                    saved += save_result.inserted
                    processed += len(batch.messages)
                    reports.append(
                        AIBatchReport(
                            chat_id=batch.chat_id,
                            chat_title=batch.chat_title,
                            message_count=len(batch.messages),
                            summary=result.summary,
                            model_items=result.items,
                            save_result=save_result,
                            lane=lane,
                            provider=result.provider,
                            model=result.model,
                            fallback_used=result.fallback_used,
                            provider_note=str(result.usage.get("fallback_reason", "")),
                        )
                    )
                except asyncio.CancelledError:
                    release_ai_job(conn, job_id)
                    raise
                except Exception as error:
                    errors += 1
                    save_ai_failure(
                        conn, batch, error, settings, lane=lane, job_id=job_id
                    )
                    reports.append(
                        AIBatchReport(
                            chat_id=batch.chat_id,
                            chat_title=batch.chat_title,
                            message_count=len(batch.messages),
                            summary="",
                            model_items=[],
                            save_result=AISaveResult(),
                            error=f"{type(error).__name__}: {error}",
                            lane=lane,
                        )
                    )
                if live is not None:
                    live.update(
                        render_ai_progress(
                            len(jobs),
                            completed,
                            total_messages,
                            processed,
                            saved,
                            errors,
                            started,
                            settings,
                            lane=lane,
                        )
                    )
                if on_progress:
                    on_progress()
    except (KeyboardInterrupt, asyncio.CancelledError):
        for job_id, _ in jobs:
            release_ai_job(conn, job_id)
        if render_console:
            console.print(
                notice(
                    f"{lane.title()} analysis stopped safely. Unfinished jobs remain pending.",
                    title="Analysis stopped",
                    tone="warning",
                )
            )
        return

    if not render_console:
        return
    show_ai_run_report(reports, console, max_batches=settings.ai_report_batches)
    remaining, total_items, open_actions = get_ai_counts(conn, settings)
    console.print(
        notice(
            f"{processed:,} messages analyzed and {saved:,} validated memory items saved.",
            title=f"{lane.title()} analysis complete",
            tone="warning" if errors else "success",
        )
    )
    console.print(
        metric_strip(
            [
                ("Requests", router.requests, "accent"),
                (
                    "Fallbacks",
                    router.fallbacks,
                    "warning" if router.fallbacks else "muted",
                ),
                ("Failed jobs", errors, "danger" if errors else "success"),
                ("Remaining", remaining, "warning" if remaining else "success"),
            ]
        )
    )
    console.print(
        safe_text(
            f"Provider-chain failures: {router.errors} · queued this run: {created} · "
            f"open actions: {open_actions:,} · total memory items: {total_items:,}",
            style="dim",
        )
    )
