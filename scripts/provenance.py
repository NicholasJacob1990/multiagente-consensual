#!/usr/bin/env python3
"""Proveniência, hashes seguros e atestação HMAC para o runtime multiagente."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import json
import os
import re
import stat
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CONTRACT = "multiagent_provenance_v1"
ATTESTATION_CONTRACT = "host_hmac_v1"
NONCE_LEDGER_CONTRACT = "multiagent_nonce_ledger_v1"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
NONCE = re.compile(r"^[A-Za-z0-9._:-]{16,256}$")
DEFAULT_MANIFEST = Path("~/.agents/multiagent-manifest.json").expanduser()
PACKAGED_MANIFEST = Path(__file__).resolve().parents[1] / "assets" / "multiagent-manifest.json"
DEFAULT_SECRET_FILE = Path("~/.agents/cowork-bridge-config.json").expanduser()
DEFAULT_NONCE_LEDGER = Path("~/.agents/multiagent-state/nonces.json").expanduser()


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def valid_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256.fullmatch(value))


def load_manifest(path: str | Path | None = None) -> dict[str, Any]:
    candidates = [Path(path).expanduser()] if path else [DEFAULT_MANIFEST, PACKAGED_MANIFEST]
    selected = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
    if selected is None:
        raise ValueError("manifesto multiagente ausente")
    payload = json.loads(selected.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("manifesto multiagente deve ser objeto JSON")
    if payload.get("manifest_version") != 1 or payload.get("policy") != "strict":
        raise ValueError("manifesto multiagente incompatível")
    if not isinstance(payload.get("routes"), dict) or not isinstance(payload.get("seats"), dict):
        raise ValueError("manifesto deve declarar routes e seats")
    payload["_resolved_path"] = str(selected)
    return payload


def resolve_seat(manifest: dict[str, Any], requested: str) -> tuple[str, dict[str, Any]]:
    seats = manifest["seats"]
    canonical = requested
    if canonical not in seats:
        matches = [
            name for name, entry in seats.items()
            if requested in entry.get("aliases", [])
        ]
        if len(matches) != 1:
            raise ValueError(f"cadeira desconhecida ou ambígua: {requested}")
        canonical = matches[0]
    entry = seats[canonical]
    if not isinstance(entry, dict) or entry.get("route") not in manifest["routes"]:
        raise ValueError(f"cadeira sem rota válida: {canonical}")
    return canonical, entry


def canonical_directory(raw: str | Path, *, reject_home: bool = True) -> Path:
    expanded = Path(raw).expanduser().absolute()
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(expanded, flags)
    except OSError as exc:
        raise ValueError(f"diretório inexistente, inseguro ou symlink: {expanded}") from exc
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISDIR(opened.st_mode):
            raise ValueError(f"diretório inexistente: {expanded}")
        path = expanded.resolve(strict=True)
        current = os.stat(path)
        if (opened.st_dev, opened.st_ino) != (current.st_dev, current.st_ino):
            raise ValueError("raiz mudou durante a validação")
    finally:
        os.close(descriptor)
    if path == Path("/") or (reject_home and path == Path.home().resolve()):
        raise ValueError("a raiz do filesystem e a pasta pessoal não são escopos válidos")
    return path


def is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def require_scoped_path(
    raw: str | Path,
    *,
    roots: Iterable[Path],
    exact_files: Iterable[Path] = (),
    must_exist: bool = True,
) -> Path:
    path = Path(raw).expanduser().resolve(strict=must_exist)
    root_list = [item.resolve(strict=True) for item in roots]
    exact_list = [item.resolve(strict=True) for item in exact_files]
    if path not in exact_list and not any(is_within(path, root) for root in root_list):
        raise ValueError(f"caminho fora dos escopos concedidos: {path}")
    return path


def _secure_open(path: Path) -> tuple[int, os.stat_result]:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    opened = os.fstat(descriptor)
    if not stat.S_ISREG(opened.st_mode):
        os.close(descriptor)
        raise ValueError(f"artefato não é arquivo regular: {path}")
    current = os.lstat(path)
    if stat.S_ISLNK(current.st_mode) or (opened.st_dev, opened.st_ino) != (
        current.st_dev,
        current.st_ino,
    ):
        os.close(descriptor)
        raise ValueError(f"artefato mudou ou usa symlink: {path}")
    return descriptor, opened


def hash_file(path: str | Path, *, roots: Iterable[Path] | None = None) -> dict[str, Any]:
    original = Path(path).expanduser().absolute()
    if original.is_symlink():
        raise ValueError(f"symlink não permitido no caminho: {original}")
    target = original.resolve(strict=True)
    if roots is not None:
        target = require_scoped_path(target, roots=roots)
    descriptor, opened = _secure_open(target)
    digest = hashlib.sha256()
    with os.fdopen(descriptor, "rb", closefd=True) as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(target), "sha256": digest.hexdigest(), "bytes": opened.st_size}


def read_file_bytes(
    path: str | Path, *, roots: Iterable[Path] | None = None
) -> tuple[bytes, dict[str, Any]]:
    original = Path(path).expanduser().absolute()
    if original.is_symlink():
        raise ValueError(f"symlink não permitido no caminho: {original}")
    target = original.resolve(strict=True)
    if roots is not None:
        target = require_scoped_path(target, roots=roots)
    descriptor, opened = _secure_open(target)
    with os.fdopen(descriptor, "rb", closefd=True) as handle:
        content = handle.read()
    return content, {
        "path": str(target),
        "sha256": hashlib.sha256(content).hexdigest(),
        "bytes": opened.st_size,
    }


def _secret_from_file(path: Path) -> bytes:
    original = path.expanduser().absolute()
    if original.is_symlink():
        raise ValueError("arquivo do segredo não pode ser symlink")
    resolved = original.resolve(strict=True)
    mode = stat.S_IMODE(resolved.stat().st_mode)
    if mode & 0o077:
        raise ValueError("arquivo do segredo deve possuir permissões 0600 ou mais restritivas")
    content, _ = read_file_bytes(resolved)
    payload = json.loads(content.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("arquivo do segredo deve conter objeto JSON")
    raw = payload.get("attestation_secret") or payload.get("bridge_secret")
    if not isinstance(raw, str):
        raise ValueError("segredo de atestação ausente no arquivo do host")
    return raw.encode("utf-8")


def load_host_secret() -> bytes:
    raw = os.environ.get("MULTIAGENT_ATTESTATION_KEY")
    if raw is not None:
        secret = raw.encode("utf-8")
    else:
        configured = os.environ.get("MULTIAGENT_ATTESTATION_SECRET_FILE")
        secret = _secret_from_file(Path(configured) if configured else DEFAULT_SECRET_FILE)
    if len(secret) < 32:
        raise ValueError("segredo de atestação deve possuir ao menos 32 bytes")
    return secret


def key_id(secret: bytes) -> str:
    return hashlib.sha256(secret).hexdigest()[:16]


def _unsigned(receipt: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in receipt.items() if key != "atestacao"}


def sign_receipt(receipt: dict[str, Any], secret: bytes) -> dict[str, Any]:
    result = dict(_unsigned(receipt))
    signature = hmac.new(secret, canonical_json(result), hashlib.sha256).hexdigest()
    result["atestacao"] = {
        "contrato": ATTESTATION_CONTRACT,
        "algoritmo": "hmac-sha256",
        "key_id": key_id(secret),
        "assinatura": signature,
    }
    return result


def validate_receipt(
    receipt: dict[str, Any],
    manifest: dict[str, Any],
    secret: bytes,
    *,
    expected_artifact_sha256: str | None = None,
    require_model: bool = True,
    require_session: bool = True,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(receipt, dict) or receipt.get("schema") != CONTRACT:
        return [f"recibo deve usar schema {CONTRACT}"]
    for field in ("run_id", "cadeira", "rota", "provedor", "nonce"):
        if not isinstance(receipt.get(field), str) or not receipt[field].strip():
            errors.append(f"recibo exige {field} não vazio")
    for field in ("tentativa", "rodada"):
        value = receipt.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            errors.append(f"recibo exige {field} inteiro >= 1")
    for field in ("argv_sha256", "entrada_sha256", "saida_sha256", "artefato_sha256"):
        if not valid_sha256(receipt.get(field)):
            errors.append(f"recibo exige {field} SHA-256 válido")
    nonce = receipt.get("nonce")
    if isinstance(nonce, str) and not NONCE.fullmatch(nonce):
        errors.append("nonce inválido")
    emitted = receipt.get("emitido_em")
    if not isinstance(emitted, str):
        errors.append("recibo exige emitido_em")
    else:
        try:
            parsed = datetime.fromisoformat(emitted.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError
        except ValueError:
            errors.append("emitido_em deve ser instante ISO-8601 com fuso")
    if expected_artifact_sha256 and receipt.get("artefato_sha256") != expected_artifact_sha256:
        errors.append("recibo refere-se a outro hash de artefato")

    seat_name = receipt.get("cadeira")
    try:
        canonical, seat = resolve_seat(manifest, str(seat_name))
    except ValueError as exc:
        errors.append(str(exc))
    else:
        if seat_name != canonical:
            errors.append("recibo deve usar o nome canônico da cadeira")
        if receipt.get("rota") != seat.get("route"):
            errors.append("rota efetiva diverge do manifesto")
        if receipt.get("provedor") != seat.get("provider"):
            errors.append("provedor efetivo diverge do manifesto")
        model = receipt.get("modelo_efetivo")
        if require_model and (not isinstance(model, str) or not model.strip()):
            errors.append("modelo efetivo não observável; recibo não satisfaz hold-out estrito")
        if require_model and receipt.get("modelo_confirmado") is not True:
            errors.append("modelo_confirmado deve ser true para hold-out estrito")
        fixed = seat.get("default_model") if seat.get("model_policy") == "fixed_default" else None
        if fixed and model != fixed:
            errors.append("modelo efetivo diverge da política fixa da cadeira")

    if receipt.get("execucao_efetiva") is not True:
        errors.append("recibo não confirma execução efetiva")
    session = receipt.get("sessao_id")
    execution_id = receipt.get("execucao_id")
    native_confirmed = (
        isinstance(session, str) and bool(session.strip())
        and receipt.get("sessao_confirmada") is True
    )
    isolated_confirmed = (
        isinstance(execution_id, str) and bool(execution_id.strip())
        and receipt.get("isolamento_execucao_confirmado") is True
    )
    if require_session and not (native_confirmed or isolated_confirmed):
        errors.append(
            "independência não confirmada: exige sessão nativa observada ou execução isolada atestada"
        )

    attestation = receipt.get("atestacao")
    if not isinstance(attestation, dict):
        errors.append("atestação HMAC ausente")
    else:
        expected = hmac.new(secret, canonical_json(_unsigned(receipt)), hashlib.sha256).hexdigest()
        signature = attestation.get("assinatura")
        if attestation.get("contrato") != ATTESTATION_CONTRACT:
            errors.append("contrato de atestação incompatível")
        if attestation.get("algoritmo") != "hmac-sha256":
            errors.append("algoritmo de atestação incompatível")
        if attestation.get("key_id") != key_id(secret):
            errors.append("key_id da atestação não corresponde ao host")
        if not isinstance(signature, str) or not hmac.compare_digest(signature, expected):
            errors.append("assinatura HMAC inválida")
    return errors


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


def consume_nonces(path: str | Path, receipts: list[dict[str, Any]]) -> None:
    requested = Path(path).expanduser().absolute()
    requested.parent.mkdir(parents=True, exist_ok=True)
    if requested.is_symlink():
        raise ValueError(f"ledger de nonces não pode ser symlink: {requested}")
    target = requested.parent.resolve(strict=True) / requested.name
    if target == DEFAULT_NONCE_LEDGER.absolute():
        target.parent.chmod(0o700)
    lock = target.with_name(f".{target.name}.lock")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            if target.exists():
                payload = json.loads(target.read_text(encoding="utf-8"))
                if payload.get("schema") != NONCE_LEDGER_CONTRACT:
                    raise ValueError("ledger de nonces incompatível")
            else:
                payload = {"schema": NONCE_LEDGER_CONTRACT, "nonces": {}}
            seen = payload.setdefault("nonces", {})
            incoming = [receipt["nonce"] for receipt in receipts]
            if len(incoming) != len(set(incoming)):
                raise ValueError("nonce duplicado no mesmo lote")
            reused = sorted(nonce for nonce in incoming if nonce in seen)
            if reused:
                raise ValueError("replay detectado para nonce: " + ", ".join(reused))
            for receipt in receipts:
                seen[receipt["nonce"]] = {
                    "run_id": receipt["run_id"],
                    "cadeira": receipt["cadeira"],
                    "tentativa": receipt["tentativa"],
                    "rodada": receipt["rodada"],
                    "artefato_sha256": receipt["artefato_sha256"],
                    "consumido_em": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                }
            _atomic_json(target, payload)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def check_nonces_available(path: str | Path, receipts: list[dict[str, Any]]) -> None:
    """Verifica replay sem efetivar a transição deliberativa."""

    requested = Path(path).expanduser().absolute()
    requested.parent.mkdir(parents=True, exist_ok=True)
    if requested.is_symlink():
        raise ValueError(f"ledger de nonces não pode ser symlink: {requested}")
    target = requested.parent.resolve(strict=True) / requested.name
    if target == DEFAULT_NONCE_LEDGER.absolute():
        target.parent.chmod(0o700)
    lock = target.with_name(f".{target.name}.lock")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock, flags, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
        try:
            if not target.exists():
                return
            payload = json.loads(target.read_text(encoding="utf-8"))
            if payload.get("schema") != NONCE_LEDGER_CONTRACT:
                raise ValueError("ledger de nonces incompatível")
            seen = payload.get("nonces")
            if not isinstance(seen, dict):
                raise ValueError("ledger de nonces inválido")
            incoming = [receipt["nonce"] for receipt in receipts]
            if len(incoming) != len(set(incoming)):
                raise ValueError("nonce duplicado no mesmo lote")
            reused = sorted(nonce for nonce in incoming if nonce in seen)
            if reused:
                raise ValueError("replay detectado para nonce: " + ", ".join(reused))
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def attest_invocation(
    template: dict[str, Any],
    metadata: dict[str, Any],
    *,
    artifact_path: str | Path,
    artifact_root: str | Path,
    manifest: dict[str, Any],
    secret: bytes,
    allow_unconfirmed_model: bool = False,
    allow_unconfirmed_session: bool = False,
) -> dict[str, Any]:
    if metadata.get("simulation") is True or metadata.get("execution_effective") is not True:
        raise ValueError("metadados não comprovam execução efetiva")
    seat_name = template.get("cadeira")
    if not isinstance(seat_name, str):
        raise ValueError("template exige cadeira")
    canonical, seat = resolve_seat(manifest, seat_name)
    if canonical != seat_name or metadata.get("seat") != canonical:
        raise ValueError("cadeira do template diverge da execução")
    if metadata.get("route") != seat.get("route") or metadata.get("provider") != seat.get("provider"):
        raise ValueError("rota ou provedor dos metadados diverge do manifesto")
    root = canonical_directory(artifact_root)
    artifact = hash_file(artifact_path, roots=[root])
    required_hashes = {
        "argv_sha256": metadata.get("argv_sha256"),
        "entrada_sha256": metadata.get("input_sha256"),
        "saida_sha256": metadata.get("output_sha256"),
    }
    if any(not valid_sha256(value) for value in required_hashes.values()):
        raise ValueError("metadados da invocação não contêm hashes completos")
    receipt = {
        **template,
        "schema": CONTRACT,
        "cadeira": canonical,
        "rota": seat["route"],
        "provedor": seat.get("provider"),
        **required_hashes,
        "artefato_sha256": artifact["sha256"],
        "emitido_em": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "modelo_efetivo": metadata.get("effective_model"),
        "modelo_confirmado": metadata.get("model_confirmed") is True,
        "execucao_efetiva": True,
        "execucao_id": metadata.get("execution_id"),
        "isolamento_execucao_confirmado": metadata.get("execution_isolation_confirmed") is True,
        "sessao_id": metadata.get("session_id"),
        "sessao_confirmada": metadata.get("native_session_confirmed") is True,
    }
    signed = sign_receipt(receipt, secret)
    errors = validate_receipt(
        signed,
        manifest,
        secret,
        expected_artifact_sha256=artifact["sha256"],
        require_model=not allow_unconfirmed_model,
        require_session=not allow_unconfirmed_session,
    )
    if errors:
        raise ValueError("; ".join(errors))
    return signed


def _load_json(path: str) -> dict[str, Any]:
    value = json.load(sys.stdin) if path == "-" else json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("entrada deve ser objeto JSON")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    digest = sub.add_parser("hash-file")
    digest.add_argument("path")
    sign = sub.add_parser("sign-receipt")
    sign.add_argument("receipt")
    attest = sub.add_parser("attest-invocation")
    attest.add_argument("template")
    attest.add_argument("metadata")
    attest.add_argument("--artifact", required=True)
    attest.add_argument("--root", required=True)
    attest.add_argument("--manifest")
    attest.add_argument("--allow-unconfirmed-model", action="store_true")
    attest.add_argument("--allow-unconfirmed-session", action="store_true")
    verify = sub.add_parser("verify-receipt")
    verify.add_argument("receipt")
    verify.add_argument("--manifest")
    verify.add_argument("--artifact-sha256")
    verify.add_argument("--allow-unconfirmed-model", action="store_true")
    verify.add_argument("--allow-unconfirmed-session", action="store_true")
    verify.add_argument("--consume-nonce-ledger")
    args = parser.parse_args()
    try:
        if args.command == "hash-file":
            result = hash_file(args.path)
        elif args.command == "sign-receipt":
            if os.environ.get("MULTIAGENT_ALLOW_LOW_LEVEL_SIGN") != "1":
                raise ValueError(
                    "sign-receipt é primitiva de manutenção; use attest-invocation ou confirme "
                    "MULTIAGENT_ALLOW_LOW_LEVEL_SIGN=1"
                )
            result = sign_receipt(_load_json(args.receipt), load_host_secret())
        elif args.command == "attest-invocation":
            result = attest_invocation(
                _load_json(args.template),
                _load_json(args.metadata),
                artifact_path=args.artifact,
                artifact_root=args.root,
                manifest=load_manifest(args.manifest),
                secret=load_host_secret(),
                allow_unconfirmed_model=args.allow_unconfirmed_model,
                allow_unconfirmed_session=args.allow_unconfirmed_session,
            )
        else:
            receipt = _load_json(args.receipt)
            errors = validate_receipt(
                receipt,
                load_manifest(args.manifest),
                load_host_secret(),
                expected_artifact_sha256=args.artifact_sha256,
                require_model=not args.allow_unconfirmed_model,
                require_session=not args.allow_unconfirmed_session,
            )
            if not errors and args.consume_nonce_ledger:
                consume_nonces(args.consume_nonce_ledger, [receipt])
            result = {"valid": not errors, "errors": errors}
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0 if result.get("valid", True) else 2
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
