"""Telethon event adapters. Persistence is intentionally delegated to a queue."""

from __future__ import annotations

from telethon import events

from ..utils import utc_now
from .normalize import is_archive_eligible, normalize_chat, normalize_message


class TelegramEventListener:
    def __init__(self, client, write_queue, state):
        self.client, self.write_queue, self.state = client, write_queue, state

    def install(self) -> None:
        self.client.add_event_handler(self.on_new_message, events.NewMessage())
        self.client.add_event_handler(self.on_message_edited, events.MessageEdited())
        self.client.add_event_handler(self.on_message_deleted, events.MessageDeleted())

    def remove(self) -> None:
        self.client.remove_event_handler(self.on_new_message)
        self.client.remove_event_handler(self.on_message_edited)
        self.client.remove_event_handler(self.on_message_deleted)

    async def _chat(self, event):
        try:
            entity = await event.get_chat()
            return normalize_chat(event.chat_id, entity, event=event)
        except Exception as error:
            self.state.last_error = f"chat metadata: {type(error).__name__}: {error}"
            return None

    async def on_new_message(self, event) -> None:
        chat = await self._chat(event)
        if not is_archive_eligible(chat):
            return
        await self.write_queue.put(("chat", chat))
        await self.write_queue.put(
            ("message", normalize_message(event.chat_id, event.message))
        )
        self.state.messages_received += 1
        self.state.last_message_at = utc_now()

    async def on_message_edited(self, event) -> None:
        chat = await self._chat(event)
        if not is_archive_eligible(chat):
            return
        await self.write_queue.put(("chat", chat))
        await self.write_queue.put(
            (
                "message_edit",
                (
                    int(event.chat_id),
                    int(event.message.id),
                    event.message.raw_text or "",
                    utc_now(),
                ),
            )
        )
        self.state.edits_received += 1

    async def on_message_deleted(self, event) -> None:
        # Telegram may omit chat_id for some deletion updates. Never infer it.
        if event.chat_id is None:
            return
        for message_id in event.deleted_ids:
            await self.write_queue.put(
                ("message_delete", (int(event.chat_id), int(message_id), utc_now()))
            )
            self.state.deletions_received += 1
