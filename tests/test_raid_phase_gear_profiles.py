"""Content-phase gear profiles (tools.bot_ml.phase_gear_*; DVC stage raid_phase_gear).

BWD 10N is bound to Tier 11: every canonical member wears ``cata_t11/<spec>``.
The shared validation gear profiles (Stonecore, Phase-8 calibration, legacy
Magmaw) stay exactly what dvc.lock pins.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from tools.bot_ml.build_validation_gear_profiles import armor_allowed, class_allowed
from tools.bot_ml.phase_gear_profiles import (
    PhaseGearError,
    composition_gear_phase,
    is_phase_profile_id,
    load_phase_config,
    merge_phase_gear_profiles,
    phase_gear_profiles_path,
    phase_profile_id,
)
from tools.bot_ml.phase_gear_sources import PhaseSourceError, resolve_loot_rows, vendor_cost_admitted

ROOT = Path(__file__).resolve().parents[1]
BWD = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
T11 = ROOT / "experiments/configs/raid_gear_phases/cata_t11_v1.json"
SHARED = ROOT / "dataset/validation_gear_profiles"
DBC = ROOT / "data/dbc/enUS"
PHASE_MODULES = ("phase_gear_profiles.py", "phase_gear_sources.py", "phase_gear_extract.py", "phase_gear_oracles.py",
                 "phase_gear_selection.py", "phase_gear_spell_requirements.py", "phase_gear_validation.py",
                 "phase_gear_equip_restrictions.py", "phase_gear_item_effects.py",
                 "build_phase_gear_profiles.py")


def _payload() -> dict:
    path = phase_gear_profiles_path()
    if not path.is_file():
        pytest.skip(f"raid_phase_gear output not reproduced here ({path}); dvc repro raid_phase_gear")
    return json.loads(path.read_text(encoding="utf-8"))


def _bwd_specs() -> list[str]:
    composition = json.loads(BWD.read_text(encoding="utf-8"))
    return sorted({spec for character in composition["characters"] for spec in character["specs"]})


def _catalog() -> dict:
    catalog = json.loads((ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json").read_text(encoding="utf-8"))
    return {row["spec_target_id"]: row for row in catalog["targets"]}


# --- binding --------------------------------------------------------------------------------------

def test_bwd_is_bound_to_tier_11_and_the_phase_caps_normal_t11():
    phase = composition_gear_phase(json.loads(BWD.read_text(encoding="utf-8")))
    assert phase["phase_id"] == "cata_t11"
    config = phase["phase_config"]
    assert config["item_policy"]["max_item_level"] == 359 and config["target_average_item_level"] == 359
    assert config["gem_policy"]["max_quality"] == 3, "epic (4.3) gems are out of phase"
    assert {row["map_id"] for row in config["sources"]["loot_maps"]} >= {669, 671, 754, 757}
    assert set(_bwd_specs()) <= set(config["tier_sets_by_spec"])


def test_a_composition_whose_phase_config_names_another_phase_is_refused(tmp_path):
    other = json.loads(T11.read_text(encoding="utf-8"))
    other["phase_id"] = other["profile_namespace"] = "cata_t12"
    (tmp_path / "t12.json").write_text(json.dumps(other))
    with pytest.raises(PhaseGearError, match="composition_gear_phase_mismatch"):
        composition_gear_phase({"composition_id": "x", "gear_phase": {"phase_id": "cata_t11", "config": str(tmp_path / "t12.json")}})
    assert composition_gear_phase({"composition_id": "legacy"}) is None, "no gear_phase: catalog profiles"


def test_an_unbounded_phase_config_is_refused(tmp_path):
    config = json.loads(T11.read_text(encoding="utf-8"))
    del config["item_policy"]["max_item_level"]
    (tmp_path / "bad.json").write_text(json.dumps(config))
    with pytest.raises(PhaseGearError, match="item_level_cap"):
        load_phase_config(tmp_path / "bad.json")


def test_phase_profile_ids_never_collide_with_catalog_ids():
    assert phase_profile_id("cata_t11", "fire_mage") == "cata_t11/fire_mage"
    assert all(not is_phase_profile_id(row["gear_profile_id"]) for row in _catalog().values())
    with pytest.raises(PhaseGearError):
        phase_profile_id("cata_t11", "../fire_mage")


def test_merge_adds_phase_profiles_and_refuses_to_overwrite(tmp_path):
    base = {"fire_mage": {"equipment": [{"slot": 0, "item_id": 1}]}}
    assert merge_phase_gear_profiles(base, tmp_path / "absent.json") == base, "missing output merges nothing"
    phase = {"schema": "raid_phase_gear_profiles_v1", "profiles": {
        "cata_t11/fire_mage": {"equipment": [{"slot": 0, "item_id": 2}], "complete_equipment_slots": True}}}
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(phase))
    merged = merge_phase_gear_profiles(base, path)
    assert merged["fire_mage"] == base["fire_mage"] and merged["cata_t11/fire_mage"]["equipment"][0]["item_id"] == 2
    with pytest.raises(PhaseGearError, match="collision"):
        merge_phase_gear_profiles({**base, "cata_t11/fire_mage": {}}, path)
    phase["profiles"]["fire_mage"] = phase["profiles"].pop("cata_t11/fire_mage")
    path.write_text(json.dumps(phase))
    with pytest.raises(PhaseGearError, match="phase_profiles_ids"):
        merge_phase_gear_profiles(base, path)


# --- plan -----------------------------------------------------------------------------------------

def test_bwd_plan_groups_wear_phase_profiles_and_legacy_compositions_do_not():
    from tests.test_raid_shard_plan import _plan
    from tools.raid_program.raid_loadout_sql import materialization_inputs, plan_uses_phase_profiles
    from tools.raid_program.raid_loadout_spells import DEFAULT_TRAINERS

    plan = _plan(full_raid=True)
    for shard in plan["shards"]:
        for bot in shard["bots"]:
            for group in bot["loadout"]["groups"]:
                assert group["gear_profile_id"] == f"cata_t11/{group['class_spec']}"
                assert "profession_setup" not in group, "the phase gear, not the catalog gear, decides professions"
            assert bot["gear_profile_id"] == bot["canonical_setup"]["gear_profile_id"] == f"cata_t11/{bot['class_spec']}"
    assert plan_uses_phase_profiles(plan)
    legacy = json.loads(BWD.read_text(encoding="utf-8"))
    del legacy["gear_phase"]
    control = _plan(composition=legacy)
    catalog = _catalog()
    for bot in control["shards"][0]["bots"]:
        assert bot["gear_profile_id"] == catalog[bot["class_spec"]]["gear_profile_id"]
    assert not plan_uses_phase_profiles(control)
    gear = SHARED / "profiles.json"
    assert "phase_gear_profiles" not in materialization_inputs(gear, DEFAULT_TRAINERS)
    assert "phase_gear_profiles" in materialization_inputs(gear, DEFAULT_TRAINERS, True)


# --- sources (synthetic, no database) --------------------------------------------------------------

def test_reference_loot_is_followed_and_a_missing_reference_fails_closed():
    references = {415700: [{"Item": 59341, "Reference": 0}, {"Item": 0, "Reference": 999}], 999: [{"Item": 59452, "Reference": 0}]}
    items = sorted(resolve_loot_rows([{"Item": 415700, "Reference": 415700}], references))
    assert items == [(59341, (415700,)), (59452, (415700, 999))]
    cyclic = {1: [{"Item": 0, "Reference": 1}, {"Item": 7, "Reference": 0}]}
    assert list(resolve_loot_rows([{"Item": 1, "Reference": 1}], cyclic)) == [(7, (1,))]
    with pytest.raises(PhaseSourceError, match="reference_missing"):
        list(resolve_loot_rows([{"Item": 5, "Reference": 5}], {}))


def test_vendor_costs_admit_only_phase_currencies_and_phase_tokens():
    config = json.loads(T11.read_text(encoding="utf-8"))
    free = {"honor": 0, "arena_points": 0, "arena_slot": 0, "personal_rating": 0, "items": [], "currencies": []}
    token = 63684  # Helm of the Forlorn Protector (Nefarian)
    assert vendor_cost_admitted({**free, "currencies": [395]}, config, set()) is None
    assert vendor_cost_admitted({**free, "items": [token]}, config, {token}) is None
    assert vendor_cost_admitted(free, config, set()) is None, "reputation (gold) vendors are in phase"
    assert vendor_cost_admitted({**free, "items": [token]}, config, set()) == "required_item_out_of_phase"
    assert vendor_cost_admitted({**free, "currencies": [390]}, config, set()) == "currency_out_of_phase"
    assert vendor_cost_admitted({**free, "honor": 1}, config, set()) == "pvp_cost"
    assert vendor_cost_admitted(None, config, set()) == "extended_cost_missing"


# --- built output -----------------------------------------------------------------------------------

def test_every_canonical_bwd_member_has_a_complete_phase_capped_loadout():
    from tools.bot_ml.build_validation_provisioning import required_equipment_slots_for

    payload = _payload()
    config = load_phase_config(T11)
    gems = json.loads((phase_gear_profiles_path().parent / "sources.json").read_text())["phases"]["cata_t11"]["gems"]
    gem_rows = {int(gem["item_id"]): gem for gem in gems}
    assert all(int(gem["quality"]) <= 3 and 81 <= int(gem["item_level"]) <= 85 for gem in gems)
    for spec in _bwd_specs():
        profile = payload["profiles"][f"cata_t11/{spec}"]
        rows = profile["equipment"]
        assert not set(required_equipment_slots_for(rows)) - {row["slot"] for row in rows}, spec
        assert all(333 <= row["item_level"] <= 359 for row in rows), spec
        assert 355.0 <= profile["average_item_level"] <= 359.0, (spec, profile["average_item_level"])
        for row in rows:
            view = {"ClassID": row["item_class"], "SubclassID": row["subclass"], "InventoryType": row["inventory_type"],
                    "AllowableClass": row["allowable_class"]}
            assert class_allowed(view, profile["class_id"]) and armor_allowed(view, profile["class_id"]), (spec, row["item_id"])
            assert "resilience" not in row["stats"], (spec, row["item_id"])
            assert row["player_acquisition"]["sources"], (spec, row["item_id"])
            natives = row["native_socket_colors"]
            assert len(row["gem_item_ids"]) == len(natives) + int(row["extra_socket"]), (spec, row["item_id"])
            assert all(gem in gem_rows for gem in row["gem_item_ids"]), (spec, row["item_id"])
            assert all((color == 1) == (gem_rows[gem]["color"] == 1) for gem, color in zip(row["gem_item_ids"], natives))
        assert profile["tier_set"]["name"] == config["tier_sets_by_spec"][spec] and profile["tier_set"]["pieces"] >= 4
        if any(1 in row["native_socket_colors"] for row in rows):
            assert profile["meta_gem"]["active"] is True, spec
    validation = payload["phases"]["cata_t11"]["validation"]
    assert validation["all_passed"] is True
    assert {"required_combat_spells_castable", "native_uniqueness", "reforge_within_rating_caps"} <= set(validation["checks"])


def test_every_canonical_bwd_member_can_cast_its_required_combat_spells():
    """Native equipped-item requirements (Spell.dbc + SpellEquippedItems.dbc) hold for every built spec."""
    from tools.bot_ml.phase_gear_spell_requirements import (
        apply_spell_exemptions,
        load_spell_requirements,
        spec_required_spells,
        unmet_requirements,
    )

    payload = _payload()
    config = load_phase_config(T11)
    requirements = load_spell_requirements(DBC)
    targets = list(_catalog().values())
    for spec in _bwd_specs():
        profile = payload["profiles"][f"cata_t11/{spec}"]
        required, exempted = apply_spell_exemptions(spec, spec_required_spells(_catalog()[spec], targets, requirements), config)
        assert [row["spell_id"] for row in profile["required_combat_spells"]] == [row.spell_id for row in required], spec
        assert profile["exempt_combat_spells"] == list(exempted), spec
        assert unmet_requirements(required, {int(row["slot"]): row for row in profile["equipment"]}) == [], spec
    rogue = {int(row["slot"]): row for row in payload["profiles"]["cata_t11/assassination_rogue"]["equipment"]}
    assert rogue[15]["subclass"] == rogue[16]["subclass"] == 15, "Mutilate: daggers in both hands"
    assert [row["spell_id"] for row in payload["profiles"]["cata_t11/assassination_rogue"]["exempt_combat_spells"]] == [51723]
    fan_of_knives = requirements[51723]
    assert unmet_requirements([fan_of_knives], rogue) == [], "the exemption left the current thrown weapon in place"


def _wearers():
    from tools.bot_ml.build_phase_gear_profiles import bound_compositions, spec_characters
    from tools.bot_ml.phase_gear_equip_restrictions import load_race_teams

    return spec_characters(bound_compositions("cata_t11", BWD.parent), load_race_teams(DBC))


def test_every_canonical_bwd_member_can_use_every_item_it_wears():
    """Player::CanUseItem at inventory load: faction, class/race masks, skill, spell, level, holiday, reputation."""
    from dataclasses import replace

    from tools.bot_ml.phase_gear_equip_restrictions import item_use_failures, profession_skills
    from tools.bot_ml.phase_gear_extract import DEFAULT_EXTRACT_DIR, item_facts, load_phase_extract

    payload = _payload()
    facts = item_facts(DBC, load_phase_extract(DEFAULT_EXTRACT_DIR, load_phase_config(T11), DBC)["hotfix"])
    wearers = _wearers()
    catalog = _catalog()
    for spec in _bwd_specs():
        bot = catalog[spec]["provisioning_bot"]
        assert [(view.race, view.class_id) for view in wearers[spec]] == [(int(bot["race"]), int(bot["class"]))], spec
        profile = payload["profiles"][f"cata_t11/{spec}"]
        assert profile["equip_restriction_characters"] == [
            {"race": view.race, "class": view.class_id, "level": view.level, "team": view.team} for view in wearers[spec]]
        skills = profession_skills(profile["profession_setup"])
        for row in profile["equipment"]:
            for view in wearers[spec]:
                assert item_use_failures(facts[int(row["item_id"])], replace(view, skills=skills)) == [], (spec, row["item_id"])
    assert wearers["survival_hunter"][0].team == "horde" and wearers["blood_death_knight"][0].team == "alliance"
    worn = {int(row["item_id"]) for row in payload["profiles"]["cata_t11/blood_death_knight"]["equipment"]}
    assert not worn & {62465, 62470}, "neither Stump of Time: one is Horde-only, both need Exalted"
    assert "native_use_restrictions" in payload["phases"]["cata_t11"]["validation"]["checks"]


def test_retribution_stays_within_the_hit_cap_with_its_socket_bonuses():
    """Round 3 reforged Retribution to 958 modeled hit; Belt of Absolute Zero's socket bonus made it 968 > 961."""
    from tools.bot_ml.phase_gear_extract import DEFAULT_EXTRACT_DIR, item_facts, load_phase_extract
    from tools.bot_ml.phase_gear_oracles import load_enchant_oracle
    from tools.bot_ml.phase_gear_validation import rating_totals

    payload = _payload()
    config = load_phase_config(T11)
    gems = {int(gem["item_id"]): gem for gem in json.loads(
        (phase_gear_profiles_path().parent / "sources.json").read_text())["phases"]["cata_t11"]["gems"]}
    facts = item_facts(DBC, load_phase_extract(DEFAULT_EXTRACT_DIR, config, DBC)["hotfix"])
    totals, _into = rating_totals(payload["profiles"]["cata_t11/retribution_paladin"]["equipment"], gems, load_enchant_oracle(DBC), facts)
    assert totals["hit"] <= config["reforge_policy"]["rating_caps_by_spec"]["retribution_paladin"]["hit"]


def test_the_revalidation_rejects_out_of_phase_mutations():
    """Adversarial: heroic item level, an epic gem, the wrong armor class and a foreign enchant; control passes."""
    from tools.bot_ml.phase_gear_oracles import load_enchant_oracle
    from tools.bot_ml.build_validation_gear_profiles import load_item_limit_categories
    from tools.bot_ml.build_validation_provisioning import gem_item_enchant_map
    from tools.bot_ml.phase_gear_extract import DEFAULT_EXTRACT_DIR, item_facts, load_phase_extract
    from tools.bot_ml.phase_gear_spell_requirements import load_spell_requirements, spec_required_spells
    from tools.bot_ml.phase_gear_item_effects import load_spell_effects
    from tools.bot_ml.phase_gear_validation import profile_failures

    payload = _payload()
    config = load_phase_config(T11)
    gems = {int(gem["item_id"]): gem for gem in json.loads(
        (phase_gear_profiles_path().parent / "sources.json").read_text())["phases"]["cata_t11"]["gems"]}
    oracle, mapping = load_enchant_oracle(DBC), gem_item_enchant_map(DBC)
    facts = item_facts(DBC, load_phase_extract(DEFAULT_EXTRACT_DIR, config, DBC)["hotfix"])
    limits = {category: int(row["quantity"]) for category, row in load_item_limit_categories(DBC).items()}
    requirements, targets = load_spell_requirements(DBC), list(_catalog().values())
    wearers = _wearers()
    effects = load_spell_effects(DBC)

    def failures(profile, key="x"):
        required = spec_required_spells(_catalog()[profile["class_spec"]], targets, requirements)
        return profile_failures(key, profile, config, gems, oracle, None, mapping, required, facts, limits,
                                wearers[profile["class_spec"]], profile["primary_stat"], effects)

    profile = payload["profiles"]["cata_t11/fire_mage"]
    assert failures(profile, "control") == []

    heroic = copy.deepcopy(profile)
    heroic["equipment"][0]["item_level"] = 372
    assert any("above_phase_cap" in failure for failure in failures(heroic))

    epic_gem = copy.deepcopy(profile)
    socketed = next(row for row in epic_gem["equipment"] if row["gem_item_ids"] and 1 not in row["native_socket_colors"])
    socketed["gem_item_ids"][0] = 71881  # Brilliant Queen's Garnet (4.3 epic)
    assert any("gems_not_phase" in failure for failure in failures(epic_gem))

    plate = copy.deepcopy(profile)
    chest = next(row for row in plate["equipment"] if row["slot"] == 4)
    chest["subclass"] = 4
    assert any("armor_or_slot_illegal" in failure for failure in failures(plate))

    wrong_enchant = copy.deepcopy(profile)
    ring = next(row for row in wrong_enchant["equipment"] if row["slot"] == 10)
    ring["enchant_id"] = 4102  # chest enchant on a ring
    ring["enchantments"] = "4102" + ring["enchantments"][1:]
    assert any("enchant_not_applicable" in failure for failure in failures(wrong_enchant))

    rogue = payload["profiles"]["cata_t11/assassination_rogue"]
    assert failures(rogue, "control") == []
    axe = copy.deepcopy(rogue)  # the rejected round-3 loadout: Maimgor's Bite (59462, an axe) in the off hand
    offhand = next(row for row in axe["equipment"] if row["slot"] == 16)
    offhand.update(item_id=59462, subclass=0, inventory_type=22)
    assert any("combat_spell_requirement_unmet:1329:Mutilate" in failure for failure in failures(axe))

    doubled = copy.deepcopy(profile)
    first, second = (row for row in doubled["equipment"] if row["slot"] in (10, 11))
    second["item_id"] = first["item_id"]
    assert any("item_unique_equipped_exceeded" in failure for failure in failures(doubled)), "rings are unique-equipped"

    blood = payload["profiles"]["cata_t11/blood_death_knight"]
    assert failures(blood, "control") == []
    horde_stump = copy.deepcopy(blood)  # the rejected round-3 trinket: the Horde Stump of Time on a Human
    trinket = next(row for row in horde_stump["equipment"] if row["slot"] == 13)
    trinket.update(item_id=62465, name="Stump of Time")
    found = failures(horde_stump)
    assert any("race1/class6/alliance:cannot_use:faction_restricted:horde" in failure for failure in found), found
    assert any("cannot_use:reputation_required:1178:7" in failure for failure in found), found
    exalted_ring = copy.deepcopy(profile)  # Signet of the Elder Council: Earthen Ring Exalted, never provisioned
    next(row for row in exalted_ring["equipment"] if row["slot"] == 10)["item_id"] = 62362
    assert any("cannot_use:reputation_required:1135:7" in failure for failure in failures(exalted_ring))
    assert profile_failures("k", profile, config, gems, oracle, None, mapping, (), facts, limits, [], "intellect", effects) \
        == ["k:equip_restriction_characters_missing"], "no wearer is not a pass"
    agility_proc = copy.deepcopy(blood)  # the rejected v2 trinket: Fluid Death (static hit, an agility proc) on a strength tank
    trinket = next(row for row in agility_proc["equipment"] if row["slot"] == 12)
    trinket.update(item_id=58181, name="Fluid Death", stats={"hit": 321})
    assert any("slot12:58181:off_spec_primary_stat:agility!=strength" in failure for failure in failures(agility_proc))
    assert profile_failures("k", blood, config, gems, oracle, None, mapping, (), facts, limits, wearers["blood_death_knight"],
                            None, effects) == ["k:primary_stat_undetermined"]


def test_every_canonical_bwd_member_wears_only_on_spec_primary_stats():
    """Trinkets and rings included, with the stats of their item spells (on equip, on use, on proc)."""
    from tools.bot_ml.phase_gear_extract import DEFAULT_EXTRACT_DIR, item_facts, load_phase_extract
    from tools.bot_ml.phase_gear_item_effects import item_spell_stats, load_spell_effects, off_spec_families

    payload = _payload()
    config = load_phase_config(T11)
    facts = item_facts(DBC, load_phase_extract(DEFAULT_EXTRACT_DIR, config, DBC)["hotfix"])
    effects = load_spell_effects(DBC)
    for spec in _bwd_specs():
        profile = payload["profiles"][f"cata_t11/{spec}"]
        assert profile["primary_stat"] == config["primary_stat_by_spec"][spec], spec
        for row in profile["equipment"]:
            spells = item_spell_stats(facts[int(row["item_id"])], effects)
            assert off_spec_families(row["stats"], spells, profile["primary_stat"]) == set(), (spec, row["item_id"], row["name"])
    blood = {int(row["slot"]): row for row in payload["profiles"]["cata_t11/blood_death_knight"]["equipment"]}
    for slot in (12, 13):  # a tank's trinkets grant a defensive stat
        spells = {name for _kind, name, _amount in item_spell_stats(facts[int(blood[slot]["item_id"])], effects)}
        assert (set(blood[slot]["stats"]) | spells) & {"stamina", "dodge", "parry", "mastery"}, blood[slot]["name"]
    assert "primary_stat_fit" in payload["phases"]["cata_t11"]["validation"]["checks"]


def test_the_bwd_plan_materializes_every_member_in_phase_gear():
    from tests.test_raid_shard_plan import _plan
    from tools.raid_program.raid_loadout_sql import prepare_config

    payload = _payload()
    config = prepare_config(_plan(), SHARED / "profiles.json", DBC)
    for scenario in config["scenarios"]:
        for bot in scenario["bots"]:
            profile = payload["profiles"][bot["gear_profile_id"]]
            assert sorted(int(item["item_id"]) for item in bot["equipment"]) == sorted(
                int(item["item_id"]) for item in profile["equipment"])
            worn = {int(item["item_id"]) for group in bot["loadout"]["groups"]
                    for item in payload["profiles"][group["gear_profile_id"]]["equipment"]}
            assert {int(row["item"]["item_id"]) for row in bot["loadout"]["physical_items"]} == worn


# --- shared scopes stay exactly as pinned -----------------------------------------------------------

def _dvc_dir_md5(folder: Path) -> str:
    rows = sorted(({"md5": hashlib.md5(path.read_bytes()).hexdigest(), "relpath": path.name}
                   for path in folder.iterdir() if path.is_file()), key=lambda row: row["relpath"])
    return hashlib.md5(json.dumps(rows, sort_keys=True).encode()).hexdigest() + ".dir"


def test_shared_validation_gear_profiles_are_the_dvc_locked_payload():
    if not (SHARED / "profiles.json").is_file():
        pytest.skip("validation_gear output not hydrated")
    lock = yaml.safe_load((ROOT / "dvc.lock").read_text(encoding="utf-8"))
    out = next(row for row in lock["stages"]["validation_gear"]["outs"] if row["path"] == "dataset/validation_gear_profiles")
    assert _dvc_dir_md5(SHARED) == out["md5"]
    for dep in lock["stages"]["validation_gear"]["deps"]:
        path = ROOT / dep["path"]
        if path.is_file():
            assert hashlib.md5(path.read_bytes()).hexdigest() == dep["md5"], f"validation_gear would rerun: {dep['path']}"


def test_the_phase_stage_is_isolated_from_the_shared_gear_stages():
    stages = yaml.safe_load((ROOT / "dvc.yaml").read_text(encoding="utf-8"))["stages"]
    phase = stages["raid_phase_gear"]
    assert [next(iter(out)) if isinstance(out, dict) else out for out in phase["outs"]] == ["dataset/raid_phase_gear_profiles"]
    for name in ("validation_gear", "validation_provisioning", "validation_provisioning_verify"):
        deps = [str(dep) for dep in stages[name]["deps"]]
        assert not any(dep.endswith(PHASE_MODULES) or "raid_phase_gear" in dep or "raid_gear_phases" in dep
                       or dep.endswith("raid_compositions") for dep in deps), name
    raid = [str(dep) for dep in stages["raid_shard_provisioning"]["deps"]]
    assert "dataset/raid_phase_gear_profiles" in raid and "experiments/configs/raid_gear_phases" in raid
    assert "tools/bot_ml/phase_gear_profiles.py" in raid
    imported = {f"tools/bot_ml/{name}" for name in PHASE_MODULES}
    assert imported <= {str(dep) for dep in phase["deps"]}
    assert "dataset/raid_phase_gear_db_extract" in {str(dep) for dep in phase["deps"]}, "pinned database rows"
    for name in ("validation_gear", "validation_provisioning", "validation_provisioning_verify"):
        assert not any("raid_phase_gear_db_extract" in str(dep) or "extract_phase_gear_db" in str(dep)
                       for dep in stages[name]["deps"]), name


def test_shared_loader_does_not_see_phase_profiles():
    from tools.bot_ml.build_validation_provisioning import load_gear_profiles

    if not (SHARED / "profiles.json").is_file():
        pytest.skip("validation_gear output not hydrated")
    assert not any(is_phase_profile_id(key) for key in load_gear_profiles(SHARED / "profiles.json", dbc_dir=DBC))
