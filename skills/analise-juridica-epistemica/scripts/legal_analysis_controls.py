#!/usr/bin/env python3
"""Deterministic controls for advanced legal analysis modules."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


INPUT_CONTRACTS = {
    "research-fusion": ("legal_research_bundle_v1", "query_id", "providers"),
    "precedent-factors": ("precedent_factor_bundle_v1", "case_id", "factors", "precedents"),
    "strategy-tree": ("procedural_strategy_bundle_v1", "case_id", "state", "objectives", "actions"),
    "credibility-matrix": ("credibility_bundle_v1", "case_id", "claims", "evidence"),
    "elicitation-queue": ("tacit_elicitation_bundle_v1", "case_id", "unknowns"),
    "persuasion-gate": ("persuasion_bundle_v1", "artifact_id", "content_hash_base", "argument_map", "draft_manifest"),
}
RECEIPT_VERSIONS = {
    "research-fusion": "legal_research_receipt_v1",
    "precedent-factors": "precedent_factor_receipt_v1",
    "strategy-tree": "procedural_strategy_receipt_v1",
    "credibility-matrix": "credibility_receipt_v1",
    "elicitation-queue": "tacit_elicitation_receipt_v1",
    "persuasion-gate": "persuasion_receipt_v1",
}


def validate_input_contract(command: str, payload: dict) -> list[dict]:
    expected_version, *required = INPUT_CONTRACTS[command]
    if not isinstance(payload, dict):
        return [{"code": "INVALID_INPUT_CONTRACT",
                 "message": "The input bundle must be a JSON object."}]
    missing = [key for key in required if key not in payload or payload[key] in (None, "")]
    violations = []
    if payload.get("schema_version") != expected_version or missing:
        violations.append({
            "code": "INVALID_INPUT_CONTRACT",
            "expected_schema_version": expected_version,
            "missing_fields": missing,
            "message": "The bundle does not satisfy the selected control's input contract.",
        })
    list_fields = {
        "research-fusion": ("providers",),
        "precedent-factors": ("factors", "precedents"),
        "strategy-tree": ("objectives", "actions"),
        "credibility-matrix": ("claims", "evidence"),
        "elicitation-queue": ("unknowns",),
        "persuasion-gate": ("argument_map",),
    }
    for field in list_fields[command]:
        value = payload.get(field)
        if value is None and field in missing:
            continue
        if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
            violations.append({
                "code": "INVALID_INPUT_CONTRACT", "field": field,
                "message": f"{field} must be an array of objects.",
            })
    if command == "research-fusion" and isinstance(payload.get("providers"), list):
        for index, provider in enumerate(payload["providers"]):
            if not isinstance(provider, dict):
                continue
            if any(not isinstance(provider.get(field, []), list) for field in ("queries", "results")):
                violations.append({
                    "code": "INVALID_INPUT_CONTRACT", "field": f"providers[{index}]",
                    "message": "Provider queries and results must be arrays.",
                })
    if command == "persuasion-gate" and not violations:
        base = payload["content_hash_base"]
        draft = payload["draft_manifest"]
        if (
            not isinstance(base, str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", base)
            or not isinstance(payload["argument_map"], list)
            or not payload["argument_map"]
            or not isinstance(draft, dict)
            or not all(draft.get(key) for key in ("genre", "audience", "tone"))
            or "claim_ids" not in draft
        ):
            violations.append({
                "code": "INVALID_INPUT_CONTRACT",
                "message": "Persuasion requires a frozen map, base hash and complete draft manifest.",
            })
    return violations


def research_fusion(bundle: dict) -> dict:
    violations = []
    requirements = bundle.get("requirements", {})
    providers = bundle.get("providers", [])
    primary_providers = [item for item in providers if item.get("role") == "primary"]
    primary_available = any(
        item.get("status") in {"available", "partial"} for item in primary_providers
    )

    if requirements.get("primary_required") and not primary_available:
        violations.append(
            {
                "code": "PRIMARY_PROVIDER_UNAVAILABLE",
                "message": "Primary legal sources are unavailable; local RAG remains discovery-only.",
            }
        )

    query_stances = {
        query.get("stance")
        for provider in primary_providers
        if provider.get("status") in {"available", "partial"}
        for query in provider.get("queries", [])
    }
    if requirements.get("adverse_search_required") and "opposes" not in query_stances:
        violations.append(
            {
                "code": "ADVERSE_SEARCH_MISSING",
                "message": "Research must include an explicit contrary-authority query.",
            }
        )

    primary_coverage_complete = bool(primary_providers) and all(
        item.get("status") == "available"
        and item.get("coverage", {}).get("complete") is True
        and bool(item.get("coverage", {}).get("sources_checked"))
        and bool(item.get("queries"))
        for item in primary_providers
    )
    if requirements.get("negative_claim_requested") and not primary_coverage_complete:
        violations.append(
            {
                "code": "NEGATIVE_SEARCH_UNSUPPORTED",
                "message": "Absence cannot be asserted without complete primary-source coverage.",
            }
        )

    for provider in providers:
        if provider.get("role") != "discovery":
            continue
        for result in provider.get("results", []):
            if not result.get("verified_primary"):
                continue
            violations.append(
                {
                    "code": "DISCOVERY_PROVIDER_CLAIMS_PRIMARY",
                    "subject": result.get("id"),
                    "provider": provider.get("id"),
                    "message": "Discovery providers cannot establish primary-source verification.",
                }
            )

    aggregated: dict[str, dict] = {}
    ranked_seen: set[tuple[str, str]] = set()
    for provider in providers:
        weight = 3.0 if provider.get("role") == "primary" else 1.0
        for result in provider.get("results", []):
            key = result.get("canonical_key") or result.get("id")
            rank = max(1, int(result.get("rank", 1)))
            current = aggregated.setdefault(
                key,
                {
                    **result,
                    "canonical_key": key,
                    "verified_primary": False,
                    "rrf_score": 0.0,
                    "providers": [],
                    "origins": [],
                },
            )
            if (provider.get("id"), key) not in ranked_seen:
                current["rrf_score"] += weight / (60 + rank)
                ranked_seen.add((provider.get("id"), key))
            current["providers"].append(provider.get("id"))
            current["origins"].append(
                {
                    "provider": provider.get("id"),
                    "id": result.get("id"),
                    "query_id": result.get("query_id"),
                    "rank": rank,
                    "verified_primary": bool(
                        provider.get("role") == "primary"
                        and result.get("verified_primary")
                    ),
                }
            )
            if provider.get("role") == "primary" and result.get("verified_primary"):
                if not current["verified_primary"]:
                    for field in ("id", "title", "source_kind", "official_url", "stance"):
                        if field in result:
                            current[field] = result[field]
                current["verified_primary"] = True

    fused = sorted(
        aggregated.values(),
        key=lambda item: (-item["rrf_score"], item["canonical_key"]),
    )
    for item in fused:
        item["rrf_score"] = round(item["rrf_score"], 8)
        item["providers"] = sorted(set(item["providers"]))
        item["origins"].sort(key=lambda origin: (origin["provider"], origin["rank"], origin["id"]))

    verified_primary_results = [
        result
        for provider in primary_providers
        for result in provider.get("results", [])
        if result.get("verified_primary")
    ]
    if requirements.get("primary_required") and not verified_primary_results and not primary_coverage_complete:
        violations.append(
            {
                "code": "PRIMARY_EVIDENCE_NOT_VERIFIED",
                "message": "No verified primary item or scoped complete no-hit search is recorded.",
            }
        )
    if verified_primary_results:
        status = "verified"
    elif primary_coverage_complete:
        status = "verified_no_hits"
    elif fused:
        status = "discovery_only" if not primary_available else "degraded"
    else:
        status = "unavailable"

    return {
        "schema_version": "legal_research_receipt_v1",
        "query_id": bundle.get("query_id"),
        "conforms": not violations,
        "research_status": status,
        "violations": violations,
        "warnings": [],
        "fused_results": fused,
        "provider_status": {
            item.get("id"): item.get("status") for item in providers
        },
        "scope": {item.get("id"): item.get("coverage", {}) for item in providers},
        "query_log": {item.get("id"): item.get("queries", []) for item in providers},
    }


def precedent_factors(bundle: dict) -> dict:
    factors = {item["id"]: item for item in bundle.get("factors", [])}
    total_weight = sum(max(1, int(item.get("weight", 1))) for item in factors.values())
    comparisons = []
    excluded = []

    for precedent in bundle.get("precedents", []):
        if not precedent.get("verified_primary"):
            excluded.append(precedent.get("id"))
            continue
        matched = []
        distinguished = []
        unknown = []
        matched_weight = 0
        compared_weight = 0
        precedent_factors_map = precedent.get("factors", {})
        for factor_id, factor in factors.items():
            case_value = factor.get("value")
            precedent_value = precedent_factors_map.get(factor_id, "unknown")
            weight = max(1, int(factor.get("weight", 1)))
            if case_value == "unknown" or precedent_value == "unknown":
                unknown.append(factor_id)
                continue
            compared_weight += weight
            if case_value == precedent_value:
                matched.append(factor_id)
                matched_weight += weight
            else:
                distinguished.append(factor_id)
        comparisons.append(
            {
                "id": precedent.get("id"),
                "outcome": precedent.get("outcome"),
                "matched_factors": sorted(matched),
                "distinguished_factors": sorted(distinguished),
                "unknown_factors": sorted(unknown),
                "matched_weight": matched_weight,
                "compared_weight": compared_weight,
                "coverage": round(compared_weight / total_weight, 6) if total_weight else 0.0,
                "similarity": (
                    round(matched_weight / total_weight, 6)
                    if total_weight and compared_weight
                    else None
                ),
            }
        )

    comparisons.sort(
        key=lambda item: (
            -(item["similarity"] if item["similarity"] is not None else -1),
            item["id"],
        )
    )

    def best(outcome: str) -> str | None:
        return next(
            (item["id"] for item in comparisons
             if item["outcome"] == outcome and item["similarity"] is not None),
            None,
        )

    return {
        "schema_version": "precedent_factor_receipt_v1",
        "case_id": bundle.get("case_id"),
        "conforms": True,
        "violations": [],
        "comparisons": comparisons,
        "excluded_precedents": sorted(excluded),
        "best_supporting": best("supports"),
        "best_opposing": best("opposes"),
        "human_judgment_required": True,
    }


def strategy_tree(bundle: dict) -> dict:
    facts = set(bundle.get("state", {}).get("facts", []))
    grants = set(bundle.get("state", {}).get("grants", []))
    must_objectives = {
        item.get("id")
        for item in bundle.get("objectives", [])
        if item.get("priority") == "must"
    }
    feasible = []
    robust = []
    blocked = []
    human_decisions = []

    for action in bundle.get("actions", []):
        unmet = sorted(set(action.get("preconditions", [])) - facts)
        if unmet:
            blocked.append(
                {
                    "id": action.get("id"),
                    "reason": "unmet_preconditions",
                    "unmet": unmet,
                }
            )
            continue
        if action.get("authority_required") and action.get("grant_id") not in grants:
            blocked.append(
                {
                    "id": action.get("id"),
                    "reason": "authority_required",
                    "grant_id": action.get("grant_id"),
                }
            )
            human_decisions.append(
                {
                    "type": "strategy_authorization",
                    "action": action.get("id"),
                    "owner": action.get("authority_owner"),
                    "reversible": bool(action.get("reversible")),
                }
            )
            continue

        feasible.append(action.get("id"))
        responses = action.get("responses", [])
        if responses and all(
            must_objectives <= set(response.get("satisfies", []))
            for response in responses
        ):
            robust.append(action.get("id"))

    return {
        "schema_version": "procedural_strategy_receipt_v1",
        "case_id": bundle.get("case_id"),
        "conforms": True,
        "violations": [],
        "feasible_actions": sorted(feasible),
        "robust_actions": sorted(robust),
        "blocked_actions": sorted(blocked, key=lambda item: item["id"]),
        "required_human_decisions": human_decisions,
        "probabilities_inferred": False,
        "not_execution_authorization": True,
    }


def credibility_matrix(bundle: dict) -> dict:
    evidence = bundle.get("evidence", [])
    profiles = []
    for claim in bundle.get("claims", []):
        related = [item for item in evidence if item.get("claim_id") == claim.get("id")]
        profiles.append(
            {
                "id": claim.get("id"),
                "statement": claim.get("statement"),
                "supporting_evidence": sorted(
                    item.get("id")
                    for item in related
                    if item.get("stance") == "supports"
                ),
                "opposing_evidence": sorted(
                    item.get("id")
                    for item in related
                    if item.get("stance") == "opposes"
                ),
                "neutral_evidence": sorted(
                    item.get("id")
                    for item in related
                    if item.get("stance") not in {"supports", "opposes"}
                ),
            }
        )

    known_ids = {item.get("id") for item in evidence}
    contradiction_pairs = set()
    for item in evidence:
        for other in item.get("contradicts", []):
            if other in known_ids and other != item.get("id"):
                contradiction_pairs.add(tuple(sorted((item.get("id"), other))))

    dimension_gaps = []
    for item in evidence:
        unknown = sorted(
            key
            for key, value in item.get("dimensions", {}).items()
            if value in {None, "unknown", "not_assessed"}
        )
        if unknown:
            dimension_gaps.append({"evidence_id": item.get("id"), "dimensions": unknown})

    return {
        "schema_version": "credibility_receipt_v1",
        "case_id": bundle.get("case_id"),
        "conforms": True,
        "violations": [],
        "claim_profiles": profiles,
        "contradictions": [list(item) for item in sorted(contradiction_pairs)],
        "dimension_gaps": dimension_gaps,
        "human_judgment_required": True,
        "automated_truth_verdict": None,
    }


def elicitation_queue(bundle: dict) -> dict:
    impact_values = {"low": 1, "medium": 2, "high": 3, "decisive": 4}
    reversibility_values = {"reversible": 1, "costly": 3, "irreversible": 4}
    queue = []
    violations = []
    for unknown in bundle.get("unknowns", []):
        if not unknown.get("question") or not unknown.get("owner"):
            violations.append(
                {
                    "code": "ELICITATION_TARGET_MISSING",
                    "subject": unknown.get("id"),
                    "message": "Each unknown needs a concrete question and human owner.",
                }
            )
            continue
        impact = impact_values.get(unknown.get("impact"), 1)
        branching = max(1, min(4, int(unknown.get("branching", 1))))
        reversibility = reversibility_values.get(unknown.get("reversibility"), 1)
        ease = max(1, min(4, int(unknown.get("ease", 1))))
        score = impact * branching * reversibility + ease
        queue.append(
            {
                "id": unknown.get("id"),
                "question": unknown.get("question"),
                "owner": unknown.get("owner"),
                "priority_score": score,
                "components": {
                    "impact": impact,
                    "branching": branching,
                    "irreversibility": reversibility,
                    "ease": ease,
                },
                "effect_if_unanswered": unknown.get("effect_if_unanswered"),
            }
        )
    queue.sort(key=lambda item: (-item["priority_score"], item["id"]))
    return {
        "schema_version": "tacit_elicitation_receipt_v1",
        "case_id": bundle.get("case_id"),
        "conforms": not violations,
        "violations": violations,
        "queue": queue,
        "score_is_priority_not_probability": True,
    }


def persuasion_gate(bundle: dict) -> dict:
    violations = []
    argument_map = bundle.get("argument_map", [])
    required = {item.get("id") for item in argument_map if item.get("required")}
    draft = bundle.get("draft_manifest", {})
    present = set(draft.get("claim_ids", []))
    missing = sorted(required - present)
    if missing:
        violations.append(
            {
                "code": "REQUIRED_ARGUMENT_MISSING",
                "subjects": missing,
                "message": "Persuasive rewrite omitted required argument-map entries.",
            }
        )

    unsupported = sorted(
        item.get("id")
        for item in draft.get("new_claims", [])
        if not item.get("source_refs")
    )
    if unsupported:
        violations.append(
            {
                "code": "UNSUPPORTED_NEW_CLAIM",
                "subjects": unsupported,
                "message": "New persuasive claims require explicit source references.",
            }
        )

    if draft.get("content_hash_base") != bundle.get("content_hash_base"):
        violations.append(
            {
                "code": "CONTENT_BASE_HASH_MISMATCH",
                "expected": bundle.get("content_hash_base"),
                "actual": draft.get("content_hash_base"),
                "message": "Draft was not produced from the frozen argument map base.",
            }
        )

    return {
        "schema_version": "persuasion_receipt_v1",
        "artifact_id": bundle.get("artifact_id"),
        "conforms": not violations,
        "violations": violations,
        "missing_arguments": missing,
        "unsupported_new_claims": unsupported,
        "coverage": round((len(required) - len(missing)) / max(len(required), 1), 6),
        "genre": draft.get("genre"),
        "audience": draft.get("audience"),
        "tone": draft.get("tone"),
        "human_editor_required": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    research = subparsers.add_parser("research-fusion")
    research.add_argument("input", type=Path)
    research.add_argument("--out", type=Path)
    precedents = subparsers.add_parser("precedent-factors")
    precedents.add_argument("input", type=Path)
    precedents.add_argument("--out", type=Path)
    strategy = subparsers.add_parser("strategy-tree")
    strategy.add_argument("input", type=Path)
    strategy.add_argument("--out", type=Path)
    credibility = subparsers.add_parser("credibility-matrix")
    credibility.add_argument("input", type=Path)
    credibility.add_argument("--out", type=Path)
    elicitation = subparsers.add_parser("elicitation-queue")
    elicitation.add_argument("input", type=Path)
    elicitation.add_argument("--out", type=Path)
    persuasion = subparsers.add_parser("persuasion-gate")
    persuasion.add_argument("input", type=Path)
    persuasion.add_argument("--out", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        input_bytes = args.input.read_bytes()
        payload = json.loads(input_bytes.decode("utf-8"))
        input_violations = validate_input_contract(args.command, payload)
        handlers = {
            "research-fusion": research_fusion,
            "precedent-factors": precedent_factors,
            "strategy-tree": strategy_tree,
            "credibility-matrix": credibility_matrix,
            "elicitation-queue": elicitation_queue,
            "persuasion-gate": persuasion_gate,
        }
        receipt = (
            {"schema_version": RECEIPT_VERSIONS[args.command], "conforms": False,
             "violations": input_violations}
            if input_violations
            else handlers[args.command](payload)
        )
        receipt["input_sha256"] = hashlib.sha256(input_bytes).hexdigest()
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"conforms": False, "error": str(error)}, ensure_ascii=False))
        return 1

    serialized = json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out is not None:
        temporary = args.out.with_suffix(args.out.suffix + ".tmp")
        temporary.write_text(serialized + "\n", encoding="utf-8")
        temporary.replace(args.out)
    print(serialized)
    return 0 if receipt["conforms"] else 2


if __name__ == "__main__":
    sys.exit(main())
