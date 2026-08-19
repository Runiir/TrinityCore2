#!/usr/bin/env python3
"""Inspect raid-performance prerequisites and emit one bounded work unit.

This command is deliberately read-only.  It joins the frozen roster, exact
WoWSims reference lifecycle, encounter strategy catalog, and script-readiness
inventory so an agent can see identity blockers before changing gameplay code.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from tools.bot_ml.build_wowsims_reference_requests import pending_catalog_projection


ROOT = Path(__file__).resolve().parents[2]
ROSTER_PATH = Path("experiments/configs/cata_raid_roster_25_v1.json")
DPS_ACCEPTANCE_PATH = Path("experiments/configs/cata_raid_dps_acceptance_v1.json")
TARGET_CATALOG_PATH = Path("experiments/configs/all_spec_targets_cata_p4_v1.json")
REFERENCE_CATALOG_PATH = Path("experiments/configs/all_spec_references_cata_p4_v1.json")
WOWSIMS_REQUESTS_PATH = Path(
    "experiments/configs/wowsims_cata_dps_reference_requests_v1.json"
)
WOWSIMS_PROMOTION_PATH = Path(
    "experiments/configs/wowsims_cata_dps_reference_promotion_index_v1.json"
)
WOWSIMS_BUNDLE = Path("artifacts/all_spec_program/wowsims_exact_reference_bundle_v1")
WOWSIMS_DVC_POINTER = Path(
    "artifacts/all_spec_program/wowsims_exact_reference_bundle_v1.dvc"
)
STRATEGY_CATALOG_PATH = Path("experiments/configs/cata_raid_strategy_catalog_v1.json")
SCRIPT_READINESS_PATH = Path("experiments/configs/cata_raid_script_readiness_v1.json")
PROGRAM_STATUS_PATH = Path(
    "experiments/configs/cata_raid_progression_program_status_v1.json"
)

EXPECTED_ROLE_COUNTS = {
    "tank": 2,
    "healer": 6,
    "ranged_dps": 12,
    "melee_dps": 5,
}
MODE_FIELDS = ("class_spec", "alternate_spec", "alternate_role_spec")
HAGARA_ALIASES = {"hagara": "hagara_the_stormbinder"}


class WorkloopError(ValueError):
    """Raised when a canonical workloop input is malformed."""


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkloopError(f"invalid_json:{path}") from exc
    if not isinstance(value, dict):
        raise WorkloopError(f"json_object_required:{path}")
    return value


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _repo_file(root: Path, relative: Any) -> Path | None:
    candidate = Path(str(relative or ""))
    if not candidate.parts or candidate.is_absolute() or ".." in candidate.parts:
        return None
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        return None
    return resolved


def _descriptor_file(root: Path, descriptor: Any) -> Path | None:
    if not isinstance(descriptor, Mapping):
        return None
    path = _repo_file(root, descriptor.get("path"))
    expected = str(descriptor.get("sha256") or "")
    if path is None or not re.fullmatch(r"[0-9a-f]{64}", expected):
        return None
    return path if _file_sha256(path) == expected else None


def _git_head(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=False,
    )
    value = completed.stdout.strip()
    return (
        value
        if completed.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", value)
        else None
    )


def _dvc_digest(path: Path) -> str | None:
    if not path.is_file():
        return None
    match = re.search(r"(?m)^\s*-\s+md5:\s+([^\s]+)\s*$", path.read_text())
    return match.group(1) if match else None


def roster_status(root: Path = ROOT) -> dict[str, Any]:
    roster = _load_json(root / ROSTER_PATH)
    acceptance = _load_json(root / DPS_ACCEPTANCE_PATH)
    slots = roster.get("slots")
    if not isinstance(slots, list):
        raise WorkloopError("roster_slots_missing")

    role_counts = Counter(
        str(row.get("role") or "") for row in slots if isinstance(row, dict)
    )
    supported_modes = {
        str(row[field])
        for row in slots
        if isinstance(row, dict)
        for field in MODE_FIELDS
        if row.get(field)
    }
    optional_modes = {
        str(row["alternate_role_spec"])
        for row in slots
        if isinstance(row, dict) and row.get("alternate_role_spec")
    }
    required_modes = supported_modes - optional_modes
    dps_targets = {str(value) for value in acceptance.get("dps_targets") or []}
    roster_dps_modes = {
        str(row[field])
        for row in slots
        if isinstance(row, dict) and str(row.get("role") or "").endswith("dps")
        for field in ("class_spec", "alternate_spec")
        if row.get(field)
    }
    issues: list[str] = []
    if len(slots) != 25:
        issues.append("roster_slot_count_not_25")
    if dict(role_counts) != EXPECTED_ROLE_COUNTS:
        issues.append("roster_role_shape_mismatch")
    if len(supported_modes) != 24:
        issues.append("supported_mode_count_not_24")
    if len(required_modes) != 23:
        issues.append("required_mode_count_not_23")
    if roster_dps_modes != dps_targets or len(dps_targets) != 16:
        issues.append("dps_target_universe_mismatch")

    return {
        "ready": not issues,
        "roster_id": roster.get("roster_id"),
        "slot_count": len(slots),
        "role_counts": dict(sorted(role_counts.items())),
        "supported_modes": sorted(supported_modes),
        "supported_mode_count": len(supported_modes),
        "required_modes": sorted(required_modes),
        "required_mode_count": len(required_modes),
        "optional_modes": sorted(optional_modes),
        "dps_targets": sorted(dps_targets),
        "dps_target_count": len(dps_targets),
        "issues": issues,
    }


def _candidate_receipts(root: Path, request_catalog_sha256: str) -> dict[str, Any]:
    receipt_dir = root / WOWSIMS_BUNDLE / "generation_receipts"
    current: dict[str, dict[str, Any]] = {}
    stale: dict[str, dict[str, Any]] = {}
    invalid: list[str] = []
    for path in sorted(receipt_dir.glob("*.json")) if receipt_dir.is_dir() else []:
        if _file_sha256(path) != path.stem:
            invalid.append(path.relative_to(root).as_posix())
            continue
        receipt = _load_json(path)
        spec = str(receipt.get("target_spec") or "")
        if not spec or spec in current or spec in stale:
            invalid.append(path.relative_to(root).as_posix())
            continue
        row = {
            "path": path.relative_to(root).as_posix(),
            "request_catalog_sha256": receipt.get("request_catalog_sha256"),
            "classification": receipt.get("classification"),
            "gate_bearing": receipt.get("gate_bearing") is True,
            "dps": (receipt.get("result_observation") or {}).get("dps"),
        }
        target = current if receipt.get("request_catalog_sha256") == request_catalog_sha256 else stale
        target[spec] = row
    return {"current": current, "stale": stale, "invalid": invalid}


def _promotion_state(
    root: Path,
    entry: Mapping[str, Any],
    *,
    request_catalog_sha256: str,
    dvc_digest: str | None,
) -> dict[str, Any]:
    spec = str(entry.get("target_spec") or "")
    generation_descriptor = entry.get("generation_receipt")
    reconstruction_path = _descriptor_file(root, entry.get("dvc_reconstruction_receipt"))
    if reconstruction_path is None:
        return {"target_spec": spec, "state": "reconstruction_receipt_missing_or_invalid"}
    reconstruction = _load_json(reconstruction_path)
    published_digest = str(
        (((reconstruction.get("dvc_pointer") or {}).get("out") or {}).get("digest"))
        or ""
    )
    if not dvc_digest or published_digest != dvc_digest:
        return {"target_spec": spec, "state": "published_bundle_pointer_stale"}
    listed = {
        str(row.get("target_spec") or ""): row
        for row in reconstruction.get("generation_receipts") or []
        if isinstance(row, Mapping)
    }
    if spec not in listed or listed[spec].get("sha256") != (
        generation_descriptor or {}
    ).get("sha256"):
        return {"target_spec": spec, "state": "reconstruction_target_mismatch"}
    generation_path = _descriptor_file(root, generation_descriptor)
    if generation_path is None:
        return {"target_spec": spec, "state": "current_remote_requires_hydration"}
    generation = _load_json(generation_path)
    if generation.get("request_catalog_sha256") != request_catalog_sha256:
        return {"target_spec": spec, "state": "request_catalog_identity_stale"}
    if generation.get("target_spec") != spec:
        return {"target_spec": spec, "state": "generation_target_mismatch"}
    dps = (generation.get("result_observation") or {}).get("dps")
    if not isinstance(dps, (int, float)) or dps <= 0:
        return {"target_spec": spec, "state": "generation_dps_missing"}
    return {
        "target_spec": spec,
        "state": "locally_reconstructed_current",
        "dps": dps,
        "generation_receipt": generation_path.relative_to(root).as_posix(),
    }


def wowsims_status(root: Path = ROOT) -> dict[str, Any]:
    roster = roster_status(root)
    requests = _load_json(root / WOWSIMS_REQUESTS_PATH)
    promotion = _load_json(root / WOWSIMS_PROMOTION_PATH)
    request_rows = requests.get("requests") or []
    request_specs = {
        str(row.get("target_spec") or "") for row in request_rows if isinstance(row, dict)
    }
    pending_requests = pending_catalog_projection(requests)
    request_catalog_sha256 = _canonical_sha256(pending_requests)
    request_catalog_file_sha256 = _file_sha256(root / WOWSIMS_REQUESTS_PATH)
    candidates = _candidate_receipts(root, request_catalog_sha256)
    dvc_digest = _dvc_digest(root / WOWSIMS_DVC_POINTER)
    promotion_rows = [
        _promotion_state(
            root,
            row,
            request_catalog_sha256=request_catalog_sha256,
            dvc_digest=dvc_digest,
        )
        for row in promotion.get("entries") or []
        if isinstance(row, Mapping)
    ]
    promotion_states = Counter(row["state"] for row in promotion_rows)
    accepted = {
        row["target_spec"]: row
        for row in promotion_rows
        if row["state"] == "locally_reconstructed_current"
    }
    issues: list[str] = []
    if request_specs != set(roster["dps_targets"]):
        issues.append("request_target_universe_mismatch")
    if len(candidates["current"]) != len(roster["dps_targets"]):
        issues.append("current_generation_receipts_incomplete")
    if len(accepted) != len(roster["dps_targets"]):
        issues.append("current_promoted_references_incomplete")
    if candidates["invalid"]:
        issues.append("invalid_generation_receipts")

    return {
        "ready": not issues,
        "provider": requests.get("provider"),
        "provider_revision": requests.get("provider_revision"),
        "request_catalog_path": WOWSIMS_REQUESTS_PATH.as_posix(),
        "request_catalog_canonical_sha256": request_catalog_sha256,
        "request_catalog_file_sha256": request_catalog_file_sha256,
        "request_count": len(request_rows),
        "request_target_count": len(request_specs),
        "current_candidate_count": len(candidates["current"]),
        "stale_candidate_count": len(candidates["stale"]),
        "invalid_candidate_receipts": candidates["invalid"],
        "dvc_bundle_digest": dvc_digest,
        "promotion_states": dict(sorted(promotion_states.items())),
        "accepted_reference_count": len(accepted),
        "accepted_dps": {
            spec: accepted[spec]["dps"] for spec in sorted(accepted)
        },
        "issues": issues,
        "_candidate_details": candidates,
        "_promotion_details": promotion_rows,
    }


def encounter_status(root: Path = ROOT) -> dict[str, Any]:
    readiness = _load_json(root / SCRIPT_READINESS_PATH)
    strategies = _load_json(root / STRATEGY_CATALOG_PATH)
    head = _git_head(root)
    encounter_states = Counter()
    encounter_count = 0
    for raid in readiness.get("raids") or []:
        for encounter in raid.get("encounters") or []:
            encounter_count += 1
            encounter_states[str(encounter.get("status") or "missing_status")] += 1
    strategy_rows = [
        row
        for raid in (strategies.get("raids") or {}).values()
        for row in raid.get("bosses") or []
    ]
    fidelity_states = Counter(str(row.get("fidelity_state") or "") for row in strategy_rows)
    audit_current = bool(head and readiness.get("repository_commit") == head)
    issues: list[str] = []
    if encounter_count != len(strategy_rows):
        issues.append("strategy_and_script_inventory_count_mismatch")
    if not audit_current:
        issues.append("script_readiness_audit_commit_stale")
    if encounter_states.get("missing_dedicated_implementation", 0):
        issues.append("boss_implementations_missing")
    if fidelity_states.get("fidelity_blocked", 0):
        issues.append("encounter_fidelity_unresolved")
    return {
        "ready": not issues,
        "repository_head": head,
        "script_readiness_commit": readiness.get("repository_commit"),
        "script_readiness_audit_current": audit_current,
        "named_encounter_count": encounter_count,
        "script_states": dict(sorted(encounter_states.items())),
        "strategy_fidelity_states": dict(sorted(fidelity_states.items())),
        "issues": issues,
    }


def build_status(root: Path = ROOT) -> dict[str, Any]:
    roster = roster_status(root)
    wowsims = wowsims_status(root)
    encounters = encounter_status(root)
    program = _load_json(root / PROGRAM_STATUS_PATH)
    wowsims.pop("_candidate_details", None)
    wowsims.pop("_promotion_details", None)
    return {
        "schema": "raid_performance_workloop_status_v1",
        "ready": roster["ready"] and wowsims["ready"] and encounters["ready"],
        "roster": roster,
        "wowsims": wowsims,
        "encounters": encounters,
        "current_program_next_action": program.get("next_action"),
    }


def _target_maps(root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    targets = _load_json(root / TARGET_CATALOG_PATH)
    references = _load_json(root / REFERENCE_CATALOG_PATH)
    target_map = {
        str(row.get("spec_target_id") or ""): row
        for row in targets.get("targets") or []
        if isinstance(row, Mapping)
    }
    reference_map = {
        str(row.get("spec_target_id") or ""): row
        for row in references.get("references") or []
        if isinstance(row, Mapping)
    }
    return target_map, reference_map


def build_spec_work_unit(spec: str, root: Path = ROOT) -> dict[str, Any]:
    roster = roster_status(root)
    if spec not in set(roster["supported_modes"]):
        raise WorkloopError(f"spec_outside_frozen_roster:{spec}")
    target_catalog = _load_json(root / TARGET_CATALOG_PATH)
    target_map, reference_map = _target_maps(root)
    target = target_map.get(spec)
    if not target:
        raise WorkloopError(f"target_catalog_missing:{spec}")
    role = str(target.get("role") or "")
    slots = [
        row.get("slot")
        for row in _load_json(root / ROSTER_PATH).get("slots") or []
        if isinstance(row, Mapping) and spec in {row.get(field) for field in MODE_FIELDS}
    ]
    reference = reference_map.get(spec) or {}
    output: dict[str, Any] = {
        "schema": "raid_performance_spec_work_unit_v1",
        "work_unit": f"spec:{spec}",
        "spec": spec,
        "role": role,
        "roster_slots": slots,
        "one_hypothesis_only": True,
        "identities": {
            "trinity_git_commit": _git_head(root),
            "roster_id": roster["roster_id"],
            "target_catalog_path": TARGET_CATALOG_PATH.as_posix(),
            "target_catalog_canonical_sha256": _canonical_sha256(target_catalog),
        },
        "profile_dump_command": (
            f".botauto rotations dump {target.get('class_id')} {spec} {role}"
        ),
        "source_paths": {
            "target_catalog": TARGET_CATALOG_PATH.as_posix(),
            "roster": ROSTER_PATH.as_posix(),
            "rotation_sql": ((target.get("runtime_rotation_profile") or {}).get("sql_path")),
            "wowsims_source_relative_apl": ((reference.get("apl") or {}).get("path")),
        },
        "loop": [
            "bind_exact_reference_and_runtime_inputs",
            "locate_first_broken_policy_to_landed_outcome_edge",
            "change_the_smallest_trigger_gate_priority_or_alternative",
            "run_static_and_deterministic_replay_checks",
            "run_one_role_harness_window",
            "run_one_script_ready_boss_shard_only_if_needed",
            "publish_accepted_evidence_and_quarantine_invalid_rows",
        ],
    }
    if role == "dps":
        exact = wowsims_status(root)
        accepted = exact["accepted_dps"].get(spec)
        stale = exact["_candidate_details"]["stale"].get(spec)
        current = exact["_candidate_details"]["current"].get(spec)
        output["benchmark"] = {
            "state": "ready" if accepted is not None else "blocked_exact_reference",
            "state_scope": "dps_acceptance_and_promotion_only",
            "accepted_dps": accepted,
            "accepted_dps_reference_class": "controlled_live_parity",
            "accepted_dps_status_authority": (
                "current_work_unit_catalog_projection_overrides_embedded_run_metadata"
            ),
            "current_unpromoted_candidate": current,
            "stale_candidate_informational_only": stale,
            "reference_class_policy": {
                "selected_acceptance_reference_class": "self_provided_baseline",
                "difference_between_classes": "expected_non_blocking",
                "classes": {
                    "self_provided_baseline": {
                        "state": "requires_generation",
                        "purpose": "one_sided_minimum_throughput_floor",
                        "duration_seconds": 300,
                        "duration_variation_seconds": 0,
                        "external_raid_buffs": False,
                        "external_individual_buffs": False,
                        "preapplied_target_debuffs": False,
                        "self_applied_class_effects": "normal_actions_only",
                        "exact_player_identity_required": True,
                        "pass_rule": "runtime_dps_greater_than_or_equal_to_reference",
                        "upper_rejection_bound": None,
                        "overtuned_is_failure": False,
                        "consumables": {
                            "item_ids": "per_spec_exact",
                            "inventory_provisioning_required": True,
                            "flask": "native_use_before_scoring",
                            "food": "native_use_before_scoring",
                            "prepot": "one_native_use_before_combat",
                            "combat_potion": "one_native_use_during_combat",
                            "static_aura_is_use_receipt": False,
                        },
                    },
                    "controlled_live_parity": {
                        "state": "ready" if accepted is not None else "missing",
                        "catalog_classification": (
                            "current_accepted" if accepted is not None else "missing"
                        ),
                        "purpose": "like_for_like_action_stat_and_damage_diagnosis",
                        "accepted_dps": accepted,
                        "condition_identity_required_for_total_dps": True,
                    },
                    "upstream_full_throughput": {
                        "state": "informational_only",
                        "purpose": "duration_bound_capability_and_ui_cross_check",
                        "supplies_acceptance_denominator": False,
                    },
                },
                "does_not_block": [
                    "static_rotation_review",
                    "unaffected_action_membership",
                    "unaffected_priority_order",
                    "eligible_cast_mix",
                    "action_rejections",
                    "pet_execution",
                ],
            },
            "diagnostic_policy": {
                "state": "ready_trace_only",
                "allowed_signals": [
                    "cast_mix",
                    "cast_cadence",
                    "action_rejections",
                    "priority_order",
                    "aura_uptime",
                    "resource_flow",
                    "pet_execution",
                ],
                "parameter_mismatch": (
                    "compare_unaffected_signals_and_isolate_sensitive_actions"
                ),
                "requires_one_attributable_first_broken_edge": True,
                "max_implementation_hypotheses": 1,
                "forbidden_claims": [
                    "stale_reference_as_tuning_target",
                    "simulator_dps_ratio",
                    "qualification_or_promotion",
                ],
            },
            "required_reference_work_unit": {
                "owner_skill": "raid-wowsims-reference",
                "work_unit": "wowsims:cata_raid_dps_reference_cohort_v1",
                "reference_class": "controlled_live_parity",
                "atomic_promotion_required": True,
                "target_count": len(roster["dps_targets"]),
                "target_specs": roster["dps_targets"],
                "provider": exact["provider"],
                "provider_revision": exact["provider_revision"],
                "request_catalog_path": exact["request_catalog_path"],
                "request_catalog_canonical_sha256": exact[
                    "request_catalog_canonical_sha256"
                ],
                "request_catalog_file_sha256": exact[
                    "request_catalog_file_sha256"
                ],
                "requested_spec": spec,
                "requested_spec_source_relative_apl": (
                    (reference.get("apl") or {}).get("path")
                ),
            },
            "required_self_provided_reference_work_unit": {
                "owner_skill": "raid-wowsims-reference",
                "work_unit": (
                    "wowsims:self_provided_baseline:"
                    "cata_raid_dps_reference_cohort_v1"
                ),
                "reference_class": "self_provided_baseline",
                "scope": "simulator_reference_generation_only",
                "atomic_promotion_required": True,
                "target_count": len(roster["dps_targets"]),
                "target_specs": roster["dps_targets"],
                "duration_seconds": 300,
                "duration_variation_seconds": 0,
                "external_raid_buffs": False,
                "external_individual_buffs": False,
                "preapplied_target_debuffs": False,
                "simulator_per_spec_consumable_item_ids_required": True,
                "runtime_receipts_are_not_reference_owner_output": True,
                "requested_spec": spec,
            },
            "downstream_runtime_consumable_work_units": [
                {
                    "owner_skill": "raid-shard-architecture",
                    "first_broken_edge": "consumable_inventory_provisioning",
                    "requires_exact_item_ids_from": "self_provided_baseline",
                    "output": "inventory_provisioning_and_readback_receipt",
                },
                {
                    "owner_skill": "raid-role-implementation",
                    "first_broken_edge": "consumable_native_execution",
                    "depends_on": "consumable_inventory_provisioning",
                    "required_native_uses": [
                        "flask_before_scoring",
                        "food_before_scoring",
                        "prepot_before_combat",
                        "combat_potion_during_combat",
                    ],
                    "static_aura_is_use_receipt": False,
                },
            ],
            "next_action": (
                "generate_self_provided_reference_and_continue_role_comparison"
                if accepted is not None
                else "run_trace_only_diagnostic_and_handoff_exact_reference"
            ),
        }
    else:
        output["benchmark"] = {
            "state": "role_harness_required",
            "reference_type": (reference.get("expected_output") or {}).get("type"),
            "reference_metrics": (reference.get("expected_output") or {}).get("metrics"),
            "next_action": (
                "run_tank_threat_300" if role == "tank" else "run_healer_controlled_damage_300"
            ),
        }
    return output


def _strategy_row(catalog: Mapping[str, Any], raid: str, boss: str) -> Mapping[str, Any]:
    raid_row = (catalog.get("raids") or {}).get(raid)
    if not isinstance(raid_row, Mapping):
        raise WorkloopError(f"unknown_raid:{raid}")
    for row in raid_row.get("bosses") or []:
        if isinstance(row, Mapping) and row.get("boss_slug") == boss:
            return row
    raise WorkloopError(f"unknown_boss:{raid}:{boss}")


def build_boss_work_unit(
    raid: str, boss: str, mode: str, root: Path = ROOT
) -> dict[str, Any]:
    catalog = _load_json(root / STRATEGY_CATALOG_PATH)
    readiness = _load_json(root / SCRIPT_READINESS_PATH)
    strategy = _strategy_row(catalog, raid, boss)
    if mode not in set(strategy.get("modes") or []):
        raise WorkloopError(f"unsupported_boss_mode:{raid}:{boss}:{mode}")
    raid_readiness = next(
        (row for row in readiness.get("raids") or [] if row.get("raid") == raid), None
    )
    if not isinstance(raid_readiness, Mapping):
        raise WorkloopError(f"script_readiness_raid_missing:{raid}")
    readiness_boss = HAGARA_ALIASES.get(boss, boss)
    script = next(
        (
            row
            for row in raid_readiness.get("encounters") or []
            if row.get("boss") == readiness_boss
        ),
        None,
    )
    if not isinstance(script, Mapping):
        raise WorkloopError(f"script_readiness_boss_missing:{raid}:{boss}")
    source = None
    if script.get("source"):
        source = (
            Path(str(raid_readiness.get("instance_source"))).parent
            / str(script["source"])
        ).as_posix()
    source_present = bool(source and (root / source).is_file())
    task_kind = (
        "implement_missing_boss_script"
        if script.get("status") == "missing_dedicated_implementation"
        else "audit_and_validate_existing_boss_script"
    )
    return {
        "schema": "raid_performance_boss_work_unit_v1",
        "work_unit": f"boss:{raid}:{boss}:{mode}",
        "raid": raid,
        "boss": boss,
        "mode": mode,
        "task_kind": task_kind,
        "script_status": script.get("status"),
        "script_readiness_audit_current": readiness.get("repository_commit") == _git_head(root),
        "source": source,
        "source_present": source_present,
        "instance_source": raid_readiness.get("instance_source"),
        "dossier": strategy.get("dossier"),
        "mechanic_contract": strategy.get("contract"),
        "value_ledger": strategy.get("ledger"),
        "fidelity_state": strategy.get("fidelity_state"),
        "diagnostic_shard_allowed_after_static_gates": source_present,
        "qualification_allowed": strategy.get("fidelity_state") != "fidelity_blocked",
        "loop": [
            "refresh_claim_ledger_from_online_sources_client_data_db_and_scripts",
            "mark_every_unproved_value_or_transition_unresolved",
            "implement_or_repair_native_encounter_state_transitions",
            "add_shared_cpp_replay_cases_for_fragile_transitions",
            "run_one_isolated_diagnostic_shard_with_exact_identity",
            "fix_the_first_broken_observation_candidate_submission_outcome_edge",
            "publish_only_reconstructible_native_evidence",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    spec = subparsers.add_parser("spec")
    spec.add_argument("spec")
    boss = subparsers.add_parser("boss")
    boss.add_argument("raid")
    boss.add_argument("boss")
    boss.add_argument("--mode", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    root = args.root.resolve()
    try:
        if args.command == "status":
            output = build_status(root)
        elif args.command == "spec":
            output = build_spec_work_unit(args.spec, root)
        else:
            output = build_boss_work_unit(args.raid, args.boss, args.mode, root)
    except WorkloopError as exc:
        print(json.dumps({"schema": "raid_performance_workloop_error_v1", "error": str(exc)}))
        return 2
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
