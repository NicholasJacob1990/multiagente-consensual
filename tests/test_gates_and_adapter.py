#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import copy
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = load_module("cli_adapter", ROOT / "skills/consenso/scripts/cli_adapter.py")
consensus = load_module("consensus_gate", ROOT / "skills/consenso/scripts/consensus_gate.py")
collegiate = load_module("collegiate_gate", ROOT / "skills/consenso/scripts/collegiate_gate.py")
provenance = load_module("provenance_test", ROOT / "scripts/provenance.py")
packager = load_module("package_plugin", ROOT / "scripts/package_plugin.py")
loop_limits = load_module(
    "loop_limits", ROOT / "skills/loop-debate-agentes/scripts/loop_limits.py"
)
durable_run = load_module(
    "durable_run", ROOT / "skills/loop-debate-agentes/scripts/durable_run.py"
)
workflow_engine = load_module(
    "workflow_engine", ROOT / "skills/workflow-agentes/scripts/protocol_engine.py"
)
publication_policy = load_module(
    "publication_policy",
    ROOT / "skills/loop-debate-agentes/scripts/publication_policy.py",
)


class AdapterAndGateTests(unittest.TestCase):
    @staticmethod
    def durable_overlay(max_seconds: int = 432000) -> dict[str, object]:
        return {
            "contrato": "durable_execution_v1",
            "perfil": "durable_5d_v1",
            "ativa": True,
            "relogio": "tempo_corrido",
            "max_segundos": max_seconds,
            "offline_conta_no_prazo": True,
            "checkpoint_apos": [
                "chamada", "rodada", "ciclo", "versao", "no", "onda", "join"
            ],
            "retomar_apos_reinicio": True,
            "gravacao_checkpoint": "atomica",
            "idempotencia": "event_id+input_sha256",
            "orcamento_diario": {"max_chamadas": 100, "max_custo": None},
            "orcamento_total": {"max_chamadas": 500, "max_custo": None},
        }

    def test_adapter_timeout_policy(self) -> None:
        self.assertEqual(adapter.timeout_value("1800"), 1800)
        self.assertEqual(adapter.timeout_value("3600"), 3600)
        with self.assertRaises(Exception):
            adapter.timeout_value("3601")

    def test_loop_and_legal_profiles_define_twenty_version_ceiling(self) -> None:
        loop_skill = (ROOT / "skills/loop-debate-agentes/SKILL.md").read_text(encoding="utf-8")
        loop_protocol = (
            ROOT / "skills/loop-debate-agentes/references/protocolo.md"
        ).read_text(encoding="utf-8")
        legal_skill = (
            ROOT / "skills/redacao-juridica-consensual/SKILL.md"
        ).read_text(encoding="utf-8")
        word_contract = (
            ROOT
            / "skills/redacao-juridica-consensual/references/controle-alteracoes-word.md"
        ).read_text(encoding="utf-8")

        self.assertIn("configurar de 1 a 20 versões completas", loop_skill)
        self.assertIn('"tentativas_maximas_motor": 20', loop_protocol)
        self.assertIn('"versoes_maximas_por_artefato": 20', loop_protocol)
        self.assertIn("Não produza `v21`", loop_skill)
        self.assertIn("configurar de 1 a 20 versões", legal_skill)
        self.assertIn("minuta-v20-limpa.docx", word_contract)

    def test_loop_limit_accepts_twenty_and_rejects_twenty_one(self) -> None:
        accepted = loop_limits.validate_config(
            {"ciclo_de_melhoria": {"tentativas": 20}, "loop": {"tentativas": 20}}
        )
        rejected = loop_limits.validate_config(
            {"ciclo_de_melhoria": {"tentativas": 21}, "loop": {"tentativas": 21}}
        )
        divergent = loop_limits.validate_config(
            {"ciclo_de_melhoria": {"tentativas": 20}, "loop": {"tentativas": 19}}
        )

        self.assertTrue(accepted["valid"])
        self.assertEqual(accepted["tentativas_efetivas"], 20)
        self.assertFalse(rejected["valid"])
        self.assertFalse(divergent["valid"])

    def test_durable_profile_accepts_five_days_and_rejects_more(self) -> None:
        accepted = durable_run.validate_durable_config(
            {
                "execucao_duravel": self.durable_overlay(),
                "limites_operacionais": {"tempo_maximo_minutos": 7200},
                "timeout_invocacao": {
                    "padrao_segundos": 1800,
                    "maximo_excepcional_segundos": 3600,
                },
            }
        )
        rejected = durable_run.validate_durable_config(
            {"execucao_duravel": self.durable_overlay(432001)}
        )
        self.assertTrue(accepted["valid"])
        self.assertEqual(accepted["max_elapsed_seconds"], 432000)
        self.assertFalse(rejected["valid"])

    def test_durable_unlimited_budget_requires_explicit_confirmation(self) -> None:
        overlay = self.durable_overlay()
        overlay["orcamento_diario"] = {"max_chamadas": None, "max_custo": None}
        overlay["orcamento_total"] = {"max_chamadas": None, "max_custo": None}
        rejected = durable_run.validate_durable_config({"execucao_duravel": overlay})
        self.assertFalse(rejected["valid"])
        overlay["orcamento_ilimitado_confirmado"] = True
        accepted = durable_run.validate_durable_config({"execucao_duravel": overlay})
        self.assertTrue(accepted["valid"])
        for invalid_cost in (float("nan"), float("inf"), float("-inf")):
            malformed = self.durable_overlay()
            malformed["orcamento_diario"] = {
                "max_chamadas": None,
                "max_custo": invalid_cost,
            }
            malformed["orcamento_total"] = {
                "max_chamadas": None,
                "max_custo": invalid_cost,
            }
            report = durable_run.validate_durable_config(
                {"execucao_duravel": malformed}
            )
            self.assertFalse(report["valid"])

    def test_durable_requires_deadline_and_rejects_forged_approval_state(self) -> None:
        overlay = self.durable_overlay()
        overlay.pop("max_segundos")
        report = durable_run.validate_durable_config({"execucao_duravel": overlay})
        self.assertFalse(report["valid"])
        self.assertTrue(any("max_segundos é obrigatório" in item for item in report["errors"]))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "meta.json"
            checkpoint_path = root / "checkpoint.json"
            config_path.write_text(
                json.dumps({"run_id": "estado-forte", "execucao_duravel": self.durable_overlay()}),
                encoding="utf-8",
            )
            cli_clock = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "skills/loop-debate-agentes/scripts/durable_run.py"),
                    "init",
                    str(config_path),
                    str(checkpoint_path),
                    "--now",
                    "2026-08-14T00:00:00Z",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(cli_clock.returncode, 2)
            self.assertIn("--allow-test-clock", cli_clock.stdout)
            now = datetime(2026, 8, 14, tzinfo=timezone.utc)
            durable_run.initialize(config_path, checkpoint_path, now)
            with self.assertRaisesRegex(ValueError, "gate externo"):
                durable_run.checkpoint(
                    checkpoint_path,
                    boundary="chamada",
                    event_id="call-approved",
                    input_sha256="a" * 64,
                    output_sha256="b" * 64,
                    state="aprovado",
                    now=now,
                )

    def test_durable_checkpoint_is_idempotent_and_expires_by_wall_clock(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "meta.json"
            checkpoint_path = root / "checkpoint.json"
            config_path.write_text(
                json.dumps({"run_id": "cinco-dias", "execucao_duravel": self.durable_overlay()}),
                encoding="utf-8",
            )
            started = datetime(2026, 8, 14, tzinfo=timezone.utc)
            durable_run.initialize(config_path, checkpoint_path, started)
            self.assertEqual(
                stat.S_IMODE(checkpoint_path.with_name("checkpoint.json.lock").stat().st_mode),
                0o600,
            )
            first = durable_run.checkpoint(
                checkpoint_path,
                boundary="chamada",
                event_id="call-001",
                input_sha256="a" * 64,
                output_sha256="b" * 64,
                state="executando",
                now=started,
            )
            duplicate = durable_run.checkpoint(
                checkpoint_path,
                boundary="chamada",
                event_id="call-001",
                input_sha256="a" * 64,
                output_sha256="b" * 64,
                state="executando",
                now=started,
            )
            before_deadline = durable_run._status_payload(
                durable_run._load_checkpoint(checkpoint_path),
                datetime(2026, 8, 18, 23, 59, 59, tzinfo=timezone.utc),
            )
            at_deadline = durable_run.resume(
                checkpoint_path, datetime(2026, 8, 19, tzinfo=timezone.utc)
            )
            self.assertEqual(first["sequencia"], 1)
            self.assertTrue(duplicate["duplicado"])
            self.assertEqual(duplicate["sequencia"], 1)
            self.assertTrue(before_deadline["retomavel"])
            self.assertFalse(at_deadline["retomavel"])
            self.assertEqual(at_deadline["estado"], "limite_operacional")
            with self.assertRaisesRegex(ValueError, "output_sha256 diferente"):
                durable_run.checkpoint(
                    checkpoint_path,
                    boundary="chamada",
                    event_id="call-001",
                    input_sha256="a" * 64,
                    output_sha256="c" * 64,
                    state="executando",
                    now=started,
                )

    def test_workflow_and_loop_validate_the_same_durable_overlay(self) -> None:
        workflow = {
            "perfil": "workflow_agents_v1",
            "protocolo": "pipeline_serial_v1",
            "objetivo": "produzir artefato",
            "participantes": [],
            "estrutura": {"etapas": [{"id": "redigir"}]},
            "limites": {"max_paralelo": 1, "max_segundos": 432000},
            "execucao_duravel": self.durable_overlay(),
        }
        loop = {
            "loop": {"tentativas": 6},
            "ciclo_de_melhoria": {"tentativas": 6},
            "limites_operacionais": {"tempo_maximo_minutos": 7200},
            "execucao_duravel": self.durable_overlay(),
        }
        workflow_report = workflow_engine.validate_config(workflow)
        loop_report = loop_limits.validate_config(loop)
        self.assertTrue(workflow_report["valid"])
        self.assertTrue(loop_report["valid"])
        self.assertEqual(
            workflow_engine.make_plan(workflow)["execucao_duravel"]["max_segundos"],
            432000,
        )

    def test_reviewer_publication_requires_explicit_shared_policy(self) -> None:
        safe_default = publication_policy.validate_config({})
        self.assertTrue(safe_default["valid"])
        self.assertEqual(safe_default["modo_publicacao"], "parecer_apenas")

        incomplete = publication_policy.validate_config(
            {"contribuicao_revisor": {"modo_publicacao": "publicar_canonico"}}
        )
        self.assertFalse(incomplete["valid"])

        config = {
            "contribuicao_revisor": {
                "modo_publicacao": "publicar_canonico",
                "publicadores_autorizados": [{"id": "codex-revisor"}],
                "publicacao_direta_sem_reincorporacao": True,
                "substituicao_automatica": False,
            },
            "consolidacao_iterativa": {
                "politica": "publicacao_compartilhada",
                "publicadores_autorizados": [{"id": "codex-revisor"}],
                "publicador_da_proxima_versao": {"id": "codex-revisor"},
                "controle_concorrencia": "base_sha256",
                "gravacao": "atomica",
            },
        }
        self.assertTrue(publication_policy.validate_config(config)["valid"])
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            canonical = root / "texto.md"
            candidate = root / "candidata.md"
            canonical.write_text("versão 1\n", encoding="utf-8")
            candidate.write_text("versão 2\n", encoding="utf-8")
            base = provenance.hash_file(canonical)["sha256"]
            digest = provenance.hash_file(candidate)["sha256"]
            receipt = {
                "schema": "publicacao_canonica_v1",
                "autor": {"id": "codex-revisor"},
                "base_sha256": base,
                "canonico_corrente_sha256": base,
                "sha256": digest,
                "versao_corrente": 1,
                "nova_versao": 2,
                "versoes_maximas": 20,
                "caminho_canonico": "texto.md",
                "caminho_candidato": "candidata.md",
                "chave_idempotencia": "publicacao-teste-0001",
            }
            self.assertTrue(
                publication_policy.validate_receipt(config, receipt, root=root)["valid"]
            )
            real_ledger = root / "real-publication-ledger.json"
            real_ledger.write_text(
                json.dumps({
                    "schema": publication_policy.PUBLICATION_LEDGER_CONTRACT,
                    "publicacoes": {},
                }),
                encoding="utf-8",
            )
            linked_ledger = root / "linked-publication-ledger.json"
            linked_ledger.symlink_to(real_ledger)
            with self.assertRaisesRegex(ValueError, "não pode ser symlink"):
                publication_policy.publish(
                    config,
                    receipt,
                    root=root,
                    ledger_path=linked_ledger,
                    secret=b"p" * 32,
                )
            self.assertEqual(canonical.read_text(encoding="utf-8"), "versão 1\n")
            published = publication_policy.publish(
                config,
                receipt,
                root=root,
                ledger_path=root / "publication-ledger.json",
                secret=b"p" * 32,
            )
            self.assertTrue(published["valid"])
            self.assertEqual(canonical.read_text(encoding="utf-8"), "versão 2\n")
            replay = publication_policy.publish(
                config,
                receipt,
                root=root,
                ledger_path=root / "publication-ledger.json",
                secret=b"p" * 32,
            )
            self.assertTrue(replay["idempotent_replay"])
            conflict = dict(receipt)
            conflict["sha256"] = "c" * 64
            self.assertFalse(
                publication_policy.publish(
                    config,
                    conflict,
                    root=root,
                    ledger_path=root / "publication-ledger.json",
                    secret=b"p" * 32,
                )["valid"]
            )

    def test_publication_rejects_nonexistent_and_symlink_candidates(self) -> None:
        config = {
            "contribuicao_revisor": {
                "modo_publicacao": "publicar_canonico",
                "publicadores_autorizados": ["revisor"],
                "publicacao_direta_sem_reincorporacao": True,
                "substituicao_automatica": False,
            },
            "consolidacao_iterativa": {
                "politica": "publicacao_compartilhada",
                "publicadores_autorizados": ["revisor"],
                "publicador_da_proxima_versao": "revisor",
                "controle_concorrencia": "base_sha256",
                "gravacao": "atomica",
            },
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            canonical = root / "canonico.md"
            external = root.parent / f"{root.name}-external.md"
            canonical.write_text("base", encoding="utf-8")
            external.write_text("fora", encoding="utf-8")
            (root / "link.md").symlink_to(external)
            base = provenance.hash_file(canonical)["sha256"]
            receipt = {
                "schema": "publicacao_canonica_v1",
                "autor": "revisor",
                "base_sha256": base,
                "canonico_corrente_sha256": base,
                "sha256": provenance.hash_file(external)["sha256"],
                "versao_corrente": 1,
                "nova_versao": 2,
                "versoes_maximas": 20,
                "caminho_canonico": "canonico.md",
                "caminho_candidato": "link.md",
                "chave_idempotencia": "publicacao-teste-0002",
            }
            report = publication_policy.validate_receipt(config, receipt, root=root)
            self.assertFalse(report["valid"])
            self.assertTrue(any("symlink" in item for item in report["errors"]))
            external.unlink(missing_ok=True)

    def test_publication_wal_recovers_crash_after_canonical_replace(self) -> None:
        config = {
            "contribuicao_revisor": {
                "modo_publicacao": "publicar_canonico",
                "publicadores_autorizados": ["revisor"],
                "publicacao_direta_sem_reincorporacao": True,
                "substituicao_automatica": False,
            },
            "consolidacao_iterativa": {
                "politica": "publicacao_compartilhada",
                "publicadores_autorizados": ["revisor"],
                "publicador_da_proxima_versao": "revisor",
                "controle_concorrencia": "base_sha256",
                "gravacao": "atomica",
            },
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            canonical = root / "canonico.md"
            candidate = root / "candidata.md"
            canonical.write_text("base", encoding="utf-8")
            candidate.write_text("nova", encoding="utf-8")
            base = provenance.hash_file(canonical)["sha256"]
            digest = provenance.hash_file(candidate)["sha256"]
            receipt = {
                "schema": "publicacao_canonica_v1",
                "autor": "revisor",
                "base_sha256": base,
                "canonico_corrente_sha256": base,
                "sha256": digest,
                "versao_corrente": 1,
                "nova_versao": 2,
                "versoes_maximas": 20,
                "caminho_canonico": "canonico.md",
                "caminho_candidato": "candidata.md",
                "chave_idempotencia": "publicacao-wal-0001",
            }
            ledger = root / "publication-ledger.json"
            prepared = {
                "schema": "publication_ledger_v1",
                "publicacoes": {
                    receipt["chave_idempotencia"]: {
                        "autor": "revisor",
                        "caminho_canonico": "canonico.md",
                        "caminho_candidato": "candidata.md",
                        "base_sha256": base,
                        "sha256": digest,
                        "nova_versao": 2,
                        "estado": "prepared",
                    }
                },
            }
            ledger.write_text(json.dumps(prepared), encoding="utf-8")
            canonical.write_bytes(candidate.read_bytes())
            recovered = publication_policy.publish(
                config,
                receipt,
                root=root,
                ledger_path=ledger,
                secret=b"w" * 32,
            )
            self.assertTrue(recovered["valid"])
            self.assertTrue(recovered["recovered"])
            committed = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual(
                committed["publicacoes"][receipt["chave_idempotencia"]]["estado"],
                "committed",
            )

    def test_publication_shared_ledger_preserves_parallel_distinct_canons(self) -> None:
        config = {
            "contribuicao_revisor": {
                "modo_publicacao": "publicar_canonico",
                "publicadores_autorizados": ["revisor"],
                "publicacao_direta_sem_reincorporacao": True,
                "substituicao_automatica": False,
            },
            "consolidacao_iterativa": {
                "politica": "publicacao_compartilhada",
                "publicadores_autorizados": ["revisor"],
                "publicador_da_proxima_versao": "revisor",
                "controle_concorrencia": "base_sha256",
                "gravacao": "atomica",
            },
        }
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            ledger = root / "publication-ledger.json"
            receipt_paths: list[Path] = []
            for index in range(8):
                canonical = root / f"canonico-{index}.md"
                candidate = root / f"candidata-{index}.md"
                canonical.write_text(f"base-{index}", encoding="utf-8")
                candidate.write_text(f"nova-{index}", encoding="utf-8")
                receipt = {
                    "schema": "publicacao_canonica_v1",
                    "autor": "revisor",
                    "base_sha256": provenance.hash_file(canonical)["sha256"],
                    "canonico_corrente_sha256": provenance.hash_file(canonical)["sha256"],
                    "sha256": provenance.hash_file(candidate)["sha256"],
                    "versao_corrente": 1,
                    "nova_versao": 2,
                    "versoes_maximas": 20,
                    "caminho_canonico": canonical.name,
                    "caminho_candidato": candidate.name,
                    "chave_idempotencia": f"publicacao-paralela-{index:04d}",
                }
                receipt_path = root / f"receipt-{index}.json"
                receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
                receipt_paths.append(receipt_path)
            env = os.environ.copy()
            env["MULTIAGENT_ATTESTATION_KEY"] = "p" * 64
            processes = [
                subprocess.Popen(
                    [
                        sys.executable,
                        str(ROOT / "skills/loop-debate-agentes/scripts/publication_policy.py"),
                        "publish",
                        str(config_path),
                        str(receipt_path),
                        "--root",
                        str(root),
                        "--ledger",
                        str(ledger),
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    env=env,
                )
                for receipt_path in receipt_paths
            ]
            outputs = [process.communicate(timeout=20) for process in processes]
            self.assertTrue(all(process.returncode == 0 for process in processes), outputs)
            payload = json.loads(ledger.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["publicacoes"]), 8)
            self.assertTrue(all(item["estado"] == "committed" for item in payload["publicacoes"].values()))

    def test_legal_recipes_compile_to_canonical_fields(self) -> None:
        recipes = (
            ROOT
            / "skills/redacao-juridica-consensual/references/receitas-juridicas.md"
        ).read_text(encoding="utf-8")
        protocol = (
            ROOT
            / "skills/redacao-juridica-consensual/references/protocolo-juridico.md"
        ).read_text(encoding="utf-8")

        self.assertIn("`estrategia_da_equipe.tipo = ensemble_nxn`", recipes)
        self.assertIn("`perfil_base = debate_agents_v1`", recipes)
        self.assertIn("`pacote.itens[].overrides.extensoes_dominio.juridico.receita`", recipes)
        self.assertIn("juízo de admissibilidade ou ato", recipes)
        self.assertIn("versões finais independentes sem matriz N×N", recipes)
        self.assertNotIn("subtipo_familia", recipes)
        self.assertIn('"receita": {', protocol)
        self.assertIn('"requested": {}', protocol)
        self.assertIn("configuracao sem receita declarada -> receita.origem = legado", protocol)

    def test_packaged_manifest_fallback(self) -> None:
        resolved = adapter.resolve_manifest(None)
        self.assertTrue(resolved.is_file())
        data = json.loads(resolved.read_text(encoding="utf-8"))
        self.assertEqual(data["contract"], "multiagent_local_v1")

    def test_build_invocation_prompt_channels(self) -> None:
        root = ROOT.resolve()
        prompt_path = root / "README.md"
        for route in ("codex", "claude", "cursor"):
            command, stdin, _env = adapter.build_invocation(
                route, route, route, root, prompt_path, "segredo", "modelo", None,
                "adaptive_up_to_native_max",
            )
            self.assertIsNotNone(stdin, route)
            self.assertFalse(any("segredo" in item for item in command), route)
        command, stdin, _env = adapter.build_invocation(
            "gemini", "antigravity", "agy", root, prompt_path, "segredo",
            "gemini-3.7-flash-high", None, "adaptive_up_to_native_max",
        )
        self.assertIsNone(stdin)
        self.assertIn("--print", command)
        self.assertFalse(any("segredo" in item for item in command))
        command, stdin, _env = adapter.build_invocation(
            "gemini", "gemini", "gemini", root, prompt_path, "segredo", "modelo", None,
            "adaptive_up_to_native_max",
        )
        self.assertIsNone(stdin)
        self.assertIn("--prompt", command)
        self.assertFalse(any("segredo" in item for item in command))
        command, stdin, _env = adapter.build_invocation(
            "kimi", "kimi", "kimi", root, prompt_path, "segredo", "kimi-code/k3", "max",
            "adaptive_up_to_native_max",
        )
        self.assertIsNone(stdin)
        self.assertIn("--prompt", command)
        self.assertNotIn("--yolo", command)
        self.assertNotIn("--auto", command)
        self.assertFalse(any("segredo" in item for item in command))

    def test_native_session_persistence_is_explicit_and_optional(self) -> None:
        root = ROOT.resolve()
        prompt_path = root / "README.md"
        native_id = "11111111-1111-4111-8111-111111111111"

        codex_default, _stdin, _env = adapter.build_invocation(
            "codex", "codex", "codex", root, prompt_path, "teste", None, None,
            "adaptive_up_to_native_max",
        )
        self.assertIn("--ephemeral", codex_default)
        codex_saved, _stdin, _env = adapter.build_invocation(
            "codex", "codex", "codex", root, prompt_path, "teste", None, None,
            "adaptive_up_to_native_max", persist_native_session=True,
            native_output_path=root / "last.txt",
        )
        self.assertNotIn("--ephemeral", codex_saved)
        self.assertIn("--json", codex_saved)

        claude_default, _stdin, _env = adapter.build_invocation(
            "claude", "claude", "claude", root, prompt_path, "teste", None, None,
            "adaptive_up_to_native_max",
        )
        self.assertIn("--no-session-persistence", claude_default)
        claude_saved, _stdin, _env = adapter.build_invocation(
            "claude", "claude", "claude", root, prompt_path, "teste", None, None,
            "adaptive_up_to_native_max", persist_native_session=True,
            native_session_id=native_id,
        )
        self.assertNotIn("--no-session-persistence", claude_saved)
        self.assertEqual(claude_saved[claude_saved.index("--session-id") + 1], native_id)

        gemini_saved, _stdin, _env = adapter.build_invocation(
            "gemini", "gemini", "gemini", root, prompt_path, "teste", None, None,
            "adaptive_up_to_native_max", persist_native_session=True,
            native_session_id=native_id,
        )
        self.assertEqual(gemini_saved[gemini_saved.index("--session-id") + 1], native_id)

        opencode_saved, _stdin, _env = adapter.build_invocation(
            "opencode", "opencode", "opencode", root, prompt_path, "teste", None, None,
            "adaptive_up_to_native_max", persist_native_session=True,
            native_session_label=f"multiagent-{native_id}",
        )
        self.assertEqual(
            opencode_saved[opencode_saved.index("--title") + 1], f"multiagent-{native_id}"
        )

    def test_opencode_argv_scope_and_secret_environment_are_fail_closed(self) -> None:
        root = ROOT.resolve()
        prompt = root / "README.md"
        old_secret = os.environ.get("MULTIAGENT_ATTESTATION_KEY")
        os.environ["MULTIAGENT_ATTESTATION_KEY"] = "s" * 64
        try:
            command, _stdin, env = adapter.build_invocation(
                "opencode", "opencode", "opencode", root, prompt, "teste",
                "opencode-go/glm-5.3", "max", "adaptive_up_to_native_max",
            )
        finally:
            if old_secret is None:
                os.environ.pop("MULTIAGENT_ATTESTATION_KEY", None)
            else:
                os.environ["MULTIAGENT_ATTESTATION_KEY"] = old_secret
        self.assertLess(command.index("--model") + 2, command.index("--file"))
        self.assertEqual(command[command.index("--variant") + 1], "max")
        self.assertNotIn("MULTIAGENT_ATTESTATION_KEY", env)
        claude, _stdin, _env = adapter.build_invocation(
            "claude", "claude", "claude", root, prompt, "teste",
            "claude-opus-5", None, "adaptive_up_to_native_max",
        )
        self.assertNotIn(str(Path.home()), claude)
        with self.assertRaises(RuntimeError):
            adapter.safe_root(str(Path.home()))

    def test_provenance_accepts_isolated_execution_and_rejects_forged_route(self) -> None:
        manifest = provenance.load_manifest(ROOT / "assets/multiagent-manifest.json")
        secret = b"z" * 32
        receipt = {
            "schema": "multiagent_provenance_v1",
            "run_id": "run-teste",
            "cadeira": "codex",
            "rota": "codex",
            "provedor": "openai",
            "nonce": "nonce-proveniencia-0001",
            "tentativa": 1,
            "rodada": 1,
            "argv_sha256": "a" * 64,
            "entrada_sha256": "b" * 64,
            "saida_sha256": "c" * 64,
            "artefato_sha256": "d" * 64,
            "emitido_em": "2026-08-14T12:00:00Z",
            "modelo_efetivo": "gpt-5.6-sol",
            "modelo_confirmado": True,
            "execucao_efetiva": True,
            "execucao_id": "execucao-isolada-0001",
            "isolamento_execucao_confirmado": True,
            "sessao_id": None,
            "sessao_confirmada": False,
        }
        signed = provenance.sign_receipt(receipt, secret)
        self.assertEqual(provenance.validate_receipt(signed, manifest, secret), [])
        forged = dict(receipt)
        forged["rota"] = "claude"
        forged = provenance.sign_receipt(forged, secret)
        self.assertTrue(provenance.validate_receipt(forged, manifest, secret))

    def test_structured_model_confirmation_is_observed_not_requested(self) -> None:
        observed, rendered, models = adapter.structured_observation(
            json.dumps({"model": "claude-opus-5", "result": "ok"}),
            "claude-opus-5",
        )
        self.assertEqual(observed, "claude-opus-5")
        self.assertEqual(rendered, "ok")
        self.assertEqual(models, ["claude-opus-5"])
        not_observed, _rendered, models = adapter.structured_observation(
            json.dumps({"model": "fallback-model", "result": "ok"}),
            "claude-opus-5",
        )
        self.assertIsNone(not_observed)
        self.assertEqual(models, ["fallback-model"])
        echoed, _rendered, models = adapter.structured_observation(
            json.dumps({
                "model": "fallback-model",
                "result": {"text": "ok", "model": "claude-opus-5"},
            }),
            "claude-opus-5",
        )
        self.assertIsNone(echoed)
        self.assertEqual(models, ["fallback-model"])
        mixed, _rendered, models = adapter.structured_observation(
            json.dumps({
                "modelUsage": {"claude-opus-5": {}, "fallback-model": {}},
                "result": "ok",
            }),
            "claude-opus-5",
        )
        self.assertIsNone(mixed)
        self.assertEqual(models, ["claude-opus-5", "fallback-model"])

    def test_native_session_confirmation_reads_only_cli_envelope(self) -> None:
        self.assertIsNone(adapter.structured_session_observation("", "claude"))
        self.assertIsNone(adapter.structured_session_observation(
            json.dumps({"result": {"session_id": "echo-controlado"}}), "claude"
        ))
        self.assertEqual(
            adapter.structured_session_observation(
                json.dumps({"session_id": "sessao-observada", "result": "ok"}), "claude"
            ),
            "sessao-observada",
        )

    def test_required_native_routes_and_opencode_default(self) -> None:
        manifest = adapter.load_manifest(str(ROOT / "assets/multiagent-manifest.json"))
        claude = adapter.resolve_seat(manifest, "claude", None)
        codex = adapter.resolve_seat(manifest, "codex", None)
        kimi = adapter.resolve_seat(manifest, "kimi", None)
        gemini = adapter.resolve_seat(manifest, "gemini", None)
        opencode = adapter.resolve_seat(manifest, "opencode", None)
        self.assertEqual(claude["route"], "claude")
        self.assertEqual(claude["model"], "claude-opus-5")
        self.assertEqual(adapter.resolve_seat(manifest, "claude", "opus")["model"], "claude-opus-5")
        with self.assertRaises(RuntimeError):
            adapter.resolve_seat(manifest, "claude", "claude-sonnet-5")
        self.assertEqual(codex["route"], "codex")
        self.assertEqual(codex["model"], "gpt-5.6-sol")
        self.assertEqual(codex["default_effort"], "xhigh")
        with self.assertRaises(RuntimeError):
            adapter.resolve_seat(manifest, "codex", "outro-modelo")
        self.assertEqual(kimi["route"], "kimi")
        self.assertEqual(kimi["model"], "kimi-code/k3")
        self.assertEqual(kimi["default_effort"], "max")
        self.assertEqual(kimi["context_window_tokens"], 1048576)
        self.assertEqual(gemini["route"], "antigravity")
        self.assertEqual(gemini["model"], "gemini-3.7-flash-high")
        self.assertEqual(opencode["route"], "opencode")
        self.assertEqual(opencode["model"], "opencode-go/glm-5.3")
        self.assertEqual(adapter.resolve_effort(opencode, None), "max")
        requested = adapter.resolve_seat(manifest, "opencode", "opencode-go/qwen3.8-max")
        self.assertEqual(requested["model"], "opencode-go/qwen3.8-max")
        self.assertEqual(adapter.resolve_effort(requested, None), "max")
        with self.assertRaises(RuntimeError):
            adapter.resolve_effort(requested, "high")
        for participant in ("glm", "deepseek", "qwen"):
            resolved = adapter.resolve_seat(manifest, participant, None)
            self.assertEqual(resolved["default_effort"], "max")
            self.assertEqual(resolved["effort_policy"], "fixed_max")
            self.assertEqual(adapter.resolve_effort(resolved, None), "max")
        non_chinese = adapter.resolve_seat(manifest, "opencode", "acme/modelo-externo")
        self.assertIsNone(adapter.resolve_effort(non_chinese, None))

    def test_consensus_rejects_duplicate_or_unrouted_seats(self) -> None:
        contract = consensus.load_contract(ROOT / "assets/multiagent-manifest.json")
        digest = "a" * 64
        verdict = {
            "schema": "veredito_consenso_v1",
            "modo": "estrito",
            "politica_por_tentativa": "sempre",
            "resultado": "consenso",
            "aprovacao": True,
            "simulacao": False,
            "artefato_sha256": digest,
            "participantes": [
                {"cadeira": "A", "rota": "codex", "modelo": "gpt", "provedor": "openai"},
                {"cadeira": "A", "rota": "claude", "modelo": "claude-opus-5", "provedor": "anthropic"},
            ],
            "bloqueadores": [],
            "dissensos": [],
            "evidencias": ["hash verificado"],
            "rodadas_usadas": 6,
            "ciclos_usados": 2,
            "estabilidade_exigida": 2,
            "estabilidade_atingida": True,
            "estado": "canonico_aprovado",
        }
        report = consensus.verdict_report(verdict, contract)
        self.assertFalse(report["valid"])
        self.assertTrue(any("duplicada" in item for item in report["errors"]))
        verdict["participantes"][1]["cadeira"] = "B"
        verdict["participantes"][1].pop("rota")
        report = consensus.verdict_report(verdict, contract)
        self.assertFalse(report["valid"])
        self.assertTrue(any("cadeira, rota" in item for item in report["errors"]))

    def test_consensus_rejects_boolean_counters_and_malformed_ledger_without_crash(self) -> None:
        contract = consensus.load_contract(ROOT / "assets/multiagent-manifest.json")
        config = consensus.config_report({
            "modo": "estrito",
            "politica_por_tentativa": "sempre",
            "rodadas": True,
            "ciclos_por_participante": False,
            "estabilidade": True,
        }, contract)
        self.assertFalse(config["valid"])
        verdict = {
            "schema": "veredito_consenso_v1",
            "modo": "estrito",
            "politica_por_tentativa": "sempre",
            "resultado": "consenso",
            "aprovacao": True,
            "simulacao": False,
            "artefato_sha256": "a" * 64,
            "run_id": "run-ledger-malformado",
            "tentativa": 1,
            "participantes": [],
            "bloqueadores": [],
            "dissensos": [],
            "evidencias": ["teste"],
            "rodadas_usadas": 2,
            "ciclos_usados": 0,
            "estabilidade_exigida": 2,
            "estabilidade_atingida": True,
            "ledger_deliberacao": "não é objeto",
        }
        report = consensus.verdict_report(verdict, contract)
        self.assertFalse(report["valid"])
        self.assertFalse(report["approval"])
        self.assertTrue(any("ledger_deliberacao" in item for item in report["errors"]))

    def test_custom_nonce_ledger_environment_requires_explicit_opt_in(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            verdict = root / "verdict.json"
            verdict.write_text("{}", encoding="utf-8")
            env = os.environ.copy()
            env["MULTIAGENT_NONCE_LEDGER"] = str(root / "alternate.json")
            env.pop("MULTIAGENT_ALLOW_CUSTOM_NONCE_LEDGER", None)
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/consensus_gate.py"),
                    "validate-verdict",
                    str(verdict),
                    "--check-only",
                ],
                text=True,
                capture_output=True,
                env=env,
                check=False,
            )
            self.assertEqual(completed.returncode, 2)
            self.assertIn("MULTIAGENT_ALLOW_CUSTOM_NONCE_LEDGER=1", completed.stdout)

    def test_strict_consensus_requires_real_hash_receipts_stability_and_no_replay(self) -> None:
        manifest, contract = consensus.load_manifest_and_contract(
            ROOT / "assets/multiagent-manifest.json"
        )
        secret = b"q" * 32
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            artifact = root / "artefato.md"
            artifact.write_text("conteúdo aprovado\n", encoding="utf-8")
            digest = provenance.hash_file(artifact)["sha256"]
            participants = [
                {
                    "cadeira": "codex", "rota": "codex",
                    "modelo": "gpt-5.6-sol", "provedor": "openai",
                },
                {
                    "cadeira": "grok", "rota": "cursor",
                    "modelo": "cursor-grok-4.6-high", "provedor": "xai",
                },
            ]
            receipts = []
            evaluations = []
            for round_number in (1, 2):
                nonces = []
                for seat_index, participant in enumerate(participants, start=1):
                    nonce = f"nonce-consenso-{round_number:02d}-{seat_index:02d}-0001"
                    nonces.append(nonce)
                    unsigned = {
                        "schema": "multiagent_provenance_v1",
                        "run_id": "run-consenso-forte",
                        "cadeira": participant["cadeira"],
                        "rota": participant["rota"],
                        "provedor": participant["provedor"],
                        "nonce": nonce,
                        "tentativa": 1,
                        "rodada": round_number,
                        "argv_sha256": "a" * 64,
                        "entrada_sha256": "b" * 64,
                        "saida_sha256": f"{round_number}{seat_index}".ljust(64, "c")[:64],
                        "artefato_sha256": digest,
                        "emitido_em": f"2026-08-14T12:0{round_number}:00Z",
                        "modelo_efetivo": participant["modelo"],
                        "modelo_confirmado": True,
                        "execucao_efetiva": True,
                        "execucao_id": f"execucao-{round_number}-{seat_index}-independente",
                        "isolamento_execucao_confirmado": True,
                        "sessao_id": None,
                        "sessao_confirmada": False,
                        "posicao": "aprovar",
                        "bloqueadores": [],
                        "dissensos": [],
                    }
                    receipts.append(provenance.sign_receipt(unsigned, secret))
                evaluations.append({
                    "numero": round_number,
                    "resultado": "consenso",
                    "artefato_sha256": digest,
                    "recibos_nonces": nonces,
                })
            verdict = {
                "schema": "veredito_consenso_v1",
                "run_id": "run-consenso-forte",
                "tentativa": 1,
                "modo": "estrito",
                "politica_por_tentativa": "sempre",
                "resultado": "consenso",
                "aprovacao": True,
                "simulacao": False,
                "artefato_sha256": digest,
                "artefato_caminho": str(artifact),
                "raiz_artefatos": str(root),
                "participantes": participants,
                "bloqueadores": [],
                "dissensos": [],
                "evidencias": ["artefato real e manifestações atestadas"],
                "rodadas_usadas": 2,
                "ciclos_usados": 0,
                "estabilidade_exigida": 2,
                "estabilidade_atingida": True,
                "estado": "canonico_aprovado",
                "quorum_declarado": 2,
                "quorum_minimo": 2,
                "ledger_deliberacao": {
                    "rodadas": [
                        {"numero": 1, "fase": "avaliacao", "artefato_sha256": digest},
                        {"numero": 2, "fase": "reavaliacao", "artefato_sha256": digest},
                    ],
                    "avaliacoes": evaluations,
                },
                "recibos_proveniencia": receipts,
            }
            nonce_ledger = root / "nonces.json"
            missing_evidence = copy.deepcopy(verdict)
            missing_evidence["evidencias"] = []
            premature_ledger = root / "premature-nonces.json"
            premature = consensus.verdict_report(
                missing_evidence,
                contract,
                manifest=manifest,
                secret=secret,
                nonce_ledger=premature_ledger,
                consume_nonce=True,
            )
            self.assertFalse(premature["valid"])
            self.assertFalse(premature["approval"])
            self.assertFalse(premature_ledger.exists())
            malformed_evidence = copy.deepcopy(verdict)
            malformed_evidence["evidencias"] = [None]
            malformed_ledger = root / "malformed-evidence-nonces.json"
            malformed_report = consensus.verdict_report(
                malformed_evidence,
                contract,
                manifest=manifest,
                secret=secret,
                nonce_ledger=malformed_ledger,
                consume_nonce=True,
            )
            self.assertFalse(malformed_report["valid"])
            self.assertFalse(malformed_report["approval"])
            self.assertFalse(malformed_report["transition_effective"])
            self.assertFalse(malformed_ledger.exists())
            weak_secret_ledger = root / "weak-consensus-secret-nonces.json"
            weak_secret_report = consensus.verdict_report(
                verdict,
                contract,
                manifest=manifest,
                secret=b"",
                nonce_ledger=weak_secret_ledger,
                consume_nonce=True,
            )
            self.assertFalse(weak_secret_report["valid"])
            self.assertFalse(weak_secret_report["approval"])
            self.assertFalse(weak_secret_report["transition_effective"])
            self.assertFalse(weak_secret_ledger.exists())
            self.assertTrue(any(
                "ao menos 32 bytes" in item for item in weak_secret_report["errors"]
            ))
            report = consensus.verdict_report(
                verdict,
                contract,
                manifest=manifest,
                secret=secret,
                nonce_ledger=nonce_ledger,
                consume_nonce=True,
            )
            self.assertTrue(report["valid"], report["errors"])
            self.assertTrue(report["approval"])
            self.assertTrue(report["transition_effective"])
            check_after_consumption = consensus.verdict_report(
                verdict,
                contract,
                manifest=manifest,
                secret=secret,
                nonce_ledger=nonce_ledger,
                consume_nonce=False,
            )
            self.assertFalse(check_after_consumption["valid"])
            self.assertFalse(check_after_consumption["approval"])
            replay = consensus.verdict_report(
                verdict,
                contract,
                manifest=manifest,
                secret=secret,
                nonce_ledger=nonce_ledger,
                consume_nonce=True,
            )
            self.assertFalse(replay["valid"])
            self.assertTrue(any("replay" in item for item in replay["errors"]))

            weak_stability = copy.deepcopy(verdict)
            weak_stability["estabilidade_exigida"] = 1
            weak_report = consensus.verdict_report(
                weak_stability,
                contract,
                manifest=manifest,
                secret=secret,
                nonce_ledger=root / "weak-nonces.json",
                consume_nonce=True,
            )
            self.assertFalse(weak_report["valid"])
            self.assertFalse(weak_report["approval"])

            wrong_round = copy.deepcopy(verdict)
            wrong_round_receipt = wrong_round["recibos_proveniencia"][-1]
            wrong_round_receipt["rodada"] = 1
            wrong_round["recibos_proveniencia"][-1] = provenance.sign_receipt(
                wrong_round_receipt, secret
            )
            wrong_round_report = consensus.verdict_report(
                wrong_round,
                contract,
                manifest=manifest,
                secret=secret,
                nonce_ledger=root / "wrong-round-nonces.json",
                consume_nonce=True,
            )
            self.assertFalse(wrong_round_report["valid"])
            self.assertTrue(any("não corresponde" in item for item in wrong_round_report["errors"]))

    def test_strict_collegiate_rule_cannot_bypass_consensus_gate(self) -> None:
        manifest, contract = collegiate.load_manifest_and_contract(
            ROOT / "assets/multiagent-manifest.json"
        )
        verdict = {
            "schema": "decisao_colegiada_v1",
            "modalidade": "seriatim",
            "regra_resultado": "consenso_estrito",
            "base_calculo": "votos_validos",
            "adesao_fundamentos": "proposicao",
            "quorum_declarado": 2,
            "ratio_exigida": False,
            "votos_dissidentes": "publicar",
            "votos_concorrentes": "publicar",
            "proclamacao_congela_votos": True,
            "artefato_sha256": "a" * 64,
            "votos": [
                {"cadeira": "codex", "tipo": "favoravel", "opcao_dispositivo": "A", "voto_sha256": "b" * 64, "adesoes": []},
                {"cadeira": "grok", "tipo": "favoravel", "opcao_dispositivo": "A", "voto_sha256": "c" * 64, "adesoes": []},
            ],
            "proposicoes": [],
            "opcao_vencedora": "A",
            "ratio_status": "nao_aplicavel",
            "votos_separados": [],
            "rotulo_deliberativo": "consenso",
            "proclamado": True,
            "gate_colegiado": True,
        }
        report = collegiate.verdict_report(verdict, contract, manifest=manifest)
        self.assertFalse(report["valid"])
        self.assertTrue(any("veredito_consenso" in item for item in report["errors"]))

    def test_majority_collegiate_gate_requires_attested_votes_and_real_artifact(self) -> None:
        manifest, contract = collegiate.load_manifest_and_contract(
            ROOT / "assets/multiagent-manifest.json"
        )
        secret = b"v" * 32
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            artifact = root / "decisao.md"
            artifact.write_text("decisão colegiada\n", encoding="utf-8")
            digest = provenance.hash_file(artifact)["sha256"]
            seats = [
                ("codex", "codex", "openai", "gpt-5.6-sol"),
                ("grok", "cursor", "xai", "cursor-grok-4.6-high"),
            ]
            votes = []
            receipts = []
            for index, (seat, route, provider, model) in enumerate(seats, start=1):
                vote_hash = (str(index) * 64)[:64]
                nonce = f"nonce-colegiado-{index:02d}-0001"
                votes.append({
                    "cadeira": seat,
                    "tipo": "favoravel",
                    "opcao_dispositivo": "A",
                    "voto_sha256": vote_hash,
                    "recibo_nonce": nonce,
                    "adesoes": [],
                })
                receipts.append(provenance.sign_receipt({
                    "schema": "multiagent_provenance_v1",
                    "run_id": "run-colegiado-atestado",
                    "cadeira": seat,
                    "rota": route,
                    "provedor": provider,
                    "nonce": nonce,
                    "tentativa": 1,
                    "rodada": 1,
                    "argv_sha256": "a" * 64,
                    "entrada_sha256": "b" * 64,
                    "saida_sha256": vote_hash,
                    "artefato_sha256": digest,
                    "emitido_em": "2026-08-15T12:00:00Z",
                    "modelo_efetivo": model,
                    "modelo_confirmado": True,
                    "execucao_efetiva": True,
                    "execucao_id": f"execucao-voto-{index}",
                    "isolamento_execucao_confirmado": True,
                    "sessao_id": None,
                    "sessao_confirmada": False,
                    "posicao_colegiada": "A",
                }, secret))
            verdict = {
                "schema": "decisao_colegiada_v1",
                "run_id": "run-colegiado-atestado",
                "tentativa": 1,
                "modalidade": "seriatim",
                "regra_resultado": "maioria_simples",
                "base_calculo": "votos_validos",
                "adesao_fundamentos": "proposicao",
                "quorum_declarado": 2,
                "ratio_exigida": False,
                "votos_dissidentes": "publicar",
                "votos_concorrentes": "publicar",
                "proclamacao_congela_votos": True,
                "artefato_sha256": digest,
                "artefato_caminho": str(artifact),
                "raiz_artefatos": str(root),
                "votos": votes,
                "recibos_proveniencia": receipts,
                "proposicoes": [],
                "opcao_vencedora": "A",
                "ratio_status": "nao_aplicavel",
                "votos_separados": [],
                "rotulo_deliberativo": "unanimidade_no_resultado",
                "proclamado": True,
                "gate_colegiado": True,
            }
            ledger = root / "nonces.json"
            report = collegiate.verdict_report(
                verdict,
                contract,
                manifest=manifest,
                secret=secret,
                nonce_ledger=ledger,
                consume_nonce=True,
            )
            self.assertTrue(report["valid"], report["errors"])
            self.assertTrue(report["gate_colegiado"])
            self.assertEqual(report["trust_level"], "attested_vote_formation")
            weak_secret_report = collegiate.verdict_report(
                verdict,
                contract,
                manifest=manifest,
                secret=b"",
                nonce_ledger=root / "weak-secret-nonces.json",
                consume_nonce=True,
            )
            self.assertFalse(weak_secret_report["valid"])
            self.assertFalse(weak_secret_report["gate_colegiado"])
            self.assertFalse(weak_secret_report["transition_effective"])
            self.assertTrue(any(
                "ao menos 32 bytes" in item for item in weak_secret_report["errors"]
            ))
            forged = copy.deepcopy(verdict)
            forged["recibos_proveniencia"] = []
            forged_report = collegiate.verdict_report(
                forged,
                contract,
                manifest=manifest,
                secret=secret,
                nonce_ledger=root / "forged-nonces.json",
                consume_nonce=True,
            )
            self.assertFalse(forged_report["valid"])
            self.assertFalse(forged_report["gate_colegiado"])

    def test_non_consensus_verdict_still_requires_provenance(self) -> None:
        manifest, contract = consensus.load_manifest_and_contract(
            ROOT / "assets/multiagent-manifest.json"
        )
        verdict = {
            "schema": "veredito_consenso_v1",
            "run_id": "run-sem-consenso",
            "tentativa": 1,
            "modo": "estrito",
            "politica_por_tentativa": "sempre",
            "resultado": "sem_consenso",
            "aprovacao": False,
            "simulacao": False,
            "artefato_sha256": "a" * 64,
            "participantes": [
                {"cadeira": "codex", "rota": "codex", "modelo": "gpt-5.6-sol", "provedor": "openai"},
                {"cadeira": "grok", "rota": "cursor", "modelo": "cursor-grok-4.6-high", "provedor": "xai"},
            ],
            "bloqueadores": ["divergência material"],
            "dissensos": ["tese A versus B"],
            "evidencias": [],
            "rodadas_usadas": 1,
            "ciclos_usados": 0,
            "estabilidade_exigida": 1,
            "estabilidade_atingida": False,
            "estado": "provisional_single_round",
            "ledger_deliberacao": {
                "rodadas": [{"numero": 1, "fase": "avaliacao", "artefato_sha256": "a" * 64}],
                "avaliacoes": [],
            },
        }
        report = consensus.verdict_report(verdict, contract, manifest=manifest)
        self.assertFalse(report["valid"])
        self.assertTrue(any("recibos_proveniencia" in item for item in report["errors"]))

    def test_delphi_runtime_reports_stable_convergence_without_approval(self) -> None:
        result = workflow_engine.delphi({
            "estabilidade_exigida": 2,
            "limiar_mediana": 8.5,
            "limiar_iqr": 1.0,
            "rodadas": [
                {"numero": 1, "respostas": [
                    {"cadeira": "claude", "nota": 8.6, "confianca": 0.8},
                    {"cadeira": "codex", "nota": 8.8, "confianca": 0.9},
                ]},
                {"numero": 2, "respostas": [
                    {"cadeira": "claude", "nota": 8.7, "confianca": 0.9},
                    {"cadeira": "codex", "nota": 8.9, "confianca": 0.9},
                ]},
            ],
        })
        self.assertTrue(result["convergencia_estavel"])
        self.assertFalse(result["aprovacao"])
        alias = workflow_engine.delphi({
            "estabilidade": 2,
            "rodadas": [
                {"numero": 1, "respostas": [
                    {"cadeira": "a", "nota": 9, "confianca": 0.9},
                    {"cadeira": "b", "nota": 9, "confianca": 0.9},
                ]},
                {"numero": 2, "respostas": [
                    {"cadeira": "a", "nota": 9, "confianca": 0.9},
                    {"cadeira": "b", "nota": 9, "confianca": 0.9},
                ]},
            ],
        })
        self.assertTrue(alias["convergencia_estavel"])
        with self.assertRaises(ValueError):
            workflow_engine.delphi({"estabilidade_exigida": 1, "rodadas": [{}]})
        with self.assertRaises(ValueError):
            workflow_engine.delphi({
                "estabilidade_exigida": 2,
                "limiar_mediana": float("nan"),
                "rodadas": [{"numero": 1, "respostas": []}],
            })

    def test_adaptive_routing_rejects_boolean_nan_and_non_normalized_weights(self) -> None:
        base = {
            "perfil": "workflow_agents_v1",
            "protocolo": "roteamento_adaptativo_v1",
            "objetivo": "rotear",
            "participantes": [],
            "estrutura": {
                "pool": [{"id": "a", "metricas": {}}],
                "pesos": {
                    "qualidade": 0.4,
                    "custo": 0.2,
                    "latencia": 0.1,
                    "falha": 0.1,
                    "diversidade": 0.2,
                },
                "exploracao": 0.1,
            },
            "limites": {"max_paralelo": 1, "max_segundos": 60},
        }
        self.assertTrue(workflow_engine.validate_config(base)["valid"])
        boolean_weight = copy.deepcopy(base)
        boolean_weight["estrutura"]["pesos"]["qualidade"] = True
        self.assertFalse(workflow_engine.validate_config(boolean_weight)["valid"])
        nan_weight = copy.deepcopy(base)
        nan_weight["estrutura"]["pesos"]["qualidade"] = float("nan")
        self.assertFalse(workflow_engine.validate_config(nan_weight)["valid"])
        wrong_sum = copy.deepcopy(base)
        wrong_sum["estrutura"]["pesos"]["qualidade"] = 0.3
        self.assertFalse(workflow_engine.validate_config(wrong_sum)["valid"])
        bad_metric = copy.deepcopy(base)
        bad_metric["estrutura"]["pool"][0]["metricas"]["qualidade"] = float("inf")
        with self.assertRaises(ValueError):
            workflow_engine.routing_plan(bad_metric["estrutura"])

        metrics_list = copy.deepcopy(base)
        metrics_list["estrutura"]["pool"][0]["metricas"] = []
        self.assertFalse(workflow_engine.validate_config(metrics_list)["valid"])
        with self.assertRaises(ValueError):
            workflow_engine.make_plan(metrics_list)
        unknown_metric = copy.deepcopy(base)
        unknown_metric["estrutura"]["pool"][0]["metricas"] = {
            "qualidde": 0.9,
        }
        self.assertFalse(workflow_engine.validate_config(unknown_metric)["valid"])
        weights_list = copy.deepcopy(base)
        weights_list["estrutura"]["pesos"] = [
            "qualidade", "custo", "latencia", "falha", "diversidade"
        ]
        self.assertFalse(workflow_engine.validate_config(weights_list)["valid"])
        with self.assertRaises(ValueError):
            workflow_engine.make_plan(weights_list)

    def test_tournament_rejects_non_string_candidates_and_invalid_seed(self) -> None:
        base = {
            "perfil": "workflow_agents_v1",
            "protocolo": "torneio_eliminatorio_v1",
            "objetivo": "selecionar",
            "participantes": [],
            "estrutura": {
                "candidatos": ["a", "b"],
                "juizes_por_confronto": 1,
                "seed": 7,
            },
            "limites": {"max_paralelo": 1, "max_segundos": 60},
        }
        self.assertTrue(workflow_engine.validate_config(base)["valid"])
        self.assertEqual(workflow_engine.make_plan(base)["seed"], 7)
        for candidates in ([True, False], [float("nan"), float("inf")], ["a", ""]):
            invalid = copy.deepcopy(base)
            invalid["estrutura"]["candidatos"] = candidates
            self.assertFalse(workflow_engine.validate_config(invalid)["valid"])
            with self.assertRaises(ValueError):
                workflow_engine.make_plan(invalid)
        for seed in (True, float("nan"), float("inf"), "7"):
            invalid = copy.deepcopy(base)
            invalid["estrutura"]["seed"] = seed
            self.assertFalse(workflow_engine.validate_config(invalid)["valid"])
            with self.assertRaises(ValueError):
                workflow_engine.make_plan(invalid)

    def test_preexisting_lock_permissions_are_restricted(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            checkpoint = root / "checkpoint.json"
            checkpoint_lock = root / "checkpoint.json.lock"
            checkpoint_lock.touch(mode=0o644)
            checkpoint_lock.chmod(0o644)
            with durable_run._checkpoint_lock(checkpoint):
                self.assertEqual(stat.S_IMODE(checkpoint_lock.stat().st_mode), 0o600)

            publication_lock = root / "publication.lock"
            publication_lock.touch(mode=0o644)
            publication_lock.chmod(0o644)
            with publication_policy._exclusive_lock(publication_lock):
                self.assertEqual(stat.S_IMODE(publication_lock.stat().st_mode), 0o600)

            nonce_ledger = root / "nonces.json"
            nonce_lock = root / ".nonces.json.lock"
            nonce_lock.touch(mode=0o644)
            nonce_lock.chmod(0o644)
            provenance.consume_nonces(nonce_ledger, [])
            self.assertEqual(stat.S_IMODE(nonce_lock.stat().st_mode), 0o600)

            victim = root / "victim.txt"
            victim.write_text("não alterar", encoding="utf-8")
            nonce_lock.unlink()
            nonce_lock.symlink_to(victim)
            with self.assertRaises(OSError):
                provenance.consume_nonces(nonce_ledger, [])
            self.assertEqual(victim.read_text(encoding="utf-8"), "não alterar")

    def test_packager_blocks_sensitive_files_and_is_reproducible(self) -> None:
        sensitive = ROOT / "scripts" / ".env.test-only"
        sensitive.write_text("SECRET=never-package", encoding="utf-8")
        try:
            with self.assertRaisesRegex(RuntimeError, "sensível"):
                packager.included(sensitive)
        finally:
            sensitive.unlink(missing_ok=True)
        bridge_secret = ROOT / "scripts" / "cowork-bridge-config.json"
        bridge_secret.write_text("{}", encoding="utf-8")
        try:
            with self.assertRaisesRegex(RuntimeError, "sensível"):
                packager.included(bridge_secret)
        finally:
            bridge_secret.unlink(missing_ok=True)
        with tempfile.TemporaryDirectory() as raw:
            first = Path(raw) / "one.plugin"
            second = Path(raw) / "two.plugin"
            subprocess.run([sys.executable, str(ROOT / "scripts/package_plugin.py"), "--output", str(first)], check=True)
            subprocess.run([sys.executable, str(ROOT / "scripts/package_plugin.py"), "--output", str(second)], check=True)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                names = archive.namelist()
                package_manifest = json.loads(
                    archive.read("PACKAGE-MANIFEST.json").decode("utf-8")
                )
            self.assertFalse(any(name == "bin" or name.startswith("bin/") for name in names))
            self.assertNotIn(".claude-plugin/marketplace.json", names)
            self.assertIn(".claude-plugin/plugin.json", names)
            self.assertIn("commands/multiagente.md", names)
            self.assertIn("scripts/cowork_bridge.py", names)
            self.assertIn("scripts/consensus_gate.py", names)
            self.assertIn("scripts/collegiate_gate.py", names)
            self.assertIn("scripts/publication_policy.py", names)
            self.assertIn("skills/bridge-agentes/SKILL.md", names)
            expected_version = json.loads(
                (ROOT / "assets/multiagent-manifest.json").read_text(encoding="utf-8")
            )["plugin_version"]
            self.assertEqual(package_manifest["plugin_version"], expected_version)
            self.assertTrue(package_manifest["files"])
            self.assertFalse(any("__pycache__" in name for name in names))
        self.assertTrue((ROOT / "bin/multiagent-bridge").is_file())


if __name__ == "__main__":
    unittest.main()
