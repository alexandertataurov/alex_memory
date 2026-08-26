from __future__ import annotations

import asyncio

from telethon.errors import FloodWaitError

from ..config import Settings
from ..models import DialogInfo, SyncState
from ..utils import sleep_interruptible, utc_now
from .normalize import normalize_message
from .inventory import dialog_last_message_id
from .policy import (
    SyncPlan,
    plan_existing_chat,
    plan_group_bootstrap,
    plan_personal_bootstrap,
)


message_to_row = normalize_message  # backwards-compatible import name


async def get_group_message_count(
    client,
    info: DialogInfo,
    state: SyncState,
    worker_id: int,
    stop_event: asyncio.Event,
) -> int | None:
    while not stop_event.is_set():
        try:
            result = await client.get_messages(info.dialog.entity, limit=0)
            return int(result.total or 0)
        except FloodWaitError as error:
            state.flood_waits += 1
            set_worker_status(state, worker_id, f"count wait {error.seconds}s")
            await sleep_interruptible(error.seconds, stop_event)
        except Exception as error:
            state.add_error(f"{info.title[:40]} count: {type(error).__name__}: {error}")
            return None
    return None


async def determine_sync_plan(
    client,
    info: DialogInfo,
    last_saved_id: int,
    saved_state: dict,
    state: SyncState,
    worker_id: int,
    stop_event: asyncio.Event,
    settings: Settings,
) -> SyncPlan | None:
    if saved_state.get("bootstrap_complete"):
        state.incremental_syncs += 1
        return plan_existing_chat(
            last_saved_id,
            saved_state.get("bootstrap_mode"),
        )

    if info.chat_type == "user":
        state.full_bootstraps += 1
        return plan_personal_bootstrap(last_saved_id)

    set_worker_status(state, worker_id, "counting")
    total = await get_group_message_count(
        client,
        info,
        state,
        worker_id,
        stop_event,
    )

    if stop_event.is_set():
        return None

    # Fail safe: an unknown group size is treated as large.
    if total is None:
        total = settings.group_full_threshold + 1

    plan = plan_group_bootstrap(total, last_saved_id, settings)
    if plan.mode == "group_recent":
        state.recent_bootstraps += 1
    else:
        state.full_bootstraps += 1
    return plan


async def sync_streaming_plan(
    client,
    info: DialogInfo,
    plan: SyncPlan,
    write_queue: asyncio.Queue,
    state: SyncState,
    worker_id: int,
    stop_event: asyncio.Event,
    settings: Settings,
) -> bool:
    resume_id = plan.min_id
    worker_count = 0

    while not stop_event.is_set():
        try:
            async for message in client.iter_messages(
                info.dialog.entity,
                min_id=resume_id,
                reverse=True,
                # Telethon otherwise sleeps 1 second between history pages
                # when the limit is unbounded. FloodWait handling below is the
                # authoritative server-side limiter.
                wait_time=settings.tg_message_request_delay,
            ):
                if stop_event.is_set():
                    return False

                await write_queue.put(
                    ("message", message_to_row(info.chat_id, message))
                )

                worker_count += 1
                state.messages_fetched += 1
                resume_id = max(resume_id, int(message.id))
                set_worker_progress(
                    state,
                    worker_id,
                    info,
                    worker_count,
                    message.id,
                    plan.status,
                )

            return not stop_event.is_set()

        except FloodWaitError as error:
            state.flood_waits += 1
            set_worker_status(state, worker_id, f"wait {error.seconds}s")
            await sleep_interruptible(error.seconds, stop_event)
            set_worker_status(state, worker_id, plan.status)

        except Exception as error:
            state.add_error(f"{info.title[:40]}: {type(error).__name__}: {error}")
            set_worker_status(state, worker_id, type(error).__name__)
            return False

    return False


async def sync_recent_group(
    client,
    info: DialogInfo,
    plan: SyncPlan,
    write_queue: asyncio.Queue,
    state: SyncState,
    worker_id: int,
    stop_event: asyncio.Event,
) -> bool:
    recent_messages = None

    while not stop_event.is_set():
        try:
            recent_messages = await client.get_messages(
                info.dialog.entity,
                limit=plan.limit,
            )
            break
        except FloodWaitError as error:
            state.flood_waits += 1
            set_worker_status(state, worker_id, f"wait {error.seconds}s")
            await sleep_interruptible(error.seconds, stop_event)
        except Exception as error:
            state.add_error(f"{info.title[:40]}: {type(error).__name__}: {error}")
            set_worker_status(state, worker_id, type(error).__name__)
            return False

    if recent_messages is None or stop_event.is_set():
        return False

    ordered = sorted(list(recent_messages), key=lambda m: int(m.id))
    for count, message in enumerate(ordered, start=1):
        if stop_event.is_set():
            return False

        await write_queue.put(("message", message_to_row(info.chat_id, message)))
        state.messages_fetched += 1
        set_worker_progress(
            state,
            worker_id,
            info,
            count,
            message.id,
            plan.status,
        )

    return True


async def sync_one_chat(
    client,
    info: DialogInfo,
    write_queue: asyncio.Queue,
    last_ids: dict[int, int],
    sync_states: dict[int, dict],
    state: SyncState,
    worker_id: int,
    stop_event: asyncio.Event,
    settings: Settings,
) -> None:
    state.chats_started += 1

    await write_queue.put(
        (
            "chat",
            (
                info.chat_id,
                info.title,
                info.username,
                info.chat_type,
                int(info.is_bot),
                utc_now(),
            ),
        )
    )

    last_saved_id = int(last_ids.get(info.chat_id, 0))
    saved_state = sync_states.get(info.chat_id, {})

    state.active[worker_id] = {
        "chat": info.title,
        "count": 0,
        "last_id": last_saved_id,
        "status": "planning",
    }

    # A dialog's latest message ID arrives with the inventory. For an already
    # bootstrapped chat, this avoids even one `iter_messages` RPC when there is
    # nothing new — the common case on routine startup/reconciliation.
    latest_id = dialog_last_message_id(info)
    if (
        saved_state.get("bootstrap_complete")
        and latest_id is not None
        and latest_id <= last_saved_id
    ):
        set_worker_status(state, worker_id, "up to date")
        state.chats_completed += 1
        return

    plan = await determine_sync_plan(
        client,
        info,
        last_saved_id,
        saved_state,
        state,
        worker_id,
        stop_event,
        settings,
    )
    if plan is None:
        return

    set_worker_status(state, worker_id, plan.status)

    if plan.mode == "group_recent":
        completed = await sync_recent_group(
            client,
            info,
            plan,
            write_queue,
            state,
            worker_id,
            stop_event,
        )
    else:
        completed = await sync_streaming_plan(
            client,
            info,
            plan,
            write_queue,
            state,
            worker_id,
            stop_event,
            settings,
        )

    if completed:
        await write_queue.put(
            (
                "sync_state",
                (
                    info.chat_id,
                    1,
                    plan.mode,
                    plan.group_total or saved_state.get("group_total"),
                    utc_now(),
                    utc_now(),
                ),
            )
        )

    state.chats_completed += 1


def set_worker_status(state: SyncState, worker_id: int, status: str) -> None:
    if worker_id in state.active:
        state.active[worker_id]["status"] = status


def set_worker_progress(
    state: SyncState,
    worker_id: int,
    info: DialogInfo,
    count: int,
    last_id: int,
    status: str,
) -> None:
    state.active[worker_id] = {
        "chat": info.title,
        "count": count,
        "last_id": last_id,
        "status": status,
    }
