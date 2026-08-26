"""Provider-neutral, strict contract for untrusted extraction output."""

from __future__ import annotations

import math
from datetime import date
from typing import Any


ANALYSIS_VERSION = 2
ITEM_KINDS = frozenset(
    {
        "task",
        "follow_up",
        "deadline",
        "promise_by_me",
        "promise_to_me",
        "project",
        "payment",
        "person",
        "company",
        "important_fact",
    }
)
TASK_KINDS = frozenset(
    {"task", "follow_up", "deadline", "promise_by_me", "promise_to_me"}
)
TASK_STATUSES = frozenset({"open", "waiting", "done", "canceled"})
INFORMATIONAL_KINDS = ITEM_KINDS - TASK_KINDS
OWNERS = frozenset({"me", "other", "shared", "unknown"})
ITEM_FIELDS = frozenset(
    {
        "kind",
        "title",
        "details",
        "status",
        "owner",
        "due_date",
        "person",
        "company",
        "project_name",
        "amount",
        "currency",
        "confidence",
        "source_chat_id",
        "source_message_id",
    }
)
PROFILE_ITEM_FIELDS = frozenset(
    {"assertion_kind", "effective_from", "effective_to", "supporting_evidence"}
)
PROFILE_ASSERTION_KINDS = frozenset({"direct", "third_party", "inference"})


class ExtractionContractError(ValueError):
    """The model returned a transport-valid but semantically invalid payload."""


def _nullable(field_type: str) -> dict[str, list[str]]:
    return {"type": [field_type, "null"]}


AI_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "enum": sorted(ITEM_KINDS)},
                    "title": {"type": "string"},
                    "details": {"type": "string"},
                    "status": {
                        "type": "string",
                        "enum": sorted(TASK_STATUSES | {"informational"}),
                    },
                    "owner": {"type": "string", "enum": sorted(OWNERS)},
                    "due_date": _nullable("string"),
                    "person": _nullable("string"),
                    "company": _nullable("string"),
                    "project_name": _nullable("string"),
                    "amount": _nullable("number"),
                    "currency": _nullable("string"),
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "source_chat_id": {"type": "integer"},
                    "source_message_id": {"type": "integer"},
                    "assertion_kind": {
                        "type": "string",
                        "enum": sorted(PROFILE_ASSERTION_KINDS),
                    },
                    "effective_from": _nullable("string"),
                    "effective_to": _nullable("string"),
                    "supporting_evidence": {
                        "type": ["array", "null"],
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_chat_id": {"type": "integer"},
                                "source_message_id": {"type": "integer"},
                            },
                            "required": ["source_chat_id", "source_message_id"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": sorted(ITEM_FIELDS),
                "additionalProperties": False,
            },
        },
    },
    "required": ["summary", "items"],
    "additionalProperties": False,
}


def validate_response(payload: object) -> dict[str, Any]:
    """Validate the top-level shape without repairing provider output."""
    if not isinstance(payload, dict):
        raise ExtractionContractError("response must be an object")
    if set(payload) != {"summary", "items"}:
        raise ExtractionContractError("response must contain only summary and items")
    if not isinstance(payload["summary"], str) or not payload["summary"].strip():
        raise ExtractionContractError("summary must be non-empty text")
    if not isinstance(payload["items"], list):
        raise ExtractionContractError("items must be a list")
    return payload


def validate_item_shape(item: object) -> tuple[dict[str, Any] | None, str | None]:
    """Validate one item before persistence verifies its source reference."""
    if not isinstance(item, dict):
        return None, "item must be an object"
    allowed_fields = ITEM_FIELDS | PROFILE_ITEM_FIELDS
    if not ITEM_FIELDS.issubset(item) or set(item) - allowed_fields:
        missing = sorted(ITEM_FIELDS - set(item))
        unknown = sorted(set(item) - allowed_fields)
        return None, (
            "missing fields: " + ", ".join(missing)
            if missing
            else "unknown fields: " + ", ".join(unknown)
        )
    for field in ("kind", "title", "details", "status", "owner"):
        if not isinstance(item[field], str):
            return None, f"{field} must be text"
    for field in ("due_date", "person", "company", "project_name", "currency"):
        if item[field] is not None and not isinstance(item[field], str):
            return None, f"{field} must be text or null"
    if isinstance(item["confidence"], bool) or not isinstance(
        item["confidence"], (int, float)
    ):
        return None, "confidence must be a finite number in [0,1]"
    if (
        not math.isfinite(float(item["confidence"]))
        or not 0 <= float(item["confidence"]) <= 1
    ):
        return None, "confidence must be a finite number in [0,1]"
    if item["amount"] is not None and (
        isinstance(item["amount"], bool)
        or not isinstance(item["amount"], (int, float))
        or not math.isfinite(float(item["amount"]))
    ):
        return None, "amount must be a finite number or null"
    for field in ("source_chat_id", "source_message_id"):
        if isinstance(item[field], bool) or not isinstance(item[field], int):
            return None, f"{field} must be an integer"
    if (
        "assertion_kind" in item
        and item["assertion_kind"] not in PROFILE_ASSERTION_KINDS
    ):
        return None, "invalid profile assertion_kind"
    for field in ("effective_from", "effective_to"):
        if field in item and item[field] is not None:
            value, error = _date_value(item[field])
            if error:
                return None, f"{field} {error}"
            item[field] = value
    supporting_evidence = item.get("supporting_evidence")
    if supporting_evidence is not None:
        if not isinstance(supporting_evidence, list) or len(supporting_evidence) > 16:
            return None, "supporting_evidence must contain at most 16 references"
        for reference in supporting_evidence:
            if not isinstance(reference, dict) or set(reference) != {
                "source_chat_id",
                "source_message_id",
            }:
                return (
                    None,
                    "supporting_evidence references must contain only source IDs",
                )
            if any(
                isinstance(reference[field], bool)
                or not isinstance(reference[field], int)
                for field in ("source_chat_id", "source_message_id")
            ):
                return None, "supporting_evidence source IDs must be integers"
    kind, status = item["kind"], item["status"]
    if kind not in ITEM_KINDS:
        return None, f"invalid kind {kind!r}"
    if item["owner"] not in OWNERS:
        return None, f"invalid owner {item['owner']!r}"
    if kind in TASK_KINDS and status not in TASK_STATUSES:
        return None, f"invalid status {status!r} for task kind"
    if kind in INFORMATIONAL_KINDS and status != "informational":
        return None, f"invalid status {status!r} for informational kind"
    return item, None


def _date_value(value: object) -> tuple[str | None, str | None]:
    if not isinstance(value, str):
        return None, "must be YYYY-MM-DD or null"
    try:
        date.fromisoformat(value)
    except ValueError:
        return None, "must be YYYY-MM-DD or null"
    return value, None
