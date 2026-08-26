"""Read-only, deterministic people discovery for the terminal interface."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from rapidfuzz import fuzz


@dataclass(frozen=True, slots=True)
class PersonSearchResult:
    person_id: int
    name: str
    username: str | None
    status: str
    last_contact_at: str | None
    matched_by: str
    score: float


def search_people(
    conn: sqlite3.Connection, query: str = "", *, limit: int = 10
) -> list[PersonSearchResult]:
    """Return a bounded canonical people list without writing any state."""
    normalized = " ".join(query.split()).casefold()
    rows = conn.execute(
        """SELECT p.person_id,p.canonical_name,p.telegram_username,p.status,
                  pcs.last_contact_at
           FROM people AS p
           LEFT JOIN person_context_state AS pcs ON pcs.person_id=p.person_id
           ORDER BY pcs.last_contact_at DESC, p.canonical_name
           LIMIT 250"""
    ).fetchall()
    person_ids = [int(row[0]) for row in rows]
    values = _search_values(conn, person_ids)
    results: list[PersonSearchResult] = []
    for (
        person_id,
        name,
        username,
        status,
        last_contact,
    ) in rows:
        aliases, projects, companies, facts = values.get(
            int(person_id), ("", "", "", "")
        )
        fields = (
            ("name", str(name)),
            ("username", str(username or "")),
            ("alias", str(aliases or "")),
            ("project", str(projects or "")),
            ("company", str(companies or "")),
            ("context", str(facts or "")),
        )
        if not normalized:
            results.append(
                PersonSearchResult(
                    int(person_id),
                    str(name),
                    username,
                    str(status),
                    last_contact,
                    "recent",
                    0,
                )
            )
            continue
        ranked: list[tuple[float, str]] = []
        for source, value in fields:
            candidate = value.casefold()
            if not candidate:
                continue
            if candidate == normalized:
                score = 100.0
            elif candidate.startswith(normalized):
                score = 95.0
            elif normalized in candidate:
                score = 85.0
            else:
                score = float(fuzz.WRatio(normalized, candidate))
            ranked.append((score, source))
        if ranked:
            score, matched_by = max(ranked, key=lambda value: value[0])
            if score >= 60:
                results.append(
                    PersonSearchResult(
                        int(person_id),
                        str(name),
                        username,
                        str(status),
                        last_contact,
                        matched_by,
                        score,
                    )
                )
    if normalized:
        results.sort(
            key=lambda item: (-item.score, item.name.casefold(), item.person_id)
        )
    return results[:limit]


def _search_values(
    conn: sqlite3.Connection, person_ids: list[int]
) -> dict[int, tuple[str, str, str, str]]:
    """Collect each one-to-many discovery dimension separately to avoid join blowups."""
    if not person_ids:
        return {}
    placeholders = ",".join("?" for _ in person_ids)
    aliases = _grouped_values(
        conn,
        f"""SELECT entity_id,group_concat(alias) FROM entity_aliases
            WHERE entity_type='person' AND entity_id IN ({placeholders}) GROUP BY entity_id""",
        person_ids,
    )
    projects = _grouped_values(
        conn,
        f"""SELECT pp.person_id,group_concat(pr.canonical_name)
            FROM person_project_context AS pp JOIN projects AS pr ON pr.project_id=pp.project_id
            WHERE pp.person_id IN ({placeholders}) GROUP BY pp.person_id""",
        person_ids,
    )
    companies = _grouped_values(
        conn,
        f"""SELECT person_id,group_concat(company_name) FROM (
                SELECT rel.from_id AS person_id,co.canonical_name AS company_name
                FROM relationships AS rel JOIN companies AS co ON rel.to_id=co.company_id
                WHERE rel.from_type='person' AND rel.to_type='company'
                UNION ALL
                SELECT rel.to_id,co.canonical_name FROM relationships AS rel
                JOIN companies AS co ON rel.from_id=co.company_id
                WHERE rel.from_type='company' AND rel.to_type='person'
            ) WHERE person_id IN ({placeholders}) GROUP BY person_id""",
        person_ids,
    )
    facts = _grouped_values(
        conn,
        f"""SELECT subject_id,group_concat(predicate || ' ' || value_json)
            FROM context_facts WHERE subject_type='person' AND is_current=1
            AND subject_id IN ({placeholders}) GROUP BY subject_id""",
        person_ids,
    )
    return {
        person_id: (
            aliases.get(person_id, ""),
            projects.get(person_id, ""),
            companies.get(person_id, ""),
            facts.get(person_id, ""),
        )
        for person_id in person_ids
    }


def _grouped_values(
    conn: sqlite3.Connection, query: str, values: list[int]
) -> dict[int, str]:
    return {int(key): str(value or "") for key, value in conn.execute(query, values)}


def relative_datetime(
    value: str | None, timezone_name: str, *, now: datetime | None = None
) -> str:
    """Present an evidence timestamp in the configured timezone without changing it."""
    if not value:
        return "—"
    try:
        when = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    zone = ZoneInfo(timezone_name)
    when = when.astimezone(zone)
    current = (now or datetime.now(zone)).astimezone(zone)
    if when.date() == current.date():
        return f"today {when:%H:%M}"
    if when.date().toordinal() == current.date().toordinal() - 1:
        return f"yesterday {when:%H:%M}"
    return f"{when:%d %b}" if when.year == current.year else f"{when:%d %b %Y}"


def person_overview(conn: sqlite3.Connection, person_id: int) -> dict[str, object]:
    """Read one compact canonical relationship overview for terminal presentation."""
    row = conn.execute(
        """SELECT p.canonical_name,p.telegram_username,pcs.last_contact_at,
                  COALESCE(pcs.current_summary,''),COALESCE(pcs.long_term_summary,'')
           FROM people AS p LEFT JOIN person_context_state AS pcs ON pcs.person_id=p.person_id
           WHERE p.person_id=?""",
        (person_id,),
    ).fetchone()
    if row is None:
        return {}
    tasks = conn.execute(
        """SELECT title FROM tasks WHERE related_person_id=? AND status IN ('open','waiting')
           ORDER BY updated_at DESC LIMIT 5""",
        (person_id,),
    ).fetchall()
    return {
        "name": str(row[0]),
        "username": row[1],
        "last_contact_at": row[2],
        "summary": str(row[3] or row[4] or "unknown / insufficient evidence"),
        "open_items": [str(item[0]) for item in tasks],
    }
