"""Round 2 package M: canonical-composition c0 cohorts get scenario rows and runtime profiles.

The legacy scenarios, diagnostic shards and runtime profiles stay byte-identical
(pinned below); every raid_shard_plan_v1 cohort has a validated row cloned from
its boss's route template and a profile equal to the plan's runtime_profile.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from tools.bot_ml.build_validation_scenario_manifests import build_manifests
from tools.raid_program import raid_shard_scenarios as rows
from tools.raid_program.raid_shard_plan import PREREQUISITES_DIR

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
PROFILES = ROOT / "dataset/bot_runtime_profiles/profiles.json"
FIXTURE = ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
BOSSES = ("magmaw", "omnotron", "chimaeron", "atramedes", "maloriak", "nefarian")
C0 = [f"blackwing_descent_10n_{boss}_c0_diagnostic" for boss in BOSSES]
FULL = "blackwing_descent_10n_full_c0"
COHORTS = C0 + [FULL]
LEGACY_SCENARIO_COUNT = 3
# sha256 of json.dumps(rows, sort_keys=True) at 1aedfb4f6c, before package M. The accepted
# Magmaw shard and the Stonecore rows are pinned byte-identical; the other legacy BWD rows
# change only through boss agents' patch requests (e.g. package AT's Atramedes regroup).
ACCEPTED_MAGMAW_SHA256 = "8db274e2c374cf93eb1d35cc9471e2e3347e3c261626700e0fb15f47ea07d1c9"
STONECORE_SHA256 = "90f7e64c0157881b3e9cfcbaa372e4659c4dee7dac454092b456186d24264a57"
LEGACY_PROFILES_SHA256 = "194fcfc0622b7beed14513ac4f55609ab1a1bf6b2b3e61734b4ad0627199046b"
LEGACY_IDS = ["stonecore_5n", "stonecore_5h", "blackwing_descent_10n"] + [
    f"blackwing_descent_10n_{boss}_diagnostic"
    for boss in ("magmaw", "omnotron", "maloriak", "atramedes", "chimaeron", "nefarian")]
LEGACY_DIAGNOSTIC_COUNT = 6
LEGACY_PROFILE_COUNT = 12

pytestmark = pytest.mark.skipif(not (PREREQUISITES_DIR / "blackwing_descent.json").is_file(),
                                reason="package-A prerequisite file absent")


def _sha(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def plan() -> dict:
    return rows.build_plan(COMPOSITION)


def test_accepted_rows_and_legacy_profiles_are_byte_identical():
    config, profiles = _read(CONFIG), _read(PROFILES)
    scenarios = rows.configured_scenarios(config)
    assert _sha(scenarios["blackwing_descent_10n_magmaw_diagnostic"]) == ACCEPTED_MAGMAW_SHA256
    assert _sha([scenarios["stonecore_5n"], scenarios["stonecore_5h"]]) == STONECORE_SHA256
    assert [row["id"] for row in config["scenarios"][:LEGACY_SCENARIO_COUNT]
            + config["diagnostic_scenarios"][:LEGACY_DIAGNOSTIC_COUNT]] == LEGACY_IDS
    assert _sha(profiles["profiles"][:LEGACY_PROFILE_COUNT]) == LEGACY_PROFILES_SHA256
    assert [row["id"] for row in config["scenarios"][LEGACY_SCENARIO_COUNT:]] == [FULL]
    assert [row["id"] for row in config["diagnostic_scenarios"][LEGACY_DIAGNOSTIC_COUNT:]] == C0
    assert [row["name"] for row in profiles["profiles"][LEGACY_PROFILE_COUNT:]] == COHORTS


def test_every_c0_cohort_has_a_validated_row_and_profile(plan):
    assert [shard["scenario_id"] for shard in plan["shards"]] == COHORTS
    report = rows.validate_raid_shard_scenarios(plan, _read(CONFIG), _read(PROFILES), _read(FIXTURE))
    assert report["all_passed"], report["failures"]
    assert report["checked"] == COHORTS and report["missing"] == []
    profiles = {row["name"]: row for row in _read(PROFILES)["profiles"]}
    for shard in plan["shards"]:
        assert profiles[shard["scenario_id"]] == shard["runtime_profile"]
        assert profiles[shard["scenario_id"]]["pool_tag_filter"] == shard["pool_tag"]


def test_rows_clone_the_route_template_and_keep_node_ids(plan):
    config = _read(CONFIG)
    scenarios = rows.configured_scenarios(config)
    slot_fields = {*rows.STEP_SLOT_FIELDS, *rows.STEP_SLOT_LIST_FIELDS, *rows.STEP_SLOT_ANCHOR_FIELDS}
    for shard in plan["shards"]:
        row, template = scenarios[shard["scenario_id"]], scenarios[shard["route_template_scenario_id"]]
        assert row["route_template_scenario_id"] == template["id"]
        assert [step["node_id"] for step in row["route"]] == [step["node_id"] for step in template["route"]]
        assert row["mechanic_profiles"] == template["mechanic_profiles"]
        for step, source in zip(row["route"], template["route"]):
            changed = {key for key in set(step) | set(source) if step.get(key) != source.get(key)}
            if "mechanic_contract" in changed:
                contract, before = step["mechanic_contract"], source["mechanic_contract"]
                assert {key for key in set(contract) | set(before) if contract.get(key) != before.get(key)} <= set(
                    rows.CONTRACT_SLOT_FIELDS)
                changed.discard("mechanic_contract")
            assert changed <= slot_fields, (row["id"], step["node_id"], changed)
            if shard["shard_kind"] == "boss":
                assert changed <= {"patrol_pull_owner_roster_slot"}
        assert row["required_roles"] == shard["role_counts"]
        if shard["shard_kind"] == "full_raid":
            assert "prerequisite_contract" not in row and "roster_identity" not in row and "diagnostic_only" not in row
            continue
        assert row["prerequisite_contract"]["precompleted_boss_entries"] == shard["lockout"]["precompleted_creature_entries"]
        assert row["prerequisite_contract"]["certifies_predecessors"] is False
    maloriak = scenarios["blackwing_descent_10n_maloriak_c0_diagnostic"]["prerequisite_contract"]
    assert maloriak["precompleted_boss_entries"] == [41570, 42186]  # the controller, not Arcanotron 42166
    assert maloriak["state_source"] == "raid_shard_lockout_seed:raid_prerequisites_v1"


def test_magmaw_patrol_pull_owner_moves_to_the_canonical_hunter(plan):
    magmaw = next(shard for shard in plan["shards"] if shard["boss_key"] == "magmaw")
    row = rows.configured_scenarios(_read(CONFIG))[magmaw["scenario_id"]]
    chainwielder = next(step for step in row["route"] if step["node_id"] == "bwd.magmaw.chainwielder")
    slot = chainwielder["patrol_pull_owner_roster_slot"]
    assert magmaw["bots"][slot - 1]["class_spec"] == "beast_mastery_hunter" and slot == 5
    legacy = next(shard for shard in _read(FIXTURE)["shards"] if shard["scenario_id"] == magmaw["route_template_scenario_id"])
    assert legacy["bots"][9 - 1]["class_spec"] == "survival_hunter"  # the template's owner slot 9


def _legacy_config() -> dict:
    config = _read(CONFIG)
    config["scenarios"] = config["scenarios"][:LEGACY_SCENARIO_COUNT]
    config["diagnostic_scenarios"] = config["diagnostic_scenarios"][:LEGACY_DIAGNOSTIC_COUNT]
    return config


def _legacy_config_text() -> str:
    """The tracked config as it was before package M: cut the appended rows out of the text."""
    text = CONFIG.read_text(encoding="utf-8")
    full = text.index(',\n    {\n      "id": "blackwing_descent_10n_full_c0"')
    text = text[:full] + text[text.index('\n  ],\n  "diagnostic_scenarios"', full):]
    text = text[:text.index(',\n    {\n      "id": "blackwing_descent_10n_magmaw_c0_diagnostic"')] + "\n  ]\n}\n"
    assert json.loads(text) == _legacy_config()
    return text


def test_builder_adds_cohort_rows_without_touching_legacy_rows(plan):
    """Adding the cohort rows and the plan leaves every legacy manifest row identical."""
    config, legacy_config = _read(CONFIG), _legacy_config()
    report = {"scenarios": [{"scenario_id": value, "missing": [], "role_counts": {"tank": 2, "healer": 3, "dps": 5}}
                            for value in rows.configured_scenarios(legacy_config)]}
    fixture = _read(FIXTURE)
    before = build_manifests(legacy_config, report, {"all_passed": True}, fixture)
    readiness = {"provisioning_readiness": {"scenarios": [
        {"scenario_id": shard["scenario_id"], "missing": [], "role_counts": shard["role_counts"]}
        for shard in plan["shards"]]}}
    after = build_manifests(config, report, {"all_passed": True}, fixture, [plan], [readiness])
    for name in ("validation_scenarios", "validation_routes", "validation_mechanics"):
        kept = [row for row in after[name] if row["scenario_id"] not in COHORTS]
        assert kept == before[name], name
    added = {row["scenario_id"]: row for row in after["validation_scenarios"] if row["scenario_id"] in COHORTS}
    assert sorted(added) == sorted(COHORTS)
    for shard in plan["shards"]:
        row = added[shard["scenario_id"]]
        assert [actor["guid"] for actor in row["roster_identity"]] == [bot["character_guid"] for bot in shard["bots"]]
        assert row["runtime_profile_id"] == shard["runtime_profile_id"]
        assert row["diagnostic_only"] is (shard["shard_kind"] == "boss")
        assert "provisioning_scenario_report" not in row["missing"]
        assert not {"diagnostic_roster_identity", "raid_shard_roster_identity"} & set(row["missing"])
    assert added[FULL]["certifies_predecessors"] is None and added[FULL]["prerequisite_contract"] == {}
    routes = [row for row in after["validation_routes"] if row["scenario_id"] in COHORTS]
    assert all(row["runtime_profile_id"] == row["scenario_id"] for row in routes)
    full_routes = [row for row in routes if row["scenario_id"] == FULL]
    assert len(full_routes) == len(rows.configured_scenarios(config)["blackwing_descent_10n"]["route"])
    assert after["report"]["raid_shard_plan_scenarios_without_config_rows"] == []
    with pytest.raises(ValueError, match="raid_shard_provisioning_scenario_collision"):
        build_manifests(config, report, {}, fixture, [plan], [{"provisioning_readiness": report}])
    declared = copy.deepcopy(config)
    rows.configured_scenarios(declared)[FULL]["roster_identity"] = [{"guid": 1}]
    with pytest.raises(ValueError, match="raid_shard_scenario_declares_roster_identity"):
        build_manifests(declared, report, {}, fixture, [plan], [readiness])


def test_full_raid_route_remaps_every_roster_slot_onto_the_canonical_roster(plan):
    full = next(shard for shard in plan["shards"] if shard["shard_kind"] == "full_raid")
    scenarios = rows.configured_scenarios(_read(CONFIG))
    template, row = scenarios["blackwing_descent_10n"], scenarios[FULL]
    legacy = template["roster_identity"]
    mapping = rows.slot_mapping(rows.legacy_rosters(_read(FIXTURE), _read(CONFIG))["blackwing_descent_10n"], full["bots"])
    assert sorted(mapping) == sorted(mapping.values()) == list(range(1, 11))  # one-to-one
    for legacy_slot, slot in mapping.items():
        assert legacy[legacy_slot - 1]["role"] == full["bots"][slot - 1]["role"]
    drudges = next(step for step in row["route"] if step["node_id"] == "bwd.magmaw.drudges")
    specs = lambda slots: [full["bots"][slot - 1]["class_spec"] for slot in slots]
    assert set(specs(drudges["split_lane_tank_slots"])) == {"blood_death_knight", "feral_druid_tank"}
    assert set(specs(drudges["split_healer_roster_slots"])) == {"holy_paladin", "discipline_priest", "restoration_shaman"}
    assert specs(drudges["split_seed_roster_slots"]) == ["demonology_warlock", "fire_mage"]  # ranged seeds stay ranged
    assert sorted(drudges["split_lane_a_roster_slots"] + drudges["split_lane_b_roster_slots"]) == list(range(1, 11))
    magmaw = next(step for step in row["route"] if step["node_id"] == "bwd.magmaw.encounter")["mechanic_contract"]
    assert specs([magmaw["main_tank_roster_slot"]]) == ["blood_death_knight"]
    assert specs([magmaw["off_tank_roster_slot"]]) == ["feral_druid_tank"]
    chainwielder = next(step for step in row["route"] if step["node_id"] == "bwd.magmaw.chainwielder")
    assert specs([chainwielder["patrol_pull_owner_roster_slot"]]) == ["beast_mastery_hunter"]


@pytest.mark.parametrize("mutate,check", [
    (lambda row: row.update(runtime_profile_id="blackwing_descent_10n_magmaw_diagnostic"), "scenario_identity"),
    (lambda row: row["required_roles"].update(healer=3), "scenario_identity"),
    (lambda row: row["prerequisite_contract"].update(certifies_predecessors=True), "scenario_identity"),
    (lambda row: row["route"].pop(), "route_template_boss_node_missing"),
    (lambda row: row["route"][1].update(patrol_pull_owner_roster_slot=11), "roster_slot_out_of_range"),
    (lambda row: row["route"][1].update(patrol_pull_owner_roster_slot=6), "roster_slot_class_changed"),
    (lambda row: row["route"][2].update(node_id="bwd.magmaw.chainwielder"), "route_node_ids_missing_or_duplicated"),
])
def test_row_identity_drift_fails_closed(plan, mutate, check):
    config = _read(CONFIG)
    mutate(rows.configured_scenarios(config)["blackwing_descent_10n_magmaw_c0_diagnostic"])
    report = rows.validate_raid_shard_scenarios(plan, config, _read(PROFILES), _read(FIXTURE))
    assert check in {row["check"] for row in report["failures"]}


@pytest.mark.parametrize("cohort", [*C0, FULL])
def test_a_moved_start_is_checked_against_the_template_not_itself(plan, cohort):
    """The plan copies a row's start from the row itself, so the reference is the route template (minor 8)."""
    shard = next(row for row in plan["shards"] if row["scenario_id"] == cohort)
    assert shard["start_position_source"] == cohort  # the self-copy that made the old check vacuous
    config = _read(CONFIG)
    scenarios = rows.configured_scenarios(config)
    row = scenarios[cohort]
    assert row["start_position"] == scenarios[shard["route_template_scenario_id"]]["start_position"]
    row["start_position"] = {**row["start_position"], "x": row["start_position"]["x"] + 25.0}
    moved = {**shard, "start_position": row["start_position"]}  # a plan regenerated from the moved row
    report = rows.validate_raid_shard_scenarios({**plan, "shards": [moved]}, config, require_all=False)
    (failure,) = [failure for failure in report["failures"] if failure["check"] == "scenario_start_position"]
    assert failure["source"] == shard["route_template_scenario_id"]
    # An explicit source must exist and carry the same start.
    row["start_position_source"] = "blackwing_descent_10n_absent"
    report = rows.validate_raid_shard_scenarios({**plan, "shards": [moved]}, config, require_all=False)
    assert "scenario_start_position_source_missing" in {failure["check"] for failure in report["failures"]}
    row["start_position_source"] = cohort
    report = rows.validate_raid_shard_scenarios({**plan, "shards": [moved]}, config, require_all=False)
    assert "scenario_start_position_source_missing" in {failure["check"] for failure in report["failures"]}


def test_a_plan_start_from_the_template_is_compared_directly(plan):
    shard = next(row for row in plan["shards"] if row["cohort_id"] == "blackwing_descent_10n_magmaw_c0")
    template = shard["route_template_scenario_id"]
    config = _read(CONFIG)
    row = rows.configured_scenarios(config)[shard["scenario_id"]]
    planned = {**shard, "start_position_source": template, "start_position": {**row["start_position"], "z": 1.0}}
    report = rows.validate_raid_shard_scenarios({**plan, "shards": [planned]}, config, require_all=False)
    assert {"check": "scenario_start_position", "source": template}.items() <= next(
        failure for failure in report["failures"] if failure["check"] == "scenario_start_position").items()


@pytest.mark.parametrize("mutate", [
    lambda row: row.update(diagnostic_only=True),
    lambda row: row.update(roster_identity=[]),
    lambda row: row.update(prerequisite_contract={"certifies_predecessors": False}),
])
def test_full_raid_row_stays_non_diagnostic(plan, mutate):
    config = _read(CONFIG)
    mutate(rows.configured_scenarios(config)[FULL])
    report = rows.validate_raid_shard_scenarios(plan, config, _read(PROFILES), _read(FIXTURE))
    assert "scenario_identity" in {row["check"] for row in report["failures"]}


def test_missing_rows_and_profile_drift_are_reported(plan):
    config = _read(CONFIG)
    config["diagnostic_scenarios"] = config["diagnostic_scenarios"][:LEGACY_DIAGNOSTIC_COUNT + 1]
    profiles = _read(PROFILES)
    profiles["profiles"][LEGACY_PROFILE_COUNT]["target_population"] = 9
    report = rows.validate_raid_shard_scenarios(plan, config, profiles, _read(FIXTURE))
    assert report["missing"] == C0[1:]
    assert {row["check"] for row in report["failures"]} == {"raid_shard_scenario_rows_missing", "runtime_profile_row"}
    assert rows.validate_raid_shard_scenarios(plan, config, None, _read(FIXTURE), require_all=False)["all_passed"]


def test_unmappable_roster_slots_are_refused(plan):
    template = copy.deepcopy(rows.configured_scenarios(_read(CONFIG))["blackwing_descent_10n_magmaw_diagnostic"])
    roster = copy.deepcopy(next(shard["bots"] for shard in _read(FIXTURE)["shards"]
                                if shard["scenario_id"] == template["id"]))
    # A second tank where the canonical Magmaw shard has only the Blood DK left: no slot of that role remains.
    roster[8].update(class_spec="protection_warrior", **{"class": 1, "role": "tank"})
    with pytest.raises(rows.RaidShardScenarioError, match="roster_slot_unmappable"):
        rows.clone_scenario(template, plan["shards"][0], roster, plan["composition_id"])


def test_write_missing_appends_only_and_is_idempotent(tmp_path, plan):
    """Fresh clones are appended after the legacy rows; committed cohort rows are never rewritten.

    A committed row may diverge from a fresh clone once a boss agent's patch lands, so
    the clone is compared semantically only where no patch touched it (identity checks
    always), and the tracked file itself must be a fixed point of --write-missing.
    """
    config_path, profiles_path = tmp_path / "config.json", tmp_path / "profiles.json"
    legacy_text = _legacy_config_text()
    config_path.write_text(legacy_text, encoding="utf-8")
    profiles_text = PROFILES.read_text(encoding="utf-8")
    first_cohort = profiles_text.index(',\n    {\n      "name": "blackwing_descent_10n_magmaw_c0_diagnostic"')
    profiles_path.write_text(profiles_text[:first_cohort] + "\n  ]\n}\n", encoding="utf-8")
    assert len(_read(profiles_path)["profiles"]) == LEGACY_PROFILE_COUNT
    argv = ["--plan", str(tmp_path / "plan.json"), "--scenario-config", str(config_path),
            "--runtime-profiles", str(profiles_path), "--legacy-fixture", str(FIXTURE)]
    (tmp_path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    assert rows.main(argv + ["--check"]) == 1
    assert rows.main(argv + ["--write-missing"]) == 0
    written = config_path.read_text(encoding="utf-8")
    fresh, tracked = rows.configured_scenarios(json.loads(written)), rows.configured_scenarios(_read(CONFIG))
    assert list(fresh) == list(tracked)
    assert {name: row for name, row in fresh.items() if name not in COHORTS} == {
        name: row for name, row in tracked.items() if name not in COHORTS}
    for cohort in COHORTS:
        assert [step["node_id"] for step in fresh[cohort]["route"]] == [step["node_id"] for step in tracked[cohort]["route"]]
        # Route rows and the free-text description may carry a boss fix (round 3: the Nefarian
        # c0 description names the central-hall trash it clears); every identity field is equal.
        assert {key: value for key, value in fresh[cohort].items() if key not in ("route", "description")} == {
            key: value for key, value in tracked[cohort].items() if key not in ("route", "description")}
    assert profiles_path.read_text(encoding="utf-8") == PROFILES.read_text(encoding="utf-8")
    assert rows.main(argv + ["--check"]) == 0
    # The tracked files are a fixed point: nothing is left to add and nothing is rewritten.
    config_path.write_text(CONFIG.read_text(encoding="utf-8"), encoding="utf-8")
    assert rows.main(argv + ["--write-missing"]) == 0
    assert config_path.read_text(encoding="utf-8") == CONFIG.read_text(encoding="utf-8")
    assert profiles_path.read_text(encoding="utf-8") == PROFILES.read_text(encoding="utf-8")


def test_append_keeps_every_other_byte_and_refuses_unknown_layouts():
    text = json.dumps({"schema": "x", "rows": [{"a": 1}], "profiles": [{"b": 2}]}, indent=2) + "\n"
    appended = rows.append_to_array(text, ['    {"c": 3}'], "rows")
    assert json.loads(appended)["rows"] == [{"a": 1}, {"c": 3}]
    assert appended.replace(',\n    {"c": 3}', "") == text
    assert rows.append_to_array(text, [], "rows") == text
    with pytest.raises(rows.RaidShardScenarioError, match="array_missing_or_empty"):
        rows.append_to_array(text, ['    {"c": 3}'], "schema")
    with pytest.raises(rows.RaidShardScenarioError, match="unexpected_array_layout"):
        rows.append_to_array(json.dumps({"rows": [1], "x": 2}) + "\n", ["3"], "rows")
