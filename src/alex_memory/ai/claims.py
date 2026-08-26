"""Immutable, source-backed semantic claims produced by AI understanding."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from typing import Any


CLAIM_TYPES = frozenset(
    {
        "entity",
        "event",
        "commitment",
        "temporal_fact",
        "relationship",
        "topic",
        "action_candidate",
    }
)
ENTITY_TYPES = frozenset(
    {
        "person",
        "company",
        "project",
        "task",
        "conversation",
        "event",
        "commitment",
        "topic",
    }
)
_CLAIM_FIELDS = frozenset(
    {"claim_type", "statement", "payload", "confidence", "evidence", "entity_refs"}
)
_EVIDENCE_FIELDS = frozenset({"source_chat_id", "source_message_id"})
_ENTITY_REF_FIELDS = frozenset(
    {"role", "entity_type", "surface_name", "canonical_entity_id"}
)
_LEGACY_CLAIM_TYPES = {
    "task": "commitment",
    "follow_up": "commitment",
    "deadline": "commitment",
    "promise_by_me": "commitment",
    "promise_to_me": "commitment",
    "project": "entity",
    "person": "entity",
    "company": "entity",
    "payment": "event",
    "important_fact": "temporal_fact",
}


def validate_claim(
    claim: object, valid_refs: set[tuple[int, int]]
) -> tuple[dict[str, Any] | None, str | None]:
    """Validate an untrusted claim without repairing meaning or evidence."""
    if not isinstance(claim, dict):
        return None, "claim must be an object"
    unknown = set(claim) - _CLAIM_FIELDS
    required = _CLAIM_FIELDS - {"entity_refs"}
    missing = required - set(claim)
    if missing or unknown:
        return None, (
            "missing fields: " + ", ".join(sorted(missing))
            if missing
            else "unknown fields: " + ", ".join(sorted(unknown))
        )
    claim_type = claim["claim_type"]
    statement = claim["statement"]
    payload = claim["payload"]
    confidence = claim["confidence"]
    evidence = claim["evidence"]
    if not isinstance(claim_type, str) or claim_type not in CLAIM_TYPES:
        return None, "invalid claim_type"
    if not isinstance(statement, str) or not statement.strip():
        return None, "statement must be non-empty text"
    if not isinstance(payload, dict):
        return None, "payload must be an object"
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None, "confidence must be a finite number in [0,1]"
    if not math.isfinite(float(confidence)) or not 0 <= float(confidence) <= 1:
        return None, "confidence must be a finite number in [0,1]"
    if not isinstance(evidence, list) or not evidence:
        return None, "claim must include direct evidence"
    if len(evidence) > 16:
        return None, "claim evidence exceeds the bounded limit"
    normalized_evidence: list[dict[str, int]] = []
    seen_evidence: set[tuple[int, int]] = set()
    for reference in evidence:
        if not isinstance(reference, dict) or set(reference) != _EVIDENCE_FIELDS:
            return None, "evidence must contain only source_chat_id/source_message_id"
        chat_id, message_id = (
            reference["source_chat_id"],
            reference["source_message_id"],
        )
        if (
            isinstance(chat_id, bool)
            or isinstance(message_id, bool)
            or not isinstance(chat_id, int)
            or not isinstance(message_id, int)
        ):
            return None, "evidence IDs must be integers"
        key = (chat_id, message_id)
        if key not in valid_refs:
            return None, f"source reference {chat_id}/{message_id} is not in this batch"
        if key not in seen_evidence:
            seen_evidence.add(key)
            normalized_evidence.append(
                {"source_chat_id": chat_id, "source_message_id": message_id}
            )
    entity_refs = claim.get("entity_refs", [])
    if not isinstance(entity_refs, list) or len(entity_refs) > 16:
        return None, "entity_refs must be a bounded list"
    normalized_refs: list[dict[str, object]] = []
    for reference in entity_refs:
        if not isinstance(reference, dict) or set(reference) != _ENTITY_REF_FIELDS:
            return None, "entity_refs must use the declared fields"
        role = reference["role"]
        entity_type = reference["entity_type"]
        surface_name = reference["surface_name"]
        canonical_id = reference["canonical_entity_id"]
        if not isinstance(role, str) or not role.strip():
            return None, "entity reference role must be text"
        if not isinstance(entity_type, str) or entity_type not in ENTITY_TYPES:
            return None, "invalid entity reference type"
        if not isinstance(surface_name, str) or not surface_name.strip():
            return None, "entity reference surface_name must be text"
        if canonical_id is not None and (
            isinstance(canonical_id, bool)
            or not isinstance(canonical_id, int)
            or canonical_id < 1
        ):
            return None, "canonical_entity_id must be a positive integer or null"
        normalized_refs.append(
            {
                "role": role.strip(),
                "entity_type": entity_type,
                "surface_name": surface_name.strip(),
                "canonical_entity_id": canonical_id,
            }
        )
    return (
        {
            "claim_type": claim_type,
            "statement": statement.strip(),
            "payload": payload,
            "confidence": float(confidence),
            "evidence": normalized_evidence,
            "entity_refs": normalized_refs,
        },
        None,
    )


def save_claim(
    conn: sqlite3.Connection,
    *,
    batch_id: int,
    claim: object,
    valid_refs: set[tuple[int, int]],
    provider: str,
    model: str,
    extractor_version: int,
    created_at: str,
) -> tuple[int | None, bool, str | None]:
    """Persist one validated claim and all of its exact evidence atomically."""
    normalized, reason = validate_claim(claim, valid_refs)
    if reason:
        return None, False, reason
    assert normalized is not None
    encoded_payload = json.dumps(
        normalized["payload"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    dedupe_key = _claim_dedupe_key(normalized, extractor_version)
    cursor = conn.execute(
        """INSERT OR IGNORE INTO semantic_claims(
               batch_id,claim_type,statement,payload_json,extractor_version,provider,
               model,confidence,authority_status,dedupe_key,created_at
           ) VALUES (?,?,?,?,?,?,?,?, 'observed', ?, ?)""",
        (
            batch_id,
            normalized["claim_type"],
            normalized["statement"],
            encoded_payload,
            extractor_version,
            provider,
            model,
            normalized["confidence"],
            dedupe_key,
            created_at,
        ),
    )
    if cursor.rowcount:
        if cursor.lastrowid is None:
            raise RuntimeError("SQLite did not return an ID for the semantic claim")
        claim_id = int(cursor.lastrowid)
        for ordinal, reference in enumerate(normalized["evidence"], start=1):
            conn.execute(
                """INSERT INTO semantic_claim_evidence(
                       claim_id,ordinal,source_chat_id,source_message_id,created_at
                   ) VALUES (?,?,?,?,?)""",
                (
                    claim_id,
                    ordinal,
                    reference["source_chat_id"],
                    reference["source_message_id"],
                    created_at,
                ),
            )
        for ordinal, reference in enumerate(normalized["entity_refs"], start=1):
            conn.execute(
                """INSERT INTO semantic_claim_entity_refs(
                       claim_id,ordinal,role,entity_type,surface_name,canonical_entity_id,
                       resolution_status,created_at
                   ) VALUES (?,?,?,?,?,?, 'unresolved', ?)""",
                (
                    claim_id,
                    ordinal,
                    reference["role"],
                    reference["entity_type"],
                    reference["surface_name"],
                    reference["canonical_entity_id"],
                    created_at,
                ),
            )
        return claim_id, True, None
    row = conn.execute(
        "SELECT claim_id FROM semantic_claims WHERE dedupe_key=?", (dedupe_key,)
    ).fetchone()
    return (int(row[0]) if row else None), False, None


def legacy_item_claim(item: dict[str, Any]) -> dict[str, Any]:
    """Express a validated legacy extraction as an immutable semantic claim."""
    kind = item["kind"]
    entity_refs = []
    for role, entity_type, value in (
        ("person", "person", item.get("person")),
        ("company", "company", item.get("company")),
        ("project", "project", item.get("project_name")),
    ):
        if value:
            entity_refs.append(
                {
                    "role": role,
                    "entity_type": entity_type,
                    "surface_name": value,
                    "canonical_entity_id": None,
                }
            )
    if kind in {"person", "company", "project"}:
        entity_refs.append(
            {
                "role": "subject",
                "entity_type": kind,
                "surface_name": item["title"],
                "canonical_entity_id": None,
            }
        )
    evidence = [
        {
            "source_chat_id": item["source_chat_id"],
            "source_message_id": item["source_message_id"],
        }
    ]
    if item.get("assertion_kind") == "inference":
        evidence = item.get("supporting_evidence") or evidence
    return {
        "claim_type": _LEGACY_CLAIM_TYPES[kind],
        "statement": ": ".join(
            value for value in (item["title"].strip(), item["details"].strip()) if value
        ),
        "payload": {"legacy_item": item},
        "confidence": item["confidence"],
        "evidence": evidence,
        "entity_refs": entity_refs,
    }


def _claim_dedupe_key(claim: dict[str, Any], extractor_version: int) -> str:
    value = json.dumps(
        {
            "claim_type": claim["claim_type"],
            "statement": claim["statement"],
            "payload": claim["payload"],
            "evidence": claim["evidence"],
            "entity_refs": claim["entity_refs"],
            "extractor_version": extractor_version,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
