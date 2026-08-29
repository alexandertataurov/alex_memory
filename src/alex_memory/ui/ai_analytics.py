"""Terminal rendering for read-only AI analytics."""

from __future__ import annotations

import sqlite3

from rich.console import Console

from ..ai.analytics import (
    fetch_ai_analytics,
    fetch_ai_request_monitor,
    fetch_ai_router_diagnostics,
)
from ..ai.repository import get_ai_counts, get_ai_text_counts
from ..ai.routing import AIWorkload, ModelRegistry
from ..config import Settings
from .components import AppPanel as Panel
from .components import DataTable as Table
from .components import metric_strip, safe_text, screen_header, status_text


def show_ai_request_monitor(
    conn: sqlite3.Connection, settings: Settings, console: Console
) -> None:
    """Render the current route, pace, jobs, and latest provider outcomes."""
    totals, provider_totals, active_jobs, recent_requests = fetch_ai_request_monitor(
        conn
    )
    (
        pending,
        running,
        _failed,
        hourly_requests,
        hourly_messages,
        hourly_fallbacks,
        hourly_errors,
    ) = (int(value or 0) for value in totals)
    provider_counts = {
        str(provider): (int(count), int(fallbacks))
        for provider, count, fallbacks in provider_totals
    }
    gemini_direct, _ = provider_counts.get("gemini", (0, 0))
    groq_completed, _ = provider_counts.get("groq", (0, 0))
    candidates = ModelRegistry(settings).candidates(AIWorkload.CONTEXT_EXTRACTION)

    screen_header(
        console,
        "AI request monitor",
        "Live queue state, provider route, pacing, and recent request outcomes.",
    )
    console.print(
        metric_strip(
            [
                ("Queued", pending, "warning" if pending else "success"),
                ("Running", running, "accent" if running else "muted"),
                ("Requests · 1h", hourly_requests, "info"),
                (
                    "Fallbacks · 1h",
                    hourly_fallbacks,
                    "warning" if hourly_fallbacks else "success",
                ),
                (
                    "Errors · 1h",
                    hourly_errors,
                    "danger" if hourly_errors else "success",
                ),
            ]
        )
    )
    route = Table.grid(expand=True, padding=(0, 2))
    route.add_column(style="bold", width=16)
    route.add_column(ratio=1)
    route.add_row(
        "Routing mode",
        safe_text(f"{settings.ai_routing_mode} · {settings.ai_routing_override}"),
    )
    route.add_row(
        "Eligible routes",
        safe_text(
            " → ".join(
                f"{profile.provider} / {profile.model}" for profile in candidates
            )
            or "none"
        ),
    )
    route.add_row(
        "Last hour",
        safe_text(f"{hourly_messages:,} messages across {hourly_requests:,} requests"),
    )
    route.add_row(
        "Gemini · 1h",
        safe_text(
            f"{gemini_direct:,} direct · {hourly_fallbacks:,} quota/failure fallbacks"
        ),
    )
    route.add_row("Groq · 1h", safe_text(f"{groq_completed:,} completed"))
    usage, decisions = fetch_ai_router_diagnostics(conn)
    last_error_text = "—"
    if recent_requests:
        (
            _lane,
            _chat,
            _messages,
            _provider,
            _model,
            _fallback,
            error,
            _status,
            _completed_at,
            fallback_reason,
        ) = recent_requests[0]
        last_error_text = error or fallback_reason or "—"

    if active_jobs:
        lane, chat, messages, state, provider, model, attempts, _last_error = (
            active_jobs[0]
        )
        route.add_row(
            "Current job",
            safe_text(
                f"{lane} · {chat} · {messages} msgs · {state} · {provider} / {model or 'selecting'} · try {attempts}",
                120,
                single_line=True,
            ),
        )
    if decisions:
        (
            workload,
            priority,
            decision_provider,
            decision_model,
            outcome,
            reason,
            _error,
            _at,
        ) = decisions[0]
        route.add_row(
            "Latest decision",
            safe_text(
                f"{workload} / {priority} · {decision_provider or 'router'} / {decision_model or 'selecting'} · {outcome} · {reason or '—'}",
                120,
                single_line=True,
            ),
        )
    route.add_row("Last error", safe_text(last_error_text, 120, single_line=True))
    console.print(Panel(route, title="Current route", border_style="magenta"))

    quick_usage = Table(title="Quota snapshot", expand=False)
    quick_usage.add_column("Route", style="bold")
    quick_usage.add_column("Attempts", justify="right")
    quick_usage.add_column("Success", justify="right")
    quick_usage.add_column("Status")
    if usage:
        for (
            key,
            _provider,
            _model,
            attempts,
            successes,
            _estimated,
            _actual,
            _output,
            cooldown,
            last_error,
        ) in usage[:4]:
            quick_usage.add_row(
                safe_text(key, 18, single_line=True),
                str(attempts),
                str(successes),
                safe_text(cooldown or last_error or "—", 50, single_line=True),
            )
    else:
        quick_usage.add_row("—", "0", "0", "No quota data yet")
    console.print(quick_usage)
    console.print()


def show_ai_analytics(
    conn: sqlite3.Connection, settings: Settings, console: Console
) -> None:
    provider_rows, item_rows, error_rows = fetch_ai_analytics(conn)
    _, total_items, open_actions = get_ai_counts(conn, settings)
    _, analyzed, backlog = get_ai_text_counts(conn, settings)
    screen_header(
        console,
        "AI analytics",
        "Provider reliability, extraction quality, and memory composition.",
    )
    console.print(
        metric_strip(
            [
                ("Backlog", backlog, "warning" if backlog else "success"),
                ("Analyzed", analyzed, "accent"),
                ("Memory", total_items, "info"),
                ("Open actions", open_actions, "danger" if open_actions else "success"),
            ]
        )
    )
    provider_table = Table(title="Provider & extraction quality", expand=True)
    for column in (
        "Lane",
        "Provider",
        "Batches",
        "Messages",
        "Items",
        "Saved",
        "Rejected",
        "Fallbacks",
        "Failed",
    ):
        provider_table.add_column(
            column, justify="right" if column not in {"Lane", "Provider"} else "left"
        )
    for row in provider_rows:
        lane, provider, *counts = row
        provider_table.add_row(
            safe_text(lane, single_line=True),
            safe_text(provider, single_line=True),
            *(f"{count:,}" for count in counts),
        )
    console.print(provider_table)
    if item_rows:
        memory_table = Table(title="Memory composition", expand=True)
        memory_table.add_column("Kind")
        memory_table.add_column("Status")
        memory_table.add_column("Count", justify="right")
        for kind, status, count in item_rows[:16]:
            memory_table.add_row(
                safe_text(kind, single_line=True), status_text(status), f"{count:,}"
            )
        console.print(memory_table)
    if error_rows:
        error_table = Table(title="Recent failed batches", expand=True)
        error_table.add_column("Lane", width=8)
        error_table.add_column("Provider", width=10)
        error_table.add_column("When", width=25)
        error_table.add_column("Error", ratio=3)
        for lane, provider, error, completed_at in error_rows:
            error_table.add_row(
                safe_text(lane, 8, single_line=True),
                safe_text(provider, 10, single_line=True),
                safe_text(completed_at or "—", 25, single_line=True),
                safe_text(error, 180, single_line=True),
            )
        console.print(error_table)
    console.print()
