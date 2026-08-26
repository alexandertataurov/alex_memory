from __future__ import annotations

import tempfile
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console
from textual.widgets import ListView, ProgressBar, Static

from alex_memory.app import AlexMemoryApp
from alex_memory.database import connect
from alex_memory.ui.discovery import relative_datetime, search_people
from alex_memory.ui.textual_app import (
    AlexMemoryTerminal,
    CommandPalette,
    EvidenceScreen,
    HomeScreen,
    ProfileScreen,
    RecordDetailScreen,
    ScanScreen,
)
from test_ai_pipeline import make_settings


def test_people_discovery_ranks_exact_prefix_and_fuzzy_matches() -> None:
    with tempfile.TemporaryDirectory() as directory:
        settings = make_settings(Path(directory))
        conn = connect(settings)
        now = "2026-08-24T10:00:00+00:00"
        conn.execute(
            "INSERT INTO people(canonical_name,telegram_username,created_at,updated_at) VALUES (?,?,?,?)",
            ("Ilya Gutovskiy", "gutovskiy", now, now),
        )
        conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES (?,?,?)",
            ("Ilia Petrov", now, now),
        )
        conn.commit()
        rows = search_people(conn, "ilya")
        assert [row.name for row in rows][:1] == ["Ilya Gutovskiy"]
        assert search_people(conn, "gutov")[0].matched_by == "username"
        conn.close()


def test_relative_datetime_respects_the_application_timezone() -> None:
    now = datetime(2026, 8, 24, 12, tzinfo=UTC)
    assert (
        relative_datetime("2026-08-24T08:30:00+00:00", "Asia/Tbilisi", now=now)
        == "today 12:30"
    )
    assert (
        relative_datetime("2026-08-23T08:30:00+00:00", "Asia/Tbilisi", now=now)
        == "yesterday 12:30"
    )


@pytest.mark.asyncio
async def test_terminal_autofocuses_search_and_filters_people() -> None:
    with tempfile.TemporaryDirectory() as directory:
        settings = make_settings(Path(directory))
        app_owner = AlexMemoryApp(settings, Console())
        app_owner.conn = connect(settings)
        now = "2026-08-24T10:00:00+00:00"
        app_owner.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES (?,?,?)",
            ("Ilya Gutovskiy", now, now),
        )
        app_owner.conn.commit()
        app = AlexMemoryTerminal(app_owner)
        async with app.run_test() as pilot:
            assert isinstance(app.screen, HomeScreen)
            await pilot.press("i", "l", "y", "a")
            assert [row.name for row in app.screen.rows] == ["Ilya Gutovskiy"]
            await pilot.press("enter")
            assert isinstance(app.screen, ProfileScreen)
            assert "SUMMARY" in app.screen.section_text
            await pilot.press("8")
            assert "EXACT SUPPORTING EVIDENCE" in app.screen.section_text
            await pilot.press("d")
            assert isinstance(app.screen, ScanScreen)
            await pilot.press("escape")
            await pilot.press("escape")
            await pilot.press("ctrl+k")
            assert isinstance(app.screen, CommandPalette)
            app.open_operations()
            assert app.operations_requested
        app_owner.conn.close()


@pytest.mark.asyncio
async def test_command_palette_filters_visible_commands() -> None:
    with tempfile.TemporaryDirectory() as directory:
        settings = make_settings(Path(directory))
        app_owner = AlexMemoryApp(settings, Console())
        app_owner.conn = connect(settings)
        app = AlexMemoryTerminal(app_owner)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+k")
            assert isinstance(app.screen, CommandPalette)
            await pilot.press("s", "t", "a", "t", "u", "s")
            commands = app.screen.query_one("#commands", ListView)
            assert [item.id for item in commands.children] == ["status"]
        app_owner.conn.close()


@pytest.mark.asyncio
async def test_profile_task_status_change_requires_confirmation() -> None:
    with tempfile.TemporaryDirectory() as directory:
        settings = make_settings(Path(directory))
        app_owner = AlexMemoryApp(settings, Console())
        app_owner.conn = connect(settings)
        now = "2026-08-24T10:00:00+00:00"
        person_id = app_owner.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES ('Ilya',?,?)",
            (now, now),
        ).lastrowid
        task_id = app_owner.conn.execute(
            """INSERT INTO tasks(title,normalized_title,status,owner,related_person_id,
                   confidence,created_at,updated_at)
               VALUES ('Send contract','send contract','open','me',?,1,?,?)""",
            (person_id, now, now),
        ).lastrowid
        app_owner.conn.commit()
        app = AlexMemoryTerminal(app_owner)
        async with app.run_test() as pilot:
            await pilot.press("enter", "2", "r")
            await pilot.press("n")
            assert (
                app_owner.conn.execute(
                    "SELECT status FROM tasks WHERE task_id=?", (task_id,)
                ).fetchone()[0]
                == "open"
            )
            await pilot.press("r", "y")
            assert (
                app_owner.conn.execute(
                    "SELECT status FROM tasks WHERE task_id=?", (task_id,)
                ).fetchone()[0]
                == "done"
            )
        app_owner.conn.close()


@pytest.mark.asyncio
async def test_contact_search_excludes_other_persons_matching_task() -> None:
    with tempfile.TemporaryDirectory() as directory:
        settings = make_settings(Path(directory))
        app_owner = AlexMemoryApp(settings, Console())
        app_owner.conn = connect(settings)
        now = "2026-08-24T10:00:00+00:00"
        person_id = app_owner.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES ('Ilya',?,?)",
            (now, now),
        ).lastrowid
        other_id = app_owner.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES ('Other',?,?)",
            (now, now),
        ).lastrowid
        app_owner.conn.executemany(
            """INSERT INTO tasks(title,normalized_title,status,owner,related_person_id,
                   confidence,created_at,updated_at)
               VALUES (?,?, 'open','other',?,1,?,?)""",
            [
                ("Ilya contract", "ilya contract", person_id, now, now),
                ("Other contract", "other contract", other_id, now, now),
            ],
        )
        app_owner.conn.commit()
        app = AlexMemoryTerminal(app_owner)
        async with app.run_test() as pilot:
            await pilot.press("enter", "slash", "c", "o", "n", "t", "r", "a", "c", "t")
            results = app.screen.query_one("#contact-search-results", ListView)
            assert [item.result.title for item in results.children] == ["Ilya contract"]
        app_owner.conn.close()


@pytest.mark.asyncio
async def test_profile_sections_and_exact_evidence_drill_down_render() -> None:
    with tempfile.TemporaryDirectory() as directory:
        settings = make_settings(Path(directory))
        app_owner = AlexMemoryApp(settings, Console())
        app_owner.conn = connect(settings)
        now = "2026-08-24T10:00:00+00:00"
        person_id = app_owner.conn.execute(
            """INSERT INTO people(canonical_name,telegram_user_id,created_at,updated_at)
               VALUES ('Ilya Gutovskiy',100,?,?)""",
            (now, now),
        ).lastrowid
        app_owner.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (100,'Ilya Gutovskiy','user')"
        )
        app_owner.conn.execute(
            """INSERT INTO messages(chat_id,message_id,sender_id,date,text,is_outgoing)
               VALUES (100,1,100,?,'I can send the contract tomorrow.',0)""",
            (now,),
        )
        claim_id = app_owner.conn.execute(
            """INSERT INTO semantic_claims(batch_id,claim_type,statement,payload_json,
               extractor_version,provider,model,confidence,authority_status,dedupe_key,created_at)
               VALUES (1,'temporal_fact','Contract delivery','{}',2,'test','test',0.9,
                       'accepted','terminal-profile-claim',?)""",
            (now,),
        ).lastrowid
        app_owner.conn.execute(
            """INSERT INTO semantic_claim_evidence(claim_id,ordinal,source_chat_id,
               source_message_id,created_at) VALUES (?,0,100,1,?)""",
            (claim_id, now),
        )
        app_owner.conn.execute(
            """INSERT INTO context_facts(subject_type,subject_id,predicate,value_json,
               valid_from,observed_at,confidence,source_claim_id,created_at,updated_at)
               VALUES ('person',?,'commitment','{"item":"contract"}',?,?,0.9,?,?,?)""",
            (person_id, now, now, claim_id, now, now),
        )
        app_owner.conn.commit()
        app = AlexMemoryTerminal(app_owner)
        async with app.run_test() as pilot:
            await pilot.press("enter")
            assert isinstance(app.screen, ProfileScreen)
            for key in "12345678":
                await pilot.press(key)
                assert (
                    app.screen.section
                    == {
                        "1": "overview",
                        "2": "actions",
                        "3": "projects",
                        "4": "profile",
                        "5": "connections",
                        "6": "timeline",
                        "7": "messages",
                        "8": "evidence",
                    }[key]
                )
            await pilot.press("4", "enter")
            assert isinstance(app.screen, RecordDetailScreen)
            await pilot.press("e")
            assert isinstance(app.screen, EvidenceScreen)
            assert "I can send the contract tomorrow." in str(
                app.screen.query_one("#evidence-body", Static).render()
            )
            assert "chat 100 / message 1" in str(
                app.screen.query_one("#evidence-body", Static).render()
            )
        app_owner.conn.close()


@pytest.mark.asyncio
async def test_deep_scan_runs_in_a_background_task_and_keeps_the_screen_responsive() -> (
    None
):
    with tempfile.TemporaryDirectory() as directory:
        settings = make_settings(Path(directory))
        app_owner = AlexMemoryApp(settings, Console())
        app_owner.conn = connect(settings)
        now = "2026-08-24T10:00:00+00:00"
        app_owner.conn.execute(
            "INSERT INTO people(canonical_name,created_at,updated_at) VALUES (?,?,?)",
            ("Ilya Gutovskiy", now, now),
        )
        app_owner.conn.commit()
        started = asyncio.Event()
        release = asyncio.Event()

        async def blocked_scan(*_args, **_kwargs):
            started.set()
            await release.wait()
            return {"outcome": "Deep Scan complete."}

        app = AlexMemoryTerminal(app_owner)
        with patch("alex_memory.ui.textual_app.enrich_person", blocked_scan):
            async with app.run_test() as pilot:
                await pilot.press("enter")
                assert isinstance(app.screen, ProfileScreen)
                await pilot.press("d", "enter")
                assert isinstance(app.screen, ScanScreen)
                assert app.screen.query_one("#scan-evidence-progress", ProgressBar)
                assert app.screen.query_one("#scan-window-progress", ProgressBar)
                try:
                    await asyncio.wait_for(started.wait(), timeout=1)
                    assert "Live Deep Scan" in str(
                        app.screen.query_one("#scan-status", Static).render()
                    )
                    await pilot.press("l")
                    assert "already running" in str(
                        app.screen.query_one("#scan-status", Static).render()
                    )
                finally:
                    release.set()
                await pilot.pause()
                assert "Deep Scan complete" in str(
                    app.screen.query_one("#scan-status", Static).render()
                )
        app_owner.conn.close()
