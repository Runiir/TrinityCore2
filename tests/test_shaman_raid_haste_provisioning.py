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


def test_elemental_setup_reconciliation_provisions_only_native_learned_spells(tmp_path):
    import json
    import pytest
    from tools.bot_ml.build_all_spec_phase1_catalogs import (
        ACTION_PROFILES_PATH, TARGET_CATALOG_PATH,
        reconcile_elemental_setup_spell_catalogs,
    )
    from tools.bot_ml.validation_profile_manifests import load_action_profile_manifest

    targets = json.loads(TARGET_CATALOG_PATH.read_text())
    actions = json.loads(ACTION_PROFILES_PATH.read_text())
    # Retain the pre-repair shape even after checked-in outputs are reconciled.
    additions = {5675, 8143, 87507}
    target = next(row for row in targets['targets'] if row['spec_target_id'] == 'elemental_shaman')
    target['action_profile_spell_ids'] = [s for s in target['action_profile_spell_ids'] if s not in additions]
    actions['action_profile_spells_by_spec']['elemental_shaman'] = list(target['action_profile_spell_ids'])
    original = deepcopy((targets, actions))
    updated_targets, updated_actions = reconcile_elemental_setup_spell_catalogs(targets, actions)
    assert (targets, actions) == original
    assert reconcile_elemental_setup_spell_catalogs(updated_targets, updated_actions) == (updated_targets, updated_actions)
    restored_targets, restored_actions = deepcopy((updated_targets, updated_actions))
    next(row for row in restored_targets['targets'] if row['spec_target_id'] == 'elemental_shaman')['action_profile_spell_ids'] = target['action_profile_spell_ids']
    restored_actions['action_profile_spells_by_spec']['elemental_shaman'] = target['action_profile_spell_ids']
    assert (restored_targets, restored_actions) == original
    drifted = deepcopy(actions)
    drifted['action_profile_spells_by_spec']['elemental_shaman'] = []
    with pytest.raises(ValueError, match='not linked'):
        reconcile_elemental_setup_spell_catalogs(targets, drifted)

    profiles = []
    for index, payload in enumerate((actions, updated_actions)):
        path = tmp_path / f'actions-{index}.json'
        path.write_text(json.dumps(payload))
        profiles.append(load_action_profile_manifest(path))
    config = load_config_with_bwd_diagnostic_shards(
        ROOT / 'experiments/configs/validation_provisioning_cata_001.json',
        ROOT / 'experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json',
    )
    for scenario in config['scenarios']:
        for bot in scenario['bots']:
            before, after = (set(bot_known_spell_ids(bot, profile)) for profile in profiles)
            if bot.get('class_spec') != 'elemental_shaman':
                assert before == after
                continue
            assert after - before == additions
            assert {324, 3738, *additions} <= after
            assert not ({86529, 86100} & after)
            sql = build_character_insert_sql(
                {**config, 'scenarios': [{**scenario, 'bots': [bot]}]}, profiles[1],
            )
            for spell in additions:
                assert f"SELECT c.`guid`, {spell}, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = '{bot['name']}'" in sql


def test_elemental_learned_spell_reconciliation_preserves_reference_requests(monkeypatch):
    import json
    from tools.bot_ml import build_wowsims_reference_requests as references
    from tools.bot_ml.build_all_spec_phase1_catalogs import (
        ACTION_PROFILES_PATH, TARGET_CATALOG_PATH,
        reconcile_elemental_setup_spell_catalogs,
    )
    targets = json.loads(TARGET_CATALOG_PATH.read_text())
    actions = json.loads(ACTION_PROFILES_PATH.read_text())
    target = next(row for row in targets['targets'] if row['spec_target_id'] == 'elemental_shaman')
    target['action_profile_spell_ids'] = [s for s in target['action_profile_spell_ids'] if s not in {5675, 8143, 87507}]
    actions['action_profile_spells_by_spec']['elemental_shaman'] = list(target['action_profile_spell_ids'])
    updated, _ = reconcile_elemental_setup_spell_catalogs(targets, actions)
    original_load = references._load_json
    selected = targets
    monkeypatch.setattr(references, '_load_json', lambda path: selected if path.resolve() == TARGET_CATALOG_PATH.resolve() else original_load(path))
    before = references.build_manifest(root=ROOT)
    selected = updated
    after = references.build_manifest(root=ROOT)
    # Pure request reconstruction uses the existing frozen fixture. No simulator
    # or generated reference artifact is run or rewritten by this comparison.
    assert before == after
    assert references.canonical_sha256(before) == references.canonical_sha256(after)
