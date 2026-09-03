from __future__ import annotations

import json
import sqlite3

from rich.console import Console, Group
from rich.text import Text

from ..ai.analytics import fetch_findings, fetch_last_batch_diagnostics
from ..config import Settings
from ..intelligence import SearchResult
from .components import AppPanel as Panel
from .components import DataTable as Table
from .components import (
    print_notice,
    priority_text,
    safe_text,
    screen_header,
    status_text,
)


def show_context_graph(
    diagnostics: dict[str, int | float],
    console: Console,
    relationships_added: int | None = None,
) -> None:
    """Render graph health in product terms, without implementation stages."""
    screen_header(console, "Context graph", "People, projects, tasks, and evidence")
    table = Table(expand=True)
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    labels = {
        "entities": "Entities",
        "relationships": "Relationships",
        "orphan_tasks": "Orphan tasks",
        "orphan_important_messages": "Unlinked important messages",
        "merge_candidates": "Identity review candidates",
        "graph_link_candidates": "Graph link review candidates",
        "temporal_segment_anomalies": "Temporal segment anomalies",
        "orphan_conversation_segments": "Segments without task evidence",
        "unclassified_messages": "Unclassified messages",
        "route_archive_only": "Archived by route",
        "route_news_memory": "News-memory route",
        "route_operational": "Operational route",
        "route_state_change": "State-change route",
        "route_contextual_memory": "Contextual-memory route",
    }
    for key, label in labels.items():
        value = diagnostics.get(key, 0)
        table.add_row(label, f"{value:,}")
    if relationships_added is not None:
        table.add_row("Links added this pass", f"{relationships_added:,}")
    console.print(table)
    console.print()


def show_ai_findings(
    conn: sqlite3.Connection,
    console: Console,
    limit: int = 60,
) -> None:
    rows = fetch_findings(conn, limit)

    if not rows:
        print_notice(
            console,
            "Run AI analysis to create the first validated findings.",
            title="No AI findings yet",
            tone="info",
        )
        return

    screen_header(console, "Recent memory", f"{len(rows)} validated findings")
    table = Table(expand=True)
    table.add_column("Kind", width=15)
    table.add_column("Status", width=13)
    table.add_column("Owner", width=8)
    table.add_column("Due", width=11)
    table.add_column("Title", ratio=3)
    table.add_column("Details", ratio=3)
    table.add_column("Person / Company", ratio=1)
    table.add_column("Chat", ratio=1)
    table.add_column("Conf", justify="right", width=6)

    for row in rows:
        (
            kind,
            status,
            owner,
            due,
            title,
            details,
            person,
            company,
            confidence,
            chat,
            _,
        ) = row
        entity = person or company or "-"
        table.add_row(
            safe_text(kind, 15, single_line=True),
            status_text(status),
            safe_text(owner, 8, single_line=True),
            safe_text(due or "—"),
            safe_text(title, 90, single_line=True),
            safe_text(details, 150, single_line=True),
            safe_text(entity, 35, single_line=True),
            safe_text(chat, 35, single_line=True),
            f"{float(confidence):.0%}",
        )

    console.print(table)
    console.print()


def show_ai_diagnostics(
    conn: sqlite3.Connection,
    console: Console,
    limit: int = 20,
) -> None:
    rows = fetch_last_batch_diagnostics(conn, limit)

    if not rows:
        print_notice(
            console,
            "Completed and failed AI batches will appear here after analysis runs.",
            title="No AI batch history",
            tone="info",
        )
        return

    screen_header(console, "AI diagnostics", f"Latest {len(rows)} batches")
    table = Table(expand=True)
    table.add_column("ID", justify="right", width=5)
    table.add_column("Lane", width=7)
    table.add_column("Chat", ratio=2, no_wrap=True)
    table.add_column("Msgs", justify="right", width=5)
    table.add_column("Provider", width=12, no_wrap=True)
    table.add_column("Items", justify="right", width=9)
    table.add_column("Status", width=7)
    table.add_column("Summary / Error", ratio=4)

    for row in rows:
        (
            batch_id,
            lane,
            chat,
            message_count,
            provider,
            model,
            fallback,
            summary,
            returned,
            saved,
            rejected,
            error,
            status,
            _,
        ) = row

        text = error or summary or "(empty)"
        table.add_row(
            str(batch_id),
            safe_text(lane, 7, single_line=True),
            safe_text(chat, 45, single_line=True),
            str(message_count),
            safe_text(f"{provider}{'*' if fallback else ''}", 12, single_line=True),
            f"{returned or 0}/{saved or 0}/{rejected or 0}",
            status_text(status),
            safe_text(text, 110, single_line=True),
        )

    console.print(table)
    console.print()


def show_settings(settings: Settings, console: Console) -> None:
    screen_header(
        console,
        "Settings",
        "Read-only runtime configuration. Secret values are never displayed.",
    )
    table = Table()
    table.add_column("Area", style="bold")
    table.add_column("Value")
    table.add_row(
        "AI routing",
        safe_text(f"{settings.ai_routing_mode} registry"),
    )
    table.add_row(
        "Registry models",
        safe_text(
            f"Gemini {settings.gemini_primary_model} · {settings.gemini_secondary_model} · Groq {settings.groq_model}"
        ),
    )
    table.add_row(
        "Chat policy",
        "personal + groups"
        if settings.ai_include_groups
        else "personal only; bots always excluded",
    )
    table.add_row("Daily", f"up to {settings.ai_daily_max_messages:,} messages per run")
    table.add_row("History", "Analyze All History resumes automatically")
    table.add_row(
        "Retries",
        f"{settings.ai_max_retries} attempts; {settings.ai_retry_base_seconds}s base backoff",
    )
    table.add_row(
        "AI acceptance",
        f"auto ≥ {settings.ai_auto_accept_confidence:.0%}; review ≥ {settings.ai_review_confidence:.0%}",
    )
    if settings.configuration_warnings:
        table.add_row(
            "Compatibility", safe_text("; ".join(settings.configuration_warnings))
        )
    table.add_row(
        "Telegram sync",
        f"Large groups initial recent limit {settings.group_recent_limit:,}",
    )
    table.add_row(
        "Credentials", "Gemini and Groq keys are configured in .env (not displayed)"
    )
    console.print(table)
    console.print()


def show_tasks(
    conn: sqlite3.Connection,
    console: Console,
    *,
    view: str = "current",
    limit: int = 80,
) -> None:
    views = {
        "current": (
            "t.status IN ('open','waiting','blocked') "
            "AND (t.due_date IS NOT NULL OR t.updated_at >= datetime('now','-30 days'))",
            "current actionable work (due work or updated in the last 30 days)",
        ),
        "all": ("1=1", "all canonical tasks"),
        "waiting": ("t.status='waiting'", "waiting tasks"),
        "blocked": ("t.status='blocked'", "blocked tasks"),
        "done": ("t.status IN ('done','canceled')", "completed and canceled tasks"),
    }
    if view not in views:
        raise ValueError("task view must be current, all, waiting, blocked, or done")
    predicate, description = views[view]
    rows = conn.execute(
        f"""SELECT t.task_id, t.status, t.due_date, t.owner, t.title, COALESCE(p.canonical_name, ''), COALESCE(c.canonical_name, ''), t.confidence, t.manual_status_locked
           FROM tasks t LEFT JOIN people p ON p.person_id=t.related_person_id LEFT JOIN companies c ON c.company_id=t.related_company_id
           WHERE {predicate}
           ORDER BY CASE t.status WHEN 'open' THEN 0 WHEN 'waiting' THEN 1
                                WHEN 'blocked' THEN 2 ELSE 3 END,
                    CASE WHEN t.due_date IS NULL THEN 1 ELSE 0 END,
                    t.due_date, t.updated_at DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    if not rows:
        _show_empty_state(
            "Tasks",
            "No tasks yet. Analyze recent messages to build your action list.",
            console,
        )
        return

    screen_header(
        console,
        "Tasks",
        f"{len(rows)} shown · {description} · manual statuses override later AI inference",
    )
    compact = console.width < 90
    table = Table(expand=True)
    table.add_column("ID", justify="right", width=6)
    table.add_column("Status", width=9)
    table.add_column("Due", width=10)
    table.add_column("Task", ratio=3)
    if not compact:
        table.add_column("Entity", ratio=1)
        table.add_column("Conf", width=6)
        table.add_column("Source", width=7)
    for task_id, status, due, owner, title, person, company, confidence, locked in rows:
        task_text = safe_text(title, 120, single_line=True)
        task_text.append(f"  ({owner})", style="dim")
        entity = " · ".join(x for x in (person, company) if x) or "—"
        cells: list[str | Text] = [
            str(task_id),
            status_text(status),
            safe_text(due or "—"),
            task_text,
        ]
        if not compact:
            cells.extend(
                [
                    safe_text(entity, 50, single_line=True),
                    f"{float(confidence):.0%}",
                    Text("MANUAL", style="yellow")
                    if locked
                    else Text("AI", style="dim"),
                ]
            )
        table.add_row(*cells)
    console.print(table)
    console.print(
        "[dim]Views: current, all, waiting, blocked, done  ·  Actions: ID open|waiting|blocked|done|canceled  ·  ID dive for source-backed investigation[/dim]\n"
    )


def show_entities(
    conn: sqlite3.Connection,
    console: Console,
    entity_type: str | None = None,
    query: str = "",
    limit: int = 60,
) -> bool:
    search = " ".join(query.split())
    search_pattern = search.casefold()
    if entity_type is None:
        rows = conn.execute(
            """SELECT * FROM (
                 SELECT 'person', person_id, canonical_name, telegram_username FROM people
                  WHERE instr(lower(canonical_name), ?) > 0
                 UNION ALL SELECT 'company', company_id, canonical_name, '' FROM companies
                  WHERE instr(lower(canonical_name), ?) > 0
                 UNION ALL SELECT 'project', project_id, canonical_name, '' FROM projects
                  WHERE instr(lower(canonical_name), ?) > 0
               ) ORDER BY 1, 3 LIMIT ?""",
            (search_pattern, search_pattern, search_pattern, limit),
        ).fetchall()
        total = conn.execute(
            """SELECT COUNT(*) FROM (
                 SELECT person_id FROM people WHERE instr(lower(canonical_name), ?) > 0
                 UNION ALL SELECT company_id FROM companies WHERE instr(lower(canonical_name), ?) > 0
                 UNION ALL SELECT project_id FROM projects WHERE instr(lower(canonical_name), ?) > 0
               )""",
            (search_pattern, search_pattern, search_pattern),
        ).fetchone()[0]
        label = "Entities"
    else:
        table_name, id_column, username_column = {
            "person": ("people", "person_id", "telegram_username"),
            "company": ("companies", "company_id", "''"),
            "project": ("projects", "project_id", "''"),
        }[entity_type]
        rows = conn.execute(
            f"""SELECT ?, {id_column}, canonical_name, {username_column}
                FROM {table_name} WHERE instr(lower(canonical_name), ?) > 0
                ORDER BY canonical_name LIMIT ?""",
            (entity_type, search_pattern, limit),
        ).fetchall()
        total = conn.execute(
            f"SELECT COUNT(*) FROM {table_name} WHERE instr(lower(canonical_name), ?) > 0",
            (search_pattern,),
        ).fetchone()[0]
        label = f"{entity_type.title()}s"

    if not rows:
        _show_empty_state(
            label,
            f"No canonical {label.lower()} are available yet.",
            console,
        )
        return False

    pending = conn.execute(
        "SELECT COUNT(*) FROM entity_merge_candidates WHERE status='pending'"
    ).fetchone()[0]
    screen_header(
        console,
        label,
        f"{len(rows)} of {total} canonical records · choose the ID shown below",
    )
    table = Table(expand=True)
    table.add_column("Type", width=10)
    table.add_column("ID", justify="right", width=6)
    table.add_column("Canonical name", ratio=2)
    table.add_column("Telegram", ratio=1)
    for entity_type, entity_id, name, username in rows:
        table.add_row(
            safe_text(entity_type, 10, single_line=True),
            str(entity_id),
            safe_text(name, 100, single_line=True),
            safe_text(f"@{username}" if username else "—", 40, single_line=True),
        )
    console.print(table)
    if pending:
        console.print(
            f"[dim]{pending} ambiguous merge candidate(s) await explicit review.[/dim]"
        )
    if total > len(rows):
        console.print("[dim]Refine the search to narrow this bounded list.[/dim]")
    console.print()
    return True


def show_people(
    conn: sqlite3.Connection, console: Console, query: str = "", limit: int = 40
) -> list[int]:
    """Render a bounded, person-only discovery list from canonical profile state."""
    search = " ".join(query.split()).casefold()
    rows = conn.execute(
        """SELECT p.person_id,p.canonical_name,p.telegram_username,p.status,
                  pcs.last_contact_at,
                  EXISTS(SELECT 1 FROM entity_aliases AS a WHERE a.entity_type='person'
                    AND a.entity_id=p.person_id AND instr(a.normalized_alias,?)>0),
                  EXISTS(SELECT 1 FROM person_project_context AS pp JOIN projects AS pr
                    ON pr.project_id=pp.project_id WHERE pp.person_id=p.person_id
                    AND instr(lower(pr.canonical_name),?)>0),
                  EXISTS(SELECT 1 FROM context_facts AS f WHERE f.subject_type='person'
                    AND f.subject_id=p.person_id AND f.is_current=1
                    AND (instr(lower(f.predicate),?)>0 OR instr(lower(f.value_json),?)>0))
           FROM people AS p LEFT JOIN person_context_state AS pcs ON pcs.person_id=p.person_id
           WHERE ?='' OR instr(lower(p.canonical_name),?)>0 OR instr(lower(COALESCE(p.telegram_username,'')),?)>0
              OR EXISTS(SELECT 1 FROM entity_aliases AS a WHERE a.entity_type='person'
                   AND a.entity_id=p.person_id AND instr(a.normalized_alias,?)>0)
              OR EXISTS(SELECT 1 FROM person_project_context AS pp JOIN projects AS pr
                   ON pr.project_id=pp.project_id WHERE pp.person_id=p.person_id
                   AND instr(lower(pr.canonical_name),?)>0)
              OR EXISTS(SELECT 1 FROM context_facts AS f WHERE f.subject_type='person'
                   AND f.subject_id=p.person_id AND f.is_current=1
                   AND (instr(lower(f.predicate),?)>0 OR instr(lower(f.value_json),?)>0))
           ORDER BY CASE WHEN instr(lower(p.canonical_name),?)>0 THEN 0
                         WHEN instr(lower(COALESCE(p.telegram_username,'')),?)>0 THEN 1
                         WHEN EXISTS(SELECT 1 FROM entity_aliases AS a WHERE a.entity_type='person'
                              AND a.entity_id=p.person_id AND instr(a.normalized_alias,?)>0) THEN 2
                         ELSE 3 END,
                    pcs.last_contact_at DESC,p.canonical_name LIMIT ?""",
        (
            search,
            search,
            search,
            search,
            search,
            search,
            search,
            search,
            search,
            search,
            search,
            search,
            search,
            search,
            limit,
        ),
    ).fetchall()
    if not rows:
        _show_empty_state("People", "No canonical people match that search.", console)
        return []
    screen_header(console, "People", "Select a person to understand the relationship.")
    table = Table(expand=True)
    table.add_column("ID", width=6, justify="right")
    table.add_column("Person", ratio=2)
    table.add_column("Telegram", ratio=1)
    table.add_column("Last contact", width=25)
    for person_id, name, username, status, last_contact, *_ in rows:
        label = safe_text(name, 100, single_line=True)
        label.append(f" · {status}", style="dim")
        table.add_row(
            str(person_id),
            label,
            safe_text(f"@{username}" if username else "—", 40),
            safe_text(last_contact or "—", 25, single_line=True),
        )
    console.print(table)
    console.print(
        "[dim]Search name, alias, Telegram account, project, company, or known context.[/dim]\n"
    )
    return [int(row[0]) for row in rows]


def show_daily_brief(brief: dict, console: Console) -> None:
    def brief_panel(
        title: str,
        items: list[dict],
        border_style: str,
        *,
        task: bool = True,
    ) -> Panel:
        if not items:
            body: Group | Text = Text("Nothing here", style="dim")
        else:
            lines: list[Text] = []
            for item in items[:15] if task else items[:12]:
                line = Text("• ", style="bright_black")
                if task:
                    line.append(f"#{item['task_id']} ", style="bold cyan")
                    line.append(str(item.get("title", ""))[:180])
                    metadata = str(item.get("status", "unknown"))
                    if item.get("due_date"):
                        metadata += f" · due {item['due_date']}"
                    line.append(f"\n  {metadata}", style="dim")
                else:
                    line.append(str(item.get("title", ""))[:120], style="bold")
                    details = str(item.get("details", ""))
                    if details:
                        line.append(f"\n  {details[:220]}", style="dim")
                lines.append(line)
            body = Group(*lines)
        return Panel(
            body,
            title=f"{title}  {len(items)}",
            border_style=border_style,
            padding=(0, 1),
        )

    screen_header(
        console,
        "Daily brief",
        "Actions first, followed by changes, risks, and durable facts.",
    )
    panels = [
        brief_panel("Open & waiting", brief["open_tasks"], "yellow"),
        brief_panel("New tasks", brief["new_tasks"], "cyan"),
        brief_panel("Follow-ups", brief.get("follow_ups", []), "red", task=False),
        brief_panel(
            "Projects going cold",
            brief.get("stale_projects", []),
            "red",
            task=False,
        ),
        brief_panel("Completed / updated", brief["updates"], "green"),
        brief_panel(
            "People requiring attention",
            brief.get("people_attention", []),
            "yellow",
            task=False,
        ),
        brief_panel("Important facts", brief["facts"], "magenta", task=False),
    ]
    if console.width >= 100:
        grid = Table.grid(expand=True, padding=(0, 1))
        grid.add_column(ratio=1)
        grid.add_column(ratio=1)
        for index in range(0, len(panels), 2):
            grid.add_row(*panels[index : index + 2])
        console.print(grid)
    else:
        console.print(Group(*panels))
    console.print()


def show_search_results(rows: list[tuple], query: str, console: Console) -> None:
    if not query:
        print_notice(
            console,
            "Enter a query to search operational tasks, memory, and summaries.",
            title="Search memory",
            tone="warning",
        )
        return
    if not rows:
        _show_empty_state(
            "Search memory", f"No source-backed results found for {query!r}.", console
        )
        return
    screen_header(console, "Search memory", f"{len(rows)} results for {query!r}")
    table = Table(expand=True)
    table.add_column("Type", width=9)
    table.add_column("ID", width=7)
    table.add_column("Title", ratio=2)
    table.add_column("Details", ratio=3)
    table.add_column("Updated", width=24)
    for kind, source_id, title, details, updated in rows:
        table.add_row(
            safe_text(kind, 9, single_line=True),
            safe_text(source_id),
            safe_text(title, 100, single_line=True),
            safe_text(details, 200, single_line=True),
            safe_text(updated or "—", 24, single_line=True),
        )
    console.print(table)
    console.print()


def show_retrieval_results(
    rows: list[SearchResult], query: str, console: Console
) -> None:
    if not rows:
        _show_empty_state(
            "Search memory",
            f"No source-backed results found for {query!r}.",
            console,
        )
        return
    screen_header(console, "Search memory", f"{len(rows)} results for {query!r}")
    compact = console.width < 90
    table = Table(expand=True)
    table.add_column("Type", width=10)
    table.add_column("Title", ratio=2)
    table.add_column("Snippet", ratio=3)
    if not compact:
        table.add_column("Date", width=18)
        table.add_column("Score", width=6)
    for row in rows:
        cells: list[str | Text] = [
            safe_text(row.result_type.upper(), 10, single_line=True),
            safe_text(row.title, 100, single_line=True),
            safe_text(row.snippet, 220, single_line=True),
        ]
        if not compact:
            cells.extend([safe_text(row.date or "—", 18), str(int(row.score))])
        table.add_row(*cells)
    console.print(table)
    console.print()


def show_result_detail(
    conn: sqlite3.Connection, row: SearchResult, console: Console
) -> None:
    """Render one selected result with its stable citation and exact raw source when available."""
    screen_header(console, "Evidence detail", row.citation)
    if row.chat_id is not None and row.message_id is not None:
        message = conn.execute(
            """SELECT COALESCE(c.title, CAST(m.chat_id AS TEXT)),m.date,m.text
               FROM messages AS m LEFT JOIN chats AS c ON c.chat_id=m.chat_id
               WHERE m.chat_id=? AND m.message_id=?""",
            (row.chat_id, row.message_id),
        ).fetchone()
        if message is not None:
            chat, when, text = message
            console.print(
                Panel(
                    safe_text(text, 4_000),
                    title=f"{chat} · {when or 'undated'}",
                    border_style="blue",
                )
            )
            console.print()
            return
    if row.task_id is not None:
        task = conn.execute(
            "SELECT title,details,status,due_date FROM tasks WHERE task_id=?",
            (row.task_id,),
        ).fetchone()
        if task is not None:
            title, details, status, due = task
            console.print(
                Panel(
                    safe_text(
                        f"{title}\n\nStatus: {status}\nDue: {due or '—'}\n\n{details or 'No additional detail.'}",
                        4_000,
                    ),
                    title=row.citation,
                    border_style="cyan",
                )
            )
            console.print()
            return
    console.print(
        Panel(safe_text(row.snippet, 2_000), title=row.citation, border_style="blue")
    )
    console.print()


def show_ask_answer(answer: str, sources: list[SearchResult], console: Console) -> None:
    screen_header(
        console,
        "Ask Alex Memory",
        "Grounded answer from bounded canonical context and retrieved evidence.",
    )
    console.print(Panel(safe_text(answer), title="Answer", border_style="cyan"))
    if sources:
        table = Table(title=f"Sources  {len(sources)}", expand=True)
        table.add_column("#", width=4, justify="right")
        table.add_column("Evidence", ratio=2)
        table.add_column("Date", width=18)
        for index, source in enumerate(sources, start=1):
            table.add_row(
                str(index),
                safe_text(source.citation, 120, single_line=True),
                safe_text(source.date or "—", 18),
            )
        console.print(table)
    console.print()


def show_attention(rows: list[SearchResult], console: Console) -> None:
    if not rows:
        _show_empty_state(
            "Today",
            "Nothing currently needs attention.",
            console,
            border_style="green",
        )
        return
    screen_header(
        console,
        "Today",
        f"{len(rows)} source-backed items ranked by urgency.",
    )
    table = Table(expand=True)
    table.add_column("Priority", width=9)
    table.add_column("Type", width=10)
    table.add_column("Item", ratio=3)
    table.add_column("Why", ratio=2)
    for row in rows:
        priority = (
            "critical" if row.score >= 95 else "high" if row.score >= 85 else "normal"
        )
        table.add_row(
            priority_text(priority),
            safe_text(row.result_type, 10, single_line=True),
            safe_text(row.title, 120, single_line=True),
            safe_text(row.snippet, 160, single_line=True),
        )
    console.print(table)
    console.print()


def show_follow_ups(conn: sqlite3.Connection, console: Console) -> None:
    rows = conn.execute(
        "SELECT follow_up_id,title,status,priority,due_at,reason FROM follow_ups WHERE status IN ('open','snoozed') ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'high' THEN 1 ELSE 2 END,due_at"
    ).fetchall()
    if not rows:
        _show_empty_state(
            "Follow-ups",
            "No open or snoozed follow-ups.",
            console,
            border_style="green",
        )
        return
    screen_header(
        console,
        "Follow-ups",
        f"{len(rows)} open or snoozed reminders, ordered by priority and due date.",
    )
    table = Table(expand=True)
    table.add_column("ID", width=6)
    table.add_column("Priority", width=9)
    table.add_column("Due", width=12)
    table.add_column("Follow-up", ratio=3)
    table.add_column("Reason", ratio=2)
    for follow_id, title, _status, priority, due, reason in rows:
        table.add_row(
            str(follow_id),
            priority_text(priority),
            safe_text(due or "—", 12),
            safe_text(title, 160, single_line=True),
            safe_text(reason, 180, single_line=True),
        )
    console.print(table)
    console.print()


def show_follow_up_detail(
    conn: sqlite3.Connection, follow_up_id: int, console: Console
) -> bool:
    """Open the task or exact source evidence behind one follow-up."""
    row = conn.execute(
        """SELECT title,reason,due_at,task_id,source_chat_id,source_message_id
           FROM follow_ups WHERE follow_up_id=?""",
        (follow_up_id,),
    ).fetchone()
    if row is None:
        print_notice(
            console,
            "That follow-up was not found.",
            title="Follow-up",
            tone="warning",
        )
        return False
    title, reason, due, task_id, chat_id, message_id = row
    show_result_detail(
        conn,
        SearchResult(
            "follow-up",
            str(title),
            str(reason),
            str(due) if due else None,
            0,
            chat_id=int(chat_id) if chat_id is not None else None,
            message_id=int(message_id) if message_id is not None else None,
            task_id=int(task_id) if task_id is not None else None,
            source_id=follow_up_id,
        ),
        console,
    )
    return True


def show_review_queue(conn: sqlite3.Connection, console: Console) -> None:
    rows = conn.execute(
        """SELECT review_id,review_type,subject_type,confidence,created_at,payload_json
           FROM review_queue WHERE status='pending' ORDER BY created_at DESC LIMIT 60"""
    ).fetchall()
    if not rows:
        _show_empty_state(
            "Review queue",
            "No ambiguous AI findings are waiting for review.",
            console,
            border_style="green",
        )
        return
    screen_header(
        console,
        "Review queue",
        f"{len(rows)} ambiguous findings require a manual decision.",
    )
    table = Table(expand=True)
    table.add_column("ID", width=6)
    table.add_column("Type")
    table.add_column("Subject")
    table.add_column("Rationale / evidence", ratio=2)
    table.add_column("Confidence")
    table.add_column("Created")
    for row in rows:
        table.add_row(
            str(row[0]),
            safe_text(row[1], single_line=True),
            safe_text(row[2], single_line=True),
            safe_text(_review_details(row[5]), 160, single_line=True),
            f"{float(row[3]):.0%}" if row[3] is not None else "—",
            safe_text(row[4], 24, single_line=True),
        )
    console.print(table)
    console.print()


def show_review_detail(
    conn: sqlite3.Connection, review_id: int, console: Console
) -> bool:
    """Show the full review payload and exact linked message before a manual decision."""
    row = conn.execute(
        """SELECT review_type,subject_type,subject_id,confidence,created_at,payload_json
           FROM review_queue WHERE review_id=? AND status='pending'""",
        (review_id,),
    ).fetchone()
    if row is None:
        print_notice(
            console,
            "That pending review item was not found.",
            title="Review",
            tone="warning",
        )
        return False
    review_type, subject_type, subject_id, confidence, created_at, payload_json = row
    try:
        payload = json.loads(payload_json)
    except (TypeError, json.JSONDecodeError):
        payload = {"payload": "Invalid review payload"}
    screen_header(
        console,
        f"Review #{review_id}",
        f"{review_type} · {subject_type} {subject_id or '—'} · {confidence or '—'} · {created_at}",
    )
    console.print(
        Panel(
            safe_text(json.dumps(payload, ensure_ascii=False, indent=2), 4_000),
            title="Proposed change and rationale",
            border_style="yellow",
        )
    )
    if isinstance(payload, dict):
        chat_id = payload.get("chat_id", payload.get("source_chat_id"))
        message_id = payload.get("message_id", payload.get("source_message_id"))
        if isinstance(chat_id, int) and isinstance(message_id, int):
            message = conn.execute(
                "SELECT date,text FROM messages WHERE chat_id=? AND message_id=?",
                (chat_id, message_id),
            ).fetchone()
            if message is not None:
                console.print(
                    Panel(
                        safe_text(message[1], 4_000),
                        title=f"Source evidence · chat {chat_id} / msg {message_id} · {message[0]}",
                        border_style="blue",
                    )
                )
    console.print()
    return True


def _review_details(payload_json: str) -> str:
    """Summarize only operator-relevant provenance from an untrusted payload."""
    try:
        payload = json.loads(payload_json)
    except (TypeError, json.JSONDecodeError):
        return "Invalid review payload"
    if not isinstance(payload, dict):
        return "Invalid review payload"
    parts = [
        str(payload[key])
        for key in ("reason", "candidate_project_id", "item_id", "task_id")
        if payload.get(key) is not None
    ]
    chat_id, message_id = payload.get("chat_id"), payload.get("message_id")
    if chat_id is not None or message_id is not None:
        parts.append(
            f"chat {chat_id if chat_id is not None else '—'} / msg {message_id if message_id is not None else '—'}"
        )
    return " · ".join(parts) or "Manual decision required"


def show_chat_policies(
    conn: sqlite3.Connection, console: Console, query: str = "", limit: int = 60
) -> bool:
    search = " ".join(query.split())
    search_pattern = search.casefold()
    rows = conn.execute(
        """SELECT c.chat_id,COALESCE(c.title,CAST(c.chat_id AS TEXT)),
                   COALESCE(c.chat_type,'unknown'),COALESCE(p.mode,'auto'),
                   COALESCE(p.reason,'')
            FROM chats AS c LEFT JOIN chat_ai_policy AS p ON p.chat_id=c.chat_id
            WHERE COALESCE(c.is_bot,0)=0
              AND (instr(lower(COALESCE(c.title,'')), ?) > 0 OR instr(CAST(c.chat_id AS TEXT), ?) > 0)
            ORDER BY c.title,c.chat_id LIMIT ?""",
        (search_pattern, search, limit),
    ).fetchall()
    total = conn.execute(
        """SELECT COUNT(*) FROM chats AS c
           WHERE COALESCE(c.is_bot,0)=0
             AND (instr(lower(COALESCE(c.title,'')), ?) > 0 OR instr(CAST(c.chat_id AS TEXT), ?) > 0)""",
        (search_pattern, search),
    ).fetchone()[0]
    if not rows:
        _show_empty_state("Chat policy", "No archived chats are available.", console)
        return False
    screen_header(
        console,
        "Chat analysis policy",
        f"{len(rows)} of {total} chats · ARCHIVE ONLY stays local; NEWS ONLY sends classified external news only.",
    )
    table = Table(expand=True)
    table.add_column("Chat ID", justify="right", width=12)
    table.add_column("Chat", ratio=2)
    table.add_column("Type", width=10)
    table.add_column("Policy", width=15)
    table.add_column("Reason", ratio=2)
    for chat_id, title, chat_type, mode, reason in rows:
        table.add_row(
            str(chat_id),
            safe_text(title, 80, single_line=True),
            safe_text(chat_type, 10, single_line=True),
            safe_text(_chat_policy_label(mode), 15, single_line=True),
            safe_text(reason or "—", 80, single_line=True),
        )
    console.print(table)
    if total > len(rows):
        console.print("[dim]Refine the search to narrow this bounded list.[/dim]")
    console.print()
    return True


def _chat_policy_label(mode: str) -> str:
    return {
        "auto": "AUTOMATIC",
        "include": "FULL",
        "classify_only": "ARCHIVE ONLY",
        "news_only": "NEWS ONLY",
        "exclude": "IGNORE",
    }.get(mode, mode.replace("_", " ").upper())


def show_temporal_conflicts(conflicts: list[dict], console: Console) -> None:
    """Render pending fact conflicts with both competing, source-backed values."""
    if not conflicts:
        return
    screen_header(
        console,
        "Temporal fact conflicts",
        f"{len(conflicts)} fact values require an explicit decision.",
    )
    table = Table(expand=True)
    table.add_column("ID", width=6)
    table.add_column("Fact", ratio=2)
    table.add_column("Current value", ratio=2)
    table.add_column("Observed value", ratio=2)
    table.add_column("Evidence", ratio=2)
    for conflict in conflicts:
        evidence = (
            f"current {conflict['existing_source_chat_id'] or '—'}/"
            f"{conflict['existing_source_message_id'] or '—'}\n"
            f"observed {conflict['observation_source_chat_id'] or '—'}/"
            f"{conflict['observation_source_message_id'] or '—'}"
        )
        table.add_row(
            str(conflict["conflict_id"]),
            safe_text(
                f"{conflict['subject_type']} {conflict['subject_id']} · {conflict['predicate']}",
                80,
                single_line=True,
            ),
            safe_text(str(conflict["existing_value"]), 100, single_line=True),
            safe_text(str(conflict["observation_value"]), 100, single_line=True),
            safe_text(evidence, 100),
        )
    console.print(table)
    console.print()


def show_context_view(context, title: str, console: Console, max_chars: int) -> None:
    screen_header(
        console,
        title,
        f"Bounded model context · maximum {max_chars:,} characters",
    )
    console.print(
        Panel(
            safe_text(context.render(max_chars)),
            title="Source-aware context",
            border_style="blue",
        )
    )
    console.print()


def show_policy(settings: Settings, console: Console) -> None:
    screen_header(
        console,
        "Telegram sync policy",
        "First-import limits protect runtime and keep ingestion bounded.",
    )
    table = Table(expand=True)
    table.add_column("Dialog type")
    table.add_column("First import")
    table.add_column("Later runs")

    table.add_row("Personal chat", status_text("complete"), "Only new messages")
    table.add_row(
        f"Group ≤ {settings.group_full_threshold:,}",
        status_text("complete"),
        "Only new messages",
    )
    table.add_row(
        f"Group > {settings.group_full_threshold:,}",
        Text(f"LATEST {settings.group_recent_limit:,}", style="yellow"),
        "Only new messages",
    )
    table.add_row("Broadcast channel", Text("SKIP", style="red"), "Skip")
    table.add_row("Bot chat", Text("ARCHIVE ONLY", style="yellow"), "Never sent to AI")

    console.print(table)
    console.print()


def _show_empty_state(
    title: str,
    message: str,
    console: Console,
    border_style: str = "blue",
) -> None:
    if border_style == "green":
        print_notice(console, message, title=title, tone="success")
    else:
        print_notice(console, message, title=title, tone="info")
