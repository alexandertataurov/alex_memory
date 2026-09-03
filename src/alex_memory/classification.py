"""Low-cost, context-aware message classification.

Classification is intentionally separate from extraction: it gives every eligible
message a durable routing signal, while expensive semantic extraction remains
reserved for useful evidence.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from .models import AIMessage
from .context.segments import active_segment_project
from .utils import utc_now


CLASSIFICATION_VERSION = 2
_TOPIC_WORDS = {
    "banking",
    "documents",
    "payment",
    "invoice",
    "hedge",
    "hedging",
    "liquidity",
    "meeting",
    "contract",
    "fx",
}
_NOISE_RE = re.compile(r"^[\W_]+$", re.UNICODE)


@dataclass(frozen=True, slots=True)
class MessageClassification:
    conversation_type: str
    content_type: str
    actionability: str
    importance: str
    content_scope: str
    temporal_relevance: str
    topics: list[str]
    potential_state_change: bool = False
    is_forwarded: bool = False
    confidence: float = 0.8
    classifier_type: str = "deterministic_contextual"

    @property
    def information_scope(self) -> str:
        """The product name for the persisted scope dimension.

        ``content_scope`` remains the compatibility field used by the first
        classification migration and its direct callers.
        """
        return self.content_scope

    def payload(self) -> dict[str, object]:
        return asdict(self)


def classify_message(
    conn: sqlite3.Connection,
    message: AIMessage,
    *,
    context_version: int = 1,
) -> MessageClassification:
    """Classify one message using Telegram metadata and bounded local context.

    The deliberately conservative rules recognise obvious routing cases and use
    open chat tasks only to resolve short state-changing replies such as "sent".
    Ambiguous semantic distinctions remain normal information instead of being
    hallucinated as tasks or graph edges.
    """
    text = " ".join(message.text.split())
    lower = text.casefold()
    conversation_type = _conversation_type(message.chat_type)
    signals = _context_signals(conn, message.chat_id, message.date, message.message_id)
    scope = _content_scope(
        conversation_type,
        lower,
        signals,
        active_segment_project(conn, message.chat_id, message.date),
        _has_project_segments(conn, message.chat_id),
    )
    forwarded = _is_forwarded(conn, message.chat_id, message.message_id)
    content_type, actionability, importance, scope, state_change, confidence = (
        _classify_content(text, lower, scope, signals)
    )
    return MessageClassification(
        conversation_type,
        content_type,
        actionability,
        importance,
        scope,
        _temporal_relevance(message.date),
        _topics(conn, message.chat_id, lower),
        state_change,
        forwarded,
        confidence,
    )


def _classify_content(
    text: str,
    lower: str,
    scope: str,
    signals: dict[str, int],
) -> tuple[str, str, str, str, bool, float]:
    """Resolve content routing before persistence and topic enrichment."""
    if not text or _NOISE_RE.match(text):
        return "conversation", "none", "noise", scope, False, 0.99
    if _looks_like_spam(lower):
        return "spam", "none", "noise", "public_information", False, 0.98
    if _looks_like_news(lower):
        return "news", "informational", "normal", "external_news", False, 0.95

    rules = (
        (_looks_like_promise(lower), "promise", "waiting", 0.9),
        (_looks_like_request(lower), "request", "actionable", 0.86),
        (_looks_like_decision(lower), "decision", "reference", 0.86),
        (_is_contextual_update(lower, signals), "update", "reference", 0.9),
        (_looks_like_payment(lower), "payment", "reference", 0.9),
        (_looks_like_meeting(lower), "meeting", "actionable", 0.86),
    )
    for matched, content_type, actionability, confidence in rules:
        if matched:
            return content_type, actionability, "high", scope, True, confidence
    if _looks_like_question(text):
        return "question", "actionable", "normal", scope, False, 0.9
    return (
        "information",
        "informational",
        "low" if len(text) < 12 else "normal",
        scope,
        False,
        0.8,
    )


def save_classification(
    conn: sqlite3.Connection,
    message: AIMessage,
    classification: MessageClassification,
    *,
    context_version: int = 1,
) -> None:
    now = utc_now()
    conn.execute(
        """INSERT INTO message_classifications(
               chat_id,message_id,conversation_type,content_type,actionability,
               importance,content_scope,temporal_relevance,potential_state_change,is_forwarded,
               information_scope,topic_json,classifier_type,confidence,classification_version,
               context_version,context_stale,classified_at
           ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,?)
           ON CONFLICT(chat_id,message_id) DO UPDATE SET
               conversation_type=excluded.conversation_type,
               content_type=excluded.content_type,
               actionability=excluded.actionability,
               importance=excluded.importance,
               content_scope=excluded.content_scope,
               information_scope=excluded.information_scope,
               temporal_relevance=excluded.temporal_relevance,
               potential_state_change=excluded.potential_state_change,
               is_forwarded=excluded.is_forwarded,
               topic_json=excluded.topic_json,
               classifier_type=excluded.classifier_type,
               confidence=excluded.confidence,
               classification_version=excluded.classification_version,
               context_version=excluded.context_version,
               context_stale=0,
               classified_at=excluded.classified_at""",
        (
            message.chat_id,
            message.message_id,
            classification.conversation_type,
            classification.content_type,
            classification.actionability,
            classification.importance,
            classification.content_scope,
            classification.temporal_relevance,
            int(classification.potential_state_change),
            int(classification.is_forwarded),
            classification.information_scope,
            json.dumps(classification.topics, ensure_ascii=False),
            classification.classifier_type,
            classification.confidence,
            CLASSIFICATION_VERSION,
            context_version,
            now,
        ),
    )


def classify_pending_messages(
    conn: sqlite3.Connection,
    messages: list[AIMessage],
    *,
    context_version: int = 1,
) -> int:
    for message in messages:
        save_classification(
            conn,
            message,
            classify_message(conn, message, context_version=context_version),
            context_version=context_version,
        )
    return len(messages)


def _conversation_type(chat_type: str) -> str:
    return {"user": "personal", "group": "group", "channel": "broadcast"}.get(
        chat_type, "unknown"
    )


def _topics(conn: sqlite3.Connection, chat_id: int, text: str) -> list[str]:
    labels = {word for word in _TOPIC_WORDS if word in text}
    rows = conn.execute(
        """SELECT p.canonical_name FROM tasks AS t
           JOIN projects AS p ON p.project_id=t.related_project_id
           WHERE t.source_chat_id=? AND t.status IN ('open','waiting','blocked')
           LIMIT 8""",
        (chat_id,),
    ).fetchall()
    for (name,) in rows:
        normalized = re.sub(r"[^\w]+", "_", str(name).casefold()).strip("_")
        if normalized and any(token in text for token in str(name).casefold().split()):
            labels.add(normalized[:48])
    return sorted(labels)[:8]


def _is_contextual_update(text: str, signals: dict[str, int]) -> bool:
    if text not in {
        "sent",
        "done",
        "received",
        "completed",
        "ready",
        "yes",
        "sent it",
        "all set",
    }:
        return False
    return signals["waiting_tasks"] > 0 or signals["recent_high_updates"] > 0


def _context_signals(
    conn: sqlite3.Connection,
    chat_id: int,
    as_of: str | None = None,
    message_id: int | None = None,
) -> dict[str, int]:
    """Bounded local signals that resolve otherwise ambiguous short replies."""
    waiting, linked = conn.execute(
        """SELECT
               SUM(CASE WHEN status='waiting' THEN 1 ELSE 0 END),
               SUM(CASE WHEN related_project_id IS NOT NULL OR related_company_id IS NOT NULL THEN 1 ELSE 0 END)
           FROM tasks WHERE source_chat_id=? AND status IN ('open','waiting','blocked')""",
        (chat_id,),
    ).fetchone()
    recent_high = conn.execute(
        """SELECT COUNT(*) FROM (
               SELECT 1 FROM message_classifications AS mc
               JOIN messages AS m
                 ON m.chat_id=mc.chat_id AND m.message_id=mc.message_id
               WHERE mc.chat_id=? AND mc.importance IN ('critical','high')
                 AND mc.content_type IN ('request','promise','decision','meeting')
                 AND (
                     ? IS NULL
                     OR COALESCE(m.date, '') < ?
                     OR (
                         COALESCE(m.date, '') = ?
                         AND (? IS NULL OR m.message_id < ?)
                     )
                 )
               ORDER BY COALESCE(m.date, '') DESC, m.message_id DESC LIMIT 8
           )""",
        (chat_id, as_of, as_of, as_of, message_id, message_id),
    ).fetchone()[0]
    return {
        "waiting_tasks": int(waiting or 0),
        "linked_tasks": int(linked or 0),
        "recent_high_updates": int(recent_high or 0),
    }


def _content_scope(
    conversation_type: str,
    text: str,
    signals: dict[str, int],
    segment_project_id: int | None,
    has_project_segments: bool,
) -> str:
    if segment_project_id is not None:
        return "project"
    if any(word in text for word in _TOPIC_WORDS):
        return "business"
    if signals["linked_tasks"] and not has_project_segments:
        return "business"
    if conversation_type == "personal":
        return "personal"
    if conversation_type == "group":
        return "private_group"
    return "public_information"


def _has_project_segments(conn: sqlite3.Connection, chat_id: int) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM conversation_segments WHERE chat_id=? LIMIT 1", (chat_id,)
        ).fetchone()
        is not None
    )


def _is_forwarded(conn: sqlite3.Connection, chat_id: int, message_id: int) -> bool:
    row = conn.execute(
        "SELECT is_forwarded FROM messages WHERE chat_id=? AND message_id=?",
        (chat_id, message_id),
    ).fetchone()
    return bool(row and row[0])


def processing_route(classification: MessageClassification) -> str:
    """Map classification dimensions to the single semantic-work decision."""
    if classification.importance == "noise" or classification.content_type == "spam":
        return "archive_only"
    if classification.information_scope == "external_news":
        return "news_memory"
    if classification.content_type == "decision":
        return "state_change"
    if (
        classification.actionability in {"actionable", "waiting"}
        or classification.potential_state_change
    ):
        return "operational"
    if classification.content_type in {"conversation", "information"}:
        return "contextual_memory"
    return "contextual_memory"


def _temporal_relevance(value: str | None) -> str:
    """Persist only source-time stability, never a classification-time age label."""
    return "dated" if _parse_occurred_at(value) is not None else "unknown"


def temporal_relevance_as_of(value: str | None, as_of: datetime | None = None) -> str:
    """Derive current versus historical relative age for a caller's as-of time."""
    occurred = _parse_occurred_at(value)
    if occurred is None:
        return "unknown"
    reference = as_of or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return "historical" if occurred < reference - timedelta(days=90) else "current"


def _parse_occurred_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        occurred = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)
    return occurred


def _looks_like_question(text: str) -> bool:
    return "?" in text or text.casefold().startswith(
        (
            "can you",
            "could you",
            "what ",
            "when ",
            "why ",
            "можете ",
            "можешь ",
            "когда ",
            "რატომ ",
            "როდის ",
        )
    )


def _looks_like_promise(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "i will ",
            "i'll ",
            "we will ",
            "will send",
            "will share",
            "я отправлю",
            "мы отправим",
            "пришлю",
            "გამოგიგზავნი",
        )
    )


def _looks_like_request(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "please ",
            "send ",
            "share ",
            "need ",
            "let's ",
            "пожалуйста",
            "отправьте",
            "отправь",
            "пришлите",
            "нужно ",
            "нужен ",
            "гთხოვთ",
            "გამომიგზავნეთ",
            "მჭირდება",
        )
    )


def _looks_like_decision(text: str) -> bool:
    return any(
        phrase in text
        for phrase in (
            "we agreed",
            "let's proceed",
            "decision is",
            "approved",
            "confirmed",
            "договорились",
            "решили",
            "одобрено",
            "подтверждено",
            "შევთანხმდით",
            "დადასტურებულია",
        )
    )


def _looks_like_payment(text: str) -> bool:
    return any(
        word in text
        for word in (
            "payment",
            "invoice",
            "paid",
            "transfer",
            "wire",
            "оплата",
            "счёт",
            "счет",
            "оплачено",
            "перевод",
            "გადახდა",
            "ინვოისი",
            "გადარიცხვა",
        )
    )


def _looks_like_meeting(text: str) -> bool:
    return any(
        word in text
        for word in (
            "meeting",
            "call at",
            "calendar",
            "zoom",
            "встреча",
            "созвон",
            "зум",
            "შეხვედრა",
            "ზარი",
            "ზუმი",
        )
    )


def _looks_like_news(text: str) -> bool:
    return any(
        word in text
        for word in ("announces", "announced", "breaking", "regulation", "rate")
    )


def _looks_like_spam(text: str) -> bool:
    return any(
        word in text
        for word in ("unsubscribe", "promo code", "airdrop", "guaranteed profit")
    )
