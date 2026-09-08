import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

from tools.bot_ml.build_validation_gear_profiles import build_gem_catalog, choose_loadout
from tools.bot_ml.build_validation_provisioning import (
    apply_gear_profiles, load_config_with_bwd_diagnostic_shards, load_gear_profiles,
)
from tools.bot_ml.phase8_calibration_adapter import canonical_gear_manifest
from tools.bot_ml.player_gear_acquisition import bind_player_acquisition


def test_acquisition_excludes_test_item_and_unresolved_reference_loot(tmp_path):
    # The client test robe legitimately parses with extreme stats; a stat score
    # or client-definition presence must not admit it into player equipment.
    base = dict(ClassID=4, SubclassID=1, InventoryType=20, AllowableClass=-1,
                RequiredLevel=85, Quality=4, ItemLevel=410,
                ItemStatType1=5, ItemStatValue1=489)
    items = [dict(base, ID=78728, Display="Robes of Dying Light"),
             dict(base, ID=55159, Display="Rough Approximation Healer Robe",
                  RequiredLevel=0, Quality=2, ItemLevel=318, ItemStatValue1=2793),
             dict(base, ID=999, Display="Unreleased Robe", ItemStatValue1=9999)]
    index = tmp_path / "sources.jsonl"
    index.write_text("\n".join(json.dumps(row) for row in [
        dict(item_id=78728, sources=[dict(item_id=78728, source_type="vendor", source_entry=44245)]),
        dict(item_id=55159, sources=[dict(item_id=55159, source_type="creature_loot", source_entry=1, reference=123)]),
    ]))
    bound = bind_player_acquisition(items, index)
    assert not bound[1]["player_acquisition"]["sources"]
    assert not bound[2]["player_acquisition"]["sources"]
    result = choose_loadout(dict(class_spec="discipline_priest", role="healer", **{"class": 5}), bound,
                            enchantments=[dict(id=4173, stats={"intellect": 99999}, name="Unverified enchant")])
    assert [item["item_id"] for item in result] == [78728]
    assert result[0]["player_accessible"]
    assert result[0]["player_acquisition"]["index_sha256"]
    assert result[0]["enchant_id"] == 0


def test_shard_dps_equipment_matches_promoted_profile_after_all_overlays():
    profiles = load_gear_profiles(Path("dataset/validation_gear_profiles/profiles.json"))
    config = load_config_with_bwd_diagnostic_shards(
        Path("experiments/configs/validation_provisioning_cata_001.json"),
        Path("experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"))
    resolved = apply_gear_profiles(config, profiles)
    targets = {row["spec_target_id"]: row for row in json.loads(
        Path("experiments/configs/all_spec_targets_cata_p4_v1.json").read_text())["targets"]}
    count = 0
    for scenario in resolved["scenarios"]:
        for bot in scenario["bots"]:
            if bot.get("canonical_setup") and bot["role"] == "dps":
                profile_id = targets[bot["class_spec"]]["gear_profile_id"]
                assert bot["canonical_setup"]["gear_profile_id"] == bot["gear_profile_id"] == profile_id
                assert canonical_gear_manifest(bot["equipment"], label="actual") == canonical_gear_manifest(
                    profiles[profile_id]["equipment"], label="expected")
                count += 1
    assert count == 30


def test_canonical_label_cannot_mask_different_resolved_equipment():
    equipment = [dict(slot=4, item_id=78729, enchant_id=0)]
    bot = dict(name="Mage", class_spec="fire_mage", gear_profile="fire_mage",
               canonical_setup=dict(gear_profile_id="wowsims_cata_p4_fire_mage"))
    profiles = {"fire_mage": dict(equipment=[dict(slot=4, item_id=55159)]),
                "wowsims_cata_p4_fire_mage": dict(equipment=equipment)}
    with pytest.raises(ValueError, match="resolved canonical gear profile identity mismatch"):
        apply_gear_profiles(dict(scenarios=[dict(bots=[bot])]), profiles)
    bot = copy.deepcopy(bot)
    bot["gear_profile"] = "wowsims_cata_p4_fire_mage"
    bot["equipment"] = [dict(slot=4, item_id=55159)]
    with pytest.raises(ValueError, match="canonical gear equipment mismatch"):
        apply_gear_profiles(dict(scenarios=[dict(bots=[bot])]), profiles)


def test_socket_does_not_admit_an_unresolved_high_score_gem(tmp_path):
    index = tmp_path / "sources.jsonl"
    index.write_text(json.dumps(dict(item_id=78728, sources=[dict(
        item_id=78728, source_type="vendor", source_entry=44245)])))
    robe = dict(ID=78728, Display="Robes of Dying Light", ClassID=4, SubclassID=1,
                InventoryType=20, AllowableClass=-1, Quality=4, ItemLevel=410,
                RequiredLevel=85, SocketColor1=2, ItemStatType1=5, ItemStatValue1=489)
    gem = dict(ID=999, Display="Unresolved gem", GemProperties=1,
               ItemLevel=85, RequiredLevel=85)
    bound = bind_player_acquisition([robe, gem], index)
    gems = build_gem_catalog(bound, {1: dict(enchant_id=7, color=2)},
                            {7: dict(id=7, stats={"intellect": 99999})})
    assert gems == []
    result = choose_loadout(dict(class_spec="discipline_priest", role="healer", **{"class": 5}), bound, gems=gems)
    assert result[0]["gem_item_ids"] == [0]
    assert result[0]["gem_enchant_ids"] == [0]


def test_missing_generated_profiles_fallback_binds_acquisition(tmp_path, monkeypatch):
    from tools.bot_ml import validate_validation_provisioning as validator
    index = tmp_path / "sources.jsonl"
    index.write_text(json.dumps(dict(item_id=78728, sources=[dict(
        item_id=78728, source_type="vendor", source_entry=44245)])))
    items = [dict(ID=78728, Display="Robes of Dying Light", ClassID=4, SubclassID=1,
                  InventoryType=20, AllowableClass=-1, Quality=4, ItemLevel=410,
                  RequiredLevel=85, ItemStatType1=5, ItemStatValue1=489)]
    monkeypatch.setattr(validator, "fetch_items", lambda *a, **kw: items)
    monkeypatch.setattr(validator, "load_spell_item_enchantments", lambda *a: [])
    for name in ("load_gem_properties", "load_enchantment_source_items", "load_item_limit_categories"):
        monkeypatch.setattr(validator, name, lambda *a: {})
    config = dict(scenarios=[dict(bots=[dict(name="Healer", class_spec="discipline_priest", role="healer", **{"class": 5})])])
    result = validator.load_or_build_gear_profiles(tmp_path / "absent.json", config, tmp_path, None, index)
    assert result["discipline_priest"]["equipment"][0]["item_id"] == 78728
    assert result["discipline_priest"]["equipment"][0]["player_acquisition"]["sources"]


def test_direct_script_import_preserves_explicit_canonical_equipment():
    subprocess.run([sys.executable, "-c", """
import sys
sys.path.insert(0, 'tools/bot_ml')
import build_validation_provisioning as module
equipment = [dict(slot=4, item_id=78729)]
bot = dict(name='Mage', gear_profile='exact', equipment=equipment,
           canonical_setup=dict(gear_profile_id='exact'))
result = module.apply_gear_profiles(dict(scenarios=[dict(bots=[bot])]),
                                   dict(exact=dict(equipment=equipment)))
assert result['scenarios'][0]['bots'][0]['equipment'] == equipment
"""], cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True, text=True)


def test_validation_evidence_counts_positive_source_gems(monkeypatch):
    from tools.bot_ml import validate_validation_provisioning as validator
    from tools.bot_ml.build_validation_gear_profiles import fetch_items
    dbc = Path("data/dbc/enUS")
    items = fetch_items("", dbc, min_item_level=1, max_required_level=85)
    monkeypatch.setattr(validator, "fetch_items", lambda *a, **kw: items)
    failures, evidence = validator.validate_payloads(dict(scenarios=[]), dbc, "unused")
    assert not failures
    assert evidence["gem_catalog_count"] > 0
