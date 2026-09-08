"""The canonical Alliance roster must provision its executable raid haste."""

from copy import deepcopy
from pathlib import Path

from tools.bot_ml.build_validation_provisioning import (
    bot_known_spell_ids,
    build_character_insert_sql,
    load_config_with_bwd_diagnostic_shards,
)


ROOT = Path(__file__).resolve().parents[1]


def test_canonical_shaman_and_each_shard_provision_only_heroism_variant():
    config = load_config_with_bwd_diagnostic_shards(
        ROOT / "experiments/configs/validation_provisioning_cata_001.json",
        ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json",
    )
    selected = []
    for scenario in config["scenarios"]:
        for bot in scenario["bots"]:
            if bot["name"] == "Bwddpse" or (
                bot.get("class_spec") == "elemental_shaman"
                and bot.get("expected_character_guid", 0) in
                (30010, 30110, 30210, 30310, 30410, 30510)
            ):
                selected.append((scenario, bot))
    assert len(selected) == 7
    for scenario, bot in selected:
        assert (bot["race"], bot["class"], bot["level"]) == (11, 7, 85)
        known = set(bot_known_spell_ids(bot))
        assert 32182 in known
        assert 2825 not in known
        without_haste = deepcopy(bot)
        without_haste["spells"] = [s for s in bot["spells"] if s != 32182]
        assert known - set(bot_known_spell_ids(without_haste)) == {32182}
        one_bot = {**config, "scenarios": [{**scenario, "bots": [bot]}]}
        sql = build_character_insert_sql(one_bot)
        spell_rows = [line for line in sql.splitlines()
                      if "INSERT INTO `characters`.`character_spell`" in line]
        assert any(f"SELECT c.`guid`, 32182, 1, 0" in row
                   and f"c.`name` = '{bot['name']}'" in row for row in spell_rows)
        assert not any("SELECT c.`guid`, 2825," in row for row in spell_rows)
