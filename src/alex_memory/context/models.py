from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


ContextPurpose = Literal[
    "message_analysis",
    "task_reconciliation",
    "ask_memory",
    "daily_brief",
    "person_profile",
    "project_profile",
    "company_profile",
    "follow_up",
    "global_state",
    "diagnostics",
]


@dataclass(slots=True)
class ContextRequest:
    purpose: ContextPurpose = "ask_memory"
    query: str = ""
    chat_id: int | None = None
    as_of: datetime | None = None
    person_ids: list[int] = field(default_factory=list)
    company_ids: list[int] = field(default_factory=list)
    project_ids: list[int] = field(default_factory=list)
    task_ids: list[int] = field(default_factory=list)
    include_raw_evidence: bool = True


@dataclass(slots=True)
class BuiltContext:
    purpose: ContextPurpose
    as_of: str
    global_state: dict
    people: list[dict]
    projects: list[dict]
    companies: list[dict]
    relationships: list[dict]
    tasks: list[dict]
    events: list[dict]
    facts: list[dict]
    historical_facts: list[dict]
    conflicts: list[dict]
    summaries: list[dict]
    evidence: list[dict]
    segments: list[dict]
    diagnostics: dict

    @property
    def context_score(self) -> float:
        return float(self.diagnostics.get("context_score", 0))

    def render(self, max_chars: int) -> str:
        return _render_sections(self, max_chars, include_provenance=True)

    def render_for_analysis(self, max_chars: int) -> str:
        return _render_sections(self, max_chars, include_provenance=False)


def _render_sections(
    context: BuiltContext, max_chars: int, *, include_provenance: bool
) -> str:
    lines = [f"PURPOSE: {context.purpose}", f"AS OF: {context.as_of}"]
    _add_entity_section(lines, "PEOPLE", context.people)
    _add_entity_section(lines, "PROJECTS", context.projects)
    _add_entity_section(lines, "COMPANIES", context.companies)
    _add_items(
        lines, "CURRENT FACTS", context.facts, "predicate", "value", include_provenance
    )
    _add_items(
        lines,
        "UNRESOLVED CONFLICTS",
        context.conflicts,
        "predicate",
        "description",
        include_provenance,
    )
    _add_items(
        lines,
        "CONVERSATION PERIODS",
        context.segments,
        "project_name",
        "description",
        include_provenance,
    )
    _add_items(
        lines, "OPEN LOOPS", context.tasks, "title", "details", include_provenance
    )
    _add_items(
        lines,
        "RELATIONSHIPS",
        context.relationships,
        "relationship_type",
        "description",
        include_provenance,
    )
    _add_items(
        lines,
        "RECENT EVENTS",
        context.events,
        "title",
        "description",
        include_provenance,
    )
    _add_items(
        lines,
        "DURABLE SUMMARIES",
        context.summaries,
        "memory_key",
        "summary",
        include_provenance,
    )
    if context.evidence:
        _add_items(
            lines,
            "EXACT SUPPORTING EVIDENCE",
            context.evidence,
            "date",
            "text",
            include_provenance,
        )
    if include_provenance:
        lines.append(
            "DIAGNOSTICS: "
            + ", ".join(f"{key}={value}" for key, value in context.diagnostics.items())
        )

    chosen: list[str] = []
    size = 0
    for line in lines:
        candidate = line + "\n"
        if size + len(candidate) > max_chars:
            break
        chosen.append(line)
        size += len(candidate)
    return "\n".join(chosen)


def _add_entity_section(lines: list[str], heading: str, entities: list[dict]) -> None:
    if not entities:
        return
    lines.append(heading + ":")
    for entity in entities:
        name = entity.get("canonical_name") or entity.get("id")
        lines.append(f"- {name}")
        for pinned in entity.get("pinned", [])[:2]:
            lines.append(f"  pinned: {pinned}")


def _add_items(
    lines: list[str],
    heading: str,
    items: list[dict],
    label_key: str,
    detail_key: str,
    include_provenance: bool,
) -> None:
    if not items:
        return
    lines.append(heading + ":")
    for item in items:
        label = item.get(label_key) or "context"
        detail = item.get(detail_key) or ""
        if isinstance(detail, dict):
            detail = ", ".join(f"{key}={value}" for key, value in detail.items())
        score = (
            f" [score {float(item.get('score', 0)):.0f}]" if include_provenance else ""
        )
        lines.append(f"- {label}: {str(detail)[:700]}{score}")
        if include_provenance and item.get("reasons"):
            lines.append("  why: " + "; ".join(item["reasons"]))
        if include_provenance and item.get("source_chat_id") is not None:
            lines.append(
                f"  source: chat {item['source_chat_id']} / message {item.get('source_message_id', '—')}"
            )
