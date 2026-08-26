"""Deterministic relevance scoring for bounded context selection."""

from __future__ import annotations

from datetime import datetime, timezone


_BASE_SCORES = {
    "pinned": 120.0,
    "task": 90.0,
    "fact": 85.0,
    "relationship": 75.0,
    "event": 65.0,
    "summary": 55.0,
    "evidence": 35.0,
}


def rank_item(
    item: dict,
    kind: str,
    *,
    direct_match: bool = False,
    graph_distance: int | None = None,
    now: str | None = None,
) -> dict:
    """Attach an explainable score; raw text can never outrank canonical state."""
    score = _BASE_SCORES[kind]
    reasons = [f"{kind} base"]
    if direct_match:
        score += 25
        reasons.append("direct entity/chat match")
    if item.get("status") == "waiting":
        score += 18
        reasons.append("waiting open loop")
    elif item.get("status") == "open":
        score += 12
        reasons.append("open loop")
    if item.get("is_current") or kind == "fact":
        score += 12
        reasons.append("current state")
    if item.get("pinned"):
        score += 35
        reasons.append("manual pinned context")
    confidence = item.get("confidence")
    if confidence is not None:
        score += max(0.0, min(float(confidence), 1.0)) * 10
        reasons.append(f"confidence {float(confidence):.0%}")
    if graph_distance is not None:
        score += max(0, 12 - graph_distance * 6)
        reasons.append(f"graph distance {graph_distance}")
    age = _age_days(
        item.get("updated_at")
        or item.get("occurred_at")
        or item.get("date")
        or item.get("valid_from"),
        now,
    )
    if age is not None:
        score += max(0.0, 12.0 - min(age, 120) / 10)
        reasons.append(f"{age}d recency")
    item["score"] = round(score, 2)
    item["reasons"] = reasons
    return item


def highest(items: list[dict], limit: int) -> list[dict]:
    return sorted(
        items,
        key=lambda item: (
            float(item.get("score", 0)),
            str(item.get("updated_at") or item.get("date") or ""),
        ),
        reverse=True,
    )[:limit]


def _age_days(value: object, now: str | None) -> int | None:
    if not value:
        return None
    try:
        instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        reference = (
            datetime.fromisoformat(now.replace("Z", "+00:00"))
            if now
            else datetime.now(timezone.utc)
        )
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        return max(0, (reference - instant).days)
    except ValueError:
        return None
