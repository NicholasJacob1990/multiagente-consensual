#!/usr/bin/env python3
"""Validador e planejador determinístico para workflow-agentes."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import statistics
import sys
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

PROTOCOLS = {
    "pipeline_serial_v1",
    "dag_assincrono_v1",
    "swarm_dinamico_v1",
    "map_reduce_v1",
    "torneio_eliminatorio_v1",
    "votacao_multiagente_v1",
    "roteamento_adaptativo_v1",
}
CONSENSUS_MODES = {"estrito", "com_decisor", "consultivo", "desativado"}
CONSENSUS_POLICIES = {"sempre", "se_necessario", "apenas_primeira", "nenhum"}


def durable_report(config: dict[str, Any]) -> dict[str, Any]:
    skills_root = Path(__file__).resolve().parents[2]
    path = skills_root / "loop-debate-agentes" / "scripts" / "durable_run.py"
    spec = importlib.util.spec_from_file_location("multiagent_durable_run", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("não foi possível carregar durable_run.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_durable_config(config)


def load_json(source: str) -> dict[str, Any]:
    if source == "-":
        data = json.load(sys.stdin)
    else:
        with Path(source).expanduser().open(encoding="utf-8") as handle:
            data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("A raiz JSON deve ser um objeto.")
    return data


def emit(payload: Any) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def graph_waves(nodes: list[str], edges: list[list[str]]) -> list[list[str]]:
    successors: dict[str, list[str]] = {node: [] for node in nodes}
    indegree = {node: 0 for node in nodes}
    for source, target in edges:
        successors[source].append(target)
        indegree[target] += 1

    ready = sorted(node for node, degree in indegree.items() if degree == 0)
    waves: list[list[str]] = []
    visited = 0
    while ready:
        wave = ready
        waves.append(wave)
        visited += len(wave)
        next_ready: list[str] = []
        for source in wave:
            for target in sorted(successors[source]):
                indegree[target] -= 1
                if indegree[target] == 0:
                    next_ready.append(target)
        ready = sorted(next_ready)

    if visited != len(nodes):
        blocked = sorted(node for node, degree in indegree.items() if degree > 0)
        raise ValueError(f"O DAG contém ciclo envolvendo: {', '.join(blocked)}")
    return waves


def structure(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("estrutura", {})
    return value if isinstance(value, dict) else {}


def validate_config(config: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    protocol = config.get("protocolo")
    data = structure(config)

    if config.get("perfil") != "workflow_agents_v1":
        errors.append("perfil deve ser workflow_agents_v1")
    if protocol not in PROTOCOLS:
        errors.append("protocolo desconhecido")
    if not config.get("objetivo"):
        errors.append("objetivo é obrigatório")
    if not isinstance(config.get("participantes", []), list):
        errors.append("participantes deve ser lista")
    limits = config.get("limites", {})
    if not isinstance(limits, dict):
        errors.append("limites deve ser objeto")
    else:
        max_parallel = limits.get("max_paralelo", 1)
        if not isinstance(max_parallel, int) or isinstance(max_parallel, bool) or max_parallel < 1:
            errors.append("max_paralelo deve ser inteiro >= 1")

    consensus = config.get("consenso")
    if consensus is not None:
        if not isinstance(consensus, dict):
            errors.append("consenso deve ser objeto quando informado")
        else:
            mode = consensus.get("modo")
            policy = consensus.get("politica_por_tentativa")
            if mode not in CONSENSUS_MODES:
                errors.append("consenso.modo desconhecido")
            if policy not in CONSENSUS_POLICIES:
                errors.append("consenso.politica_por_tentativa desconhecida")
            if mode == "desativado" and policy != "nenhum":
                errors.append("consenso desativado exige política nenhum")
            if mode != "desativado" and policy == "nenhum":
                errors.append("política nenhum exige consenso desativado")
            if mode in {"estrito", "com_decisor"} and not config.get("integracao_loop"):
                warnings.append("consenso vinculante exige integração com loop-debate-agentes")

    durable = durable_report(config)
    errors.extend(durable["errors"])
    warnings.extend(durable["warnings"])

    try:
        if protocol == "pipeline_serial_v1":
            stages = data.get("etapas", [])
            ids = [item.get("id") for item in stages if isinstance(item, dict)]
            if not stages:
                errors.append("pipeline exige etapas")
            if (
                len(ids) != len(stages)
                or any(not isinstance(item, str) or not item.strip() for item in ids)
                or len(set(ids)) != len(ids)
            ):
                errors.append("etapas precisam de IDs únicos")

        elif protocol == "dag_assincrono_v1":
            node_items = data.get("nos", [])
            node_ids = [item.get("id") for item in node_items if isinstance(item, dict)]
            edges = data.get("arestas", [])
            if not node_ids:
                errors.append("DAG exige nós")
            if (
                len(node_ids) != len(node_items)
                or any(not isinstance(item, str) or not item.strip() for item in node_ids)
                or len(set(node_ids)) != len(node_ids)
            ):
                errors.append("nós precisam de IDs únicos")
            for edge in edges:
                if not isinstance(edge, list) or len(edge) != 2:
                    errors.append("cada aresta deve ser [origem, destino]")
                    continue
                if edge[0] not in node_ids or edge[1] not in node_ids:
                    errors.append(f"aresta refere nó inexistente: {edge}")
            if not errors:
                graph_waves(node_ids, edges)

        elif protocol == "swarm_dinamico_v1":
            pool = data.get("pool_elegivel", [])
            initial = data.get("membros_iniciais", [])
            if not data.get("supervisor"):
                errors.append("swarm exige supervisor")
            if not pool:
                errors.append("swarm exige pool_elegivel")
            if any(member not in pool for member in initial):
                errors.append("membro inicial fora do pool")
            max_members = data.get("max_membros")
            if (
                not isinstance(max_members, int)
                or isinstance(max_members, bool)
                or max_members < max(1, len(initial))
            ):
                errors.append("max_membros deve ser inteiro >= 1 e cobrir membros_iniciais")
            max_expansions = data.get("max_expansoes")
            if (
                not isinstance(max_expansions, int)
                or isinstance(max_expansions, bool)
                or max_expansions < 0
            ):
                errors.append("max_expansoes deve ser inteiro >= 0")

        elif protocol == "map_reduce_v1":
            partition = data.get("particionamento", {})
            if not partition.get("itens"):
                errors.append("map-reduce exige itens de particionamento")
            if not data.get("mappers"):
                errors.append("map-reduce exige mappers")
            if not data.get("reducers"):
                errors.append("map-reduce exige reducers")
            if not data.get("funcao_map") or not data.get("funcao_reduce"):
                errors.append("funcoes map e reduce são obrigatórias")

        elif protocol == "torneio_eliminatorio_v1":
            candidates = data.get("candidatos", [])
            if not isinstance(candidates, list) or len(candidates) < 2:
                errors.append("torneio exige pelo menos dois candidatos")
            elif any(
                not isinstance(candidate, str) or not candidate.strip()
                for candidate in candidates
            ):
                errors.append("candidatos do torneio devem ser strings não vazias")
            elif len(set(candidates)) != len(candidates):
                errors.append("candidatos do torneio devem ser únicos")
            judges = data.get("juizes_por_confronto", 1)
            if isinstance(judges, bool) or not isinstance(judges, int) or judges < 1:
                errors.append("juizes_por_confronto deve ser >= 1")
            seed = data.get("seed", 0)
            if isinstance(seed, bool) or not isinstance(seed, int):
                errors.append("seed do torneio deve ser inteiro")

        elif protocol == "votacao_multiagente_v1":
            method = data.get("metodo")
            if method not in {"borda", "condorcet", "delphi"}:
                errors.append("método deve ser borda, condorcet ou delphi")
            if method in {"borda", "condorcet"} and len(data.get("candidatos", [])) < 2:
                errors.append("votação exige pelo menos dois candidatos")
            if method == "delphi":
                if not data.get("especialistas"):
                    errors.append("Delphi exige especialistas")
                maximum_rounds = data.get("rodadas_maximas", 0)
                if (
                    isinstance(maximum_rounds, bool)
                    or not isinstance(maximum_rounds, int)
                    or maximum_rounds < 1
                ):
                    errors.append("rodadas_maximas deve ser >= 1")

        elif protocol == "roteamento_adaptativo_v1":
            pool = data.get("pool", [])
            weights = data.get("pesos", {})
            required = {"qualidade", "custo", "latencia", "falha", "diversidade"}
            if not pool:
                errors.append("roteamento exige pool")
            ids = [item.get("id") for item in pool if isinstance(item, dict)]
            if (
                len(ids) != len(pool)
                or any(not isinstance(item, str) or not item.strip() for item in ids)
                or len(set(ids)) != len(ids)
            ):
                errors.append("itens do pool precisam de IDs únicos")
            for item in pool:
                if not isinstance(item, dict):
                    continue
                metrics = item.get("metricas", {})
                if not isinstance(metrics, dict):
                    errors.append(f"métricas de {item.get('id')} devem ser um objeto")
                    continue
                for key, value in metrics.items():
                    if (
                        key not in required
                        or isinstance(value, bool)
                        or not isinstance(value, (int, float))
                        or not math.isfinite(float(value))
                        or not 0 <= float(value) <= 1
                    ):
                        errors.append(f"métrica {key!r} inválida para {item.get('id')}")
            if not isinstance(weights, dict):
                errors.append("pesos devem ser um objeto")
            elif set(weights) != required:
                errors.append("pesos devem conter qualidade, custo, latencia, falha e diversidade")
            elif any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or not 0 <= float(value) <= 1
                for value in weights.values()
            ):
                errors.append("cada peso deve ser número finito entre 0 e 1")
            elif not math.isclose(
                sum(float(value) for value in weights.values()), 1.0, abs_tol=1e-6
            ):
                errors.append("a soma dos pesos deve ser 1")
            exploration = data.get("exploracao", 0)
            if (
                isinstance(exploration, bool)
                or not isinstance(exploration, (int, float))
                or not math.isfinite(float(exploration))
                or not 0 <= float(exploration) <= 1
            ):
                errors.append("exploracao deve ficar entre 0 e 1")
    except (TypeError, ValueError) as exc:
        errors.append(str(exc))

    return {
        "valid": not errors,
        "perfil": config.get("perfil"),
        "protocolo": protocol,
        "errors": errors,
        "warnings": warnings,
        "execucao_duravel": {
            "ativa": durable["active"],
            "perfil": durable["profile"],
            "max_segundos": durable["max_elapsed_seconds"],
        },
    }


def tournament_plan(candidates: list[str], seed: int) -> dict[str, Any]:
    ordered = list(candidates)
    random.Random(seed).shuffle(ordered)
    size = 1
    while size < len(ordered):
        size *= 2
    ordered.extend([None] * (size - len(ordered)))
    pairs = []
    for index in range(0, size, 2):
        left, right = ordered[index], ordered[index + 1]
        pairs.append({
            "confronto": index // 2 + 1,
            "esquerda": left,
            "direita": right,
            "bye": left if right is None else right if left is None else None,
        })
    return {"seed": seed, "tamanho_chave": size, "ordem": ordered, "primeira_rodada": pairs}


def routing_plan(data: dict[str, Any]) -> dict[str, Any]:
    weights = data["pesos"]
    ranking = []
    for item in data["pool"]:
        if item.get("elegivel", True) is False:
            continue
        metrics = item.get("metricas", {})
        unknown = [key for key in weights if key not in metrics]
        values: dict[str, float] = {}
        for key in weights:
            raw = metrics.get(key, 0.5)
            if (
                isinstance(raw, bool)
                or not isinstance(raw, (int, float))
                or not math.isfinite(float(raw))
                or not 0 <= float(raw) <= 1
            ):
                raise ValueError(f"métrica {key} inválida para {item.get('id')}")
            values[key] = float(raw)
        score = (
            float(weights["qualidade"]) * values["qualidade"]
            + float(weights["diversidade"]) * values["diversidade"]
            - float(weights["custo"]) * values["custo"]
            - float(weights["latencia"]) * values["latencia"]
            - float(weights["falha"]) * values["falha"]
        )
        ranking.append({
            "id": item["id"],
            "modelo": item.get("modelo"),
            "score": round(score, 6),
            "metricas_desconhecidas": unknown,
            "prior_neutro_aplicado": bool(unknown),
        })
    ranking.sort(key=lambda row: (-row["score"], row["id"]))
    selected = ranking[0] if ranking else None
    return {
        "ranking": ranking,
        "escolhido": selected,
        "estado": "canonico_selecionado" if selected else "sem_selecao",
        "aprovacao": False,
        "gate_necessario": "consenso+avaliacao+auditoria quando configurados",
    }


def make_plan(config: dict[str, Any]) -> dict[str, Any]:
    report = validate_config(config)
    if not report["valid"]:
        raise ValueError("; ".join(report["errors"]))
    protocol = config["protocolo"]
    data = structure(config)

    common = {
        "aprovacao": False,
        "semantica": "plano ou seleção; nunca aprovação",
    }
    durable = report["execucao_duravel"]
    if durable["ativa"]:
        common["execucao_duravel"] = {
            **durable,
            "checkpoint": "checkpoint.json",
            "relogio": "tempo_corrido",
            "offline_conta_no_prazo": True,
        }
    if config.get("consenso") is not None:
        common["consenso"] = {
            "configurado": True,
            "delegado_para": "veredito_consenso_v1",
            "modo": config["consenso"].get("modo"),
            "politica_por_tentativa": config["consenso"].get("politica_por_tentativa"),
        }

    if protocol == "pipeline_serial_v1":
        return {"protocolo": protocol, "ordem": [stage["id"] for stage in data["etapas"]], **common}
    if protocol == "dag_assincrono_v1":
        nodes = [node["id"] for node in data["nos"]]
        return {"protocolo": protocol, "ondas": graph_waves(nodes, data.get("arestas", [])), **common}
    if protocol == "swarm_dinamico_v1":
        return {
            "protocolo": protocol,
            "supervisor": data["supervisor"],
            "roster_inicial": data.get("membros_iniciais", []),
            "vagas_disponiveis": data["max_membros"] - len(data.get("membros_iniciais", [])),
            "max_expansoes": data["max_expansoes"],
            **common,
        }
    if protocol == "map_reduce_v1":
        items = data["particionamento"]["itens"]
        mappers = data["mappers"]
        assignments = defaultdict(list)
        for index, item in enumerate(items):
            assignments[mappers[index % len(mappers)]].append(item)
        return {
            "protocolo": protocol,
            "atribuicoes_map": dict(sorted(assignments.items())),
            "reducers": data["reducers"],
            "aridade_reduce": data.get("aridade_reduce", 8),
            **common,
        }
    if protocol == "torneio_eliminatorio_v1":
        return {
            "protocolo": protocol,
            **tournament_plan(data["candidatos"], data.get("seed", 0)),
            "estado": "planejado",
            **common,
        }
    if protocol == "votacao_multiagente_v1":
        return {
            "protocolo": protocol,
            "metodo": data["metodo"],
            "participantes": data.get("eleitores", data.get("especialistas", [])),
            "rodadas_maximas": data.get("rodadas_maximas", 1),
            **common,
        }
    if protocol == "roteamento_adaptativo_v1":
        return {"protocolo": protocol, **routing_plan(data), **common}
    raise ValueError("protocolo sem planejador")


def normalize_ballots(payload: dict[str, Any]) -> tuple[list[str], list[list[str]]]:
    candidates = payload.get("candidatos", payload.get("candidates", []))
    raw = payload.get("cedulas", payload.get("ballots", []))
    ballots = [item.get("ranking", []) if isinstance(item, dict) else item for item in raw]
    if len(candidates) < 2 or len(set(candidates)) != len(candidates):
        raise ValueError("candidatos devem ser uma lista única com pelo menos dois itens")
    expected = set(candidates)
    for ballot in ballots:
        if not isinstance(ballot, list) or len(ballot) != len(candidates) or set(ballot) != expected:
            raise ValueError("cada cédula deve ordenar todos os candidatos uma única vez")
    if not ballots:
        raise ValueError("nenhuma cédula fornecida")
    return candidates, ballots


def borda(payload: dict[str, Any]) -> dict[str, Any]:
    candidates, ballots = normalize_ballots(payload)
    maximum = len(candidates) - 1
    scores = {candidate: 0 for candidate in candidates}
    for ballot in ballots:
        for position, candidate in enumerate(ballot):
            scores[candidate] += maximum - position
    best = max(scores.values())
    winners = sorted(candidate for candidate, score in scores.items() if score == best)
    return {
        "metodo": "borda",
        "scores": scores,
        "vencedores": winners,
        "empate": len(winners) > 1,
        "estado": "canonico_selecionado" if len(winners) == 1 else "selecao_inconclusiva",
        "aprovacao": False,
        "gate_necessario": "consenso+avaliacao+auditoria quando configurados",
    }


def condorcet(payload: dict[str, Any]) -> dict[str, Any]:
    candidates, ballots = normalize_ballots(payload)
    matrix = {left: {right: 0 for right in candidates if right != left} for left in candidates}
    for ballot in ballots:
        positions = {candidate: index for index, candidate in enumerate(ballot)}
        for left in candidates:
            for right in candidates:
                if left != right and positions[left] < positions[right]:
                    matrix[left][right] += 1
    winners = []
    for left in candidates:
        if all(matrix[left][right] > matrix[right][left] for right in candidates if right != left):
            winners.append(left)
    return {
        "metodo": "condorcet",
        "matriz_preferencias": matrix,
        "vencedor": winners[0] if len(winners) == 1 else None,
        "sem_vencedor_condorcet": len(winners) != 1,
        "estado": "canonico_selecionado" if len(winners) == 1 else "selecao_inconclusiva",
        "aprovacao": False,
        "gate_necessario": "consenso+avaliacao+auditoria quando configurados",
    }


def _percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def delphi(payload: dict[str, Any]) -> dict[str, Any]:
    rounds = payload.get("rodadas")
    stability_declared = payload.get("estabilidade")
    stability_required = payload.get("estabilidade_exigida")
    if (
        stability_declared is not None
        and stability_required is not None
        and stability_declared != stability_required
    ):
        raise ValueError("estabilidade e estabilidade_exigida não podem divergir")
    stability = (
        stability_required
        if stability_required is not None
        else stability_declared if stability_declared is not None else 2
    )
    median_target = payload.get("limiar_mediana", 8.5)
    iqr_target = payload.get("limiar_iqr", 1.0)
    if not isinstance(rounds, list) or not rounds:
        raise ValueError("Delphi exige rodadas não vazias")
    if isinstance(stability, bool) or not isinstance(stability, int) or stability < 2:
        raise ValueError("estabilidade_exigida deve ser inteiro >= 2")
    if (
        isinstance(median_target, bool)
        or not isinstance(median_target, (int, float))
        or not math.isfinite(float(median_target))
        or not 0 <= float(median_target) <= 10
    ):
        raise ValueError("limiar_mediana deve ficar entre 0 e 10")
    if (
        isinstance(iqr_target, bool)
        or not isinstance(iqr_target, (int, float))
        or not math.isfinite(float(iqr_target))
        or float(iqr_target) < 0
    ):
        raise ValueError("limiar_iqr deve ser não negativo")

    expected_seats: set[str] | None = None
    summaries: list[dict[str, Any]] = []
    last_responses: list[dict[str, Any]] = []
    for expected_number, round_item in enumerate(rounds, start=1):
        if not isinstance(round_item, dict) or round_item.get("numero") != expected_number:
            raise ValueError("rodadas Delphi devem ser objetos numerados sequencialmente")
        responses = round_item.get("respostas")
        if not isinstance(responses, list) or len(responses) < 2:
            raise ValueError("cada rodada Delphi exige ao menos duas respostas")
        seats: set[str] = set()
        scores: list[float] = []
        for response in responses:
            if not isinstance(response, dict):
                raise ValueError("resposta Delphi deve ser objeto")
            seat = response.get("cadeira")
            score = response.get("nota")
            confidence = response.get("confianca")
            if not isinstance(seat, str) or not seat or seat in seats:
                raise ValueError("cadeiras Delphi devem ser não vazias e únicas por rodada")
            if (
                not isinstance(score, (int, float))
                or isinstance(score, bool)
                or not math.isfinite(float(score))
                or not 0 <= float(score) <= 10
            ):
                raise ValueError(f"nota Delphi inválida para {seat}")
            if (
                not isinstance(confidence, (int, float))
                or isinstance(confidence, bool)
                or not math.isfinite(float(confidence))
                or not 0 <= float(confidence) <= 1
            ):
                raise ValueError(f"confiança Delphi inválida para {seat}")
            seats.add(seat)
            scores.append(float(score))
        if expected_seats is None:
            expected_seats = seats
        elif seats != expected_seats:
            raise ValueError("todas as rodadas Delphi devem usar as mesmas cadeiras")
        median_value = float(statistics.median(scores))
        iqr_value = _percentile(scores, 0.75) - _percentile(scores, 0.25)
        qualifies = median_value >= float(median_target) and iqr_value <= float(iqr_target)
        summaries.append({
            "numero": expected_number,
            "mediana": median_value,
            "iqr": iqr_value,
            "atingiu_limiares": qualifies,
        })
        last_responses = responses

    stable_tail = summaries[-stability:]
    convergence = len(stable_tail) == stability and all(
        item["atingiu_limiares"] for item in stable_tail
    )
    dissents = [
        {
            "cadeira": item["cadeira"],
            "nota": item["nota"],
            "bloqueadores": item.get("bloqueadores", []),
        }
        for item in last_responses
        if float(item["nota"]) < float(median_target) or item.get("bloqueadores")
    ]
    return {
        "metodo": "delphi",
        "rodadas": summaries,
        "estabilidade_exigida": stability,
        "convergencia_estavel": convergence,
        "dissensos_finais": dissents,
        "estado": "convergencia_consultiva" if convergence else "sem_convergencia_estavel",
        "aprovacao": False,
        "gate_necessario": "Delphi não equivale a consenso nem aprovação",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="validar meta.json")
    validate_parser.add_argument("source", help="arquivo JSON ou - para stdin")

    plan_parser = subparsers.add_parser("plan", help="gerar plano determinístico")
    plan_parser.add_argument("source", help="arquivo JSON ou - para stdin")

    vote_parser = subparsers.add_parser("vote", help="executar Borda, Condorcet ou Delphi")
    vote_parser.add_argument("--method", choices=["borda", "condorcet", "delphi"], required=True)
    vote_parser.add_argument("source", help="arquivo JSON ou - para stdin")

    args = parser.parse_args()
    try:
        payload = load_json(args.source)
        if args.command == "validate":
            result = validate_config(payload)
            emit(result)
            return 0 if result["valid"] else 2
        if args.command == "plan":
            emit(make_plan(payload))
            return 0
        if args.method == "borda":
            result = borda(payload)
        elif args.method == "condorcet":
            result = condorcet(payload)
        else:
            result = delphi(payload)
        emit(result)
        return 0
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        emit({"error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
