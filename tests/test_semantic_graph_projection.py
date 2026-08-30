from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from alex_memory.ai.repository import save_ai_success
from alex_memory.context import ContextBuilder, ContextRequest
from alex_memory.context.graph import (
    SemanticGraphProjector,
    context_builder_relationship_parity_gaps,
    current_authoritative_edges,
)
from alex_memory.context.repository import ensure_relationship
from alex_memory.database import connect
from alex_memory.models import AIBatch
from alex_memory.operational import (
    EntityResolver,
    process_ai_batch,
    resolve_review_item,
)
from test_ai_pipeline import make_settings, message, valid_item


class SemanticGraphProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = make_settings(Path(self.directory.name))
        self.conn = connect(self.settings)
        self.conn.execute(
            "INSERT INTO chats(chat_id,title,chat_type) VALUES (100,'Work','group')"
        )
        self.conn.execute(
            """INSERT INTO messages(chat_id,message_id,date,text,is_outgoing,has_media)
               VALUES (100,1,'2026-08-24T10:00:00+00:00','Send the invoice',0,0)"""
        )

    def tearDown(self) -> None:
        self.conn.close()
        self.directory.cleanup()

    def test_accepted_task_project_edge_has_exact_claim_lineage(self) -> None:
        batch = AIBatch(100, "Work", [message()], "prompt")
        saved = save_ai_success(
            self.conn,
            batch,
            {
                "summary": "Project invoice work.",
                "items": [
                    valid_item()
                    | {
                        "kind": "project",
                        "title": "Project Amber",
                        "details": "Invoice work.",
                        "status": "informational",
                        "owner": "unknown",
                    },
                    valid_item()
                    | {
                        "project_name": "Project Amber",
                        "confidence": 0.96,
                    },
                ],
            },
            self.settings,
        )

        self.assertTrue(process_ai_batch(self.conn, saved.batch_id, self.settings))
        task_claim_id = self.conn.execute(
            """SELECT source_claim_id FROM ai_items
               WHERE batch_id=? AND kind='task'""",
            (saved.batch_id,),
        ).fetchone()[0]
        task_id, source_claim_id = self.conn.execute(
            "SELECT task_id,source_claim_id FROM tasks"
        ).fetchone()
        self.assertEqual(task_claim_id, source_claim_id)
        edge = self.conn.execute(
            """SELECT e.edge_id,e.authority_status,e.valid_from,e.valid_to
               FROM graph_edges AS e
               JOIN graph_nodes AS task ON task.node_id=e.from_node_id
               JOIN graph_nodes AS project ON project.node_id=e.to_node_id
               WHERE task.canonical_entity_type='task'
                 AND task.canonical_entity_id=?
                 AND project.canonical_entity_type='project'
                 AND e.relationship_type='belongs_to'""",
            (task_id,),
        ).fetchone()
        self.assertEqual("accepted", edge[1])
        self.assertEqual("2026-08-22T10:00:00+00:00", edge[2])
        self.assertIsNone(edge[3])
        self.assertEqual(
            [(task_claim_id,)],
            self.conn.execute(
                "SELECT claim_id FROM graph_edge_claims WHERE edge_id=?", (edge[0],)
            ).fetchall(),
        )
        self.assertEqual(
            "projected",
            self.conn.execute(
                "SELECT projection_status FROM semantic_claims WHERE claim_id=?",
                (task_claim_id,),
            ).fetchone()[0],
        )
        self.assertEqual(
            "resolved",
            self.conn.execute(
                """SELECT resolution_status FROM semantic_claim_entity_refs
                   WHERE claim_id=? AND entity_type='project'""",
                (task_claim_id,),
            ).fetchone()[0],
        )

    def test_replaying_the_same_claim_does_not_duplicate_graph_rows(self) -> None:
        batch = AIBatch(100, "Work", [message()], "prompt")
        saved = save_ai_success(
            self.conn,
            batch,
            {
                "summary": "Project invoice work.",
                "items": [
                    valid_item()
                    | {
                        "kind": "project",
                        "title": "Project Amber",
                        "details": "Invoice work.",
                        "status": "informational",
                        "owner": "unknown",
                    },
                    valid_item()
                    | {"project_name": "Project Amber", "confidence": 0.96},
                ],
            },
            self.settings,
        )
        self.assertTrue(process_ai_batch(self.conn, saved.batch_id, self.settings))
        task_item = self.conn.execute(
            """SELECT item_id,source_claim_id,source_date,person_id,company_id,project_id
               FROM ai_items WHERE batch_id=? AND kind='task'""",
            (saved.batch_id,),
        ).fetchone()
        task_id = self.conn.execute("SELECT task_id FROM tasks").fetchone()[0]
        before = tuple(
            self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("graph_nodes", "graph_edges", "graph_edge_claims")
        )

        SemanticGraphProjector(self.conn).project_item(
            claim_id=task_item[1],
            item_id=task_item[0],
            source_at=task_item[2],
            person_id=task_item[3],
            company_id=task_item[4],
            project_id=task_item[5],
            task_id=task_id,
        )

        after = tuple(
            self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("graph_nodes", "graph_edges", "graph_edge_claims")
        )
        self.assertEqual(before, after)

    def test_unaccepted_task_claim_has_no_accepted_relationship(self) -> None:
        batch = AIBatch(100, "Work", [message()], "prompt")
        saved = save_ai_success(
            self.conn,
            batch,
            {
                "summary": "Possible Project Amber task.",
                "items": [
                    valid_item()
                    | {
                        "project_name": "Project Amber",
                        "confidence": 0.6,
                    }
                ],
            },
            self.settings,
        )

        self.assertTrue(process_ai_batch(self.conn, saved.batch_id, self.settings))
        self.assertEqual(
            0,
            self.conn.execute(
                """SELECT COUNT(*) FROM graph_edges
                   WHERE relationship_type='belongs_to' AND authority_status='accepted'"""
            ).fetchone()[0],
        )
        self.assertEqual(
            1,
            self.conn.execute(
                """SELECT COUNT(*) FROM graph_nodes
                   WHERE node_key=(
                       SELECT 'claim:' || source_claim_id FROM ai_items
                       WHERE batch_id=?
                   ) AND authority_status='observed'""",
                (saved.batch_id,),
            ).fetchone()[0],
        )

    def test_manual_task_project_edge_blocks_automatic_replay(self) -> None:
        batch = AIBatch(100, "Work", [message()], "prompt")
        saved = save_ai_success(
            self.conn,
            batch,
            {
                "summary": "Project invoice work.",
                "items": [
                    valid_item()
                    | {
                        "kind": "project",
                        "title": "Project Amber",
                        "details": "Invoice work.",
                        "status": "informational",
                        "owner": "unknown",
                    },
                    valid_item()
                    | {"project_name": "Project Amber", "confidence": 0.96},
                ],
            },
            self.settings,
        )
        self.assertTrue(process_ai_batch(self.conn, saved.batch_id, self.settings))
        item = self.conn.execute(
            """SELECT item_id,source_claim_id,source_date,person_id,company_id,project_id
               FROM ai_items WHERE batch_id=? AND kind='task'""",
            (saved.batch_id,),
        ).fetchone()
        task_id = self.conn.execute("SELECT task_id FROM tasks").fetchone()[0]
        task_node_id = self.conn.execute(
            """SELECT node_id FROM graph_nodes
               WHERE node_key='canonical:task:' || ?""",
            (task_id,),
        ).fetchone()[0]
        manual_project_id = EntityResolver(self.conn).entity(
            "project", "Operator Project", source="manual"
        )
        assert manual_project_id is not None
        now = "2026-08-24T12:00:00+00:00"
        self.conn.execute(
            """INSERT INTO graph_nodes(
                   node_key,node_type,canonical_entity_type,canonical_entity_id,
                   properties_json,authority_status,created_at,updated_at
               ) VALUES (?,?,?,?,?,'manual',?,?)""",
            (
                f"canonical:project:{manual_project_id}",
                "project",
                "project",
                manual_project_id,
                "{}",
                now,
                now,
            ),
        )
        manual_node_id = self.conn.execute(
            "SELECT node_id FROM graph_nodes WHERE node_key=?",
            (f"canonical:project:{manual_project_id}",),
        ).fetchone()[0]
        self.conn.execute(
            """UPDATE graph_edges SET valid_to=?,authority_status='superseded'
               WHERE from_node_id=? AND relationship_type='belongs_to'""",
            (now, task_node_id),
        )
        self.conn.execute(
            """INSERT INTO graph_edges(
                   from_node_id,to_node_id,relationship_type,valid_from,valid_to,
                   first_seen_at,last_seen_at,confidence,authority_status,
                   properties_json,created_at,updated_at
               ) VALUES (?,?,'belongs_to',?,NULL,?,?,1.0,'manual','{}',?,?)""",
            (task_node_id, manual_node_id, now, now, now, now, now),
        )

        SemanticGraphProjector(self.conn).project_item(
            claim_id=item[1],
            item_id=item[0],
            source_at=item[2],
            person_id=item[3],
            company_id=item[4],
            project_id=item[5],
            task_id=task_id,
        )

        self.assertEqual(
            0,
            self.conn.execute(
                """SELECT COUNT(*) FROM graph_edges
                   WHERE from_node_id=? AND relationship_type='belongs_to'
                     AND authority_status='accepted' AND valid_to IS NULL""",
                (task_node_id,),
            ).fetchone()[0],
        )
        self.assertEqual(
            "review",
            self.conn.execute(
                "SELECT projection_status FROM semantic_claims WHERE claim_id=?",
                (item[1],),
            ).fetchone()[0],
        )

    def test_current_authoritative_edges_enforce_temporal_authority_and_lineage(
        self,
    ) -> None:
        batch = AIBatch(100, "Work", [message()], "prompt")
        saved = save_ai_success(
            self.conn,
            batch,
            {
                "summary": "Project invoice work.",
                "items": [
                    valid_item()
                    | {
                        "kind": "project",
                        "title": "Project Amber",
                        "details": "Invoice work.",
                        "status": "informational",
                        "owner": "unknown",
                    },
                    valid_item()
                    | {"project_name": "Project Amber", "confidence": 0.96},
                ],
            },
            self.settings,
        )
        self.assertTrue(process_ai_batch(self.conn, saved.batch_id, self.settings))
        task_id = self.conn.execute("SELECT task_id FROM tasks").fetchone()[0]

        edges = current_authoritative_edges(
            self.conn, [("task", task_id)], "2026-08-25T00:00:00+00:00"
        )

        self.assertEqual(1, len(edges))
        self.assertEqual("accepted", edges[0]["authority_status"])
        self.assertEqual("belongs_to", edges[0]["relationship_type"])
        self.assertTrue(edges[0]["claim_ids"])

        edge_id = edges[0]["edge_id"]
        task_node_id, project_node_id = self.conn.execute(
            """SELECT from_node_id,to_node_id FROM graph_edges WHERE edge_id=?""",
            (edge_id,),
        ).fetchone()
        self.conn.execute(
            "UPDATE graph_edges SET valid_to='2026-08-24T12:00:00+00:00' WHERE edge_id=?",
            (edge_id,),
        )
        self.assertEqual(
            [],
            current_authoritative_edges(
                self.conn, [("task", task_id)], "2026-08-25T00:00:00+00:00"
            ),
        )
        now = "2026-08-24T13:00:00+00:00"
        for authority_status in ("observed", "accepted"):
            self.conn.execute(
                """INSERT INTO graph_edges(
                       from_node_id,to_node_id,relationship_type,valid_from,valid_to,
                       first_seen_at,last_seen_at,confidence,authority_status,
                       properties_json,created_at,updated_at
                   ) VALUES (?,?,'belongs_to',?,NULL,?,?,0.9,?,'{}',?,?)""",
                (
                    task_node_id,
                    project_node_id,
                    now,
                    now,
                    now,
                    authority_status,
                    now,
                    now,
                ),
            )
        self.assertEqual(
            [],
            current_authoritative_edges(
                self.conn, [("task", task_id)], "2026-08-25T00:00:00+00:00"
            ),
        )
        self.conn.execute(
            """INSERT INTO graph_edges(
                   from_node_id,to_node_id,relationship_type,valid_from,valid_to,
                   first_seen_at,last_seen_at,confidence,authority_status,
                   properties_json,created_at,updated_at
               ) VALUES (?,?,'manually_confirmed',?,NULL,?,?,1.0,'manual','{}',?,?)""",
            (task_node_id, project_node_id, now, now, now, now, now),
        )
        self.assertEqual(
            [
                {
                    "authority_status": "manual",
                    "claim_ids": (),
                    "from_id": task_id,
                    "from_type": "task",
                    "relationship_type": "manually_confirmed",
                    "to_id": edges[0]["to_id"],
                    "to_type": "project",
                    "valid_from": now,
                    "valid_to": None,
                    "confidence": 1.0,
                    "edge_id": self.conn.execute(
                        "SELECT MAX(edge_id) FROM graph_edges"
                    ).fetchone()[0],
                }
            ],
            current_authoritative_edges(
                self.conn, [("task", task_id)], "2026-08-25T00:00:00+00:00"
            ),
        )

    def test_manual_person_company_relationships_have_accepted_graph_parity(
        self,
    ) -> None:
        batch = AIBatch(100, "Work", [message()], "prompt")
        saved = save_ai_success(
            self.conn,
            batch,
            {
                "summary": "Project invoice work.",
                "items": [
                    valid_item()
                    | {
                        "kind": "project",
                        "title": "Project Amber",
                        "details": "Invoice work.",
                        "status": "informational",
                        "owner": "unknown",
                    },
                    valid_item()
                    | {"project_name": "Project Amber", "confidence": 0.96},
                ],
            },
            self.settings,
        )
        self.assertTrue(process_ai_batch(self.conn, saved.batch_id, self.settings))
        task_id, project_id = self.conn.execute(
            "SELECT task_id,related_project_id FROM tasks"
        ).fetchone()
        person_id = EntityResolver(self.conn).entity("person", "Ari", source="manual")
        company_id = EntityResolver(self.conn).entity(
            "company", "Acme", source="manual"
        )
        assert person_id is not None
        assert company_id is not None
        as_of = "2026-08-25T00:00:00+00:00"
        for from_type, from_id, to_type, to_id, relationship_type in (
            ("person", person_id, "company", company_id, "works_for"),
            ("person", person_id, "project", project_id, "contributes_to"),
            ("company", company_id, "project", project_id, "delivers_for"),
        ):
            ensure_relationship(
                self.conn,
                from_type,
                from_id,
                to_type,
                to_id,
                relationship_type,
                0.95,
                100,
                1,
                "2026-08-24T10:00:00+00:00",
            )
        legacy_types = {
            tuple(row)
            for row in self.conn.execute(
                """SELECT from_type,relationship_type,to_type FROM relationships
                   WHERE valid_from<=? AND (valid_to IS NULL OR valid_to>?)""",
                (as_of, as_of),
            ).fetchall()
        }
        self.assertEqual(
            {
                ("person", "works_for", "company"),
                ("person", "contributes_to", "project"),
                ("company", "delivers_for", "project"),
            },
            legacy_types,
        )
        graph_types = {
            (edge["from_type"], edge["relationship_type"], edge["to_type"])
            for edge in current_authoritative_edges(
                self.conn,
                [
                    ("person", person_id),
                    ("company", company_id),
                    ("project", project_id),
                ],
                as_of,
            )
        }
        self.assertEqual({("task", "belongs_to", "project")}, graph_types)
        self.assertTrue(legacy_types.isdisjoint(graph_types))
        self.assertEqual(
            [
                {
                    "accepted_graph_authority": "missing",
                    "count": 1,
                    "from_type": "company",
                    "legacy_authority": "compatibility",
                    "relationship_type": "delivers_for",
                    "to_type": "project",
                },
                {
                    "accepted_graph_authority": "missing",
                    "count": 1,
                    "from_type": "person",
                    "legacy_authority": "compatibility",
                    "relationship_type": "contributes_to",
                    "to_type": "project",
                },
                {
                    "accepted_graph_authority": "missing",
                    "count": 1,
                    "from_type": "person",
                    "legacy_authority": "compatibility",
                    "relationship_type": "works_for",
                    "to_type": "company",
                },
            ],
            context_builder_relationship_parity_gaps(
                self.conn,
                [("person", person_id)],
                as_of,
            )["gaps"],
        )
        projector = SemanticGraphProjector(self.conn)
        for from_type, from_id, to_type, to_id, relationship_type in (
            ("person", person_id, "company", company_id, "works_for"),
            ("person", person_id, "project", project_id, "contributes_to"),
            ("company", company_id, "project", project_id, "delivers_for"),
        ):
            projector.project_manual_relationship(
                from_type=from_type,
                from_id=from_id,
                to_type=to_type,
                to_id=to_id,
                relationship_type=relationship_type,
                valid_from="2026-08-24T10:00:00+00:00",
            )

        accepted = current_authoritative_edges(
            self.conn,
            [
                ("person", person_id),
                ("company", company_id),
                ("project", project_id),
            ],
            as_of,
        )
        self.assertEqual(
            legacy_types | {("task", "belongs_to", "project")},
            {
                (edge["from_type"], edge["relationship_type"], edge["to_type"])
                for edge in accepted
            },
        )
        self.assertEqual(
            set(),
            {
                claim_id
                for edge in accepted
                if edge["authority_status"] == "manual"
                for claim_id in edge["claim_ids"]
            },
        )
        self.assertEqual(
            [],
            context_builder_relationship_parity_gaps(
                self.conn,
                [("person", person_id)],
                as_of,
            )["gaps"],
        )
        self.conn.execute(
            """UPDATE graph_edges SET authority_status='observed'
               WHERE relationship_type='works_for'"""
        )
        self.assertEqual(
            [
                {
                    "accepted_graph_authority": "missing",
                    "count": 1,
                    "from_type": "person",
                    "legacy_authority": "compatibility",
                    "relationship_type": "works_for",
                    "to_type": "company",
                }
            ],
            context_builder_relationship_parity_gaps(
                self.conn,
                [("person", person_id)],
                as_of,
            )["gaps"],
        )
        self.conn.execute(
            """UPDATE relationships SET valid_to='2026-08-24T12:00:00+00:00'
               WHERE relationship_type='works_for'"""
        )
        self.assertEqual(
            [],
            context_builder_relationship_parity_gaps(
                self.conn,
                [("person", person_id)],
                as_of,
            )["gaps"],
        )

    def test_accepted_graph_link_review_projects_manual_person_relationship(
        self,
    ) -> None:
        resolver = EntityResolver(self.conn)
        person_id = resolver.entity("person", "Ari", source="manual")
        project_id = resolver.entity("project", "Amber", source="manual")
        assert person_id is not None
        assert project_id is not None
        item_id = self.conn.execute(
            """INSERT INTO ai_items(
                   batch_id,kind,title,details,status,owner,confidence,
                   source_chat_id,source_message_id,source_date,person_id,created_at,
                   dedupe_key
               ) VALUES (1,'event','Planning','','informational','unknown',0.9,
                         100,1,'2026-08-24T10:00:00+00:00',?,'now','manual-link')""",
            (person_id,),
        ).lastrowid
        assert item_id is not None
        review_id = self.conn.execute(
            """INSERT INTO review_queue(
                   review_type,subject_type,subject_id,payload_json,confidence,created_at
               ) VALUES ('graph_link','ai_item',?,json_object(
                   'source_item_id',?,'candidate_project_id',?),0.9,'now')""",
            (item_id, item_id, project_id),
        ).lastrowid
        assert review_id is not None

        resolve_review_item(self.conn, int(review_id), "accept")

        edges = current_authoritative_edges(
            self.conn,
            [("person", person_id)],
            "2026-08-25T00:00:00+00:00",
        )
        self.assertEqual(
            [("person", person_id, "project", project_id, "involved_in", "manual")],
            [
                (
                    edge["from_type"],
                    edge["from_id"],
                    edge["to_type"],
                    edge["to_id"],
                    edge["relationship_type"],
                    edge["authority_status"],
                )
                for edge in edges
            ],
        )
        self.assertEqual((), edges[0]["claim_ids"])

    def test_parity_diagnostic_matches_context_builder_top_relationships(self) -> None:
        """A parity green result must cover the reader's ranked, not first, rows."""
        resolver = EntityResolver(self.conn)
        project_id = resolver.entity("project", "Amber", source="manual")
        assert project_id is not None
        projector = SemanticGraphProjector(self.conn)
        as_of = "2026-08-25T00:00:00+00:00"
        newest_company_id = None
        for index in range(81):
            company_id = resolver.entity("company", f"Company {index}", source="manual")
            assert company_id is not None
            ensure_relationship(
                self.conn,
                "project",
                project_id,
                "company",
                company_id,
                "uses_bank",
                1.0,
                100,
                index + 1,
                "2026-08-24T10:00:00+00:00",
            )
            if index < 80:
                projector.project_manual_relationship(
                    from_type="project",
                    from_id=project_id,
                    to_type="company",
                    to_id=company_id,
                    relationship_type="uses_bank",
                    valid_from="2026-08-24T10:00:00+00:00",
                )
            else:
                newest_company_id = company_id
        assert newest_company_id is not None
        self.conn.execute(
            """UPDATE relationships SET updated_at='2026-08-24T09:00:00+00:00'
               WHERE from_type='project' AND from_id=? AND to_type='company'
                 AND relationship_type='uses_bank'""",
            (project_id,),
        )
        self.conn.execute(
            """UPDATE relationships SET updated_at='2026-08-24T23:59:00+00:00'
               WHERE from_type='project' AND from_id=? AND to_type='company'
                 AND to_id=? AND relationship_type='uses_bank'""",
            (project_id, newest_company_id),
        )

        context = ContextBuilder(self.conn, self.settings).build(
            ContextRequest(
                project_ids=[project_id],
                as_of=datetime.fromisoformat(as_of),
            )
        )
        self.assertEqual(80, len(context.relationships))
        self.assertIn(
            newest_company_id,
            {relation["to_id"] for relation in context.relationships},
        )
        self.assertEqual(
            [
                {
                    "accepted_graph_authority": "missing",
                    "count": 1,
                    "from_type": "project",
                    "legacy_authority": "compatibility",
                    "relationship_type": "uses_bank",
                    "to_type": "company",
                }
            ],
            context_builder_relationship_parity_gaps(
                self.conn, [("project", project_id)], as_of
            )["gaps"],
        )

    def test_parity_diagnostic_marks_clipped_depth_inconclusive(self) -> None:
        report = context_builder_relationship_parity_gaps(
            self.conn,
            [("person", 1)],
            "2026-08-25T00:00:00+00:00",
            max_depth=5,
        )

        self.assertTrue(report["truncated"])


if __name__ == "__main__":
    unittest.main()
