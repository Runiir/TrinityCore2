"""Learn the Hunter parent; native loading and equipped armor own its child."""
from copy import deepcopy
import json
from pathlib import Path

import pytest
from tools.bot_ml import build_all_spec_phase1_catalogs as catalogs
from tools.bot_ml import run_live_bot_validation as live
from test_calibration_known_spell_preparation import Database, SocketDatabase, replay_main_preparation

ROOT = Path(__file__).resolve().parents[1]
HUNTERS = {'beast_mastery_hunter', 'marksmanship_hunter', 'survival_hunter'}


def documents():
    return (json.loads(catalogs.TARGET_CATALOG_PATH.read_text()),
            json.loads(catalogs.ACTION_PROFILES_PATH.read_text()))


def without_parent():
    targets, actions = documents()
    for target in targets['targets']:
        if target['spec_target_id'] in HUNTERS:
            target['action_profile_spell_ids'].remove(87506)
            actions['action_profile_spells_by_spec'][target['spec_target_id']].remove(87506)
    return targets, actions


def test_hunter_producer_and_linked_catalogs_include_only_learned_parent():
    targets, actions = documents()
    for target in targets['targets']:
        spec = target['spec_target_id']
        spells = catalogs.action_spell_ids(spec, target['class_id'], target['talent_build'])
        assert (87506 in spells) == (spec in HUNTERS)
        assert target['action_profile_spell_ids'] == actions['action_profile_spells_by_spec'][spec]
        assert (87506 in target['action_profile_spell_ids']) == (spec in HUNTERS)
        assert 86528 not in spells


def test_hunter_reconciliation_is_idempotent_and_preserves_every_other_field():
    targets, actions = without_parent()
    before = deepcopy((targets, actions))
    updated = catalogs.reconcile_hunter_setup_spell_catalogs(targets, actions)
    assert (targets, actions) == before
    assert updated == documents()
    assert catalogs.reconcile_hunter_setup_spell_catalogs(*updated) == updated
    restored = deepcopy(updated)
    for target in restored[0]['targets']:
        if target['spec_target_id'] in HUNTERS:
            original = next(t for t in targets['targets'] if t['spec_target_id'] == target['spec_target_id'])
            assert set(target['action_profile_spell_ids']) - set(original['action_profile_spell_ids']) == {87506}
            target['action_profile_spell_ids'].remove(87506)
            restored[1]['action_profile_spells_by_spec'][target['spec_target_id']].remove(87506)
    assert restored == before  # Includes exact pet, gear, reference, and non-Hunter rows.


def test_hunter_reconciliation_preserves_pure_reference_request_manifest(monkeypatch):
    from tools.bot_ml import build_wowsims_reference_requests as references
    targets, actions = without_parent()
    updated, _ = catalogs.reconcile_hunter_setup_spell_catalogs(targets, actions)
    original_load = references._load_json
    selected = targets
    monkeypatch.setattr(references, '_load_json', lambda path: selected
                        if path.resolve() == catalogs.TARGET_CATALOG_PATH.resolve() else original_load(path))
    before = references.build_manifest(root=ROOT)
    selected = updated
    after = references.build_manifest(root=ROOT)
    assert before == after
    assert references.canonical_sha256(before) == references.canonical_sha256(after)


@pytest.mark.parametrize('spec', sorted(HUNTERS))
@pytest.mark.parametrize('prior', ['missing', 'inactive', 'disabled'])
def test_actual_hunter_launch_repairs_parent_and_repeated_launch_is_noop(tmp_path, monkeypatch, spec, prior):
    expected = live.prepare_calibration_known_spells(tmp_path, tmp_path/'world.conf', spec,
        catalogs.TARGET_CATALOG_PATH, apply=False, pool_tag='all_spec_candidate_pool')['expected_spell_ids']
    assert 87506 in expected and 86528 not in expected
    db = hunter_database(spec, [s for s in expected if s != 87506])
    if prior != 'missing':
        db.spells[87506] = {'spell': 87506, 'active': int(prior != 'inactive'), 'disabled': int(prior == 'disabled')}
    result = replay_main_preparation(tmp_path, monkeypatch, db)['calibration_known_spells']
    assert db.writes == [(1294, 87506)]
    assert result['reconciled_spell_ids'] == [87506] and result['readback']['passed']
    assert db.commits == 1 and not db.rollbacks
    assert not getattr(db, 'item_writes', [])
    replay_main_preparation(tmp_path, monkeypatch, db)
    assert db.writes == [(1294, 87506)] and not db.skill_writes
    assert not getattr(db, 'item_writes', [])


def hunter_database(spec, spells, **kwargs):
    target = next(t for t in documents()[0]['targets'] if t['spec_target_id'] == spec)
    if spec in {'marksmanship_hunter', 'survival_hunter'}:
        plan = live.prepare_calibration_known_spells(
            ROOT, ROOT/'unused-world.conf', spec, catalogs.TARGET_CATALOG_PATH,
            pool_tag='all_spec_candidate_pool')
        rows = [
            {
                'slot': item['slot'],
                'item_guid': 90000 + item['slot'],
                'item_entry': item['item_entry'],
                'owner_guid': 1294,
                'enchantments': item['enchantments'],
            }
            for item in plan['expected_socket_items']
        ]
        db = SocketDatabase(spells, rows)
        db.spec = spec
        db.discard = bool(kwargs.get('discard', False))
        db.skills = {164: {'skill': 164, 'value': 525, 'max': 525}}
        db.original_skills = deepcopy(db.skills)
    else:
        db = Database(spells, spec=spec, **kwargs)
    db.name = target['provisioning_bot']['name']
    db.actor.update(guid=1294, **{'class': 3})
    return db


@pytest.mark.parametrize('guard', ['wrong_class', 'online', 'in_use', 'failed_readback'])
def test_hunter_actual_preparation_rejects_actor_or_readback_and_rolls_back(tmp_path, monkeypatch, guard):
    spec = 'marksmanship_hunter'
    expected = live.prepare_calibration_known_spells(tmp_path, tmp_path/'world.conf', spec,
        catalogs.TARGET_CATALOG_PATH, pool_tag='all_spec_candidate_pool')['expected_spell_ids']
    db = hunter_database(spec, [s for s in expected if s != 87506], discard=guard == 'failed_readback')
    if guard == 'wrong_class': db.actor['class'] = 8
    if guard in ('online', 'in_use'): db.actor[guard] = 1
    before = deepcopy(db.spells)
    monkeypatch.setattr(live, 'connect_mysql', lambda _: db)
    monkeypatch.setattr(live, 'database_url_from_worldserver_conf', lambda *_: 'mysql://fixture/characters')
    with pytest.raises(RuntimeError):
        live.prepare_calibration_known_spells(tmp_path, tmp_path/'world.conf', spec,
            catalogs.TARGET_CATALOG_PATH, apply=True, pool_tag='all_spec_candidate_pool')
    assert db.rollbacks == 1 and db.commits == 0 and db.spells == before
    assert db.writes == ([(1294, 87506)] if guard == 'failed_readback' else [])
    assert not db.skill_writes
    assert not getattr(db, 'item_writes', [])


def test_unlinked_hunter_metadata_rejects_reconciliation_and_main_before_reset(tmp_path, monkeypatch):
    targets, actions = documents()
    actions['action_profile_spells_by_spec']['marksmanship_hunter'].remove(87506)
    with pytest.raises(ValueError, match='not linked'):
        catalogs.reconcile_hunter_setup_spell_catalogs(targets, actions)
    target_path = tmp_path/'targets.json'
    target_path.write_text(json.dumps(targets))
    (tmp_path/'cata_434_action_profiles.json').write_text(json.dumps(actions))
    db = hunter_database('marksmanship_hunter', [])
    with pytest.raises(RuntimeError, match='not linked'):
        replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=target_path)
    assert db.preparation_order == [] and db.connections == 0
    assert not db.writes and not db.skill_writes


def test_native_specialization_child_and_equipped_armor_keep_ownership():
    learning = (ROOT/'sql/old/4.3.4/world/20091_2021_07_06/2021_02_19_02_world.sql').read_text()
    assert '(87506, 86528, 1)' in learning
    source = (ROOT/'src/server/game/Entities/Player/Player.cpp').read_text()
    begin = source.index('void Player::UpdateArmorSpecialization()')
    body = source[begin:source.index('\nuint8 Player::', begin)]
    assert 'if (HasSpell(ArmorSpecializationIds[id]))' in body
    assert 'CastSpell(this, ArmorSpecializationIds[id], TRIGGERED_FULL_MASK);' in body
    assert 'SPELL_ATTR8_REQUIRES_EQUIPPED_INV_TYPES' in body
    script = (ROOT/'src/server/scripts/Spells/spell_generic_bonuses_utilities.cpp').read_text()
    begin = script.index('class spell_gen_armor_specialization')
    body = script[begin:script.index('\nenum PvPTrinket', begin)]
    assert 'if (player->HasAllItemsToFitToSpellRequirements(spellInfo))' in body
    assert 'spellId = SPELL_ARMOR_SPEC_HUN;' in body
