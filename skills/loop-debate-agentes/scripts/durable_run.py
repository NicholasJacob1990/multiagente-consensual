#!/usr/bin/env python3
"""Contrato e checkpoints atômicos para execuções multiagente duráveis."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


CONTRACT = "durable_execution_v1"
PROFILE = "durable_5d_v1"
CHECKPOINT_SCHEMA = "durable_checkpoint_v1"
MAX_ELAPSED_SECONDS = 5 * 24 * 60 * 60
MAX_CALL_SECONDS = 60 * 60
MAX_IDEMPOTENT_EVENTS = 100_000
EVENT_ID = re.compile(r"^[A-Za-z0-9._:-]{1,256}$")
DEFAULT_CHECKPOINT_BOUNDARIES = (
    "chamada",
    "rodada",
    "ciclo",
    "versao",
    "no",
    "onda",
    "join",
)
TERMINAL_STATES = {
    "concluido",
    "cancelado",
    "falhou",
    "limite_operacional",
}
CHECKPOINT_STATES = {
    "validando",
    "executando",
    "aguardando",
    "pausado",
    "revisando",
    "auditando",
    "consolidando",
    "concluido",
    "cancelado",
    "falhou",
}


def _integer(value: Any, field: str, errors: list[str]) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{field} deve ser inteiro")
        return None
    return value


def _number_or_null(value: Any, field: str, errors: list[str]) -> None:
    if value is None:
        return
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or value <= 0
    ):
        errors.append(f"{field} deve ser número positivo ou null")


def _durable_block(config: dict[str, Any]) -> dict[str, Any] | None:
    block = config.get("execucao_duravel")
    return block if isinstance(block, dict) else None


def validate_durable_config(config: dict[str, Any]) -> dict[str, Any]:
    """Valida o overlay durável sem alterar runs comuns ou legados."""

    errors: list[str] = []
    warnings: list[str] = []
    raw = config.get("execucao_duravel")
    if raw is None:
        return {
            "valid": True,
            "active": False,
            "profile": "standard",
            "max_elapsed_seconds": None,
            "errors": [],
            "warnings": [],
        }
    if not isinstance(raw, dict):
        return {
            "valid": False,
            "active": False,
            "profile": None,
            "max_elapsed_seconds": None,
            "errors": ["execucao_duravel deve ser objeto"],
            "warnings": [],
        }

    active = raw.get("ativa", False)
    if not isinstance(active, bool):
        errors.append("execucao_duravel.ativa deve ser booleano")
        active = False
    if not active:
        return {
            "valid": not errors,
            "active": False,
            "profile": "standard",
            "max_elapsed_seconds": None,
            "errors": errors,
            "warnings": warnings,
        }

    if raw.get("contrato") != CONTRACT:
        errors.append(f"execucao_duravel.contrato deve ser {CONTRACT}")
    if raw.get("perfil") != PROFILE:
        errors.append(f"execucao_duravel.perfil deve ser {PROFILE}")
    if raw.get("relogio") != "tempo_corrido":
        errors.append("execucao_duravel.relogio deve ser tempo_corrido")
    if raw.get("offline_conta_no_prazo") is not True:
        errors.append("tempo corrido exige offline_conta_no_prazo=true")
    if raw.get("retomar_apos_reinicio") is not True:
        errors.append("execução durável exige retomar_apos_reinicio=true")
    if raw.get("gravacao_checkpoint") != "atomica":
        errors.append("execucao_duravel.gravacao_checkpoint deve ser atomica")
    if raw.get("idempotencia") != "event_id+input_sha256":
        errors.append("execucao_duravel.idempotencia deve ser event_id+input_sha256")

    maximum = _integer(raw.get("max_segundos"), "execucao_duravel.max_segundos", errors)
    if maximum is None:
        errors.append("execucao_duravel.max_segundos é obrigatório quando ativa=true")
    elif not 1 <= maximum <= MAX_ELAPSED_SECONDS:
        errors.append(
            f"execucao_duravel.max_segundos deve ficar entre 1 e {MAX_ELAPSED_SECONDS}"
        )

    boundaries = raw.get("checkpoint_apos")
    if not isinstance(boundaries, list) or not boundaries:
        errors.append("execucao_duravel.checkpoint_apos deve ser lista não vazia")
    else:
        unknown = sorted(set(boundaries) - set(DEFAULT_CHECKPOINT_BOUNDARIES))
        if unknown:
            errors.append(f"fronteiras de checkpoint desconhecidas: {', '.join(unknown)}")
        if "chamada" not in boundaries:
            errors.append("execução durável exige checkpoint após cada chamada")

    for budget_name in ("orcamento_diario", "orcamento_total"):
        budget = raw.get(budget_name)
        if not isinstance(budget, dict):
            errors.append(f"execucao_duravel.{budget_name} deve ser objeto")
            continue
        calls = budget.get("max_chamadas")
        if calls is not None and (
            isinstance(calls, bool) or not isinstance(calls, int) or calls <= 0
        ):
            errors.append(
                f"execucao_duravel.{budget_name}.max_chamadas deve ser inteiro positivo ou null"
            )
        _number_or_null(
            budget.get("max_custo"),
            f"execucao_duravel.{budget_name}.max_custo",
            errors,
        )
    daily = raw.get("orcamento_diario", {})
    total = raw.get("orcamento_total", {})
    if isinstance(daily, dict) and isinstance(total, dict):
        if all(
            budget.get(key) is None
            for budget in (daily, total)
            for key in ("max_chamadas", "max_custo")
        ):
            if raw.get("orcamento_ilimitado_confirmado") is not True:
                errors.append(
                    "orçamentos integralmente nulos exigem "
                    "orcamento_ilimitado_confirmado=true"
                )
            else:
                warnings.append(
                    "execução sem limite de chamadas/custo explicitamente confirmada; "
                    "o prazo continua obrigatório"
                )

    limits = config.get("limites")
    if isinstance(limits, dict) and limits.get("max_segundos") is not None:
        legacy = _integer(limits.get("max_segundos"), "limites.max_segundos", errors)
        if maximum is not None and legacy is not None and legacy != maximum:
            errors.append("limites.max_segundos deve espelhar execucao_duravel.max_segundos")

    operational = config.get("limites_operacionais")
    if isinstance(operational, dict) and operational.get("tempo_maximo_minutos") is not None:
        minutes = _integer(
            operational.get("tempo_maximo_minutos"),
            "limites_operacionais.tempo_maximo_minutos",
            errors,
        )
        if maximum is not None and minutes is not None and minutes * 60 != maximum:
            errors.append(
                "limites_operacionais.tempo_maximo_minutos deve espelhar "
                "execucao_duravel.max_segundos"
            )

    timeout = config.get("timeout_invocacao")
    if isinstance(timeout, dict):
        for key in ("padrao_segundos", "maximo_excepcional_segundos"):
            value = _integer(timeout.get(key), f"timeout_invocacao.{key}", errors)
            if value is not None and not 1 <= value <= MAX_CALL_SECONDS:
                errors.append(f"timeout_invocacao.{key} não pode exceder {MAX_CALL_SECONDS}")

    return {
        "valid": not errors,
        "active": True,
        "profile": raw.get("perfil"),
        "max_elapsed_seconds": maximum,
        "errors": errors,
        "warnings": warnings,
    }


def _parse_instant(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    instant = datetime.fromisoformat(normalized)
    if instant.tzinfo is None:
        raise ValueError("o instante deve conter fuso horário")
    return instant.astimezone(timezone.utc)


def _format_instant(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_sha256(value: str) -> bool:
    return len(value) == 64 and all(char in "0123456789abcdef" for char in value.lower())


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def _checkpoint_lock(path: Path):
    """Serializa coordenadores concorrentes sem depender de estado em memória."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f"{path.name}.lock")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_checkpoint(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != CHECKPOINT_SCHEMA:
        raise ValueError(f"checkpoint incompatível; esperado {CHECKPOINT_SCHEMA}")
    return payload


def _timing(payload: dict[str, Any], now: datetime) -> tuple[int, int, bool]:
    started = _parse_instant(payload["iniciado_em"])
    deadline = _parse_instant(payload["deadline_em"])
    elapsed = max(0, int((now - started).total_seconds()))
    remaining = max(0, int((deadline - now).total_seconds()))
    return elapsed, remaining, now >= deadline


def _status_payload(payload: dict[str, Any], now: datetime) -> dict[str, Any]:
    elapsed, remaining, expired = _timing(payload, now)
    state = payload.get("estado")
    return {
        "schema": payload.get("schema"),
        "run_id": payload.get("run_id"),
        "perfil": payload.get("perfil"),
        "estado": "limite_operacional" if expired and state not in TERMINAL_STATES else state,
        "expirado": expired,
        "retomavel": not expired and state not in TERMINAL_STATES,
        "iniciado_em": payload.get("iniciado_em"),
        "deadline_em": payload.get("deadline_em"),
        "atualizado_em": payload.get("atualizado_em"),
        "segundos_decorridos": elapsed,
        "segundos_restantes": remaining,
        "sequencia": payload.get("sequencia", 0),
        "retomadas": payload.get("retomadas", 0),
        "ultimo_checkpoint": payload.get("ultimo_checkpoint"),
        "razao_parada": "deadline" if expired and state not in TERMINAL_STATES else payload.get("razao_parada"),
    }


def initialize(config_path: Path, checkpoint_path: Path, now: datetime) -> dict[str, Any]:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(config, dict):
        raise ValueError("configuração deve ser objeto JSON")
    report = validate_durable_config(config)
    if not report["valid"]:
        raise ValueError("; ".join(report["errors"]))
    if not report["active"]:
        raise ValueError("execucao_duravel não está ativa")

    run_id = str(config.get("run_id") or config.get("id") or config_path.stem)
    with _checkpoint_lock(checkpoint_path):
        if checkpoint_path.exists():
            existing = _load_checkpoint(checkpoint_path)
            if existing.get("run_id") != run_id or existing.get("config_sha256") != _sha256_file(config_path):
                raise ValueError("checkpoint existente pertence a outra configuração")
            return _status_payload(existing, now)

        maximum = int(report["max_elapsed_seconds"])
        durable = _durable_block(config) or {}
        total_calls = (durable.get("orcamento_total") or {}).get("max_chamadas")
        maximum_events = min(
            total_calls if isinstance(total_calls, int) and not isinstance(total_calls, bool) else MAX_IDEMPOTENT_EVENTS,
            MAX_IDEMPOTENT_EVENTS,
        )
        payload = {
            "schema": CHECKPOINT_SCHEMA,
            "contrato": CONTRACT,
            "perfil": PROFILE,
            "run_id": run_id,
            "config_sha256": _sha256_file(config_path),
            "iniciado_em": _format_instant(now),
            "deadline_em": _format_instant(now + timedelta(seconds=maximum)),
            "atualizado_em": _format_instant(now),
            "offline_conta_no_prazo": True,
            "max_segundos": maximum,
            "estado": "validando",
            "estado_anterior": None,
            "razao_parada": None,
            "sequencia": 0,
            "retomadas": 0,
            "checkpoint_apos": durable["checkpoint_apos"],
            "ultimo_checkpoint": None,
            "eventos_idempotentes": {},
            "eventos_maximos": maximum_events,
        }
        _atomic_write(checkpoint_path, payload)
        return _status_payload(payload, now)


def checkpoint(
    path: Path,
    *,
    boundary: str,
    event_id: str,
    input_sha256: str,
    output_sha256: str | None,
    state: str,
    now: datetime,
) -> dict[str, Any]:
    with _checkpoint_lock(path):
        payload = _load_checkpoint(path)
        if boundary not in payload.get("checkpoint_apos", []):
            raise ValueError(f"fronteira {boundary} não foi autorizada no run")
        if not isinstance(event_id, str) or not EVENT_ID.fullmatch(event_id):
            raise ValueError("event_id deve possuir 1 a 256 caracteres seguros")
        if not _valid_sha256(input_sha256):
            raise ValueError("input_sha256 inválido")
        if output_sha256 is not None and not _valid_sha256(output_sha256):
            raise ValueError("output_sha256 inválido")
        if state not in CHECKPOINT_STATES:
            if state == "aprovado":
                raise ValueError(
                    "estado aprovado pertence ao gate externo de consenso/auditoria; "
                    "o checkpoint durável só registra estados operacionais"
                )
            raise ValueError(f"estado de checkpoint desconhecido: {state}")

        events = payload.setdefault("eventos_idempotentes", {})
        previous = events.get(event_id)
        if previous is not None:
            if previous.get("input_sha256") != input_sha256:
                raise ValueError("event_id reutilizado com input_sha256 diferente")
            if previous.get("output_sha256") != output_sha256:
                raise ValueError("event_id reutilizado com output_sha256 diferente")
            if previous.get("estado") != state:
                raise ValueError("event_id reutilizado com estado diferente")
            status = _status_payload(payload, now)
            status["duplicado"] = True
            return status
        maximum_events = payload.get("eventos_maximos", MAX_IDEMPOTENT_EVENTS)
        if (
            isinstance(maximum_events, bool)
            or not isinstance(maximum_events, int)
            or maximum_events < 1
            or len(events) >= maximum_events
        ):
            raise ValueError("limite de eventos idempotentes do run atingido ou inválido")

        _elapsed, _remaining, expired = _timing(payload, now)
        if expired:
            payload["estado_anterior"] = payload.get("estado")
            payload["estado"] = "limite_operacional"
            payload["razao_parada"] = "deadline"
            payload["atualizado_em"] = _format_instant(now)
            _atomic_write(path, payload)
            return _status_payload(payload, now)
        if payload.get("estado") in TERMINAL_STATES:
            raise ValueError(f"run terminal não aceita checkpoint: {payload.get('estado')}")

        payload["estado_anterior"] = payload.get("estado")
        payload["estado"] = state
        payload["sequencia"] = int(payload.get("sequencia", 0)) + 1
        payload["atualizado_em"] = _format_instant(now)
        payload["ultimo_checkpoint"] = {
            "fronteira": boundary,
            "event_id": event_id,
            "input_sha256": input_sha256,
            "output_sha256": output_sha256,
            "estado": state,
            "instante": _format_instant(now),
        }
        events[event_id] = {
            "input_sha256": input_sha256,
            "output_sha256": output_sha256,
            "estado": state,
            "sequencia": payload["sequencia"],
        }
        _atomic_write(path, payload)
        status = _status_payload(payload, now)
        status["duplicado"] = False
        return status


def resume(path: Path, now: datetime) -> dict[str, Any]:
    with _checkpoint_lock(path):
        payload = _load_checkpoint(path)
        _elapsed, _remaining, expired = _timing(payload, now)
        if expired:
            if payload.get("estado") not in TERMINAL_STATES:
                payload["estado_anterior"] = payload.get("estado")
                payload["estado"] = "limite_operacional"
                payload["razao_parada"] = "deadline"
                payload["atualizado_em"] = _format_instant(now)
                _atomic_write(path, payload)
            return _status_payload(payload, now)
        if payload.get("estado") in TERMINAL_STATES:
            raise ValueError(f"run terminal não pode ser retomado: {payload.get('estado')}")
        payload["retomadas"] = int(payload.get("retomadas", 0)) + 1
        payload["atualizado_em"] = _format_instant(now)
        _atomic_write(path, payload)
        return _status_payload(payload, now)


def emit(payload: Any) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("config", type=Path)

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("config", type=Path)
    init_parser.add_argument("checkpoint", type=Path)
    init_parser.add_argument("--now")
    init_parser.add_argument("--allow-test-clock", action="store_true")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("checkpoint", type=Path)
    status_parser.add_argument("--now")
    status_parser.add_argument("--allow-test-clock", action="store_true")

    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("checkpoint", type=Path)
    resume_parser.add_argument("--now")
    resume_parser.add_argument("--allow-test-clock", action="store_true")

    checkpoint_parser = subparsers.add_parser("checkpoint")
    checkpoint_parser.add_argument("checkpoint", type=Path)
    checkpoint_parser.add_argument("--boundary", choices=DEFAULT_CHECKPOINT_BOUNDARIES, required=True)
    checkpoint_parser.add_argument("--event-id", required=True)
    checkpoint_parser.add_argument("--input-sha256", required=True)
    checkpoint_parser.add_argument("--output-sha256")
    checkpoint_parser.add_argument("--state", required=True)
    checkpoint_parser.add_argument("--now")
    checkpoint_parser.add_argument("--allow-test-clock", action="store_true")

    args = parser.parse_args()
    try:
        if args.command == "validate":
            config = json.loads(args.config.read_text(encoding="utf-8"))
            report = validate_durable_config(config)
            emit(report)
            return 0 if report["valid"] else 2
        if args.now and not args.allow_test_clock:
            raise ValueError("--now exige --allow-test-clock e é reservado a testes")
        now = _parse_instant(args.now)
        if args.command == "init":
            emit(initialize(args.config, args.checkpoint, now))
            return 0
        if args.command == "status":
            emit(_status_payload(_load_checkpoint(args.checkpoint), now))
            return 0
        if args.command == "resume":
            result = resume(args.checkpoint, now)
            emit(result)
            return 0 if result["retomavel"] else 3
        result = checkpoint(
            args.checkpoint,
            boundary=args.boundary,
            event_id=args.event_id,
            input_sha256=args.input_sha256,
            output_sha256=args.output_sha256,
            state=args.state,
            now=now,
        )
        emit(result)
        return 0 if result["retomavel"] or result["estado"] == "concluido" else 3
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        emit({"error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
