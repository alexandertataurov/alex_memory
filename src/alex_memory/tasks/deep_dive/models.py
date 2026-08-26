from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class EvidenceItem:
    """A displayable claim or raw record, always carrying its source identity."""

    evidence_id: str
    evidence_type: str
    title: str
    text: str
    occurred_at: str | None = None
    source_chat_id: int | None = None
    source_message_id: int | None = None
    relevance_score: float = 0.0
    confidence: float | None = None
    reasons: list[str] = field(default_factory=list)
    conversation_window: list[dict] = field(default_factory=list)

    @property
    def citation(self) -> str:
        return self.evidence_id


@dataclass(slots=True)
class TaskDeepDiveReport:
    task: dict
    session_id: int
    as_of: str
    concepts: list[str]
    executive_summary: str
    origin: list[str]
    current_state: list[str]
    people: list[dict]
    projects: list[dict]
    companies: list[dict]
    known_facts: list[str]
    unknowns: list[str]
    open_loops: list[str]
    recommendations: list[str]
    timeline: list[EvidenceItem]
    evidence: list[EvidenceItem]
    notes: list[dict]
    pinned_evidence_ids: set[str]
    diagnostics: dict
