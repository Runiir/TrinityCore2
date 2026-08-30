from __future__ import annotations

import json
from math import hypot, isfinite
from pathlib import Path
from typing import Any

try:
    from tools.raid_program.capture_value_types import _positive_int
except ModuleNotFoundError:
    from capture_value_types import _positive_int


ROOT = Path(__file__).resolve().parents[2]


def _frozen_drudge_member_anchors(
    route_manifest: Path | None = None,
) -> dict[int, tuple[float, float, float]]:
    """Load reviewed per-slot Drudge geometry from a sealed route manifest.

    Production capture passes the exact generated manifest selected and hashed
    by ``validate_runtime_profile_assets``.  The default exists only for the
    pure verifier tests; live capture must never re-read the mutable controller
    checkout after binding a different worktree.
    """
    try:
        manifest = route_manifest or (
            ROOT / "dataset/validation_scenarios/validation_routes.jsonl"
        )
        rows = [
            json.loads(line)
            for line in manifest.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        by_scenario: list[dict[int, tuple[float, float, float]]] = []
        for scenario_id in (
            "blackwing_descent_10n",
            "blackwing_descent_10n_magmaw_diagnostic",
        ):
            node = next(
                row for row in rows
                if row.get("scenario_id") == scenario_id
                and row.get("mechanic_profile") == "trash_two_tank_charge_lanes"
            )
            anchors = {
                int(row["roster_slot"]): (
                    float(row["x"]), float(row["y"]), float(row["z"])
                )
                for row in node.get("split_recovery_member_anchors", [])
            }
            combat_tank_anchors = {
                int(row["roster_slot"]): (
                    float(row["x"]), float(row["y"]), float(row["z"])
                )
                for row in node.get("split_tank_combat_anchors", [])
            }
            navigation_tank_anchors = {
                int(row["roster_slot"]): (
                    float(row["x"]), float(row["y"]), float(row["z"])
                )
                for row in node.get("split_tank_navigation_anchors", [])
            }
            recovery_tank_anchors = {
                int(row["roster_slot"]): (
                    float(row["x"]), float(row["y"]), float(row["z"])
                )
                for row in node.get("split_tank_recovery_anchors", [])
            }
            if (set(anchors) != set(range(1, 11)) or (
                node.get("boss_recovery_policy") != "native_full_wipe_only"
            ) or set(combat_tank_anchors) != {1, 2}
                    or set(navigation_tank_anchors) != {1, 2}):
                return {}
            # The contract anchors prove conservative native chase geometry;
            # the separately sealed navigation anchors are exact Detour
            # terminals and therefore own the live tank arrival evidence.
            if set(recovery_tank_anchors) != {1, 2}:
                return {}
            # Drudges are fought at the sealed entrance formation. Only the
            # two tanks use the initial navigation anchors long enough to gain
            # native ownership and pull the pair away from Magmaw.
            anchors.update(recovery_tank_anchors)
            by_scenario.append(anchors)
        return by_scenario[0] if by_scenario[0] == by_scenario[1] else {}
    except (OSError, KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError):
        return {}


def _validate_drudge_observation_geometry(
    observation: dict[str, Any],
    roster: list[dict[str, Any]],
    tank_guids: set[int],
    frozen_anchors: dict[int, tuple[float, float, float]] | None = None,
) -> list[str]:
    """Recompute the frozen two-lane geometry from immutable coordinates.

    The runtime's ``reseparation_recorded`` bit and lane-side booleans are
    claims, not acceptance evidence.  This verifier deliberately recomputes
    projections, source separation, tank ownership geometry, and every
    non-tank anchor from the serialized observation so a forged completion bit
    or crossed source cannot certify a capture.
    """

    geometry = observation.get("geometry")
    if not isinstance(geometry, dict):
        return ["drudge_observation_geometry_missing"]
    required = (
        "entrance_pull_established",
        "home0_x", "home0_y", "home1_x", "home1_y", "midpoint_x", "midpoint_y",
        "axis_x", "axis_y", "lane_separation", "minimum_distance", "navigation_margin",
        "source0_x", "source0_y", "source0_projection", "source0_lane_side_valid",
        "source0_health_pct",
        "source1_x", "source1_y", "source1_projection", "source1_lane_side_valid",
        "source1_health_pct",
        "source0_victim_guid", "source1_victim_guid",
        "source0_alive", "source1_alive",
        "source_separation", "minimum_source_separation", "minimum_member_spacing",
        "arrival_tolerance", "tank_arrival_tolerance", "members",
        "tank0_x", "tank0_y", "tank0_guid", "tank0_slot", "tank0_projection",
        "tank0_source_distance", "tank1_x", "tank1_y", "tank1_guid", "tank1_slot",
        "tank1_projection", "tank1_source_distance",
    )
    reasons: list[str] = []

    def number(name: str) -> float | None:
        value = geometry.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
            reasons.append(f"drudge_geometry_{name}_invalid")
            return None
        return float(value)

    boolean_fields = {
        "entrance_pull_established",
        "source0_lane_side_valid", "source1_lane_side_valid",
        "source0_alive", "source1_alive",
    }
    values = {
        name: number(name)
        for name in required
        if name not in boolean_fields and name != "members"
    }
    entrance_pull_established = geometry.get("entrance_pull_established")
    if not isinstance(entrance_pull_established, bool):
        reasons.append("drudge_geometry_entrance_pull_established_invalid")
        entrance_pull_established = False
    if any(value is None for value in values.values()):
        return sorted(set(reasons))
    tolerance = 0.05
    home_dx = values["home1_x"] - values["home0_x"]
    home_dy = values["home1_y"] - values["home0_y"]
    home_length = hypot(home_dx, home_dy)
    if home_length <= 0.001:
        reasons.append("drudge_geometry_home_axis_invalid")
        return sorted(set(reasons))
    expected_axis = (home_dx / home_length, home_dy / home_length)
    if hypot(values["axis_x"] - expected_axis[0], values["axis_y"] - expected_axis[1]) > tolerance:
        reasons.append("drudge_geometry_axis_mismatch")
    expected_midpoint = (
        (values["home0_x"] + values["home1_x"]) * 0.5,
        (values["home0_y"] + values["home1_y"]) * 0.5,
    )
    if hypot(values["midpoint_x"] - expected_midpoint[0], values["midpoint_y"] - expected_midpoint[1]) > tolerance:
        reasons.append("drudge_geometry_midpoint_mismatch")
    lane_sep = values["lane_separation"]
    minimum_source_sep = values["minimum_source_separation"]
    minimum_spacing = values["minimum_member_spacing"]
    arrival_tolerance = values["arrival_tolerance"]
    tank_arrival_tolerance = values["tank_arrival_tolerance"]
    if (lane_sep <= 0 or minimum_source_sep <= 0 or minimum_spacing <= 0
            or arrival_tolerance <= 0 or tank_arrival_tolerance <= 0
            or tank_arrival_tolerance > arrival_tolerance):
        reasons.append("drudge_geometry_threshold_invalid")
    # Frozen in validation_scenarios_cata_001.json, BWD step 3
    # (trash_two_tank_charge_lanes); these are contract values, not claims
    # copied from the runtime row.
    frozen_thresholds = {
        "minimum_source_separation": 15.0,
        "navigation_margin": 2.0,
        "lane_separation": 17.0,
        "minimum_distance": 15.0,
        "minimum_member_spacing": 3.0,
        "arrival_tolerance": 2.0,
        "tank_arrival_tolerance": 1.0,
    }
    for name, expected in frozen_thresholds.items():
        if abs(values[name] - expected) > tolerance:
            reasons.append(f"drudge_geometry_{name}_contract_mismatch")
    if abs(values["lane_separation"] - (
        values["minimum_source_separation"] + values["navigation_margin"]
    )) > tolerance:
        reasons.append("drudge_geometry_lane_separation_contract_mismatch")

    def projection(x: float, y: float) -> float:
        return ((x - values["midpoint_x"]) * values["axis_x"]
                + (y - values["midpoint_y"]) * values["axis_y"])

    source_positions = (
        (values["source0_x"], values["source0_y"], "source0"),
        (values["source1_x"], values["source1_y"], "source1"),
    )
    source_projections: list[float] = []
    for index, (x, y, prefix) in enumerate(source_positions):
        computed = projection(x, y)
        source_projections.append(computed)
        if abs(values[f"{prefix}_projection"] - computed) > tolerance:
            reasons.append(f"drudge_geometry_{prefix}_projection_mismatch")
        expected_side = entrance_pull_established or (
            (-1.0 if index == 0 else 1.0) * computed >= lane_sep * 0.25
        )
        if geometry.get(f"{prefix}_lane_side_valid") is not expected_side:
            reasons.append(f"drudge_geometry_{prefix}_lane_side_mismatch")
        if not expected_side:
            reasons.append(f"drudge_geometry_{prefix}_lane_side_unsafe")
        if not isinstance(geometry.get(f"{prefix}_alive"), bool):
            reasons.append(f"drudge_geometry_{prefix}_alive_invalid")
        health_pct = values[f"{prefix}_health_pct"]
        if health_pct < 0.0 or health_pct > 100.0:
            reasons.append(f"drudge_geometry_{prefix}_health_invalid")
        if geometry.get(f"{prefix}_alive") is not (health_pct > 0.0):
            reasons.append(f"drudge_geometry_{prefix}_alive_health_mismatch")
        if geometry.get(f"{prefix}_alive") is True and not _positive_int(geometry.get(f"{prefix}_victim_guid")):
            reasons.append(f"drudge_geometry_{prefix}_victim_missing")
        if geometry.get(f"{prefix}_alive") is False and geometry.get(f"{prefix}_victim_guid") not in (0, None):
            reasons.append(f"drudge_geometry_{prefix}_dead_victim_present")
    source_separation = hypot(
        values["source1_x"] - values["source0_x"],
        values["source1_y"] - values["source0_y"],
    )
    if abs(values["source_separation"] - source_separation) > tolerance:
        reasons.append("drudge_geometry_source_separation_mismatch")
    if source_separation < lane_sep:
        reasons.append("drudge_geometry_source_separation_unsafe")

    roster_by_guid = {
        row.get("guid"): row for row in roster
        if isinstance(row, dict) and _positive_int(row.get("guid"))
    }
    lane_a_slots = {1, 3, 4, 6, 7}
    expected_tank_by_slot = {
        int(row["slot"]) + 1: int(row["guid"])
        for row in roster
        if isinstance(row, dict) and row.get("role") == "tank"
        and _positive_int(row.get("guid"))
    }
    source_victims = {
        0: geometry.get("source0_victim_guid"),
        1: geometry.get("source1_victim_guid"),
    }
    for source_index, victim in source_victims.items():
        alive = geometry.get(f"source{source_index}_alive")
        expected_victim = expected_tank_by_slot.get(source_index + 1)
        if alive is True and (not _positive_int(victim) or victim != expected_victim):
            reasons.append(f"drudge_geometry_source{source_index}_victim_invalid")
        if alive is False and victim not in (0, None):
            reasons.append(f"drudge_geometry_source{source_index}_dead_victim_present")
    members = geometry.get("members")
    if not isinstance(members, list):
        reasons.append("drudge_geometry_members_missing")
        return sorted(set(reasons))
    member_by_guid = {
        row.get("guid"): row for row in members
        if isinstance(row, dict) and _positive_int(row.get("guid"))
    }
    if set(member_by_guid) != set(roster_by_guid) or len(members) != len(roster_by_guid):
        reasons.append("drudge_geometry_exact_members_missing")
    canonical_tanks = (
        ("tank0", values["tank0_guid"], values["tank0_slot"], 0,
         values["tank0_x"], values["tank0_y"], values["tank0_projection"], values["tank0_source_distance"]),
        ("tank1", values["tank1_guid"], values["tank1_slot"], 1,
         values["tank1_x"], values["tank1_y"], values["tank1_projection"], values["tank1_source_distance"]),
    )
    canonical_guids: set[int] = set()
    frozen_anchors = frozen_anchors or _frozen_drudge_member_anchors()
    if set(frozen_anchors) != set(range(1, 11)):
        reasons.append("drudge_geometry_frozen_member_anchors_missing")
    for prefix, guid_value, slot_value, source_index, x, y, stored_projection, stored_distance in canonical_tanks:
        raw_guid = geometry.get(f"{prefix}_guid")
        raw_slot = geometry.get(f"{prefix}_slot")
        if (not isinstance(raw_guid, int) or isinstance(raw_guid, bool) or raw_guid <= 0
                or not isinstance(raw_slot, int) or isinstance(raw_slot, bool) or raw_slot <= 0):
            reasons.append(f"drudge_geometry_{prefix}_identity_invalid")
            continue
        guid, slot = raw_guid, raw_slot
        canonical_guids.add(guid)
        expected_guid = expected_tank_by_slot.get(source_index + 1)
        if guid != expected_guid or slot != source_index + 1:
            reasons.append(f"drudge_geometry_{prefix}_identity_invalid")
        expected_anchor = frozen_anchors.get(source_index + 1)
        if (expected_anchor is None
                or hypot(x - expected_anchor[0], y - expected_anchor[1])
                > tank_arrival_tolerance):
            reasons.append(f"drudge_geometry_{prefix}_declared_anchor_mismatch")
        computed_projection = projection(x, y)
        if abs(stored_projection - computed_projection) > tolerance:
            reasons.append(f"drudge_geometry_{prefix}_projection_mismatch")
        source_x, source_y, _ = source_positions[source_index]
        distance = hypot(x - source_x, y - source_y)
        if abs(stored_distance - distance) > tolerance:
            reasons.append(f"drudge_geometry_{prefix}_source_distance_mismatch")
        if distance > minimum_source_sep:
            reasons.append(f"drudge_geometry_{prefix}_source_distance_unsafe")
        member = member_by_guid.get(guid)
        if not isinstance(member, dict):
            reasons.append(f"drudge_geometry_{prefix}_member_missing")
        else:
            for field, expected in (("x", x), ("y", y), ("projection", stored_projection)):
                observed = member.get(field)
                if (not isinstance(observed, (int, float)) or isinstance(observed, bool)
                        or not isfinite(observed) or abs(float(observed) - expected) > tolerance):
                    reasons.append(f"drudge_geometry_{prefix}_member_{field}_mismatch")
        if (not entrance_pull_established
                and (-1.0 if source_index == 0 else 1.0) * computed_projection
                    < lane_sep * 0.25):
            reasons.append(f"drudge_geometry_{prefix}_lane_side_invalid")
    if hypot(values["tank1_x"] - values["tank0_x"], values["tank1_y"] - values["tank0_y"]) < minimum_source_sep:
        reasons.append("drudge_geometry_tank_pair_separation_unsafe")
    if canonical_guids != tank_guids:
        reasons.append("drudge_geometry_canonical_tanks_missing")

    non_tank_positions: dict[int, tuple[float, float, bool]] = {}
    for guid, roster_row in roster_by_guid.items():
        member = member_by_guid.get(guid)
        if not isinstance(member, dict):
            continue
        slot = roster_row.get("slot")
        expected_slot = int(slot) + 1 if isinstance(slot, int) and not isinstance(slot, bool) else -1
        if member.get("roster_slot") != expected_slot:
            reasons.append("drudge_geometry_member_slot_mismatch")
            continue
        def member_number(name: str) -> float | None:
            value = member.get(name)
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not isfinite(value):
                reasons.append(f"drudge_geometry_member_{name}_invalid")
                return None
            return float(value)
        x = member_number("x")
        y = member_number("y")
        stored_projection = member_number("projection")
        if x is None or y is None or stored_projection is None:
            continue
        computed_projection = projection(x, y)
        if abs(stored_projection - computed_projection) > tolerance:
            reasons.append("drudge_geometry_member_projection_mismatch")
        slot_one = expected_slot
        lane_a = slot_one in lane_a_slots
        home_lane_minimum = hypot(
            values["home1_x"] - values["home0_x"],
            values["home1_y"] - values["home0_y"],
        ) * 0.25
        recovery_lane_minimum = max(
            0.0, home_lane_minimum - arrival_tolerance,
        )
        side_valid = entrance_pull_established or (
            (-1.0 if lane_a else 1.0) * computed_projection
            >= recovery_lane_minimum
        )
        if member.get("lane_side_valid") is not side_valid:
            reasons.append("drudge_geometry_member_lane_side_mismatch")
        if not side_valid:
            reasons.append("drudge_geometry_member_lane_side_unsafe")
        if guid in tank_guids:
            continue
        non_tank_positions[guid] = (x, y, lane_a)
        source_distances = (
            hypot(x - values["source0_x"], y - values["source0_y"]),
            hypot(x - values["source1_x"], y - values["source1_y"]),
        )
        if any(distance < values["minimum_distance"] for distance in source_distances):
            reasons.append("drudge_geometry_member_source_distance_unsafe")
        if member.get("anchor_selected") is not True:
            reasons.append("drudge_geometry_member_anchor_missing")
        if member.get("anchor_path_valid") is not True:
            reasons.append("drudge_geometry_member_anchor_path_unverified")
        candidate_index = member.get("anchor_candidate_index")
        if not isinstance(candidate_index, int) or isinstance(candidate_index, bool) or candidate_index != 0:
            reasons.append("drudge_geometry_member_anchor_index_invalid")
            continue
        expected_anchor_xyz = frozen_anchors.get(slot_one)
        if expected_anchor_xyz is None:
            reasons.append("drudge_geometry_member_declared_anchor_missing")
            continue
        expected_anchor = expected_anchor_xyz[:2]
        stored_anchor = (member_number("anchor_x"), member_number("anchor_y"))
        if stored_anchor[0] is None or stored_anchor[1] is None:
            continue
        if hypot(stored_anchor[0] - expected_anchor[0], stored_anchor[1] - expected_anchor[1]) > tolerance:
            reasons.append("drudge_geometry_member_anchor_mismatch")
        anchor_distance = hypot(x - expected_anchor[0], y - expected_anchor[1])
        stored_distance = member_number("anchor_distance")
        if stored_distance is None or abs(stored_distance - anchor_distance) > tolerance:
            reasons.append("drudge_geometry_member_anchor_distance_mismatch")
        if anchor_distance > arrival_tolerance:
            reasons.append("drudge_geometry_member_anchor_unsafe")
        stored_base = (member_number("group_anchor_base_x"), member_number("group_anchor_base_y"))
        if stored_base[0] is None or stored_base[1] is None or hypot(
            stored_base[0] - expected_anchor[0], stored_base[1] - expected_anchor[1]
        ) > tolerance:
            reasons.append("drudge_geometry_member_anchor_base_mismatch")

    for guid, (x, y, lane_a) in non_tank_positions.items():
        same_lane = [
            hypot(x - other_x, y - other_y)
            for other_guid, (other_x, other_y, other_lane_a) in non_tank_positions.items()
            if other_guid != guid and other_lane_a == lane_a
        ]
        nearest = min(same_lane) if same_lane else 0.0
        member = member_by_guid[guid]
        stored_nearest = member.get("nearest_same_lane_distance")
        if not isinstance(stored_nearest, (int, float)) or isinstance(stored_nearest, bool) or not isfinite(stored_nearest) or abs(float(stored_nearest) - nearest) > tolerance:
            reasons.append("drudge_geometry_member_spacing_measurement_mismatch")
        spacing_valid = not same_lane or nearest >= minimum_spacing
        if member.get("same_lane_spacing_valid") is not spacing_valid:
            reasons.append("drudge_geometry_member_spacing_invalid")
        if not spacing_valid:
            reasons.append("drudge_geometry_member_spacing_unsafe")
    return sorted(set(reasons))
