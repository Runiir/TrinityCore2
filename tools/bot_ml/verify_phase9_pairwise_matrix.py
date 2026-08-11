"""Independently reconstruct and verify the Phase 9 pairwise matrix contract."""

from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from .common import write_json
from .live_validation_session import canonical_sha256, sha256_file


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TARGETS = REPO_ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
DEFAULT_POLICY = REPO_ROOT / "experiments/configs/stonecore_phase9_pair_policy_v1.json"
DEFAULT_MATRIX = REPO_ROOT / "experiments/configs/stonecore_phase9_pairwise_matrix_v1.json"
DEFAULT_OUTPUT = REPO_ROOT / "dataset/all_spec_phase9_pairwise_contract"


def load_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def pair_key(kind: str, first: str, second: str) -> str:
    return f"{kind}:{first}|{second}"


def reconstruct_universe(
    roles: Mapping[str, str], policy: Mapping[str, Any]
) -> tuple[set[str], set[str]]:
    policy_exclusions = {
        tuple(sorted((str(row[0]), str(row[1]))))
        for row in policy.get("policy_incompatible_pairs") or []
    }
    required: set[str] = set()
    excluded = {pair_key("self", target, target) for target in roles}
    for first, second in itertools.combinations(sorted(roles), 2):
        first_role = roles[first]
        second_role = roles[second]
        role_set = {first_role, second_role}
        if first_role == second_role == "tank":
            excluded.add(pair_key("tank_tank", first, second))
        elif first_role == second_role == "healer":
            excluded.add(pair_key("healer_healer", first, second))
        elif first_role == second_role == "dps":
            if (first, second) in policy_exclusions:
                excluded.add(pair_key("policy_incompatible", first, second))
            else:
                required.add(pair_key("dps_dps", first, second))
        elif role_set == {"tank", "healer"}:
            tank = first if first_role == "tank" else second
            healer = second if first_role == "tank" else first
            required.add(pair_key("tank_healer", tank, healer))
        elif role_set == {"tank", "dps"}:
            tank = first if first_role == "tank" else second
            dps = second if first_role == "tank" else first
            required.add(pair_key("tank_dps", tank, dps))
        elif role_set == {"healer", "dps"}:
            healer = first if first_role == "healer" else second
            dps = second if first_role == "healer" else first
            required.add(pair_key("healer_dps", healer, dps))
        else:
            raise ValueError(f"unhandled role pair: {first_role}, {second_role}")
    return required, excluded


def reconstruct_composition_pairs(
    tank: str, healer: str, dps: list[str]
) -> set[str]:
    return {
        pair_key("tank_healer", tank, healer),
        *(pair_key("tank_dps", tank, target) for target in dps),
        *(pair_key("healer_dps", healer, target) for target in dps),
        *(
            pair_key("dps_dps", first, second)
            for first, second in itertools.combinations(dps, 2)
        ),
    }


def verify(
    targets_path: Path,
    policy_path: Path,
    matrix_path: Path,
) -> dict[str, Any]:
    targets = load_object(targets_path)
    policy = load_object(policy_path)
    matrix = load_object(matrix_path)
    canonical_roles = {
        str(row["spec_target_id"]): str(row["role"])
        for row in targets.get("targets") or []
        if isinstance(row, Mapping)
    }
    qualification = policy.get("live_qualification_policy") or {}
    exclusion_rows = qualification.get("excluded_targets") or []
    excluded_targets = sorted(
        str(row.get("spec_target_id") or "")
        for row in exclusion_rows
        if isinstance(row, Mapping)
    )
    roles = {
        target: role
        for target, role in canonical_roles.items()
        if target not in excluded_targets
    }
    live_qualification_tanks = sorted(
        str(value) for value in qualification.get("supported_tank_targets") or []
    )
    expected_required, expected_excluded = reconstruct_universe(roles, policy)
    observed_required = set(matrix.get("required_pair_ids") or [])
    observed_excluded = set(matrix.get("excluded_pair_ids") or [])

    composition_ids: list[str] = []
    composition_hashes: list[str] = []
    mapped_pairs: set[str] = set()
    malformed: list[str] = []
    mapping_mismatches: list[str] = []
    target_counts: Counter[str] = Counter()
    composition_mapping = matrix.get("composition_to_pair_ids") or {}
    for row in matrix.get("compositions") or []:
        composition_id = str(row.get("composition_id") or "")
        tank = str(row.get("tank") or "")
        healer = str(row.get("healer") or "")
        dps = [str(value) for value in row.get("dps") or []]
        ordered_party = [str(value) for value in row.get("ordered_party") or []]
        identity = {"tank": tank, "healer": healer, "dps": dps}
        expected_hash = canonical_sha256(identity)
        expected_pairs = reconstruct_composition_pairs(tank, healer, dps) if len(dps) == 3 else set()
        row_pairs = set(row.get("covered_pair_ids") or [])
        mapped_row_pairs = set(composition_mapping.get(composition_id) or [])
        valid = bool(
            composition_id
            and roles.get(tank) == "tank"
            and roles.get(healer) == "healer"
            and len(dps) == 3
            and len(set(dps)) == 3
            and dps == sorted(dps)
            and all(roles.get(target) == "dps" for target in dps)
            and len(set(ordered_party)) == 5
            and ordered_party == [tank, healer, *dps]
            and row.get("composition_sha256") == expected_hash
            and row_pairs == expected_pairs
            and not (expected_pairs & expected_excluded)
        )
        if not valid:
            malformed.append(composition_id or "<missing>")
        if mapped_row_pairs != expected_pairs:
            mapping_mismatches.append(composition_id or "<missing>")
        composition_ids.append(composition_id)
        composition_hashes.append(str(row.get("composition_sha256") or ""))
        mapped_pairs.update(expected_pairs)
        target_counts.update(ordered_party)

    serial_rows = matrix.get("serial_canaries") or []
    serial_ids = [str(row.get("composition_id") or "") for row in serial_rows]
    serial_hashes = [
        str(row.get("composition_sha256") or "") for row in serial_rows
    ]
    selected_ids = set(composition_ids)
    serial_union = {
        str(target)
        for row in serial_rows
        for target in row.get("ordered_party") or []
    }
    serial_counts = Counter(
        str(target)
        for row in serial_rows
        for target in row.get("ordered_party") or []
    )
    serial_policy = policy.get("serial_canary_policy") or {}
    expected_serial_hashes = [
        str(value) for value in serial_policy.get("composition_sha256s") or []
    ]
    expected_serial_count = int(serial_policy.get("composition_count") or 0)
    serial_bounds = serial_policy.get("role_representation_bounds") or {}
    serial_representation_in_bounds = all(
        int((serial_bounds.get(role) or {}).get("min") or 0)
        <= serial_counts[target]
        <= int((serial_bounds.get(role) or {}).get("max") or 0)
        for target, role in roles.items()
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
    serial_native_support_valid = bool(
        supported_tanks and support_targets and minimum_support > 0
    ) and all(
        not row.get("ordered_party")
        or str(row["ordered_party"][0]) not in supported_tanks
        or len(
            {
                str(target)
                for target in row.get("ordered_party") or []
            }
            & support_targets
        )
        >= minimum_support
        for row in serial_rows
    )
    serial_representation = {
        str(row.get("spec_target_id") or ""): int(row.get("composition_count") or 0)
        for row in matrix.get("serial_representation") or []
    }
    representation = {
        str(row.get("spec_target_id") or ""): int(row.get("composition_count") or 0)
        for row in matrix.get("representation") or []
    }
    expected_pair_universe_hash = canonical_sha256(
        {"required": sorted(expected_required), "excluded": sorted(expected_excluded)}
    )
    matrix_identity = dict(matrix)
    stored_matrix_hash = str(matrix_identity.pop("matrix_sha256", ""))
    checks = {
        "target_catalog_is_canonical_31": len(canonical_roles) == 31
        and Counter(canonical_roles.values()) == Counter({"tank": 4, "healer": 5, "dps": 22}),
        "live_qualification_exclusion_is_exact": excluded_targets == ["protection_warrior"]
        and len(exclusion_rows) == 1
        and str(exclusion_rows[0].get("role") or "") == "tank"
        and bool(str(exclusion_rows[0].get("reason") or "").strip())
        and Counter(roles.values()) == Counter({"tank": 3, "healer": 5, "dps": 22})
        and live_qualification_tanks == sorted(target for target, role in roles.items() if role == "tank")
        and matrix.get("canonical_target_count") == 31
        and matrix.get("qualification_excluded_targets") == excluded_targets
        and matrix.get("target_count") == len(roles),
        "input_hashes_match": (matrix.get("inputs") or {}).get("target_catalog_sha256") == sha256_file(targets_path)
        and (matrix.get("inputs") or {}).get("pair_policy_sha256") == sha256_file(policy_path),
        "required_universe_matches_independent_reconstruction": observed_required == expected_required,
        "excluded_universe_matches_independent_reconstruction": observed_excluded == expected_excluded,
        "required_and_excluded_are_disjoint": not (observed_required & observed_excluded),
        "all_compositions_well_formed": not malformed,
        "composition_ids_are_unique": bool(composition_ids)
        and len(composition_ids) == len(set(composition_ids))
        and "" not in composition_ids,
        "composition_hashes_are_unique": len(composition_hashes) == len(set(composition_hashes))
        and "" not in composition_hashes,
        "composition_mapping_matches_independent_reconstruction": not mapping_mismatches,
        "zero_uncovered_required_pairs": mapped_pairs == expected_required
        and not set(matrix.get("uncovered_pair_ids") or []),
        "no_excluded_pair_is_covered": not (mapped_pairs & expected_excluded),
        "representation_matches_compositions": representation == dict(target_counts),
        "every_target_is_represented": set(target_counts) == set(roles)
        and min(target_counts.values(), default=0) > 0,
        "serial_canaries_reference_selected_compositions": bool(serial_ids)
        and set(serial_ids) <= selected_ids
        and len(serial_ids) == len(set(serial_ids)),
        "serial_canaries_match_pinned_policy": len(serial_rows) == expected_serial_count
        and serial_hashes == expected_serial_hashes,
        "serial_canaries_cover_all_live_qualification_targets": serial_union == set(roles)
        and sorted(serial_union) == matrix.get("serial_target_union"),
        "serial_canary_representation_matches_compositions": serial_representation
        == dict(serial_counts),
        "serial_canary_representation_is_balanced": serial_representation_in_bounds,
        "serial_canaries_have_native_threat_transfer_support": serial_native_support_valid,
        "pair_universe_hash_matches": matrix.get("pair_universe_sha256") == expected_pair_universe_hash,
        "matrix_hash_valid": bool(stored_matrix_hash)
        and canonical_sha256(matrix_identity) == stored_matrix_hash,
    }
    report: dict[str, Any] = {
        "schema": "all_spec_phase9_pairwise_contract_v1",
        "matrix_path": display_path(matrix_path),
        "matrix_file_sha256": sha256_file(matrix_path),
        "matrix_identity_sha256": stored_matrix_hash,
        "target_catalog_sha256": sha256_file(targets_path),
        "pair_policy_sha256": sha256_file(policy_path),
        "independent_required_pair_count": len(expected_required),
        "independent_excluded_pair_count": len(expected_excluded),
        "observed_composition_count": len(composition_ids),
        "observed_serial_canary_count": len(serial_ids),
        "malformed_composition_ids": malformed,
        "mapping_mismatch_composition_ids": mapping_mismatches,
        "missing_required_pair_ids": sorted(expected_required - mapped_pairs),
        "unexpected_covered_pair_ids": sorted(mapped_pairs - expected_required),
        "checks": checks,
        "passed": all(checks.values()),
    }
    report["contract_sha256"] = canonical_sha256(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=Path, default=DEFAULT_TARGETS)
    parser.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    targets_path = args.targets.resolve()
    policy_path = args.policy.resolve()
    matrix_path = args.matrix.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    contract = verify(targets_path, policy_path, matrix_path)
    contract_path = output_dir / "contract.json"
    write_json(contract_path, contract)
    manifest = {
        "schema": "all_spec_phase9_pairwise_contract_manifest_v1",
        "contract_path": display_path(contract_path),
        "contract_file_sha256": sha256_file(contract_path),
        "contract_identity_sha256": contract["contract_sha256"],
        "passed": contract["passed"],
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if contract["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
