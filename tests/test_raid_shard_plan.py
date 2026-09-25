from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.raid_program import raid_shard_identity as ids
from tools.raid_program.raid_composition import COMPOSITION_DIR, read_json
from tools.raid_program.raid_shard_plan import (
    PREREQUISITES_DIR,
    ShardPlanError,
    build_shard_plan,
    load_plan_inputs,
    precompleted_closure,
    validate_prerequisites,
    validate_shard_plan,
)

ROOT = Path(__file__).resolve().parents[1]
BWD = COMPOSITION_DIR / "blackwing_descent_10n.json"
LEGACY_FIXTURE = ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"
START = {"map_id": 669, "x": -345.872, "y": -224.344, "z": 193.127, "o": 0.0}


def bwd_prerequisites(omnotron_key: str = "omnotron") -> dict:
    """Schema-conformant BWD graph from the round-1 audit (native script indices)."""
    lower = ["magmaw", omnotron_key]
    rows = [
        ("magmaw", 0, 41570, []),
        (omnotron_key, 1, 42186, []),
        ("chimaeron", 2, 43296, lower),
        ("atramedes", 3, 41442, lower),
        ("maloriak", 4, 41378, lower),
        ("nefarian", 5, 41376, ["chimaeron", "atramedes", "maloriak"]),
    ]
    return {
        "schema": "raid_prerequisites_v1", "raid": "blackwing_descent", "map_id": 669,
        "difficulties": ["10N", "10H", "25N", "25H"], "script_header": "BWD",
        "bosses": [{"key": key, "boss_index": index, "creature_entry": entry, "credit_entry": entry,
                    "dungeon_encounter_bit": index, "predecessors": list(pre), "extra_save_values": {}}
                   for key, index, entry, pre in rows],
        "save_extras": [],
    }


def _starts() -> dict:
    return {f"blackwing_descent_10n_{boss}_diagnostic": dict(START)
            for boss in ("magmaw", "omnotron", "chimaeron", "atramedes", "maloriak", "nefarian")}


def _plan(copies: int = 1, prerequisites: dict | None = None, composition: dict | None = None) -> dict:
    return build_shard_plan(composition or read_json(BWD), prerequisites or bwd_prerequisites(),
                            copies=copies, starts=_starts(), provisioning_defaults={"default_consumables": []})


def test_plan_covers_every_boss_with_contract_named_isolated_cohorts():
    plan = _plan()
    assert plan["shard_count"] == 6 and plan["bot_count"] == 60
    assert [shard["cohort_id"] for shard in plan["shards"]] == [
        f"blackwing_descent_10n_{boss}_c0"
        for boss in ("magmaw", "omnotron", "chimaeron", "atramedes", "maloriak", "nefarian")]
    for shard in plan["shards"]:
        tag = shard["cohort_id"] + "_diagnostic"
        assert shard["scenario_id"] == shard["pool_tag"] == shard["runtime_profile_id"] == tag
        assert shard["runtime_profile"]["pool_tag_filter"] == tag
        assert shard["runtime_profile"]["validation_route"]["scenario_id"] == tag
        assert {bot["pool_tag"] for bot in shard["bots"]} == {tag}
        assert shard["diagnostic_only"] is True
        assert shard["lockout"]["certifies_predecessors"] is False
        assert shard["lockout"]["diagnostic_only_assistance"] is True
        assert shard["live_identity_requirements"]["fixture_values"] is None


def test_precompleted_bosses_are_the_transitive_prerequisite_closure():
    plan = _plan()
    closure = {shard["boss_key"]: shard["lockout"]["precompleted_boss_keys"] for shard in plan["shards"]}
    assert closure == {
        "magmaw": [], "omnotron": [],
        "chimaeron": ["magmaw", "omnotron"], "atramedes": ["magmaw", "omnotron"],
        "maloriak": ["magmaw", "omnotron"],
        "nefarian": ["magmaw", "omnotron", "chimaeron", "atramedes", "maloriak"],
    }
    nefarian = next(shard for shard in plan["shards"] if shard["boss_key"] == "nefarian")
    assert nefarian["lockout"]["precompleted_boss_indices"] == [0, 1, 2, 3, 4]
    assert nefarian["lockout"]["precompleted_creature_entries"] == [41570, 42186, 43296, 41442, 41378]
    assert nefarian["lockout"]["seed_boss_argument"] == "magmaw,omnotron,chimaeron,atramedes,maloriak"
    magmaw = plan["shards"][0]
    assert magmaw["lockout"]["seed_boss_argument"] == "none"


def test_copies_are_identical_characters_with_disjoint_identities():
    plan = _plan(copies=3)
    assert plan["shard_count"] == 18 and plan["bot_count"] == 180
    by_character: dict[tuple[str, str], list[dict]] = {}
    for shard in plan["shards"]:
        for bot in shard["bots"]:
            by_character.setdefault((shard["boss_key"], bot["character_key"]), []).append(bot)
    for copies in by_character.values():
        assert len(copies) == 3
        shape = [{k: v for k, v in bot.items() if k not in {
            "name", "account", "account_id", "expected_account_id", "character_guid", "expected_character_guid",
            "roster_slot_id", "pool_tag", "runtime_profile_id", "evidence_namespace", "expected_pet_id", "pet", "loadout"}}
                 for bot in copies]
        assert all(row == shape[0] for row in shape)
        groups = [bot["loadout"]["groups"] for bot in copies]
        assert all(group == groups[0] for group in groups)
    everyone = [bot for shard in plan["shards"] for bot in shard["bots"]]
    for field in ("character_guid", "account_id", "account", "name"):
        assert len({bot[field] for bot in everyone}) == 180
    assert len({bot["loadout"]["item_guid_base"] for bot in everyone}) == 180
    legacy = json.loads(LEGACY_FIXTURE.read_text(encoding="utf-8"))
    legacy_bots = [bot for shard in legacy["shards"] for bot in shard["bots"]]
    for field in ("character_guid", "account_id", "account", "name"):
        assert not {bot[field] for bot in everyone} & {bot[field] for bot in legacy_bots}
    assert all(bot["character_guid"] > 30510 for bot in everyone)


def test_character_slots_and_specs_are_stable_across_bosses():
    plan = _plan()
    for shard in plan["shards"]:
        druid = next(bot for bot in shard["bots"] if bot["character_key"] == "druid")
        assert druid["character_guid"] % 100 == 2
        assert [group["class_spec"] for group in druid["loadout"]["groups"]] == ["balance_druid", "feral_druid_tank"]
        dk = next(bot for bot in shard["bots"] if bot["character_key"] == "death_knight")
        groups = dk["loadout"]["groups"]
        assert groups[1]["mirrors_talent_group"] == 0
        assert groups[0]["talents"] == groups[1]["talents"] and groups[0]["glyphs"] == groups[1]["glyphs"]
        assert [bot["role"] for bot in shard["bots"]] == sorted(
            (bot["role"] for bot in shard["bots"]), key=["tank", "healer", "dps"].index)


def test_pool_class_spec_and_active_group_follow_the_boss_selection():
    plan = _plan()
    selected = {}
    for shard in plan["shards"]:
        druid = next(bot for bot in shard["bots"] if bot["character_key"] == "druid")
        shaman = next(bot for bot in shard["bots"] if bot["character_key"] == "shaman")
        selected[shard["boss_key"]] = (druid["class_spec"], druid["loadout"]["active_talent_group"], druid["role"],
                                       shaman["class_spec"], shaman["loadout"]["active_talent_group"], shaman["role"])
        for bot in (druid, shaman):
            active = bot["loadout"]["groups"][bot["loadout"]["active_talent_group"]]
            assert active["class_spec"] == bot["class_spec"] == bot["action_profile_id"]
            assert active["talents"] == bot["talents"] and active["glyphs"] == bot["glyphs"]
            assert active["gear_profile_id"] == bot["gear_profile_id"] == bot["canonical_setup"]["gear_profile_id"]
    assert selected["magmaw"] == ("balance_druid", 0, "dps", "elemental_shaman", 0, "dps")
    assert selected["omnotron"] == ("feral_druid_tank", 1, "tank", "elemental_shaman", 0, "dps")
    assert selected["chimaeron"] == ("feral_druid_tank", 1, "tank", "restoration_shaman", 1, "healer")


def test_prerequisite_key_aliases_bind_and_name_the_cohort():
    plan = _plan(prerequisites=bwd_prerequisites("omnotron_defense_system"))
    omnotron = plan["shards"][1]
    assert omnotron["cohort_id"] == "blackwing_descent_10n_omnotron_defense_system_c0"
    assert omnotron["composition_boss_key"] == "omnotron"
    maloriak = next(shard for shard in plan["shards"] if shard["boss_key"] == "maloriak")
    assert maloriak["lockout"]["precompleted_boss_keys"] == ["magmaw", "omnotron_defense_system"]


@pytest.mark.parametrize("mutate,check", [
    (lambda p: p["bosses"][0]["predecessors"].append("nefarian"), "prerequisite_cycle"),
    (lambda p: p["bosses"][1]["predecessors"].append("onyxia"), "prerequisite_unknown_predecessor"),
    (lambda p: p.update(map_id=671), "prerequisite_map_id"),
    (lambda p: p.update(difficulties=["25H"]), "prerequisite_difficulty"),
    (lambda p: p.update(schema="other"), "prerequisite_schema"),
    (lambda p: p["bosses"][2].update(boss_index=1), "prerequisite_boss_identity_not_unique"),
])
def test_invalid_prerequisite_graphs_fail_closed(mutate, check):
    prerequisites = bwd_prerequisites()
    mutate(prerequisites)
    with pytest.raises(ShardPlanError) as error:
        validate_prerequisites(prerequisites, "blackwing_descent", "10N", 669)
    assert check in str(error.value)


def test_native_boss_index_must_match_the_identity_boss_number():
    prerequisites = bwd_prerequisites()
    prerequisites["bosses"][2]["boss_index"], prerequisites["bosses"][3]["boss_index"] = 3, 2
    with pytest.raises(ShardPlanError, match="composition_boss_number_differs_from_native_index"):
        _plan(prerequisites=prerequisites)


def test_closure_rejects_unknown_boss():
    with pytest.raises(ShardPlanError, match="unknown_prerequisite_boss"):
        precompleted_closure({}, "magmaw")


@pytest.mark.parametrize("mutate,check", [
    (lambda p: p["shards"][1]["bots"][0].update(name=p["shards"][0]["bots"][0]["name"]), "duplicate_name"),
    (lambda p: p["shards"][1]["bots"][0].update(character_guid=30001, expected_character_guid=30001), "legacy_identity_overlap"),
    (lambda p: p["shards"][0]["lockout"].update(certifies_predecessors=True), "lockout_contract"),
    (lambda p: p["shards"][0].update(pool_tag="blackwing_descent_10n_magmaw_diagnostic"), "shard_pool_binding"),
    (lambda p: p["shards"][0]["bots"][0].update(name="Bwmgwnaaa"), "character_name"),
    (lambda p: p["shards"][0]["bots"].pop(), "shard_bot_count"),
    (lambda p: p["shards"][0]["bots"][0]["loadout"].update(active_talent_group=1), "loadout_active_group"),
])
def test_plan_validation_rejects_identity_and_contract_drift(mutate, check):
    plan = copy.deepcopy(_plan())
    mutate(plan)
    with pytest.raises(ShardPlanError) as error:
        validate_shard_plan(plan)
    assert check in str(error.value)


def test_start_positions_come_from_the_route_template_until_a_cohort_route_exists():
    plan = _plan()
    assert all(shard["start_position"] == START for shard in plan["shards"])
    assert plan["shards"][0]["start_position_source"] == "blackwing_descent_10n_magmaw_diagnostic"
    plan = build_shard_plan(read_json(BWD), bwd_prerequisites(), starts={})
    assert all(shard["start_position"] is None for shard in plan["shards"])


@pytest.mark.skipif(not (PREREQUISITES_DIR / "blackwing_descent.json").is_file(),
                    reason="package-A prerequisite file not merged yet")
def test_real_package_a_prerequisites_build_the_bwd_plan():
    composition, prerequisites, defaults, starts, sources = load_plan_inputs(BWD)
    plan = build_shard_plan(composition, prerequisites, starts=starts, provisioning_defaults=defaults, sources=sources)
    closure = {shard["composition_boss_key"]: set(shard["lockout"]["precompleted_boss_keys"]) for shard in plan["shards"]}
    lower = {shard["boss_key"] for shard in plan["shards"] if shard["composition_boss_key"] in ("magmaw", "omnotron")}
    for boss in ("maloriak", "atramedes", "chimaeron"):
        assert closure[boss] == lower
    assert len(closure["nefarian"]) == 5
    assert closure["magmaw"] == set()
    assert all(bot["character_guid"] > ids.CHARACTER_GUID_BASE for shard in plan["shards"] for bot in shard["bots"])
