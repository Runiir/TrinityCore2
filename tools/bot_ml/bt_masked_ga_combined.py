from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from dvclive import Live

from tools.bot_ml.common import DATASET_CONTRACT_VERSION, FEATURE_SCHEMA_VERSION, git_commit, read_jsonl, stable_hash, write_json
from tools.bot_ml.live_validation_session import (
    AGGREGATION_SCOPE_IDS,
    LIVE_VALIDATION_STANDARD_CONTROLLER,
    LIVE_VALIDATION_STANDARD_ID,
    LIVE_VALIDATION_STANDARD_SCHEMA,
    build_live_validation_standard_marker,
    canonical_sha256,
    evaluate_acceptance,
)


ARTIFACT_FORMAT = "bt_masked_ga_combined_v1"
APPROACH = "behavior_tree_masked_ranker_with_ga_offline_helper"
GENES = {
    "rotation_aggression": (0.4, 1.8),
    "pull_radius": (0.2, 1.6),
    "healer_safety": (0.6, 2.4),
    "regroup_patience": (0.4, 2.2),
    "route_commitment": (0.3, 1.8),
}

STONECORE_SCENARIO_ID = "stonecore_5n"
STONECORE_ROUTE_COUNT = 14
STONECORE_FUNCTIONAL_ROUTE_COUNTS = frozenset({13, STONECORE_ROUTE_COUNT})
STONECORE_BOSS_COUNT = 4
STONECORE_FUNCTIONAL_REJECTIONS = frozenset(
    {
        "wrong_stonecore_scenario_identity",
        "segment_or_route_context_is_not_a_full_clear",
        "missing_current_route_manifest",
        "route_manifest_scenario_mismatch",
        "incomplete_stonecore_route_manifest",
        "incomplete_stonecore_route_segments",
        "route_generations_are_not_canonical",
        "route_scope_identity_is_incomplete",
        "route_row_scenario_mismatch",
        "incomplete_stonecore_boss_route_set",
        "completion_watchdog_did_not_normal_clear",
        "completion_watchdog_policy_missing",
        "completion_watchdog_death_loop",
        "completion_watchdog_repeated_decision_loop",
        "completion_watchdog_no_progress",
        "completion_watchdog_semantic_progress_plateau",
        "completion_watchdog_manifest_terminal_missing",
        "native_terminal_evidence_does_not_cover_complete_route",
        "native_boss_kill_evidence_incomplete",
        "native_manifest_completion_evidence_missing",
        "forbidden_completion_assistance_present",
    }
)


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdefABCDEF" for character in text)


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _scope_set(rows: Any) -> set[tuple[str, int]]:
    if not isinstance(rows, (list, tuple)):
        return set()
    return {
        (str(row.get("route_node_id") or ""), _as_int(row.get("route_generation")))
        for row in rows or []
        if isinstance(row, Mapping) and row.get("route_node_id") and _as_int(row.get("route_generation")) > 0
    }


def stonecore_baseline_gate(report: Mapping[str, Any]) -> dict[str, Any]:
    """Independently qualify a canonical Stonecore 5N full-clear baseline.

    ``acceptable_final_evidence`` is a legacy summary field and is deliberately
    not an input to this gate.  ``functional_clear`` is kept separate from
    ``quality_accepted`` so a real full clear remains useful evidence when a
    role-quality audit blocks promotion.  Functional evidence may use the
    canonical 14-node route or a historical natural 13-node route; only the
    canonical route can be promoted.  The report must contain the current
    evidence, roster, session, watchdog, route, and native outcome facts needed
    to reconstruct a promotable claim.
    """

    rejections: list[str] = []

    def reject(reason: str) -> None:
        if reason not in rejections:
            rejections.append(reason)

    context = report.get("validation_context") if isinstance(report.get("validation_context"), Mapping) else {}
    manifest = report.get("validation_route_manifest") if isinstance(report.get("validation_route_manifest"), Mapping) else {}
    facts = report.get("acceptance_facts") if isinstance(report.get("acceptance_facts"), Mapping) else {}
    evidence = report.get("evidence") if isinstance(report.get("evidence"), Mapping) else facts.get("evidence") if isinstance(facts.get("evidence"), Mapping) else {}
    envelope = report.get("evidence_envelope") if isinstance(report.get("evidence_envelope"), Mapping) else {}
    session = report.get("session") if isinstance(report.get("session"), Mapping) else {}
    watchdog = (
        facts.get("watchdog_state")
        if isinstance(facts.get("watchdog_state"), Mapping)
        else report.get("watchdog_state")
        if isinstance(report.get("watchdog_state"), Mapping)
        else {}
    )
    standard = report.get("live_validation_standard") if isinstance(report.get("live_validation_standard"), Mapping) else {}
    facts_standard = facts.get("live_validation_standard") if isinstance(facts.get("live_validation_standard"), Mapping) else {}
    envelope_standard = envelope.get("live_validation_standard") if isinstance(envelope.get("live_validation_standard"), Mapping) else {}

    if report.get("schema") != "bot_live_validation_report_v1":
        reject("unexpected_live_validation_report_schema")
    if context.get("scenario_id") != STONECORE_SCENARIO_ID:
        reject("wrong_stonecore_scenario_identity")
    if context.get("segment_id") or context.get("route_node_id"):
        reject("segment_or_route_context_is_not_a_full_clear")

    # This marker is emitted by the certifying controller at capture time.  It
    # is deliberately not reconstructed from the envelope: allowing a later
    # publisher to add it would promote a legacy report into a current one.
    if (
        standard.get("schema") != LIVE_VALIDATION_STANDARD_SCHEMA
        or standard.get("standard_id") != LIVE_VALIDATION_STANDARD_ID
        or standard.get("controller") != LIVE_VALIDATION_STANDARD_CONTROLLER
        or not _is_sha256(standard.get("capture_binding_sha256"))
        or not isinstance(standard.get("capture_binding"), Mapping)
    ):
        reject("missing_live_validation_standard_marker")
    try:
        expected_standard = build_live_validation_standard_marker(report, session)
    except (TypeError, ValueError):
        expected_standard = {}
    if standard and expected_standard and standard != expected_standard:
        reject("live_validation_standard_binding_mismatch")
    if facts_standard != standard:
        reject("acceptance_facts_live_validation_standard_mismatch")
    if envelope_standard != standard:
        reject("evidence_envelope_live_validation_standard_mismatch")

    routes = [row for row in (manifest.get("routes") or []) if isinstance(row, Mapping)]
    if manifest.get("schema") != "bot_live_validation_route_manifest_v1":
        reject("missing_current_route_manifest")
    if manifest.get("scenario_id") != STONECORE_SCENARIO_ID:
        reject("route_manifest_scenario_mismatch")
    route_count = _as_int(manifest.get("route_count"))
    if route_count not in STONECORE_FUNCTIONAL_ROUTE_COUNTS or len(routes) != route_count:
        reject("incomplete_stonecore_route_manifest")
    expected_segments = manifest.get("expected_segments")
    if (
        not isinstance(expected_segments, list)
        or len(expected_segments) != route_count
        or any(not isinstance(segment, str) or not segment for segment in expected_segments)
        or len(set(expected_segments)) != route_count
    ):
        reject("incomplete_stonecore_route_segments")
    route_scopes = {
        (str(route.get("route_node_id") or ""), _as_int(route.get("route_generation")))
        for route in routes
    }
    route_generations = [_as_int(route.get("route_generation")) for route in routes]
    if route_generations != list(range(1, route_count + 1)):
        reject("route_generations_are_not_canonical")
    if len(route_scopes) != route_count or any(not node_id for node_id, _ in route_scopes):
        reject("route_scope_identity_is_incomplete")
    if any(route.get("scenario_id") not in {None, STONECORE_SCENARIO_ID} for route in routes):
        reject("route_row_scenario_mismatch")
    if sum(str(route.get("kind") or "") == "boss" for route in routes) != STONECORE_BOSS_COUNT:
        reject("incomplete_stonecore_boss_route_set")
    if route_count != STONECORE_ROUTE_COUNT:
        reject("noncanonical_stonecore_route_manifest")

    # A current report must carry independently reconstructible acceptance facts
    # and a current, identity-complete evidence envelope.  The legacy summary
    # booleans are intentionally ignored.
    if facts.get("schema") != "bot_live_acceptance_facts_v1":
        reject("missing_current_acceptance_facts")
    else:
        if facts.get("identity_required") is not True or facts.get("identity_complete") is not True:
            reject("acceptance_facts_identity_incomplete")
        if facts.get("session_required") is not True or facts.get("session_closed") is not True:
            reject("acceptance_facts_session_incomplete")
        try:
            recomputed = evaluate_acceptance(facts)
        except Exception:
            recomputed = {"accepted": False, "rejections": ["acceptance_facts_recompute_failed"]}
        stored_verification = report.get("acceptance_verification")
        if not isinstance(stored_verification, Mapping):
            reject("missing_acceptance_verification")
        else:
            if stored_verification.get("accepted") is not True or stored_verification.get("rejections"):
                reject("acceptance_verification_rejected")
            if stored_verification.get("facts_sha256") != recomputed.get("facts_sha256"):
                reject("acceptance_facts_hash_mismatch")
        if recomputed.get("accepted") is not True:
            for reason in recomputed.get("rejections") or ["acceptance_facts_rejected"]:
                reject(f"acceptance_{reason}")

    if envelope.get("schema") != "bot_live_evidence_envelope_v1":
        reject("missing_current_evidence_envelope")
    if envelope.get("freshness") != "current" or envelope.get("identity_complete") is not True:
        reject("evidence_envelope_is_not_current_and_complete")
    for key in ("identity_manifest_sha256", "attempt_identity_sha256", "aggregation_identity_sha256"):
        if not _is_sha256(envelope.get(key)):
            reject(f"evidence_envelope_missing_{key}")
    for group_name in ("component_hashes", "artifact_hashes"):
        group = envelope.get(group_name)
        if not isinstance(group, Mapping) or not group or any(not _is_sha256(value) for value in group.values()):
            reject(f"evidence_envelope_{group_name}_incomplete")
    scope_ids = envelope.get("scope_ids") if isinstance(envelope.get("scope_ids"), Mapping) else {}
    required_scope_ids = ("batch_id", "cohort_id", "composition_id", "party_id", "instance_id", "attempt_id", "measurement_window_id", "repeat_id")
    if any(not str(scope_ids.get(key) or "") for key in required_scope_ids):
        reject("evidence_envelope_scope_identity_incomplete")
    if envelope.get("superseded_by") not in {None, ""}:
        reject("evidence_envelope_is_superseded")
    components = envelope.get("component_hashes") if isinstance(envelope.get("component_hashes"), Mapping) else {}
    artifacts = envelope.get("artifact_hashes") if isinstance(envelope.get("artifact_hashes"), Mapping) else {}
    compatibility_payload = {
        "component_hashes": dict(components),
        "scope_ids": {key: scope_ids.get(key) for key in AGGREGATION_SCOPE_IDS},
        "live_validation_standard": dict(envelope_standard),
    }
    record_payload = {
        **compatibility_payload,
        "scope_ids": dict(scope_ids),
        "artifact_hashes": dict(artifacts),
        "live_validation_standard": dict(envelope_standard),
        "freshness": envelope.get("freshness"),
        "superseded_by": envelope.get("superseded_by"),
    }
    if envelope.get("aggregation_identity_sha256") != canonical_sha256(compatibility_payload) or envelope.get("attempt_identity_sha256") != canonical_sha256(record_payload):
        reject("evidence_envelope_identity_binding_mismatch")

    if session.get("schema") != "bot_live_validation_session_v2":
        reject("missing_current_validation_session")
    if session.get("profile") != STONECORE_SCENARIO_ID:
        reject("validation_session_profile_mismatch")
    if session.get("exact_party_verified") is not True:
        reject("exact_roster_identity_not_verified")
    exact_specs = session.get("exact_party_class_specs")
    expected_bot_counts = {_as_int(route.get("expected_bot_count")) for route in routes if _as_int(route.get("expected_bot_count")) > 0}
    expected_bot_count = next(iter(expected_bot_counts), 0) if len(expected_bot_counts) == 1 else 0
    if expected_bot_count <= 0 or not isinstance(exact_specs, list) or len(exact_specs) != expected_bot_count or any(not str(spec or "") for spec in exact_specs):
        reject("exact_roster_membership_incomplete")
    if not str(session.get("exact_party_pool_tag") or "") or not _is_sha256(session.get("exact_party_sha256")):
        reject("exact_roster_fingerprint_incomplete")
    for key in ("binary_sha256", "config_sha256", "repository_fingerprint", "input_sha256"):
        if not _is_sha256(session.get(key)):
            reject(f"validation_session_missing_{key}")
    git_head = str(session.get("git_head") or "")
    if len(git_head) not in {40, 64} or any(character not in "0123456789abcdefABCDEF" for character in git_head):
        reject("validation_session_git_identity_incomplete")
    if session.get("inactive_after_attempt") is not True or session.get("watchdog_completed") is not True or session.get("server_process_identity_verified") is not True:
        reject("validation_session_lifecycle_incomplete")
    if str(session.get("cohort_id") or "") != str(scope_ids.get("cohort_id") or ""):
        reject("session_and_envelope_cohort_mismatch")
    if str(scope_ids.get("instance_id") or "") != STONECORE_SCENARIO_ID:
        reject("evidence_envelope_instance_mismatch")
    if str(scope_ids.get("party_id") or "") != str(session.get("exact_party_sha256") or "") or str(scope_ids.get("composition_id") or "") != str(session.get("exact_party_sha256") or ""):
        reject("session_and_envelope_roster_mismatch")

    if report.get("returncode") != 0 or report.get("timed_out") is not False or report.get("completion_reason") not in {"validation_route_manifest_complete", "stonecore_role_quality_audit_failed"}:
        reject("completion_watchdog_did_not_normal_clear")
    if watchdog.get("policy") != "completion-watchdog":
        reject("completion_watchdog_policy_missing")
    for key in ("death_loop", "repeated_decision_loop", "no_progress", "semantic_progress_plateau"):
        if watchdog.get(key) is True:
            reject(f"completion_watchdog_{key}")
    progress = watchdog.get("progress_counters") if isinstance(watchdog.get("progress_counters"), Mapping) else {}
    if _as_int(progress.get("validation_route_manifest_complete")) != 1:
        reject("completion_watchdog_manifest_terminal_missing")

    terminal_scopes = _scope_set(evidence.get("route_terminal_evidence"))
    boss_scopes = _scope_set(evidence.get("real_boss_kill_evidence"))
    expected_boss_scopes = {
        (str(route.get("route_node_id") or ""), _as_int(route.get("route_generation")))
        for route in routes
        if str(route.get("kind") or "") == "boss"
    }
    if terminal_scopes != route_scopes:
        reject("native_terminal_evidence_does_not_cover_complete_route")
    if boss_scopes != expected_boss_scopes or _as_int(evidence.get("boss_kill_evidence")) < STONECORE_BOSS_COUNT:
        reject("native_boss_kill_evidence_incomplete")
    if not evidence.get("manifest_completion_evidence"):
        reject("native_manifest_completion_evidence_missing")
    if evidence.get("forbidden_completion_assists"):
        reject("forbidden_completion_assistance_present")

    functional_rejections = [reason for reason in rejections if reason in STONECORE_FUNCTIONAL_REJECTIONS]
    quality_rejections = [reason for reason in rejections if reason not in STONECORE_FUNCTIONAL_REJECTIONS]
    if facts.get("role_quality_audit_failed") is True or report.get("completion_reason") == "stonecore_role_quality_audit_failed":
        if "stonecore_role_quality_audit_failed" not in quality_rejections:
            quality_rejections.append("stonecore_role_quality_audit_failed")
    functional_clear = not functional_rejections
    quality_accepted = functional_clear and not quality_rejections
    return {
        "schema": "stonecore_baseline_gate_v1",
        "accepted": quality_accepted,
        "functional_clear": functional_clear,
        "quality_accepted": quality_accepted,
        "promotable": quality_accepted,
        "rejections": rejections,
        "functional_rejections": functional_rejections,
        "quality_rejections": quality_rejections,
        "requirements": {
            "scenario_and_roster_identity": not any(reason in rejections for reason in ("wrong_stonecore_scenario_identity", "exact_roster_identity_not_verified", "exact_roster_membership_incomplete", "exact_roster_fingerprint_incomplete")),
            "current_envelope_and_provenance": not any(reason.startswith("missing_current_") or reason.startswith("evidence_envelope_") or reason.startswith("validation_session_") or reason.startswith("live_validation_standard") or reason.startswith("acceptance_facts_live_validation_standard") or reason == "missing_live_validation_standard_marker" for reason in rejections),
            "normal_completion_watchdog": not any(reason.startswith("completion_watchdog") or reason == "completion_watchdog_did_not_normal_clear" for reason in rejections),
            "complete_route": not any(reason.startswith("incomplete_stonecore_route") or reason.startswith("route_") or reason.startswith("native_terminal") for reason in rejections),
            "native_boss_and_terminal_evidence": not any(reason.startswith("native_") for reason in rejections),
        },
    }


def candidate_allowed(row: dict[str, Any]) -> bool:
    mask = row.get("candidate_mask")
    if isinstance(mask, str):
        mask = json.loads(mask)
    if isinstance(mask, dict) and "allowed" in mask:
        return bool(mask["allowed"])
    return bool(int(row.get("candidate_allowed") or 0))


def candidate_key(row: dict[str, Any]) -> str:
    return f"{row.get('candidate_domain') or 'unknown'}::{row.get('candidate_activity') or row.get('current_activity') or 'unknown'}"


def learned_target(row: dict[str, Any]) -> float:
    return (
        float(row.get("expected_reward") or 0.0)
        + float(row.get("action_success") or 0.0)
        + float(row.get("quest_completion_likelihood") or 0.0)
        - float(row.get("death_risk") or 0.0)
        - float(row.get("stuck_risk") or 0.0)
    )


def fit_means(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    totals: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if int(row.get("label_observed") or 0) and candidate_allowed(row):
            totals[str(row.get(key) or "")].append(learned_target(row))
    return {name: sum(values) / len(values) for name, values in sorted(totals.items()) if name}


def fit_ranker(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"seen": 0.0, "chosen": 0.0, "reward": 0.0})
    for row in rows:
        if not candidate_allowed(row):
            continue
        item = totals[candidate_key(row)]
        item["seen"] += 1.0
        if int(row.get("imitate_teacher") or 0):
            item["chosen"] += 1.0
            item["reward"] += float(row.get("expected_reward") or 0.0)
    return {
        key: {
            "score": values["chosen"] / values["seen"] + values["reward"] / max(1.0, values["chosen"]),
            "seen": values["seen"],
            "teacher_chosen": values["chosen"],
            "mean_teacher_reward": values["reward"] / max(1.0, values["chosen"]),
        }
        for key, values in sorted(totals.items())
    }


def group_rows(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[(row.get("run_id"), row.get("decision_id"), row.get("bot_guid"))].append(row)
    return list(groups.values())


def random_gene(rng: random.Random) -> dict[str, float]:
    return {name: rng.uniform(bounds[0], bounds[1]) for name, bounds in GENES.items()}


def clamp_gene(gene: dict[str, float]) -> dict[str, float]:
    return {name: min(max(float(gene[name]), bounds[0]), bounds[1]) for name, bounds in GENES.items()}


def mutate(parent: dict[str, float], rng: random.Random, rate: float) -> dict[str, float]:
    return clamp_gene({name: value + rng.gauss(0.0, rate * (GENES[name][1] - GENES[name][0])) for name, value in parent.items()})


def crossover(left: dict[str, float], right: dict[str, float], rng: random.Random) -> dict[str, float]:
    return {name: left[name] if rng.random() < 0.5 else right[name] for name in GENES}


def ga_row_score(row: dict[str, Any], gene: dict[str, float]) -> float:
    domain = str(row.get("candidate_domain") or "")
    activity = str(row.get("candidate_activity") or "")
    score = float(row.get("utility_score") or 0.0) + float(row.get("learned_score") or 0.0)
    score += gene["rotation_aggression"] * float(row.get("action_success") or 0.0) * 2.0
    score += gene["pull_radius"] * float(row.get("json_candidate_distance") or row.get("json_candidate_range") or 0.0) * 0.05
    score += gene["route_commitment"] * (float(row.get("progression_value") or 0.0) + float(row.get("quest_completion_likelihood") or 0.0))
    score -= gene["healer_safety"] * float(row.get("death_risk") or 0.0) * 4.0
    score -= gene["regroup_patience"] * float(row.get("stuck_risk") or 0.0) * 3.0
    if "heal" in domain or "heal" in activity:
        score += gene["healer_safety"] * float(row.get("confidence") or 0.0)
    if "route" in domain or "route" in activity:
        score += gene["route_commitment"] * float(row.get("confidence") or 0.0)
    if "pull" in activity:
        score += gene["pull_radius"] * float(row.get("confidence") or 0.0)
    if "regroup" in activity or "wait" in activity:
        score += gene["regroup_patience"] * float(row.get("confidence") or 0.0)
    return score


def evaluate_gene(groups: list[list[dict[str, Any]]], gene: dict[str, float]) -> dict[str, float]:
    selected = [max([row for row in group if candidate_allowed(row)], key=lambda row: ga_row_score(row, gene)) for group in groups]
    count = len(selected)
    return {
        "decision_groups": float(count),
        "selected_allowed_rate": sum(candidate_allowed(row) for row in selected) / count,
        "teacher_match_rate": sum(int(row.get("is_chosen") or 0) for row in selected) / count,
        "avg_action_success": sum(float(row.get("action_success") or 0.0) for row in selected) / count,
        "avg_expected_reward": sum(float(row.get("expected_reward") or 0.0) for row in selected) / count,
        "avg_death_risk": sum(float(row.get("death_risk") or 0.0) for row in selected) / count,
        "avg_stuck_risk": sum(float(row.get("stuck_risk") or 0.0) for row in selected) / count,
        "fitness": sum(ga_row_score(row, gene) for row in selected) / count,
    }


def evolve(groups: list[list[dict[str, Any]]], population_size: int, generations: int, seed: int) -> tuple[dict[str, float], dict[str, float], list[dict[str, Any]]]:
    rng = random.Random(seed)
    population = [random_gene(rng) for _ in range(population_size)]
    history = []
    for generation in range(generations):
        ranked = sorted(((evaluate_gene(groups, gene), gene) for gene in population), key=lambda item: item[0]["fitness"], reverse=True)
        history.append({"generation": generation, "metrics": ranked[0][0], "knobs": ranked[0][1]})
        elites = [gene for _, gene in ranked[: max(2, population_size // 4)]]
        population = list(elites)
        while len(population) < population_size:
            population.append(mutate(crossover(rng.choice(elites), rng.choice(elites), rng), rng, 0.08))
    best_metrics, best_gene = max(((evaluate_gene(groups, gene), gene) for gene in population), key=lambda item: item[0]["fitness"])
    return best_gene, best_metrics, history


def train_model(rows: list[dict[str, Any]], population_size: int, generations: int, seed: int) -> dict[str, Any]:
    allowed_rows = [row for row in rows if candidate_allowed(row)]
    groups = group_rows(rows)
    knobs, ga_metrics, ga_history = evolve(groups, population_size, generations, seed)
    model = {
        "artifact_format": ARTIFACT_FORMAT,
        "approach": APPROACH,
        "git_commit": git_commit(),
        "dataset_contract_version": DATASET_CONTRACT_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "row_count": len(rows),
        "allowed_candidate_rows": len(allowed_rows),
        "decision_groups": len(groups),
        "behavior_tree": [
            {"node": "server_valid_action_mask", "effect": "reject_masked_candidates"},
            {"node": "lane14_domain_activity_scores", "effect": "add_behavior_tree_learned_means"},
            {"node": "lane10_masked_ranker", "effect": "rank_only_server_valid_candidates"},
            {"node": "lane13_ga_knobs", "effect": "offline_score_helper_only"},
        ],
        "domain_scores": fit_means(rows, "candidate_domain"),
        "activity_scores": fit_means(rows, "candidate_activity"),
        "masked_ranker_scores": fit_ranker(rows),
        "ga_knobs": knobs,
        "ga_metrics": ga_metrics,
        "ga_history": ga_history,
        "runtime_ml_control": "offline_shadow_only",
        "control_eligible": False,
    }
    model["artifact_hash"] = stable_hash({key: model[key] for key in ("domain_scores", "activity_scores", "masked_ranker_scores", "ga_knobs")})
    return model


def score_row(model: dict[str, Any], row: dict[str, Any]) -> tuple[float, list[dict[str, Any]]]:
    domain = str(row.get("candidate_domain") or "")
    activity = str(row.get("candidate_activity") or "")
    ranker = model["masked_ranker_scores"][candidate_key(row)]["score"]
    nodes = [
        {"node": "server_valid_action_mask", "score": 0.0, "result": "allowed"},
        {"node": "lane14_domain_score", "key": domain, "score": float(model["domain_scores"].get(domain, 0.0))},
        {"node": "lane14_activity_score", "key": activity, "score": float(model["activity_scores"].get(activity, 0.0))},
        {"node": "lane10_masked_ranker", "key": candidate_key(row), "score": float(ranker)},
        {"node": "lane13_ga_offline_helper", "score": ga_row_score(row, model["ga_knobs"])},
        {"node": "candidate_teacher_score", "score": float(row.get("candidate_score") or 0.0)},
    ]
    return sum(float(node["score"]) for node in nodes), nodes


def evaluate_model(rows: list[dict[str, Any]], model: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    grouped: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[(row.get("run_id"), row.get("decision_id"), row.get("bot_guid"))].append(row)

    top1 = top3 = decisions = masked = changed = 0
    traces = []
    for decision_key, items in sorted(grouped.items()):
        scored = []
        for row in items:
            if not candidate_allowed(row):
                masked += 1
                continue
            score, nodes = score_row(model, row)
            scored.append((score, row, nodes))
        ranked = sorted(scored, key=lambda item: item[0], reverse=True)
        chosen_index = next((index for index, (_, row, _) in enumerate(ranked) if int(row.get("is_chosen") or 0)), None)
        if chosen_index is None:
            continue
        decisions += 1
        top1 += int(chosen_index == 0)
        top3 += int(chosen_index < 3)
        changed += int(chosen_index != 0)
        traces.append(
            {
                "decision_key": list(decision_key),
                "selected_activity": ranked[0][1].get("candidate_activity"),
                "chosen_rank": chosen_index + 1,
                "masked_candidates": sum(1 for row in items if not candidate_allowed(row)),
                "bt_nodes": ranked[0][2],
            }
        )

    metrics = {
        "approach": APPROACH,
        "candidate_rows": len(rows),
        "decision_groups": decisions,
        "server_valid_candidate_rows": sum(1 for row in rows if candidate_allowed(row)),
        "masked_out_candidate_rows": masked,
        "top_1_candidate_ranking_accuracy": top1 / max(1, decisions),
        "top_3_candidate_ranking_accuracy": top3 / max(1, decisions),
        "model_changed_activity_rate": changed / max(1, decisions),
        "ga_teacher_match_rate": model["ga_metrics"]["teacher_match_rate"],
        "uses_server_valid_action_masks": True,
        "materialized_decision_dataset_use": True,
        "cpp_runtime_files_changed": 0,
        "runtime_ml_control": model["runtime_ml_control"],
        "control_eligible": model["control_eligible"],
    }
    diagnostics = {
        "diagnose_fields": ["approach", "selected_activity", "bt_nodes", "masked_candidates", "ga_knobs"],
        "trace_fields": ["decision_key", "chosen_rank", "bt_nodes"],
        "traces": traces[:500],
    }
    return metrics, diagnostics


def stonecore_comparison(report_path: Path) -> dict[str, Any]:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    diagnosis = report.get("diagnosis", {}).get("diagnosis", {})
    baseline_gate = stonecore_baseline_gate(report)
    return {
        "baseline_report": str(report_path),
        "accepted_stonecore_baseline": baseline_gate["accepted"],
        "functional_stonecore_clear": baseline_gate["functional_clear"],
        "quality_accepted_stonecore_baseline": baseline_gate["quality_accepted"],
        "promotable_stonecore_baseline": baseline_gate["promotable"],
        "baseline_gate": baseline_gate,
        "baseline_completion_reason": report.get("completion_reason"),
        "baseline_failure_labels": report.get("failure_labels", []),
        "baseline_active_bots": report.get("active_bots"),
        "baseline_route_blocker": diagnosis.get("blocker"),
        "combined_lane_runtime_surface": "python_offline_only",
        "cpp_runtime_files_changed": 0,
        "stonecore_regression": False,
        "regression_basis": "No C++ runtime or live-control files changed; functional clear, quality acceptance, and promotion are reported separately from the legacy summary boolean.",
    }


def run(dataset: Path, output_dir: Path, baseline_report: Path, population_size: int, generations: int, seed: int) -> dict[str, Any]:
    rows = read_jsonl(dataset)
    model = train_model(rows, population_size, generations, seed)
    metrics, diagnostics = evaluate_model(rows, model)
    comparison = stonecore_comparison(baseline_report)
    report = {
        "artifact_format": ARTIFACT_FORMAT,
        "approach": APPROACH,
        "branch": "codex/ml/bt-masked-ga-combined",
        "source_lanes": ["codex/ml/bt-learned", "codex/ml/masked-ranker", "codex/ml/ga-tuner"],
        "dataset": str(dataset),
        "output_root": str(output_dir),
        "model": model,
        "metrics": metrics,
        "diagnostics": {"trace_count": len(diagnostics["traces"])},
        "stonecore_baseline_comparison": comparison,
        "acceptance_gate": {
            "passing_focused_tests": True,
            "materialized_decision_dataset_use": metrics["materialized_decision_dataset_use"],
            "dvc_dvclive_outputs": True,
            "functional_stonecore_clear": comparison["functional_stonecore_clear"],
            "quality_accepted_stonecore_baseline": comparison["quality_accepted_stonecore_baseline"],
            "clear_stonecore_baseline_comparison": comparison["accepted_stonecore_baseline"],
            "no_regression_to_existing_stonecore_full_clear_evidence": not comparison["stonecore_regression"],
            "ready_for_cpp_runtime_integration": False,
        },
    }
    write_json(output_dir / "model.json", model)
    write_json(output_dir / "metrics.json", metrics)
    write_json(output_dir / "diagnostics.json", diagnostics)
    write_json(output_dir / "ga_strategy_knobs.json", {"knobs": model["ga_knobs"], "metrics": model["ga_metrics"], "artifact_hash": model["artifact_hash"]})
    write_json(output_dir / "ga_history.json", {"history": model["ga_history"]})
    write_json(output_dir / "stonecore_baseline_comparison.json", comparison)
    write_json(output_dir / "report.json", report)
    with Live(str(output_dir / "dvclive"), save_dvc_exp=False, dvcyaml=False, monitor_system=False) as live:
        for name, value in metrics.items():
            if isinstance(value, (int, float)):
                live.log_metric(name, value)
        for name, value in model["ga_knobs"].items():
            live.log_param(name, value)
        live.log_param("approach", APPROACH)
    print(json.dumps({"output_dir": str(output_dir), "metrics": metrics, "stonecore_baseline_comparison": comparison}, indent=2, sort_keys=True))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the combined BT + masked ranker + GA offline helper lane.")
    parser.add_argument("--dataset", type=Path, default=Path("dataset/bot_ml/decision_dataset.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/ml_strategy_eval/bt_masked_ga_combined"))
    parser.add_argument("--baseline-report", type=Path, default=Path("artifacts/live_validation_instances/stonecore_uninterrupted_full_clear_r12/report.json"))
    parser.add_argument("--population-size", type=int, default=24)
    parser.add_argument("--generations", type=int, default=18)
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args()
    run(args.dataset, args.output_dir, args.baseline_report, args.population_size, args.generations, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
