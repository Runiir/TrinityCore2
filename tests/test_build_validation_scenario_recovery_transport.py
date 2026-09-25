"""Recovery rides derived from the composed full route (request to M).

The scenario builder attaches, to every route row that lies across a ride
between two levels, that ride's unchanged transport contract
(`recovery_transport`), from the scenario's own route and from its composed
parent route. BWD: the lower-wing elevator (full-route step 8) separates the
upper wing (entrance, Magmaw, Omnotron) from every lower-wing node, so every
Maloriak, Atramedes, Chimaeron and Nefarian row (legacy and canonical c0
shards, and the full route after step 8) carries it, and no other row does.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.bot_ml import build_validation_scenario_manifests as builder


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
ELEVATOR_ID = "bwd.transit.lower_wing_elevator"
LOWER_WING = ("maloriak", "atramedes", "chimaeron", "nefarian")


def _scenarios() -> dict[str, dict]:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    rows = list(config.get("scenarios") or []) + list(config.get("diagnostic_scenarios") or [])
    return {str(row["id"]): row for row in rows if isinstance(row, dict) and row.get("id")}


def _derived(scenarios: dict[str, dict], scenario_id: str) -> dict[str, list]:
    scenario = scenarios[scenario_id]
    parent = scenarios.get(str(scenario.get("diagnostic_parent_scenario_id") or ""), {})
    rides = builder.recovery_rides(scenario.get("route") or [], parent.get("route") or [])
    return {str(step.get("node_id") or index): builder.recovery_transport(step, rides)
            for index, step in enumerate(scenario.get("route") or [])}


def test_full_route_rows_after_the_elevator_carry_it() -> None:
    scenarios = _scenarios()
    for scenario_id in ("blackwing_descent_10n", "blackwing_descent_10n_full_c0"):
        full = scenarios[scenario_id]
        transit = next(step for step in full["route"] if step["node_id"] == ELEVATOR_ID)
        assert builder.ride_levels(transit["transport_contract"]) == (190.163, 76.8211)
        derived = _derived(scenarios, scenario_id)
        order = [step["node_id"] for step in full["route"]]
        cut = order.index(ELEVATOR_ID)
        for node_id in order[:cut + 1]:
            assert derived[node_id] == [], (scenario_id, node_id)
        for node_id in order[cut + 1:]:
            assert derived[node_id] == [
                {"node_id": ELEVATOR_ID, "contract": transit["transport_contract"]}], (scenario_id, node_id)
    # The Nefarian descent boards without an exit: never a recovery ride.
    assert builder.ride_levels(next(step for step in full["route"]
                                    if step["node_id"] == "bwd.nefarian.descent")["transport_contract"]) is None


def test_lower_wing_shards_derive_the_elevator_from_their_parent_route() -> None:
    scenarios = _scenarios()
    transit = next(step for step in scenarios["blackwing_descent_10n"]["route"]
                   if step["node_id"] == ELEVATOR_ID)["transport_contract"]
    checked = 0
    for scenario_id, scenario in scenarios.items():
        if (not scenario_id.startswith("blackwing_descent_10n_") or "_full_" in scenario_id
                or not scenario.get("route")):
            continue
        derived = _derived(scenarios, scenario_id)
        lower = any(f"_{boss}_" in scenario_id for boss in LOWER_WING)
        for node_id, across in derived.items():
            if lower:
                assert across == [{"node_id": ELEVATOR_ID, "contract": transit}], (scenario_id, node_id)
            else:
                assert across == [], (scenario_id, node_id)
        checked += 1
    assert checked >= 12


def test_rows_without_a_ride_stay_byte_identical() -> None:
    # Scenarios without a ride in their own or parent route (Stonecore, the
    # accepted Magmaw shard) gain no field.
    scenarios = _scenarios()
    for scenario_id in scenarios:
        if "blackwing_descent" in scenario_id:
            continue
        assert all(not across for across in _derived(scenarios, scenario_id).values()), scenario_id


def test_the_builder_emits_the_field_under_its_runtime_name() -> None:
    source = (ROOT / "tools/bot_ml/build_validation_scenario_manifests.py").read_text(encoding="utf-8")
    assert 'route["recovery_transport"] = across' in source
    assert 'rides.append({"node_id": node_id, "contract": contract})' in source
    assert "RECOVERY_MIN_LEVEL_SEPARATION_YARDS = 8.0" in source
