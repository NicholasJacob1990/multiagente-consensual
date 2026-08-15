#!/usr/bin/env python3
"""Valida e publica versões canônicas com CAS, lock, fsync e recibo atestado."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import stat
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
if str(PLUGIN_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
import provenance  # noqa: E402


MODES = {"parecer_apenas", "publicar_candidata", "publicar_canonico"}
POLICIES = {"redator_original", "consolidador_designado", "publicacao_compartilhada"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
PUBLICATION_CONTRACT = "publicacao_canonica_v1"
PUBLICATION_LEDGER_CONTRACT = "publication_ledger_v1"


def _identity_id(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if not isinstance(value, dict):
        return None
    for field in ("id", "agente", "cadeira"):
        item = value.get(field)
        if isinstance(item, str) and item.strip():
            return item.strip()
    return None


def _authorized(config: dict[str, Any], errors: list[str]) -> list[str]:
    contribution = config.get("contribuicao_revisor") or {}
    consolidation = config.get("consolidacao_iterativa") or {}
    raw = contribution.get("publicadores_autorizados") or consolidation.get(
        "publicadores_autorizados"
    ) or []
    if not isinstance(raw, list):
        errors.append("publicadores_autorizados deve ser lista")
        return []
    result: list[str] = []
    for index, item in enumerate(raw):
        identity = _identity_id(item)
        if not identity:
            errors.append(f"publicadores_autorizados[{index}] não possui identidade")
        elif identity in result:
            errors.append(f"publicador autorizado duplicado: {identity}")
        else:
            result.append(identity)
    return result


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {"valid": False, "errors": ["configuração deve ser objeto JSON"]}
    errors: list[str] = []
    contribution = config.get("contribuicao_revisor") or {}
    consolidation = config.get("consolidacao_iterativa") or {}
    if not isinstance(contribution, dict):
        errors.append("contribuicao_revisor deve ser objeto")
        contribution = {}
    if not isinstance(consolidation, dict):
        errors.append("consolidacao_iterativa deve ser objeto")
        consolidation = {}

    mode = contribution.get("modo_publicacao", "parecer_apenas")
    policy = consolidation.get("politica", "redator_original")
    if mode not in MODES:
        errors.append(f"modo_publicacao inválido: {mode}")
    if policy not in POLICIES:
        errors.append(f"politica de consolidação inválida: {policy}")

    authorized = _authorized(config, errors)
    turn = _identity_id(consolidation.get("publicador_da_proxima_versao"))
    if mode == "publicar_canonico":
        if policy != "publicacao_compartilhada":
            errors.append("publicar_canonico exige publicacao_compartilhada")
        if not authorized:
            errors.append("publicar_canonico exige publicadores_autorizados")
        if consolidation.get("controle_concorrencia") != "base_sha256":
            errors.append("publicar_canonico exige controle_concorrencia = base_sha256")
        if consolidation.get("gravacao") != "atomica":
            errors.append("publicar_canonico exige gravacao = atomica")
        if turn and turn not in authorized:
            errors.append("publicador_da_proxima_versao não está autorizado")
        if contribution.get("publicacao_direta_sem_reincorporacao") is not True:
            errors.append("publicar_canonico exige publicacao_direta_sem_reincorporacao = true")
    elif policy == "publicacao_compartilhada":
        errors.append("publicacao_compartilhada exige modo_publicacao = publicar_canonico")

    if contribution.get("substituicao_automatica") is True:
        errors.append("substituicao_automatica deve permanecer false")

    return {
        "valid": not errors,
        "errors": errors,
        "modo_publicacao": mode,
        "politica": policy,
        "publicadores_autorizados": authorized,
        "publicador_da_proxima_versao": turn,
    }


def _relative_path(value: Any, field: str, errors: list[str]) -> str | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{field} é obrigatório")
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value in {".", ""}:
        errors.append(f"{field} deve ser relativo e seguro")
        return None
    return value


def _scoped_file(root: Path, relative: str, *, must_exist: bool) -> Path:
    parts = PurePosixPath(relative).parts
    if not parts:
        raise ValueError("caminho relativo vazio")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(root, directory_flags)
    try:
        for part in parts[:-1]:
            next_descriptor = os.open(part, directory_flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        if must_exist:
            file_descriptor = os.open(parts[-1], file_flags, dir_fd=descriptor)
            try:
                opened = os.fstat(file_descriptor)
                if not stat.S_ISREG(opened.st_mode):
                    raise ValueError(f"arquivo regular inexistente: {relative}")
            finally:
                os.close(file_descriptor)
        target = root.joinpath(*parts)
        provenance.require_scoped_path(target, roots=[root], must_exist=must_exist)
        return target
    except OSError as exc:
        raise ValueError(f"caminho inexistente, inseguro ou symlink: {relative}") from exc
    finally:
        os.close(descriptor)


def validate_receipt(
    config: dict[str, Any],
    receipt: dict[str, Any],
    *,
    root: str | Path | None = None,
) -> dict[str, Any]:
    report = validate_config(config)
    errors = list(report["errors"])
    if report.get("modo_publicacao") != "publicar_canonico":
        errors.append("recibo canônico exige modo publicar_canonico")
    if not isinstance(receipt, dict):
        errors.append("recibo deve ser objeto JSON")
        receipt = {}
    if receipt.get("schema") != PUBLICATION_CONTRACT:
        errors.append(f"recibo deve usar schema {PUBLICATION_CONTRACT}")

    author = _identity_id(receipt.get("autor"))
    turn = report.get("publicador_da_proxima_versao")
    if not author or author not in report.get("publicadores_autorizados", []):
        errors.append("autor do recibo não está autorizado")
    if turn and author != turn:
        errors.append("autor do recibo não detém o turno de publicação")

    base = receipt.get("base_sha256")
    current = receipt.get("canonico_corrente_sha256")
    digest = receipt.get("sha256")
    if not isinstance(base, str) or not SHA256.fullmatch(base):
        errors.append("base_sha256 inválido")
    if not isinstance(current, str) or not SHA256.fullmatch(current):
        errors.append("canonico_corrente_sha256 inválido")
    if base != current:
        errors.append("base_sha256 não corresponde ao canônico corrente declarado")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        errors.append("sha256 da nova versão inválido")
    if digest == base:
        errors.append("nova versão deve possuir hash diferente da base")

    current_version = receipt.get("versao_corrente")
    new_version = receipt.get("nova_versao")
    limit = receipt.get("versoes_maximas", 20)
    if any(isinstance(v, bool) or not isinstance(v, int) for v in (current_version, new_version, limit)):
        errors.append("versões e limite devem ser inteiros")
    elif new_version != current_version + 1:
        errors.append("nova_versao deve ser sucessora da versão corrente")
    elif not 1 <= new_version <= min(limit, 20):
        errors.append("nova versão excede o limite efetivo")

    canonical_relative = _relative_path(receipt.get("caminho_canonico"), "caminho_canonico", errors)
    candidate_relative = _relative_path(receipt.get("caminho_candidato"), "caminho_candidato", errors)
    key = receipt.get("chave_idempotencia")
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{16,256}", key):
        errors.append("chave_idempotencia inválida")

    resolved_root: Path | None = None
    canonical_path: Path | None = None
    candidate_path: Path | None = None
    if root is not None:
        try:
            resolved_root = provenance.canonical_directory(root)
            if canonical_relative:
                canonical_path = _scoped_file(resolved_root, canonical_relative, must_exist=True)
                actual_current = provenance.hash_file(canonical_path, roots=[resolved_root])["sha256"]
                if actual_current != base or actual_current != current:
                    errors.append("hash do canônico real diverge da base CAS")
            if candidate_relative:
                candidate_path = _scoped_file(resolved_root, candidate_relative, must_exist=True)
                actual_candidate = provenance.hash_file(candidate_path, roots=[resolved_root])["sha256"]
                if actual_candidate != digest:
                    errors.append("hash da candidata real diverge do recibo")
        except (OSError, ValueError) as exc:
            errors.append(str(exc))
    else:
        errors.append("validação de publicação exige raiz explícita")

    return {
        **report,
        "valid": not errors,
        "errors": errors,
        "autor": author,
        "root": str(resolved_root) if resolved_root else None,
        "canonical_path": str(canonical_path) if canonical_path else None,
        "candidate_path": str(candidate_path) if candidate_path else None,
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
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
        temporary.unlink(missing_ok=True)


def _load_ledger(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema": PUBLICATION_LEDGER_CONTRACT, "publicacoes": {}}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != PUBLICATION_LEDGER_CONTRACT:
        raise ValueError("ledger de publicação incompatível")
    if not isinstance(payload.get("publicacoes"), dict):
        raise ValueError("ledger de publicação inválido")
    return payload


def _scoped_ledger_path(root: Path, raw: str | Path) -> Path:
    requested = Path(raw).expanduser().absolute()
    if requested.is_symlink():
        raise ValueError(f"ledger de publicação não pode ser symlink: {requested}")
    parent = requested.parent.resolve(strict=True)
    provenance.require_scoped_path(parent, roots=[root])
    return parent / requested.name


def _publication_secret(secret: bytes | None) -> bytes:
    resolved = provenance.load_host_secret() if secret is None else secret
    if not isinstance(resolved, bytes) or len(resolved) < 32:
        raise ValueError("segredo HMAC de publicação deve possuir ao menos 32 bytes")
    return resolved


@contextmanager
def _exclusive_lock(path: Path):
    """Mantém um lock advisory exclusivo e com permissões locais restritas."""

    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _replay_fields(receipt: dict[str, Any], canonical_relative: str) -> dict[str, Any]:
    return {
        "autor": _identity_id(receipt.get("autor")),
        "caminho_canonico": canonical_relative,
        "caminho_candidato": receipt.get("caminho_candidato"),
        "base_sha256": receipt.get("base_sha256"),
        "sha256": receipt.get("sha256"),
        "nova_versao": receipt.get("nova_versao"),
    }


def _install_candidate(
    candidate: Path,
    canonical: Path,
    resolved_root: Path,
    expected_sha256: str,
) -> dict[str, Any]:
    candidate_bytes, candidate_observed = provenance.read_file_bytes(
        candidate, roots=[resolved_root]
    )
    if candidate_observed["sha256"] != expected_sha256:
        raise ValueError("candidata mudou após validação")
    descriptor, raw = tempfile.mkstemp(prefix=f".{canonical.name}.stage.", dir=canonical.parent)
    staged = Path(raw)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(candidate_bytes)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(staged, 0o600)
        if provenance.hash_file(staged)["sha256"] != expected_sha256:
            raise ValueError("hash do estágio diverge da candidata")
        os.replace(staged, canonical)
        directory_fd = os.open(canonical.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        staged.unlink(missing_ok=True)
    final = provenance.hash_file(canonical, roots=[resolved_root])
    if final["sha256"] != expected_sha256:
        raise ValueError("publicação atômica terminou com hash inesperado")
    return final


def _commit_receipt(
    fields: dict[str, Any],
    final: dict[str, Any],
    key: str,
    secret: bytes,
) -> dict[str, Any]:
    unsigned = {
        "schema": "publication_receipt_v1",
        "publicado": True,
        "autor": fields["autor"],
        "caminho_canonico": fields["caminho_canonico"],
        "base_sha256": fields["base_sha256"],
        "sha256": final["sha256"],
        "bytes": final["bytes"],
        "nova_versao": fields["nova_versao"],
        "chave_idempotencia": key,
        "publicado_em": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    return provenance.sign_receipt(unsigned, secret)


def _publish_with_canonical_lock(
    config: dict[str, Any],
    receipt: dict[str, Any],
    *,
    root: str | Path,
    ledger_path: str | Path,
    secret: bytes | None = None,
) -> dict[str, Any]:
    resolved_root = provenance.canonical_directory(root)
    ledger = _scoped_ledger_path(resolved_root, ledger_path)
    secret = _publication_secret(secret)
    canonical_relative = receipt.get("caminho_canonico")
    if not isinstance(canonical_relative, str):
        raise ValueError("caminho_canonico ausente")
    canonical = _scoped_file(resolved_root, canonical_relative, must_exist=True)
    lock_path = canonical.with_name(f".{canonical.name}.publish.lock")

    with _exclusive_lock(lock_path):
        key = receipt.get("chave_idempotencia")
        publication_ledger = _load_ledger(ledger)
        prior = publication_ledger["publicacoes"].get(key) if isinstance(key, str) else None
        fields = _replay_fields(receipt, canonical_relative)
        if prior is not None:
            if any(prior.get(field) != value for field, value in fields.items()):
                return {"valid": False, "errors": ["replay conflitante da chave de idempotência"]}
            state = prior.get("estado")
            current = provenance.hash_file(canonical, roots=[resolved_root])
            if state == "committed":
                if current["sha256"] != fields["sha256"]:
                    return {"valid": False, "errors": ["ledger committed diverge do canônico real"]}
                return {**prior["recibo"], "valid": True, "idempotent_replay": True}
            if state != "prepared":
                return {"valid": False, "errors": ["estado WAL de publicação incompatível"]}
            if current["sha256"] == fields["base_sha256"]:
                candidate = _scoped_file(
                    resolved_root, str(fields["caminho_candidato"]), must_exist=True
                )
                current = _install_candidate(
                    candidate, canonical, resolved_root, str(fields["sha256"])
                )
            elif current["sha256"] != fields["sha256"]:
                return {"valid": False, "errors": ["WAL preparado e canônico em estado inesperado"]}
            signed = _commit_receipt(
                fields, current, str(key), secret
            )
            publication_ledger["publicacoes"][key] = {
                **fields, "estado": "committed", "recibo": signed
            }
            _atomic_json(ledger, publication_ledger)
            return {**signed, "valid": True, "idempotent_replay": True, "recovered": True}

        report = validate_receipt(config, receipt, root=resolved_root)
        if not report["valid"]:
            return report

        fields["autor"] = report["autor"]
        publication_ledger["publicacoes"][key] = {**fields, "estado": "prepared"}
        _atomic_json(ledger, publication_ledger)
        final = _install_candidate(
            Path(report["candidate_path"]), canonical, resolved_root, receipt["sha256"]
        )
        signed = _commit_receipt(
            fields, final, str(key), secret
        )
        publication_ledger["publicacoes"][key] = {
            **fields, "estado": "committed", "recibo": signed
        }
        _atomic_json(ledger, publication_ledger)
        return {**signed, "valid": True, "idempotent_replay": False}


def publish(
    config: dict[str, Any],
    receipt: dict[str, Any],
    *,
    root: str | Path,
    ledger_path: str | Path,
    secret: bytes | None = None,
) -> dict[str, Any]:
    """Serializa o ledger global antes do lock específico de cada canônico.

    A ordem única ledger -> canônico evita perda de atualizações quando dois
    documentos distintos são publicados simultaneamente no mesmo ledger.
    """

    resolved_root = provenance.canonical_directory(root)
    ledger = _scoped_ledger_path(resolved_root, ledger_path)
    ledger_lock = ledger.with_name(f".{ledger.name}.global.lock")
    with _exclusive_lock(ledger_lock):
        return _publish_with_canonical_lock(
            config,
            receipt,
            root=resolved_root,
            ledger_path=ledger,
            secret=secret,
        )


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} deve conter objeto JSON")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate-config", "validate-receipt", "publish"))
    parser.add_argument("config", type=Path)
    parser.add_argument("receipt", type=Path, nargs="?")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--ledger", type=Path)
    args = parser.parse_args()
    try:
        config = _read(args.config)
        if args.command == "validate-config":
            report = validate_config(config)
        else:
            if args.receipt is None or args.root is None:
                raise ValueError(f"{args.command} exige recibo e --root explícito")
            receipt = _read(args.receipt)
            if args.command == "publish":
                if args.ledger is None:
                    raise ValueError("publish exige --ledger dentro da raiz")
                report = publish(
                    config,
                    receipt,
                    root=args.root,
                    ledger_path=args.ledger,
                )
            else:
                report = validate_receipt(config, receipt, root=args.root)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        report = {"valid": False, "errors": [str(exc)]}
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
