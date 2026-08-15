#!/usr/bin/env python3
"""Invoke one explicitly selected CLI with full local filesystem access."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
if str(PLUGIN_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
import provenance  # noqa: E402


PACKAGED_MANIFEST = Path(__file__).resolve().parents[3] / "assets" / "multiagent-manifest.json"
HOST_MANIFEST = Path("~/.agents/multiagent-manifest.json").expanduser()
MODEL_PATTERN = re.compile(r"^[A-Za-z0-9._:/@+\-]+$")
EFFORT_PATTERN = re.compile(r"^[A-Za-z0-9._+\-]+$")
MAX_PROMPT_BYTES = 512 * 1024
OUTPUT_POLICIES = ("adaptive_up_to_native_max", "concise_soft_target")
REQUIRED_GROK_MODEL = "cursor-grok-4.6-high"


def default_output_policy() -> dict[str, Any]:
    return {
        "contract": "adaptive_output_v1",
        "default_policy": "adaptive_up_to_native_max",
        "policies": list(OUTPUT_POLICIES),
        "force_fill": False,
        "global_max_output_tokens": None,
    }


def default_filesystem_policy() -> dict[str, Any]:
    return {
        "contract": "scoped_full_tools_v2",
        "default_policy": "project_root_plus_explicit_directories",
        "directory_scope": "explicit_per_invocation",
        "implicit_home_scope": False,
        "home_scope_requires_explicit_opt_in": True,
        "full_tool_permissions_within_host_identity": True,
        "os_security_boundary": False,
        "can_read": True,
        "can_create": True,
        "can_modify": True,
        "can_delete": True,
        "auto_approve_local_tools": True,
        "canonical_write_requires_resolved_role": True,
    }


def resolve_manifest(raw: str | None) -> Path:
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw).expanduser())
    elif os.environ.get("MULTIAGENT_MANIFEST"):
        candidates.append(Path(os.environ["MULTIAGENT_MANIFEST"]).expanduser())
    else:
        candidates.extend((HOST_MANIFEST, PACKAGED_MANIFEST))
    for candidate in candidates:
        path = candidate.resolve()
        if path.is_file():
            return path
    rendered = ", ".join(str(item.resolve()) for item in candidates)
    raise RuntimeError(f"Manifesto multiagente ausente; verificados: {rendered}")


def load_manifest(raw: str | None) -> dict[str, Any]:
    path = resolve_manifest(raw)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Manifesto multiagente ausente: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Manifesto multiagente inválido: {exc}") from exc
    if data.get("manifest_version") != 1 or data.get("policy") != "strict":
        raise RuntimeError("Manifesto multiagente incompatível; esperado v1 com policy=strict.")
    if data.get("fallback") != "pause_and_report":
        raise RuntimeError("Manifesto deve usar fallback=pause_and_report.")
    if not isinstance(data.get("routes"), dict) or not isinstance(data.get("seats"), dict):
        raise RuntimeError("Manifesto precisa declarar routes e seats.")
    native_sessions = data.get("native_sessions")
    if not isinstance(native_sessions, dict) or native_sessions.get("contract") != "native_session_mirror_v1":
        raise RuntimeError("Contrato de sessões nativas incompatível; esperado native_session_mirror_v1.")
    if native_sessions.get("default_persist") is not False:
        raise RuntimeError("Persistência nativa deve permanecer opcional e desativada por padrão.")
    if native_sessions.get("central_history_is_canonical") is not True:
        raise RuntimeError("O ledger central deve permanecer como histórico canônico.")
    output = data.get("output")
    if output is None:
        output = default_output_policy()
        data["output"] = output
    if not isinstance(output, dict) or output.get("contract") != "adaptive_output_v1":
        raise RuntimeError("Contrato de saída incompatível; esperado adaptive_output_v1.")
    if "policies" not in output:
        # Retrocompatibilidade com o primeiro formato do contrato adaptativo.
        output["policies"] = list(OUTPUT_POLICIES)
    if output.get("default_policy") != "adaptive_up_to_native_max":
        raise RuntimeError("A política padrão deve permitir até o teto nativo da rota.")
    if output.get("force_fill") is not False or output.get("global_max_output_tokens") is not None:
        raise RuntimeError("A política de saída não pode forçar preenchimento nem impor teto global.")
    filesystem = data.get("filesystem")
    if not isinstance(filesystem, dict) or filesystem.get("contract") != "scoped_full_tools_v2":
        raise RuntimeError("Contrato de arquivos incompatível; esperado scoped_full_tools_v2.")
    expected_true = (
        "can_read", "can_create", "can_modify", "can_delete",
        "auto_approve_local_tools", "canonical_write_requires_resolved_role",
    )
    if (
        filesystem.get("default_policy") != "project_root_plus_explicit_directories"
        or filesystem.get("directory_scope") != "explicit_per_invocation"
        or filesystem.get("implicit_home_scope") is not False
        or filesystem.get("home_scope_requires_explicit_opt_in") is not True
        or filesystem.get("full_tool_permissions_within_host_identity") is not True
        or filesystem.get("os_security_boundary") is not False
        or any(filesystem.get(field) is not True for field in expected_true)
    ):
        raise RuntimeError("O manifesto não aplica ferramentas completas com escopos explícitos.")
    required = {
        "claude": "claude",
        "grok": "cursor",
        "kimi": "kimi",
        "gemini": "antigravity",
    }
    for seat, route in required.items():
        if data["seats"].get(seat, {}).get("route") != route:
            raise RuntimeError(f"Rota obrigatória inválida para {seat}; esperado {route}.")
    return data


def resolve_output_policy(data: dict[str, Any], requested: str | None, route: str) -> dict[str, Any]:
    output = data["output"]
    policy = requested or output["default_policy"]
    if policy not in output.get("policies", []):
        raise RuntimeError(f"Política de saída inválida: {policy}")
    control = data["routes"][route].get("output_control") or {
        "mode": "native_route_ceiling",
        "max_output_tokens_flag": None,
    }
    if not isinstance(control, dict) or control.get("mode") != "native_route_ceiling":
        raise RuntimeError(f"Rota {route} não declara controle de saída compatível.")
    return {
        "policy": policy,
        "control": control["mode"],
        "explicit_max_flag": control.get("max_output_tokens_flag"),
        "force_fill": False,
        "artificial_global_cap": None,
    }


def output_directive(policy: str) -> str:
    if policy == "concise_soft_target":
        return (
            "POLÍTICA DE SAÍDA — META FLEXÍVEL DE CONCISÃO:\n"
            "Responda de forma concisa, mas trate qualquer meta de palavras como orientação, não "
            "como truncamento. Exceda-a quando necessário para completar corretamente a tarefa. "
            "Não produza texto para preencher cota e não omita partes obrigatórias."
        )
    return (
        "POLÍTICA DE SAÍDA — ADAPTATIVA ATÉ O MÁXIMO NATIVO:\n"
        "Use apenas a extensão necessária para concluir a tarefa, sem meta mínima e sem preencher "
        "artificialmente a resposta. Quando necessário, use até o teto de saída disponibilizado "
        "pela rota para o modelo selecionado. Não abrevie, resuma ou omita entregáveis para caber "
        "em um limite menor inventado. Se um artefato obrigatório não couber, pare em um limite "
        "estrutural limpo, indique CONTINUATION_REQUIRED e não alegue que ele está completo."
    )


def resolve_seat(data: dict[str, Any], participant: str, model: str | None) -> dict[str, Any]:
    seats = data["seats"]
    canonical = participant
    if participant not in seats:
        matches = [name for name, entry in seats.items() if participant in entry.get("aliases", [])]
        if len(matches) != 1:
            raise RuntimeError(f"Participante desconhecido: {participant}")
        canonical = matches[0]
    seat = seats[canonical]
    route = seat.get("route")
    if route not in data["routes"]:
        raise RuntimeError(f"Rota inexistente para {canonical}: {route}")
    if seat.get("model_policy") == "fixed_default":
        fixed = seat.get("default_model")
        if model in seat.get("aliases", []):
            model = fixed
        elif model and model != fixed:
            raise RuntimeError(
                f"Modelo incompatível para {canonical}: a política local fixa {fixed}, recebeu {model}."
            )
        model = fixed
    return {
        "seat": canonical,
        "route": route,
        "model": model or seat.get("default_model"),
        "provider": seat.get("provider"),
        "default_effort": seat.get("default_effort"),
        "effort_policy": seat.get("effort_policy"),
        "context_window_tokens": seat.get("context_window_tokens"),
    }


def chinese_model_requires_max_effort(resolved: dict[str, Any]) -> bool:
    """Return whether the effective seat/model is governed by fixed max effort."""
    if resolved.get("effort_policy") == "fixed_max":
        return True
    model = str(resolved.get("model") or "").lower()
    return any(marker in model for marker in ("kimi", "glm-", "deepseek", "qwen"))


def resolve_effort(resolved: dict[str, Any], requested: str | None) -> str | None:
    """Resolve effort without silently downgrading governed Chinese models."""
    if chinese_model_requires_max_effort(resolved):
        if requested not in {None, "max"}:
            raise RuntimeError(
                "Kimi, GLM, DeepSeek e Qwen usam esforço máximo obrigatório; use --effort max."
            )
        return "max"
    return requested or resolved.get("default_effort")


def executable(route: str, data: dict[str, Any]) -> str:
    name = data["routes"][route]["binary"]
    resolved = shutil.which(name)
    if not resolved:
        raise RuntimeError(f"CLI ausente para rota {route}: {name}")
    return resolved


def safe_root(raw: str) -> Path:
    try:
        return provenance.canonical_directory(raw)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from exc


def additional_directories(
    values: list[str] | None,
    *,
    root: Path,
    allow_home: bool,
) -> list[Path]:
    result: list[Path] = []
    home = Path.home().resolve()
    for raw in values or []:
        try:
            candidate = provenance.canonical_directory(raw, reject_home=not allow_home)
        except ValueError as exc:
            raise RuntimeError(str(exc)) from exc
        if candidate == home and not allow_home:
            raise RuntimeError("A pasta pessoal exige --allow-home explícito.")
        if candidate == root or candidate in result:
            continue
        result.append(candidate)
    if allow_home and home not in result:
        result.append(home)
    return result


def prompt_text(raw: str) -> tuple[Path, str]:
    path = Path(raw).expanduser().resolve(strict=True)
    try:
        content, record = provenance.read_file_bytes(path)
    except (OSError, ValueError) as exc:
        raise RuntimeError(str(exc)) from exc
    if record["bytes"] > MAX_PROMPT_BYTES:
        raise RuntimeError(f"Prompt excede {MAX_PROMPT_BYTES} bytes: {path}")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("O prompt deve usar UTF-8 válido.") from exc
    if "\x00" in text:
        raise RuntimeError("O prompt contém byte nulo.")
    return path, text


def validate_model(model: str | None) -> None:
    if model and not MODEL_PATTERN.fullmatch(model):
        raise RuntimeError("Nome de modelo inválido; use apenas letras, números e ._:/@+-")


def validate_effort(effort: str | None) -> None:
    if effort and not EFFORT_PATTERN.fullmatch(effort):
        raise RuntimeError("Nível de esforço inválido; use apenas letras, números e ._+-")


def timeout_value(raw: str) -> int:
    value = int(raw)
    if not 30 <= value <= 3600:
        raise argparse.ArgumentTypeError("o timeout deve ficar entre 30 e 3600 segundos")
    return value


def session_uuid(raw: str | None) -> str:
    if raw is None:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(raw))
    except ValueError as exc:
        raise RuntimeError("O identificador de correlação da sessão deve ser UUID.") from exc


def write_metadata(path: str | None, payload: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, raw = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    tmp = Path(raw)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, target)
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        tmp.unlink(missing_ok=True)


def json_objects(raw: str) -> list[Any]:
    values: list[Any] = []
    stripped = raw.strip()
    if not stripped:
        return values
    try:
        values.append(json.loads(stripped))
        return values
    except json.JSONDecodeError:
        pass
    for line in stripped.splitlines():
        try:
            values.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return values


def recursive_value(value: Any, keys: tuple[str, ...]) -> str | None:
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
        for candidate in value.values():
            found = recursive_value(candidate, keys)
            if found:
                return found
    elif isinstance(value, list):
        for candidate in value:
            found = recursive_value(candidate, keys)
            if found:
                return found
    return None


def structured_observation(
    raw: str, requested_model: str | None
) -> tuple[str | None, str | None, list[str]]:
    values = json_objects(raw)
    model_candidates: list[str] = []
    for value in values:
        if not isinstance(value, dict):
            continue
        for key in ("model", "model_id", "modelId", "modelID", "model_name", "modelName"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                model_candidates.append(candidate)
        for key in ("modelUsage", "model_usage", "usageByModel", "usage_by_model"):
            usage = value.get(key)
            if isinstance(usage, dict):
                model_candidates.extend(
                    candidate for candidate in usage if isinstance(candidate, str) and candidate
                )
    unique_models = sorted(set(model_candidates))
    observed = (
        requested_model
        if requested_model and unique_models == [requested_model]
        else None
    )
    rendered: str | None = None
    for value in reversed(values):
        rendered = recursive_value(
            value,
            ("result", "final_output", "finalOutput", "output_text", "outputText", "text"),
        )
        if rendered:
            break
    return observed, rendered, unique_models


def structured_session_observation(raw: str, route: str) -> str | None:
    """Lê somente campos de envelope da CLI, nunca conteúdo aninhado do agente."""

    keys = {
        "codex": ("thread_id", "threadId"),
        "claude": ("session_id", "sessionId"),
        "gemini": ("session_id", "sessionId"),
    }.get(route, ())
    for value in json_objects(raw):
        if not isinstance(value, dict):
            continue
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate:
                return candidate
    return None


def cursor_chat(binary: str) -> str:
    completed = subprocess.run(
        [binary, "create-chat"], text=True, capture_output=True, timeout=20, check=False
    )
    candidate = (completed.stdout or completed.stderr).strip().splitlines()
    if completed.returncode != 0 or not candidate:
        raise RuntimeError("O Cursor não conseguiu criar a sessão nativa solicitada.")
    return session_uuid(candidate[-1].strip())


def opencode_session(binary: str, label: str) -> str | None:
    completed = subprocess.run(
        [binary, "session", "list", "--max-count", "100", "--format", "json"],
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if completed.returncode != 0:
        return None
    for value in json_objects(completed.stdout):
        entries = value if isinstance(value, list) else [value]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            title = recursive_value(entry, ("title", "name"))
            if title == label:
                return recursive_value(entry, ("id", "sessionID", "session_id", "sessionId"))
    return None


def opencode_permissions() -> str:
    return json.dumps(
        {
            "read": "allow",
            "glob": "allow",
            "grep": "allow",
            "list": "allow",
            "lsp": "allow",
            "edit": "allow",
            "bash": "allow",
            "task": "allow",
            "external_directory": "allow",
            "webfetch": "allow",
            "websearch": "allow",
            "skill": "allow",
            "question": "allow",
            "todowrite": "allow",
            "doom_loop": "allow",
        },
        separators=(",", ":"),
    )


def build_invocation(
    participant: str,
    route: str,
    binary: str,
    root: Path,
    prompt_path: Path,
    prompt: str,
    model: str | None,
    effort: str | None,
    output_policy: str,
    persist_native_session: bool = False,
    native_session_id: str | None = None,
    native_session_label: str | None = None,
    native_output_path: Path | None = None,
    additional_dirs: list[Path] | None = None,
) -> tuple[list[str], str | None, dict[str, str]]:
    env = os.environ.copy()
    for sensitive_name in (
        "MULTIAGENT_ATTESTATION_KEY",
        "MULTIAGENT_ATTESTATION_SECRET_FILE",
        "MULTIAGENT_BRIDGE_SECRET",
        "CLAUDE_PLUGIN_OPTION_BRIDGE_SECRET",
    ):
        env.pop(sensitive_name, None)
    stdin: str | None = None
    directive = output_directive(output_policy)
    governed_prompt = f"{prompt.rstrip()}\n\n{directive}\n"
    granted_dirs = [str(item) for item in additional_dirs or []]

    if route == "codex":
        command = [
            binary,
            "exec",
            "--dangerously-bypass-approvals-and-sandbox",
            "--skip-git-repo-check",
            "--cd",
            str(root),
        ]
        command.append("--json")
        if native_output_path is not None:
            command += ["--output-last-message", str(native_output_path)]
        if not persist_native_session:
            command.append("--ephemeral")
        if model:
            command += ["--model", model]
        if effort:
            command += ["-c", f"model_reasoning_effort={effort}"]
        command.append("-")
        stdin = governed_prompt
    elif route == "claude":
        command = [
            binary,
            "--print",
            "--dangerously-skip-permissions",
            "--tools",
            "default",
            "--output-format",
            "json",
        ]
        for directory in granted_dirs:
            command += ["--add-dir", directory]
        if persist_native_session:
            command += ["--session-id", native_session_id or session_uuid(None)]
        else:
            command.append("--no-session-persistence")
        if model:
            command += ["--model", model]
        if effort:
            command += ["--effort", effort]
        stdin = governed_prompt
    elif route == "gemini":
        command = [
            binary,
            "--approval-mode",
            "yolo",
            "--skip-trust",
            "--output-format",
            "json",
        ]
        if granted_dirs:
            command += ["--include-directories", ",".join(granted_dirs)]
        if model:
            command += ["--model", model]
        if persist_native_session:
            command += ["--session-id", native_session_id or session_uuid(None)]
        command += [
            "--prompt",
            (
                "Leia integralmente o arquivo de instruções "
                f"{prompt_path} e execute-o.\n\n{directive}"
            ),
        ]
    elif route == "antigravity":
        command = [
            binary,
            "--mode",
            "accept-edits",
            "--dangerously-skip-permissions",
            "--output-format",
            "json",
        ]
        for directory in granted_dirs:
            command += ["--add-dir", directory]
        if model:
            command += ["--model", model]
        if effort:
            command += ["--effort", effort]
        command += [
            "--print",
            (
                "Leia integralmente o arquivo de instruções "
                f"{prompt_path} e execute-o.\n\n{directive}"
            ),
        ]
    elif route == "kimi":
        command = [
            binary,
            "--output-format",
            "stream-json",
        ]
        for directory in granted_dirs:
            command += ["--add-dir", directory]
        if model:
            command += ["--model", model]
        command += [
            "--prompt",
            (
                "Leia integralmente o arquivo de instruções "
                f"{prompt_path} e execute-o.\n\n{directive}"
            ),
        ]
    elif route == "cursor":
        command = [
            binary,
            "--print",
            "--force",
            "--sandbox",
            "disabled",
            "--trust",
            "--approve-mcps",
            "--workspace",
            str(root),
            "--output-format",
            "json",
        ]
        for directory in granted_dirs:
            command += ["--add-dir", directory]
        if persist_native_session and native_session_id:
            command += ["--resume", native_session_id]
        command += ["--model", model or REQUIRED_GROK_MODEL]
        stdin = governed_prompt
    elif route == "opencode":
        env["OPENCODE_PERMISSION"] = opencode_permissions()
        env["OPENCODE_AUTO_SHARE"] = "false"
        command = [binary, "run", "--auto", "--dir", str(root), "--format", "json"]
        if persist_native_session and native_session_label:
            command += ["--title", native_session_label]
        if model:
            command += ["--model", model]
        if effort:
            command += ["--variant", effort]
        # A mensagem posicional precisa vir antes de --file. Na ordem inversa,
        # algumas versões do OpenCode consomem a mensagem como outro arquivo.
        command += [
            f"Siga integralmente as instruções do arquivo anexado.\n\n{directive}",
            "--file",
            str(prompt_path),
        ]
    else:
        raise RuntimeError(f"Rota sem adaptador de invocação: {route}")

    return command, stdin, env


def version_of(participant: str, manifest: dict[str, Any]) -> dict[str, object]:
    resolved = resolve_seat(manifest, participant, None)
    route = resolved["route"]
    name = manifest["routes"][route]["binary"]
    binary = shutil.which(name)
    if not binary:
        return {"installed": False, "command": name, "route": route}
    try:
        completed = subprocess.run(
            [binary, "--version"],
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
        output = (completed.stdout or completed.stderr).strip().splitlines()
        return {
            "installed": True,
            "command": binary,
            "route": route,
            "default_model": resolved.get("model"),
            "version": output[0] if output else "desconhecida",
        }
    except Exception as exc:
        return {"installed": True, "command": binary, "version_error": str(exc)}


def deep_status(participant: str, manifest: dict[str, Any]) -> str:
    resolved = resolve_seat(manifest, participant, None)
    route = resolved["route"]
    binary = executable(route, manifest)
    if route == "antigravity":
        command = [binary, "models"]
    elif route == "kimi":
        command = [binary, "provider", "list"]
    elif route == "cursor":
        command = [binary, "status"]
    elif route == "opencode":
        command = [binary, "auth", "list"]
    else:
        return "não sondado; validar na primeira invocação"
    completed = subprocess.run(command, text=True, capture_output=True, timeout=20, check=False)
    output = f"{completed.stdout}\n{completed.stderr}".strip().lower()
    if (
        "not authenticated" in output
        or "0 credentials" in output
        or "no providers configured" in output
    ):
        return "não autenticado"
    return "disponível" if completed.returncode == 0 else "falhou na sondagem"


def run_doctor(manifest: dict[str, Any], deep: bool) -> int:
    report: dict[str, object] = {}
    for participant in manifest["seats"]:
        status = version_of(participant, manifest)
        if deep and status.get("installed"):
            try:
                status["authentication"] = deep_status(participant, manifest)
            except subprocess.TimeoutExpired:
                status["authentication"] = "sondagem inconclusiva; validar na primeira invocação"
            except Exception as exc:
                status["authentication"] = f"erro: {exc}"
        report[participant] = status
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


def run_invoke(args: argparse.Namespace, manifest: dict[str, Any]) -> int:
    root = safe_root(args.root)
    source_prompt_path, prompt = prompt_text(args.prompt_file)
    granted = additional_directories(args.add_dir, root=root, allow_home=args.allow_home)
    validate_model(args.model)
    validate_effort(args.effort)
    resolved = resolve_seat(manifest, args.participant, args.model)
    route = resolved["route"]
    model = resolved["model"]
    effort = resolve_effort(resolved, args.effort)
    output = resolve_output_policy(manifest, args.output_policy, route)
    binary = manifest["routes"][route]["binary"] if args.dry_run else executable(route, manifest)
    if route == "gemini" and effort:
        raise RuntimeError("O Gemini CLI atual não expõe nível de esforço; remova --effort.")
    persist = bool(args.persist_native_session)
    execution_id = str(uuid.uuid4())
    correlation_id = session_uuid(args.native_session_correlation_id) if persist else None
    native_session_id: str | None = None
    native_session_label = f"multiagent-{correlation_id}" if correlation_id else None
    route_policy = (
        manifest.get("native_sessions", {}).get("routes", {}).get(route, {})
        if isinstance(manifest.get("native_sessions"), dict)
        else {}
    )
    metadata: dict[str, Any] = {
        "contract": "native_session_mirror_v1",
        "requested": persist,
        "route": route,
        "seat": resolved["seat"],
        "provider": resolved.get("provider"),
        "mode": route_policy.get("mode", "not_declared"),
        "correlation_id": correlation_id,
        "session_id": None,
        "session_requested_id": correlation_id,
        "session_label": native_session_label,
        "effective": False,
        "confirmed": False,
        "execution_effective": False,
        "execution_id": execution_id,
        "execution_isolated": False,
        "execution_isolation_confirmed": False,
        "native_session_confirmed": False,
        "model_requested": model,
        "effective_model": None,
        "model_confirmed": False,
        "status": "not_requested" if not persist else "pending",
        "central_history_is_canonical": True,
        "native_history_is_mirror_only": True,
        "simulation": bool(args.dry_run),
        "filesystem_scope": {
            "project_root": str(root),
            "additional_directories": [str(item) for item in granted],
            "home_scope_opt_in": bool(args.allow_home),
        },
    }

    temporary = Path(tempfile.mkdtemp(prefix="multiagent-native-"))
    native_output_path = temporary / "codex-last-message.txt" if route == "codex" else None
    try:
        # Rotas que recebem um caminho, em vez do conteúdo pelo stdin, leem uma
        # cópia imutável dentro de um diretório temporário concedido por chamada.
        scoped_prompt_path = temporary / "instructions.md"
        scoped_prompt_path.write_text(prompt, encoding="utf-8")
        scoped_prompt_path.chmod(0o400)
        invocation_dirs = [*granted, temporary.resolve()]
        if persist:
            if route in {"claude", "gemini"}:
                native_session_id = correlation_id
            elif route == "cursor":
                native_session_id = correlation_id if args.dry_run else cursor_chat(binary)
                metadata["session_id"] = native_session_id

        command, stdin, env = build_invocation(
            resolved["seat"],
            route,
            binary,
            root,
            scoped_prompt_path,
            prompt,
            model,
            effort,
            output["policy"],
            persist_native_session=persist,
            native_session_id=native_session_id,
            native_session_label=native_session_label,
            native_output_path=native_output_path,
            additional_dirs=invocation_dirs,
        )
        metadata["argv_sha256"] = hashlib.sha256(
            provenance.canonical_json(command)
        ).hexdigest()
        metadata["input_sha256"] = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

        if args.dry_run:
            displayed_command = list(command)
            if route == "gemini" and "--prompt" in displayed_command:
                displayed_command[displayed_command.index("--prompt") + 1] = "<PROMPT_REDACTED>"
            metadata["status"] = "simulated"
            write_metadata(args.metadata_file, metadata)
            print(
                json.dumps(
                    {
                        "participant": args.participant,
                        "seat": resolved["seat"],
                        "route": route,
                        "provider": resolved.get("provider"),
                        "model": model or "padrão do CLI",
                        "effort": effort or "padrão do CLI",
                        "context_window_tokens": resolved.get("context_window_tokens"),
                        "output_policy": output["policy"],
                        "output_control": output["control"],
                        "max_output_tokens_flag": output["explicit_max_flag"],
                        "force_fill": output["force_fill"],
                        "artificial_global_cap": output["artificial_global_cap"],
                        "cwd": str(root),
                        "command": displayed_command,
                        "stdin": stdin is not None,
                        "filesystem_access": "full_tools_with_explicit_scopes",
                        "directory_scope": {
                            "project_root": str(root),
                            "additional_directories": [str(item) for item in granted],
                            "home_scope_opt_in": bool(args.allow_home),
                        },
                        "can_read": True,
                        "can_create": True,
                        "can_modify": True,
                        "can_delete": True,
                        "auto_approve_local_tools": True,
                        "persist_native_session": persist,
                        "native_session": metadata,
                        "simulation": True,
                        "verdict": None,
                        "evidence_status": "non-probative",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        process = subprocess.Popen(
            command,
            cwd=root,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if stdin is not None else None,
            start_new_session=True,
        )
        try:
            stdout, stderr = process.communicate(input=stdin, timeout=args.timeout)
            returncode = process.returncode
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
            stderr = (
                f"{stderr.rstrip()}\nTempo limite excedido.\n"
                "MULTIAGENT_PROCESS_GROUP_KILLED=1\n"
            )
            returncode = 124

        rendered_stdout = stdout
        observed_model, structured_render, model_candidates = structured_observation(stdout, model)
        if structured_render:
            rendered_stdout = structured_render
        if native_output_path and native_output_path.is_file():
            rendered_stdout = native_output_path.read_text(encoding="utf-8")
        metadata["effective_model"] = observed_model
        metadata["model_confirmed"] = bool(observed_model)
        metadata["model_confirmation_source"] = (
            "cli_structured_output" if observed_model else "unconfirmed"
        )
        metadata["models_observed"] = model_candidates
        if returncode == 0 and model_candidates and model and observed_model is None:
            stderr = (
                f"{stderr.rstrip()}\nModelo efetivo divergente do solicitado; "
                "substituição silenciosa rejeitada.\n"
            )
            returncode = 65
        metadata["output_sha256"] = hashlib.sha256(
            rendered_stdout.encode("utf-8")
        ).hexdigest()
        if persist and returncode == 0:
            metadata["effective"] = True
            metadata["execution_effective"] = True
            metadata["execution_isolated"] = True
            metadata["execution_isolation_confirmed"] = True
            if route == "codex":
                native_session_id = structured_session_observation(stdout, route)
            elif route == "claude":
                native_session_id = structured_session_observation(stdout, route)
                values = json_objects(stdout)
                if values:
                    result = recursive_value(values[0], ("result",))
                    if result is not None:
                        rendered_stdout = result
            elif route == "gemini":
                native_session_id = structured_session_observation(stdout, route)
            elif route == "opencode" and native_session_label:
                native_session_id = opencode_session(binary, native_session_label)

            metadata["session_id"] = native_session_id
            metadata["confirmed"] = bool(native_session_id)
            metadata["native_session_confirmed"] = bool(native_session_id)
            metadata["status"] = (
                "confirmed" if native_session_id else "unverifiable_by_design"
            )
        elif returncode == 0:
            metadata["execution_effective"] = True
            metadata["execution_isolated"] = True
            metadata["execution_isolation_confirmed"] = True
        elif persist:
            metadata["status"] = "failed"
        write_metadata(args.metadata_file, metadata)

        if rendered_stdout:
            sys.stdout.write(rendered_stdout)
            if not rendered_stdout.endswith("\n"):
                sys.stdout.write("\n")
        if stderr:
            sys.stderr.write(stderr)
        return returncode
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument(
        "--manifest",
        default=None,
        help="Manifesto canônico de seats, routes e política",
    )
    subparsers = result.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Listar CLIs e versões")
    doctor.add_argument("--deep", action="store_true", help="Sondar autenticação quando possível")

    invoke = subparsers.add_parser("invoke", help="Invocar uma cadeira com acesso integral a arquivos")
    invoke.add_argument("--participant", required=True)
    invoke.add_argument("--root", required=True)
    invoke.add_argument("--prompt-file", required=True)
    invoke.add_argument(
        "--add-dir",
        action="append",
        default=[],
        help="Diretório adicional explicitamente concedido; pode ser repetido",
    )
    invoke.add_argument(
        "--allow-home",
        action="store_true",
        help="Conceder a pasta pessoal inteira de forma explícita e auditável",
    )
    invoke.add_argument("--model")
    invoke.add_argument("--effort")
    invoke.add_argument("--output-policy", choices=OUTPUT_POLICIES)
    invoke.add_argument("--timeout", type=timeout_value, default=1800)
    invoke.add_argument(
        "--persist-native-session",
        action="store_true",
        help="Criar também um espelho recuperável na CLI nativa, sem substituir o ledger central",
    )
    invoke.add_argument("--native-session-correlation-id")
    invoke.add_argument("--metadata-file")
    invoke.add_argument("--dry-run", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        manifest = load_manifest(args.manifest)
        if args.command == "doctor":
            return run_doctor(manifest, args.deep)
        return run_invoke(args, manifest)
    except subprocess.TimeoutExpired as exc:
        print(f"Tempo limite excedido: {exc}", file=sys.stderr)
        return 124
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
