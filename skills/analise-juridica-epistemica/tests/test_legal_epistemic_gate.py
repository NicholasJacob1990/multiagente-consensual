import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "legal_epistemic_gate.py"


class LegalEpistemicGateTests(unittest.TestCase):
    def run_gate(self, graph, artifact_content=None):
        with tempfile.TemporaryDirectory() as tmp:
            graph_path = Path(tmp) / "graph.json"
            graph_path.write_text(json.dumps(graph), encoding="utf-8")
            command = [sys.executable, str(SCRIPT), "validate", str(graph_path)]
            if artifact_content is not None:
                artifact_path = Path(tmp) / "artefato.md"
                artifact_path.write_text(artifact_content, encoding="utf-8")
                command.extend(["--artifact", str(artifact_path)])
            completed = subprocess.run(
                command,
                text=True,
                capture_output=True,
                check=False,
            )
            receipt = json.loads(completed.stdout) if completed.stdout else None
            return completed, receipt

    def valid_graph(self):
        return {
            "schema_version": "legal_epistemic_graph_v1",
            "graph_id": "caso-exemplo",
            "as_of": "2026-09-21",
            "mode": "analysis",
            "objective": {
                "owner": "consulente",
                "statement": "obter cumprimento preservando a relação",
                "status": "confirmed",
            },
            "sources": [
                {
                    "id": "S1",
                    "kind": "case_document",
                    "status": "verified",
                    "locator": "contrato.pdf:clausula-8",
                    "sha256": "a" * 64,
                }
            ],
            "propositions": [
                {
                    "id": "P1",
                    "kind": "fact",
                    "statement": "A obrigação venceu sem cumprimento",
                    "status": "confirmed",
                    "source_refs": ["S1"],
                    "impact": "decisive",
                },
                {
                    "id": "C1",
                    "kind": "conclusion",
                    "statement": "A medida de cobrança é juridicamente sustentada",
                    "status": "unknown",
                    "source_refs": [],
                    "impact": "decisive",
                    "decisive": True,
                },
            ],
            "rules": [
                {
                    "id": "R1",
                    "kind": "strict",
                    "when": [
                        {"proposition": "P1", "statuses": ["confirmed"]}
                    ],
                    "unless": [],
                    "then": "C1",
                    "priority": 100,
                    "source_refs": ["S1"],
                }
            ],
            "conflicts": [],
            "grants": [],
            "actions": [],
        }

    def test_valid_graph_derives_conclusion_with_proof_trace(self):
        """Catches an engine that validates syntax but never performs inference."""
        completed, receipt = self.run_gate(self.valid_graph())

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(receipt["conforms"])
        self.assertEqual(receipt["violations"], [])
        self.assertEqual(receipt["accepted_conclusions"][0]["id"], "C1")
        self.assertEqual(receipt["accepted_conclusions"][0]["derived_by"], "R1")
        self.assertEqual(receipt["accepted_conclusions"][0]["source_refs"], ["S1"])

    def test_decisive_conclusion_without_source_or_rule_is_rejected(self):
        """Catches silent promotion of an unsupported conclusion to confirmed."""
        graph = self.valid_graph()
        graph["rules"] = []
        graph["propositions"][1]["status"] = "confirmed"

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 2)
        self.assertFalse(receipt["conforms"])
        self.assertIn(
            "CONCLUSION_WITHOUT_PROVENANCE",
            {item["code"] for item in receipt["violations"]},
        )

    def test_authorized_action_without_a_grant_is_rejected(self):
        """Catches an agent treating a proposed capability as delegated authority."""
        graph = self.valid_graph()
        graph["actions"] = [
            {
                "id": "A1",
                "actor": "agente-redator",
                "operation": "protocolar",
                "target": "processo-123",
                "state": "authorized",
                "grant_id": "G-ausente",
            }
        ]

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 2)
        self.assertIn(
            "ACTION_WITHOUT_VALID_GRANT",
            {item["code"] for item in receipt["violations"]},
        )

    def test_proposed_external_action_exposes_pending_authorization(self):
        """Catches a proposal that hides the human grant needed before execution."""
        graph = self.valid_graph()
        graph["actions"] = [
            {
                "id": "A1",
                "actor": "agente-redator",
                "operation": "enviar_negativa",
                "target": "cliente-123",
                "state": "proposed",
            }
        ]

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIsNotNone(receipt.get("pending_authorizations"), receipt)
        self.assertEqual(receipt.get("pending_authorizations")[0]["id"], "A1")
        self.assertIn(
            "external_authorization",
            {item["type"] for item in receipt["required_human_decisions"]},
        )
        authorization = next(
            item
            for item in receipt["required_human_decisions"]
            if item["type"] == "external_authorization"
        )
        self.assertEqual(authorization["owner"], "consulente")

    def test_grant_must_match_actor_operation_and_target(self):
        """Catches reuse of a real grant outside its exact delegated scope."""
        graph = self.valid_graph()
        graph["grants"] = [
            {
                "id": "G1",
                "grantee": "agente-redator",
                "operation": "protocolar",
                "target": "processo-999",
                "status": "active",
                "valid_from": "2026-09-01",
                "valid_until": "2026-09-30",
            }
        ]
        graph["actions"] = [
            {
                "id": "A1",
                "actor": "agente-redator",
                "operation": "protocolar",
                "target": "processo-123",
                "state": "authorized",
                "grant_id": "G1",
            }
        ]

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 2)
        violation = next(
            item
            for item in receipt["violations"]
            if item["code"] == "ACTION_WITHOUT_VALID_GRANT"
        )
        self.assertIn("target", violation["mismatches"])

    def test_expired_grant_cannot_authorize_action(self):
        """Catches authority that matches scope but is no longer temporally valid."""
        graph = self.valid_graph()
        graph["grants"] = [
            {
                "id": "G1",
                "grantee": "agente-redator",
                "operation": "protocolar",
                "target": "processo-123",
                "status": "active",
                "valid_from": "2026-08-01",
                "valid_until": "2026-08-31",
            }
        ]
        graph["actions"] = [
            {
                "id": "A1",
                "actor": "agente-redator",
                "operation": "protocolar",
                "target": "processo-123",
                "state": "authorized",
                "grant_id": "G1",
            }
        ]

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 2)
        violation = next(
            item
            for item in receipt["violations"]
            if item["code"] == "ACTION_WITHOUT_VALID_GRANT"
        )
        self.assertIn("valid_until", violation["mismatches"])

    def test_equal_strength_conflicting_rules_require_resolution(self):
        """Catches arbitrary selection between equally supported legal conclusions."""
        graph = self.valid_graph()
        graph["propositions"].append(
            {
                "id": "C2",
                "kind": "conclusion",
                "statement": "A medida de cobrança não é juridicamente sustentada",
                "status": "unknown",
                "source_refs": [],
                "impact": "decisive",
                "decisive": True,
            }
        )
        graph["rules"][0]["kind"] = "defeasible"
        graph["rules"][0]["priority"] = 10
        graph["rules"].append(
            {
                "id": "R2",
                "kind": "defeasible",
                "when": [{"proposition": "P1", "statuses": ["confirmed"]}],
                "unless": [],
                "then": "C2",
                "priority": 10,
                "source_refs": ["S1"],
            }
        )
        graph["conflicts"] = [{"left": "C1", "right": "C2"}]

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 2)
        self.assertIn(
            "UNRESOLVED_RULE_CONFLICT",
            {item["code"] for item in receipt["violations"]},
        )

    def test_higher_priority_rule_defeats_conflicting_conclusion(self):
        """Catches a solver that reports both sides after a declared priority resolves them."""
        graph = self.valid_graph()
        graph["propositions"].append(
            {
                "id": "C2",
                "kind": "conclusion",
                "statement": "A medida de cobrança não é juridicamente sustentada",
                "status": "unknown",
                "source_refs": [],
                "impact": "decisive",
                "decisive": True,
            }
        )
        graph["rules"][0]["kind"] = "defeasible"
        graph["rules"][0]["priority"] = 20
        graph["rules"].append(
            {
                "id": "R2",
                "kind": "defeasible",
                "when": [{"proposition": "P1", "statuses": ["confirmed"]}],
                "unless": [],
                "then": "C2",
                "priority": 10,
                "source_refs": ["S1"],
            }
        )
        graph["conflicts"] = [{"left": "C1", "right": "C2"}]

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(
            [item["id"] for item in receipt["accepted_conclusions"]], ["C1"]
        )
        self.assertEqual(receipt["defeated_conclusions"][0]["id"], "C2")
        self.assertEqual(receipt["defeated_conclusions"][0]["defeated_by"], "C1")

    def test_confirmed_exception_blocks_rule_and_is_explained(self):
        """Catches inference that ignores a confirmed exception to the legal rule."""
        graph = self.valid_graph()
        graph["propositions"].append(
            {
                "id": "E1",
                "kind": "fact",
                "statement": "Há exceção contratual aplicável",
                "status": "confirmed",
                "source_refs": ["S1"],
                "impact": "decisive",
            }
        )
        graph["rules"][0]["unless"] = [
            {"proposition": "E1", "statuses": ["confirmed"]}
        ]

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 2)
        self.assertIn(
            "CONCLUSION_BLOCKED_BY_EXCEPTION",
            {item["code"] for item in receipt["violations"]},
        )
        self.assertEqual(receipt["blocked_rules"][0]["id"], "R1")
        self.assertEqual(receipt["blocked_rules"][0]["exceptions"], ["E1"])

    def test_missing_governing_objective_creates_human_decision_gate(self):
        """Catches an agent silently choosing the client's practical objective."""
        graph = self.valid_graph()
        graph["objective"]["status"] = "unknown"
        graph["objective"]["statement"] = ""

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 2)
        self.assertIn(
            "OBJECTIVE_NOT_GOVERNED",
            {item["code"] for item in receipt["violations"]},
        )
        self.assertEqual(
            receipt["required_human_decisions"][0]["type"], "governing_objective"
        )
        self.assertEqual(
            [item["id"] for item in receipt["accepted_conclusions"]], ["C1"]
        )

    def test_decisive_unknown_dependency_blocks_conclusion(self):
        """Catches a derived conclusion that hides a decisive missing fact."""
        graph = self.valid_graph()
        graph["propositions"].append(
            {
                "id": "U1",
                "kind": "unknown",
                "statement": "Não consta se houve notificação válida",
                "status": "unknown",
                "source_refs": [],
                "impact": "decisive",
                "owner": "consulente",
            }
        )
        graph["propositions"][1]["depends_on"] = ["U1"]
        graph["rules"][0]["unless"] = [
            {"proposition": "U1", "statuses": ["confirmed"]}
        ]

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 2)
        self.assertIn(
            "DECISIVE_UNKNOWN_DEPENDENCY",
            {item["code"] for item in receipt["violations"]},
        )
        self.assertIn(
            "U1",
            {
                item.get("proposition")
                for item in receipt["required_human_decisions"]
            },
        )
        self.assertNotIn(
            "C1", {item["id"] for item in receipt["accepted_conclusions"]}
        )
        self.assertEqual(receipt["conditional_conclusions"][0]["id"], "C1")
        self.assertEqual(
            receipt["conditional_conclusions"][0]["depends_on"], ["U1"]
        )
        self.assertEqual(
            receipt.get("potential_exceptions"),
            [{"id": "R1", "target": "C1", "exceptions": ["U1"]}],
        )

    def test_artifact_hash_must_match_graph_snapshot(self):
        """Catches approval of a file different from the one represented by the graph."""
        graph = self.valid_graph()
        graph["artifact"] = {
            "path": "artefato.md",
            "sha256": "0" * 64,
        }

        completed, receipt = self.run_gate(graph, artifact_content="versão efetiva")

        self.assertIsNotNone(receipt, completed.stderr)
        self.assertEqual(completed.returncode, 2)
        self.assertIn(
            "ARTIFACT_HASH_MISMATCH",
            {item["code"] for item in receipt["violations"]},
        )

    def test_derived_conclusion_requires_verified_source_chain(self):
        """Catches inference that is logically connected but evidentially ungrounded."""
        graph = self.valid_graph()
        graph["propositions"][0]["source_refs"] = []
        graph["rules"][0]["source_refs"] = []

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 2)
        self.assertIn(
            "DERIVATION_WITHOUT_VERIFIED_SOURCE",
            {item["code"] for item in receipt["violations"]},
        )

    def test_duplicate_identifiers_are_rejected_before_inference(self):
        """Catches ambiguous graph nodes that would be silently overwritten in a map."""
        graph = self.valid_graph()
        duplicate = dict(graph["propositions"][0])
        duplicate["statement"] = "Versão incompatível do mesmo identificador"
        graph["propositions"].append(duplicate)

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 2)
        violation = next(
            item for item in receipt["violations"] if item["code"] == "DUPLICATE_ID"
        )
        self.assertEqual(violation["subject"], "P1")

    def test_rule_with_dangling_proposition_reference_is_rejected(self):
        """Catches rules that appear valid but depend on a nonexistent proposition."""
        graph = self.valid_graph()
        graph["rules"][0]["when"][0]["proposition"] = "P-ausente"

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 2)
        matches = [
            item
            for item in receipt["violations"]
            if item["code"] == "DANGLING_REFERENCE"
        ]
        self.assertTrue(matches, receipt["violations"])
        violation = matches[0]
        self.assertEqual(violation["reference"], "P-ausente")
        self.assertEqual(violation["subject"], "R1")

    def test_receipt_can_be_persisted_for_the_agent_ledger(self):
        """Catches a CLI that validates but cannot leave an auditable receipt."""
        with tempfile.TemporaryDirectory() as tmp:
            graph_path = Path(tmp) / "graph.json"
            receipt_path = Path(tmp) / "receipt.json"
            graph_path.write_text(json.dumps(self.valid_graph()), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "validate",
                    str(graph_path),
                    "--out",
                    str(receipt_path),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(receipt_path.exists())
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            self.assertTrue(receipt["conforms"])
            self.assertEqual(receipt["graph_id"], "caso-exemplo")

    def test_agent_consensus_cannot_be_used_as_evidentiary_source(self):
        """Catches consensus being relabeled as verified evidence for a conclusion."""
        graph = self.valid_graph()
        graph["sources"][0]["kind"] = "agent_consensus"

        completed, receipt = self.run_gate(graph)

        self.assertEqual(completed.returncode, 2)
        self.assertIn(
            "INVALID_EVIDENCE_SOURCE",
            {item["code"] for item in receipt["violations"]},
        )


if __name__ == "__main__":
    unittest.main()
