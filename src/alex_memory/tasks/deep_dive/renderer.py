from __future__ import annotations

from rich.console import Console, Group
from rich.text import Text

from ...ui.components import AppPanel as Panel
from ...ui.components import DataTable as Table
from ...ui.components import safe_text, screen_header
from .models import TaskDeepDiveReport


def render_report(report: TaskDeepDiveReport, console: Console) -> None:
    """Render a task investigation without interpreting source text as Rich markup."""
    task = report.task
    screen_header(
        console,
        f"Task Deep Dive #{task['task_id']}",
        "Source-backed investigation; unknowns and recommendations remain separate from facts.",
    )
    console.print(
        Panel(
            safe_text(report.executive_summary),
            title=safe_text(task["title"], 120, single_line=True),
            border_style="cyan",
        )
    )
    current = Text("Current state  ", style="bold")
    current.append(" · ".join(report.current_state))
    console.print(current)
    if report.origin:
        origin = Text("Origin  ", style="bold")
        origin.append(" ".join(report.origin))
        console.print(origin)
    if report.known_facts:
        console.print(Text("Known facts", style="bold"))
        console.print(
            Group(*(safe_text(f"• {item}", 600) for item in report.known_facts[:12]))
        )
    if report.unknowns:
        console.print(Text("Unknowns", style="bold yellow"))
        console.print(Group(*(safe_text(f"• {item}", 600) for item in report.unknowns)))
    if report.open_loops:
        console.print(Text("Open loops", style="bold"))
        console.print(
            Group(*(safe_text(f"• {item}", 600) for item in report.open_loops[:12]))
        )
    table = Table(
        title=f"Evidence and timeline — session {report.session_id}", expand=True
    )
    table.add_column("ID", width=18)
    table.add_column("When", width=20)
    table.add_column("Source", width=15)
    table.add_column("Evidence", ratio=4)
    for evidence in report.timeline[:40]:
        source = (
            f"chat {evidence.source_chat_id}/{evidence.source_message_id}"
            if evidence.source_chat_id is not None
            else evidence.evidence_type
        )
        identifier = Text(evidence.citation)
        if evidence.evidence_id in report.pinned_evidence_ids:
            identifier.append(" ★", style="yellow")
        table.add_row(
            identifier,
            safe_text(evidence.occurred_at or "—", 20, single_line=True),
            safe_text(source, 20, single_line=True),
            safe_text(evidence.text, 500, single_line=True),
        )
    console.print(table)
    console.print(
        safe_text(
            f"Concepts: {', '.join(report.concepts[:12])}. Diagnostics: {report.diagnostics}",
            style="dim",
        )
    )
