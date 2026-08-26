"""Shared Telegram-to-SQLite normalization for history and live updates."""

from __future__ import annotations

from ..utils import utc_now


def normalize_message(chat_id: int, message) -> tuple:
    reply_to = getattr(message, "reply_to", None)
    reply_to_id = getattr(reply_to, "reply_to_msg_id", None) if reply_to else None
    forwarded = getattr(message, "fwd_from", None)
    forward_source = None
    if forwarded is not None:
        forward_source = (
            getattr(forwarded, "from_name", None)
            or str(getattr(forwarded, "from_id", "") or "")
            or getattr(forwarded, "channel_post", None)
        )
    return (
        int(chat_id),
        int(message.id),
        getattr(message, "sender_id", None),
        message.date.isoformat() if getattr(message, "date", None) else None,
        getattr(message, "raw_text", None) or "",
        reply_to_id,
        int(bool(getattr(message, "out", False))),
        int(getattr(message, "media", None) is not None),
        int(forwarded is not None),
        str(forward_source) if forward_source else None,
    )


def normalize_chat(
    chat_id: int, entity, *, fallback_title: str | None = None, event=None
) -> tuple | None:
    if entity is None:
        return None
    is_group = bool(
        getattr(entity, "megagroup", False)
        or getattr(entity, "gigagroup", False)
        or getattr(event, "is_group", False)
    )
    is_user = bool(
        getattr(entity, "first_name", None) is not None
        or (hasattr(entity, "bot") and not hasattr(entity, "title"))
    )
    if is_group:
        chat_type = "group"
        title = getattr(entity, "title", None)
    elif is_user:
        chat_type = "user"
        title = " ".join(
            part
            for part in (
                getattr(entity, "first_name", None),
                getattr(entity, "last_name", None),
            )
            if part
        ) or getattr(entity, "username", None)
    else:
        # Broadcast channels remain excluded by the existing policy.
        chat_type = (
            "channel"
            if hasattr(entity, "broadcast") or getattr(event, "is_channel", False)
            else "other"
        )
        title = getattr(entity, "title", None)
    return (
        int(chat_id),
        title or fallback_title or str(chat_id),
        getattr(entity, "username", None),
        chat_type,
        int(bool(getattr(entity, "bot", False))),
        utc_now(),
    )


def is_archive_eligible(chat_row: tuple | None) -> bool:
    return bool(chat_row and chat_row[3] in {"user", "group"})
