from __future__ import annotations

from html import escape
import re

from ..config import Settings
from ..models import AIBatch, AIMessage


_ONE_TIME_CODE = re.compile(
    r"(?ix)\b(?:login|verification|security|confirm(?:ation)?|otp|code|код)"
    r"\s*(?:is|:|=|\#|-)?\s*(\d[\d\s-]{2,10}\d)\b"
)


def redact_sensitive_text(text: str) -> str:
    """Keep messages useful for context without sending one-time codes to AI."""
    return _ONE_TIME_CODE.sub(
        lambda match: match.group(0).replace(match.group(1), "[REDACTED]"), text
    )


def format_ai_message(message: AIMessage, settings: Settings) -> str:
    author = _author(message)
    text = _safe_text(message.text, settings)

    return (
        f"<MESSAGE chat_id={message.chat_id} "
        f"message_id={message.message_id} "
        f"date={message.date or '-'} "
        f"author={author}>\n"
        f"{text}\n"
        "</MESSAGE>"
    )


def format_ai_context_message(message: AIMessage, settings: Settings) -> str:
    """Format prior context without source IDs that the model could cite."""
    return (
        f"<PRIOR_CONTEXT date={message.date or '-'} author={_author(message)}>\n"
        f"{_safe_text(message.text, settings)}\n"
        "</PRIOR_CONTEXT>"
    )


def _author(message: AIMessage) -> str:
    if message.is_outgoing:
        return "ME"
    if message.sender_id is not None:
        return f"SENDER:{message.sender_id}"
    return "OTHER"


def _safe_text(text: str, settings: Settings) -> str:
    # Telegram text is untrusted input. Escaping prevents a message from
    # closing its enclosing tag and impersonating metadata in the prompt.
    text = escape(redact_sensitive_text(text.strip()), quote=False)
    if len(text) > settings.ai_max_message_chars:
        text = text[: settings.ai_max_message_chars] + "\n[TRUNCATED]"
    return text


def build_ai_batches(
    messages: list[AIMessage],
    settings: Settings,
) -> list[AIBatch]:
    by_chat: dict[int, list[AIMessage]] = {}
    chat_order: list[int] = []

    for message in messages:
        if message.chat_id not in by_chat:
            by_chat[message.chat_id] = []
            chat_order.append(message.chat_id)
        by_chat[message.chat_id].append(message)

    batches: list[AIBatch] = []

    for chat_id in chat_order:
        chat_messages = sorted(
            by_chat[chat_id],
            key=lambda m: (m.date or "", m.message_id),
        )
        batches.extend(_build_chat_batches(chat_id, chat_messages, settings))

    return batches


def _build_chat_batches(
    chat_id: int,
    messages: list[AIMessage],
    settings: Settings,
) -> list[AIBatch]:
    batches: list[AIBatch] = []
    current: list[AIMessage] = []
    title = messages[0].chat_title
    chat_type = messages[0].chat_type
    prefix = (
        f"CHAT TITLE: {escape(title, quote=False)}\n"
        f"CHAT TYPE: {chat_type}\n"
        f"CHAT ID: {chat_id}\n\n"
        "Analyze this message window and return only the structured result.\n\n"
    )
    prompt_overhead = len(prefix)
    current_chars = prompt_overhead

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return

        body = "\n\n".join(format_ai_message(message, settings) for message in current)
        prompt = prefix + body

        batches.append(
            AIBatch(
                chat_id=chat_id,
                chat_title=title,
                messages=current,
                prompt=prompt,
            )
        )
        current = []
        current_chars = prompt_overhead

    for message in messages:
        formatted = format_ai_message(message, settings)
        msg_chars = len(formatted)

        if current and (
            len(current) >= settings.ai_batch_messages
            or current_chars + msg_chars > settings.ai_batch_chars
        ):
            flush()

        # A single message can exceed the target after tags are included. It
        # still needs a batch of its own, but never makes following messages
        # overflow it.
        current.append(message)
        current_chars += msg_chars

    flush()
    return batches
