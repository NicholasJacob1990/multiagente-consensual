#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "cowork_bridge.py"
SPEC = importlib.util.spec_from_file_location("cowork_bridge", SCRIPT)
assert SPEC and SPEC.loader
bridge = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bridge)


class CoworkBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = bridge.load_manifest(bridge.DEFAULT_MANIFEST)

    def test_grok_route_is_fixed(self) -> None:
        resolved = bridge.resolve_seat(self.manifest, "grok", "grok-4.6-high")
        self.assertEqual(resolved["route"], "cursor")
        self.assertEqual(resolved["model"], "cursor-grok-4.6-high")
        with self.assertRaisesRegex(ValueError, "modelo incompatível"):
            bridge.resolve_seat(self.manifest, "grok", "grok-4")

    def test_rejects_home_as_root(self) -> None:
        with self.assertRaisesRegex(ValueError, "pasta pessoal"):
            bridge.specific_root(str(Path.home()))

    def test_validate_request_and_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            prompt = root / "prompt.md"
            prompt.write_text("Revise o arquivo sem alterá-lo.", encoding="utf-8")
            payload = {
                "bridge_version": 1,
                "request_id": str(uuid.uuid4()),
                "participant": "grok",
                "model": "grok-4.6-high",
                "root": str(root),
                "prompt_file": str(prompt),
                "output_policy": "adaptive_up_to_native_max",
                "timeout": 60,
                "dry_run": True,
            }
            resolved = bridge.validate_request(payload, self.manifest, [root])
            command = bridge.adapter_command(resolved, bridge.DEFAULT_MANIFEST)
            self.assertIn("--dry-run", command)
            self.assertEqual(resolved["model"], "cursor-grok-4.6-high")
            self.assertFalse(resolved["persist_native_session"])

    def test_native_session_alias_and_adapter_flags(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            prompt = root / "prompt.md"
            prompt.write_text("Revise.", encoding="utf-8")
            rid = str(uuid.uuid4())
            payload = {
                "bridge_version": 1,
                "request_id": rid,
                "participant": "claude",
                "root": str(root),
                "prompt_file": str(prompt),
                "persistir_sessoes_nativas": True,
                "dry_run": True,
            }
            resolved = bridge.validate_request(payload, self.manifest, [root])
            command = bridge.adapter_command(resolved, bridge.DEFAULT_MANIFEST)
            self.assertTrue(resolved["persist_native_session"])
            self.assertIn("--persist-native-session", command)
            self.assertEqual(
                command[command.index("--native-session-correlation-id") + 1], rid
            )

            payload["persist_native_session"] = False
            with self.assertRaisesRegex(ValueError, "não podem divergir"):
                bridge.validate_request(payload, self.manifest, [root])

    def test_validate_request_by_registered_root_id(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            prompts = root / ".multiagent" / "prompts"
            prompts.mkdir(parents=True)
            prompt = prompts / "critica.md"
            prompt.write_text("Critique.", encoding="utf-8")
            payload = {
                "bridge_version": 1,
                "request_id": str(uuid.uuid4()),
                "participant": "codex",
                "root_id": "caso-1",
                "prompt_rel": ".multiagent/prompts/critica.md",
                "timeout": 60,
            }
            resolved = bridge.validate_request(payload, self.manifest, [], {"caso-1": str(root)})
            self.assertEqual(resolved["root"], root)
            self.assertEqual(resolved["prompt"], prompt)

    def test_registered_root_rejects_parent_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            payload = {
                "bridge_version": 1,
                "request_id": str(uuid.uuid4()),
                "participant": "codex",
                "root_id": "caso-1",
                "prompt_rel": "../segredo.txt",
                "timeout": 60,
            }
            with self.assertRaisesRegex(ValueError, "sem '..'"):
                bridge.validate_request(payload, self.manifest, [], {"caso-1": str(root)})

    def test_failure_is_visible_in_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            dirs = bridge.bridge_dirs(Path(raw))
            request = dirs["processing"] / f"{uuid.uuid4()}.request.json"
            request.write_text("{}", encoding="utf-8")
            bridge.failure_record(request, dirs, ValueError("inválido"))
            responses = list(dirs["outbox"].glob("*.response.json"))
            self.assertEqual(len(responses), 1)
            payload = json.loads(responses[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")
            self.assertIsNone(payload["verdict"])

    def test_failure_does_not_overwrite_existing_response(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            dirs = bridge.bridge_dirs(Path(raw))
            rid = str(uuid.uuid4())
            response = dirs["outbox"] / f"{rid}.response.json"
            response.write_text('{"status":"completed"}\n', encoding="utf-8")
            request = dirs["processing"] / f"{rid}.request.json"
            request.write_text("{}", encoding="utf-8")
            bridge.failure_record(request, dirs, ValueError("duplicado"))
            payload = json.loads(response.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "completed")

    def test_signature_round_trip_and_tamper_rejection(self) -> None:
        secret = "a" * 64
        payload = {
            "bridge_version": 1,
            "request_id": str(uuid.uuid4()),
            "participant": "codex",
            "root_id": "caso-1",
            "prompt_rel": "prompt.md",
        }
        signed = bridge.sign_payload(payload, secret)
        bridge.verify_signature(signed, secret)
        signed["participant"] = "claude"
        with self.assertRaisesRegex(ValueError, "HMAC inválida"):
            bridge.verify_signature(signed, secret)

    def test_request_filename_must_match_payload_id(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            queue = base / "queue"
            private = base / "private"
            project = base / "project"
            project.mkdir()
            prompt = project / "prompt.md"
            prompt.write_text("Revise.", encoding="utf-8")
            dirs = bridge.bridge_dirs(queue)
            payload_id = str(uuid.uuid4())
            filename_id = str(uuid.uuid4())
            secret = "b" * 64
            payload = bridge.sign_payload(
                {
                    "bridge_version": 1,
                    "request_id": payload_id,
                    "participant": "codex",
                    "root": str(project),
                    "prompt_file": str(prompt),
                    "dry_run": True,
                },
                secret,
            )
            request = dirs["processing"] / f"{filename_id}.request.json"
            bridge.atomic_json(request, payload)
            with self.assertRaisesRegex(ValueError, "nome do arquivo"):
                bridge.process_request(
                    request, dirs, self.manifest, bridge.DEFAULT_MANIFEST, [], {}, secret, private
                )

    def test_orphan_generates_interrupted_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            dirs = bridge.bridge_dirs(Path(raw))
            rid = str(uuid.uuid4())
            request = dirs["processing"] / f"{rid}.request.json"
            request.write_text("{}", encoding="utf-8")
            self.assertEqual(bridge.recover_orphans(dirs), 1)
            response = json.loads(
                (dirs["outbox"] / f"{rid}.response.json").read_text(encoding="utf-8")
            )
            self.assertIn("interrupted", response["error"])

    def test_partial_or_recent_request_is_not_consumed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / f"{uuid.uuid4()}.request.json"
            path.write_text('{"incompleto":', encoding="utf-8")
            self.assertFalse(bridge.request_is_stable(path))

    def test_config_requires_private_mode(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            config = Path(raw) / "config.json"
            config.write_text(
                json.dumps({"config_version": 2, "bridge_secret": "d" * 64, "roots": {}}),
                encoding="utf-8",
            )
            config.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "permissão 0600"):
                bridge.load_config(config)

    def test_atomic_json_new_never_overwrites(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            target = Path(raw) / "pedido.json"
            bridge.atomic_json_new(target, {"versao": 1})
            with self.assertRaisesRegex(ValueError, "não será sobrescrito"):
                bridge.atomic_json_new(target, {"versao": 2})
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["versao"], 1)

    def test_case_inventory_is_deterministic_and_excludes_sensitive_files(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            (root / "autos").mkdir()
            (root / "autos" / "peticao.md").write_text("conteúdo jurídico", encoding="utf-8")
            (root / "notas.txt").write_text("nota", encoding="utf-8")
            (root / ".env").write_text("TOKEN=segredo", encoding="utf-8")
            (root / "credentials.json").write_text('{"secret":"x"}', encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "pacote.js").write_text("ignorar", encoding="utf-8")
            (root / "atalho.txt").symlink_to(root / "notas.txt")

            first = bridge.build_case_inventory(root)
            second = bridge.build_case_inventory(root)

            self.assertEqual(first["snapshot_sha256"], second["snapshot_sha256"])
            self.assertEqual(
                [entry["path"] for entry in first["files"]],
                ["autos/peticao.md", "notas.txt"],
            )
            excluded = {entry["path"]: entry["reason"] for entry in first["excluded"]}
            self.assertEqual(excluded[".env"], "sensitive")
            self.assertEqual(excluded["credentials.json"], "sensitive")
            self.assertEqual(excluded["node_modules"], "excluded_directory")
            self.assertEqual(excluded["atalho.txt"], "symlink")

    def test_prepare_case_registers_root_and_creates_auditable_bundle_without_model_calls(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw).resolve()
            root = base / "caso"
            root.mkdir()
            (root / "documento.md").write_text("fatos do caso", encoding="utf-8")
            queue = base / "queue"
            private = base / "private"
            config = base / "config.json"
            bridge.atomic_json(
                config,
                {"config_version": 2, "bridge_secret": "f" * 64, "roots": {}},
            )
            args = type(
                "Args",
                (),
                {
                    "id": "caso-teste",
                    "path": str(root),
                    "participant": ["claude", "codex"],
                    "replace": False,
                    "start": False,
                    "bridge_dir": str(queue),
                    "private_state": str(private),
                    "config": str(config),
                    "manifest": str(bridge.DEFAULT_MANIFEST),
                },
            )()

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                self.assertEqual(bridge.run_prepare_case(args), 0)

            receipt = json.loads(stdout.getvalue())
            saved_config = bridge.load_config(config)
            case_manifest = json.loads(
                (root / ".multiagent" / "case-manifest.json").read_text(encoding="utf-8")
            )
            stored_receipt = json.loads(
                (root / ".multiagent" / "prepare-case-receipt.json").read_text(encoding="utf-8")
            )
            prompt = root / ".multiagent" / "prompts" / "shared-case.md"

            self.assertEqual(saved_config["roots"]["caso-teste"], str(root))
            self.assertEqual(case_manifest["contract"], "multiagent_case_v1")
            self.assertEqual(case_manifest["files"][0]["path"], "documento.md")
            self.assertEqual(receipt["snapshot_sha256"], case_manifest["snapshot_sha256"])
            self.assertEqual(stored_receipt["model_calls_executed"], False)
            self.assertEqual(stored_receipt["file_read_by_models_confirmed"], False)
            self.assertEqual([item["seat"] for item in receipt["participants"]], ["claude", "codex"])
            self.assertTrue(prompt.is_file())
            self.assertIn(case_manifest["snapshot_sha256"], prompt.read_text(encoding="utf-8"))
            self.assertTrue(queue.joinpath("inbox").is_dir())

    def test_prepare_case_refuses_to_remap_existing_root_without_replace(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw).resolve()
            first = base / "primeiro"
            second = base / "segundo"
            first.mkdir()
            second.mkdir()
            (second / "doc.txt").write_text("x", encoding="utf-8")
            config = base / "config.json"
            bridge.atomic_json(
                config,
                {
                    "config_version": 2,
                    "bridge_secret": "g" * 64,
                    "roots": {"caso": str(first)},
                },
            )
            args = type(
                "Args",
                (),
                {
                    "id": "caso",
                    "path": str(second),
                    "participant": ["codex"],
                    "replace": False,
                    "start": False,
                    "bridge_dir": str(base / "queue"),
                    "private_state": str(base / "private"),
                    "config": str(config),
                    "manifest": str(bridge.DEFAULT_MANIFEST),
                },
            )()
            with self.assertRaisesRegex(ValueError, "já aponta para outra pasta"):
                bridge.run_prepare_case(args)

    def test_prepare_case_does_not_register_empty_corpus(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw).resolve()
            root = base / "vazio"
            root.mkdir()
            (root / ".env").write_text("TOKEN=x", encoding="utf-8")
            config = base / "config.json"
            bridge.atomic_json(
                config,
                {"config_version": 2, "bridge_secret": "j" * 64, "roots": {}},
            )
            args = type(
                "Args",
                (),
                {
                    "id": "caso-vazio",
                    "path": str(root),
                    "participant": ["codex"],
                    "replace": False,
                    "start": False,
                    "bridge_dir": str(base / "queue"),
                    "private_state": str(base / "private"),
                    "config": str(config),
                    "manifest": str(bridge.DEFAULT_MANIFEST),
                },
            )()
            with self.assertRaisesRegex(ValueError, "nenhum arquivo elegível"):
                bridge.run_prepare_case(args)
            self.assertEqual(bridge.load_config(config)["roots"], {})

    def test_prepare_case_creates_private_config_on_first_use(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw).resolve()
            root = base / "caso"
            root.mkdir()
            (root / "documento.txt").write_text("conteúdo", encoding="utf-8")
            config = base / "config.json"
            args = type(
                "Args",
                (),
                {
                    "id": "primeiro-caso",
                    "path": str(root),
                    "participant": ["codex"],
                    "replace": False,
                    "start": False,
                    "bridge_dir": str(base / "queue"),
                    "private_state": str(base / "private"),
                    "config": str(config),
                    "manifest": str(bridge.DEFAULT_MANIFEST),
                },
            )()
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(bridge.run_prepare_case(args), 0)
            saved = bridge.load_config(config)
            self.assertEqual(saved["roots"]["primeiro-caso"], str(root))
            self.assertGreaterEqual(len(saved["bridge_secret"]), 64)
            self.assertEqual(config.stat().st_mode & 0o777, 0o600)

    def test_prepare_case_start_reuses_existing_daemon(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw).resolve()
            root = base / "caso"
            root.mkdir()
            (root / "documento.txt").write_text("conteúdo", encoding="utf-8")
            queue = base / "queue"
            private = base / "private"
            config = base / "config.json"
            bridge.atomic_json(
                config,
                {"config_version": 2, "bridge_secret": "h" * 64, "roots": {}},
            )
            args = type(
                "Args",
                (),
                {
                    "id": "caso",
                    "path": str(root),
                    "participant": ["codex"],
                    "replace": False,
                    "start": True,
                    "bridge_dir": str(queue),
                    "private_state": str(private),
                    "config": str(config),
                    "manifest": str(bridge.DEFAULT_MANIFEST),
                },
            )()
            stdout = io.StringIO()
            with bridge.exclusive_daemon(private):
                with contextlib.redirect_stdout(stdout):
                    self.assertEqual(bridge.run_prepare_case(args), 0)
            receipt = json.loads(stdout.getvalue())
            self.assertEqual(receipt["bridge_service"]["status"], "already_running")
            self.assertIsNone(receipt["bridge_service"]["pid"])

    def test_start_bridge_service_launches_and_records_background_worker(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw).resolve()
            root = base / "caso"
            root.mkdir()
            queue = base / "queue"
            private = base / "private"
            config = base / "config.json"
            bridge.atomic_json(
                config,
                {"config_version": 2, "bridge_secret": "i" * 64, "roots": {"caso": str(root)}},
            )
            args = type(
                "Args",
                (),
                {
                    "bridge_dir": str(queue),
                    "private_state": str(private),
                    "config": str(config),
                    "manifest": str(bridge.DEFAULT_MANIFEST),
                },
            )()
            state = None
            try:
                state = bridge.start_bridge_service(args, root)
                self.assertEqual(state["status"], "started")
                self.assertGreater(state["pid"], 0)
                self.assertTrue((private / "bridge-daemon.json").is_file())
                self.assertTrue(bridge.bridge_daemon_running(private))
                self.assertNotIn("--allow-root", state["command"])
                self.assertEqual(state["root_policy"], "registered_roots")
            finally:
                if state and state.get("pid"):
                    with contextlib.suppress(ProcessLookupError):
                        os.killpg(state["pid"], bridge.signal.SIGTERM)
                    for _ in range(30):
                        if not bridge.bridge_daemon_running(private):
                            break
                        time.sleep(0.05)

    def test_run_once_signed_dry_run_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            queue = base / "queue"
            private = base / "private"
            project = base / "project"
            project.mkdir()
            prompt = project / "prompt.md"
            prompt.write_text("Apenas simule.", encoding="utf-8")
            secret = "c" * 64
            config = base / "config.json"
            bridge.atomic_json(
                config,
                {"config_version": 2, "bridge_secret": secret, "roots": {"caso": str(project)}},
            )
            rid = str(uuid.uuid4())
            payload = bridge.sign_payload(
                {
                    "bridge_version": 1,
                    "request_id": rid,
                    "participant": "codex",
                    "root_id": "caso",
                    "prompt_rel": "prompt.md",
                    "timeout": 60,
                    "dry_run": True,
                },
                secret,
            )
            dirs = bridge.bridge_dirs(queue)
            request = dirs["inbox"] / f"{rid}.request.json"
            bridge.atomic_json(request, payload)
            old = request.stat().st_mtime - 5
            os.utime(request, (old, old))
            args = type(
                "Args",
                (),
                {
                    "bridge_dir": str(queue),
                    "manifest": str(bridge.DEFAULT_MANIFEST),
                    "config": str(config),
                    "private_state": str(private),
                    "allow_root": [],
                    "report_empty": False,
                },
            )()
            self.assertEqual(bridge.run_once(args), 0)
            response = json.loads(
                (dirs["outbox"] / f"{rid}.response.json").read_text(encoding="utf-8")
            )
            self.assertEqual(response["status"], "completed")
            self.assertTrue(response["simulation"])
            self.assertIsNone(response["verdict"])
            self.assertTrue(response["prompt_stable"])
            self.assertFalse(response["model_confirmed"])
            self.assertFalse(response["native_session_persistence_requested"])
            self.assertFalse(response["native_session_is_canonical"])
            self.assertTrue((private / "consumed" / f"{rid}.json").is_file())

    def test_run_once_native_session_dry_run_has_nonprobative_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            queue = base / "queue"
            private = base / "private"
            project = base / "project"
            project.mkdir()
            prompt = project / "prompt.md"
            prompt.write_text("Apenas simule.", encoding="utf-8")
            secret = "e" * 64
            config = base / "config.json"
            bridge.atomic_json(
                config,
                {"config_version": 2, "bridge_secret": secret, "roots": {"caso": str(project)}},
            )
            rid = str(uuid.uuid4())
            payload = bridge.sign_payload(
                {
                    "bridge_version": 1,
                    "request_id": rid,
                    "participant": "claude",
                    "root_id": "caso",
                    "prompt_rel": "prompt.md",
                    "persistir_sessoes_nativas": True,
                    "timeout": 60,
                    "dry_run": True,
                },
                secret,
            )
            dirs = bridge.bridge_dirs(queue)
            request = dirs["inbox"] / f"{rid}.request.json"
            bridge.atomic_json(request, payload)
            old = request.stat().st_mtime - 5
            os.utime(request, (old, old))
            args = type(
                "Args",
                (),
                {
                    "bridge_dir": str(queue),
                    "manifest": str(bridge.DEFAULT_MANIFEST),
                    "config": str(config),
                    "private_state": str(private),
                    "allow_root": [],
                    "report_empty": False,
                },
            )()
            self.assertEqual(bridge.run_once(args), 0)
            response = json.loads(
                (dirs["outbox"] / f"{rid}.response.json").read_text(encoding="utf-8")
            )
            self.assertTrue(response["native_session_persistence_requested"])
            self.assertFalse(response["native_session_persistence_effective"])
            self.assertFalse(response["native_session_persistence_confirmed"])
            self.assertEqual(response["native_session_persistence_status"], "simulated")
            self.assertTrue((private / "native-sessions" / f"{rid}.json").is_file())

    def test_timeout_kills_process_group(self) -> None:
        command = [
            bridge.sys.executable,
            "-c",
            "import time; time.sleep(60)",
        ]
        returncode, _stdout, stderr, killed = bridge.run_adapter(command, Path.cwd(), -29)
        self.assertEqual(returncode, 124)
        self.assertTrue(killed)
        self.assertIn("grupo de processos", stderr)

    def test_timeout_kills_real_descendant(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            marker = Path(raw) / "child.txt"
            command = [
                sys.executable,
                "-c",
                (
                    "import subprocess,sys,time; "
                    f"subprocess.Popen([sys.executable,'-c',\"import time; time.sleep(2); open({str(marker)!r},'w').write('alive')\"]); "
                    "time.sleep(60)"
                ),
            ]
            returncode, _stdout, _stderr, killed = bridge.run_adapter(command, Path.cwd(), -29)
            self.assertEqual(returncode, 124)
            self.assertTrue(killed)
            time.sleep(2.3)
            self.assertFalse(marker.exists())

    def test_exclusive_daemon_lock(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            private = Path(raw) / "private"
            with bridge.exclusive_daemon(private):
                with self.assertRaisesRegex(RuntimeError, "já existe"):
                    with bridge.exclusive_daemon(private):
                        pass

    def test_prompt_change_during_call_fails_but_snapshot_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            project = base / "project"
            private = base / "private"
            project.mkdir()
            prompt = project / "prompt.md"
            prompt.write_text("original", encoding="utf-8")
            rid = str(uuid.uuid4())
            request = {
                "request_id": rid,
                "prompt": prompt,
                "root": project,
                "timeout": 60,
            }
            snapshot, pre, snapshot_pre = bridge.snapshot_prompt(request, private)
            prompt.write_text("alterado", encoding="utf-8")
            self.assertEqual(pre, snapshot_pre)
            self.assertEqual(snapshot.read_text(encoding="utf-8"), "original")
            self.assertNotEqual(pre, bridge.sha256(prompt))

    def test_replay_ledger_refuses_second_claim(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            ledger = Path(raw) / "consumed" / f"{uuid.uuid4()}.json"
            bridge.atomic_json_new(ledger, {"claimed": 1})
            with self.assertRaisesRegex(ValueError, "não será sobrescrito"):
                bridge.atomic_json_new(ledger, {"claimed": 2})


if __name__ == "__main__":
    unittest.main()
