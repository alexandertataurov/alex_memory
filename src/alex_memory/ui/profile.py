"""Canonical entity-profile rendering for the terminal UI."""

from __future__ import annotations

from rich.console import Console, Group

from .components import AppPanel as Panel
from .components import DataTable as Table
from .components import notice, print_notice, safe_text, screen_header, status_text


def show_profile(
    data: dict, entity_type: str, console: Console, *, section: str = "overview"
) -> None:
    """Render one canonical profile and its bounded operational context."""
    if not data:
        print_notice(
            console,
            "No matching canonical entity was found.",
            title=f"{entity_type.title()} profile",
            tone="warning",
        )
        return
    if entity_type == "person":
        _show_person_profile(data, console, section)
        return
    entity, tasks, memories = data["entity"], data["tasks"], data["memories"]
    name = entity[1]
    screen_header(
        console,
        f"{entity_type.title()} profile",
        "Canonical state and durable memory linked to this entity.",
    )
    identity = safe_text(name, 160, style="bold white", single_line=True)
    identity.append(f"\n{entity_type.title()} · canonical record", style="dim")
    console.print(Panel(identity, title="Identity", border_style="cyan"))
    if entity_type == "person" and data.get("conversation"):
        _show_person_conversation(data, console)
    _show_tasks(tasks, console)
    _show_connections(data.get("connections", []), console)
    _show_timeline(data.get("timeline", []), console)
    _show_memories(memories, console)
    console.print()


def _show_connections(connections: list, console: Console) -> None:
    if not connections:
        return
    table = Table(expand=True)
    table.add_column("Connected entity", ratio=3)
    table.add_column("Relationship", ratio=2)
    table.add_column("Evidence", ratio=2)
    for connection in connections:
        table.add_row(
            safe_text(connection.title, 100, single_line=True),
            safe_text(connection.snippet, 80, single_line=True),
            safe_text(connection.citation, 80, single_line=True),
        )
    console.print(table)


def _show_timeline(timeline: list[tuple], console: Console) -> None:
    if not timeline:
        return
    table = Table(title="Recent source-backed events", expand=True)
    table.add_column("When", width=24)
    table.add_column("Event", ratio=3)
    table.add_column("Evidence", ratio=2)
    for title, description, occurred_at, chat_id, message_id in timeline:
        table.add_row(
            safe_text(occurred_at, 24, single_line=True),
            safe_text(
                f"{title}: {description}" if description else title,
                180,
                single_line=True,
            ),
            safe_text(
                "[E]" if chat_id is not None and message_id is not None else "—",
                80,
                single_line=True,
            ),
        )
    console.print(table)


def _show_person_profile(data: dict, console: Console, section: str) -> None:
    entity = data["entity"]
    name, telegram_id, username, status = entity[1], entity[2], entity[3], entity[4]
    screen_header(
        console, "Person profile", "Canonical state with exact source evidence."
    )
    if section == "overview":
        _show_operational_overview(data, console)
        console.print()
        return
    lines = [safe_text(name, 160, style="bold white", single_line=True)]
    accounts = [
        f"Telegram ID: {telegram_id}" if telegram_id else None,
        f"@{username}" if username else None,
    ]
    aliases = data.get("aliases", [])
    identity = data.get("identity", {})
    lines.append(
        safe_text(
            " · ".join(part for part in accounts if part) or "No linked account",
            style="dim",
        )
    )
    if aliases:
        lines.append(safe_text("Aliases: " + ", ".join(aliases), 400, single_line=True))
    lines.append(status_text(status))
    if identity.get("direct_chat_owned"):
        lines.append(
            safe_text("Direct Telegram chat is canonically owned.", style="dim")
        )
    if identity.get("pending_reviews"):
        lines.append(
            safe_text(
                f"{identity['pending_reviews']} identity or claim review item(s) pending.",
                style="yellow",
            )
        )
    console.print(Panel(Group(*lines), title="Identity", border_style="cyan"))
    contact = data.get("contact", {})
    if contact.get("profile_summary"):
        summary = [safe_text(contact["profile_summary"], 950)]
        if contact.get("profile_summary_updated_at"):
            summary.append(
                safe_text(
                    f"Updated: {contact['profile_summary_updated_at']}", style="dim"
                )
            )
        console.print(
            Panel(
                Group(*summary), title="Current AI summary", border_style="bright_blue"
            )
        )
    elif contact.get("current_summary") or contact.get("long_term_summary"):
        console.print(
            Panel(
                Group(
                    *(
                        safe_text(value, 800)
                        for value in (
                            contact.get("current_summary"),
                            contact.get("long_term_summary"),
                        )
                        if value
                    )
                ),
                title="Current context",
                border_style="bright_blue",
            )
        )
    if section == "contact":
        _show_contact_briefing(data.get("contact_briefing", {}), console)
    elif section == "scan_status":
        scan = data.get("scan_status", {})
        if not scan.get("direct_chat_available"):
            detail = "Unavailable: no canonically owned direct Telegram chat is linked to this person."
        elif not (scan.get("done") or scan.get("pending") or scan.get("failed")):
            eligible = int(scan.get("eligible_messages", 0))
            detail = (
                f"Ready: {eligible} eligible messages. Choose Deep Scan to process a bounded window."
                if eligible
                else "No eligible unscanned messages remain. New evidence can be scanned after it is projected."
            )
        else:
            detail = f"Last completed: {scan.get('last_completed_at') or 'unknown'}"
        console.print(
            Panel(
                safe_text(
                    f"AI completed {scan.get('completed_messages', 0)} / {scan.get('eligible_messages', 0)} evidence messages\n"
                    f"{scan.get('done', 0)} scanned · {scan.get('pending', 0)} pending · "
                    f"{scan.get('failed', 0)} failed · extractor v{scan.get('extractor_version', '—')}\n"
                    + detail
                ),
                title="Deep Scan history",
                border_style="magenta",
            )
        )
    elif section == "loops":
        _show_records(
            data.get("tasks", []), "Tasks and promises", "status", "title", console
        )
        _show_records(
            data.get("follow_ups", []) + data.get("open_loops", []),
            "Waiting and follow-ups",
            "status",
            "title",
            console,
        )
    elif section == "projects":
        _show_projects(data.get("projects", []), console)
    elif section == "context":
        _show_profile_facts(data.get("facts", []) + data.get("changes", []), console)
        _show_records(
            [
                item
                for item in data.get("profile_claims", [])
                if item.get("assertion_kind") == "direct"
            ],
            "Evidence-backed Deep Profile details",
            "category",
            "title",
            console,
        )
    elif section == "private":
        private_details = data.get("private_details", [])
        if private_details:
            _show_records(
                private_details,
                "Private details (direct evidence only)",
                "category",
                "title",
                console,
            )
        else:
            console.print(
                safe_text("unknown / insufficient direct private evidence", style="dim")
            )
    elif section == "uncertain":
        uncertain = data.get("uncertain", [])
        if uncertain:
            _show_records(
                uncertain,
                "Third-party claims and supported inferences",
                "assertion_kind",
                "title",
                console,
            )
        else:
            console.print(
                safe_text("No uncertain profile claims are recorded.", style="dim")
            )
    elif section == "connections":
        _show_records(
            data.get("relationships", []),
            "Direct canonical connections",
            "relationship_type",
            "other_name",
            console,
        )
    elif section == "timeline":
        _show_records(
            data.get("events", []), "Important events", "occurred_at", "title", console
        )
        _show_conversation_periods_dict(data.get("segments", []), console)
    elif section == "communication":
        _show_stats(data.get("stats", {}), console, compact=False)
    elif section == "evidence":
        _show_records(
            data.get("facts", [])
            + data.get("relationships", [])
            + data.get("tasks", [])
            + data.get("events", []),
            "Exact supporting evidence",
            "title",
            "details",
            console,
        )
    console.print()


def _show_operational_overview(data: dict, console: Console) -> None:
    """Render the five requested dashboard blocks from the existing profile package."""
    overview = data.get("overview", {})
    identity = overview.get("identity", {})
    identity_lines = [
        safe_text(str(identity.get("name") or "unknown"), 160, style="bold white"),
        status_text(identity.get("status") or "unknown"),
        safe_text(
            "Direct Telegram chat is canonically owned."
            if identity.get("direct_chat_owned")
            else "Direct Telegram chat is unknown or not canonically owned.",
            style="dim",
        ),
    ]
    aliases = identity.get("aliases", [])
    if aliases:
        identity_lines.append(
            safe_text("Aliases: " + ", ".join(map(str, aliases)), 400, style="dim")
        )
    if identity.get("pending_reviews"):
        identity_lines.append(
            safe_text(
                f"{identity['pending_reviews']} review item(s) pending.", style="yellow"
            )
        )
    console.print(
        Panel(Group(*identity_lines), title="Identity / status", border_style="cyan")
    )
    brief = (
        "\n".join(overview.get("brief_lines", [])) or "unknown / insufficient evidence"
    )
    console.print(
        Panel(safe_text(brief, 700), title="Brief", border_style="bright_blue")
    )
    _show_overview_records(
        overview.get("needs_attention", []), "Needs attention", console
    )
    _show_overview_records(
        overview.get("active_threads", []), "Active threads / projects", console
    )
    health = overview.get("relationship_memory_health", {})
    lines = [
        f"Relationship: {health.get('relationship_type') or 'unknown'}",
        f"Last contact: {health.get('last_contact_at') or 'unknown'}",
        f"Memory: {health.get('context_state') or 'unknown'}",
    ]
    eligible = health.get("eligible_messages")
    if eligible:
        lines.append(
            f"Profile coverage: {health.get('completed_messages', 0)} / {eligible} analyzed"
        )
    profile_work = _profile_work_status(health)
    if profile_work:
        lines.append(f"Profile work: {profile_work}")
    console.print(
        Panel(
            safe_text("\n".join(lines), 700),
            title="Relationship + memory health",
            border_style="green",
        )
    )


def _profile_work_status(health: dict) -> str:
    """Summarize only durable work attached to the selected person."""
    states = (
        ("queued", health.get("pending_messages", 0)),
        ("analyzing", health.get("running_messages", 0)),
        ("retryable", health.get("failed_messages", 0)),
        ("completed", health.get("completed_messages", 0)),
    )
    return " · ".join(f"{int(count)} {label}" for label, count in states if count)


def _show_overview_records(records: list[dict], title: str, console: Console) -> None:
    if not records:
        console.print(
            Panel(
                safe_text("unknown / insufficient evidence", style="dim"),
                title=title,
                border_style="yellow",
            )
        )
        return
    lines = []
    for record in records[:6]:
        label = (
            record.get("display_value")
            or record.get("title")
            or record.get("name")
            or "—"
        )
        state = (
            record.get("display_label")
            or record.get("action_state")
            or record.get("status")
            or record.get("loop_type")
            or "record"
        )
        evidence = " [E]" if record.get("evidence") else ""
        lines.append(f"• {state}: {label}{evidence}")
    console.print(
        Panel(safe_text("\n".join(lines), 700), title=title, border_style="yellow")
    )


def _show_records(
    records: list[dict], title: str, left: str, right: str, console: Console
) -> None:
    if not records:
        return
    table = Table(title=title, expand=True)
    table.add_column("Type", width=20)
    table.add_column("Detail", ratio=4)
    table.add_column("Evidence", width=22)
    for record in records:
        value = record.get(right, "—")
        if isinstance(value, (dict, list)):
            value = (
                ", ".join(f"{key}={item}" for key, item in value.items())
                if isinstance(value, dict)
                else str(value)
            )
        evidence = "[E]" if record.get("evidence") else "—"
        table.add_row(
            safe_text(record.get(left, "—"), 80, single_line=True),
            safe_text(value or "—", 230, single_line=True),
            safe_text(evidence, 22, single_line=True),
        )
    console.print(table)


def _show_profile_facts(facts: list[dict], console: Console) -> None:
    """Group already-presented canonical facts without exposing schema labels."""
    sections: dict[str, list[dict]] = {}
    for fact in facts:
        section = str(fact.get("display_section") or "Profile")
        temporal = str(fact.get("temporal_state") or "")
        sections.setdefault(
            f"{temporal} — {section}" if temporal else section, []
        ).append(fact)
    for section, records in sections.items():
        _show_records(records, section, "display_label", "display_value", console)


def _show_projects(projects: list[dict], console: Console) -> None:
    if not projects:
        return
    table = Table(title="Companies and projects", expand=True)
    table.add_column("Project", ratio=2)
    table.add_column("Status", width=14)
    table.add_column("Context", ratio=3)
    table.add_column("Evidence", width=22)
    for project in projects:
        evidence = "[E]" if project.get("evidence") else "—"
        table.add_row(
            safe_text(project["name"], 100, single_line=True),
            status_text(project["status"]),
            safe_text(project.get("summary") or "—", 180, single_line=True),
            safe_text(evidence, 22, single_line=True),
        )
    console.print(table)


def _show_contact_briefing(briefing: dict, console: Console) -> None:
    """Render a deterministic pre-contact briefing without inventing missing context."""
    last = briefing.get("last_interaction")
    if last:
        record, evidence = last["record"], last["evidence"]
        label = (
            record.get("title")
            or record.get("predicate")
            or "Source-backed profile record"
        )
        text = safe_text(str(label), 320, single_line=True)
        text.append(
            f"\n[E] · {evidence['date']}: {evidence['text'][:220]}", style="dim"
        )
        console.print(
            Panel(text, title="Last source-backed interaction", border_style="green")
        )
    else:
        console.print(
            notice(
                "Unknown — no exact-evidence profile interaction is available.",
                title="Last source-backed interaction",
            )
        )
    _show_brief_records(
        briefing.get("waiting_from_them", []), "Waiting for them", console
    )
    _show_brief_records(
        briefing.get("waiting_from_me", []), "They are waiting for me", console
    )
    _show_brief_records(
        briefing.get("follow_ups", []), "Follow-ups to consider", console
    )
    _show_brief_records(
        briefing.get("active_projects", []), "Active projects with evidence", console
    )
    _show_brief_records(
        briefing.get("unresolved_questions", []), "Unresolved questions", console
    )
    _show_brief_records(
        briefing.get("recent_changes", []), "Important recent changes", console
    )
    _show_brief_records(
        briefing.get("connections", []), "Useful direct connections", console
    )


def _show_brief_records(records: list[dict], title: str, console: Console) -> None:
    if not records:
        console.print(
            safe_text(f"{title}: unknown / insufficient evidence.", style="dim")
        )
        return
    prepared = []
    for record in records:
        item = dict(record)
        item["brief_type"] = (
            item.get("loop_type")
            or item.get("relationship_type")
            or item.get("status")
            or item.get("predicate")
            or "record"
        )
        item["brief_detail"] = (
            item.get("title")
            or item.get("name")
            or item.get("other_name")
            or item.get("predicate")
            or "—"
        )
        prepared.append(item)
    _show_records(prepared, title, "brief_type", "brief_detail", console)


def _show_stats(stats: dict, console: Console, *, compact: bool = False) -> None:
    if not stats.get("conversations"):
        return
    text = (
        f"{stats['total']} messages · {stats['outgoing']} sent · {stats['incoming']} received · "
        f"{stats['active_days']} active days · {stats.get('first_at') or '—'} to {stats.get('last_at') or '—'}"
    )
    console.print(
        Panel(safe_text(text, 900), title="Communication stats", border_style="green")
    )
    response = stats.get("response_times", {})
    if response:
        details = []
        if response.get("their_reply_samples"):
            details.append(
                f"Their replies: median {response['their_reply_hours']}h / {response['their_reply_samples']} pairs"
            )
        if response.get("my_reply_samples"):
            details.append(
                f"My replies: median {response['my_reply_hours']}h / {response['my_reply_samples']} pairs"
            )
        if details:
            console.print(safe_text(" · ".join(details), style="dim"))
    activity = stats.get("activity", {})
    if activity and not compact:
        detail = [
            f"Initiation periods: {activity.get('initiation_periods', 0)}",
            f"Me/them: {activity.get('initiated_by_me', 0)}/{activity.get('initiated_by_them', 0)}",
            f"Long gaps: {activity.get('long_gaps', 0)}",
            f"Recent 7d/30d: {activity.get('recent_7d', 0)}/{activity.get('recent_30d', 0)}",
        ]
        if activity.get("usual_initiator"):
            detail.append(f"Usually initiates: {activity['usual_initiator']}")
        console.print(safe_text(" · ".join(detail), style="dim"))
    if compact:
        return
    table = Table(title="Linked conversations", expand=True)
    table.add_column("Conversation", ratio=2)
    table.add_column("Messages", width=10)
    table.add_column("Last contact", width=25)
    for item in stats["conversations"]:
        table.add_row(
            safe_text(item["title"], 80, single_line=True),
            f"{item['total']} ({item['outgoing']}↑/{item['incoming']}↓)",
            safe_text(item["last_at"] or "—", 25, single_line=True),
        )
    console.print(table)


def _show_conversation_periods_dict(segments: list[dict], console: Console) -> None:
    if not segments:
        return
    table = Table(title="Conversation periods", expand=True)
    table.add_column("Period", width=25)
    table.add_column("Project / topic", ratio=2)
    table.add_column("Summary", ratio=3)
    for segment in segments:
        table.add_row(
            safe_text(
                f"{segment['started_at']} → {segment.get('ended_at') or 'present'}",
                25,
                single_line=True,
            ),
            safe_text(
                segment.get("project_name") or "General conversation",
                80,
                single_line=True,
            ),
            safe_text(segment.get("summary") or "—", 180, single_line=True),
        )
    console.print(table)


def _show_person_conversation(data: dict, console: Console) -> None:
    current, long_term, last_contact, _ = data["conversation"]
    contact_lines = []
    if current:
        contact_lines.append(safe_text(current, 900))
    if last_contact:
        contact_lines.append(safe_text(f"Last contact: {last_contact}", style="dim"))
    for title, owner, status in data.get("open_loops", []):
        contact_lines.append(
            safe_text(f"{status.upper()} · {owner}: {title}", 280, single_line=True)
        )
    if long_term:
        contact_lines.append(safe_text(f"Relationship: {long_term}", 700))
    if contact_lines:
        console.print(
            Panel(
                Group(*contact_lines),
                title="Conversation context",
                border_style="bright_blue",
            )
        )
    _show_contact_projects(data.get("projects", []), console)
    _show_conversation_periods(data.get("segments", []), console)


def _show_contact_projects(projects: list[tuple], console: Console) -> None:
    if not projects:
        return
    table = Table(title="Contact projects", expand=True)
    table.add_column("Project", ratio=2)
    table.add_column("Status", width=12)
    table.add_column("Current context", ratio=3)
    for project, status, summary in projects:
        table.add_row(
            safe_text(project, 80, single_line=True),
            status_text(status),
            safe_text(summary or "—", 180, single_line=True),
        )
    console.print(table)


def _show_conversation_periods(segments: list[tuple], console: Console) -> None:
    if not segments:
        return
    table = Table(title="Conversation periods", expand=True)
    table.add_column("Period", width=25)
    table.add_column("Project / topic", ratio=2)
    table.add_column("Summary", ratio=3)
    for started, ended, project, summary in segments:
        table.add_row(
            safe_text(f"{started} → {ended or 'present'}", 25, single_line=True),
            safe_text(project or "General conversation", 80, single_line=True),
            safe_text(summary or "—", 180, single_line=True),
        )
    console.print(table)


def _show_tasks(tasks: list[tuple], console: Console) -> None:
    if not tasks:
        console.print(notice("No tasks linked to this profile.", title="Tasks"))
        return
    table = Table(title="Tasks", expand=True)
    table.add_column("Status", width=10)
    table.add_column("Task", ratio=3)
    table.add_column("Due", width=12)
    table.add_column("Evidence", ratio=2)
    for _, title, status, due, chat_id, message_id in tasks:
        table.add_row(
            status_text(status),
            safe_text(title, 180, single_line=True),
            safe_text(due or "—", 12),
            safe_text(
                "[E]"
                if chat_id is not None and message_id is not None
                else "Manual/canonical",
                80,
                single_line=True,
            ),
        )
    console.print(table)


def _show_memories(memories: list[tuple], console: Console) -> None:
    if not memories:
        console.print(notice("No durable facts saved yet.", title="Important facts"))
        return
    console.print(
        Panel(
            Group(
                *(safe_text(f"• {row[0]}", 500, single_line=True) for row in memories)
            ),
            title="Important facts",
            border_style="magenta",
        )
    )
