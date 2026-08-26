"""Shared visual language for Alex Memory's Rich terminal interface."""

from __future__ import annotations

from typing import Literal

from rich import box
from rich.console import Console, RenderableType
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

Tone = Literal["accent", "info", "success", "warning", "danger", "muted"]

TONE_STYLES: dict[Tone, str] = {
    "accent": "bright_cyan",
    "info": "bright_blue",
    "success": "green",
    "warning": "yellow",
    "danger": "red",
    "muted": "bright_black",
}


class AppPanel(Panel):
    """Panel with consistent spacing and title treatment."""

    def __init__(self, renderable: RenderableType, *args, **kwargs) -> None:
        kwargs.setdefault("border_style", TONE_STYLES["muted"])
        kwargs.setdefault("title_align", "left")
        kwargs.setdefault("padding", (1, 2))
        super().__init__(renderable, *args, **kwargs)


class DataTable(Table):
    """Data table with restrained borders and accessible headers."""

    def __init__(self, *args, **kwargs) -> None:
        kwargs.setdefault("box", box.SIMPLE_HEAD)
        kwargs.setdefault("border_style", TONE_STYLES["muted"])
        kwargs.setdefault("header_style", "bold bright_cyan")
        kwargs.setdefault("title_style", "bold white")
        kwargs.setdefault("title_justify", "left")
        kwargs.setdefault("padding", (0, 1))
        super().__init__(*args, **kwargs)


def safe_text(
    value: object,
    limit: int | None = None,
    *,
    style: str | None = None,
    single_line: bool = False,
) -> Text:
    """Render untrusted source/model text literally, never as Rich markup."""
    text = str(value if value is not None else "")
    if single_line:
        text = " ".join(text.split())
    if limit is not None and len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + "…"
    return Text(text, style=style or "")


def status_text(value: object) -> Text:
    label = str(value or "unknown")
    style = {
        "connected": "bold green",
        "complete": "bold green",
        "completed": "bold green",
        "done": "green",
        "open": "cyan",
        "running": "cyan",
        "pending": "cyan",
        "waiting": "yellow",
        "recovering": "bold yellow",
        "stopping": "bold yellow",
        "snoozed": "yellow",
        "failed": "red",
        "error": "red",
        "canceled": "dim",
        "cancelled": "dim",
        "idle": "dim",
    }.get(label.casefold(), "white")
    return Text(label.upper(), style=style)


def priority_text(value: object) -> Text:
    label = str(value or "normal")
    style = {
        "critical": "bold red",
        "high": "bold yellow",
        "normal": "cyan",
        "low": "dim",
    }.get(label.casefold(), "white")
    return Text(label.upper(), style=style)


def screen_header(console: Console, title: str, subtitle: str | None = None) -> None:
    console.print()
    console.print(
        Rule(safe_text(title, style="bold bright_cyan"), style="bright_black")
    )
    if subtitle:
        console.print(safe_text(subtitle, style="dim"))


def notice(
    message: object,
    *,
    title: str,
    tone: Tone = "info",
) -> AppPanel:
    return AppPanel(
        safe_text(message),
        title=title,
        border_style=TONE_STYLES[tone],
    )


def progress_meter(completed: int, total: int, width: int = 16) -> Text:
    safe_total = max(total, 0)
    safe_completed = max(0, min(completed, safe_total))
    fraction = safe_completed / safe_total if safe_total else 0
    filled = round(fraction * width)
    meter = Text()
    meter.append("█" * filled, style="bright_cyan")
    meter.append("░" * (width - filled), style="bright_black")
    meter.append(f"  {safe_completed:,}/{safe_total:,}", style="white")
    return meter


def metric_strip(metrics: list[tuple[str, object, Tone]]) -> AppPanel:
    grid = DataTable.grid(expand=True, padding=(0, 1))
    for _ in metrics:
        grid.add_column(justify="center", ratio=1)
    cells: list[Text] = []
    for label, value, tone in metrics:
        cell = Text(str(value), style=f"bold {TONE_STYLES[tone]}", justify="center")
        cell.append(f"\n{label}", style="dim")
        cells.append(cell)
    grid.add_row(*cells)
    return AppPanel(grid, padding=(0, 1))


def print_notice(
    console: Console,
    message: object,
    *,
    title: str,
    tone: Tone = "info",
) -> None:
    console.print()
    console.print(notice(message, title=title, tone=tone))
    console.print()
