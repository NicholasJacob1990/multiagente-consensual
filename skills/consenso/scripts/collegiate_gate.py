#!/usr/bin/env python3
"""Validate collegial decision configurations and formation receipts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = Path("~/.agents/multiagent-manifest.json").expanduser()
PACKAGED_MANIFEST = Path(__file__).resolve().parents[3] / "assets" / "multiagent-manifest.json"
SHA256 = re.compile(r"^[0-9a-f]{64}$")
SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import consensus_gate  # noqa: E402
import analytic_tally  # noqa: E402
provenance = consensus_gate.provenance


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
    contract = data.get("collegiate_decision")
    if not isinstance(contract, dict) or contract.get("contract") != "decisao_colegiada_v1":
        raise ValueError("contrato de decisão colegiada ausente ou incompatível")
    return contract


def load_manifest_and_contract(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest, _ = consensus_gate.load_manifest_and_contract(path)
    contract = manifest.get("collegiate_decision")
    if not isinstance(contract, dict) or contract.get("contract") != "decisao_colegiada_v1":
        raise ValueError("contrato de decisão colegiada ausente ou incompatível")
    return manifest, contract


def emit(payload: Any) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def valid_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256.fullmatch(value))


def config_report(config: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    method = config.get("metodo_apuracao", contract.get("default_tally_method", "global"))
    if method in {"analitico", "hibrido"}:
        analytic_config = dict(config)
        analytic_config["metodo_apuracao"] = method
        return analytic_tally.config_report(analytic_config, contract)
    errors: list[str] = []
    warnings: list[str] = []
    modality = config.get("modalidade", contract["default_modality"])
    result_rule = config.get("regra_resultado", contract["default_result_rule"])
    calculation_base = config.get("base_calculo", contract["default_calculation_base"])
    join_scope = config.get("adesao_fundamentos", contract["default_join_scope"])
    quorum = config.get("quorum")
    threshold = config.get("limiar_maioria_qualificada")
    ratio_required = config.get("ratio_exigida", False)
    dissent_policy = config.get("votos_dissidentes", "publicar")
    concurrence_policy = config.get("votos_concorrentes", "publicar")
    freeze = config.get("proclamacao_congela_votos", True)

    if method != "global":
        errors.append(f"metodo_apuracao inválido: {method}")
    explicit_contract = config.get("contrato")
    if explicit_contract is not None and explicit_contract != contract["contract"]:
        errors.append(f"o método global exige {contract['contract']}")

    if modality not in contract["modalities"]:
        errors.append(f"modalidade inválida: {modality}")
    if result_rule not in contract["result_rules"]:
        errors.append(f"regra_resultado inválida: {result_rule}")
    if calculation_base not in contract["calculation_bases"]:
        errors.append(f"base_calculo inválida: {calculation_base}")
    if join_scope not in contract["join_scopes"]:
        errors.append(f"adesao_fundamentos inválida: {join_scope}")
    if isinstance(quorum, bool) or not isinstance(quorum, int) or quorum < 2:
        errors.append("quorum deve ser inteiro >= 2")
    if result_rule == "maioria_qualificada":
        if (
            isinstance(threshold, bool)
            or not isinstance(threshold, (int, float))
            or not math.isfinite(float(threshold))
            or not 0.5 < float(threshold) <= 1
        ):
            errors.append("maioria_qualificada exige limiar entre 0,5 exclusivo e 1 inclusivo")
    elif threshold is not None:
        warnings.append("limiar_maioria_qualificada será ignorado fora da regra correspondente")
    if not isinstance(ratio_required, bool):
        errors.append("ratio_exigida deve ser booleana")
    if dissent_policy not in contract["separate_opinion_policies"]:
        errors.append(f"política de votos dissidentes inválida: {dissent_policy}")
    if concurrence_policy not in contract["separate_opinion_policies"]:
        errors.append(f"política de votos concorrentes inválida: {concurrence_policy}")
    if freeze is not True:
        errors.append("a proclamação deve congelar os votos")
    if modality == "opinion_of_court" and dissent_policy != "publicar":
        errors.append("opinion_of_court exige publicação dos votos dissidentes")
    if modality == "seriatim" and (
        dissent_policy != "publicar" or concurrence_policy != "publicar"
    ):
        errors.append("seriatim exige publicação das manifestações individuais")
    if modality == "per_curiam" and dissent_policy == "nao_aplicavel":
        warnings.append("per_curiam sem voto separado ainda deve preservar dissenso no recibo de auditoria")

    return {
        "valid": not errors,
        "contract": contract["contract"],
        "normalized": {
            "metodo_apuracao": "global",
            "modalidade": modality,
            "regra_resultado": result_rule,
            "base_calculo": calculation_base,
            "adesao_fundamentos": join_scope,
            "quorum": quorum,
            "limiar_maioria_qualificada": threshold,
            "ratio_exigida": ratio_required,
            "votos_dissidentes": dissent_policy,
            "votos_concorrentes": concurrence_policy,
            "proclamacao_congela_votos": freeze,
        },
        "errors": errors,
        "warnings": warnings,
    }


def required_support(rule: str, total: int, threshold: float | None) -> int:
    if rule in {"unanimidade", "consenso_estrito"}:
        return total
    if rule == "maioria_qualificada":
        try:
            numeric = float(threshold)
        except (TypeError, ValueError):
            return total + 1
        if not math.isfinite(numeric) or not 0.5 < numeric <= 1:
            return total + 1
        return math.ceil(total * numeric)
    return total // 2 + 1


def verdict_report(
    verdict: dict[str, Any],
    contract: dict[str, Any],
    *,
    manifest: dict[str, Any] | None = None,
    secret: bytes | None = None,
    nonce_ledger: str | Path | None = None,
    consume_nonce: bool = False,
) -> dict[str, Any]:
    method = verdict.get("metodo_apuracao", contract.get("default_tally_method", "global"))
    if verdict.get("schema") == contract.get("analytic_schema") or method in {
        "analitico", "hibrido"
    }:
        return analytic_tally.verdict_report(
            verdict,
            contract,
            manifest=manifest or provenance.load_manifest(PACKAGED_MANIFEST),
            consensus_gate=consensus_gate,
            secret=secret,
            nonce_ledger=nonce_ledger,
            consume_nonce=consume_nonce,
        )
    errors: list[str] = []
    warnings: list[str] = []
    pending_nonce_receipts: list[dict[str, Any]] = []
    if verdict.get("schema") != contract["contract"]:
        errors.append(f"schema deve ser {contract['contract']}")

    config_input = {
        "contrato": verdict.get("schema"),
        "metodo_apuracao": method,
        "modalidade": verdict.get("modalidade"),
        "regra_resultado": verdict.get("regra_resultado"),
        "base_calculo": verdict.get("base_calculo", contract["default_calculation_base"]),
        "adesao_fundamentos": verdict.get("adesao_fundamentos", contract["default_join_scope"]),
        "quorum": verdict.get("quorum_declarado"),
        "limiar_maioria_qualificada": verdict.get("limiar_maioria_qualificada"),
        "ratio_exigida": verdict.get("ratio_exigida", False),
        "votos_dissidentes": verdict.get("votos_dissidentes", "publicar"),
        "votos_concorrentes": verdict.get("votos_concorrentes", "publicar"),
        "proclamacao_congela_votos": verdict.get("proclamacao_congela_votos", True),
    }
    config = config_report(config_input, contract)
    errors.extend(config["errors"])
    warnings.extend(config["warnings"])
    normalized = config["normalized"]

    manifest = manifest or provenance.load_manifest(PACKAGED_MANIFEST)
    artifact_hash = verdict.get("artefato_sha256")
    if not valid_hash(artifact_hash):
        errors.append("artefato_sha256 deve conter 64 caracteres hexadecimais")
    votes = verdict.get("votos")
    propositions = verdict.get("proposicoes")
    if not isinstance(votes, list) or len(votes) < 2:
        errors.append("votos deve conter ao menos duas cadeiras")
        votes = []
    if not isinstance(propositions, list):
        errors.append("proposicoes deve ser lista")
        propositions = []

    seats: set[str] = set()
    vote_by_seat: dict[str, dict[str, Any]] = {}
    valid_votes: list[dict[str, Any]] = []
    abstentions: list[dict[str, Any]] = []
    option_counts: dict[str, int] = {}
    for index, vote in enumerate(votes):
        if not isinstance(vote, dict):
            errors.append(f"voto {index} deve ser objeto")
            continue
        seat = vote.get("cadeira")
        if not isinstance(seat, str) or not seat.strip():
            errors.append(f"voto {index} exige cadeira")
            continue
        if seat in seats:
            errors.append(f"cadeira duplicada: {seat}")
            continue
        seats.add(seat)
        vote_by_seat[seat] = vote
        kind = vote.get("tipo")
        if kind == "abstencao":
            abstentions.append(vote)
            continue
        option = vote.get("opcao_dispositivo")
        if not isinstance(option, str) or not option.strip():
            errors.append(f"voto de {seat} exige opcao_dispositivo")
        else:
            option_counts[option] = option_counts.get(option, 0) + 1
        if not valid_hash(vote.get("voto_sha256")):
            errors.append(f"voto de {seat} exige voto_sha256 válido")
        joins = vote.get("adesoes", [])
        if not isinstance(joins, list) or any(not isinstance(item, str) for item in joins):
            errors.append(f"adesoes de {seat} deve ser lista de IDs")
        valid_votes.append(vote)

    declared_quorum = normalized["quorum"]
    if isinstance(declared_quorum, int) and len(votes) < declared_quorum:
        errors.append(f"quórum insuficiente: {len(votes)} < {declared_quorum}")
    if not valid_votes:
        errors.append("não há votos válidos para formar o resultado")

    winning_option = verdict.get("opcao_vencedora")
    if not isinstance(winning_option, str) or not winning_option.strip():
        errors.append("opcao_vencedora é obrigatória")
        winning_count = 0
    else:
        winning_count = option_counts.get(winning_option, 0)
    denominator = len(valid_votes) if normalized["base_calculo"] == "votos_validos" else len(votes)
    threshold = normalized["limiar_maioria_qualificada"]
    support_needed = required_support(normalized["regra_resultado"], denominator, threshold)
    rule = normalized["regra_resultado"]
    if rule in {"unanimidade", "consenso_estrito"} and abstentions:
        errors.append(f"{rule} não admite abstenção")
    if rule != "com_decisor" and winning_count < support_needed:
        errors.append(
            f"opção vencedora não satisfaz {rule}: {winning_count} apoio(s), exigidos {support_needed}"
        )
    if rule == "com_decisor":
        decider = verdict.get("decisor")
        if not isinstance(decider, dict) or decider.get("opcao") != winning_option or not decider.get("fundamento"):
            errors.append("com_decisor exige decisão fundamentada sobre a opção vencedora")

    proposition_map: dict[str, dict[str, Any]] = {}
    for index, proposition in enumerate(propositions):
        if not isinstance(proposition, dict):
            errors.append(f"proposição {index} deve ser objeto")
            continue
        prop_id = proposition.get("id")
        if not isinstance(prop_id, str) or not prop_id.strip():
            errors.append(f"proposição {index} exige id")
            continue
        if prop_id in proposition_map:
            errors.append(f"proposição duplicada: {prop_id}")
            continue
        if not valid_hash(proposition.get("texto_sha256")):
            errors.append(f"proposição {prop_id} exige texto_sha256 válido")
        if not isinstance(proposition.get("essencial"), bool):
            errors.append(f"proposição {prop_id} exige essencial booleano")
        proposition_map[prop_id] = proposition

    for seat, vote in vote_by_seat.items():
        for prop_id in vote.get("adesoes", []) if isinstance(vote.get("adesoes", []), list) else []:
            if prop_id not in proposition_map:
                errors.append(f"voto de {seat} adere a proposição inexistente: {prop_id}")

    winning_seats = {
        vote["cadeira"] for vote in valid_votes
        if vote.get("opcao_dispositivo") == winning_option
    }
    supported_propositions: set[str] = set()
    supported_ratio: set[str] = set()
    for prop_id, proposition in proposition_map.items():
        supporters = {
            seat for seat in winning_seats
            if prop_id in vote_by_seat[seat].get("adesoes", [])
        }
        if len(supporters) >= support_needed:
            supported_propositions.add(prop_id)
            if proposition.get("essencial"):
                supported_ratio.add(prop_id)

    declared_ratio = verdict.get("ratio_status")
    if declared_ratio not in contract["ratio_statuses"]:
        errors.append(f"ratio_status inválido: {declared_ratio}")
    if not proposition_map:
        computed_ratio = "nao_aplicavel"
    elif supported_ratio:
        computed_ratio = "unificada"
    elif winning_count >= support_needed:
        computed_ratio = "somente_resultado"
    else:
        computed_ratio = "pluralidade"
    if declared_ratio in contract["ratio_statuses"] and declared_ratio != computed_ratio:
        errors.append(f"ratio_status divergente: declarado {declared_ratio}, calculado {computed_ratio}")
    if normalized["ratio_exigida"] and computed_ratio != "unificada":
        errors.append("ratio_exigida impede formação com fundamentos não unificados")

    main_opinion = verdict.get("opiniao_principal")
    modality = normalized["modalidade"]
    main_adherents: set[str] = set()
    if modality in {"per_curiam", "opinion_of_court"}:
        if not isinstance(main_opinion, dict):
            errors.append(f"{modality} exige opiniao_principal")
            main_opinion = {}
        if not valid_hash(main_opinion.get("sha256")):
            errors.append("opiniao_principal exige sha256 válido")
        author = main_opinion.get("autoria")
        if modality == "per_curiam" and author != contract["per_curiam_author"]:
            errors.append("per_curiam exige autoria institucional_impessoal")
        if modality == "opinion_of_court" and author not in contract["opinion_of_court_authors"]:
            errors.append("opinion_of_court exige autoria da maioria ou do relator da maioria")
        adherents = main_opinion.get("aderentes")
        if not isinstance(adherents, list) or any(item not in seats for item in adherents):
            errors.append("aderentes da opinião principal devem ser cadeiras válidas")
            adherents = []
        main_adherents = set(adherents)
        if len(main_adherents) < support_needed:
            errors.append("opinião principal não possui adesões suficientes")
        if not main_adherents.issubset(winning_seats):
            errors.append("aderente da opinião principal não votou na opção vencedora")
        main_props = main_opinion.get("proposicoes", [])
        if not isinstance(main_props, list) or any(prop not in supported_propositions for prop in main_props):
            errors.append("opinião principal só pode declarar proposições com apoio suficiente")

    separate = verdict.get("votos_separados", [])
    if not isinstance(separate, list):
        errors.append("votos_separados deve ser lista")
        separate = []
    separate_seats: set[str] = set()
    for index, opinion in enumerate(separate):
        if not isinstance(opinion, dict):
            errors.append(f"voto separado {index} deve ser objeto")
            continue
        seat = opinion.get("cadeira")
        if seat not in seats or seat in separate_seats:
            errors.append(f"cadeira inválida ou duplicada em voto separado: {seat}")
            continue
        separate_seats.add(seat)
        if opinion.get("tipo") not in contract["separate_opinion_types"]:
            errors.append(f"tipo inválido de voto separado para {seat}")
        if opinion.get("tipo") != "abstencao" and not valid_hash(opinion.get("sha256")):
            errors.append(f"voto separado de {seat} exige sha256 válido")

    if modality == "opinion_of_court":
        non_joiners = seats - main_adherents
        missing_separate = {
            seat for seat in non_joiners
            if vote_by_seat.get(seat, {}).get("tipo") != "abstencao" and seat not in separate_seats
        }
        if missing_separate:
            errors.append(
                "opinion_of_court exige manifestação separada dos não aderentes: "
                + ", ".join(sorted(missing_separate))
            )

    label = verdict.get("rotulo_deliberativo")
    consensus_proof = verdict.get("veredito_consenso")
    requires_consensus_proof = rule == "consenso_estrito" or label == "consenso"
    if requires_consensus_proof:
        if not isinstance(consensus_proof, dict):
            errors.append("consenso estrito exige veredito_consenso completo e verificável")
        else:
            consensus_contract = (manifest or {}).get("consensus")
            if not isinstance(consensus_contract, dict):
                errors.append("manifesto sem contrato de consenso")
            else:
                consensus_report = consensus_gate.verdict_report(
                    consensus_proof,
                    consensus_contract,
                    manifest=manifest,
                    secret=secret,
                    nonce_ledger=nonce_ledger,
                    consume_nonce=False,
                )
                if (
                    not consensus_report["valid"]
                    or consensus_report.get("approval_requested") is not True
                ):
                    detail = "; ".join(consensus_report["errors"])
                    errors.append(f"veredito_consenso não comprova aprovação forte: {detail}")
                if consensus_proof.get("artefato_sha256") != artifact_hash:
                    errors.append("veredito_consenso e decisão colegiada referem-se a hashes distintos")
                proof_seats = {
                    item.get("cadeira")
                    for item in consensus_proof.get("participantes", [])
                    if isinstance(item, dict)
                }
                if seats != proof_seats:
                    errors.append(
                        "as cadeiras votantes devem coincidir com as cadeiras do consenso incorporado"
                    )
                if consensus_report["valid"]:
                    pending_nonce_receipts.extend(
                        item
                        for item in consensus_proof.get("recibos_proveniencia", [])
                        if isinstance(item, dict)
                    )
        if rule in {"maioria_simples", "maioria_qualificada", "com_decisor"}:
            errors.append("maioria ou decisão de terceiro não pode receber rótulo consenso")
    if label == "decisao_por_maioria" and winning_count == denominator:
        warnings.append("o placar é unânime no resultado; confirme se o rótulo desejado é unanimidade_no_resultado")

    gate = verdict.get("gate_colegiado")
    if gate is True and not requires_consensus_proof:
        run_id = verdict.get("run_id")
        attempt = verdict.get("tentativa")
        if not isinstance(run_id, str) or not run_id.strip():
            errors.append("gate colegiado forte exige run_id")
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 1:
            errors.append("gate colegiado forte exige tentativa inteira >= 1")
        artifact_path = verdict.get("artefato_caminho")
        artifact_root = verdict.get("raiz_artefatos")
        if not isinstance(artifact_path, str) or not artifact_path:
            errors.append("gate colegiado forte exige artefato_caminho")
        elif not isinstance(artifact_root, str) or not artifact_root:
            errors.append("gate colegiado forte exige raiz_artefatos")
        else:
            try:
                resolved_root = provenance.canonical_directory(artifact_root)
                actual = provenance.hash_file(artifact_path, roots=[resolved_root])
                if actual["sha256"] != artifact_hash:
                    errors.append("artefato colegiado diverge do arquivo real")
            except (OSError, ValueError) as exc:
                errors.append(str(exc))

        receipts = verdict.get("recibos_proveniencia")
        if not isinstance(receipts, list):
            errors.append("gate colegiado forte exige recibos_proveniencia")
            receipts = []
        by_nonce = {
            item.get("nonce"): item
            for item in receipts
            if isinstance(item, dict) and isinstance(item.get("nonce"), str)
        }
        if len(by_nonce) != len(receipts):
            errors.append("recibos colegiados devem ter nonces únicos")
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
        verified_vote_receipts: list[dict[str, Any]] = []
        for vote in valid_votes:
            seat = vote.get("cadeira")
            nonce = vote.get("recibo_nonce")
            receipt = by_nonce.get(nonce)
            if not isinstance(nonce, str) or receipt is None:
                errors.append(f"voto de {seat} exige recibo_nonce existente")
                continue
            if secret is None:
                errors.append(f"{seat}: segredo HMAC indisponível; recibo não verificável")
                continue
            receipt_errors = provenance.validate_receipt(
                receipt,
                manifest,
                secret,
                expected_artifact_sha256=artifact_hash,
                require_model=True,
                require_session=True,
            )
            if receipt.get("cadeira") != seat:
                receipt_errors.append("cadeira do recibo diverge do voto")
            if receipt.get("saida_sha256") != vote.get("voto_sha256"):
                receipt_errors.append("saida_sha256 do recibo diverge do voto congelado")
            if receipt.get("posicao_colegiada") != vote.get("opcao_dispositivo"):
                receipt_errors.append("posição colegiada do recibo diverge da opção votada")
            if receipt.get("run_id") != run_id or receipt.get("tentativa") != attempt:
                receipt_errors.append("recibo colegiado diverge do run_id ou tentativa")
            if receipt_errors:
                errors.extend(f"{seat}: {item}" for item in receipt_errors)
            else:
                verified_vote_receipts.append(receipt)
        if set(by_nonce) != {
            vote.get("recibo_nonce") for vote in valid_votes if isinstance(vote, dict)
        }:
            errors.append("recibos colegiados devem ser usados exatamente uma vez pelos votos")
        if nonce_ledger is None:
            errors.append("gate colegiado forte exige ledger de nonces do host")
        elif not errors:
            try:
                provenance.check_nonces_available(nonce_ledger, verified_vote_receipts)
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
        if not errors:
            pending_nonce_receipts.extend(verified_vote_receipts)

    proclaimed = verdict.get("proclamado")
    if proclaimed is not True:
        errors.append("o resultado precisa estar proclamado para congelar votos e hashes")
    if not isinstance(gate, bool):
        errors.append("gate_colegiado deve ser booleano")
    elif gate and errors:
        errors.append("gate_colegiado=true é incompatível com erros de formação")

    if gate is True and not errors and consume_nonce:
        try:
            provenance.consume_nonces(nonce_ledger, pending_nonce_receipts)
        except (OSError, ValueError, TypeError) as exc:
            errors.append(str(exc))

    valid = not errors
    transition_effective = valid and gate is True and consume_nonce
    trust_level = (
        "nested_consensus_proof"
        if valid and requires_consensus_proof
        else "attested_vote_formation" if valid and gate is True else "formation_only"
    )
    return {
        "valid": valid,
        "contract": contract["contract"],
        "gate_colegiado_requested": gate if isinstance(gate, bool) else None,
        "gate_colegiado": bool(gate) if transition_effective else False,
        "transition_effective": transition_effective,
        "trust_level": trust_level,
        "modalidade": modality,
        "opcao_vencedora": winning_option,
        "apoios_resultado": winning_count,
        "apoios_exigidos": support_needed,
        "ratio_status_calculado": computed_ratio,
        "proposicoes_ratio": sorted(supported_ratio),
        "errors": errors,
        "warnings": warnings,
    }


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
        help="ledger do host associado ao veredito de consenso incorporado",
    )
    verdict.add_argument(
        "--check-only",
        action="store_true",
        help="valida a formação sem consumir nonces nem efetivar o gate",
    )
    verdict.add_argument(
        "--allow-custom-nonce-ledger",
        action="store_true",
        help="permite --nonce-ledger alternativo somente para teste isolado ou migração",
    )
    digest = sub.add_parser("hash-text")
    digest.add_argument("text")
    args = parser.parse_args()
    try:
        manifest, contract = load_manifest_and_contract(Path(args.manifest).expanduser().resolve())
        if args.command == "validate-config":
            report = config_report(load_json(args.source), contract)
        elif args.command == "validate-verdict":
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
                load_json(args.source),
                contract,
                manifest=manifest,
                nonce_ledger=ledger,
                consume_nonce=not args.check_only,
            )
            if args.check_only:
                report["warnings"].append(
                    "check-only não consome nonces nem efetiva o gate colegiado"
                )
        else:
            report = {"text_sha256": hash_text(args.text)}
        emit(report)
        return 0 if report.get("valid", True) else 2
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        emit({"valid": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
