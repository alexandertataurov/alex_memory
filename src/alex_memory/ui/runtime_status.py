"""Terminal rendering for the authoritative runtime-status snapshot."""

from __future__ import annotations

from rich.console import Console

from ..runtime_status import RuntimeStatus
from ..utils import human_time
from .components import AppPanel as Panel
from .components import DataTable as Table
from .components import metric_strip, safe_text, screen_header


def show_status(status: RuntimeStatus, console: Console) -> None:
    """Render the single runtime-status snapshot used by the home screen."""
    screen_header(
        console,
        "System status",
        "Live state, bounded work, freshness, and data-quality observations.",
    )
    console.print(
        metric_strip(
            [
                (
                    "Runtime",
                    status.phase,
                    "danger" if status.phase == "FAILED" else "accent",
                ),
                (
                    "AI backlog",
                    status.ai.pending_jobs,
                    "warning" if status.ai.pending_jobs else "muted",
                ),
                (
                    "Context dirty",
                    status.context.dirty_count,
                    "warning" if status.context.dirty_count else "success",
                ),
                (
                    "Reviews",
                    status.review_count,
                    "warning" if status.review_count else "success",
                ),
            ]
        )
    )

    telegram_table = Table(title="Telegram and writer")
    telegram_table.add_column("Metric")
    telegram_table.add_column("Value", justify="right")
    telegram_table.add_row(
        "Connection", "connected" if status.telegram.connected else "offline"
    )
    telegram_table.add_row(
        "Archive lag",
        human_time(status.telegram.archive_lag_seconds)
        if status.telegram.archive_lag_seconds is not None
        else "—",
    )
    telegram_table.add_row("Writer", safe_text(status.writer.state))
    telegram_table.add_row("Writer queue", f"{status.telegram.queue_size:,}")
    telegram_table.add_row(
        "Last reconciliation", safe_text(status.telegram.last_reconciliation_at or "—")
    )
    telegram_table.add_row(
        "Retry",
        "supervised retry scheduled"
        if status.telegram.retry_scheduled
        else "not scheduled",
    )
    console.print(telegram_table)

    ai_table = Table(title="AI and context")
    ai_table.add_column("Metric")
    ai_table.add_column("Value", justify="right")
    ai_table.add_row(
        "Jobs",
        f"{status.ai.pending_jobs:,} pending · {status.ai.running_jobs:,} running · {status.ai.failed_jobs:,} failed",
    )
    ai_table.add_row("Current route", safe_text(status.ai.current_route or "—"))
    ai_table.add_row(
        "Quota", "cooldown active" if status.ai.quota_limited else "available"
    )
    ai_table.add_row(
        "History coverage",
        f"{status.history['semantic']:,}/{status.history['eligible']:,} semantic · "
        f"{status.history['canonicalized']:,} canonical · "
        f"{status.history['context_integrated']:,} integrated · "
        f"{status.history['current_enough']:,} current-enough",
    )
    ai_table.add_row("Context freshness", safe_text(status.context.freshness))
    ai_table.add_row(
        "Context work",
        f"{status.context.raw_pending:,} raw · {status.context.semantic_pending:,} semantic · {status.context.materialization_dirty:,} dirty",
    )
    ai_table.add_row("Context dirty", f"{status.context.dirty_count:,}")
    ai_table.add_row(
        "Oldest dirty",
        human_time(status.context.oldest_dirty_age_seconds)
        if status.context.oldest_dirty_age_seconds is not None
        else "—",
    )
    console.print(ai_table)

    quality = status.quality
    quality_table = Table(title="Data quality")
    quality_table.add_column("Metric")
    quality_table.add_column("Value", justify="right")
    quality_table.add_row(
        "FTS coverage",
        "not available"
        if quality.fts_healthy is None
        else ("healthy" if quality.fts_healthy else "drift detected"),
    )
    quality_table.add_row(
        "Task-project links",
        f"{quality.task_project_coverage:.1%} · {quality.task_project_linked:,}/{quality.task_total:,}",
    )
    quality_table.add_row("Current actionable tasks", f"{quality.actionable_tasks:,}")
    quality_table.add_row(
        "Project health valid",
        f"{quality.project_health_validity:.1%} · {quality.valid_projects:,}/{quality.project_total:,}",
    )
    quality_table.add_row(
        "Classification unknown",
        f"{quality.classification_unknown_rate:.1%} · {quality.unknown_classifications:,}/{quality.classified_messages:,}",
    )
    quality_table.add_row(
        "Source contact identity",
        f"{quality.source_identity_coverage:.1%} · {quality.source_identified_chats:,}/{quality.direct_chats:,}",
    )
    quality_table.add_row("Context freshness", safe_text(status.context.freshness))
    quality_table.add_row(
        "Graph maintenance",
        f"{int(status.graph.get('graph_link_candidates', 0)):,} links pending · {int(status.graph.get('stale_analyses', 0)):,} stale analyses",
    )
    console.print(quality_table)
    if status.recent_errors:
        console.print(
            Panel(
                safe_text("\n".join(status.recent_errors), 500),
                title="Recent errors",
                border_style="red",
                padding=(0, 1),
            )
        )
    console.print()
