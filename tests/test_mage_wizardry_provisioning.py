"""Wizardry is learned through ordinary provisioning, never a manual aura."""
from copy import deepcopy
import json
from pathlib import Path

from tools.bot_ml import build_all_spec_phase1_catalogs as catalogs
from tools.bot_ml.build_validation_provisioning import (
    bot_known_spell_ids, build_character_insert_sql, load_config_with_bwd_diagnostic_shards,
)
from tools.bot_ml.validation_profile_manifests import load_action_profile_manifest

ROOT = Path(__file__).resolve().parents[1]
MAGES = {'arcane_mage', 'fire_mage', 'frost_mage'}


def test_wizardry_real_known_spell_builder_all_mages_only():
    targets = json.loads(catalogs.TARGET_CATALOG_PATH.read_text())
    for target in targets['targets']:
        spells = catalogs.action_spell_ids(target['spec_target_id'], target['class_id'], target['talent_build'])
        assert (89744 in spells) == (target['spec_target_id'] in MAGES)


def test_wizardry_reconciliation_and_actual_character_spell_sql(tmp_path):
    targets = json.loads(catalogs.TARGET_CATALOG_PATH.read_text())
    actions = json.loads(catalogs.ACTION_PROFILES_PATH.read_text())
    for target in targets['targets']:
        if target['spec_target_id'] in MAGES:
            target['action_profile_spell_ids'] = [s for s in target['action_profile_spell_ids'] if s != 89744]
            actions['action_profile_spells_by_spec'][target['spec_target_id']] = list(target['action_profile_spell_ids'])
    before = deepcopy((targets, actions))
    updated, manifest = catalogs.reconcile_mage_setup_spell_catalogs(targets, actions)
    assert (targets, actions) == before
    assert catalogs.reconcile_mage_setup_spell_catalogs(updated, manifest) == (updated, manifest)
    for original, result in zip(targets['targets'], updated['targets']):
        if original['spec_target_id'] in MAGES:
            assert set(result['action_profile_spell_ids']) - set(original['action_profile_spell_ids']) == {89744}
            result = {**result, 'action_profile_spell_ids': original['action_profile_spell_ids']}
        assert result == original  # gear/talents/glyphs/consumes/rotation identity unchanged
    path = tmp_path / 'actions.json'
    path.write_text(json.dumps(manifest))
    profiles = load_action_profile_manifest(path)
    config = load_config_with_bwd_diagnostic_shards(
        catalogs.PROVISIONING_PATH, ROOT/'experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json')
    seen = set()
    for scenario in config['scenarios']:
        for bot in scenario['bots']:
            mage = bot.get('class_spec') in MAGES
            assert (89744 in bot_known_spell_ids(bot, profiles)) == mage
            if not mage:
                continue
            seen.add(bot['class_spec'])
            sql = build_character_insert_sql({**config, 'scenarios': [{**scenario, 'bots': [bot]}]}, profiles)
            assert f"SELECT c.`guid`, 89744, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = '{bot['name']}'" in sql
    assert seen == MAGES


def test_wizardry_checked_in_catalogs_and_generated_identity_agree(tmp_path):
    from tools.bot_ml import generate_bot_admission_identities as admission
    targets = json.loads(catalogs.TARGET_CATALOG_PATH.read_text())
    actions = json.loads(catalogs.ACTION_PROFILES_PATH.read_text())
    for row in targets['targets']:
        assert row['action_profile_spell_ids'] == actions['action_profile_spells_by_spec'][row['spec_target_id']]
        assert (89744 in row['action_profile_spell_ids']) == (row['spec_target_id'] in MAGES)
    current = admission.build_identity_catalog()
    assert admission.DEFAULT_OUTPUT.read_text() == admission.render_header(current)
    before = deepcopy(targets)
    for row in before['targets']:
        if row['spec_target_id'] in MAGES:
            row['action_profile_spell_ids'].remove(89744)
    path = tmp_path/'before.json'
    path.write_text(json.dumps(before, indent=2)+'\n')
    previous = admission.build_identity_catalog(targets_path=path)
    # Admission tracks talent/gear identities and a whole-source hash, not the
    # ordinary known-spell set. Wizardry changes only the latter source binding.
    assert previous['identities'] == current['identities']
    assert previous['source_content_sha256'] != current['source_content_sha256']
    for name, digest in previous['source']['sources'].items():
        if name != 'all_spec_targets_cata_p4_v1.json':
            assert digest == current['source']['sources'][name]
