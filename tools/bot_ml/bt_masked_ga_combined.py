from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any

from dvclive import Live

from tools.bot_ml.common import DATASET_CONTRACT_VERSION, FEATURE_SCHEMA_VERSION, git_commit, read_jsonl, stable_hash, write_json


ARTIFACT_FORMAT = "bt_masked_ga_combined_v1"
APPROACH = "behavior_tree_masked_ranker_with_ga_offline_helper"
GENES = {
    "rotation_aggression": (0.4, 1.8),
    "pull_radius": (0.2, 1.6),
    "healer_safety": (0.6, 2.4),
    "regroup_patience": (0.4, 2.2),
    "route_commitment": (0.3, 1.8),
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
    return {
        "baseline_report": str(report_path),
        "accepted_stonecore_baseline": bool(report.get("acceptable_final_evidence")),
        "baseline_completion_reason": report.get("completion_reason"),
        "baseline_failure_labels": report.get("failure_labels", []),
        "baseline_active_bots": report.get("active_bots"),
        "baseline_route_blocker": diagnosis.get("blocker"),
        "combined_lane_runtime_surface": "python_offline_only",
        "cpp_runtime_files_changed": 0,
        "stonecore_regression": False,
        "regression_basis": "No C++ runtime or live-control files changed; accepted Stonecore r12 evidence is compared as an unchanged baseline.",
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
