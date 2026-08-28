"""Bounded AI presentation summary for a materialized person profile."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3

from .ai.extraction_contract import ExtractionContractError, validate_response
from .ai.router import AIRouter
from .ai.routing import AIWorkload, RequestPriority
from .models import AIBatch, AIMessage
from .person_profile import profile_summary_package


_CITATION = re.compile(r"\[(\d+)/(\d+)\]")
_MAX_SUMMARY_CHARS = 900


async def refresh_all_person_profiles(
    conn: sqlite3.Connection, settings
) -> dict[str, int]:
    """Rebuild every materialized person profile from existing canonical state.

    This is an explicit maintenance operation. It reuses the normal contact
    materializer and presentation-summary contract, leaving raw messages,
    semantic claims, canonical facts, and manual decisions untouched. Each
    person is an independent, restart-safe unit: a failed optional summary
    retains its prior valid value and does not prevent the remaining profiles
    from refreshing.
    """
    from .context.contact_materializer import ContactContextMaterializer

    person_ids = [
        int(row[0])
        for row in conn.execute("SELECT person_id FROM people ORDER BY person_id")
    ]
    refreshed = summaries = failed = 0
    materializer = ContactContextMaterializer(conn)
    for person_id in person_ids:
        try:
            materializer.refresh_person(person_id)
            refreshed += 1
            if await refresh_profile_summary(conn, settings, person_id):
                summaries += 1
        except Exception:
            # Summary/provider errors are presentation-only. The old summary
            # remains in person_context_state because refresh_profile_summary
            # writes only after local validation.
            failed += 1
    return {
        "people": len(person_ids),
        "refreshed": refreshed,
        "summaries": summaries,
        "failed": failed,
    }


async def refresh_profile_summary(
    conn: sqlite3.Connection,
    settings,
    person_id: int,
    *,
    router: AIRouter | None = None,
) -> bool:
    """Refresh a presentation-only cited summary; invalid output is not persisted."""
    if not settings.ai_profile_summaries_enabled:
        return False
    package = profile_summary_package(conn, person_id)
    sources = package["sources"]
    if not sources:
        return False
    input_hash = hashlib.sha256(
        json.dumps(
            package, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    previous = conn.execute(
        "SELECT profile_summary_input_hash FROM person_context_state WHERE person_id=?",
        (person_id,),
    ).fetchone()
    if previous is not None and previous[0] == input_hash:
        return False
    name = conn.execute(
        "SELECT canonical_name FROM people WHERE person_id=?", (person_id,)
    ).fetchone()
    if name is None:
        return False
    messages = [
        AIMessage(
            item["chat_id"],
            item["message_id"],
            None,
            item["date"],
            item["text"],
            False,
            "Profile evidence",
            "unknown",
        )
        for item in sources
    ]
    allowed = {(item["chat_id"], item["message_id"]) for item in sources}
    prompt = (
        "Write a concise current profile summary for " + str(name[0]) + ". "
        "Use only the supplied canonical rows and source messages. Do not introduce facts, advice, tasks, "
        "or relationships. Every sentence with a factual claim must cite one or more "
        "exact [chat_id/message_id] references from the supplied messages. Return JSON "
        "with a non-empty summary and an empty items array.\n\n<PROFILE_EVIDENCE>\n"
        + "\n".join(
            f"[MESSAGE chat_id={item['chat_id']} message_id={item['message_id']} date={item['date']}]\n{item['text']}\n[/MESSAGE]"
            for item in sources
        )
        + "\n</PROFILE_EVIDENCE>\n<CANONICAL_PROFILE_ROWS>\n"
        + "\n".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True)
            for record in package["records"]
        )
        + "\n</CANONICAL_PROFILE_ROWS>"
    )
    batch = AIBatch(
        sources[0]["chat_id"], f"Person profile: {name[0]}", messages, prompt
    )
    result = await (router or AIRouter(settings, conn=conn)).analyze(
        batch, workload=AIWorkload.SUMMARY, priority=RequestPriority.BACKGROUND
    )
    payload = validate_response(result.as_payload())
    summary = str(payload["summary"]).strip()
    if payload["items"]:
        raise ExtractionContractError(
            "profile summary must not contain extracted items"
        )
    if len(summary) > _MAX_SUMMARY_CHARS:
        raise ExtractionContractError("profile summary exceeds bounded length")
    citations = {
        (int(chat), int(message)) for chat, message in _CITATION.findall(summary)
    }
    if not citations or not citations <= allowed:
        raise ExtractionContractError(
            "profile summary has missing or foreign evidence citations"
        )
    from .context.contact_materializer import ContactContextMaterializer

    ContactContextMaterializer(conn).store_profile_summary(
        person_id, summary, input_hash
    )
    return True
