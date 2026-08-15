#!/usr/bin/env python3
"""Deterministic validation for consensus configuration and verdicts."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


PLUGIN_ROOT = Path(__file__).resolve().parents[3]
if str(PLUGIN_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT / "scripts"))
import provenance  # noqa: E402


DEFAULT_MANIFEST = Path("~/.agents/multiagent-manifest.json").expanduser()
PACKAGED_MANIFEST = Path(__file__).resolve().parents[3] / "assets" / "multiagent-manifest.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def load_json(source: str) -> dict[str, Any]:
    if source == "-":
        data = json.load(sys.stdin)
    else:
        with Path(source).expanduser().open(encoding="utf-8") as handle:
            data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("a raiz JSON deve ser um objeto")
    return data


def load_contract(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"manifesto ausente: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifesto inválido: {exc}") from exc
    contract = data.get("consensus")
    if not isinstance(contract, dict) or contract.get("contract") != "veredito_consenso_v1":
        raise ValueError("contrato de consenso ausente ou incompatível")
    return contract


def load_manifest_and_contract(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = provenance.load_manifest(path)
    contract = manifest.get("consensus")
    if not isinstance(contract, dict) or contract.get("contract") != "veredito_consenso_v1":
        raise ValueError("contrato de consenso ausente ou incompatível")
    return manifest, contract


def emit(payload: Any) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def config_report(config: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    mode = config.get("modo")
    policy = config.get("politica_por_tentativa")
    rounds = config.get("rodadas", contract["rounds_default"])
    cycles = config.get("ciclos_por_participante", contract["cycles_default"])
    stability = config.get("estabilidade", contract["stable_evaluations_default"])
    simulation = config.get("simulacao", False)
    auto_extend = config.get("extensao_automatica", contract.get("auto_extend_if_needed", False))

    if mode not in contract["modes"]:
        errors.append(f"modo inválido: {mode}")
    if policy not in contract["policies"]:
        errors.append(f"política inválida: {policy}")
    if mode == "desativado" and policy != "nenhum":
        errors.append("modo desativado exige política nenhum")
    if mode != "desativado" and policy == "nenhum":
        errors.append("política nenhum exige modo desativado")
    minimum_rounds = 0 if mode == "desativado" else 1
    if isinstance(rounds, bool) or not isinstance(rounds, int) or not minimum_rounds <= rounds <= contract["rounds_max"]:
        errors.append(f"rodadas deve ficar entre {minimum_rounds} e {contract['rounds_max']}")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 0 <= cycles <= contract["cycles_max_per_seat"]:
        errors.append(f"ciclos deve ficar entre 0 e {contract['cycles_max_per_seat']}")
    if (
        isinstance(rounds, int) and not isinstance(rounds, bool)
        and isinstance(cycles, int) and not isinstance(cycles, bool)
    ):
        minimum = contract["phases_per_cycle"] * cycles
        if rounds < minimum:
            errors.append(f"rodadas insuficientes: {rounds} < {minimum} para {cycles} ciclos")
    minimum_stability = 0 if mode == "desativado" else 1
    if isinstance(stability, bool) or not isinstance(stability, int) or stability < minimum_stability:
        errors.append(f"estabilidade deve ser inteiro >= {minimum_stability}")
    if mode in {"estrito", "com_decisor"} and (
        isinstance(stability, bool) or not isinstance(stability, int) or stability < 2
    ):
        errors.append("modos estrito e com_decisor exigem estabilidade >= 2")
    if mode == "desativado" and (cycles != 0 or rounds != 0 or stability != 0):
        errors.append("modo desativado exige zero rodadas, ciclos e estabilidade")
    if rounds == 1 and cycles != 0:
        errors.append("rodada única exige zero ciclos completos")
    if rounds == 1 and stability != 1:
        warnings.append("rodada única normalmente usa estabilidade 1")
    if simulation and mode in {"estrito", "com_decisor"}:
        warnings.append("simulação pode testar o fluxo, mas não pode emitir veredito")
    if not isinstance(auto_extend, bool):
        errors.append("extensao_automatica deve ser booleana")
    recommended_rounds = contract.get("rounds_recommended_max", contract["rounds_max"])
    recommended_cycles = contract.get(
        "cycles_recommended_max_per_seat", contract["cycles_max_per_seat"]
    )
    if isinstance(rounds, int) and not isinstance(rounds, bool) and rounds > recommended_rounds:
        warnings.append("rodadas na faixa excepcional; registrar necessidade, progresso e custo")
    if isinstance(cycles, int) and not isinstance(cycles, bool) and cycles > recommended_cycles:
        warnings.append("ciclos na faixa excepcional; registrar necessidade, progresso e custo")

    return {
        "valid": not errors,
        "contract": contract["contract"],
        "normalized": {
            "modo": mode,
            "politica_por_tentativa": policy,
            "rodadas": rounds,
            "ciclos_por_participante": cycles,
            "estabilidade": stability,
            "simulacao": bool(simulation),
            "extensao_automatica": auto_extend,
            "incremento_extensao_rodadas": contract.get("extension_increment_rounds"),
            "incremento_extensao_ciclos": contract.get("extension_increment_cycles"),
            "parada_apos_ciclos_sem_progresso": contract.get("no_progress_cycles_before_stop"),
        },
        "errors": errors,
        "warnings": warnings,
    }


def _validate_ledger(
    verdict: dict[str, Any],
    artifact_hash: Any,
    rounds: Any,
    required_stability: Any,
    outcome: Any,
    approved: Any,
) -> list[str]:
    errors: list[str] = []
    ledger = verdict.get("ledger_deliberacao")
    if not isinstance(ledger, dict):
        return ["veredito ativo exige ledger_deliberacao verificável"]
    recorded_rounds = ledger.get("rodadas")
    evaluations = ledger.get("avaliacoes")
    if not isinstance(recorded_rounds, list):
        errors.append("ledger_deliberacao.rodadas deve ser lista")
        recorded_rounds = []
    if not isinstance(evaluations, list):
        errors.append("ledger_deliberacao.avaliacoes deve ser lista")
        evaluations = []
    if isinstance(rounds, int) and len(recorded_rounds) != rounds:
        errors.append("rodadas_usadas deve ser derivado da quantidade de rodadas do ledger")
    for expected, item in enumerate(recorded_rounds, start=1):
        if not isinstance(item, dict):
            errors.append(f"rodada {expected} do ledger deve ser objeto")
            continue
        if item.get("numero") != expected:
            errors.append("rodadas do ledger devem ser numeradas sequencialmente")
        if item.get("artefato_sha256") != artifact_hash:
            errors.append(f"rodada {expected} refere-se a outro hash")
        if not isinstance(item.get("fase"), str) or not item["fase"].strip():
            errors.append(f"rodada {expected} exige fase")
    if approved and rounds == 1:
        errors.append("rodada única é provisória e nunca emite aprovação forte")
    if rounds == 1 and verdict.get("estado") != "provisional_single_round":
        errors.append("rodada única exige estado provisional_single_round")
    if approved and (
        isinstance(required_stability, bool)
        or not isinstance(required_stability, int)
        or required_stability < 2
    ):
        errors.append("aprovação forte exige estabilidade_exigida >= 2")
    if outcome == "consenso":
        if (
            isinstance(required_stability, bool)
            or not isinstance(required_stability, int)
            or required_stability < 2
        ):
            errors.append("consenso exige ao menos duas avaliações estáveis consecutivas")
        else:
            tail = evaluations[-required_stability:]
            if len(tail) != required_stability or any(
                not isinstance(item, dict)
                or item.get("resultado") != "consenso"
                or item.get("artefato_sha256") != artifact_hash
                for item in tail
            ):
                errors.append("estabilidade deve ser derivada de avaliações consecutivas do mesmo hash")
    return errors


def verdict_report(
    verdict: dict[str, Any],
    contract: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
    secret: bytes | None = None,
    nonce_ledger: str | Path | None = None,
    consume_nonce: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if verdict.get("schema") != contract["contract"]:
        errors.append(f"schema deve ser {contract['contract']}")
    mode = verdict.get("modo")
    policy = verdict.get("politica_por_tentativa")
    outcome = verdict.get("resultado")
    approved = verdict.get("aprovacao")
    simulation = verdict.get("simulacao", False)
    artifact_hash = verdict.get("artefato_sha256")
    run_id = verdict.get("run_id")
    attempt = verdict.get("tentativa")
    participants = verdict.get("participantes")
    blockers = verdict.get("bloqueadores", [])
    dissents = verdict.get("dissensos", [])
    evidence = verdict.get("evidencias", [])
    rounds = verdict.get("rodadas_usadas")
    cycles = verdict.get("ciclos_usados")
    stable = verdict.get("estabilidade_atingida", False)
    collegiate = verdict.get("formacao_decisao_colegiada")
    manifest = manifest or provenance.load_manifest(PACKAGED_MANIFEST)

    config_input: dict[str, Any] = {
        "modo": mode,
        "politica_por_tentativa": policy,
        "simulacao": simulation,
    }
    provided = {
        "rodadas": rounds,
        "ciclos_por_participante": cycles,
        "estabilidade": verdict.get("estabilidade_exigida"),
    }
    if mode == "desativado":
        config_input.update({
            "rodadas": 0 if rounds is None else rounds,
            "ciclos_por_participante": 0 if cycles is None else cycles,
            "estabilidade": 0 if provided["estabilidade"] is None else provided["estabilidade"],
        })
    else:
        for key, value in provided.items():
            if value is None:
                errors.append(f"{key} é obrigatório em veredito ativo")
            else:
                config_input[key] = value
    config = config_report(config_input, contract)
    errors.extend(config["errors"])
    warnings.extend(config["warnings"])
    if outcome not in contract["outcomes"]:
        errors.append(f"resultado inválido: {outcome}")
    if not isinstance(approved, bool):
        errors.append("aprovacao deve ser booleano")
    if mode != "desativado" and (not isinstance(artifact_hash, str) or not SHA256.fullmatch(artifact_hash)):
        errors.append("artefato_sha256 deve conter 64 caracteres hexadecimais")
    if mode != "desativado" and (not isinstance(run_id, str) or not run_id.strip()):
        errors.append("veredito ativo exige run_id")
    if mode != "desativado" and (
        isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1
    ):
        errors.append("veredito ativo exige tentativa inteira >= 1")
    if mode != "desativado" and (not isinstance(participants, list) or len(participants) < 2):
        errors.append("veredito ativo exige ao menos dois participantes")
    elif mode != "desativado":
        seen_seats: set[str] = set()
        for index, participant in enumerate(participants):
            if not isinstance(participant, dict):
                errors.append(f"participante {index} deve ser objeto com cadeira, rota, modelo e provedor")
                continue
            required_identity = ("cadeira", "rota", "modelo", "provedor")
            if any(not isinstance(participant.get(field), str) or not participant[field].strip() for field in required_identity):
                errors.append(f"participante {index} exige cadeira, rota, modelo e provedor não vazios")
                continue
            seat = participant["cadeira"]
            if seat in seen_seats:
                errors.append(f"cadeira duplicada no consenso: {seat}")
            seen_seats.add(seat)
            try:
                canonical, seat_config = provenance.resolve_seat(manifest, seat)
            except ValueError as exc:
                errors.append(str(exc))
                continue
            if canonical != seat:
                errors.append(f"participante {index} deve usar cadeira canônica {canonical}")
            if participant.get("rota") != seat_config.get("route"):
                errors.append(f"rota de {seat} diverge do manifesto")
            if participant.get("provedor") != seat_config.get("provider"):
                errors.append(f"provedor de {seat} diverge do manifesto")
    if not isinstance(blockers, list) or not isinstance(dissents, list) or not isinstance(evidence, list):
        errors.append("bloqueadores, dissensos e evidencias devem ser listas")
    else:
        for field, entries in (
            ("bloqueadores", blockers),
            ("dissensos", dissents),
            ("evidencias", evidence),
        ):
            if any(not isinstance(item, str) or not item.strip() for item in entries):
                errors.append(f"{field} deve conter somente textos não vazios")

    if mode != "desativado":
        errors.extend(
            _validate_ledger(
                verdict,
                artifact_hash,
                rounds,
                verdict.get("estabilidade_exigida"),
                outcome,
                approved,
            )
        )

    verified_receipts: list[dict[str, Any]] = []
    if mode != "desativado":
        artifact_path = verdict.get("artefato_caminho")
        artifact_root = verdict.get("raiz_artefatos")
        if not isinstance(artifact_path, str) or not artifact_path:
            errors.append("veredito ativo exige artefato_caminho")
        elif not isinstance(artifact_root, str) or not artifact_root:
            errors.append("veredito ativo exige raiz_artefatos explícita")
        else:
            try:
                resolved_root = provenance.canonical_directory(artifact_root)
                actual = provenance.hash_file(artifact_path, roots=[resolved_root])
                if actual["sha256"] != artifact_hash:
                    errors.append("artefato_sha256 diverge do arquivo real")
            except (OSError, ValueError) as exc:
                errors.append(str(exc))

        receipts = verdict.get("recibos_proveniencia")
        if not isinstance(receipts, list):
            errors.append("veredito ativo exige recibos_proveniencia")
            receipts = []
        by_nonce: dict[str, dict[str, Any]] = {}
        for receipt in receipts:
            if not isinstance(receipt, dict):
                errors.append("cada recibo de proveniência deve ser objeto")
                continue
            seat = receipt.get("cadeira")
            nonce = receipt.get("nonce")
            if not isinstance(seat, str):
                errors.append("recibo de proveniência possui cadeira ausente")
                continue
            if not isinstance(nonce, str) or nonce in by_nonce:
                errors.append("recibo de proveniência possui nonce ausente ou duplicado")
                continue
            by_nonce[nonce] = receipt
        expected_seats = {
            item["cadeira"] for item in participants or []
            if isinstance(item, dict) and isinstance(item.get("cadeira"), str)
        }
        referenced_nonces: set[str] = set()
        deliberation_ledger = verdict.get("ledger_deliberacao")
        evaluations = (
            deliberation_ledger.get("avaliacoes", [])
            if isinstance(deliberation_ledger, dict)
            else []
        )
        nonce_evaluation_round: dict[str, int] = {}
        for index, evaluation in enumerate(evaluations):
            if not isinstance(evaluation, dict):
                continue
            evaluation_number = evaluation.get("numero")
            if (
                isinstance(evaluation_number, bool)
                or not isinstance(evaluation_number, int)
                or evaluation_number < 1
                or (isinstance(rounds, int) and evaluation_number > rounds)
            ):
                errors.append(f"avaliação {index + 1} exige numero de rodada válido")
                evaluation_number = -1
            nonces = evaluation.get("recibos_nonces")
            if not isinstance(nonces, list) or any(not isinstance(item, str) for item in nonces):
                errors.append(f"avaliação {index + 1} exige recibos_nonces")
                continue
            if len(nonces) != len(set(nonces)):
                errors.append(f"avaliação {index + 1} repete nonce")
            for nonce in nonces:
                if nonce in nonce_evaluation_round:
                    errors.append(f"nonce {nonce} aparece em mais de uma avaliação")
                else:
                    nonce_evaluation_round[nonce] = evaluation_number
            seats_in_evaluation = {
                by_nonce[item].get("cadeira") for item in nonces if item in by_nonce
            }
            if set(nonces) - set(by_nonce):
                errors.append(f"avaliação {index + 1} referencia recibo inexistente")
            if seats_in_evaluation != expected_seats:
                errors.append(
                    f"avaliação {index + 1} deve conter exatamente uma manifestação por cadeira"
                )
            referenced_nonces.update(nonces)
        if set(by_nonce) != referenced_nonces:
            errors.append("recibos devem ser usados exatamente pelo ledger deliberativo")
        secret_was_supplied = secret is not None
        if secret_was_supplied and (
            not isinstance(secret, bytes) or len(secret) < 32
        ):
            errors.append("segredo HMAC injetado deve possuir ao menos 32 bytes")
            secret = None
        elif secret is None:
            try:
                secret = provenance.load_host_secret()
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
        if secret is not None:
            participant_map = {
                item["cadeira"]: item for item in participants or []
                if isinstance(item, dict) and isinstance(item.get("cadeira"), str)
            }
            for nonce, receipt in by_nonce.items():
                seat = receipt.get("cadeira", f"nonce:{nonce}")
                receipt_errors = provenance.validate_receipt(
                    receipt,
                    manifest,
                    secret,
                    expected_artifact_sha256=artifact_hash,
                    require_model=True,
                    require_session=True,
                )
                identity = participant_map.get(seat, {})
                if receipt.get("modelo_efetivo") != identity.get("modelo"):
                    receipt_errors.append("modelo do participante diverge do recibo efetivo")
                if receipt.get("run_id") != run_id or receipt.get("tentativa") != attempt:
                    receipt_errors.append("recibo diverge do run_id ou tentativa do veredito")
                receipt_round = receipt.get("rodada")
                if isinstance(rounds, int) and (
                    isinstance(receipt_round, bool)
                    or not isinstance(receipt_round, int)
                    or receipt_round > rounds
                ):
                    receipt_errors.append("rodada do recibo excede as rodadas do veredito")
                expected_round = nonce_evaluation_round.get(nonce)
                if expected_round is not None and receipt_round != expected_round:
                    receipt_errors.append(
                        "rodada do recibo não corresponde à avaliação que referencia o nonce"
                    )
                if outcome == "consenso":
                    if receipt.get("posicao") != "aprovar":
                        receipt_errors.append("consenso exige posição aprovar em cada recibo")
                    if receipt.get("bloqueadores") not in ([], None):
                        receipt_errors.append("consenso exige recibo sem bloqueadores")
                    if receipt.get("dissensos") not in ([], None):
                        receipt_errors.append("consenso exige recibo sem dissensos")
                if receipt_errors:
                    errors.extend(f"{seat}: {item}" for item in receipt_errors)
                else:
                    verified_receipts.append(receipt)

        session_groups: dict[tuple[int, int], list[str]] = {}
        for receipt in verified_receipts:
            group = (receipt["tentativa"], receipt["rodada"])
            independence_id = receipt.get("sessao_id") or receipt.get("execucao_id")
            session_groups.setdefault(group, []).append(independence_id)
        for group, sessions in session_groups.items():
            if len(sessions) != len(set(sessions)):
                errors.append(
                    f"sessões correlacionadas entre cadeiras na tentativa/rodada {group}"
                )

        declared_quorum = verdict.get("quorum_declarado", len(expected_seats))
        minimum_quorum = verdict.get("quorum_minimo", declared_quorum)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 2
            for value in (declared_quorum, minimum_quorum)
        ):
            errors.append("quorum_declarado e quorum_minimo devem ser inteiros >= 2")
        latest_verified_seats = {
            receipt["cadeira"] for receipt in verified_receipts
            if receipt.get("nonce") in set(
                evaluations[-1].get("recibos_nonces", [])
                if evaluations and isinstance(evaluations[-1], dict) else []
            )
        }
        if not errors and len(latest_verified_seats) < minimum_quorum:
            errors.append("cadeiras verificadas abaixo do piso de quórum")
        elif not errors and len(latest_verified_seats) < declared_quorum:
            if verdict.get("reducao_quorum_confirmada") is not True:
                errors.append("redução de quórum exige política previamente confirmada")
            if verdict.get("diversidade_reduzida") is not True:
                errors.append("redução de quórum exige diversidade_reduzida=true")

        if nonce_ledger is None:
            errors.append("veredito ativo exige ledger de nonces do host")
    if collegiate is not None:
        if not isinstance(collegiate, dict):
            errors.append("formacao_decisao_colegiada deve ser objeto")
        else:
            collegiate_result = collegiate.get("resultado_deliberativo")
            if collegiate_result in {
                "decisao_por_maioria", "decisao_por_maioria_qualificada",
                "decisao_do_decisor", "unanimidade_no_resultado_sem_fundamentos_comuns",
            } and outcome == "consenso":
                errors.append("maioria, unanimidade apenas no resultado ou decisão não equivalem a consenso")
            if outcome == "consenso" and collegiate.get("artefato_sha256") != artifact_hash:
                errors.append("consenso e decisão colegiada devem referir-se ao mesmo hash")

    if simulation:
        if approved is not False or outcome not in {None, "desativado"}:
            errors.append("simulação não pode emitir resultado deliberativo nem aprovação")
    elif mode == "estrito":
        if approved and outcome != "consenso":
            errors.append("modo estrito só aprova com resultado consenso")
        if approved and (blockers or dissents or not stable):
            errors.append("consenso estrito exige estabilidade e nenhum bloqueador ou dissenso material")
    elif mode == "com_decisor":
        if approved and outcome not in {"consenso", "decisao_sem_consenso"}:
            errors.append("com_decisor aprova somente por consenso ou decisão registrada")
        if approved and blockers:
            errors.append("bloqueadores materiais impedem aprovação mesmo com decisor")
        if approved and outcome == "consenso" and (dissents or not stable):
            errors.append("resultado consenso exige estabilidade e ausência de dissenso material")
    elif mode == "consultivo":
        if approved is not False:
            errors.append("modo consultivo nunca aprova o artefato")
        if outcome != "consultivo":
            errors.append("modo consultivo exige resultado consultivo")
    elif mode == "desativado":
        if approved is not False or outcome != "desativado":
            errors.append("modo desativado não emite aprovação")

    if approved and not evidence:
        errors.append("aprovação exige evidências registradas")
    if verdict.get("estado") == contract["approved_state"] and not approved:
        errors.append("canonico_aprovado exige aprovacao=true")
    if verdict.get("estado") == contract["selected_state"] and approved:
        errors.append("canonico_selecionado não equivale a aprovação")

    if mode != "desativado" and nonce_ledger is not None and not errors:
        try:
            if consume_nonce:
                provenance.consume_nonces(nonce_ledger, verified_receipts)
            else:
                provenance.check_nonces_available(nonce_ledger, verified_receipts)
        except (OSError, ValueError) as exc:
            errors.append(str(exc))

    valid = not errors
    transition_effective = valid and mode != "desativado" and consume_nonce
    return {
        "valid": valid,
        "contract": contract["contract"],
        "approval_requested": approved if isinstance(approved, bool) else None,
        "approval": bool(approved) if transition_effective else False,
        "transition_effective": transition_effective,
        "resultado": outcome,
        "errors": errors,
        "warnings": warnings,
    }


def hash_file(path: str) -> dict[str, Any]:
    return provenance.hash_file(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        default=os.environ.get(
            "MULTIAGENT_MANIFEST",
            str(DEFAULT_MANIFEST if DEFAULT_MANIFEST.is_file() else PACKAGED_MANIFEST),
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    config = sub.add_parser("validate-config")
    config.add_argument("source")
    verdict = sub.add_parser("validate-verdict")
    verdict.add_argument("source")
    verdict.add_argument(
        "--nonce-ledger",
        help="ledger host-only usado para impedir replay dos recibos de uma aprovação",
    )
    verdict.add_argument(
        "--check-only",
        action="store_true",
        help="valida sem consumir nonces; não efetiva a transição de aprovação",
    )
    verdict.add_argument(
        "--allow-custom-nonce-ledger",
        action="store_true",
        help="permite --nonce-ledger alternativo somente para teste isolado ou migração",
    )
    artifact = sub.add_parser("hash-artifact")
    artifact.add_argument("path")
    args = parser.parse_args()
    try:
        manifest, contract = load_manifest_and_contract(Path(args.manifest).expanduser().resolve())
        if args.command == "validate-config":
            report = config_report(load_json(args.source), contract)
        elif args.command == "validate-verdict":
            payload = load_json(args.source)
            environment_ledger = os.environ.get("MULTIAGENT_NONCE_LEDGER")
            requested_ledger = args.nonce_ledger or environment_ledger
            custom_opt_in = args.allow_custom_nonce_ledger or (
                os.environ.get("MULTIAGENT_ALLOW_CUSTOM_NONCE_LEDGER") == "1"
            )
            if requested_ledger and not custom_opt_in:
                requested = Path(requested_ledger).expanduser().resolve()
                if requested != provenance.DEFAULT_NONCE_LEDGER.resolve():
                    raise ValueError(
                        "ledger alternativo exige --allow-custom-nonce-ledger ou "
                        "MULTIAGENT_ALLOW_CUSTOM_NONCE_LEDGER=1"
                    )
            ledger = args.nonce_ledger or environment_ledger or str(
                provenance.DEFAULT_NONCE_LEDGER
            )
            report = verdict_report(
                payload,
                contract,
                manifest=manifest,
                nonce_ledger=ledger,
                consume_nonce=payload.get("modo") != "desativado" and not args.check_only,
            )
            if args.check_only and payload.get("modo") != "desativado":
                report["warnings"].append(
                    "check-only não consome nonces nem efetiva o veredito"
                )
        else:
            report = hash_file(args.path)
        emit(report)
        return 0 if report.get("valid", True) else 2
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        emit({"valid": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
