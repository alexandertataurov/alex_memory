"""Conservative relative-time extraction preserving the original expression."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


def resolve_temporal_expressions(
    text: str, message_at: str | None, timezone_name: str
) -> list[dict]:
    if not text or not message_at:
        return []
    timestamp = datetime.fromisoformat(message_at.replace("Z", "+00:00")).astimezone(
        ZoneInfo(timezone_name)
    )
    lowered = text.casefold()
    results: list[dict] = []
    if "tomorrow" in lowered or "завтра" in lowered:
        raw = _phrase(lowered, "tomorrow", "завтра")
        results.append(
            {
                "raw_expression": raw,
                "resolved_at": (timestamp.date() + timedelta(days=1)).isoformat(),
                "resolution_type": "absolute_date",
                "dependency_type": None,
                "resolution_confidence": 1.0,
            }
        )
    if "in two days" in lowered or "через два дня" in lowered:
        raw = _phrase(lowered, "in two days", "через два дня")
        results.append(
            {
                "raw_expression": raw,
                "resolved_at": (timestamp.date() + timedelta(days=2)).isoformat(),
                "resolution_type": "absolute_date",
                "dependency_type": None,
                "resolution_confidence": 1.0,
            }
        )
    if "next week" in lowered or "на следующей неделе" in lowered:
        results.append(
            {
                "raw_expression": _phrase(lowered, "next week", "на следующей неделе"),
                "resolved_at": (timestamp.date() + timedelta(days=7)).isoformat(),
                "resolution_type": "relative_window",
                "dependency_type": None,
                "resolution_confidence": 0.7,
            }
        )
    dependency = re.search(r"(?:once|after)\s+([\w\s-]{3,40})(?:\.|,|$)", lowered)
    if dependency:
        results.append(
            {
                "raw_expression": dependency.group(0).strip(),
                "resolved_at": None,
                "resolution_type": "dependency",
                "dependency_type": dependency.group(1).strip().replace(" ", "_"),
                "resolution_confidence": 0.85,
            }
        )
    return results


def _phrase(text: str, *terms: str) -> str:
    for term in terms:
        if term in text:
            match = re.search(re.escape(term) + r"(?:\s+\w+)?", text)
            return match.group(0) if match else term
    return terms[0]
