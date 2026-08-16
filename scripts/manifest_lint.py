#!/usr/bin/env python3
"""Validate and resolve the canonical local multi-agent manifest."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any


DEFAULT_MANIFEST = Path("~/.agents/multiagent-manifest.json").expanduser()
REQUIRED_COMMANDS = {
    "a2a-status", "a2a-call", "a2a-broadcast", "a2a-team", "a2a-debate",
    "a2a-consensus", "a2a-ensemble", "council", "council-high", "llm-council",
    "multi-debate", "pal-council", "sage-debate", "consenso",
    "loop-debate-agentes", "redacao-juridica-consensual", "workflow-agentes",
    "pipeline-agentes", "dag-agentes", "swarm-agentes", "map-reduce-agentes",
    "torneio-agentes", "votacao-agentes", "roteamento-adaptativo", "council-list",
    "council-replay", "council-revisit", "council-outcome", "multiagente",
    "bridge-agentes",
}
REQUIRED_SEAT_ROUTES = {
    "claude": "claude",
    "grok": "cursor",
    "kimi": "kimi",
    "gemini": "antigravity",
}
REQUIRED_CLAUDE_MODEL = "claude-opus-5"
REQUIRED_GROK_MODEL = "cursor-grok-4.6-high"
REQUIRED_GROK_OFFICIAL_MODEL = "grok-4.6"
REQUIRED_KIMI_MODEL = "kimi-code/k3"
REQUIRED_GEMINI_MODEL = "gemini-3.7-flash-high"
REQUIRED_OPENCODE_MODEL = "opencode-go/glm-5.3"
REQUIRED_MAX_EFFORT_SEATS = {"kimi", "glm", "deepseek", "qwen"}
CANONICAL_ENTRYPOINTS = {
    "consenso", "loop-debate-agentes", "workflow-agentes", "multiagente",
    "bridge-agentes"
}


def default_output_policy() -> dict[str, Any]:
    return {
        "contract": "adaptive_output_v1",
        "default_policy": "adaptive_up_to_native_max",
        "policies": ["adaptive_up_to_native_max", "concise_soft_target"],
        "native_route_limit_is_ceiling": True,
        "force_fill": False,
        "global_max_output_tokens": None,
        "phase_word_targets_are_soft": True,
        "continuation": {"approval_requires_complete_output": True},
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
        "destructive_actions_require_task_scope": True,
        "external_side_effects_require_task_scope": True,
    }


def expand(raw: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(raw))).resolve()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"manifesto ausente: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"manifesto JSON inválido: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("a raiz do manifesto deve ser um objeto")
    return data


def expected_routing_yaml(data: dict[str, Any]) -> str:
    seats = data["seats"]
    routes = data["routes"]
    output = data.get("output") or default_output_policy()
    filesystem = data.get("filesystem") or default_filesystem_policy()

    def route_block(seat: str, cli: str, notes: str) -> list[str]:
        entry = seats[seat]
        route = routes[entry["route"]]
        lines = [
            f"  {seat}:",
            f"    cli: {cli}",
            f"    binary: {route['binary']}",
            f"    provider: {entry.get('provider') or 'não fixado'}",
        ]
        if entry.get("default_model"):
            lines.append(f"    default_model: {entry['default_model']}")
        if entry.get("default_effort"):
            lines.append(f"    default_effort: {entry['default_effort']}")
        policy = {
            "fixed_default": "fixed_default",
            "fixed_per_route": "fixed_per_route",
        }.get(entry.get("model_policy"), f"preserve_requested_{seat}_model")
        lines.extend([
            f"    model_policy: {policy}",
            f"    notes: {notes}",
            "",
        ])
        return lines

    lines = [
        "# GENERATED COMPATIBILITY VIEW.",
        "# Source of truth: ~/.agents/multiagent-manifest.json",
        "# Do not edit routes here; update the JSON manifest and validate/render this view.",
        "version: 1",
        f"policy: {data['policy']}",
        f"fallback: {data['fallback']}",
        f"output_policy: {output['default_policy']}",
        f"output_force_fill: {str(output['force_fill']).lower()}",
        f"filesystem_policy: {filesystem['default_policy']}",
        f"filesystem_scope: {filesystem['directory_scope']}",
        "",
        "routes:",
    ]
    lines += route_block(
        "claude", "claude",
        "Claude deve usar Claude Opus 5 exclusivamente pelo Claude Code CLI.",
    )
    lines += route_block(
        "codex", "codex",
        "Codex deve usar gpt-5.6-sol com esforço xhigh pelo Codex CLI.",
    )
    grok_lines = route_block(
        "grok", "cursor",
        "Grok usa Cursor por padrão; a rota grok_official pode ser selecionada explicitamente. "
        "Cada rota preserva seu modelo fixo e nunca há fallback silencioso.",
    )
    grok_lines[-1:-1] = [
        "    allowed_routes: [cursor, grok_official]",
        "    models_by_route: {cursor: cursor-grok-4.6-high, grok_official: grok-4.6}",
        "    effort_by_route: {cursor: high, grok_official: xhigh}",
        "    silent_fallback: false",
    ]
    lines += grok_lines
    lines += route_block(
        "kimi", "kimi",
        "Kimi K3 deve ser invocado pelo Kimi Code CLI oficial com esforço max obrigatório.",
    )
    lines += route_block(
        "gemini", "antigravity",
        "Gemini 3.7 Flash High deve ser invocado pelo Antigravity CLI.",
    )
    lines += route_block(
        "opencode", "opencode",
        "OpenCode usa GLM-5.3 por padrão e preserva outro modelo solicitado; GLM, DeepSeek e Qwen exigem esforço max.",
    )
    return "\n".join(lines).rstrip() + "\n"


def validate_manifest(data: dict[str, Any], check_binaries: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if data.get("manifest_version") != 1:
        errors.append("manifest_version deve ser 1")
    if data.get("policy") != "strict":
        errors.append("policy deve ser strict")
    if data.get("fallback") != "pause_and_report":
        errors.append("fallback deve ser pause_and_report")

    routes = data.get("routes")
    seats = data.get("seats")
    commands = data.get("commands")
    consensus = data.get("consensus")
    collegiate = data.get("collegiate_decision")
    output = data.get("output")
    filesystem = data.get("filesystem")
    native_sessions = data.get("native_sessions")
    durable_execution = data.get("durable_execution")
    provenance_contract = data.get("provenance")
    identity_policy = data.get("identity_policy")
    if not isinstance(routes, dict) or not routes:
        errors.append("routes deve ser objeto não vazio")
        routes = {}
    if not isinstance(seats, dict) or not seats:
        errors.append("seats deve ser objeto não vazio")
        seats = {}
    if not isinstance(commands, dict):
        errors.append("commands deve ser objeto")
        commands = {}
    if not isinstance(consensus, dict):
        errors.append("consensus deve ser objeto")
        consensus = {}
    if collegiate is None:
        warnings.append("manifesto legado sem collegiate_decision; modalidades colegiadas ficam inativas")
        collegiate = {}
    elif not isinstance(collegiate, dict):
        errors.append("collegiate_decision deve ser objeto")
        collegiate = {}
    if output is None:
        warnings.append("manifesto legado sem output; aplicado adaptive_output_v1 em memória")
        output = default_output_policy()
    elif not isinstance(output, dict):
        errors.append("output deve ser objeto")
        output = {}
    if filesystem is None:
        warnings.append("manifesto legado sem filesystem; aplicado scoped_full_tools_v2 em memória")
        filesystem = default_filesystem_policy()
    elif not isinstance(filesystem, dict):
        errors.append("filesystem deve ser objeto")
        filesystem = {}
    if not isinstance(native_sessions, dict):
        errors.append("native_sessions deve ser objeto")
        native_sessions = {}
    if not isinstance(durable_execution, dict):
        errors.append("durable_execution deve ser objeto")
        durable_execution = {}
    if not isinstance(provenance_contract, dict):
        errors.append("provenance deve ser objeto")
        provenance_contract = {}
    if not isinstance(identity_policy, dict):
        errors.append("identity_policy deve ser objeto")
        identity_policy = {}

    for seat, expected_route in REQUIRED_SEAT_ROUTES.items():
        actual = seats.get(seat, {}).get("route") if isinstance(seats.get(seat), dict) else None
        if actual != expected_route:
            errors.append(f"rota obrigatória inválida: {seat} deve usar {expected_route}, recebeu {actual}")

    claude = seats.get("claude", {}) if isinstance(seats.get("claude"), dict) else {}
    if claude.get("default_model") != REQUIRED_CLAUDE_MODEL:
        errors.append(f"modelo obrigatório do Claude deve ser {REQUIRED_CLAUDE_MODEL}")
    if claude.get("model_policy") != "fixed_default":
        errors.append("Claude deve usar model_policy=fixed_default")

    grok = seats.get("grok", {}) if isinstance(seats.get("grok"), dict) else {}
    if grok.get("default_model") != REQUIRED_GROK_MODEL:
        errors.append(f"modelo obrigatório do Grok deve ser {REQUIRED_GROK_MODEL}")
    if grok.get("model_policy") != "fixed_per_route":
        errors.append("Grok deve usar model_policy=fixed_per_route")
    if grok.get("allowed_routes") != ["cursor", "grok_official"]:
        errors.append("Grok deve permitir exatamente cursor e grok_official")
    if grok.get("models_by_route") != {
        "cursor": REQUIRED_GROK_MODEL,
        "grok_official": REQUIRED_GROK_OFFICIAL_MODEL,
    }:
        errors.append("Grok deve fixar um modelo compatível para cada rota")
    if grok.get("silent_fallback") is not False:
        errors.append("Grok não pode fazer fallback silencioso entre rotas")

    kimi = seats.get("kimi", {}) if isinstance(seats.get("kimi"), dict) else {}
    if kimi.get("default_model") != REQUIRED_KIMI_MODEL:
        errors.append(f"modelo padrão do Kimi deve ser {REQUIRED_KIMI_MODEL}")
    if kimi.get("context_window_tokens") != 1048576:
        errors.append("Kimi K3 deve declarar a janela integral de 1.048.576 tokens")

    for seat_name in sorted(REQUIRED_MAX_EFFORT_SEATS):
        entry = seats.get(seat_name, {}) if isinstance(seats.get(seat_name), dict) else {}
        if entry.get("default_effort") != "max":
            errors.append(f"{seat_name} deve usar default_effort=max")
        if entry.get("effort_policy") != "fixed_max":
            errors.append(f"{seat_name} deve usar effort_policy=fixed_max")

    gemini = seats.get("gemini", {}) if isinstance(seats.get("gemini"), dict) else {}
    if gemini.get("default_model") != REQUIRED_GEMINI_MODEL:
        errors.append(f"modelo padrão do Gemini deve ser {REQUIRED_GEMINI_MODEL}")

    opencode = seats.get("opencode", {}) if isinstance(seats.get("opencode"), dict) else {}
    if opencode.get("default_model") != REQUIRED_OPENCODE_MODEL:
        errors.append(f"modelo padrão do OpenCode deve ser {REQUIRED_OPENCODE_MODEL}")
    if opencode.get("model_policy") != "preserve_requested":
        errors.append("OpenCode deve preservar modelos solicitados explicitamente")

    for seat, entry in seats.items():
        if not isinstance(entry, dict):
            errors.append(f"seat {seat} deve ser objeto")
            continue
        route = entry.get("route")
        if route not in routes:
            errors.append(f"seat {seat} refere rota inexistente: {route}")
        aliases = entry.get("aliases", [])
        if not isinstance(aliases, list):
            errors.append(f"aliases de {seat} deve ser lista")

    for route, entry in routes.items():
        if not isinstance(entry, dict) or not entry.get("binary"):
            errors.append(f"rota {route} precisa de binary")
            continue
        output_control = entry.get("output_control")
        filesystem_control = entry.get("filesystem_control")
        if output_control is None:
            warnings.append(f"rota legada sem output_control: {route}; assumido native_route_ceiling")
        elif not isinstance(output_control, dict):
            errors.append(f"output_control de {route} deve ser objeto")
        elif output_control.get("mode") != "native_route_ceiling":
            errors.append(f"output_control.mode inválido em {route}")
        if filesystem_control is None:
            warnings.append(f"rota legada sem filesystem_control: {route}; assumido full_tools_host_identity")
            filesystem_control = {
                "access": "full_tools_host_identity",
                "directory_scope": "explicit_advisory",
                "auto_approve": True,
            }
        elif not isinstance(filesystem_control, dict):
            errors.append(f"filesystem_control de {route} deve ser objeto")
        else:
            if filesystem_control.get("access") != "full_tools_host_identity":
                errors.append(f"filesystem_control.access inválido em {route}")
            if filesystem_control.get("directory_scope") != "explicit_advisory":
                errors.append(f"filesystem_control.directory_scope inválido em {route}")
            if filesystem_control.get("auto_approve") is not True:
                errors.append(f"filesystem_control.auto_approve deve ser true em {route}")
        if check_binaries and not shutil.which(str(entry["binary"])):
            warnings.append(f"binário indisponível: {route} -> {entry['binary']}")

    missing = sorted(REQUIRED_COMMANDS - set(commands))
    extra = sorted(set(commands) - REQUIRED_COMMANDS)
    if missing:
        errors.append(f"comandos públicos ausentes: {', '.join(missing)}")
    if extra:
        warnings.append(f"comandos adicionais no manifesto: {', '.join(extra)}")
    for name, entry in commands.items():
        if not isinstance(entry, dict):
            errors.append(f"comando {name} deve ser objeto")
            continue
        target = entry.get("entrypoint")
        if target not in CANONICAL_ENTRYPOINTS:
            errors.append(f"entrypoint inválido em {name}: {target}")
        if target not in commands:
            errors.append(f"comando {name} aponta para entrada ausente: {target}")
        if not entry.get("profile"):
            errors.append(f"comando {name} não declara profile")
        if entry.get("approval_ceiling") not in {"none", "consultivo", "candidate_only", "configured"}:
            errors.append(f"approval_ceiling inválido em {name}")

    expected_modes = {"estrito", "com_decisor", "consultivo", "desativado"}
    expected_policies = {"sempre", "se_necessario", "apenas_primeira", "nenhum"}
    if set(consensus.get("modes", [])) != expected_modes:
        errors.append("consensus.modes diverge do contrato")
    if set(consensus.get("policies", [])) != expected_policies:
        errors.append("consensus.policies diverge do contrato")
    if consensus.get("simulation_can_issue_verdict") is not False:
        errors.append("simulação nunca pode emitir veredito")
    if consensus.get("selection_is_approval") is not False:
        errors.append("seleção nunca pode equivaler a aprovação")
    if consensus.get("rounds_max") != 36 or consensus.get("cycles_max_per_seat") != 12:
        errors.append("limites centrais devem ser 36 rodadas e 12 ciclos")
    if consensus.get("rounds_recommended_max") != 18 or consensus.get("cycles_recommended_max_per_seat") != 6:
        errors.append("limites operacionais recomendados devem ser 18 rodadas e 6 ciclos")
    if consensus.get("auto_extend_if_needed") is not True:
        errors.append("consensus deve permitir extensão automática quando necessária")
    if consensus.get("extension_increment_rounds") != 3 or consensus.get("extension_increment_cycles") != 1:
        errors.append("a extensão deve ocorrer em um ciclo completo por vez")
    if consensus.get("no_progress_cycles_before_stop") != 2:
        errors.append("consensus deve parar após dois ciclos sem progresso")

    if collegiate:
        if collegiate.get("contract") != "decisao_colegiada_v1":
            errors.append("collegiate_decision.contract deve ser decisao_colegiada_v1")
        if collegiate.get("analytic_schema") != "decisao_colegiada_v2":
            errors.append("collegiate_decision.analytic_schema deve ser decisao_colegiada_v2")
        if set(collegiate.get("tally_methods", [])) != {
            "global", "analitico", "hibrido"
        }:
            errors.append("collegiate_decision.tally_methods diverge do contrato")
        if collegiate.get("default_tally_method") != "global":
            errors.append("global deve ser o método de apuração padrão")
        if collegiate.get("analytic_dependency_graph") != "single_parent_forest":
            errors.append("a apuração analítica deve usar floresta de pai único")
        if collegiate.get("analytic_max_reachable_worlds") != 4096:
            errors.append("o limite analítico deve ser 4096 mundos alcançáveis")
        if collegiate.get("hybrid_confirmation_policy") != "bloqueante":
            errors.append("a confirmação híbrida deve ser bloqueante")
        if set(collegiate.get("modalities", [])) != {
            "seriatim", "per_curiam", "opinion_of_court"
        }:
            errors.append("collegiate_decision.modalities diverge do contrato")
        if collegiate.get("default_modality") != "opinion_of_court":
            errors.append("opinion_of_court deve ser a modalidade colegiada padrão")
        if set(collegiate.get("result_rules", [])) != {
            "unanimidade", "maioria_simples", "maioria_qualificada",
            "consenso_estrito", "com_decisor",
        }:
            errors.append("collegiate_decision.result_rules diverge do contrato")
        if set(collegiate.get("join_scopes", [])) != {
            "dispositivo", "proposicao", "secao"
        }:
            errors.append("collegiate_decision.join_scopes diverge do contrato")
        if set(collegiate.get("ratio_statuses", [])) != {
            "unificada", "pluralidade", "somente_resultado", "nao_aplicavel"
        }:
            errors.append("collegiate_decision.ratio_statuses diverge do contrato")
        for field in (
            "seriatim_requires_individual_votes",
            "opinion_of_court_requires_majority_join",
            "preserve_dissent_in_audit",
            "new_hash_invalidates_decision",
            "proclamation_freezes_votes",
        ):
            if collegiate.get(field) is not True:
                errors.append(f"collegiate_decision.{field} deve ser true")
        if collegiate.get("majority_is_consensus") is not False:
            errors.append("maioria colegiada nunca pode equivaler a consenso")

    expected_filesystem_bools = {
        "can_read", "can_create", "can_modify", "can_delete",
        "auto_approve_local_tools", "canonical_write_requires_resolved_role",
        "destructive_actions_require_task_scope", "external_side_effects_require_task_scope",
    }
    if filesystem.get("contract") != "scoped_full_tools_v2":
        errors.append("filesystem.contract deve ser scoped_full_tools_v2")
    if filesystem.get("default_policy") != "project_root_plus_explicit_directories":
        errors.append("filesystem.default_policy deve exigir raiz e diretórios explícitos")
    if filesystem.get("directory_scope") != "explicit_per_invocation":
        errors.append("filesystem.directory_scope deve ser explicit_per_invocation")
    if filesystem.get("implicit_home_scope") is not False:
        errors.append("filesystem.implicit_home_scope deve ser false")
    if filesystem.get("home_scope_requires_explicit_opt_in") is not True:
        errors.append("filesystem.home_scope_requires_explicit_opt_in deve ser true")
    if filesystem.get("full_tool_permissions_within_host_identity") is not True:
        errors.append("filesystem.full_tool_permissions_within_host_identity deve ser true")
    if filesystem.get("os_security_boundary") is not False:
        errors.append("filesystem.os_security_boundary deve ser false")
    for field in sorted(expected_filesystem_bools):
        if filesystem.get(field) is not True:
            errors.append(f"filesystem.{field} deve ser true")

    if provenance_contract.get("contract") != "multiagent_provenance_v1":
        errors.append("provenance.contract deve ser multiagent_provenance_v1")
    if provenance_contract.get("attestation") != "host_hmac_v1":
        errors.append("provenance.attestation deve ser host_hmac_v1")
    for field in (
        "receipt_requires_real_artifact_hash",
        "receipt_requires_observed_model",
        "receipt_requires_confirmed_native_session_or_isolated_execution",
        "strict_consensus_requires_one_receipt_per_seat_per_stability_evaluation",
        "replay_is_fail_closed",
        "secrets_removed_from_child_environment",
    ):
        if provenance_contract.get(field) is not True:
            errors.append(f"provenance.{field} deve ser true")
    if provenance_contract.get("same_user_unrestricted_shell_is_cryptographic_boundary") is not False:
        errors.append("provenance deve declarar que shell irrestrito do mesmo usuário não é boundary")
    if identity_policy.get("aliases_never_create_independent_seats") is not True:
        errors.append("aliases nunca podem criar cadeiras independentes")
    if identity_policy.get("local_persona_homonyms_count_as_external_seat") is not False:
        errors.append("personas locais homônimas não podem contar como cadeiras externas")
    if identity_policy.get("silent_substitution") is not False:
        errors.append("identity_policy.silent_substitution deve ser false")

    if native_sessions.get("contract") != "native_session_mirror_v1":
        errors.append("native_sessions.contract deve ser native_session_mirror_v1")
    if native_sessions.get("default_persist") is not False:
        errors.append("native_sessions.default_persist deve ser false")
    if native_sessions.get("central_history_is_canonical") is not True:
        errors.append("o histórico central deve permanecer canônico")
    if native_sessions.get("native_history_is_mirror_only") is not True:
        errors.append("sessões nativas devem ser apenas espelhos")
    if native_sessions.get("native_history_never_proves_consensus") is not True:
        errors.append("sessões nativas nunca podem provar consenso")
    expected_native_routes = {
        "claude", "codex", "gemini", "antigravity", "cursor", "grok_official",
        "opencode", "kimi"
    }
    if set((native_sessions.get("routes") or {}).keys()) != expected_native_routes:
        errors.append("native_sessions.routes diverge das rotas executáveis")

    if durable_execution.get("contract") != "durable_execution_v1":
        errors.append("durable_execution.contract deve ser durable_execution_v1")
    if durable_execution.get("default_profile") != "standard":
        errors.append("durable_execution.default_profile deve ser standard")
    if durable_execution.get("opt_in_profile") != "durable_5d_v1":
        errors.append("durable_execution.opt_in_profile deve ser durable_5d_v1")
    if durable_execution.get("clock") != "elapsed_wall_time":
        errors.append("durable_execution.clock deve ser elapsed_wall_time")
    if durable_execution.get("max_elapsed_seconds") != 432000:
        errors.append("durable_execution.max_elapsed_seconds deve ser 432000")
    if durable_execution.get("offline_counts_toward_deadline") is not True:
        errors.append("tempo offline deve contar no deadline durável")
    if durable_execution.get("per_call_timeout_seconds") != 1800:
        errors.append("durable_execution.per_call_timeout_seconds deve ser 1800")
    if durable_execution.get("per_call_exception_max_seconds") != 3600:
        errors.append("durable_execution.per_call_exception_max_seconds deve ser 3600")
    if durable_execution.get("checkpoint_write") != "atomic":
        errors.append("durable_execution.checkpoint_write deve ser atomic")
    if set(durable_execution.get("checkpoint_after", [])) != {
        "call", "round", "cycle", "version", "node", "wave", "join"
    }:
        errors.append("durable_execution.checkpoint_after diverge do contrato")
    if durable_execution.get("resume_after_process_or_host_restart") is not True:
        errors.append("execução durável deve permitir retomada após reinício")
    if durable_execution.get("idempotency") != "event_id+input_sha256":
        errors.append("durable_execution.idempotency deve ser event_id+input_sha256")
    if durable_execution.get("silent_route_or_model_substitution") is not False:
        errors.append("execução durável não pode substituir rota ou modelo silenciosamente")

    expected_output_policies = {"adaptive_up_to_native_max", "concise_soft_target"}
    if output.get("contract") != "adaptive_output_v1":
        errors.append("output.contract deve ser adaptive_output_v1")
    if output.get("default_policy") != "adaptive_up_to_native_max":
        errors.append("output.default_policy deve permitir até o teto nativo")
    if set(output.get("policies", [])) != expected_output_policies:
        errors.append("output.policies diverge do contrato")
    if output.get("native_route_limit_is_ceiling") is not True:
        errors.append("o limite nativo da rota deve ser tratado como teto")
    if output.get("force_fill") is not False:
        errors.append("a política de saída não pode obrigar preenchimento")
    if output.get("global_max_output_tokens") is not None:
        errors.append("não deve existir teto global artificial de saída")
    if output.get("phase_word_targets_are_soft") is not True:
        errors.append("metas de palavras por fase devem ser flexíveis")
    continuation = output.get("continuation", {})
    if not isinstance(continuation, dict) or continuation.get("approval_requires_complete_output") is not True:
        errors.append("output.continuation deve impedir aprovação de saída incompleta")

    state = data.get("state", {})
    if not isinstance(state, dict) or not state.get("canonical_root"):
        errors.append("state.canonical_root é obrigatório")

    return {
        "valid": not errors,
        "contract": data.get("contract"),
        "manifest_version": data.get("manifest_version"),
        "commands": len(commands),
        "seats": sorted(seats),
        "routes": sorted(routes),
        "errors": errors,
        "warnings": warnings,
    }


def resolve_seat(data: dict[str, Any], requested: str, model: str | None) -> dict[str, Any]:
    seats = data["seats"]
    canonical = requested
    if requested not in seats:
        matches = [name for name, entry in seats.items() if requested in entry.get("aliases", [])]
        if len(matches) != 1:
            raise ValueError(f"seat desconhecida ou ambígua: {requested}")
        canonical = matches[0]
    seat = seats[canonical]
    if seat.get("model_policy") == "fixed_default":
        fixed = seat.get("default_model")
        if model in seat.get("aliases", []):
            model = fixed
        elif model and model != fixed:
            raise ValueError(
                f"modelo incompatível para {canonical}: a política local fixa {fixed}, recebeu {model}"
            )
        model = fixed
    route_name = seat["route"]
    route = data["routes"][route_name]
    output = data.get("output") or default_output_policy()
    filesystem = data.get("filesystem") or default_filesystem_policy()
    native_sessions = data.get("native_sessions") or {}
    return {
        "seat": canonical,
        "requested": requested,
        "route": route_name,
        "binary": route["binary"],
        "host": route.get("host"),
        "model": model or seat.get("default_model"),
        "default_effort": seat.get("default_effort"),
        "effort_policy": seat.get("effort_policy"),
        "context_window_tokens": seat.get("context_window_tokens"),
        "model_fixed": bool(model or seat.get("default_model")),
        "provider": seat.get("provider"),
        "fallback": data["fallback"],
        "output_policy": output["default_policy"],
        "output_control": route.get("output_control") or {"mode": "native_route_ceiling", "max_output_tokens_flag": None},
        "filesystem_policy": filesystem["default_policy"],
        "filesystem_control": route.get("filesystem_control"),
        "native_session_policy": {
            "default_persist": native_sessions.get("default_persist", False),
            "central_history_is_canonical": native_sessions.get("central_history_is_canonical", True),
            "route": (native_sessions.get("routes") or {}).get(route_name),
        },
    }


def emit(payload: Any) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--check-binaries", action="store_true")
    validate.add_argument("--check-routing", action="store_true")
    seat = sub.add_parser("resolve-seat")
    seat.add_argument("seat")
    seat.add_argument("--model")
    command = sub.add_parser("resolve-command")
    command.add_argument("name")
    routing = sub.add_parser("render-routing")
    routing.add_argument("--check")
    args = parser.parse_args()

    try:
        path = expand(args.manifest)
        data = load_manifest(path)
        report = validate_manifest(data, getattr(args, "check_binaries", False))
        if not report["valid"]:
            emit(report)
            return 2
        if args.command == "validate":
            if args.check_routing:
                legacy = expand(data["legacy"]["routing_file"])
                expected = expected_routing_yaml(data)
                actual = legacy.read_text(encoding="utf-8") if legacy.is_file() else None
                report["routing_view"] = "ok" if actual == expected else "drift"
                if actual != expected:
                    report["valid"] = False
                    report["errors"].append(f"visão YAML divergente: {legacy}")
            emit(report)
            return 0 if report["valid"] else 2
        if args.command == "resolve-seat":
            emit(resolve_seat(data, args.seat, args.model))
            return 0
        if args.command == "resolve-command":
            if args.name not in data["commands"]:
                raise ValueError(f"comando não registrado: {args.name}")
            emit({"command": args.name, **data["commands"][args.name]})
            return 0
        rendered = expected_routing_yaml(data)
        if args.check:
            target = expand(args.check)
            if not target.is_file() or target.read_text(encoding="utf-8") != rendered:
                emit({"valid": False, "error": f"visão de roteamento divergente: {target}"})
                return 2
            emit({"valid": True, "routing_file": str(target)})
            return 0
        sys.stdout.write(rendered)
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        emit({"valid": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
