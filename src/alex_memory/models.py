from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class DialogInfo:
    dialog: Any
    chat_id: int
    title: str
    username: str | None
    chat_type: str
    is_bot: bool
    last_date: str | None


@dataclass(slots=True)
class SyncState:
    selected_count: int
    started: float = field(default_factory=time.monotonic)

    personal_chats: int = 0
    groups: int = 0
    channels_skipped: int = 0
    other_skipped: int = 0

    chats_started: int = 0
    chats_completed: int = 0
    full_bootstraps: int = 0
    recent_bootstraps: int = 0
    incremental_syncs: int = 0

    messages_fetched: int = 0
    messages_saved: int = 0
    errors: int = 0
    flood_waits: int = 0

    status: str = "Starting"
    active: dict[int, dict] = field(default_factory=dict)
    recent_errors: list[str] = field(default_factory=list)

    def add_error(self, text: str) -> None:
        self.errors += 1
        self.recent_errors.append(text)
        self.recent_errors = self.recent_errors[-4:]


@dataclass(slots=True)
class LiveSyncState:
    phase: str = "STARTING"
    connected: bool = False
    messages_received: int = 0
    messages_saved: int = 0
    edits_received: int = 0
    deletions_received: int = 0
    last_message_at: str | None = None
    last_reconciliation_at: str | None = None
    last_error: str | None = None
    reconnect_attempts: int = 0
    retry_scheduled: bool = False


@dataclass(slots=True)
class AIMessage:
    chat_id: int
    message_id: int
    sender_id: int | None
    date: str | None
    text: str
    is_outgoing: bool
    chat_title: str
    chat_type: str


@dataclass(slots=True)
class AIBatch:
    chat_id: int
    chat_title: str
    messages: list[AIMessage]
    prompt: str


@dataclass(frozen=True, slots=True)
class AIRequest:
    """A bounded analysis request with routing intent, never raw global history."""

    batch: AIBatch
    workload: str = "context_extraction"
    priority: str = "background"
    requires_structured_output: bool = True
    estimated_input_tokens: int | None = None


@dataclass(slots=True)
class AIAnalysisResult:
    provider: str
    model: str
    summary: str
    items: list[dict]
    usage: dict[str, int | str] = field(default_factory=dict)
    fallback_used: bool = False
    raw_payload: object | None = None

    def as_payload(self) -> object:
        """Return the provider response unchanged for contract validation."""
        if self.raw_payload is not None:
            return self.raw_payload
        return {"summary": self.summary, "items": self.items}


@dataclass(frozen=True, slots=True)
class AIAnswerResult:
    """One provider response for a bounded grounded-answer request."""

    provider: str
    model: str
    text: str
    usage: dict[str, int | str] = field(default_factory=dict)


@dataclass(slots=True)
class AISaveResult:
    inserted: int = 0
    duplicates: int = 0
    rejected: int = 0
    claims_inserted: int = 0
    claims_duplicated: int = 0
    rejection_reasons: list[str] = field(default_factory=list)
    batch_id: int | None = None
    saved_item_ids: list[int] = field(default_factory=list)
    saved_claim_ids: list[int] = field(default_factory=list)


@dataclass(slots=True)
class AIBatchReport:
    chat_id: int
    chat_title: str
    message_count: int
    summary: str
    model_items: list[dict]
    save_result: AISaveResult
    error: str | None = None
    lane: str = "daily"
    provider: str = "-"
    model: str = "-"
    fallback_used: bool = False
    provider_note: str = ""
