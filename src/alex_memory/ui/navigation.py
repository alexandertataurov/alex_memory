"""Small, testable building blocks for the interactive terminal home screen."""

from __future__ import annotations

from dataclasses import dataclass

from rich.align import Align
from rich.console import Console, RenderableType
from rich.text import Text

from ..config import Settings
from ..runtime_status import RuntimeStatus
from ..utils import human_time
from .components import AppPanel as Panel
from .components import DataTable as Table
from .components import safe_text


@dataclass(frozen=True, slots=True)
class CommandSpec:
    name: str
    key: str
    number: str
    label: str
    section: str
    aliases: tuple[str, ...] = ()


COMMANDS = (
    CommandSpec("contacts", "p", "", "People", "People", ("people",)),
    CommandSpec("search", "s", "", "Search People", "People", ("search",)),
    CommandSpec("review", "r", "", "Review", "People", ("review",)),
    CommandSpec("diagnostics", "i", "", "System Status", "People", ("status",)),
    CommandSpec("quit", "q", "", "Quit", "People", ("quit", "exit")),
)

_COMMAND_LOOKUP = {
    alias: command.name
    for command in COMMANDS
    for alias in (command.key, command.number, *command.aliases)
}
_COMMAND_LOOKUP.update(
    {
        ":maintain": "maintain",
    }
)


def resolve_command(value: str) -> str | None:
    """Resolve memorable aliases while retaining every legacy menu number."""
    return _COMMAND_LOOKUP.get(value.strip().casefold())


def resolve_maintenance_command(value: str) -> str | None:
    """Keep recovery commands available without exposing them in normal navigation."""
    commands = {
        "sync": "sync",
        "resync_profiles": "resync_profiles",
        "full_refresh": "resync_profiles",
        "daily": "analyze_daily",
        "history": "analyze_history",
        "tasks": "tasks",
        "ask": "ask",
        "brief": "brief",
        "followups": "follow_ups",
        "projects": "projects",
        "graph": "context_graph",
        "policy": "chat_policy",
        "refresh": "refresh",
        "generate_brief": "generate_brief",
        "ai": "ai_diagnostics",
        "context": "context_diagnostics",
        "settings": "settings",
    }
    return commands.get(value.strip().casefold())


def show_app_header(settings: Settings, console: Console) -> None:
    title = Text("ALEX MEMORY", style="bold bright_cyan", justify="center")
    title.append("\nYour source-backed relationship memory", style="white")
    title.append(
        f"\nLocal-first  ·  Telegram connected on start  ·  {settings.app_timezone}",
        style="dim",
    )
    console.print(
        Panel(
            Align.center(title),
            border_style="bright_blue",
            padding=(1, 2),
        )
    )


def show_main_menu(
    console: Console,
    runtime_status: RuntimeStatus | None = None,
) -> None:
    if runtime_status is not None:
        console.print(_live_status_panel(runtime_status))
    body = Text("Find a person to understand the relationship.", style="bold white")
    body.append(
        "\nSearch by name, alias, Telegram account, company, project, or known context.",
        style="dim",
    )
    body.append("\n\nType / to search actions.", style="bright_cyan")
    console.print(
        Panel(
            body,
            title="People",
            subtitle="Relationship intelligence",
            border_style="cyan",
        )
    )


def _command_panel(section: str, subtitle: str, border_style: str) -> Panel:
    table = Table.grid(expand=True, padding=(0, 1))
    table.add_column(width=3, style="bold bright_cyan", no_wrap=True)
    table.add_column(ratio=1)
    table.add_column(width=4, style="dim", justify="right", no_wrap=True)
    for command in COMMANDS:
        if command.section == section:
            number = "" if command.number == command.key else command.number
            table.add_row(command.key, command.label, number)
    return Panel(
        table,
        title=section,
        subtitle=subtitle,
        border_style=border_style,
        padding=(0, 1),
    )


def _live_status_panel(status: RuntimeStatus) -> RenderableType:
    state = Text(status.phase, style=_phase_style(status.phase))
    values = Table.grid(expand=True, padding=(0, 1))
    values.add_column(no_wrap=True)
    values.add_column(justify="center", ratio=1)
    values.add_column(justify="center", ratio=1)
    values.add_column(justify="center", ratio=1)
    values.add_column(justify="right", ratio=2)
    values.add_row(
        state,
        safe_text(
            f"archive {human_time(status.telegram.archive_lag_seconds)} ago"
            if status.telegram.archive_lag_seconds is not None
            else "archive age —"
        ),
        safe_text(
            f"AI {status.ai.pending_jobs:,} queued / {status.ai.running_jobs:,} active"
        ),
        safe_text(
            f"writer {status.writer.state} · queue {status.telegram.queue_size:,}"
        ),
        safe_text(
            "supervised retry scheduled"
            if status.telegram.retry_scheduled
            else f"{status.telegram.messages_saved:,} saved · last sync {status.telegram.last_reconciliation_at or '—'}"
        ),
    )
    return Panel(values, border_style=_phase_border(status.phase))


def _phase_style(phase: str) -> str:
    return {
        "HEALTHY": "bold green",
        "STARTING": "bold cyan",
        "RETRYING": "bold yellow",
        "DEGRADED": "bold yellow",
        "FAILED": "bold red",
        "OFFLINE": "bold dim",
    }.get(phase, "bold yellow")


def _phase_border(phase: str) -> str:
    return {
        "HEALTHY": "green",
        "STARTING": "cyan",
        "RETRYING": "yellow",
        "DEGRADED": "yellow",
        "FAILED": "red",
        "OFFLINE": "dim",
    }.get(phase, "yellow")
