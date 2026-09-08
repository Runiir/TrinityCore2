from __future__ import annotations

import json
from pathlib import Path

from tools.bot_ml.build_validation_provisioning import (
    glyph_item_to_property_map,
    glyph_property_type_map,
    normalized_glyph_slots,
)
from tools.raid_program.bwd_shard_fixtures import (
    CANONICAL_ROSTER_SLOT_IDS,
    SHARD_ROSTER_SOURCE_OVERRIDES,
    build_shard_fixture,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/validation_provisioning_cata_001.json"
FIXTURE = ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json"

EXPECTED_NON_DPS_GLYPHS = {
    "protection_paladin": [45742, 41098, 43869, 41107, 43367, 43867, 43368, 43340, 43366],
    "blood_death_knight": [43533, 43547, 43549],
    "restoration_druid": [45623, 40906, 40913],
    "holy_paladin": [45741, 41099, 41105],
    "discipline_priest": [42409, 42400, 42403],
}


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical(config: dict) -> dict:
    return next(row for row in config["scenarios"] if row["id"] == "blackwing_descent_10n")


def _target_glyphs(config: dict) -> dict[str, list[int]]:
    catalog = _read(ROOT / config["canonical_target_catalog"])
    return {
        str(row["runtime_join_key"]): list(row["provisioning_bot"]["glyphs"])
        for row in catalog["targets"]
        if row.get("role") == "dps" and isinstance(row.get("provisioning_bot"), dict)
    }


def test_bwd_canonical_dps_glyphs_match_target_catalog_and_keep_fallbacks():
    config = _read(CONFIG)
    canonical = _canonical(config)
    target_glyphs = _target_glyphs(config)

    dps = [bot for bot in canonical["bots"] if bot["role"] == "dps"]
    assert {bot["class_spec"] for bot in dps} <= set(target_glyphs)
    for bot in dps:
        assert bot["glyphs"] == target_glyphs[bot["class_spec"]]

    for bot in canonical["bots"]:
        if bot["role"] != "dps":
            assert bot["glyphs"] == EXPECTED_NON_DPS_GLYPHS[bot["class_spec"]]


def test_all_six_bwd_shards_clone_canonical_or_declared_override_glyph_source():
    config = _read(CONFIG)
    canonical = _canonical(config)
    canonical_by_slot = dict(zip(CANONICAL_ROSTER_SLOT_IDS, canonical["bots"], strict=True))
    fixture = _read(FIXTURE)

    assert fixture == build_shard_fixture(config)
    assert len(fixture["shards"]) == 6
    for shard in fixture["shards"]:
        overrides = SHARD_ROSTER_SOURCE_OVERRIDES.get(shard["boss_key"], {})
        for bot in shard["bots"]:
            slot = bot["canonical_roster_slot_id"]
            source_slot = overrides.get(slot, slot)
            source = canonical_by_slot[source_slot]
            assert bot["roster_source_slot_id"] == source_slot
            assert bot["glyphs"] == source["glyphs"]
            assert bot["canonical_setup"]["glyph_ids"] == source["glyphs"]


def test_bwd_dps_normalized_glyph_slots_use_pinned_dbc_and_elemental_950_is_prime():
    config = _read(CONFIG)
    canonical = _canonical(config)
    target_glyphs = _target_glyphs(config)
    dbc_dir = ROOT / "data/dbc/enUS"
    item_to_property = glyph_item_to_property_map(dbc_dir)
    property_types = glyph_property_type_map(dbc_dir)

    for bot in canonical["bots"]:
        if bot["role"] != "dps":
            continue
        assert all(item_id in item_to_property for item_id in bot["glyphs"])
        expected = normalized_glyph_slots(
            {"glyphs": target_glyphs[bot["class_spec"]]},
            item_to_property,
            property_types,
        )
        assert normalized_glyph_slots(bot, item_to_property, property_types) == expected

    elemental = next(bot for bot in canonical["bots"] if bot["class_spec"] == "elemental_shaman")
    assert item_to_property[71155] == 950
    assert property_types[950] == 2
    assert normalized_glyph_slots(elemental, item_to_property, property_types) == [
        225,
        612,
        473,
        222,
        471,
        754,
        219,
        214,
        950,
    ]
