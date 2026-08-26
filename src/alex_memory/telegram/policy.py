from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..models import DialogInfo


@dataclass(frozen=True, slots=True)
class SyncPlan:
    mode: str
    status: str
    limit: int | None = None
    min_id: int = 0
    group_total: int | None = None


def eligible_dialogs(dialogs: list[DialogInfo]) -> list[DialogInfo]:
    return [d for d in dialogs if d.chat_type in ("user", "group")]


def plan_existing_chat(
    last_saved_id: int,
    bootstrap_mode: str | None,
) -> SyncPlan:
    return SyncPlan(
        mode="incremental",
        status="incremental",
        min_id=last_saved_id,
    )


def plan_personal_bootstrap(last_saved_id: int) -> SyncPlan:
    return SyncPlan(
        mode="personal_full",
        status="personal/full",
        min_id=last_saved_id,
    )


def plan_group_bootstrap(
    group_total: int,
    last_saved_id: int,
    settings: Settings,
) -> SyncPlan:
    if group_total <= settings.group_full_threshold:
        return SyncPlan(
            mode="group_full",
            status=f"group/full {group_total:,}",
            min_id=last_saved_id,
            group_total=group_total,
        )

    return SyncPlan(
        mode="group_recent",
        status=(f"recent {settings.group_recent_limit:,}/{group_total:,}"),
        limit=settings.group_recent_limit,
        group_total=group_total,
    )
