#!/usr/bin/env python3
"""Bridge auditável entre uma pasta Cowork compartilhada e CLIs locais."""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(os.environ.get("MULTIAGENT_PLUGIN_ROOT", Path(__file__).resolve().parents[1])).resolve()
DEFAULT_MANIFEST = PLUGIN_ROOT / "assets" / "multiagent-manifest.json"
DEFAULT_BRIDGE_DIR = Path("~/.agents/cowork-bridge").expanduser()
DEFAULT_CONFIG = Path("~/.agents/cowork-bridge-config.json").expanduser()
DEFAULT_PRIVATE_STATE = Path("~/.agents/cowork-bridge-state").expanduser()
ADAPTER = PLUGIN_ROOT / "skills" / "consenso" / "scripts" / "cli_adapter.py"
REQUEST_SUFFIX = ".request.json"
BRIDGE_VERSION = 1
MAX_REQUEST_BYTES = 128 * 1024
MAX_PROMPT_BYTES = 512 * 1024
MIN_REQUEST_AGE_SECONDS = 2.0


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as target:
            json.dump(payload, target, ensure_ascii=False, indent=2, sort_keys=True)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp, path)
        path.chmod(0o600)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(handle, "wb") as target:
            target.write(payload)
            target.flush()
            os.fsync(target.fileno())
        os.replace(tmp, path)
        path.chmod(0o600)
    finally:
        tmp.unlink(missing_ok=True)


def atomic_text(path: Path, payload: str) -> None:
    atomic_bytes(path, payload.encode("utf-8"))


def atomic_json_new(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as target:
            json.dump(payload, target, ensure_ascii=False, indent=2, sort_keys=True)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
        try:
            os.link(tmp, path)
        except FileExistsError as exc:
            raise ValueError(f"o arquivo já existe e não será sobrescrito: {path}") from exc
        path.chmod(0o600)
    finally:
        tmp.unlink(missing_ok=True)


def ensure_private_dir(path: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"diretório privado não pode ser symlink: {path}")
    created = not path.exists()
    path.mkdir(parents=True, exist_ok=True)
    mode = path.lstat().st_mode
    if not stat.S_ISDIR(mode):
        raise ValueError(f"esperado diretório: {path}")
    if path.stat().st_uid != os.getuid():
        raise ValueError(f"diretório não pertence ao usuário atual: {path}")
    if created:
        path.chmod(0o700)


def bridge_dirs(root: Path, enforce_permissions: bool = False) -> dict[str, Path]:
    result = {name: root / name for name in ("inbox", "processing", "outbox", "failed", "state")}
    ensure_private_dir(root)
    for path in result.values():
        ensure_private_dir(path)
        if enforce_permissions:
            path.chmod(0o700)
    if enforce_permissions:
        root.chmod(0o700)
    return result


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValueError(f"configuração privada ausente: {path}; execute install_host.py")
    mode = path.lstat().st_mode
    if path.is_symlink() or not stat.S_ISREG(mode):
        raise ValueError(f"configuração privada precisa ser arquivo regular, não symlink: {path}")
    if path.stat().st_uid != os.getuid() or mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ValueError("configuração privada deve pertencer ao usuário e ter permissão 0600")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("config_version") != 2 or not isinstance(data.get("roots"), dict):
        raise ValueError("configuração do bridge inválida")
    secret = data.get("bridge_secret")
    if not isinstance(secret, str) or len(secret) < 64:
        raise ValueError("bridge_secret ausente ou fraco; reinstale/atualize o bridge")
    return data


def save_config(path: Path, data: dict[str, Any]) -> None:
    atomic_json(path, data)


def valid_root_id(raw: str) -> str:
    if not raw or len(raw) > 64 or not all(ch.isalnum() or ch in "-_" for ch in raw):
        raise ValueError("root_id deve ter 1–64 caracteres alfanuméricos, hífen ou sublinhado")
    return raw


def relative_path(raw: str, field: str) -> Path:
    value = Path(raw)
    if value.is_absolute() or ".." in value.parts or not value.parts:
        raise ValueError(f"{field} deve ser caminho relativo sem '..'")
    return value


def canonical_request(payload: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in payload.items() if key != "signature"}
    return json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign_payload(payload: dict[str, Any], secret: str) -> dict[str, Any]:
    signed = dict(payload)
    signed["signature_alg"] = "hmac-sha256"
    signed.pop("signature", None)
    signed["signature"] = hmac.new(
        secret.encode("utf-8"), canonical_request(signed), hashlib.sha256
    ).hexdigest()
    return signed


def verify_signature(payload: dict[str, Any], secret: str) -> None:
    supplied = payload.get("signature")
    if payload.get("signature_alg") != "hmac-sha256" or not isinstance(supplied, str):
        raise ValueError("pedido sem assinatura HMAC-SHA256")
    expected = hmac.new(
        secret.encode("utf-8"), canonical_request(payload), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise ValueError("assinatura HMAC inválida")


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("manifest_version") != 1 or data.get("policy") != "strict":
        raise ValueError("manifesto incompatível; esperado manifest_version=1 e policy=strict")
    if data.get("fallback") != "pause_and_report":
        raise ValueError("manifesto deve usar fallback=pause_and_report")
    if not isinstance(data.get("seats"), dict) or not isinstance(data.get("routes"), dict):
        raise ValueError("manifesto precisa declarar seats e routes")
    native_sessions = data.get("native_sessions")
    if not isinstance(native_sessions, dict) or native_sessions.get("contract") != "native_session_mirror_v1":
        raise ValueError("manifesto precisa declarar native_session_mirror_v1")
    if native_sessions.get("default_persist") is not False:
        raise ValueError("persistência nativa deve ser opcional e desativada por padrão")
    return data


def resolve_seat(manifest: dict[str, Any], requested: str, model: str | None) -> dict[str, Any]:
    seats = manifest["seats"]
    canonical = requested
    if canonical not in seats:
        matches = [name for name, item in seats.items() if requested in item.get("aliases", [])]
        if len(matches) != 1:
            raise ValueError(f"cadeira desconhecida ou ambígua: {requested}")
        canonical = matches[0]
    seat = seats[canonical]
    route = seat.get("route")
    if route not in manifest["routes"]:
        raise ValueError(f"rota inexistente para {canonical}: {route}")
    if seat.get("model_policy") == "fixed_default":
        fixed = seat.get("default_model")
        if model in seat.get("aliases", []):
            model = fixed
        elif model and model != fixed:
            raise ValueError(f"modelo incompatível para {canonical}; esperado {fixed}")
        model = fixed
    return {
        "seat": canonical,
        "route": route,
        "provider": seat.get("provider"),
        "model": model or seat.get("default_model"),
    }


def specific_root(raw: str) -> Path:
    path = Path(raw).expanduser().resolve()
    if not path.is_dir():
        raise ValueError(f"raiz inexistente: {path}")
    if path in {Path("/").resolve(), Path.home().resolve()}:
        raise ValueError("a raiz deve ser uma pasta específica; '/' e a pasta pessoal são rejeitadas")
    return path


def ensure_allowed(root: Path, allowed: list[Path]) -> None:
    if not allowed:
        return
    if not any(root == parent or root.is_relative_to(parent) for parent in allowed):
        raise ValueError(f"raiz fora das pastas autorizadas: {root}")


def request_id(raw: Any) -> str:
    try:
        return str(uuid.UUID(str(raw)))
    except (ValueError, AttributeError) as exc:
        raise ValueError("request_id deve ser UUID") from exc


def validate_request(
    payload: dict[str, Any], manifest: dict[str, Any], allowed: list[Path], roots: dict[str, str] | None = None
) -> dict[str, Any]:
    if payload.get("bridge_version") != BRIDGE_VERSION:
        raise ValueError(f"bridge_version deve ser {BRIDGE_VERSION}")
    rid = request_id(payload.get("request_id"))
    participant = payload.get("participant")
    if not isinstance(participant, str) or not participant:
        raise ValueError("participant é obrigatório")
    model = payload.get("model")
    if model is not None and not isinstance(model, str):
        raise ValueError("model deve ser texto")
    resolved = resolve_seat(manifest, participant, model)
    root_id = payload.get("root_id")
    if root_id is not None:
        root_id = valid_root_id(str(root_id))
        root_map = roots or {}
        if root_id not in root_map:
            raise ValueError(f"root_id não cadastrado no host: {root_id}")
        root = specific_root(root_map[root_id])
        prompt_rel = relative_path(str(payload.get("prompt_rel", "")), "prompt_rel")
        prompt = (root / prompt_rel).resolve()
    else:
        if not payload.get("root") or not payload.get("prompt_file"):
            raise ValueError("root e prompt_file são obrigatórios no modo de caminho absoluto")
        root = specific_root(str(payload["root"]))
        prompt = Path(str(payload["prompt_file"])).expanduser().resolve()
    ensure_allowed(root, allowed)
    if not prompt.is_file():
        raise ValueError(f"prompt_file inexistente: {prompt}")
    if prompt.stat().st_size > MAX_PROMPT_BYTES:
        raise ValueError(f"prompt_file excede {MAX_PROMPT_BYTES} bytes")
    if not (prompt == root or prompt.is_relative_to(root)):
        raise ValueError("prompt_file precisa estar dentro da raiz do projeto")
    timeout = int(payload.get("timeout", 1800))
    if not 30 <= timeout <= 3600:
        raise ValueError("timeout deve ficar entre 30 e 3600 segundos")
    output_policy = payload.get("output_policy", "adaptive_up_to_native_max")
    if output_policy not in {"adaptive_up_to_native_max", "concise_soft_target"}:
        raise ValueError("output_policy inválida")
    effort = payload.get("effort")
    if effort is not None and not isinstance(effort, str):
        raise ValueError("effort deve ser texto")
    persist_en = payload.get("persist_native_session")
    persist_pt = payload.get("persistir_sessoes_nativas")
    for field, value in (
        ("persist_native_session", persist_en),
        ("persistir_sessoes_nativas", persist_pt),
    ):
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{field} deve ser booleano")
    if persist_en is not None and persist_pt is not None and persist_en != persist_pt:
        raise ValueError("aliases de persistência nativa não podem divergir")
    persist_native_session = bool(
        persist_pt if persist_pt is not None else persist_en if persist_en is not None else False
    )
    return {
        "request_id": rid,
        "participant": participant,
        "seat": resolved["seat"],
        "route": resolved["route"],
        "provider": resolved["provider"],
        "model": resolved["model"],
        "root": root,
        "root_id": root_id,
        "prompt": prompt,
        "timeout": timeout,
        "output_policy": output_policy,
        "effort": effort,
        "persist_native_session": persist_native_session,
        "dry_run": bool(payload.get("dry_run", False)),
    }


def adapter_command(
    request: dict[str, Any], manifest_path: Path, metadata_file: Path | None = None
) -> list[str]:
    command = [
        sys.executable,
        str(ADAPTER),
        "--manifest",
        str(manifest_path),
        "invoke",
        "--participant",
        request["participant"],
        "--root",
        str(request["root"]),
        "--prompt-file",
        str(request["prompt"]),
        "--output-policy",
        request["output_policy"],
        "--timeout",
        str(request["timeout"]),
    ]
    if request["model"]:
        command += ["--model", request["model"]]
    if request["effort"]:
        command += ["--effort", request["effort"]]
    if request.get("persist_native_session"):
        command += [
            "--persist-native-session",
            "--native-session-correlation-id",
            request["request_id"],
        ]
    if metadata_file is not None:
        command += ["--metadata-file", str(metadata_file)]
    if request["dry_run"]:
        command.append("--dry-run")
    return command


def validate_adapter() -> str:
    try:
        mode = ADAPTER.lstat().st_mode
    except FileNotFoundError as exc:
        raise ValueError(f"adaptador ausente: {ADAPTER}") from exc
    if not stat.S_ISREG(mode) or ADAPTER.is_symlink():
        raise ValueError(f"adaptador precisa ser arquivo regular, não symlink: {ADAPTER}")
    if mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ValueError(f"adaptador não pode ser gravável por grupo/outros: {ADAPTER}")
    return sha256(ADAPTER)


def run_adapter(command: list[str], root: Path, timeout: int) -> tuple[int, str, str, bool]:
    process = subprocess.Popen(
        command,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    killed_group = False
    try:
        stdout, stderr = process.communicate(timeout=timeout + 30)
        if process.returncode == 124 and "MULTIAGENT_PROCESS_GROUP_KILLED=1" in stderr:
            killed_group = True
        return process.returncode, stdout, stderr, killed_group
    except subprocess.TimeoutExpired:
        killed_group = True
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGTERM)
        try:
            stdout, stderr = process.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGKILL)
            stdout, stderr = process.communicate()
        stderr = f"{stderr.rstrip()}\nTempo limite excedido; grupo de processos encerrado.\n"
        return 124, stdout, stderr, killed_group


def snapshot_prompt(request: dict[str, Any], private_state: Path) -> tuple[Path, str, str]:
    source = request["prompt"]
    before = source.read_bytes()
    if len(before) > MAX_PROMPT_BYTES:
        raise ValueError(f"prompt_file excede {MAX_PROMPT_BYTES} bytes")
    source_hash = hashlib.sha256(before).hexdigest()
    snapshot = private_state / "requests" / f"{request['request_id']}.prompt.md"
    atomic_bytes(snapshot, before)
    snapshot_hash = sha256(snapshot)
    if snapshot_hash != source_hash:
        raise RuntimeError("falha ao congelar o prompt")
    return snapshot, source_hash, snapshot_hash


def process_request(
    source: Path,
    dirs: dict[str, Path],
    manifest: dict[str, Any],
    manifest_path: Path,
    allowed: list[Path],
    roots: dict[str, str],
    secret: str,
    private_state: Path,
) -> dict[str, Any]:
    mode = source.lstat().st_mode
    if not stat.S_ISREG(mode) or source.is_symlink():
        raise ValueError("pedido precisa ser arquivo regular, não symlink")
    if source.stat().st_size > MAX_REQUEST_BYTES:
        raise ValueError(f"pedido excede {MAX_REQUEST_BYTES} bytes")
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("pedido deve ser um objeto JSON")
    verify_signature(payload, secret)
    request = validate_request(payload, manifest, allowed, roots)
    rid = request["request_id"]
    if source.name != f"{rid}{REQUEST_SUFFIX}":
        raise ValueError("nome do arquivo não corresponde ao request_id validado")
    stdout_path = dirs["outbox"] / f"{rid}.stdout.txt"
    stderr_path = dirs["outbox"] / f"{rid}.stderr.txt"
    response_path = dirs["outbox"] / f"{rid}.response.json"
    if response_path.exists():
        raise ValueError(f"request_id já possui resposta: {rid}")
    consumed_path = private_state / "consumed" / f"{rid}.json"
    if consumed_path.exists():
        raise ValueError(f"request_id já foi consumido: {rid}")
    atomic_json_new(consumed_path, {
        "request_id": rid, "claimed_at": now(), "request_sha256": sha256(source)
    })
    started = now()
    adapter_hash = validate_adapter()
    snapshot, source_hash_pre, snapshot_hash_pre = snapshot_prompt(request, private_state)
    frozen_request = dict(request)
    frozen_request["prompt"] = snapshot
    native_metadata_path = private_state / "native-sessions" / f"{rid}.json"
    command = adapter_command(frozen_request, manifest_path, native_metadata_path)
    returncode, stdout, stderr, killed_group = run_adapter(command, request["root"], request["timeout"])
    snapshot_hash_post = sha256(snapshot)
    source_hash_post = sha256(request["prompt"])
    prompt_stable = snapshot_hash_pre == snapshot_hash_post and source_hash_pre == source_hash_post
    if returncode == 0 and not stdout.strip():
        returncode = 65
        stderr = f"{stderr.rstrip()}\nA CLI encerrou sem produzir manifestação.\n"
    status = "completed" if returncode == 0 and prompt_stable else "failed"
    atomic_text(stdout_path, stdout)
    atomic_text(stderr_path, stderr)
    native_metadata: dict[str, Any] = {
        "contract": "native_session_mirror_v1",
        "requested": request["persist_native_session"],
        "effective": False,
        "confirmed": False,
        "status": "missing_receipt" if request["persist_native_session"] else "not_requested",
        "session_id": None,
        "session_label": None,
        "central_history_is_canonical": True,
        "native_history_is_mirror_only": True,
    }
    if native_metadata_path.is_file():
        loaded = json.loads(native_metadata_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            native_metadata.update(loaded)
    response = {
        "bridge_version": BRIDGE_VERSION,
        "request_id": rid,
        "status": status,
        "participant": request["participant"],
        "seat": request["seat"],
        "route": request["route"],
        "provider": request["provider"],
        "model": request["model"] or "padrão do CLI",
        "model_requested": request["model"] or "padrão do CLI",
        "model_confirmed": False,
        "native_session_persistence_requested": bool(native_metadata.get("requested")),
        "native_session_persistence_effective": bool(native_metadata.get("effective")),
        "native_session_persistence_confirmed": bool(native_metadata.get("confirmed")),
        "native_session_persistence_status": native_metadata.get("status"),
        "native_session_id": native_metadata.get("session_id"),
        "native_session_label": native_metadata.get("session_label"),
        "native_session_receipt_file": str(native_metadata_path),
        "native_session_is_canonical": False,
        "output_policy": request["output_policy"],
        "root": str(request["root"]),
        "root_id": request["root_id"],
        "prompt_file": str(request["prompt"]),
        "prompt_snapshot_file": str(snapshot),
        "prompt_sha256": snapshot_hash_pre,
        "prompt_sha256_source_pre": source_hash_pre,
        "prompt_sha256_source_post": source_hash_post,
        "prompt_sha256_snapshot_pre": snapshot_hash_pre,
        "prompt_sha256_snapshot_post": snapshot_hash_post,
        "prompt_stable": prompt_stable,
        "stdout_file": stdout_path.name,
        "stdout_sha256": sha256(stdout_path),
        "stderr_file": stderr_path.name,
        "stderr_sha256": sha256(stderr_path),
        "returncode": returncode,
        "killed_process_group": killed_group,
        "adapter_file": str(ADAPTER),
        "adapter_sha256": adapter_hash,
        "simulation": request["dry_run"],
        "verdict": (
            "external_manifestation_only"
            if status == "completed" and not request["dry_run"]
            else None
        ),
        "started_at": started,
        "completed_at": now(),
    }
    atomic_json(response_path, response)
    return response


def failure_record(path: Path, dirs: dict[str, Path], exc: Exception) -> None:
    raw_rid = path.name.removesuffix(REQUEST_SUFFIX)
    try:
        rid = request_id(raw_rid)
    except ValueError:
        rid = None
    target = dirs["failed"] / path.name
    if path.exists():
        os.replace(path, target)
    payload = {
        "bridge_version": BRIDGE_VERSION,
        "request_id": rid,
        "request_file": target.name,
        "status": "failed",
        "error": str(exc),
        "simulation": False,
        "verdict": None,
        "failed_at": now(),
    }
    error_name = f"{rid}.error.json" if rid else f"invalid-{hashlib.sha256(path.name.encode()).hexdigest()[:16]}.error.json"
    atomic_json(dirs["failed"] / error_name, payload)
    if rid:
        visible_response = dirs["outbox"] / f"{rid}.response.json"
        if not visible_response.exists():
            atomic_json(visible_response, payload)


def claim(path: Path, processing: Path) -> Path | None:
    target = processing / path.name
    try:
        os.replace(path, target)
    except FileNotFoundError:
        return None
    return target


def request_is_stable(path: Path) -> bool:
    with contextlib.suppress(FileNotFoundError):
        return time.time() - path.stat().st_mtime >= MIN_REQUEST_AGE_SECONDS
    return False


def recover_orphans(dirs: dict[str, Path]) -> int:
    recovered = 0
    for current in sorted(dirs["processing"].glob(f"*{REQUEST_SUFFIX}")):
        raw_rid = current.name.removesuffix(REQUEST_SUFFIX)
        response_path = dirs["outbox"] / f"{raw_rid}.response.json"
        if response_path.exists():
            try:
                status_value = json.loads(response_path.read_text(encoding="utf-8")).get("status")
            except (OSError, json.JSONDecodeError):
                status_value = "failed"
            destination = dirs["state"] if status_value == "completed" else dirs["failed"]
            os.replace(current, destination / current.name)
        else:
            failure_record(current, dirs, RuntimeError("interrupted: pedido órfão recuperado após reinício"))
        recovered += 1
    return recovered


@contextlib.contextmanager
def exclusive_daemon(private_state: Path):
    ensure_private_dir(private_state)
    lock_path = private_state / "bridge.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        os.fchmod(handle.fileno(), 0o600)
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("já existe um bridge processando esta fila") from exc
        yield


def run_once(args: argparse.Namespace) -> int:
    root = Path(args.bridge_dir).expanduser().resolve()
    dirs = bridge_dirs(root)
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = load_manifest(manifest_path)
    config = load_config(Path(args.config).expanduser().resolve())
    private_state = Path(args.private_state).expanduser().resolve()
    if private_state == root or private_state.is_relative_to(root):
        raise ValueError("private-state deve ficar fora da pasta compartilhada")
    ensure_private_dir(private_state)
    allowed = [specific_root(item) for item in args.allow_root]
    processed = 0
    for pending in sorted(dirs["inbox"].glob(f"*{REQUEST_SUFFIX}")):
        if not request_is_stable(pending):
            continue
        current = claim(pending, dirs["processing"])
        if current is None:
            continue
        try:
            response = process_request(
                current, dirs, manifest, manifest_path, allowed, config["roots"],
                config["bridge_secret"], private_state,
            )
            destination = dirs["failed"] if response["status"] == "failed" else dirs["state"]
            os.replace(current, destination / current.name)
        except Exception as exc:  # recibo de falha é parte do contrato do bridge
            failure_record(current, dirs, exc)
        processed += 1
    if processed or getattr(args, "report_empty", False):
        print(json.dumps({"processed": processed, "bridge_dir": str(root)}, ensure_ascii=False))
    return 0


def run_serve(args: argparse.Namespace) -> int:
    stop = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    dirs = bridge_dirs(Path(args.bridge_dir).expanduser().resolve())
    private_state = Path(args.private_state).expanduser().resolve()
    args.report_empty = bool(args.once)
    with exclusive_daemon(private_state):
        recovered = recover_orphans(dirs)
        if recovered:
            print(json.dumps({"recovered": recovered, "bridge_dir": str(args.bridge_dir)}, ensure_ascii=False))
        while not stop:
            try:
                run_once(args)
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                atomic_json(private_state / "bridge.pause.json", {
                    "status": "paused", "error": str(exc), "paused_at": now()
                })
                print(json.dumps({"status": "paused", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
            if args.once:
                break
            time.sleep(args.poll_interval)
    return 0


def run_doctor(args: argparse.Namespace) -> int:
    command = [sys.executable, str(ADAPTER), "--manifest", str(Path(args.manifest).expanduser()), "doctor"]
    if args.deep:
        command.append("--deep")
    return subprocess.run(command, check=False).returncode


def run_invoke(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = load_manifest(manifest_path)
    payload = {
        "bridge_version": BRIDGE_VERSION,
        "request_id": str(uuid.uuid4()),
        "participant": args.participant,
        "model": args.model,
        "root": args.root,
        "prompt_file": args.prompt_file,
        "effort": args.effort,
        "output_policy": args.output_policy,
        "persist_native_session": args.persist_native_session,
        "timeout": args.timeout,
        "dry_run": args.dry_run,
        "created_at": now(),
    }
    request = validate_request(payload, manifest, [specific_root(item) for item in args.allow_root])
    return subprocess.run(adapter_command(request, manifest_path), cwd=request["root"], check=False).returncode


def run_sign_request(args: argparse.Namespace) -> int:
    target = Path(args.output).expanduser().resolve()
    if target.exists() or target.is_symlink():
        raise ValueError(f"o pedido já existe e não será sobrescrito: {target}")
    if args.input == "-":
        payload = json.load(sys.stdin)
    else:
        source = Path(args.input).expanduser().resolve()
        payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("pedido a assinar deve ser objeto JSON")
    rid = request_id(payload.get("request_id"))
    if target.name != f"{rid}{REQUEST_SUFFIX}":
        raise ValueError("o nome de saída deve ser <request_id>.request.json")
    secret = os.environ.get("MULTIAGENT_BRIDGE_SECRET") or os.environ.get(
        "CLAUDE_PLUGIN_OPTION_BRIDGE_SECRET"
    )
    if not secret or len(secret) < 64:
        raise ValueError("segredo do bridge ausente; configure a opção sensível bridge_secret")
    atomic_json_new(target, sign_payload(payload, secret))
    print(json.dumps({"request_id": rid, "output": str(target), "signed": True}, ensure_ascii=False))
    return 0


def run_register_root(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    root_id = valid_root_id(args.id)
    root = specific_root(args.path)
    config["roots"][root_id] = str(root)
    save_config(config_path, config)
    print(json.dumps({"root_id": root_id, "path": str(root)}, ensure_ascii=False))
    return 0


def run_remove_root(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    root_id = valid_root_id(args.id)
    if root_id not in config["roots"]:
        raise ValueError(f"root_id não cadastrado: {root_id}")
    removed = config["roots"].pop(root_id)
    save_config(config_path, config)
    print(json.dumps({"removed": root_id, "path": removed}, ensure_ascii=False))
    return 0


def copy_secret(config_path: Path) -> None:
    config = load_config(config_path)
    completed = subprocess.run(
        ["/usr/bin/pbcopy"], input=config["bridge_secret"], text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError("não foi possível copiar o segredo para a área de transferência")


def run_rotate_secret(args: argparse.Namespace) -> int:
    config_path = Path(args.config).expanduser().resolve()
    config = load_config(config_path)
    config["bridge_secret"] = hashlib.sha256(os.urandom(64)).hexdigest()
    save_config(config_path, config)
    if args.copy:
        copy_secret(config_path)
    print(json.dumps({"rotated": True, "copied_to_clipboard": bool(args.copy)}, ensure_ascii=False))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--manifest",
        default=os.environ.get("MULTIAGENT_MANIFEST", str(DEFAULT_MANIFEST)),
        help="manifesto canônico de rotas e cadeiras",
    )
    result.add_argument(
        "--private-state",
        default=os.environ.get("MULTIAGENT_COWORK_PRIVATE_STATE", str(DEFAULT_PRIVATE_STATE)),
        help="ledger privado de replay, snapshots e lock do host",
    )
    result.add_argument(
        "--bridge-dir",
        default=os.environ.get("MULTIAGENT_COWORK_BRIDGE_DIR", str(DEFAULT_BRIDGE_DIR)),
    )
    result.add_argument(
        "--config",
        default=os.environ.get("MULTIAGENT_COWORK_BRIDGE_CONFIG", str(DEFAULT_CONFIG)),
        help="cadastro privado de raízes do host",
    )
    subs = result.add_subparsers(dest="command", required=True)

    init = subs.add_parser("init", help="criar a fila compartilhada")

    doctor = subs.add_parser("doctor", help="diagnosticar CLIs")
    doctor.add_argument("--deep", action="store_true")

    register = subs.add_parser("register-root", help="cadastrar raiz por identificador para o Cowork")
    register.add_argument("--id", required=True)
    register.add_argument("--path", required=True)

    remove = subs.add_parser("remove-root", help="remover raiz cadastrada")
    remove.add_argument("--id", required=True)

    subs.add_parser("list-roots", help="listar identificadores e caminhos cadastrados")

    subs.add_parser("copy-secret", help="copiar o segredo para a área de transferência sem exibi-lo")

    rotate = subs.add_parser("rotate-secret", help="rotacionar o segredo HMAC do bridge")
    rotate.add_argument("--copy", action="store_true", help="copiar o novo segredo para a área de transferência")

    once = subs.add_parser("once", help="processar os pedidos disponíveis")
    once.add_argument("--allow-root", action="append", default=[])

    serve = subs.add_parser("serve", help="processar continuamente a fila")
    serve.add_argument("--allow-root", action="append", default=[])
    serve.add_argument("--poll-interval", type=float, default=1.0)
    serve.add_argument("--once", action="store_true")

    invoke = subs.add_parser("invoke", help="invocar uma cadeira diretamente")
    invoke.add_argument("--participant", required=True)
    invoke.add_argument("--model")
    invoke.add_argument("--root", required=True)
    invoke.add_argument("--prompt-file", required=True)
    invoke.add_argument("--effort")
    invoke.add_argument(
        "--output-policy",
        choices=("adaptive_up_to_native_max", "concise_soft_target"),
        default="adaptive_up_to_native_max",
    )
    invoke.add_argument("--timeout", type=int, default=1800)
    invoke.add_argument(
        "--persist-native-session",
        action="store_true",
        help="Espelhar a chamada no histórico nativo da CLI quando suportado",
    )
    invoke.add_argument("--allow-root", action="append", default=[])
    invoke.add_argument("--dry-run", action="store_true")

    sign_request = subs.add_parser("sign-request", help="assinar e publicar pedido do Cowork")
    sign_request.add_argument("--input", required=True, help="JSON sem assinatura ou '-' para stdin")
    sign_request.add_argument("--output", required=True, help="destino <uuid>.request.json")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "init":
            dirs = bridge_dirs(Path(args.bridge_dir).expanduser().resolve(), enforce_permissions=True)
            print(json.dumps({"bridge_dir": str(Path(args.bridge_dir).expanduser().resolve()), "dirs": {k: str(v) for k, v in dirs.items()}}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "doctor":
            return run_doctor(args)
        if args.command == "register-root":
            return run_register_root(args)
        if args.command == "remove-root":
            return run_remove_root(args)
        if args.command == "list-roots":
            config = load_config(Path(args.config).expanduser().resolve())
            print(json.dumps({"config_version": config["config_version"], "roots": config["roots"]}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "copy-secret":
            copy_secret(Path(args.config).expanduser().resolve())
            print(json.dumps({"copied_to_clipboard": True}, ensure_ascii=False))
            return 0
        if args.command == "rotate-secret":
            return run_rotate_secret(args)
        if args.command == "invoke":
            return run_invoke(args)
        if args.command == "sign-request":
            return run_sign_request(args)
        if args.command == "once":
            args.poll_interval = 0.2
            args.once = True
            args.report_empty = True
        if args.poll_interval < 0.2 or args.poll_interval > 60:
            raise ValueError("poll-interval deve ficar entre 0.2 e 60 segundos")
        return run_serve(args)
    except (OSError, ValueError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
