import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "legal_analysis_controls.py"


class LegalAnalysisControlsTests(unittest.TestCase):
    def run_control(self, command, payload):
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), command, str(input_path)],
                text=True,
                capture_output=True,
                check=False,
            )
            receipt = json.loads(completed.stdout) if completed.stdout else None
            return completed, receipt

    def test_discovery_results_do_not_satisfy_primary_research_gate(self):
        """Catches local RAG material being promoted to verified jurisprudence."""
        payload = {
            "schema_version": "legal_research_bundle_v1",
            "query_id": "Q1",
            "as_of": "2026-09-21",
            "requirements": {
                "primary_required": True,
                "negative_claim_requested": False,
                "adverse_search_required": True,
            },
            "providers": [
                {
                    "id": "jurisbase",
                    "role": "primary",
                    "status": "unavailable",
                    "coverage": {"reason": "postgres_offline"},
                    "queries": [],
                    "results": [],
                },
                {
                    "id": "qmd",
                    "role": "discovery",
                    "status": "available",
                    "queries": [
                        {"id": "qmd-1", "stance": "supports", "text": "boa-fé"},
                        {"id": "qmd-2", "stance": "opposes", "text": "boa-fé abuso"},
                    ],
                    "results": [
                        {
                            "id": "qmd-doc-1",
                            "canonical_key": "acervo:nota-1",
                            "title": "Nota doutrinária",
                            "rank": 1,
                            "source_kind": "doctrine",
                            "verified_primary": False,
                            "stance": "supports",
                        }
                    ],
                },
            ],
        }

        completed, receipt = self.run_control("research-fusion", payload)

        self.assertEqual(completed.returncode, 2)
        self.assertIsNotNone(receipt, completed.stderr)
        self.assertEqual(receipt["research_status"], "discovery_only")
        self.assertEqual(receipt["fused_results"][0]["canonical_key"], "acervo:nota-1")
        self.assertIn(
            "PRIMARY_PROVIDER_UNAVAILABLE",
            {item["code"] for item in receipt["violations"]},
        )

    def test_research_requires_an_adverse_query_when_configured(self):
        """Catches a confirmatory search that never looks for contrary authority."""
        payload = {
            "schema_version": "legal_research_bundle_v1",
            "query_id": "Q2",
            "as_of": "2026-09-21",
            "requirements": {
                "primary_required": True,
                "negative_claim_requested": False,
                "adverse_search_required": True,
            },
            "providers": [
                {
                    "id": "jurisbase",
                    "role": "primary",
                    "status": "available",
                    "coverage": {"complete": True},
                    "queries": [
                        {"id": "j-1", "stance": "supports", "text": "boa-fé"}
                    ],
                    "results": [
                        {
                            "id": "decisao-1",
                            "canonical_key": "jurisbase:decisao-1",
                            "title": "Acórdão",
                            "rank": 1,
                            "source_kind": "decision",
                            "verified_primary": True,
                            "stance": "supports",
                        }
                    ],
                }
            ],
        }

        completed, receipt = self.run_control("research-fusion", payload)

        self.assertEqual(completed.returncode, 2)
        self.assertIn(
            "ADVERSE_SEARCH_MISSING",
            {item["code"] for item in receipt["violations"]},
        )

    def test_local_adverse_search_does_not_replace_primary_adverse_search(self):
        """Catches a contrary QMD query satisfying the jurisprudence search gate."""
        payload = {
            "schema_version": "legal_research_bundle_v1", "query_id": "Q2B",
            "as_of": "2026-09-21",
            "requirements": {"primary_required": True, "adverse_search_required": True,
                             "negative_claim_requested": False},
            "providers": [
                {"id": "jurisbase", "role": "primary", "status": "available",
                 "coverage": {"complete": False},
                 "queries": [{"id": "j1", "stance": "supports", "text": "tese"}],
                 "results": [{"id": "p1", "canonical_key": "p1", "title": "Tema",
                              "rank": 1, "verified_primary": True,
                              "source_kind": "precedent"}]},
                {"id": "qmd", "role": "discovery", "status": "available",
                 "coverage": {},
                 "queries": [{"id": "q1", "stance": "opposes", "text": "tese contrária"}],
                 "results": []},
            ],
        }
        completed, receipt = self.run_control("research-fusion", payload)
        self.assertEqual(completed.returncode, 2)
        self.assertIn("ADVERSE_SEARCH_MISSING", {v["code"] for v in receipt["violations"]})

    def test_negative_research_claim_requires_complete_primary_coverage(self):
        """Catches 'no precedent exists' when the official corpus is incomplete."""
        payload = {
            "schema_version": "legal_research_bundle_v1",
            "query_id": "Q3",
            "as_of": "2026-09-21",
            "requirements": {
                "primary_required": True,
                "negative_claim_requested": True,
                "adverse_search_required": False,
            },
            "providers": [
                {
                    "id": "jurisbase",
                    "role": "primary",
                    "status": "partial",
                    "coverage": {"complete": False, "reason": "tribunal_not_collected"},
                    "queries": [
                        {"id": "j-1", "stance": "neutral", "text": "tese rara"}
                    ],
                    "results": [],
                }
            ],
        }

        completed, receipt = self.run_control("research-fusion", payload)

        self.assertEqual(completed.returncode, 2)
        self.assertIn(
            "NEGATIVE_SEARCH_UNSUPPORTED",
            {item["code"] for item in receipt["violations"]},
        )

    def test_partial_primary_with_no_verified_item_cannot_close_research_gate(self):
        """Catches an available but incomplete primary index being treated as verified."""
        payload = {
            "schema_version": "legal_research_bundle_v1", "query_id": "Q3D",
            "as_of": "2026-09-21",
            "requirements": {"primary_required": True, "negative_claim_requested": False,
                             "adverse_search_required": False},
            "providers": [{"id": "jurisbase", "role": "primary", "status": "partial",
                           "coverage": {"complete": False, "reason": "tribunal_not_collected"},
                           "queries": [{"id": "j1", "stance": "neutral", "text": "tese"}],
                           "results": []}],
        }
        completed, receipt = self.run_control("research-fusion", payload)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(receipt["research_status"], "unavailable")
        self.assertIn("PRIMARY_EVIDENCE_NOT_VERIFIED", {v["code"] for v in receipt["violations"]})

    def test_complete_primary_search_can_report_verified_no_hits(self):
        """Catches conflation of a complete negative search with provider failure."""
        payload = {
            "schema_version": "legal_research_bundle_v1",
            "query_id": "Q3B",
            "as_of": "2026-09-21",
            "requirements": {
                "primary_required": True,
                "negative_claim_requested": True,
                "adverse_search_required": False,
            },
            "providers": [
                {
                    "id": "jurisbase",
                    "role": "primary",
                    "status": "available",
                    "coverage": {"complete": True, "sources_checked": ["STJ"]},
                    "queries": [
                        {"id": "j-1", "stance": "neutral", "text": "tese rara"}
                    ],
                    "results": [],
                }
            ],
        }

        completed, receipt = self.run_control("research-fusion", payload)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(receipt["research_status"], "verified_no_hits")
        self.assertEqual(receipt["violations"], [])
        self.assertEqual(receipt["scope"]["jurisbase"]["sources_checked"], ["STJ"])
        self.assertEqual(receipt["query_log"]["jurisbase"][0]["id"], "j-1")

    def test_empty_query_log_cannot_substantiate_negative_search(self):
        """Catches a coverage label declaring absence without any executed query."""
        payload = {
            "schema_version": "legal_research_bundle_v1", "query_id": "Q3C",
            "as_of": "2026-09-21",
            "requirements": {"primary_required": True, "negative_claim_requested": True,
                             "adverse_search_required": False},
            "providers": [{"id": "jurisbase", "role": "primary", "status": "available",
                           "coverage": {"complete": True, "sources_checked": ["STJ"]},
                           "queries": [], "results": []}],
        }
        completed, receipt = self.run_control("research-fusion", payload)
        self.assertEqual(completed.returncode, 2)
        self.assertNotEqual(receipt["research_status"], "verified_no_hits")
        self.assertIn("NEGATIVE_SEARCH_UNSUPPORTED", {v["code"] for v in receipt["violations"]})

    def test_discovery_provider_cannot_mark_result_as_primary_verified(self):
        """Catches QMD or ChromaDB output falsely labeled as official verification."""
        payload = {
            "schema_version": "legal_research_bundle_v1",
            "query_id": "Q4",
            "as_of": "2026-09-21",
            "requirements": {
                "primary_required": False,
                "negative_claim_requested": False,
                "adverse_search_required": False,
            },
            "providers": [
                {
                    "id": "qmd",
                    "role": "discovery",
                    "status": "available",
                    "coverage": {},
                    "queries": [],
                    "results": [
                        {
                            "id": "q1",
                            "canonical_key": "acervo:q1",
                            "title": "Resumo local",
                            "rank": 1,
                            "source_kind": "precedent",
                            "verified_primary": True,
                            "stance": "supports",
                        }
                    ],
                }
            ],
        }

        completed, receipt = self.run_control("research-fusion", payload)

        self.assertEqual(completed.returncode, 2)
        self.assertIn(
            "DISCOVERY_PROVIDER_CLAIMS_PRIMARY",
            {item["code"] for item in receipt["violations"]},
        )
        self.assertFalse(receipt["fused_results"][0]["verified_primary"])

    def test_fused_duplicate_uses_verified_primary_metadata_and_retains_origins(self):
        """Catches a local summary being displayed as if it were the official result."""
        payload = {
            "schema_version": "legal_research_bundle_v1",
            "query_id": "Q5",
            "as_of": "2026-09-21",
            "requirements": {"primary_required": True, "adverse_search_required": False,
                             "negative_claim_requested": False},
            "providers": [
                {"id": "qmd", "role": "discovery", "status": "available",
                 "coverage": {}, "queries": [{"id": "q1", "stance": "neutral", "text": "tema 7"}],
                 "results": [{"id": "local-7", "canonical_key": "STJ:tema-7",
                              "title": "Resumo pessoal", "rank": 1,
                              "source_kind": "note", "verified_primary": False,
                              "query_id": "q1"}]},
                {"id": "jurisbase", "role": "primary", "status": "available",
                 "coverage": {"complete": False},
                 "queries": [{"id": "j1", "stance": "neutral", "text": "tema 7"}],
                 "results": [{"id": "precedente-7", "canonical_key": "STJ:tema-7",
                              "title": "Tema 7 do STJ", "rank": 2,
                              "source_kind": "precedent", "verified_primary": True,
                              "query_id": "j1", "official_url": "https://stj.jus.br/tema7"}]},
            ],
        }

        completed, receipt = self.run_control("research-fusion", payload)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        item = receipt["fused_results"][0]
        self.assertEqual(item["title"], "Tema 7 do STJ")
        self.assertEqual(item["source_kind"], "precedent")
        self.assertTrue(item["verified_primary"])
        self.assertEqual(item["providers"], ["jurisbase", "qmd"])
        self.assertEqual(
            {(origin["provider"], origin["id"], origin["query_id"])
             for origin in item["origins"]},
            {("qmd", "local-7", "q1"), ("jurisbase", "precedente-7", "j1")},
        )

    def test_precedent_comparison_uses_verified_cases_and_exposes_distinctions(self):
        """Catches nearest-text selection that ignores verification and material factors."""
        payload = {
            "schema_version": "precedent_factor_bundle_v1",
            "case_id": "CASO-1",
            "factors": [
                {"id": "F1", "value": "present", "weight": 3},
                {"id": "F2", "value": "present", "weight": 2},
            ],
            "precedents": [
                {
                    "id": "P-VERIFICADO",
                    "verified_primary": True,
                    "outcome": "supports",
                    "factors": {"F1": "present", "F2": "absent"},
                },
                {
                    "id": "P-NAO-VERIFICADO",
                    "verified_primary": False,
                    "outcome": "supports",
                    "factors": {"F1": "present", "F2": "present"},
                },
                {
                    "id": "P-CONTRARIO",
                    "verified_primary": True,
                    "outcome": "opposes",
                    "factors": {"F1": "absent", "F2": "present"},
                },
            ],
        }

        completed, receipt = self.run_control("precedent-factors", payload)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIsNotNone(receipt, completed.stderr)
        self.assertEqual(receipt["best_supporting"], "P-VERIFICADO")
        self.assertEqual(receipt["best_opposing"], "P-CONTRARIO")
        self.assertIn("P-NAO-VERIFICADO", receipt["excluded_precedents"])
        comparison = next(
            item for item in receipt["comparisons"] if item["id"] == "P-VERIFICADO"
        )
        self.assertEqual(comparison["matched_factors"], ["F1"])
        self.assertEqual(comparison["distinguished_factors"], ["F2"])

    def test_precedent_with_one_known_factor_does_not_beat_broader_match(self):
        """Catches a sparse precedent scoring 100% by ignoring missing factors."""
        payload = {
            "schema_version": "precedent_factor_bundle_v1", "case_id": "CASO-SPARSE",
            "factors": [{"id": f"F{i}", "value": "present", "weight": 1}
                        for i in range(1, 6)],
            "precedents": [
                {"id": "P-SPARSE", "verified_primary": True, "outcome": "supports",
                 "factors": {"F1": "present"}},
                {"id": "P-BROAD", "verified_primary": True, "outcome": "supports",
                 "factors": {"F1": "present", "F2": "present", "F3": "present",
                             "F4": "present", "F5": "absent"}},
            ],
        }
        completed, receipt = self.run_control("precedent-factors", payload)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(receipt["best_supporting"], "P-BROAD")
        by_id = {p["id"]: p for p in receipt["comparisons"]}
        self.assertLess(by_id["P-SPARSE"]["coverage"], by_id["P-BROAD"]["coverage"])

    def test_strategy_respects_preconditions_authority_and_robustness(self):
        """Catches strategic recommendations that ignore state or human authority."""
        payload = {
            "schema_version": "procedural_strategy_bundle_v1",
            "case_id": "CASO-2",
            "state": {"facts": ["prazo_aberto", "citacao_valida"], "grants": []},
            "objectives": [{"id": "O1", "priority": "must"}],
            "actions": [
                {
                    "id": "A-INVIAVEL",
                    "preconditions": ["documento_novo_disponivel"],
                    "authority_required": False,
                    "reversible": True,
                    "responses": [],
                },
                {
                    "id": "A-BLOQUEADA",
                    "preconditions": ["prazo_aberto"],
                    "authority_required": True,
                    "grant_id": None,
                    "authority_owner": "cliente",
                    "reversible": False,
                    "responses": [],
                },
                {
                    "id": "A-ROBUSTA",
                    "preconditions": ["prazo_aberto", "citacao_valida"],
                    "authority_required": False,
                    "reversible": True,
                    "responses": [
                        {"id": "R1", "satisfies": ["O1"]},
                        {"id": "R2", "satisfies": ["O1"]},
                    ],
                },
            ],
        }

        completed, receipt = self.run_control("strategy-tree", payload)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIsNotNone(receipt, completed.stderr)
        self.assertEqual(receipt["feasible_actions"], ["A-ROBUSTA"])
        self.assertEqual(receipt["robust_actions"], ["A-ROBUSTA"])
        blocked = {item["id"]: item["reason"] for item in receipt["blocked_actions"]}
        self.assertEqual(blocked["A-INVIAVEL"], "unmet_preconditions")
        self.assertEqual(blocked["A-BLOQUEADA"], "authority_required")
        self.assertEqual(
            receipt["required_human_decisions"][0]["owner"], "cliente"
        )
        self.assertTrue(receipt["not_execution_authorization"])

    def test_credibility_matrix_exposes_conflict_without_scalar_verdict(self):
        """Catches automated truth scores that collapse distinct evidentiary dimensions."""
        payload = {
            "schema_version": "credibility_bundle_v1",
            "case_id": "CASO-3",
            "claims": [{"id": "C1", "statement": "A notificação foi recebida"}],
            "evidence": [
                {
                    "id": "E1",
                    "claim_id": "C1",
                    "stance": "supports",
                    "contradicts": ["E2"],
                    "dimensions": {
                        "internal_consistency": "supported",
                        "corroboration": "independent",
                        "opportunity": "direct",
                        "incentive": "unknown",
                        "chain_of_custody": "verified",
                    },
                },
                {
                    "id": "E2",
                    "claim_id": "C1",
                    "stance": "opposes",
                    "contradicts": ["E1"],
                    "dimensions": {
                        "internal_consistency": "supported",
                        "corroboration": "none",
                        "opportunity": "indirect",
                        "incentive": "interested",
                        "chain_of_custody": "unknown",
                    },
                },
            ],
        }

        completed, receipt = self.run_control("credibility-matrix", payload)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIsNotNone(receipt, completed.stderr)
        profile = receipt["claim_profiles"][0]
        self.assertEqual(profile["supporting_evidence"], ["E1"])
        self.assertEqual(profile["opposing_evidence"], ["E2"])
        self.assertEqual(receipt["contradictions"], [["E1", "E2"]])
        self.assertNotIn("credibility_score", receipt)
        self.assertTrue(receipt["human_judgment_required"])

    def test_elicitation_prioritizes_decision_impact_over_easy_low_value_questions(self):
        """Catches interviews ordered by convenience instead of value to the decision."""
        payload = {
            "schema_version": "tacit_elicitation_bundle_v1",
            "case_id": "CASO-4",
            "unknowns": [
                {
                    "id": "U-DECISIVO",
                    "question": "Preservar a relação é mais importante que rescindir?",
                    "owner": "cliente",
                    "impact": "decisive",
                    "branching": 4,
                    "reversibility": "irreversible",
                    "ease": 2,
                    "effect_if_unanswered": "estratégias incompatíveis permanecem abertas",
                },
                {
                    "id": "U-FACIL",
                    "question": "Qual formato de relatório prefere?",
                    "owner": "cliente",
                    "impact": "low",
                    "branching": 1,
                    "reversibility": "reversible",
                    "ease": 4,
                    "effect_if_unanswered": "ajuste editorial posterior",
                },
            ],
        }

        completed, receipt = self.run_control("elicitation-queue", payload)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIsNotNone(receipt, completed.stderr)
        self.assertEqual(
            [item["id"] for item in receipt["queue"]], ["U-DECISIVO", "U-FACIL"]
        )
        self.assertGreater(
            receipt["queue"][0]["priority_score"],
            receipt["queue"][1]["priority_score"],
        )
        self.assertEqual(receipt["queue"][0]["owner"], "cliente")

    def test_persuasion_gate_preserves_required_arguments_and_rejects_new_claims(self):
        """Catches stylistic rewriting that drops rebuttals or invents unsupported content."""
        payload = {
            "schema_version": "persuasion_bundle_v1",
            "artifact_id": "PETICAO-1",
            "content_hash_base": "a" * 64,
            "argument_map": [
                {"id": "T1", "role": "thesis", "required": True, "source_refs": ["S1"]},
                {"id": "R1", "role": "rebuttal", "required": True, "source_refs": ["S2"]},
                {"id": "P1", "role": "request", "required": True, "source_refs": []},
            ],
            "draft_manifest": {
                "content_hash_base": "a" * 64,
                "genre": "petition",
                "audience": "court",
                "tone": "firm_evidenced",
                "claim_ids": ["T1", "P1"],
                "new_claims": [{"id": "N1", "source_refs": []}],
            },
        }

        completed, receipt = self.run_control("persuasion-gate", payload)

        self.assertEqual(completed.returncode, 2)
        self.assertIsNotNone(receipt, completed.stderr)
        codes = {item["code"] for item in receipt["violations"]}
        self.assertIn("REQUIRED_ARGUMENT_MISSING", codes)
        self.assertIn("UNSUPPORTED_NEW_CLAIM", codes)
        self.assertEqual(receipt["missing_arguments"], ["R1"])
        self.assertEqual(receipt["unsupported_new_claims"], ["N1"])

    def test_control_receipt_can_be_written_atomically(self):
        """Catches controls that cannot leave a durable receipt for the run ledger."""
        payload = {
            "schema_version": "tacit_elicitation_bundle_v1",
            "case_id": "CASO-5",
            "unknowns": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            input_path = Path(tmp) / "input.json"
            output_path = Path(tmp) / "receipt.json"
            input_path.write_text(json.dumps(payload), encoding="utf-8")

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "elicitation-queue",
                    str(input_path),
                    "--out",
                    str(output_path),
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertTrue(output_path.exists())
            receipt = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(receipt["case_id"], "CASO-5")
            import hashlib
            self.assertEqual(
                receipt["input_sha256"],
                hashlib.sha256(input_path.read_bytes()).hexdigest(),
            )

    def test_empty_persuasion_bundle_cannot_pass(self):
        """Catches a supposedly approved rewrite with no map, draft or hash."""
        completed, receipt = self.run_control("persuasion-gate", {})
        self.assertEqual(completed.returncode, 2)
        self.assertFalse(receipt["conforms"])
        self.assertIn("INVALID_INPUT_CONTRACT", {v["code"] for v in receipt["violations"]})

    def test_wrong_provider_shape_returns_structured_violation(self):
        """Catches malformed input crashing before an auditable receipt is produced."""
        payload = {
            "schema_version": "legal_research_bundle_v1", "query_id": "Q-BAD",
            "providers": None,
        }
        completed, receipt = self.run_control("research-fusion", payload)
        self.assertEqual(completed.returncode, 2)
        self.assertIsNotNone(receipt, completed.stderr)
        self.assertIn("INVALID_INPUT_CONTRACT", {v["code"] for v in receipt["violations"]})

    def test_provider_entry_with_wrong_type_returns_structured_violation(self):
        """Catches malformed provider lists crashing before a receipt exists."""
        payload = {
            "schema_version": "legal_research_bundle_v1", "query_id": "Q-BAD-2",
            "providers": ["jurisbase"],
        }
        completed, receipt = self.run_control("research-fusion", payload)
        self.assertEqual(completed.returncode, 2)
        self.assertIsNotNone(receipt, completed.stderr)
        self.assertIn("INVALID_INPUT_CONTRACT", {v["code"] for v in receipt["violations"]})


if __name__ == "__main__":
    unittest.main()
