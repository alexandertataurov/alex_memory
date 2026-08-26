from __future__ import annotations

import time

from rich.console import Console, Group
from rich.text import Text

from ..config import Settings
from ..models import AIBatchReport
from ..utils import human_time
from .components import AppPanel as Panel
from .components import DataTable as Table
from .components import notice, progress_meter, safe_text, screen_header, status_text


def render_ai_progress(
    total_batches: int,
    completed_batches: int,
    total_messages: int,
    processed_messages: int,
    extracted_items: int,
    errors: int,
    started: float,
    settings: Settings,
    lane: str = "daily",
) -> Panel:
    table = Table.grid(expand=True, padding=(0, 2))
    table.add_column(style="bold", width=18)
    table.add_column(ratio=1)

    primary_model = (
        settings.gemini_primary_model
        if settings.ai_primary_provider == "gemini"
        else settings.groq_model
    )
    table.add_row("Lane", safe_text(lane.title()))
    table.add_row(
        "Provider",
        safe_text(
            f"{settings.ai_primary_provider} / {primary_model}  ·  "
            f"fallback {settings.ai_fallback_provider}"
        ),
    )
    table.add_row("Batches", progress_meter(completed_batches, total_batches))
    table.add_row("Messages", progress_meter(processed_messages, total_messages))
    table.add_row("New memory items", f"{extracted_items:,}")
    table.add_row("Failed batches", status_text("error") if errors else Text("0"))
    table.add_row("Elapsed", human_time(time.monotonic() - started))

    return Panel(
        table,
        title=f"AI analysis · {lane.title()}",
        border_style="red" if errors else "magenta",
        padding=(1, 2),
    )


def show_ai_run_report(
    reports: list[AIBatchReport],
    console: Console,
    max_batches: int = 20,
) -> None:
    if not reports:
        return

    screen_header(
        console,
        "AI analysis report",
        "Returned / saved / rejected item counts remain source-backed diagnostics.",
    )

    # Prefer batches that produced items/rejections, then fill with summaries.
    important = [
        r
        for r in reports
        if r.error
        or r.model_items
        or r.save_result.rejected
        or r.save_result.duplicates
    ]
    ordinary = [r for r in reports if r not in important]
    shown = (important + ordinary)[:max_batches]

    table = Table(
        title=f"AI batch results — showing {len(shown)}/{len(reports)}",
        expand=True,
    )
    table.add_column("Chat", ratio=2, no_wrap=True)
    table.add_column("Msgs", justify="right", width=5)
    table.add_column("Provider", width=13, no_wrap=True)
    table.add_column("Items", justify="right", width=9)
    table.add_column("Summary", ratio=5)

    for report in shown:
        summary = report.error or report.summary or "(empty summary)"
        provider = report.provider
        if report.fallback_used:
            provider += "*"
        item_counts = (
            "ERR"
            if report.error
            else f"{len(report.model_items)}/{report.save_result.inserted}/{report.save_result.rejected}"
        )
        table.add_row(
            safe_text(report.chat_title, 45, single_line=True),
            str(report.message_count),
            safe_text(provider, 13, single_line=True),
            status_text("error") if report.error else safe_text(item_counts),
            safe_text(summary, 120, single_line=True),
        )

    console.print(table)

    fallback_lines = [
        f"{report.chat_title}: {report.provider_note}"
        for report in reports
        if report.fallback_used and report.provider_note
    ]
    if fallback_lines:
        console.print(
            Panel(
                Group(
                    *(
                        safe_text(line, 300, single_line=True)
                        for line in fallback_lines[:10]
                    )
                ),
                title="Fallbacks used",
                subtitle="Primary-provider reason",
                border_style="yellow",
            )
        )

    returned_items = [
        (report, item)
        for report in reports
        if not report.error
        for item in report.model_items
    ]

    if returned_items:
        items_table = Table(
            title=f"New memory returned this run ({len(returned_items)})",
            expand=True,
        )
        items_table.add_column("Kind", width=15)
        items_table.add_column("Status", width=13)
        items_table.add_column("Title", ratio=3)
        items_table.add_column("Chat", ratio=1)
        items_table.add_column("Source", justify="right", width=10)

        shown_items = returned_items[:25]
        for report, item in shown_items:
            items_table.add_row(
                safe_text(item.get("kind", "?"), 15, single_line=True),
                status_text(item.get("status", "?")),
                safe_text(item.get("title", ""), 100, single_line=True),
                safe_text(report.chat_title, 35, single_line=True),
                safe_text(item.get("source_message_id", "-")),
            )

        console.print(items_table)
        if len(returned_items) > len(shown_items):
            console.print(
                f"[dim]Showing {len(shown_items)}/{len(returned_items)} findings. "
                "Use AI findings / tasks for the complete list.[/dim]"
            )
    else:
        successful_reports = [r for r in reports if not r.error]
        if successful_reports:
            console.print(
                notice(
                    "Successful batches returned no actionable memory. This is normal "
                    "for non-actionable conversations.",
                    title="No new memory",
                    tone="info",
                )
            )
        else:
            console.print(
                notice(
                    "No AI batch completed successfully. Review the errors above.",
                    title="Analysis failed",
                    tone="danger",
                )
            )

    rejection_lines: list[str] = []
    for report in reports:
        for reason in report.save_result.rejection_reasons:
            rejection_lines.append(f"{report.chat_title}: {reason}")

    if rejection_lines:
        console.print(
            Panel(
                Group(
                    *(
                        safe_text(line, 300, single_line=True)
                        for line in rejection_lines[:30]
                    )
                ),
                title="Rejected AI items",
                subtitle="Validation diagnostics",
                border_style="red",
            )
        )

    console.print()
