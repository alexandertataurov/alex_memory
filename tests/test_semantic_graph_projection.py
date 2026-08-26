from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alex_memory.ai.repository import save_ai_success
from alex_memory.context.graph import SemanticGraphProjector
from alex_memory.database import connect
from alex_memory.models import AIBatch
from alex_memory.operational import EntityResolver, process_ai_batch
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


if __name__ == "__main__":
    unittest.main()
