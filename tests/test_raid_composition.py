from __future__ import annotations

import copy
import json

import pytest

from tools.raid_program.raid_composition import (
    BASE_GEAR_PROFILES,
    COMPOSITION_DIR,
    REFERENCE_REQUESTS,
    WOWSIMS_GEAR_PROFILES,
    CompositionError,
    composition_specs,
    gear_coverage_report,
    legacy_bwd_specs,
    load_catalog,
    read_json,
    role_counts,
    selected_specs,
    validate_composition,
)

BWD = COMPOSITION_DIR / "blackwing_descent_10n.json"


def _composition() -> dict:
    return read_json(BWD)


def test_canonical_bwd_10n_composition_matches_the_decision_table():
    composition = _composition()
    catalog = load_catalog(composition)
    assert validate_composition(composition, catalog)["multi_spec_characters"] == ["druid", "shaman"]
    specs = {row["character_key"]: row["specs"] for row in composition["characters"]}
    assert specs == {
        "death_knight": ["blood_death_knight"],
        "druid": ["balance_druid", "feral_druid_tank"],
        "hunter": ["beast_mastery_hunter"],
        "mage": ["fire_mage"],
        "paladin_holy": ["holy_paladin"],
        "paladin_ret": ["retribution_paladin"],
        "priest": ["discipline_priest"],
        "rogue": ["assassination_rogue"],
        "shaman": ["elemental_shaman", "restoration_shaman"],
        "warlock": ["demonology_warlock"],
    }
    assert "protection_paladin" not in composition_specs(composition)
    assert not any("warrior" in spec for spec in composition_specs(composition))


def test_per_boss_spec_selection_is_explicit_provisional_and_sets_role_counts():
    composition = _composition()
    catalog = load_catalog(composition)
    expected = {
        "magmaw": ("balance_druid", "elemental_shaman", {"tank": 1, "healer": 2, "dps": 7}),
        "omnotron": ("feral_druid_tank", "elemental_shaman", {"tank": 2, "healer": 2, "dps": 6}),
        "chimaeron": ("feral_druid_tank", "restoration_shaman", {"tank": 2, "healer": 3, "dps": 5}),
        "atramedes": ("balance_druid", "elemental_shaman", {"tank": 1, "healer": 2, "dps": 7}),
        "maloriak": ("feral_druid_tank", "elemental_shaman", {"tank": 2, "healer": 2, "dps": 6}),
        "nefarian": ("feral_druid_tank", "restoration_shaman", {"tank": 2, "healer": 3, "dps": 5}),
    }
    for boss in composition["bosses"]:
        druid, shaman, counts = expected[boss["boss_key"]]
        specs = selected_specs(composition, boss)
        assert (specs["druid"], specs["shaman"]) == (druid, shaman)
        assert specs["death_knight"] == "blood_death_knight"
        assert role_counts(composition, catalog, boss) == counts
        assert boss["selection_status"] == "provisional"


@pytest.mark.parametrize("mutate,check", [
    (lambda c: c["bosses"][0]["spec_selection"].pop("druid"), "spec_selection_characters"),
    (lambda c: c["bosses"][0]["spec_selection"].update(druid="restoration_druid"), "spec_selection_value"),
    (lambda c: c["characters"][1]["specs"].__setitem__(1, "frost_mage"), "character_specs_share_class"),
    (lambda c: c["characters"].pop(), "character_count"),
    (lambda c: c["characters"][0]["specs"].append("frost_death_knight") or c["characters"][0]["specs"].append("unholy_death_knight"), "character_specs"),
    (lambda c: c["bosses"][1].update(name_code="mgw"), "duplicate_boss_name_code"),
    (lambda c: c["bosses"][1].update(boss_number=0), "duplicate_boss_boss_number"),
    (lambda c: c.update(talent_groups_count=1), "talent_groups_count_must_be_2"),
    (lambda c: c["off_spec_bag"].update(container_slots=16), "off_spec_bag"),
])
def test_composition_defects_fail_closed(mutate, check):
    composition = copy.deepcopy(_composition())
    mutate(composition)
    with pytest.raises(CompositionError) as error:
        validate_composition(composition, load_catalog(composition))
    assert check in {row["check"] for row in json.loads(str(error.value))["failures"]}


def test_single_tank_boss_without_a_healer_is_rejected():
    composition = copy.deepcopy(_composition())
    catalog = load_catalog(composition)
    composition["characters"][4]["specs"] = ["retribution_paladin"]
    composition["characters"][6]["specs"] = ["shadow_priest"]
    for boss in composition["bosses"]:
        boss["spec_selection"]["shaman"] = "elemental_shaman"
    with pytest.raises(CompositionError, match="boss_role_counts"):
        validate_composition(composition, catalog)


def test_gear_coverage_lists_gaps_without_inventing_gear():
    composition = _composition()
    catalog = load_catalog(composition)
    base = read_json(BASE_GEAR_PROFILES) if BASE_GEAR_PROFILES.is_file() else None
    specs = composition_specs(composition) + [s for s in legacy_bwd_specs() if s not in composition_specs(composition)]
    report = gear_coverage_report(specs, catalog, read_json(WOWSIMS_GEAR_PROFILES), base, read_json(REFERENCE_REQUESTS))
    for spec in ("retribution_paladin", "assassination_rogue", "demonology_warlock",
                 "fire_mage", "balance_druid", "elemental_shaman", "affliction_warlock", "marksmanship_hunter"):
        assert spec in report["covered"], spec
        assert report["specs"][spec]["authority"] == "wowsims_p4_preset"
        assert report["specs"][spec]["provider_revision"] == "70d87383a9b92f30fb9e370c4676d3ce33b6e6b6"
    for spec in ("beast_mastery_hunter", "feral_druid_tank", "restoration_shaman",
                 "blood_death_knight", "holy_paladin", "discipline_priest"):
        assert spec in report["gaps"], spec
        assert report["specs"][spec]["authority"] != "wowsims_p4_preset"
    assert report["specs"]["beast_mastery_hunter"]["wowsims_dps_reference_request"] is False
    if base is not None:
        assert report["specs"]["feral_druid_tank"]["authority"] == "heuristic_player_acquisition_profile"


def test_missing_catalog_target_is_a_gap():
    report = gear_coverage_report(["not_a_spec"], {}, {"profiles": {}}, None, None)
    assert report["gaps"] == ["not_a_spec"]
    assert report["specs"]["not_a_spec"]["authority"] == "missing_catalog_target"
