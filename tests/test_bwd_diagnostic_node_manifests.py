from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

from tools.bot_ml.run_live_bot_validation import write_validation_config

from tools.bot_ml.build_validation_scenario_manifests import (
    build_manifests,
    drudge_split_geometry_status,
)
from tools.bot_ml.build_live_scenario_reports import build_reports


ROOT = Path(__file__).resolve().parents[1]
SCENARIO_CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
PROFILE_MANIFEST = ROOT / "dataset/bot_runtime_profiles/profiles.json"
SHARD_FIXTURE = ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"

CANONICAL_ID = "blackwing_descent_10n"
DIAGNOSTIC_IDS = {
    "magmaw": "blackwing_descent_10n_magmaw_diagnostic",
    "omnotron": "blackwing_descent_10n_omnotron_diagnostic",
    "maloriak": "blackwing_descent_10n_maloriak_diagnostic",
    "atramedes": "blackwing_descent_10n_atramedes_diagnostic",
    "chimaeron": "blackwing_descent_10n_chimaeron_diagnostic",
    "nefarian": "blackwing_descent_10n_nefarian_diagnostic",
}


def _config() -> dict:
    return json.loads(SCENARIO_CONFIG.read_text(encoding="utf-8"))


def _manifests() -> dict:
    return build_manifests(
        _config(),
        {
            "all_ready": True,
            "scenarios": [
                {
                    "scenario_id": "stonecore_5n",
                    "role_counts": {"tank": 1, "healer": 1, "dps": 3},
                },
                {
                    "scenario_id": CANONICAL_ID,
                    "role_counts": {"tank": 2, "healer": 3, "dps": 5},
                },
            ],
        },
        {"all_passed": True},
        json.loads(SHARD_FIXTURE.read_text(encoding="utf-8")),
    )


def _routes(manifests: dict, scenario_id: str) -> list[dict]:
    return [row for row in manifests["validation_routes"] if row["scenario_id"] == scenario_id]


def test_drudge_combat_anchor_geometry_is_sql_bound_and_requires_native_chase_margin():
    config = _config()
    canonical = next(row for row in config["scenarios"] if row["id"] == CANONICAL_ID)
    drudges = next(
        row for row in canonical["route"]
        if row.get("mechanic_profile") == "trash_two_tank_charge_lanes"
    )
    assert drudge_split_geometry_status(drudges) == (True, "")

    unsafe = deepcopy(drudges)
    unsafe["split_tank_combat_anchors"] = [
        {"roster_slot": 1, "x": -294.904, "y": -50.6863, "z": 212.232},
        {"roster_slot": 2, "x": -311.842, "y": -49.2321, "z": 212.129},
    ]
    assert drudge_split_geometry_status(unsafe) == (
        False,
        "split_combat_anchor_insufficient_native_chase",
    )

    wrong_oracle = deepcopy(drudges)
    wrong_oracle["split_source_home_anchors"][0]["x"] += 1.0
    assert drudge_split_geometry_status(wrong_oracle) == (
        False,
        "split_source_home_oracle",
    )


def test_canonical_bwd_route_is_still_the_ordered_eleven_node_parent_route():
    routes = _routes(_manifests(), CANONICAL_ID)
    assert [(row["step"], row["kind"], row["label"]) for row in routes] == [
        (1, "regroup", "BWD entrance junction regroup"),
        (2, "trash", "Magmaw Chainwielder trash"),
        (3, "trash", "Magmaw Drudge pair"),
        (4, "boss", "Magmaw"),
        (5, "trash", "Omnotron Golem Sentries"),
        (6, "boss", "Omnotron Defense System"),
        (7, "trash", "laboratory trash"),
        (8, "boss", "Maloriak"),
        (9, "boss", "Atramedes"),
        (10, "boss", "Chimaeron"),
        (11, "boss", "Nefarian"),
    ]
    assert all(row["diagnostic_only"] is False for row in routes)
    assert all(row["runtime_profile_id"] == CANONICAL_ID for row in routes)


def test_each_bwd_diagnostic_shard_has_exact_local_membership_and_unique_profile():
    manifests = _manifests()
    expected = {
        "magmaw": ["BWD entrance junction regroup", "Magmaw Chainwielder trash", "Magmaw Drudge pair", "Magmaw"],
        "omnotron": ["Omnotron sentry approach regroup", "Omnotron Golem Sentries", "Omnotron Defense System"],
        "maloriak": ["Maloriak laboratory regroup", "laboratory trash", "Maloriak"],
        "atramedes": ["Atramedes chamber regroup", "Atramedes"],
        "chimaeron": ["Chimaeron chamber regroup", "Chimaeron"],
        "nefarian": ["Nefarian upper ledge preparation", "Nefarian legitimate upper-ledge descent", "Nefarian"],
    }
    for boss, scenario_id in DIAGNOSTIC_IDS.items():
        routes = _routes(manifests, scenario_id)
        assert [row["label"] for row in routes] == expected[boss]
        assert [row["step"] for row in routes] == list(range(1, len(routes) + 1))
        assert all(row["diagnostic_only"] is True for row in routes)
        assert all(row["runtime_profile_id"] == scenario_id for row in routes)
        assert all(row["diagnostic_parent_scenario_id"] == CANONICAL_ID for row in routes)
        assert all(row["diagnostic_prerequisite_state"]["certifies_predecessors"] is False for row in routes)
        assert all(len(row["roster_identity"]) == 10 for row in routes)
        assert all(len({member["guid"] for member in row["roster_identity"]}) == 10 for row in routes)
        assert all({member["roster_slot_id"] for member in row["roster_identity"]} == {
            "raid_tank_1", "raid_tank_2", "raid_healer_1", "raid_healer_2", "raid_healer_3",
            "raid_dps_1", "raid_dps_2", "raid_dps_3", "raid_dps_4", "raid_dps_5",
        } for row in routes)
        assert routes[-1]["kind"] == "boss"


def test_magmaw_shard_excludes_omnotron_and_later_route_nodes():
    routes = _routes(_manifests(), DIAGNOSTIC_IDS["magmaw"])
    assert [row["source_entry"] for row in routes] == [0, 42649, 42362, 41570]
    assert not any("Omnotron" in row["label"] for row in routes)
    assert not any(row["source_entry"] in {42166, 41378, 41442, 43296, 41376} for row in routes)


def test_diagnostic_prerequisites_are_explicitly_non_certifying():
    scenarios = {row["scenario_id"]: row for row in _manifests()["validation_scenarios"]}
    assert set(DIAGNOSTIC_IDS.values()).issubset(scenarios)
    assert scenarios[CANONICAL_ID]["diagnostic_only"] is False
    assert scenarios[CANONICAL_ID]["prerequisite_contract"] == {}
    assert scenarios[DIAGNOSTIC_IDS["omnotron"]]["prerequisite_contract"]["precompleted_boss_entries"] == [41570]
    assert scenarios[DIAGNOSTIC_IDS["nefarian"]]["prerequisite_contract"]["precompleted_boss_entries"] == [41570, 42166, 41378, 41442, 43296]
    for scenario_id in DIAGNOSTIC_IDS.values():
        row = scenarios[scenario_id]
        assert row["certifies_predecessors"] is False
        assert row["diagnostic_parent_scenario_id"] == CANONICAL_ID


def test_nefarian_shard_starts_on_upper_ledge_and_descends_before_engagement():
    routes = _routes(_manifests(), DIAGNOSTIC_IDS["nefarian"])
    preparation, descent, boss = routes
    assert preparation["label"] == "Nefarian upper ledge preparation"
    assert preparation["z"] == 6.57143
    assert preparation["diagnostic_prerequisite_state"]["upper_ledge_start"] is True
    assert descent["node_kind"] == "descent"
    assert descent["descent_action"] == "native_jump_or_fall"
    assert descent["z"] < preparation["z"]
    assert descent["diagnostic_prerequisite_state"]["requires_native_descent_before_engagement"] is True
    assert boss["label"] == "Nefarian"
    assert [row["kind"] for row in routes] == ["regroup", "descent", "boss"]


def test_runtime_profiles_select_only_the_matching_diagnostic_scenario():
    payload = json.loads(PROFILE_MANIFEST.read_text(encoding="utf-8"))
    profiles = {row["name"]: row for row in payload["profiles"]}
    for scenario_id in DIAGNOSTIC_IDS.values():
        profile = profiles[scenario_id]
        route = profile["validation_route"]
        assert route["scenario_id"] == scenario_id
        assert route["manifest_path"] == "dataset/validation_scenarios/validation_routes.jsonl"
        assert profile["pool_tag_filter"] == scenario_id
        assert profile["diagnostic_only"] is True
        assert profile["diagnostic_parent_scenario_id"] == CANONICAL_ID
        assert profile["prerequisite_contract"]["certifies_predecessors"] is False
    assert len({profiles[scenario_id]["pool_tag_filter"] for scenario_id in DIAGNOSTIC_IDS.values()}) == 6


def test_manifest_config_selects_exact_magmaw_profile_instead_of_base_stonecore(tmp_path: Path):
    route = _routes(_manifests(), DIAGNOSTIC_IDS["magmaw"])[0]
    base = tmp_path / "worldserver.conf"
    base.write_text('BotWorld.AutoStart = 1\nBotWorld.RuntimeProfile = "stonecore_5n"\n', encoding="utf-8")
    manifest = tmp_path / "validation_route_manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    generated = write_validation_config(
        base,
        tmp_path / "run",
        pool_tag=DIAGNOSTIC_IDS["magmaw"],
        validation_route=route,
        validation_route_manifest_path=manifest,
    )
    text = generated.read_text(encoding="utf-8")
    assert f'BotWorld.RuntimeProfile = "{DIAGNOSTIC_IDS["magmaw"]}"' in text
    assert 'BotWorld.RuntimeProfile = "stonecore_5n"' not in text


def test_manifest_config_cannot_override_empty_calibration_controller(tmp_path: Path):
    route = _routes(_manifests(), DIAGNOSTIC_IDS["magmaw"])[0]
    base = tmp_path / "worldserver.conf"
    base.write_text(
        'BotWorld.AutoStart = 0\nBotWorld.RuntimeProfile = "stonecore_5n"\n'
        "BotWorld.TargetPopulation = 5\nBotWorld.ValidationRoute.Enable = 1\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "validation_route_manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    generated = write_validation_config(
        base,
        tmp_path / "run",
        pool_tag=DIAGNOSTIC_IDS["magmaw"],
        validation_route=route,
        validation_route_manifest_path=manifest,
        calibration_only=True,
    )
    text = generated.read_text(encoding="utf-8")
    assert 'BotWorld.RuntimeProfile = ""' in text
    assert f'BotWorld.RuntimeProfile = "{DIAGNOSTIC_IDS["magmaw"]}"' not in text
    assert "BotWorld.TargetPopulation = 0" in text
    assert "BotWorld.ValidationRoute.Enable = 0" in text
    assert "BotWorld.ValidationRoute.ManifestPath" not in text


def test_manifest_config_preserves_disabled_autostart_for_preparation(tmp_path: Path):
    route = _routes(_manifests(), DIAGNOSTIC_IDS["magmaw"])[0]
    base = tmp_path / "worldserver.conf"
    base.write_text('BotWorld.AutoStart = 1\nBotWorld.RuntimeProfile = "stonecore_5n"\n', encoding="utf-8")
    manifest = tmp_path / "validation_route_manifest.json"
    manifest.write_text("{}\n", encoding="utf-8")
    generated = write_validation_config(
        base,
        tmp_path / "run",
        pool_tag=DIAGNOSTIC_IDS["magmaw"],
        validation_route=route,
        validation_route_manifest_path=manifest,
        autostart=False,
    )
    text = generated.read_text(encoding="utf-8")
    assert "BotWorld.AutoStart = 0" in text
    assert f'BotWorld.RuntimeProfile = "{DIAGNOSTIC_IDS["magmaw"]}"' in text

def test_live_report_builder_keeps_all_seven_bwd_route_partitions_distinct(tmp_path: Path):
    manifests = _manifests()
    bwd_ids = [CANONICAL_ID, *DIAGNOSTIC_IDS.values()]
    scenario_dir = tmp_path / "validation_scenarios"
    scenario_dir.mkdir()
    scenarios = [row for row in manifests["validation_scenarios"] if row["scenario_id"] in bwd_ids]
    routes = [row for row in manifests["validation_routes"] if row["scenario_id"] in bwd_ids]
    (scenario_dir / "validation_scenarios.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in scenarios),
        encoding="utf-8",
    )
    (scenario_dir / "validation_routes.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in routes),
        encoding="utf-8",
    )
    (scenario_dir / "validation_mechanics.jsonl").write_text("", encoding="utf-8")

    # A context-free report is intentionally reused as a smoke input for every
    # selected scenario; the builder must still derive each route partition
    # from its own scenario ID and never merge the seven contracts.
    reports = build_reports(
        {
            "schema": "bot_live_validation_report_v1",
            "validation_context": {},
            "trace": {},
            "evidence": {},
            "stages": [],
        },
        scenario_dir,
    )
    assert set(reports) == set(bwd_ids)
    assert reports[CANONICAL_ID]["expected_bosses"] == 6
    assert reports[CANONICAL_ID]["diagnostic_only"] is False
    for scenario_id in DIAGNOSTIC_IDS.values():
        report = reports[scenario_id]
        assert report["diagnostic_only"] is True
        assert report["runtime_profile_id"] == scenario_id
        assert report["diagnostic_parent_scenario_id"] == CANONICAL_ID
        assert report["certifies_predecessors"] is False
        assert report["expected_bosses"] == 1
        assert all(
            str(row["route_node_id"]) in {str(route["route_node_id"]) for route in routes if route["scenario_id"] == scenario_id}
            for row in report["expected_route_evidence"]
        )
