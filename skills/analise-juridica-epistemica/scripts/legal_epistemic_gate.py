#!/usr/bin/env python3
"""Deterministic gate for a typed legal epistemic graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path


SCHEMA_VERSION = "legal_epistemic_graph_v1"
BASE_STATUSES = {"confirmed", "verified", "assumed"}
EVIDENCE_SOURCE_KINDS = {
    "case_document",
    "legislation",
    "precedent",
    "official_act",
    "doctrine",
    "record",
    "expert_report",
    "other",
}


def infer(graph: dict) -> list[dict]:
    propositions = {item["id"]: item for item in graph.get("propositions", [])}
    available = {
        item_id: item.get("status")
        for item_id, item in propositions.items()
        if item.get("status") in BASE_STATUSES
    }
    derived: dict[str, dict] = {}

    changed = True
    while changed:
        changed = False
        for rule in graph.get("rules", []):
            target = rule.get("then")
            if not target or target in available:
                continue
            conditions = rule.get("when", [])
            if not all(
                condition.get("proposition") in available
                and available[condition["proposition"]]
                in condition.get("statuses", [available[condition["proposition"]]])
                for condition in conditions
            ):
                continue
            if any(
                item.get("proposition") in available
                and available[item["proposition"]]
                in item.get("statuses", [available[item["proposition"]]])
                for item in rule.get("unless", [])
            ):
                continue

            conditional = any(
                available[condition["proposition"]] == "assumed"
                for condition in conditions
            )
            status = "conditional" if conditional else "derived"
            source_refs = set(rule.get("source_refs", []))
            for condition in conditions:
                antecedent_id = condition["proposition"]
                if antecedent_id in derived:
                    source_refs.update(derived[antecedent_id].get("source_refs", []))
                else:
                    source_refs.update(
                        propositions.get(antecedent_id, {}).get("source_refs", [])
                    )
            available[target] = status
            derived[target] = {
                "id": target,
                "status": status,
                "derived_by": rule["id"],
                "rule_kind": rule.get("kind", "defeasible"),
                "priority": int(rule.get("priority", 0)),
                "antecedents": [item["proposition"] for item in conditions],
                "source_refs": sorted(source_refs),
            }
            changed = True

    return [
        derived[item_id]
        for item_id in sorted(derived)
        if propositions.get(item_id, {}).get("kind") == "conclusion"
    ]


def validate(graph: dict, artifact_path: Path | None = None) -> dict:
    violations = []
    required_human_decisions = []
    artifact_receipt = None
    if graph.get("schema_version") != SCHEMA_VERSION:
        violations.append(
            {
                "code": "UNSUPPORTED_SCHEMA_VERSION",
                "message": f"Expected {SCHEMA_VERSION}",
            }
        )

    proposition_ids = [item.get("id") for item in graph.get("propositions", [])]
    for proposition_id in sorted(
        {item_id for item_id in proposition_ids if proposition_ids.count(item_id) > 1}
    ):
        violations.append(
            {
                "code": "DUPLICATE_ID",
                "subject": proposition_id,
                "collection": "propositions",
                "message": "Proposition identifiers must be unique.",
            }
        )
    known_propositions = set(proposition_ids)
    for rule in graph.get("rules", []):
        references = [
            item.get("proposition")
            for item in rule.get("when", []) + rule.get("unless", [])
        ] + [rule.get("then")]
        for reference in references:
            if reference in known_propositions:
                continue
            violations.append(
                {
                    "code": "DANGLING_REFERENCE",
                    "subject": rule.get("id"),
                    "reference": reference,
                    "message": "Rule references a nonexistent proposition.",
                }
            )

    for source in graph.get("sources", []):
        if source.get("kind") in EVIDENCE_SOURCE_KINDS:
            continue
        violations.append(
            {
                "code": "INVALID_EVIDENCE_SOURCE",
                "subject": source.get("id"),
                "kind": source.get("kind"),
                "message": "Agent votes, consensus, and evaluations are not evidence sources.",
            }
        )

    objective = graph.get("objective", {})
    governed_by_scenarios = (
        objective.get("status") == "scenarios"
        and len(objective.get("scenarios", [])) >= 2
    )
    if objective.get("status") != "confirmed" and not governed_by_scenarios:
        violations.append(
            {
                "code": "OBJECTIVE_NOT_GOVERNED",
                "subject": "objective",
                "message": "Confirm the governing objective or provide material scenarios.",
            }
        )
        required_human_decisions.append(
            {
                "type": "governing_objective",
                "owner": objective.get("owner"),
                "question": "Which practical objective governs the legal recommendation?",
            }
        )

    if artifact_path is not None:
        actual_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        expected_hash = graph.get("artifact", {}).get("sha256")
        artifact_receipt = {
            "path": str(artifact_path),
            "expected_sha256": expected_hash,
            "actual_sha256": actual_hash,
        }
        if expected_hash != actual_hash:
            violations.append(
                {
                    "code": "ARTIFACT_HASH_MISMATCH",
                    "subject": str(artifact_path),
                    "expected_sha256": expected_hash,
                    "actual_sha256": actual_hash,
                    "message": "Artifact bytes do not match the graph snapshot.",
                }
            )
    structural_codes = {
        "UNSUPPORTED_SCHEMA_VERSION",
        "DUPLICATE_ID",
        "DANGLING_REFERENCE",
    }
    has_structural_failure = any(
        item.get("code") in structural_codes for item in violations
    )
    conclusions = infer(graph) if not has_structural_failure else []
    derived_ids = {item["id"] for item in conclusions}
    derived_by_id = {item["id"]: item for item in conclusions}
    proposition_statuses = {
        item.get("id"): item.get("status")
        for item in graph.get("propositions", [])
    }
    propositions_by_id = {
        item.get("id"): item for item in graph.get("propositions", [])
    }
    blocked_rules = []
    potential_exceptions = []
    blocked_by_target: dict[str, list[str]] = {}
    for rule in graph.get("rules", []):
        active_exceptions = sorted(
            item["proposition"]
            for item in rule.get("unless", [])
            if proposition_statuses.get(item.get("proposition"))
            in item.get(
                "statuses", [proposition_statuses.get(item.get("proposition"))]
            )
        )
        if active_exceptions:
            blocked_rules.append(
                {
                    "id": rule.get("id"),
                    "target": rule.get("then"),
                    "exceptions": active_exceptions,
                }
            )
            blocked_by_target[rule.get("then")] = active_exceptions
        uncertain_exceptions = sorted(
            item["proposition"]
            for item in rule.get("unless", [])
            if proposition_statuses.get(item.get("proposition"))
            in {"unknown", "disputed"}
        )
        if uncertain_exceptions:
            potential_exceptions.append(
                {
                    "id": rule.get("id"),
                    "target": rule.get("then"),
                    "exceptions": uncertain_exceptions,
                }
            )
    verified_sources = {
        item.get("id")
        for item in graph.get("sources", [])
        if item.get("status") == "verified"
        and item.get("kind") in EVIDENCE_SOURCE_KINDS
    }
    for conclusion in conclusions:
        if set(conclusion.get("source_refs", [])) & verified_sources:
            continue
        violations.append(
            {
                "code": "DERIVATION_WITHOUT_VERIFIED_SOURCE",
                "subject": conclusion.get("id"),
                "rule": conclusion.get("derived_by"),
                "message": "Derived conclusion lacks a verified source chain.",
            }
        )
    for proposition in graph.get("propositions", []):
        if proposition.get("kind") != "conclusion" or not proposition.get("decisive"):
            continue
        if proposition.get("id") in derived_ids:
            continue
        source_refs = set(proposition.get("source_refs", []))
        if proposition.get("status") == "confirmed" and source_refs & verified_sources:
            conclusions.append(
                {
                    "id": proposition["id"],
                    "status": "confirmed",
                    "derived_by": None,
                    "antecedents": [],
                    "source_refs": sorted(source_refs & verified_sources),
                }
            )
            continue
        blocked = blocked_by_target.get(proposition.get("id"))
        violations.append(
            {
                "code": (
                    "CONCLUSION_BLOCKED_BY_EXCEPTION"
                    if blocked
                    else "CONCLUSION_WITHOUT_PROVENANCE"
                ),
                "subject": proposition.get("id"),
                "exceptions": blocked or [],
                "message": (
                    "Decisive conclusion is blocked by a confirmed exception."
                    if blocked
                    else "Decisive conclusion lacks a verified source or derivation."
                ),
            }
        )

    accepted_ids = {item["id"] for item in conclusions}
    conditional_by_id: dict[str, dict] = {}
    for conclusion_id in sorted(accepted_ids):
        conclusion = propositions_by_id.get(conclusion_id, {})
        for dependency_id in conclusion.get("depends_on", []):
            dependency = propositions_by_id.get(dependency_id, {})
            if dependency.get("impact") != "decisive" or dependency.get("status") not in {
                "unknown",
                "disputed",
            }:
                continue
            violations.append(
                {
                    "code": "DECISIVE_UNKNOWN_DEPENDENCY",
                    "subject": conclusion_id,
                    "dependency": dependency_id,
                    "message": "Derived conclusion is conditional on a decisive unresolved proposition.",
                }
            )
            required_human_decisions.append(
                {
                    "type": "missing_information",
                    "proposition": dependency_id,
                    "owner": dependency.get("owner"),
                    "question": dependency.get("statement"),
                }
            )
            conditional = conditional_by_id.setdefault(
                conclusion_id,
                {
                    **next(
                        item for item in conclusions if item["id"] == conclusion_id
                    ),
                    "status": "conditional",
                    "depends_on": [],
                },
            )
            conditional["depends_on"].append(dependency_id)

    defeated_conclusions = []
    defeated_ids = set()
    for conflict in graph.get("conflicts", []):
        left = derived_by_id.get(conflict.get("left"))
        right = derived_by_id.get(conflict.get("right"))
        if not left or not right:
            continue
        left_strength = (left.get("rule_kind") == "strict", left.get("priority", 0))
        right_strength = (
            right.get("rule_kind") == "strict",
            right.get("priority", 0),
        )
        if left_strength == right_strength:
            violations.append(
                {
                    "code": "UNRESOLVED_RULE_CONFLICT",
                    "subject": [left["id"], right["id"]],
                    "message": "Conflicting conclusions have equal symbolic strength.",
                }
            )
            continue
        winner, loser = (left, right) if left_strength > right_strength else (right, left)
        defeated_ids.add(loser["id"])
        defeated_conclusions.append(
            {
                "id": loser["id"],
                "derived_by": loser.get("derived_by"),
                "defeated_by": winner["id"],
                "winning_rule": winner.get("derived_by"),
            }
        )

    as_of = date.fromisoformat(graph["as_of"])
    grants = {item.get("id"): item for item in graph.get("grants", [])}
    pending_authorizations = []
    for action in graph.get("actions", []):
        if action.get("state") in {"proposed", "prepared"} and action.get(
            "grant_id"
        ) not in grants:
            pending_authorizations.append(
                {
                    "id": action.get("id"),
                    "actor": action.get("actor"),
                    "operation": action.get("operation"),
                    "target": action.get("target"),
                    "state": action.get("state"),
                    "reason": "explicit_grant_required_before_authorization",
                }
            )
            required_human_decisions.append(
                {
                    "type": "external_authorization",
                    "action": action.get("id"),
                    "owner": action.get("authority_owner")
                    or objective.get("owner"),
                    "question": (
                        f"Authorize {action.get('operation')} on {action.get('target')} "
                        f"for {action.get('actor')}?"
                    ),
                }
            )
            continue
        if action.get("state") not in {"authorized", "executed", "verified"}:
            continue
        grant = grants.get(action.get("grant_id"))
        mismatches = []
        if grant is None:
            mismatches.append("grant_id")
        else:
            expected = {
                "grantee": action.get("actor"),
                "operation": action.get("operation"),
                "target": action.get("target"),
                "status": "active",
            }
            mismatches.extend(
                field for field, value in expected.items() if grant.get(field) != value
            )
            if grant.get("valid_from") and date.fromisoformat(grant["valid_from"]) > as_of:
                mismatches.append("valid_from")
            if grant.get("valid_until") and date.fromisoformat(grant["valid_until"]) < as_of:
                mismatches.append("valid_until")
        if mismatches:
            violations.append(
                {
                    "code": "ACTION_WITHOUT_VALID_GRANT",
                    "subject": action.get("id"),
                    "mismatches": sorted(mismatches),
                    "message": "Action state requires an exact active grant.",
                }
            )

    conditional_ids = set(conditional_by_id)
    conclusions = [
        item
        for item in conclusions
        if item["id"] not in defeated_ids and item["id"] not in conditional_ids
    ]
    conclusions.sort(key=lambda item: item["id"])
    defeated_conclusions.sort(key=lambda item: item["id"])
    conditional_conclusions = sorted(
        conditional_by_id.values(), key=lambda item: item["id"]
    )
    return {
        "schema_version": "legal_epistemic_receipt_v1",
        "graph_id": graph.get("graph_id"),
        "conforms": not violations,
        "violations": violations,
        "warnings": [],
        "accepted_conclusions": conclusions,
        "conditional_conclusions": conditional_conclusions,
        "defeated_conclusions": defeated_conclusions,
        "blocked_rules": blocked_rules,
        "potential_exceptions": potential_exceptions,
        "pending_authorizations": pending_authorizations,
        "required_human_decisions": required_human_decisions,
        "artifact": artifact_receipt,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("graph", type=Path)
    validate_parser.add_argument("--artifact", type=Path)
    validate_parser.add_argument("--out", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        graph = json.loads(args.graph.read_text(encoding="utf-8"))
        receipt = validate(graph, args.artifact)
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
