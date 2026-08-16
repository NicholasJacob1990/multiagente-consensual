#!/usr/bin/env python3
"""Deterministic issue-by-issue and hybrid collegiate tallying."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import provenance


SHA256 = re.compile(r"^[0-9a-f]{64}$")
METHODS = {"analitico", "hibrido"}
CONFIRMATION_REASONS = {
    "questao",
    "tabela_inadequada",
    "consequencia_juridica_recusada",
}


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(SHA256.fullmatch(value))


def _hash_payload(value: Any) -> str:
    return hashlib.sha256(provenance.canonical_json(value)).hexdigest()


def _required_support(rule: str, total: int, threshold: float | None) -> int:
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


def _reachable_worlds(
    questions: list[dict[str, Any]], maximum: int
) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    worlds: list[dict[str, str]] = [{}]
    for question in questions:
        expanded: list[dict[str, str]] = []
        dependency = question.get("depende_de")
        for world in worlds:
            active = dependency is None or world.get(dependency["questao"]) in dependency["respostas"]
            if not active:
                expanded.append(dict(world))
                continue
            for answer in question["dominio"]:
                candidate = dict(world)
                candidate[question["id"]] = answer
                expanded.append(candidate)
                if len(expanded) > maximum:
                    errors.append(
                        f"a derivação excede {maximum} mundos alcançáveis; simplifique as questões"
                    )
                    return [], errors
        worlds = expanded
    return worlds, errors


def _normalize_questions(
    raw: Any, maximum: int
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[str]]:
    errors: list[str] = []
    if not isinstance(raw, list) or not raw:
        return [], [], ["questoes deve ser lista não vazia no método analítico"]
    questions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"questão {index} deve ser objeto")
            continue
        question_id = item.get("id")
        if not isinstance(question_id, str) or not question_id.strip():
            errors.append(f"questão {index} exige id")
            continue
        if question_id in seen:
            errors.append(f"questão duplicada: {question_id}")
            continue
        seen.add(question_id)
        text = item.get("texto")
        if not isinstance(text, str) or not text.strip():
            errors.append(f"questão {question_id} exige texto")
            text = ""
        text_hash = item.get("texto_sha256")
        if not _valid_hash(text_hash):
            errors.append(f"questão {question_id} exige texto_sha256 válido")
        elif hashlib.sha256(text.encode("utf-8")).hexdigest() != text_hash:
            errors.append(f"texto_sha256 divergente na questão {question_id}")
        domain = item.get("dominio")
        if (
            not isinstance(domain, list)
            or len(domain) < 2
            or any(not isinstance(value, str) or not value.strip() for value in domain)
            or len(set(domain)) != len(domain)
        ):
            errors.append(f"domínio da questão {question_id} deve conter ao menos duas respostas únicas")
            domain = []
        dependency = item.get("depende_de")
        normalized_dependency: dict[str, Any] | None = None
        if dependency is not None:
            if not isinstance(dependency, dict):
                errors.append(f"depende_de de {question_id} deve ser objeto ou null")
            else:
                parent = dependency.get("questao")
                answers = dependency.get("respostas")
                parent_question = next((question for question in questions if question["id"] == parent), None)
                if parent_question is None:
                    errors.append(
                        f"questão {question_id} deve depender de um único pai já declarado"
                    )
                if (
                    not isinstance(answers, list)
                    or not answers
                    or any(not isinstance(value, str) for value in answers)
                    or len(set(answers)) != len(answers)
                ):
                    errors.append(f"guarda de {question_id} exige respostas únicas")
                elif parent_question is not None and not set(answers).issubset(
                    set(parent_question["dominio"])
                ):
                    errors.append(f"guarda de {question_id} usa resposta fora do domínio do pai")
                if parent_question is not None and isinstance(answers, list) and answers:
                    normalized_dependency = {"questao": parent, "respostas": list(answers)}
        questions.append(
            {
                "id": question_id,
                "texto": text,
                "texto_sha256": text_hash,
                "dominio": list(domain),
                "depende_de": normalized_dependency,
            }
        )
    worlds: list[dict[str, str]] = []
    if not errors:
        worlds, world_errors = _reachable_worlds(questions, maximum)
        errors.extend(world_errors)
    return questions, worlds, errors


def _compile_derivation(
    raw: Any,
    questions: list[dict[str, Any]],
    worlds: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if not isinstance(raw, list) or not raw:
        return [], ["regras_derivacao deve ser lista não vazia"]
    domains = {question["id"]: set(question["dominio"]) for question in questions}
    rules: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"regra de derivação {index} deve ser objeto")
            continue
        condition = item.get("se")
        option = item.get("opcao")
        if not isinstance(condition, dict):
            errors.append(f"regra de derivação {index} exige se como objeto")
            continue
        if not isinstance(option, str) or not option.strip():
            errors.append(f"regra de derivação {index} exige opcao")
            continue
        normalized_condition: dict[str, str] = {}
        for question_id, answer in condition.items():
            if question_id not in domains:
                errors.append(f"regra {index} referencia questão inexistente: {question_id}")
            elif answer not in domains[question_id]:
                errors.append(f"regra {index} usa resposta inválida em {question_id}")
            else:
                normalized_condition[question_id] = answer
        rules.append({"se": normalized_condition, "opcao": option})
    table: list[dict[str, Any]] = []
    if errors:
        return table, errors
    for world in worlds:
        matches = [
            rule
            for rule in rules
            if all(world.get(question_id) == answer for question_id, answer in rule["se"].items())
        ]
        if len(matches) != 1:
            errors.append(
                "cada mundo alcançável deve casar exatamente uma regra de derivação: "
                + repr(world)
            )
            continue
        table.append({"respostas": dict(world), "opcao": matches[0]["opcao"]})
    return table, errors


def _derive(table: list[dict[str, Any]], answers: dict[str, str]) -> str | None:
    for row in table:
        if row["respostas"] == answers:
            return row["opcao"]
    return None


def _confirmation_payload(normalized: dict[str, Any]) -> dict[str, Any]:
    return {
        "politica": "bloqueante",
        "regra_resultado": normalized["regra_resultado"],
        "base_calculo": normalized["base_calculo"],
        "quorum": normalized["quorum"],
        "limiar_maioria_qualificada": normalized["limiar_maioria_qualificada"],
    }


def _confirmation_vote_payload(
    item: dict[str, Any], derived_hash: str, confirmation_hash: str
) -> dict[str, Any]:
    return {
        "cadeira": item.get("cadeira"),
        "confirma": item.get("confirma"),
        "derivado_sha256": derived_hash,
        "confirmacao_sha256": confirmation_hash,
        "fundamento_divergencia": item.get("fundamento_divergencia"),
    }


def config_report(config: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    method = config.get("metodo_apuracao")
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
    expected_schema = contract.get("analytic_schema", "decisao_colegiada_v2")

    if method not in METHODS:
        errors.append(f"metodo_apuracao inválido para o contrato analítico: {method}")
    if config.get("contrato", expected_schema) != expected_schema:
        errors.append(f"métodos analítico e híbrido exigem {expected_schema}")
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

    maximum = contract.get("analytic_max_reachable_worlds", 4096)
    questions, worlds, question_errors = _normalize_questions(config.get("questoes"), maximum)
    errors.extend(question_errors)
    table, derivation_errors = _compile_derivation(
        config.get("regras_derivacao"), questions, worlds
    )
    errors.extend(derivation_errors)
    questions_hash = _hash_payload(questions) if questions and not question_errors else None
    derivation_hash = _hash_payload(table) if table and not derivation_errors else None
    declared_questions_hash = config.get("questoes_sha256")
    declared_derivation_hash = config.get("derivacao_sha256")
    if not _valid_hash(declared_questions_hash):
        errors.append("questoes_sha256 deve conter 64 caracteres hexadecimais")
    elif questions_hash is not None and declared_questions_hash != questions_hash:
        errors.append("questoes_sha256 diverge do pacote canônico de questões")
    if not _valid_hash(declared_derivation_hash):
        errors.append("derivacao_sha256 deve conter 64 caracteres hexadecimais")
    elif derivation_hash is not None and declared_derivation_hash != derivation_hash:
        errors.append("derivacao_sha256 diverge da tabela compilada")

    normalized = {
        "metodo_apuracao": method,
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
        "questoes": questions,
        "tabela_derivacao": table,
        "questoes_sha256": questions_hash,
        "derivacao_sha256": derivation_hash,
    }
    if method == "hibrido":
        if config.get("politica_confirmacao", "bloqueante") != "bloqueante":
            errors.append("o método híbrido admite somente confirmação bloqueante")
        confirmation_hash = _hash_payload(_confirmation_payload(normalized))
        normalized["politica_confirmacao"] = "bloqueante"
        normalized["confirmacao_sha256"] = confirmation_hash
        declared_confirmation_hash = config.get("confirmacao_sha256")
        if not _valid_hash(declared_confirmation_hash):
            errors.append("confirmacao_sha256 deve conter 64 caracteres hexadecimais")
        elif declared_confirmation_hash != confirmation_hash:
            errors.append("confirmacao_sha256 diverge da política congelada")

    return {
        "valid": not errors,
        "contract": expected_schema,
        "normalized": normalized,
        "errors": errors,
        "warnings": warnings,
    }


def _parse_ballot(
    vote: dict[str, Any], questions: list[dict[str, Any]], errors: list[str]
) -> tuple[dict[str, str | None], list[dict[str, Any]]]:
    seat = vote.get("cadeira")
    raw_answers = vote.get("respostas")
    if not isinstance(raw_answers, list):
        errors.append(f"respostas de {seat} deve ser lista")
        raw_answers = []
    entries: dict[str, dict[str, Any]] = {}
    for item in raw_answers:
        if not isinstance(item, dict) or not isinstance(item.get("questao"), str):
            errors.append(f"resposta inválida na cédula de {seat}")
            continue
        question_id = item["questao"]
        if question_id in entries:
            errors.append(f"resposta duplicada de {seat} para {question_id}")
            continue
        entries[question_id] = item
    known = {question["id"] for question in questions}
    for unknown in set(entries) - known:
        errors.append(f"cédula de {seat} referencia questão inexistente: {unknown}")

    answers: dict[str, str | None] = {}
    canonical: list[dict[str, Any]] = []
    for question in questions:
        question_id = question["id"]
        dependency = question.get("depende_de")
        active = dependency is None or answers.get(dependency["questao"]) in dependency["respostas"]
        item = entries.get(question_id)
        if not active:
            if item is not None:
                errors.append(f"{seat} respondeu questão prejudicada no próprio caminho: {question_id}")
            continue
        if item is None:
            errors.append(f"cédula de {seat} omite questão ativa: {question_id}")
            answers[question_id] = None
            canonical.append({"questao": question_id, "abstencao": True})
            continue
        if item.get("abstencao") is True:
            if "resposta" in item:
                errors.append(f"abstenção de {seat} em {question_id} não pode conter resposta")
            answers[question_id] = None
            canonical.append({"questao": question_id, "abstencao": True})
            continue
        answer = item.get("resposta")
        if answer not in question["dominio"]:
            errors.append(f"resposta inválida de {seat} em {question_id}: {answer}")
            answers[question_id] = None
            canonical.append({"questao": question_id, "abstencao": True})
            continue
        answers[question_id] = answer
        canonical.append({"questao": question_id, "resposta": answer})
    return answers, canonical


def verdict_report(
    verdict: dict[str, Any],
    contract: dict[str, Any],
    *,
    manifest: dict[str, Any],
    consensus_gate: Any,
    secret: bytes | None = None,
    nonce_ledger: str | Path | None = None,
    consume_nonce: bool = False,
) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    pending_nonce_receipts: list[dict[str, Any]] = []
    expected_schema = contract.get("analytic_schema", "decisao_colegiada_v2")
    if verdict.get("schema") != expected_schema:
        errors.append(f"schema deve ser {expected_schema}")

    config = config_report(
        {
            "contrato": verdict.get("schema"),
            "metodo_apuracao": verdict.get("metodo_apuracao"),
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
            "questoes": verdict.get("questoes"),
            "regras_derivacao": verdict.get("regras_derivacao"),
            "questoes_sha256": verdict.get("questoes_sha256"),
            "derivacao_sha256": verdict.get("derivacao_sha256"),
            "politica_confirmacao": verdict.get("politica_confirmacao"),
            "confirmacao_sha256": verdict.get("confirmacao_sha256"),
        },
        contract,
    )
    errors.extend(config["errors"])
    warnings.extend(config["warnings"])
    normalized = config["normalized"]
    method = normalized["metodo_apuracao"]
    questions = normalized["questoes"]
    table = normalized["tabela_derivacao"]
    artifact_hash = verdict.get("artefato_sha256")
    if not _valid_hash(artifact_hash):
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
    ballots: dict[str, dict[str, str | None]] = {}
    canonical_ballots: dict[str, list[dict[str, Any]]] = {}
    valid_votes: list[dict[str, Any]] = []
    abstentions: list[dict[str, Any]] = []
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
        if vote.get("tipo") == "abstencao":
            abstentions.append(vote)
            continue
        if "opcao_dispositivo" in vote:
            errors.append(f"voto analítico de {seat} não pode declarar opcao_dispositivo primária")
        if not _valid_hash(vote.get("voto_sha256")):
            errors.append(f"voto de {seat} exige voto_sha256 válido")
        joins = vote.get("adesoes", [])
        if not isinstance(joins, list) or any(not isinstance(item, str) for item in joins):
            errors.append(f"adesoes de {seat} deve ser lista de IDs")
        answers, canonical = _parse_ballot(vote, questions, errors)
        ballots[seat] = answers
        canonical_ballots[seat] = canonical
        answers_hash = _hash_payload(canonical)
        if vote.get("respostas_sha256") != answers_hash:
            errors.append(f"respostas_sha256 divergente na cédula de {seat}")
        valid_votes.append(vote)

    quorum = normalized["quorum"]
    if isinstance(quorum, int) and len(votes) < quorum:
        errors.append(f"quórum insuficiente: {len(votes)} < {quorum}")
    if not valid_votes:
        errors.append("não há cédulas válidas para formar o resultado")
    rule = normalized["regra_resultado"]
    threshold = normalized["limiar_maioria_qualificada"]
    if rule in {"unanimidade", "consenso_estrito"} and abstentions:
        errors.append(f"{rule} não admite abstenção")

    decider = verdict.get("decisor")
    decider_answers: dict[str, str] = {}
    if rule == "com_decisor":
        if not isinstance(decider, dict) or not isinstance(decider.get("fundamento"), str):
            errors.append("com_decisor exige decisão fundamentada sobre questões não alcançadas")
        else:
            raw_decisions = decider.get("respostas")
            if not isinstance(raw_decisions, list):
                errors.append("decisor.respostas deve ser lista")
            else:
                for item in raw_decisions:
                    if isinstance(item, dict) and isinstance(item.get("questao"), str):
                        decider_answers[item["questao"]] = item.get("resposta")

    collective: dict[str, str] = {}
    coalitions_by_question: dict[str, dict[str, Any]] = {}
    abstentions_by_question: dict[str, dict[str, Any]] = {}
    decider_used = False
    for question in questions:
        question_id = question["id"]
        dependency = question.get("depende_de")
        active = dependency is None or collective.get(dependency["questao"]) in dependency["respostas"]
        if not active:
            coalitions_by_question[question_id] = {
                "estado": "prejudicada",
                "resposta": None,
                "cadeiras": [],
                "votos_validos": 0,
                "apoios_exigidos": 0,
            }
            abstentions_by_question[question_id] = {
                "estado": "prejudicada",
                "cadeiras": [],
            }
            continue
        answer_seats: dict[str, list[str]] = {answer: [] for answer in question["dominio"]}
        explicit_abstention_seats: list[str] = []
        for vote in valid_votes:
            seat = vote["cadeira"]
            if question_id not in ballots[seat]:
                continue
            answer = ballots[seat][question_id]
            if answer is None:
                explicit_abstention_seats.append(seat)
            else:
                answer_seats[answer].append(seat)
        valid_count = sum(len(items) for items in answer_seats.values())
        denominator = valid_count if normalized["base_calculo"] == "votos_validos" else len(votes)
        support_needed = _required_support(rule, denominator, threshold)
        if valid_count < 2:
            errors.append(f"questão ativa {question_id} possui menos de dois votos válidos")
        if rule in {"unanimidade", "consenso_estrito"} and explicit_abstention_seats:
            errors.append(f"{rule} não admite abstenção na questão {question_id}")
        winners = [answer for answer, members in answer_seats.items() if len(members) >= support_needed]
        winner = winners[0] if len(winners) == 1 else None
        state = "apurada"
        if winner is None and rule == "com_decisor":
            candidate = decider_answers.get(question_id)
            if candidate in question["dominio"]:
                winner = candidate
                decider_used = True
                state = "decidida_por_decisor"
            else:
                errors.append(f"decisor não resolveu a questão não alcançada {question_id}")
        elif winner is None:
            errors.append(f"questão ativa não alcançada: {question_id}")
            state = "nao_alcancada"
        coalitions_by_question[question_id] = {
            "estado": state,
            "resposta": winner,
            "cadeiras": sorted(answer_seats.get(winner, [])) if winner is not None else [],
            "votos_validos": valid_count,
            "apoios_exigidos": support_needed,
        }
        abstentions_by_question[question_id] = {
            "estado": "ativa",
            "cadeiras": sorted(explicit_abstention_seats),
        }
        if winner is not None:
            collective[question_id] = winner

    derived = _derive(table, collective) if not errors else None
    if not errors and derived is None:
        errors.append("as respostas apuradas não possuem derivação única")

    individual_options: dict[str, str | None] = {}
    option_members: dict[str, list[str]] = {}
    for vote in valid_votes:
        seat = vote["cadeira"]
        answers = ballots[seat]
        defined = all(value is not None for value in answers.values())
        option = _derive(table, {key: value for key, value in answers.items() if value is not None}) if defined else None
        individual_options[seat] = option
        if option is not None:
            option_members.setdefault(option, []).append(seat)
    denominator = len(valid_votes) if normalized["base_calculo"] == "votos_validos" else len(votes)
    support_needed = _required_support(rule, denominator, threshold)
    direct_winners = [
        option for option, members in option_members.items() if len(members) >= support_needed
    ]
    direct_option = direct_winners[0] if len(direct_winners) == 1 else None
    package_coalition = sorted(option_members.get(derived, [])) if derived is not None else []
    package_support = len(package_coalition)
    paradox = derived is not None and package_support < support_needed
    declared_results = {
        "respostas_apuradas": collective,
        "coalizoes_por_questao": coalitions_by_question,
        "dispositivo_derivado": derived,
        "dispositivo_por_cadeira": direct_option,
        "contagem_dispositivos_por_cadeira": {
            option: len(members) for option, members in sorted(option_members.items())
        },
        "coalizao_do_dispositivo": package_coalition,
        "apoio_direto_do_derivado": package_support,
        "paradoxo_doutrinario": paradox,
    }
    for field, computed in declared_results.items():
        if verdict.get(field) != computed:
            errors.append(f"{field} diverge da apuração determinística")

    proposition_map: dict[str, dict[str, Any]] = {}
    for index, proposition in enumerate(propositions):
        if not isinstance(proposition, dict):
            errors.append(f"proposição {index} deve ser objeto")
            continue
        prop_id = proposition.get("id")
        if not isinstance(prop_id, str) or not prop_id.strip() or prop_id in proposition_map:
            errors.append(f"proposição inválida ou duplicada: {prop_id}")
            continue
        if not _valid_hash(proposition.get("texto_sha256")):
            errors.append(f"proposição {prop_id} exige texto_sha256 válido")
        if not isinstance(proposition.get("essencial"), bool):
            errors.append(f"proposição {prop_id} exige essencial booleano")
        proposition_map[prop_id] = proposition
    for seat, vote in vote_by_seat.items():
        for prop_id in vote.get("adesoes", []) if isinstance(vote.get("adesoes", []), list) else []:
            if prop_id not in proposition_map:
                errors.append(f"voto de {seat} adere a proposição inexistente: {prop_id}")
    supported_propositions: set[str] = set()
    supported_ratio: set[str] = set()
    for prop_id in proposition_map:
        supporters = {
            seat for seat in package_coalition if prop_id in vote_by_seat[seat].get("adesoes", [])
        }
        if len(supporters) >= support_needed:
            supported_propositions.add(prop_id)
            if proposition_map[prop_id].get("essencial"):
                supported_ratio.add(prop_id)

    if not proposition_map:
        computed_ratio = "nao_aplicavel"
    elif derived is not None and package_support >= support_needed and supported_ratio:
        computed_ratio = "unificada"
    elif decider_used and package_support < support_needed:
        computed_ratio = "pluralidade"
    else:
        computed_ratio = "somente_resultado"

    declared_ratio = verdict.get("ratio_status")
    if declared_ratio not in contract["ratio_statuses"]:
        errors.append(f"ratio_status inválido: {declared_ratio}")
    elif declared_ratio != computed_ratio:
        errors.append(f"ratio_status divergente: declarado {declared_ratio}, calculado {computed_ratio}")
    if normalized["ratio_exigida"] and computed_ratio != "unificada":
        errors.append("ratio_exigida impede formação com fundamentos essenciais não unificados")

    modality = normalized["modalidade"]
    main_opinion = verdict.get("opiniao_principal")
    main_adherents: set[str] = set()
    if modality in {"per_curiam", "opinion_of_court"}:
        if not isinstance(main_opinion, dict):
            errors.append(f"{modality} exige opiniao_principal")
            main_opinion = {}
        if not _valid_hash(main_opinion.get("sha256")):
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
        if not main_adherents.issubset(set(package_coalition)):
            errors.append("aderente da opinião principal não integra a coalizão do pacote")
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
        if opinion.get("tipo") != "abstencao" and not _valid_hash(opinion.get("sha256")):
            errors.append(f"voto separado de {seat} exige sha256 válido")
    if modality == "opinion_of_court":
        missing = {
            seat for seat in seats - main_adherents
            if vote_by_seat.get(seat, {}).get("tipo") != "abstencao" and seat not in separate_seats
        }
        if missing:
            errors.append(
                "opinion_of_court exige manifestação separada dos não aderentes: "
                + ", ".join(sorted(missing))
            )

    confirmation_votes: list[dict[str, Any]] = []
    confirmation_passed = method == "analitico"
    confirmation_state = "nao_aplicavel"
    derived_hash = _hash_payload(
        {
            "artefato_sha256": artifact_hash,
            "questoes_sha256": normalized.get("questoes_sha256"),
            "derivacao_sha256": normalized.get("derivacao_sha256"),
            "dispositivo": derived,
        }
    ) if derived is not None else None
    if method == "hibrido":
        confirmation = verdict.get("confirmacao")
        if not isinstance(confirmation, dict):
            errors.append("método híbrido exige objeto confirmacao")
            confirmation = {}
        raw_confirmation_votes = confirmation.get("votos")
        if not isinstance(raw_confirmation_votes, list):
            errors.append("confirmacao.votos deve ser lista")
            raw_confirmation_votes = []
        confirmation_by_seat: dict[str, dict[str, Any]] = {}
        for item in raw_confirmation_votes:
            if not isinstance(item, dict) or item.get("cadeira") not in ballots:
                errors.append("voto de confirmação exige cadeira com cédula analítica")
                continue
            seat = item["cadeira"]
            if seat in confirmation_by_seat:
                errors.append(f"confirmação duplicada para {seat}")
                continue
            if not isinstance(item.get("confirma"), bool):
                errors.append(f"confirmação de {seat} deve ser booleana")
            if not _valid_hash(item.get("voto_sha256")):
                errors.append(f"confirmação de {seat} exige voto_sha256 válido")
            elif derived_hash is not None:
                expected_vote_hash = _hash_payload(
                    _confirmation_vote_payload(
                        item, derived_hash, normalized.get("confirmacao_sha256")
                    )
                )
                if item.get("voto_sha256") != expected_vote_hash:
                    errors.append(
                        f"confirmação de {seat} não corresponde ao ato congelado"
                    )
            if item.get("confirma") is False and individual_options.get(seat) == derived:
                reason = item.get("fundamento_divergencia")
                if (
                    not isinstance(reason, dict)
                    or reason.get("tipo") not in CONFIRMATION_REASONS
                    or not isinstance(reason.get("fundamento"), str)
                    or not reason["fundamento"].strip()
                ):
                    errors.append(
                        f"{seat} rejeita a própria derivação sem fundamento de divergência válido"
                    )
            confirmation_by_seat[seat] = item
            confirmation_votes.append(item)
        if set(confirmation_by_seat) != set(ballots):
            errors.append("confirmação híbrida exige um segundo ato de cada cédula analítica")
        confirmations = sum(item.get("confirma") is True for item in confirmation_votes)
        confirmation_needed = _required_support(rule, denominator, threshold)
        confirmation_passed = confirmations >= confirmation_needed
        confirmation_state = "confirmada" if confirmation_passed else "rejeitada"
        if confirmation.get("resultado") != confirmation_state:
            errors.append("resultado da confirmação diverge da apuração")

    label = verdict.get("rotulo_deliberativo")
    consensus_proof = verdict.get("veredito_consenso")
    requires_consensus_proof = rule == "consenso_estrito" or label == "consenso"
    if requires_consensus_proof:
        if not isinstance(consensus_proof, dict):
            errors.append("consenso estrito exige veredito_consenso completo e verificável")
        else:
            consensus_contract = manifest.get("consensus")
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
                if not consensus_report["valid"] or consensus_report.get("approval_requested") is not True:
                    errors.append(
                        "veredito_consenso não comprova aprovação forte: "
                        + "; ".join(consensus_report["errors"])
                    )
                if consensus_proof.get("artefato_sha256") != artifact_hash:
                    errors.append("veredito_consenso e decisão colegiada referem-se a hashes distintos")
                proof_seats = {
                    item.get("cadeira") for item in consensus_proof.get("participantes", [])
                    if isinstance(item, dict)
                }
                if seats != proof_seats:
                    errors.append("as cadeiras votantes devem coincidir com as cadeiras do consenso")
                if consensus_report["valid"]:
                    pending_nonce_receipts.extend(
                        item for item in consensus_proof.get("recibos_proveniencia", [])
                        if isinstance(item, dict)
                    )
        if rule in {"maioria_simples", "maioria_qualificada", "com_decisor"}:
            errors.append("maioria ou decisão de terceiro não pode receber rótulo consenso")

    gate = verdict.get("gate_colegiado")
    formation_passed = derived is not None and confirmation_passed and not errors
    if gate is True and not formation_passed:
        errors.append("gate_colegiado=true é incompatível com formação ou confirmação incompleta")
    if gate is True and (not requires_consensus_proof or method == "hibrido"):
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
            item.get("nonce"): item for item in receipts
            if isinstance(item, dict) and isinstance(item.get("nonce"), str)
        }
        if len(by_nonce) != len(receipts):
            errors.append("recibos colegiados devem ter nonces únicos")
        if secret is not None and (not isinstance(secret, bytes) or len(secret) < 32):
            errors.append("segredo HMAC injetado deve possuir ao menos 32 bytes")
            secret = None
        elif secret is None:
            try:
                secret = provenance.load_host_secret()
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
        verified: list[dict[str, Any]] = []
        ballot_package_hash = _hash_payload(
            {
                "artefato_sha256": artifact_hash,
                "questoes_sha256": normalized.get("questoes_sha256"),
                "derivacao_sha256": normalized.get("derivacao_sha256"),
            }
        )
        expected_nonces: set[str] = set()
        for vote in valid_votes:
            seat = vote["cadeira"]
            nonce = vote.get("recibo_nonce")
            if isinstance(nonce, str):
                expected_nonces.add(nonce)
            receipt = by_nonce.get(nonce)
            if receipt is None or secret is None:
                errors.append(f"voto de {seat} exige recibo verificável")
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
                receipt_errors.append("saida_sha256 diverge da cédula congelada")
            if receipt.get("posicao_colegiada") != vote.get("respostas_sha256"):
                receipt_errors.append("posição colegiada diverge do vetor congelado da cédula")
            if receipt.get("questoes_sha256") != normalized.get("questoes_sha256"):
                receipt_errors.append("recibo diverge do pacote de questões")
            if receipt.get("derivacao_sha256") != normalized.get("derivacao_sha256"):
                receipt_errors.append("recibo diverge da tabela de derivação")
            if receipt.get("entrada_sha256") != ballot_package_hash:
                receipt_errors.append("entrada_sha256 não cobre o pacote congelado da cédula")
            if receipt.get("run_id") != run_id or receipt.get("tentativa") != attempt:
                receipt_errors.append("recibo colegiado diverge do run_id ou tentativa")
            if receipt_errors:
                errors.extend(f"{seat}: {item}" for item in receipt_errors)
            else:
                verified.append(receipt)
        if method == "hibrido":
            for item in confirmation_votes:
                seat = item["cadeira"]
                nonce = item.get("recibo_nonce")
                if isinstance(nonce, str):
                    expected_nonces.add(nonce)
                receipt = by_nonce.get(nonce)
                if receipt is None or secret is None:
                    errors.append(f"confirmação de {seat} exige recibo verificável")
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
                    receipt_errors.append("cadeira do recibo diverge da confirmação")
                confirmation_vote_hash = _hash_payload(
                    _confirmation_vote_payload(
                        item, derived_hash, normalized.get("confirmacao_sha256")
                    )
                )
                if receipt.get("saida_sha256") != confirmation_vote_hash:
                    receipt_errors.append("saida_sha256 diverge da confirmação congelada")
                if item.get("voto_sha256") != confirmation_vote_hash:
                    receipt_errors.append("voto_sha256 diverge do ato de confirmação")
                if receipt.get("posicao_colegiada") != confirmation_vote_hash:
                    receipt_errors.append("posição colegiada não atesta o ato de confirmação")
                if receipt.get("derivado_sha256") != derived_hash:
                    receipt_errors.append("recibo diverge do dispositivo derivado congelado")
                if receipt.get("confirmacao_sha256") != normalized.get("confirmacao_sha256"):
                    receipt_errors.append("recibo diverge da política de confirmação")
                if receipt.get("entrada_sha256") != derived_hash:
                    receipt_errors.append("entrada_sha256 da confirmação diverge do derivado")
                if receipt.get("run_id") != run_id or receipt.get("tentativa") != attempt:
                    receipt_errors.append("recibo de confirmação diverge do run_id ou tentativa")
                if receipt_errors:
                    errors.extend(f"{seat}: {error}" for error in receipt_errors)
                else:
                    verified.append(receipt)
        if set(by_nonce) != expected_nonces:
            errors.append("recibos colegiados devem ser usados exatamente uma vez pelos atos")
        if nonce_ledger is None:
            errors.append("gate colegiado forte exige ledger de nonces do host")
        elif not errors:
            try:
                provenance.check_nonces_available(nonce_ledger, verified)
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
        if not errors:
            pending_nonce_receipts.extend(verified)

    proclaimed = verdict.get("proclamado")
    if method == "hibrido" and not confirmation_passed:
        if proclaimed is not False:
            errors.append("confirmação rejeitada impede proclamação do dispositivo")
    elif proclaimed is not True:
        errors.append("o resultado precisa estar proclamado para congelar votos e hashes")
    if not isinstance(gate, bool):
        errors.append("gate_colegiado deve ser booleano")

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
        "contract": expected_schema,
        "gate_colegiado_requested": gate if isinstance(gate, bool) else None,
        "gate_colegiado": bool(gate) if transition_effective else False,
        "transition_effective": transition_effective,
        "trust_level": trust_level,
        "metodo_apuracao": method,
        "modalidade": modality,
        "opcao_vencedora": derived,
        "respostas_apuradas": collective,
        "dispositivo_derivado": derived,
        "dispositivo_por_cadeira": direct_option,
        "apoios_resultado": package_support,
        "apoios_exigidos": support_needed,
        "paradoxo_doutrinario": paradox,
        "coalizoes_por_questao": coalitions_by_question,
        "abstencoes_por_questao": abstentions_by_question,
        "coalizao_do_dispositivo": package_coalition,
        "ratio_status_calculado": computed_ratio,
        "confirmacao": confirmation_state,
        "cedula_sha256": _hash_payload(
            {
                "artefato_sha256": artifact_hash,
                "questoes_sha256": normalized.get("questoes_sha256"),
                "derivacao_sha256": normalized.get("derivacao_sha256"),
            }
        ),
        "derivado_sha256": derived_hash,
        "errors": errors,
        "warnings": warnings,
    }
