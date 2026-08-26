from __future__ import annotations

from rich.console import Console
from rich.live import Live
from rich.text import Text

from ..models import DialogInfo
from ..ui.components import AppPanel as Panel
from ..ui.components import DataTable as Table
from ..ui.components import safe_text


def dialog_type(dialog) -> str:
    # Megagroups can be channel entities internally. is_group wins.
    if dialog.is_user:
        return "user"
    if dialog.is_group:
        return "group"
    if dialog.is_channel:
        return "channel"
    return "other"


def dialog_last_date(dialog) -> str | None:
    message = getattr(dialog, "message", None)
    dt = getattr(message, "date", None)
    return dt.isoformat() if dt else None


def dialog_last_message_id(info: DialogInfo) -> int | None:
    """Use the dialog inventory as a zero-request incremental fast path."""
    message = getattr(info.dialog, "message", None)
    message_id = getattr(message, "id", None)
    try:
        return int(message_id) if message_id is not None else None
    except (TypeError, ValueError):
        return None


async def load_dialog_inventory(client, console: Console) -> list[DialogInfo]:
    dialogs: list[DialogInfo] = []
    counts = {"user": 0, "group": 0, "channel": 0, "other": 0}

    with Live(
        Panel(
            Text("● Loading Telegram dialogs…", style="cyan"),
            title="Dialog inventory",
        ),
        console=console,
        refresh_per_second=8,
        transient=True,
    ) as live:
        async for dialog in client.iter_dialogs(
            limit=None,
            ignore_migrated=True,
        ):
            title = dialog.name or str(dialog.id)
            kind = dialog_type(dialog)
            counts[kind] += 1

            dialogs.append(
                DialogInfo(
                    dialog=dialog,
                    chat_id=int(dialog.id),
                    title=title,
                    username=getattr(dialog.entity, "username", None),
                    chat_type=kind,
                    is_bot=bool(getattr(dialog.entity, "bot", False)),
                    last_date=dialog_last_date(dialog),
                )
            )

            progress = Table.grid(expand=True, padding=(0, 1))
            progress.add_column(justify="center", ratio=1)
            progress.add_column(justify="center", ratio=1)
            progress.add_column(justify="center", ratio=1)
            progress.add_column(justify="center", ratio=1)
            progress.add_row(
                Text(f"{len(dialogs):,}\nDialogs", style="bold bright_cyan"),
                Text(f"{counts['user']:,}\nPersonal", style="green"),
                Text(f"{counts['group']:,}\nGroups", style="cyan"),
                Text(f"{counts['channel']:,}\nChannels", style="yellow"),
            )
            latest = safe_text(title, 70, single_line=True)
            latest.stylize("dim")
            body = Table.grid(expand=True)
            body.add_row(progress)
            body.add_row(latest)
            live.update(
                Panel(
                    body,
                    title="Dialog inventory",
                    border_style="cyan",
                )
            )

    return dialogs


async def collect_dialog_inventory(client) -> list[DialogInfo]:
    """Silent inventory collection for background reconciliation."""
    dialogs: list[DialogInfo] = []
    async for dialog in client.iter_dialogs(limit=None, ignore_migrated=True):
        dialogs.append(
            DialogInfo(
                dialog=dialog,
                chat_id=int(dialog.id),
                title=dialog.name or str(dialog.id),
                username=getattr(dialog.entity, "username", None),
                chat_type=dialog_type(dialog),
                is_bot=bool(getattr(dialog.entity, "bot", False)),
                last_date=dialog_last_date(dialog),
            )
        )
    return dialogs
