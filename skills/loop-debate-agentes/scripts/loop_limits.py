#!/usr/bin/env python3
"""Valida os limites persistidos do loop de versões canônicas."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_VERSIONS = 6
MAX_VERSIONS = 20


def _durable_report(config: dict[str, Any]) -> dict[str, Any]:
    path = Path(__file__).with_name("durable_run.py")
    spec = importlib.util.spec_from_file_location("multiagent_durable_run", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("não foi possível carregar durable_run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_durable_config(config)


def _integer(value: Any, field: str, errors: list[str]) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        errors.append(f"{field} deve ser inteiro")
        return None
    return value


def _attempts(config: dict[str, Any], errors: list[str], prefix: str = "") -> int:
    improvement = config.get("ciclo_de_melhoria") or {}
    loop = config.get("loop") or {}
    if not isinstance(improvement, dict):
        errors.append(f"{prefix}ciclo_de_melhoria deve ser objeto")
        improvement = {}
    if not isinstance(loop, dict):
        errors.append(f"{prefix}loop deve ser objeto")
        loop = {}

    first = _integer(improvement.get("tentativas"), f"{prefix}ciclo_de_melhoria.tentativas", errors)
    second = _integer(loop.get("tentativas"), f"{prefix}loop.tentativas", errors)
    if first is not None and second is not None and first != second:
        errors.append(f"{prefix}os espelhos de tentativas divergem: {first} != {second}")
    effective = first if first is not None else second
    if effective is None:
        effective = DEFAULT_VERSIONS
    if not 1 <= effective <= MAX_VERSIONS:
        errors.append(f"{prefix}tentativas/versões deve estar entre 1 e {MAX_VERSIONS}")
    return effective


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {"valid": False, "errors": ["configuração deve ser objeto JSON"]}

    errors: list[str] = []
    effective = _attempts(config, errors)
    item_limits: dict[str, int] = {}
    package = config.get("pacote") or {}
    items = package.get("itens") or [] if isinstance(package, dict) else []
    if items and not isinstance(items, list):
        errors.append("pacote.itens deve ser lista")
        items = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"pacote.itens[{index}] deve ser objeto")
            continue
        artifact_id = item.get("artefato_id") or f"item-{index + 1}"
        overrides = item.get("overrides") or {}
        if not isinstance(overrides, dict):
            errors.append(f"artefato {artifact_id}: overrides deve ser objeto")
            continue
        if "loop" in overrides or "ciclo_de_melhoria" in overrides:
            item_limits[str(artifact_id)] = _attempts(
                overrides, errors, f"artefato {artifact_id}: "
            )
        else:
            item_limits[str(artifact_id)] = effective

    durable = _durable_report(config)
    errors.extend(durable["errors"])

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": durable["warnings"],
        "tentativas_efetivas": effective,
        "versoes_maximas_motor": MAX_VERSIONS,
        "limites_por_artefato": item_limits,
        "execucao_duravel": {
            "ativa": durable["active"],
            "perfil": durable["profile"],
            "max_segundos": durable["max_elapsed_seconds"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("validate-config",))
    parser.add_argument("config", type=Path)
    args = parser.parse_args()

    try:
        payload = json.loads(args.config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False))
        return 2

    report = validate_config(payload)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
