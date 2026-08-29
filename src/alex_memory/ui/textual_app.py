"""Interactive terminal widgets."""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import TYPE_CHECKING, Any, cast

from textual.app import App, ComposeResult, ScreenStackError
from textual.binding import Binding
from textual.containers import Horizontal
from textual.events import Key
from textual.screen import Screen
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    ProgressBar,
    Static,
)

from ..operational import manually_update_task
from ..person_profile import build_person_profile
from ..profile_enrichment import (
    drain_queued_profile_scan,
    enrich_person,
    profile_scan_debug,
    profile_scan_status,
)
from ..retrieval import SearchResult, retrieve_related
from .discovery import (
    PersonSearchResult,
    person_overview,
    relative_datetime,
    search_people,
)

if TYPE_CHECKING:
    from ..app import AlexMemoryApp


class PersonItem(ListItem):
    def __init__(self, result: PersonSearchResult, date_label: str) -> None:
        label = f"{result.name}  {('@' + result.username) if result.username else ''}  {date_label}"
        super().__init__(Label(label))
        self.result = result


class HomeScreen(Screen[None]):
    BINDINGS = [
        Binding("ctrl+k", "palette", "Commands"),
        Binding("slash", "palette", "Commands"),
        Binding("enter", "open_selected", "Open"),
    ]

    def __init__(self, owner: AlexMemoryApp) -> None:
        super().__init__()
        self.owner = owner
        self.rows: list[PersonSearchResult] = []
        self._search_revision = 0

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("Telegram connecting · Sync — · AI — · Writer —", id="status")
        yield Label("PEOPLE", id="section-title")
        yield Input(
            placeholder="Search people, companies, projects, context…",
            id="people-search",
        )
        with Horizontal(id="content"):
            yield ListView(id="people-results")
            yield Static(
                "Select a person to preview their relationship context.", id="preview"
            )
        yield Footer()

    def on_mount(self) -> None:
        self.query_one(Input).focus()
        self._refresh("")
        self.set_interval(10, self._refresh_status)

    def _refresh_status(self) -> None:
        if self.owner.runtime_status is None:
            return
        status = self.owner.runtime_status.snapshot(self.owner.live_sync)
        telegram = "connected" if status.telegram.connected else status.phase.lower()
        text = f"Telegram {telegram} · AI {status.ai.pending_jobs} queued"
        self.query_one("#status", Static).update(text)

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "people-search":
            self._search_revision += 1
            revision = self._search_revision
            self.set_timer(
                0.12, lambda: self._refresh_if_current(event.value, revision)
            )

    def _refresh_if_current(self, query: str, revision: int) -> None:
        if revision == self._search_revision:
            self._refresh(query)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "people-search":
            if event.value.strip() == "/":
                event.input.value = ""
                self.action_palette()
                return
            self.action_open_selected()

    def on_key(self, event: Key) -> None:
        if event.key == "ctrl+k":
            event.prevent_default()
            event.stop()
            self.action_palette()

    def _refresh(self, query: str) -> None:
        if self.owner.conn is None:
            return
        self.rows = search_people(self.owner.conn, query)
        view = self.query_one("#people-results", ListView)
        view.clear()
        for row in self.rows:
            view.append(
                PersonItem(
                    row,
                    relative_datetime(
                        row.last_contact_at, self.owner.settings.app_timezone
                    ),
                )
            )
        if self.rows:
            view.index = 0
            self._preview(self.rows[0].person_id)
        else:
            self.query_one("#preview", Static).update(
                "No canonical people match this search."
            )

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, PersonItem):
            self._preview(event.item.result.person_id)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, PersonItem):
            self.app.push_screen(ProfileScreen(self.owner, event.item.result.person_id))

    def action_open_selected(self) -> None:
        view = self.query_one("#people-results", ListView)
        if isinstance(view.highlighted_child, PersonItem):
            self.app.push_screen(
                ProfileScreen(self.owner, view.highlighted_child.result.person_id)
            )

    def action_palette(self) -> None:
        self.app.push_screen(CommandPalette(self.owner))

    def _preview(self, value: int) -> None:
        if self.owner.conn is None:
            return
        overview = person_overview(self.owner.conn, value)
        if not overview:
            return
        items = cast(list[str], overview["open_items"])
        detail = (
            "\n".join(f"• {item}" for item in items)
            if items
            else "unknown / insufficient evidence"
        )
        self.query_one("#preview", Static).update(
            f"{overview['name']}\n{overview['summary']}\n\nOpen items\n{detail}"
        )


class ProfileRecordItem(ListItem):
    def __init__(self, record: dict) -> None:
        self.record = record
        super().__init__(Label(_record_label(record)))


class ProfileScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("slash", "search", "Search"),
        Binding("1", "section('overview')", "Overview"),
        Binding("2", "section('actions')", "Actions"),
        Binding("3", "section('projects')", "Projects"),
        Binding("4", "section('profile')", "Profile"),
        Binding("5", "section('connections')", "Connections"),
        Binding("6", "section('timeline')", "Timeline"),
        Binding("7", "section('messages')", "Messages"),
        Binding("8", "section('evidence')", "Evidence"),
        Binding("d", "scan", "Scan"),
        Binding("p", "palette", "Commands"),
        Binding("at", "contacts", "Contacts"),
        Binding("a", "actions", "Action"),
        Binding("r", "resolve", "Resolve"),
        Binding("w", "waiting", "Waiting"),
        Binding("u", "uncertain", "Uncertain"),
        Binding("e", "evidence", "Evidence"),
        Binding("enter", "inspect", "Inspect"),
        Binding("j", "down", "Down", show=False),
        Binding("k", "up", "Up", show=False),
    ]

    def __init__(self, owner: AlexMemoryApp, person_id: int) -> None:
        super().__init__()
        self.owner, self.person_id = owner, person_id
        self.section_text = ""
        self.section = "overview"
        self.records: list[dict] = []
        self.show_uncertain = False

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(id="profile-heading")
        yield Static(id="profile-summary")
        yield ListView(id="profile-records")
        yield Footer()

    def on_mount(self) -> None:
        self.action_section("overview")

    def action_section(self, section: str) -> None:
        if self.owner.conn is None:
            return
        detail = build_person_profile(self.owner.conn, self.person_id)
        self.section = section
        self.records = _section_records(detail, section, self.show_uncertain)
        self.section_text = _dashboard_text(
            detail, section, self.records, self.show_uncertain
        )
        entity = detail["entity"]
        account = f" @{entity[3]}" if entity[3] else ""
        self.query_one("#profile-heading", Static).update(
            f"{entity[1]}{account}  ·  {section.upper()}"
        )
        self.query_one("#profile-summary", Static).update(self.section_text)
        view = self.query_one("#profile-records", ListView)
        view.clear()
        for record in self.records:
            view.append(ProfileRecordItem(record))
        if self.records:
            view.index = 0

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_scan(self) -> None:
        self.app.push_screen(ScanScreen(self.owner, self.person_id))

    def action_palette(self) -> None:
        self.app.push_screen(CommandPalette(self.owner))

    def action_search(self) -> None:
        self.app.push_screen(SearchScreen(self.owner, self.person_id))

    def action_contacts(self) -> None:
        self.app.pop_screen()

    def action_actions(self) -> None:
        if self.section == "actions":
            self.action_inspect()
        else:
            self.action_section("actions")

    def action_uncertain(self) -> None:
        self.show_uncertain = not self.show_uncertain
        self.action_section("actions" if self.section == "overview" else self.section)

    def action_down(self) -> None:
        self.query_one("#profile-records", ListView).action_cursor_down()

    def action_up(self) -> None:
        self.query_one("#profile-records", ListView).action_cursor_up()

    def _selected(self) -> dict | None:
        child = self.query_one("#profile-records", ListView).highlighted_child
        return child.record if isinstance(child, ProfileRecordItem) else None

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ProfileRecordItem):
            self.action_inspect()

    def action_inspect(self) -> None:
        if record := self._selected():
            self.app.push_screen(RecordDetailScreen(self.owner, record))

    def action_evidence(self) -> None:
        if record := self._selected():
            self.app.push_screen(
                EvidenceScreen(
                    record.get("evidence", []), str(record.get("title", "Evidence"))
                )
            )

    def _change_task(self, status: str) -> None:
        record = self._selected()
        if record and record.get("record_type") == "task" and record.get("task_id"):
            self.app.push_screen(
                TaskConfirmScreen(
                    self.owner,
                    self,
                    int(record["task_id"]),
                    status,
                    str(record["title"]),
                )
            )

    def action_resolve(self) -> None:
        self._change_task("done")

    def action_waiting(self) -> None:
        self._change_task("waiting")


class RecordDetailScreen(Screen[None]):
    BINDINGS = [Binding("escape", "back", "Back"), Binding("e", "evidence", "Evidence")]

    def __init__(self, owner: AlexMemoryApp, record: dict) -> None:
        super().__init__()
        self.owner, self.record = owner, record

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static(_record_detail(self.record), id="record-detail")
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_evidence(self) -> None:
        self.app.push_screen(
            EvidenceScreen(
                self.record.get("evidence", []),
                str(self.record.get("title", "Evidence")),
            )
        )


class EvidenceScreen(Screen[None]):
    BINDINGS = [Binding("escape", "back", "Back")]

    def __init__(self, evidence: list[dict], title: str) -> None:
        super().__init__()
        self.evidence, self.title = evidence[:16], title

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        body = (
            "\n\n".join(
                f"{item.get('speaker', 'OTHER')} · {item.get('date') or 'undated'}"
                + _evidence_locator(item)
                + f"\n{item.get('text', '')}"
                for item in self.evidence
            )
            or "No supporting evidence is available."
        )
        yield Static(f"EVIDENCE · {self.title}\n\n{body}", id="evidence-body")
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()


class TaskConfirmScreen(Screen[None]):
    BINDINGS = [
        Binding("y", "confirm", "Confirm"),
        Binding("n", "cancel", "Cancel"),
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(
        self,
        owner: AlexMemoryApp,
        profile: ProfileScreen,
        task_id: int,
        status: str,
        title: str,
    ) -> None:
        super().__init__()
        self.owner, self.profile, self.task_id, self.status, self.title = (
            owner,
            profile,
            task_id,
            status,
            title,
        )

    def compose(self) -> ComposeResult:
        yield Static(
            f"Set {self.title} to {self.status.upper()}?  Y confirm · N cancel",
            id="task-confirm",
        )

    def action_confirm(self) -> None:
        if self.owner.conn is not None and manually_update_task(
            self.owner.conn, self.task_id, self.status
        ):
            self.owner.conn.commit()
            self.app.pop_screen()
            self.profile.action_section(self.profile.section)

    def action_cancel(self) -> None:
        self.app.pop_screen()


class SearchResultItem(ListItem):
    def __init__(self, result: SearchResult) -> None:
        self.result = result
        super().__init__(Label(f"{result.result_type.upper():10} {result.title}"))


class SearchScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("enter", "inspect", "Inspect"),
    ]

    def __init__(self, owner: AlexMemoryApp, person_id: int) -> None:
        super().__init__()
        self.owner, self.person_id = owner, person_id

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Input(placeholder="Search this contact…", id="contact-search")
        yield ListView(id="contact-search-results")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#contact-search", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "contact-search" or self.owner.conn is None:
            return
        results = (
            retrieve_related(
                self.owner.conn,
                "person",
                self.person_id,
                self.owner.settings,
                query=event.value,
            )[:30]
            if event.value.strip()
            else []
        )
        view = self.query_one("#contact-search-results", ListView)
        view.clear()
        for result in results:
            view.append(SearchResultItem(result))

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, SearchResultItem):
            self._open(event.item.result)

    def action_inspect(self) -> None:
        child = self.query_one("#contact-search-results", ListView).highlighted_child
        if isinstance(child, SearchResultItem):
            self._open(child.result)

    def _open(self, result: SearchResult) -> None:
        evidence = []
        if (
            result.chat_id is not None
            and result.message_id is not None
            and self.owner.conn is not None
        ):
            row = self.owner.conn.execute(
                "SELECT date,text,is_outgoing FROM messages WHERE chat_id=? AND message_id=?",
                (result.chat_id, result.message_id),
            ).fetchone()
            if row is not None:
                evidence = [
                    {
                        "date": row[0],
                        "text": row[1],
                        "speaker": "You" if row[2] else "Other",
                        "chat_id": result.chat_id,
                        "message_id": result.message_id,
                    }
                ]
        self.app.push_screen(EvidenceScreen(evidence, result.title))

    def action_back(self) -> None:
        self.app.pop_screen()


def _evidence_locator(item: dict) -> str:
    chat_id, message_id = item.get("chat_id"), item.get("message_id")
    if isinstance(chat_id, int) and isinstance(message_id, int):
        return f" · chat {chat_id} / message {message_id}"
    return ""


class ScanScreen(Screen[None]):
    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("enter", "queue", "Process next"),
        Binding("l", "live_scan", "Live scan"),
    ]

    def __init__(self, owner: AlexMemoryApp, person_id: int) -> None:
        super().__init__()
        self.owner = owner
        self.person_id = person_id

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("DEEP SCAN", id="scan-title")
        yield Static(id="scan-status")
        yield Static("EVIDENCE COVERAGE", id="scan-evidence-label")
        yield ProgressBar(total=1, show_eta=False, id="scan-evidence-progress")
        yield Static("WINDOW PROGRESS", id="scan-window-label")
        yield ProgressBar(total=1, show_eta=False, id="scan-window-progress")
        yield Static(id="scan-debug")
        yield Static(
            "Enter processes the next two windows. L runs up to 64 queued windows live. "
            "Only accepted direct claims may update canonical profile state.",
            id="scan-help",
        )
        yield Footer()

    def on_mount(self) -> None:
        self._live_scan_active = False
        self._scan_task: asyncio.Task | None = None
        self._coverage: tuple[bool, int] | None = None
        self._show_status()
        self.set_interval(1, self._refresh_live_status)

    def action_queue(self) -> None:
        if self.owner.conn is None:
            return
        self._start_scan(
            enrich_person(
                self.owner.conn,
                self.owner.settings,
                self.owner.console,
                self.person_id,
                live_progress=self._live_progress,
                render_console=False,
            )
        )

    def action_live_scan(self) -> None:
        if self.owner.conn is None:
            return
        self._start_scan(
            drain_queued_profile_scan(
                self.owner.conn,
                self.owner.settings,
                self.owner.console,
                self.person_id,
                live_progress=self._live_progress,
                render_console=False,
            )
        )

    def action_back(self) -> None:
        self.app.pop_screen()

    def _show_status(self, prefix: str = "", *, refresh_coverage: bool = True) -> None:
        if self.owner.conn is None:
            return
        status = profile_scan_status(
            self.owner.conn,
            self.person_id,
            include_eligibility=refresh_coverage,
        )
        if refresh_coverage:
            self._coverage = (
                bool(status["direct_chat_available"]),
                int(status["eligible_messages"] or 0),
            )
        direct_chat_available, eligible_messages = self._coverage or (False, 0)
        availability = (
            f"{eligible_messages} evidence messages found"
            if direct_chat_available
            else "No canonically owned direct conversation is available"
        )
        backlog = (
            f"{status['pending']} ready to process"
            if status["pending"]
            else "No queued backlog"
        )
        running = (
            f"Live: {status['running']} window(s) / {status['running_messages']} messages in progress\n"
            if status.get("running")
            else ""
        )
        self.query_one("#scan-status", Static).update(
            prefix
            + f"{availability}\n"
            + f"AI completed {status['completed_messages']} / {eligible_messages} evidence messages\n"
            + running
            + f"{backlog}\n"
            + f"{status['done']} completed · {status['failed']} failed · "
            + f"extractor v{status['extractor_version']}"
        )
        evidence_progress = min(
            _scan_count(status, "completed_messages"), eligible_messages
        )
        self.query_one("#scan-evidence-progress", ProgressBar).update(
            total=max(eligible_messages, 1), progress=evidence_progress
        )
        window_total = sum(
            _scan_count(status, key) for key in ("done", "pending", "running", "failed")
        )
        self.query_one("#scan-window-progress", ProgressBar).update(
            total=max(window_total, 1),
            progress=_scan_count(status, "done") + _scan_count(status, "failed"),
        )
        debug = profile_scan_debug(self.owner.conn, self.person_id)
        recent = (
            " · ".join(
                f"#{row[0]} {row[1]} · {row[2]} msg · attempt {row[3]} · "
                f"{row[6] or 'provider unknown'}/{row[7] or 'model unknown'}"
                + (" · failure recorded" if row[8] else "")
                for row in debug["jobs"][:3]
            )
            or "No profile jobs recorded"
        )
        reason_parts = [f"{row[1]}× {row[0]}" for row in debug["rejection_reasons"]]
        omitted_rejections = int(debug["rejected_items"]) - sum(
            int(row[1]) for row in debug["rejection_reasons"]
        )
        if omitted_rejections:
            reason_parts.append(f"+{omitted_rejections} other")
        reasons = "; ".join(reason_parts) or "none"
        self.query_one("#scan-debug", Static).update(
            f"ANALYSIS AUDIT · claims direct/third-party/inference: {debug['direct_claims']}/"
            f"{debug['third_party_claims']}/{debug['inference_claims']} · "
            f"rejected rows: {debug['rejected_items']}\n"
            f"Rejection reasons: {reasons}\nRecent durable jobs: {recent}"
        )

    def _refresh_live_status(self) -> None:
        if self._live_scan_active:
            self._show_status(prefix="Live Deep Scan running. ", refresh_coverage=False)

    def _live_progress(self) -> None:
        if self._is_visible():
            self._show_status(prefix="Live Deep Scan running. ", refresh_coverage=False)

    def _start_scan(
        self, work: Coroutine[Any, Any, dict[str, int | str | None]]
    ) -> None:
        if self._scan_task is not None and not self._scan_task.done():
            work.close()
            self._show_status(prefix="A Deep Scan is already running. ")
            return
        self._live_scan_active = True
        self._show_status(prefix="Live Deep Scan started. ")
        self._scan_task = asyncio.create_task(work)
        self._scan_task.add_done_callback(self._finish_scan)

    def _finish_scan(self, task: asyncio.Task[dict[str, int | str | None]]) -> None:
        self._live_scan_active = False
        try:
            outcome = task.result()
            prefix = str(outcome["outcome"]) + " "
        except asyncio.CancelledError:
            prefix = "Deep Scan stopped safely; unfinished windows remain pending. "
        except Exception as error:
            prefix = f"Deep Scan stopped: {type(error).__name__}. "
        if self._is_visible():
            self._show_status(prefix=prefix)

    def _is_visible(self) -> bool:
        """Avoid a late worker callback writing after the terminal has closed."""
        try:
            return self.app.screen is self
        except ScreenStackError:
            return False


class CommandPalette(Screen[None]):
    BINDINGS = [Binding("escape", "close_palette", "Close")]
    _COMMANDS = (
        ("People", "people"),
        ("Review", "review"),
        ("System Status", "status"),
        ("Maintenance", "maintenance"),
    )

    def __init__(self, owner: AlexMemoryApp) -> None:
        super().__init__()
        self.owner = owner

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Search commands…", id="command-search")
        yield ListView(*self._command_items(), id="commands")
        yield Static(
            "People is the product. Review and System Status are operational views. "
            "Maintenance is for explicit recovery only."
        )

    def on_mount(self) -> None:
        self.query_one(Input).focus()

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "command-search":
            return
        query = event.value.casefold().strip()
        commands = [
            command
            for command in self._COMMANDS
            if not query or query in command[0].casefold()
        ]
        view = self.query_one("#commands", ListView)
        await view.clear()
        for item in self._command_items(commands):
            await view.append(item)

    @classmethod
    def _command_items(
        cls, commands: tuple[tuple[str, str], ...] | list[tuple[str, str]] | None = None
    ) -> list[ListItem]:
        return [
            ListItem(Label(label), id=item_id)
            for label, item_id in commands or cls._COMMANDS
        ]

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item is None:
            return
        if event.item.id == "people":
            self.app.pop_screen()
        else:
            terminal = cast(AlexMemoryTerminal, self.app)
            terminal.open_operations()

    def action_close_palette(self) -> None:
        self.app.pop_screen()


class AlexMemoryTerminal(App[None]):
    CSS = """
    #status { height: 1; color: $text-muted; padding: 0 1; }
    #section-title { padding: 1 1 0 1; text-style: bold; }
    #people-search { margin: 0 1 1 1; }
    #content { height: 1fr; }
    #people-results { width: 52%; border: none; }
    #preview { width: 48%; padding: 1 2; border-left: solid $primary; }
    #profile-heading { padding: 1 2 0 2; text-style: bold; }
    #profile-summary { margin: 1 2; color: $text-muted; }
    #profile-records { height: 1fr; margin: 0 2; border-top: solid $primary; }
    #scan-title { padding: 1 2 0 2; text-style: bold; }
    #scan-status { margin: 1 2; padding: 1; border: solid $primary; }
    #scan-evidence-label, #scan-window-label { margin: 0 2; color: $text-muted; }
    #scan-evidence-progress, #scan-window-progress { margin: 0 2 1 2; }
    #scan-debug { margin: 0 2 1 2; padding: 1; color: $text-muted; border: solid $secondary; }
    #scan-help { margin: 0 2; color: $text-muted; }
    """

    def __init__(self, owner: AlexMemoryApp) -> None:
        super().__init__()
        self.owner = owner
        self.operations_requested = False

    def on_mount(self) -> None:
        self.push_screen(HomeScreen(self.owner))

    def open_operations(self) -> None:
        self.operations_requested = True
        self.exit()


def _summary(detail: dict) -> str:
    contact = detail.get("contact", {})
    summary = contact.get("profile_summary") or contact.get("current_summary")
    if not summary:
        summary = contact.get("long_term_summary") or "unknown / insufficient evidence"
    topics = detail.get("topics", [])
    suffix = f"\nTopics: {', '.join(topics[:6])}" if topics else ""
    return f"SUMMARY\n{summary}{suffix}"


def _section(title: str, records: list[dict], left: str, right: str) -> str:
    if not records:
        return f"{title}\nunknown / insufficient evidence"
    lines = [title]
    for record in records[:6]:
        label = record.get(right) or record.get("title") or record.get("name") or "—"
        kind = (
            record.get(left)
            or record.get("status")
            or record.get("event_type")
            or "record"
        )
        evidence = record.get("evidence", [])
        citation = ""
        if evidence:
            source = evidence[0]
            citation = f" [{source['chat_id']}/{source['message_id']}]"
        lines.append(f"• {kind}: {label}{citation}")
    return "\n".join(lines)


def _section_records(detail: dict, section: str, show_uncertain: bool) -> list[dict]:
    """Select bounded existing profile rows for one Textual section."""
    mapping = {
        "overview": detail.get("actions", []),
        "actions": detail.get("actions", []),
        "projects": detail.get("projects", []),
        "profile": detail.get("facts", [])
        + [
            claim
            for claim in detail.get("profile_claims", [])
            if claim.get("assertion_kind") == "direct"
        ],
        "connections": detail.get("relationships", []),
        "timeline": detail.get("events", []) + detail.get("segments", []),
        "messages": detail.get("messages", []),
        "evidence": detail.get("facts", [])
        + detail.get("relationships", [])
        + detail.get("tasks", [])
        + detail.get("follow_ups", [])
        + detail.get("open_loops", [])
        + detail.get("events", []),
    }
    records = [dict(record) for record in mapping.get(section, [])]
    if section == "profile" and show_uncertain:
        records.extend(dict(record) for record in detail.get("uncertain", []))
    return records[:80]


def _dashboard_text(
    detail: dict, section: str, records: list[dict], show_uncertain: bool
) -> str:
    """Summarize the currently visible Textual section without inventing state."""
    titles = {
        "overview": "SUMMARY",
        "actions": "ACTION ITEMS",
        "projects": "PROJECTS",
        "profile": "PROFILE FACTS AND DIRECT CLAIMS",
        "connections": "DIRECT CONNECTIONS",
        "timeline": "TIMELINE",
        "messages": "RECENT LINKED MESSAGES",
        "evidence": "EXACT SUPPORTING EVIDENCE",
    }
    title = titles.get(section, "PROFILE")
    if section == "overview":
        return "\n\n".join(
            (
                _summary(detail),
                _section("NEXT ACTIONS", records, "action_state", "title"),
                _stats(detail.get("stats", {})),
                _scan_coverage(detail.get("scan_status", {})),
            )
        )
    notice = (
        "\nUncertain third-party and inference claims included."
        if show_uncertain and section == "profile"
        else ""
    )
    return _section(title, records, "record_type", "title") + notice


def _record_label(record: dict) -> str:
    kind = str(
        record.get("action_state")
        or record.get("assertion_kind")
        or record.get("relationship_type")
        or record.get("event_type")
        or record.get("predicate")
        or record.get("speaker")
        or record.get("status")
        or "record"
    ).upper()
    title = _record_title(record)
    evidence = record.get("evidence", [])
    citation = (
        f" [{evidence[0]['chat_id']}/{evidence[0]['message_id']}]" if evidence else ""
    )
    return f"{kind:14} {title[:140]}{citation}"


def _record_detail(record: dict) -> str:
    excluded = {
        "evidence",
        "text",
        "details",
        "description",
        "summary",
        "value_json",
        "payload_json",
    }
    lines = [
        _record_label(record),
        "",
        str(
            record.get("details")
            or record.get("description")
            or record.get("summary")
            or record.get("text")
            or "No additional detail."
        ),
    ]
    for key, value in record.items():
        if key in excluded or key.endswith("_id") or value in (None, "", [], {}):
            continue
        lines.append(f"{key.replace('_', ' ').title()}: {value}")
    evidence = record.get("evidence", [])
    if evidence:
        lines.extend(
            ["", "Exact evidence:"]
            + [
                f"[{item['chat_id']}/{item['message_id']}] {item.get('date') or 'undated'}"
                for item in evidence
            ]
        )
    return "\n".join(lines)


def _record_title(record: dict) -> str:
    value = (
        record.get("title")
        or record.get("name")
        or record.get("other_name")
        or record.get("project_name")
        or record.get("predicate")
        or record.get("text")
        or "unknown / insufficient evidence"
    )
    return str(value).replace("\n", " ")


def _stats(stats: dict) -> str:
    if not stats.get("conversations"):
        return "COMMUNICATION\nunknown / insufficient evidence"
    return (
        "COMMUNICATION\n"
        f"{stats.get('total', 0)} messages · {stats.get('incoming', 0)} received · "
        f"{stats.get('outgoing', 0)} sent · {stats.get('active_days', 0)} active days"
    )


def _scan_coverage(scan: dict) -> str:
    if not scan.get("direct_chat_available"):
        return "AI COVERAGE\nunknown / no canonically owned direct chat"
    return (
        "AI PROFILE COVERAGE\n"
        f"{scan.get('completed_messages', 0)} / {scan.get('eligible_messages', 0)} evidence messages completed · "
        f"{scan.get('pending', 0)} ready · {scan.get('failed', 0)} failed"
    )


def _scan_count(status: dict[str, int | str | bool | None], key: str) -> int:
    """Read a numeric durable status field without trusting a display dictionary."""
    value = status.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0
