"""Build the deterministic Phase 9 Stonecore constrained covering array."""

from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from .common import write_json
from .live_validation_session import canonical_sha256, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS = REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
DEFAULT_POLICY = REPO_ROOT / "experiments/configs/stonecore_phase9_pair_policy_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "experiments/configs/stonecore_phase9_pairwise_matrix_v1.json"

ROLE_ORDER = {"tank": 0, "healer": 1, "dps": 2}


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def target_roles(
    target_catalog: Mapping[str, Any], policy: Mapping[str, Any]
) -> tuple[dict[str, str], list[str]]:
    rows = target_catalog.get("targets") or []
    canonical_roles = {
        str(row["spec_target_id"]): str(row["role"])
        for row in rows
        if isinstance(row, Mapping)
    }
    if len(canonical_roles) != 31 or Counter(canonical_roles.values()) != Counter({"tank": 4, "healer": 5, "dps": 22}):
        raise ValueError("Phase 9 requires the canonical 4 tank, 5 healer, and 22 DPS targets")
    qualification = policy.get("live_qualification_policy") or {}
    exclusion_rows = qualification.get("excluded_targets") or []
    excluded = sorted(str(row.get("spec_target_id") or "") for row in exclusion_rows if isinstance(row, Mapping))
    if not excluded or len(excluded) != len(set(excluded)) or any(target not in canonical_roles for target in excluded):
        raise ValueError("Phase 9 live qualification exclusions must name unique canonical targets")
    if any(
        str(row.get("role") or "") != canonical_roles.get(str(row.get("spec_target_id") or ""))
        or not str(row.get("reason") or "").strip()
        for row in exclusion_rows
        if isinstance(row, Mapping)
    ):
        raise ValueError("Phase 9 live qualification exclusions require the canonical role and a reason")
    roles = {target: role for target, role in canonical_roles.items() if target not in excluded}
    declared_by_role = {
        role: sorted(
            str(value)
            for value in qualification.get(f"supported_{role}_targets") or []
        )
        for role in ("tank", "healer", "dps")
    }
    active_by_role = {
        role: sorted(target for target, target_role in roles.items() if target_role == role)
        for role in ("tank", "healer", "dps")
    }
    if (
        Counter(roles.values()) != Counter({"tank": 3, "healer": 5, "dps": 16})
        or declared_by_role != active_by_role
    ):
        raise ValueError(
            "Phase 9 live qualification requires the exact targeted 25H spec surface"
        )

    roster = policy.get("progression_roster_25h") or {}
    shape = roster.get("default_shape") or {}
    slots = roster.get("slots") or []
    slot_names = [str(row.get("slot") or "") for row in slots if isinstance(row, Mapping)]
    slot_targets = {
        str(row.get(key) or "")
        for row in slots
        if isinstance(row, Mapping)
        for key in ("class_spec", "alternate", "alternate_role_spec")
        if str(row.get(key) or "")
    }
    slot_groups = Counter(name.split("_", 1)[0] for name in slot_names)
    slot_roles_valid = all(
        canonical_roles.get(str(row.get("class_spec") or ""))
        == ("tank" if str(row.get("slot") or "").startswith("tank_")
            else "healer" if str(row.get("slot") or "").startswith("healer_")
            else "dps")
        and (
            not row.get("alternate")
            or canonical_roles.get(str(row.get("alternate")))
            == canonical_roles.get(str(row.get("class_spec") or ""))
        )
        and (
            not row.get("alternate_role_spec")
            or canonical_roles.get(str(row.get("alternate_role_spec"))) == "tank"
        )
        for row in slots
        if isinstance(row, Mapping)
    )
    if (
        shape != {
            "tank": 2,
            "healer": 6,
            "dps": 17,
            "ranged_dps": 12,
            "melee_dps": 5,
            "total": 25,
        }
        or len(slots) != 25
        or len(slot_names) != len(set(slot_names))
        or "" in slot_names
        or slot_groups != Counter({"tank": 2, "healer": 6, "ranged": 12, "melee": 5})
        or not slot_roles_valid
        or slot_targets != set(roles)
    ):
        raise ValueError("Phase 9 targeted 25H roster contract is malformed")
    return roles, excluded


def ordered_pair(left: str, right: str, roles: Mapping[str, str]) -> tuple[str, str, str]:
    left_role = roles[left]
    right_role = roles[right]
    if left == right:
        return "self", left, right
    if left_role == right_role == "dps":
        first, second = sorted((left, right))
        return "dps_dps", first, second
    if left_role == right_role == "tank":
        first, second = sorted((left, right))
        return "tank_tank", first, second
    if left_role == right_role == "healer":
        first, second = sorted((left, right))
        return "healer_healer", first, second
    ordered = sorted((left, right), key=lambda target: (ROLE_ORDER[roles[target]], target))
    return f"{roles[ordered[0]]}_{roles[ordered[1]]}", ordered[0], ordered[1]


def pair_id(kind: str, left: str, right: str) -> str:
    return f"{kind}:{left}|{right}"


def normalize_policy_pairs(
    policy: Mapping[str, Any], roles: Mapping[str, str]
) -> set[str]:
    normalized: set[str] = set()
    for row in policy.get("policy_incompatible_pairs") or []:
        if not isinstance(row, list) or len(row) != 2:
            raise ValueError("policy_incompatible_pairs rows must contain exactly two target IDs")
        left, right = (str(value) for value in row)
        if left not in roles or right not in roles or left == right:
            raise ValueError(f"invalid policy-incompatible pair: {row!r}")
        kind, first, second = ordered_pair(left, right, roles)
        if kind != "dps_dps":
            raise ValueError("Phase 9 policy-incompatible pairs may only remove otherwise-valid DPS-DPS pairs")
        normalized.add(pair_id("policy_incompatible", first, second))
    return normalized


def build_pair_universe(
    roles: Mapping[str, str], policy: Mapping[str, Any]
) -> tuple[set[str], set[str], set[tuple[str, str]]]:
    targets = sorted(roles)
    policy_pair_ids = normalize_policy_pairs(policy, roles)
    policy_pairs = {
        tuple(pair.removeprefix("policy_incompatible:").split("|", 1))
        for pair in policy_pair_ids
    }
    required: set[str] = set()
    excluded: set[str] = set()
    for target in targets:
        excluded.add(pair_id("self", target, target))
    for left, right in itertools.combinations(targets, 2):
        kind, first, second = ordered_pair(left, right, roles)
        if kind in {"tank_tank", "healer_healer"}:
            excluded.add(pair_id(kind, first, second))
        elif kind == "dps_dps" and (first, second) in policy_pairs:
            excluded.add(pair_id("policy_incompatible", first, second))
        elif kind in {"tank_healer", "tank_dps", "healer_dps", "dps_dps"}:
            required.add(pair_id(kind, first, second))
        else:
            raise ValueError(f"unexpected pair kind: {kind}")
    return required, excluded, policy_pairs


def composition_pairs(
    tank: str,
    healer: str,
    dps: tuple[str, str, str],
) -> set[str]:
    pairs = {
        pair_id("tank_healer", tank, healer),
        *(pair_id("tank_dps", tank, target) for target in dps),
        *(pair_id("healer_dps", healer, target) for target in dps),
        *(
            pair_id("dps_dps", left, right)
            for left, right in itertools.combinations(dps, 2)
        ),
    }
    return set(pairs)


def candidate_rows(
    roles: Mapping[str, str], policy_pairs: set[tuple[str, str]]
) -> list[dict[str, Any]]:
    tanks = sorted(target for target, role in roles.items() if role == "tank")
    healers = sorted(target for target, role in roles.items() if role == "healer")
    dps_targets = sorted(target for target, role in roles.items() if role == "dps")
    rows: list[dict[str, Any]] = []
    for tank in tanks:
        for healer in healers:
            for trio in itertools.combinations(dps_targets, 3):
                if any(pair in policy_pairs for pair in itertools.combinations(trio, 2)):
                    continue
                members = (tank, healer, *trio)
                identity = {"tank": tank, "healer": healer, "dps": list(trio)}
                rows.append(
                    {
                        "tank": tank,
                        "healer": healer,
                        "dps": trio,
                        "members": members,
                        "pairs": frozenset(composition_pairs(tank, healer, trio)),
                        "composition_sha256": canonical_sha256(identity),
                    }
                )
    return rows


def greedy_cover(
    candidates: list[dict[str, Any]], required_pairs: set[str]
) -> list[dict[str, Any]]:
    uncovered = set(required_pairs)
    representation: Counter[str] = Counter()
    selected: list[dict[str, Any]] = []
    available = list(candidates)
    while uncovered:
        best = min(
            available,
            key=lambda row: (
                -len(row["pairs"] & uncovered),
                max(representation[target] for target in row["members"]),
                sum(representation[target] for target in row["members"]),
                row["tank"],
                row["healer"],
                row["dps"],
            ),
        )
        gain = best["pairs"] & uncovered
        if not gain:
            raise ValueError(f"covering array stalled with {len(uncovered)} uncovered pairs")
        selected.append(best)
        uncovered.difference_update(gain)
        representation.update(best["members"])
        available.remove(best)

    pair_counts = Counter(pair for row in selected for pair in row["pairs"])
    for row in reversed(selected.copy()):
        if all(pair_counts[pair] > 1 for pair in row["pairs"]):
            selected.remove(row)
            for pair in row["pairs"]:
                pair_counts[pair] -= 1
    return selected


def select_serial_canaries(
    rows: list[dict[str, Any]],
    roles: Mapping[str, str],
    policy: Mapping[str, Any],
) -> list[dict[str, Any]]:
    serial_policy = policy.get("serial_canary_policy") or {}
    pinned_hashes = [
        str(value) for value in serial_policy.get("composition_sha256s") or []
    ]
    expected_count = int(serial_policy.get("composition_count") or 0)
    if not pinned_hashes or len(pinned_hashes) != expected_count:
        raise ValueError("Phase 9 requires an explicitly pinned serial canary subset")
    if len(pinned_hashes) != len(set(pinned_hashes)):
        raise ValueError("serial canary composition hashes must be unique")

    row_by_hash = {str(row["composition_sha256"]): row for row in rows}
    missing_hashes = [value for value in pinned_hashes if value not in row_by_hash]
    if missing_hashes:
        raise ValueError(
            "serial canaries must reference selected covering-array compositions: "
            f"{missing_hashes}"
        )
    selected = [row_by_hash[value] for value in pinned_hashes]

    target_set = set(roles)
    selected_union = {target for row in selected for target in row["members"]}
    if selected_union != target_set:
        raise ValueError(
            "serial canaries must cover every canonical target exactly as a union: "
            f"missing={sorted(target_set - selected_union)} "
            f"unexpected={sorted(selected_union - target_set)}"
        )

    representation = Counter(target for row in selected for target in row["members"])
    bounds = serial_policy.get("role_representation_bounds") or {}
    for target in sorted(target_set):
        role = roles[target]
        role_bounds = bounds.get(role) or {}
        minimum = int(role_bounds.get("min") or 0)
        maximum = int(role_bounds.get("max") or 0)
        count = representation[target]
        if minimum <= 0 or maximum < minimum or not minimum <= count <= maximum:
            raise ValueError(
                f"serial canary representation for {target} is {count}, "
                f"outside the configured {role} bounds {minimum}..{maximum}"
            )

    support_policy = serial_policy.get("native_threat_transfer_support") or {}
    supported_tanks = {
        str(value) for value in support_policy.get("tank_targets") or []
    }
    support_targets = {
        str(value) for value in support_policy.get("support_targets") or []
    }
    minimum_support = int(
        support_policy.get("minimum_support_targets_per_composition") or 0
    )
    if supported_tanks and (not support_targets or minimum_support <= 0):
        raise ValueError("native threat-transfer support policy is incomplete")
    for row in selected:
        if row["tank"] not in supported_tanks:
            continue
        support_count = len(set(row["dps"]) & support_targets)
        if support_count < minimum_support:
            raise ValueError(
                f"serial canary {row['composition_sha256']} pairs {row['tank']} "
                f"with only {support_count} native threat-transfer targets"
            )
    return selected


def pair_kind(pair: str) -> str:
    return pair.split(":", 1)[0]


def representation_rows(
    rows: Iterable[dict[str, Any]], roles: Mapping[str, str]
) -> list[dict[str, Any]]:
    counts = Counter(target for row in rows for target in row["members"])
    return [
        {
            "spec_target_id": target,
            "role": roles[target],
            "composition_count": counts[target],
        }
        for target in sorted(roles, key=lambda value: (ROLE_ORDER[roles[value]], value))
    ]


def build_matrix(
    targets_path: Path, policy_path: Path
) -> dict[str, Any]:
    target_catalog = load_object(targets_path)
    policy = load_object(policy_path)
    if policy.get("schema") != "stonecore_phase9_pair_policy_v1":
        raise ValueError("unexpected Phase 9 pair-policy schema")
    roles, qualification_excluded_targets = target_roles(target_catalog, policy)
    required, excluded, policy_pairs = build_pair_universe(roles, policy)
    candidates = candidate_rows(roles, policy_pairs)
    selected = greedy_cover(candidates, required)
    candidate_by_hash = {str(row["composition_sha256"]): row for row in candidates}
    selected_hashes = {str(row["composition_sha256"]) for row in selected}
    for pinned_hash in (policy.get("serial_canary_policy") or {}).get("composition_sha256s") or []:
        pinned_hash = str(pinned_hash)
        if pinned_hash not in candidate_by_hash:
            raise ValueError(f"serial canary is not a valid live-qualification composition: {pinned_hash}")
        if pinned_hash not in selected_hashes:
            selected.append(candidate_by_hash[pinned_hash])
            selected_hashes.add(pinned_hash)

    rendered_rows: list[dict[str, Any]] = []
    row_by_hash: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(selected, start=1):
        composition_id = f"stonecore_phase9_{index:03d}_{row['composition_sha256'][:12]}"
        rendered = {
            "composition_id": composition_id,
            "composition_sha256": row["composition_sha256"],
            "tank": row["tank"],
            "healer": row["healer"],
            "dps": list(row["dps"]),
            "ordered_party": list(row["members"]),
            "lease_keys": [f"all_spec_candidate_pool:{target}" for target in row["members"]],
            "covered_pair_ids": sorted(row["pairs"]),
        }
        rendered_rows.append(rendered)
        row_by_hash[row["composition_sha256"]] = rendered

    serial = select_serial_canaries(selected, roles, policy)
    serial_rows = [
        {
            "serial_index": index,
            "composition_id": row_by_hash[row["composition_sha256"]]["composition_id"],
            "composition_sha256": row["composition_sha256"],
            "ordered_party": list(row["members"]),
            "new_targets": sorted(
                set(row["members"])
                - set(
                    target
                    for prior in serial[: index - 1]
                    for target in prior["members"]
                )
            ),
        }
        for index, row in enumerate(serial, start=1)
    ]
    covered = set().union(*(row["pairs"] for row in selected)) if selected else set()
    required_by_kind = Counter(pair_kind(pair) for pair in required)
    covered_by_kind = Counter(pair_kind(pair) for pair in covered)
    excluded_by_kind = Counter(pair_kind(pair) for pair in excluded)
    representation = representation_rows(selected, roles)
    serial_representation = representation_rows(serial, roles)
    composition_mapping = {
        row["composition_id"]: row["covered_pair_ids"] for row in rendered_rows
    }
    matrix: dict[str, Any] = {
        "schema": "stonecore_phase9_pairwise_matrix_v1",
        "algorithm": {
            "name": "deterministic_greedy_uncovered_pair_cover_v1",
            "candidate_order": "tank_lexical_then_healer_lexical_then_canonical_sorted_dps_triple",
            "tie_break": "maximum_uncovered_gain_then_minimum_member_representation_then_lexical",
            "redundancy_pruning": "reverse_selection_order_when_every_pair_remains_covered",
            "serial_canary_selection": "policy_pinned_all_live_qualification_target_subset_with_native_threat_transfer_support",
            "pinned_serial_rows_retained": True,
        },
        "inputs": {
            "target_catalog_path": str(targets_path.relative_to(REPO_ROOT)),
            "target_catalog_sha256": sha256_file(targets_path),
            "pair_policy_path": str(policy_path.relative_to(REPO_ROOT)),
            "pair_policy_sha256": sha256_file(policy_path),
            "candidate_pool_tag": str(target_catalog.get("candidate_pool_scenario_id") or ""),
        },
        "composition_contract": {
            "tank": 1,
            "healer": 1,
            "dps": 3,
            "dps_triple_order": "lexically_sorted_before_hashing",
            "party_order": "tank_then_healer_then_sorted_dps",
            "certification": "strict_uninterrupted_current_manifest_full_clear",
            "diagnostic_segments_certify": False,
        },
        "canonical_target_count": 31,
        "qualification_excluded_targets": qualification_excluded_targets,
        "target_count": len(roles),
        "candidate_composition_count": len(candidates),
        "selected_composition_count": len(rendered_rows),
        "required_pair_count": len(required),
        "covered_pair_count": len(covered),
        "uncovered_pair_count": len(required - covered),
        "excluded_pair_count": len(excluded),
        "required_pair_counts_by_kind": dict(sorted(required_by_kind.items())),
        "covered_pair_counts_by_kind": dict(sorted(covered_by_kind.items())),
        "excluded_pair_counts_by_kind": dict(sorted(excluded_by_kind.items())),
        "required_pair_ids": sorted(required),
        "covered_pair_ids": sorted(covered),
        "uncovered_pair_ids": sorted(required - covered),
        "excluded_pair_ids": sorted(excluded),
        "representation": representation,
        "representation_sha256": canonical_sha256(representation),
        "compositions": rendered_rows,
        "composition_to_pair_ids": composition_mapping,
        "serial_canary_count": len(serial_rows),
        "serial_canaries": serial_rows,
        "serial_representation": serial_representation,
        "serial_target_union": sorted(
            {target for row in serial for target in row["members"]}
        ),
    }
    matrix["pair_universe_sha256"] = canonical_sha256(
        {
            "required": matrix["required_pair_ids"],
            "excluded": matrix["excluded_pair_ids"],
        }
    )
    matrix["composition_set_sha256"] = canonical_sha256(rendered_rows)
    matrix["serial_canary_set_sha256"] = canonical_sha256(serial_rows)
    matrix["matrix_sha256"] = canonical_sha256(matrix)
    return matrix


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    matrix = build_matrix(args.targets.resolve(), args.policy.resolve())
    write_json(args.output.resolve(), matrix)
    print(
        json.dumps(
            {
                "matrix_sha256": matrix["matrix_sha256"],
                "selected_composition_count": matrix["selected_composition_count"],
                "serial_canary_count": matrix["serial_canary_count"],
                "required_pair_count": matrix["required_pair_count"],
                "uncovered_pair_count": matrix["uncovered_pair_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not matrix["uncovered_pair_ids"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
