"""Replay the actual process-runner preparation branch with an existing actor."""
import inspect
import json
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.bot_ml.phase8_fixture_contract import load_materialized_fixture_contract
from tools.bot_ml import run_live_bot_validation as live

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT/'experiments/configs/all_spec_targets_cata_p4_v1.json'


class Database:
    def __init__(self, spells, *, online=0, in_use=0, enabled=1, discard=False, spec="fire_mage", skills=None, discard_skills=False):
        self.spells = {s: {'spell': s, 'active': 1, 'disabled': 0} for s in spells}
        self.actor = {'guid': 1304, 'class': 8, 'online': online, 'in_use': in_use, 'enabled': enabled}
        self.spec = spec
        self.name = 'Afflock' if spec == 'affliction_warlock' else 'Firemage'
        if spec == 'affliction_warlock': self.actor.update(guid=1306, **{'class': 9})
        if spec == 'beast_mastery_hunter':
            self.name = next(t['provisioning_bot']['name'] for t in json.loads(TARGETS.read_text())['targets']
                             if t['spec_target_id'] == spec)
            self.actor.update(guid=1313, **{'class': 3})
        self.skills = copy.deepcopy(skills if skills is not None else {197: {'skill': 197, 'value': 525, 'max': 525}})
        self.original_spells, self.original_skills = copy.deepcopy(self.spells), copy.deepcopy(self.skills)
        self.skill_writes = []
        self.discard_skills = discard_skills
        self.rows = []
        self.writes = []
        self.connections = 0
        self.commits = self.rollbacks = 0
        self.discard = discard
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def close(self): pass
    def commit(self): self.commits += 1
    def rollback(self):
        self.rollbacks += 1
        self.spells, self.skills = copy.deepcopy(self.original_spells), copy.deepcopy(self.original_skills)
    def fetchall(self): return self.rows
    def execute(self, sql, params):
        if sql.startswith('SELECT c.guid'):
            assert params == (self.name, self.spec, 'all_spec_candidate_pool')
            self.rows = [self.actor]
        elif sql.startswith('SELECT spell'):
            assert params == (self.actor["guid"],)
            self.rows = list(self.spells.values())
        elif sql.startswith('SELECT skill'):
            assert params[0] == self.actor['guid'] and len(params) > 1
            self.rows = [self.skills[s].copy() for s in params[1:] if s in self.skills]
        elif sql.startswith('INSERT INTO character_skills'):
            assert params[0] == self.actor['guid']
            self.skill_writes.append(params)
            if not self.discard_skills:
                self.skills[params[1]] = dict(skill=params[1], value=params[2], max=params[3])
        else:
            assert sql == ('INSERT INTO character_spell (guid, spell, active, disabled) VALUES (%s, %s, 1, 0) '
                           'ON DUPLICATE KEY UPDATE active = 1, disabled = 0')
            assert params[0] == self.actor["guid"]
            self.writes.append(params)
            if not self.discard:
                self.spells[params[1]] = {'spell': params[1], 'active': 1, 'disabled': 0}


def replay_main_preparation(tmp_path, monkeypatch, db, *, pool_tags=None, dry_run=False, runtime_pool="all_spec_candidate_pool", transport="process", catalog_path=TARGETS):
    # Extract the unchanged actual main preparation statements, including its
    # flag predicates and call ordering. No hand-written dispatch surrogate.
    source = inspect.getsource(live.main)
    start = source.index('\n', source.index('    scenario_reports =', source.index('    preparation:'))) + 1
    end = source.index('    if validation_route and ', start)
    import textwrap
    branch = textwrap.dedent(source[start:end])
    order = []
    def connect(_):
        db.connections += 1
        return db
    monkeypatch.setattr(live, 'connect_mysql', connect)
    monkeypatch.setattr(live, 'database_url_from_worldserver_conf', lambda *_: 'mysql://fixture/characters')
    db.preparation_order = order
    namespace = dict(vars(live))
    namespace.update(
        args=SimpleNamespace(reset_bot_pool=True, calibration_only=True,
            calibration_self_provided_baseline=True, transport=transport, dry_run=dry_run,
            output_dir=tmp_path, config=tmp_path/'world.conf',
            calibration_target_spec=db.spec, all_spec_target_catalog=catalog_path,
            keep_bot_pool_position=False, keep_bot_pool_quests=False, keep_bot_pool_memory=False,
            apply_validation_provisioning=False),
        pool_tag_filter=runtime_pool, preparation={}, bot_pool_tags=['all_spec_candidate_pool'] if pool_tags is None else pool_tags,
        prepare_bot_pool_reset=lambda *a, **k: order.append('reset') or {},
        prepare_calibration_consumables=lambda *a, **k: order.append('consumables') or {},
        prepare_validation_provisioning=lambda *a, **k: pytest.fail('full provisioning forbidden'),
    )
    exec(compile(branch, str(ROOT/'tools/bot_ml/run_live_bot_validation.py'), 'exec'), namespace)
    assert order == (['reset'] if transport == 'session' else ['reset', 'consumables'])
    return namespace['preparation']


def expected_spells(tmp_path):
    return live.prepare_calibration_known_spells(tmp_path, tmp_path/'world.conf', 'fire_mage', TARGETS, pool_tag='all_spec_candidate_pool')['expected_spell_ids']


def test_session_keeps_its_separate_provisioning_owner(tmp_path, monkeypatch):
    db = Database([])
    result = replay_main_preparation(
        tmp_path, monkeypatch, db, pool_tags=['session_owned_pool'],
        runtime_pool='session_owned_pool', transport='session',
    )
    assert 'calibration_known_spells' not in result
    assert db.writes == []
    assert db.commits == db.rollbacks == 0


@pytest.mark.parametrize('prior', ['missing', 'inactive', 'disabled'])
def test_actual_reset_only_calibration_launch_repairs_existing_actor(tmp_path, monkeypatch, prior):
    spells = expected_spells(tmp_path)
    assert 89744 in spells
    db = Database(spells)
    if prior == 'missing': del db.spells[89744]
    else: db.spells[89744]['active' if prior == 'inactive' else 'disabled'] = 0 if prior == 'inactive' else 1
    report = replay_main_preparation(tmp_path, monkeypatch, db)
    assert db.writes == [(1304, 89744)]
    assert db.commits == 1 and not db.rollbacks
    assert report['calibration_known_spells']['readback']['passed']
    replay_main_preparation(tmp_path, monkeypatch, db)
    assert db.writes == [(1304, 89744)]  # repeated launch adds no duplicate work


@pytest.mark.parametrize('guard', ['online', 'in_use', 'disabled_pool', 'wrong_native_class', 'failed_readback'])
def test_selected_spellbook_preparation_fails_closed(tmp_path, monkeypatch, guard):
    db = Database([s for s in expected_spells(tmp_path) if s != 89744],
        online=int(guard=='online'), in_use=int(guard=='in_use'),
        enabled=int(guard!='disabled_pool'), discard=guard=='failed_readback')
    if guard == 'wrong_native_class': db.actor['class'] = 9
    monkeypatch.setattr(live, 'connect_mysql', lambda _: db)
    monkeypatch.setattr(live, 'database_url_from_worldserver_conf', lambda *_: 'mysql://fixture/characters')
    with pytest.raises(RuntimeError):
        live.prepare_calibration_known_spells(tmp_path, tmp_path/'world.conf', 'fire_mage', TARGETS, apply=True, pool_tag='all_spec_candidate_pool')
    assert db.commits == 0 and db.rollbacks == 1
    if guard != 'failed_readback': assert not db.writes


def test_inconsistent_canonical_class_rejects_before_database(tmp_path, monkeypatch):
    import json
    catalog = json.loads(TARGETS.read_text())
    target = next(row for row in catalog['targets'] if row['spec_target_id'] == 'fire_mage')
    target['provisioning_bot']['class'] = 9
    path = tmp_path/'targets.json'
    path.write_text(json.dumps(catalog))
    monkeypatch.setattr(live, 'connect_mysql', lambda _: pytest.fail('invalid catalog must not open a transaction'))
    with pytest.raises(RuntimeError, match='target/provisioning class mismatch'):
        live.prepare_calibration_known_spells(tmp_path, tmp_path/'world.conf', 'fire_mage', path, apply=True, pool_tag='all_spec_candidate_pool')


def test_inconsistent_provisioning_spec_rejects_before_database(tmp_path, monkeypatch):
    import json
    catalog = json.loads(TARGETS.read_text())
    target = next(row for row in catalog['targets'] if row['spec_target_id'] == 'fire_mage')
    target['provisioning_bot']['class_spec'] = 'frost_mage'
    path = tmp_path/'targets.json'
    path.write_text(json.dumps(catalog))
    monkeypatch.setattr(live, 'connect_mysql', lambda _: pytest.fail('invalid spec must not open a transaction'))
    monkeypatch.setattr(live, 'bot_known_spell_ids', lambda *_: pytest.fail('invalid spec must not select spells'))
    with pytest.raises(RuntimeError, match='target/provisioning spec mismatch'):
        live.prepare_calibration_known_spells(tmp_path, tmp_path/'world.conf', 'fire_mage', path, apply=True, pool_tag='all_spec_candidate_pool')


@pytest.mark.parametrize('pool_tags', [['foreign_pool'], ['all_spec_candidate_pool', 'foreign_pool'], []])
@pytest.mark.parametrize('dry_run', [False, True])
def test_actual_main_rejects_pool_before_any_reset_or_spell_write(tmp_path, monkeypatch, pool_tags, dry_run):
    db = Database([])
    with pytest.raises(RuntimeError, match='exactly the canonical candidate pool'):
        replay_main_preparation(tmp_path, monkeypatch, db, pool_tags=pool_tags, dry_run=dry_run)
    assert db.preparation_order == []
    assert db.writes == [] and db.commits == 0


def test_actual_main_rejects_runtime_pool_override_before_reset(tmp_path, monkeypatch):
    db = Database([])
    with pytest.raises(RuntimeError, match='runtime pool differs'):
        replay_main_preparation(tmp_path, monkeypatch, db, runtime_pool='foreign_scenario')
    assert db.preparation_order == [] and db.writes == []


@pytest.mark.parametrize('prior', [{}, {197: {'skill': 197, 'value': 1, 'max': 525}},
                                  {197: {'skill': 197, 'value': 525, 'max': 600}}])
def test_actual_affliction_launch_reconciles_profession_and_is_idempotent(tmp_path, monkeypatch, prior):
    db = Database([], spec='affliction_warlock', skills=prior)
    result = replay_main_preparation(tmp_path, monkeypatch, db)['calibration_known_spells']
    assert db.skill_writes == [(1306, 197, 525, 525)]
    assert result['character_guid'] == 1306 and result['character_class'] == 9
    assert result['expected_profession_skills'] == [{'id': 197, 'value': 525, 'max': 525}]
    assert result['profession_skills_readback'] == [{'skill': 197, 'value': 525, 'max': 525}]
    assert len(result['profession_setup_sha256']) == len(result['profession_equipment_sha256']) == 64
    assert len(result['profession_skills_readback_sha256']) == 64
    again = replay_main_preparation(tmp_path, monkeypatch, db)['calibration_known_spells']
    assert again['reconciled_profession_skills'] == []
    assert db.skill_writes == [(1306, 197, 525, 525)]


def test_profession_readback_failure_rolls_back_spell_and_skill_transaction(tmp_path, monkeypatch):
    db = Database([], spec='affliction_warlock', skills={}, discard_skills=True)
    with pytest.raises(RuntimeError, match='profession skill readback failed'):
        replay_main_preparation(tmp_path, monkeypatch, db)
    assert db.writes and db.skill_writes
    assert db.spells == {} and db.skills == {}
    assert db.rollbacks == 1 and db.commits == 0
    assert not (tmp_path/'calibration_known_spells.json').exists()


def test_affliction_dry_run_and_session_do_not_mutate_professions(tmp_path, monkeypatch):
    for options in [{'dry_run': True}, {'transport': 'session'}]:
        db = Database([], spec='affliction_warlock', skills={})
        replay_main_preparation(tmp_path, monkeypatch, db, **options)
        assert not db.writes and not db.skill_writes and not db.commits


def mutated_catalog(tmp_path, mutate):
    catalog = json.loads(TARGETS.read_text())
    bot = next(t['provisioning_bot'] for t in catalog['targets'] if t['spec_target_id'] == 'fire_mage')
    mutate(bot)
    path = tmp_path/'targets.json'
    path.write_text(json.dumps(catalog))
    (tmp_path/'cata_434_action_profiles.json').write_bytes((TARGETS.parent/'cata_434_action_profiles.json').read_bytes())
    return path


def test_fire_without_required_professions_keeps_skill_rows_unchanged(tmp_path, monkeypatch):
    def without_professions(bot):
        bot['profession_equipment'] = []
        bot['profession_setup'] = {'requirements': [], 'wowsims_professions': ['ProfessionUnknown', 'ProfessionUnknown']}
    path = mutated_catalog(tmp_path, without_professions)
    db = Database(expected_spells(tmp_path))
    before = copy.deepcopy(db.skills)
    result = replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path)['calibration_known_spells']
    assert result['expected_profession_skills'] == []
    assert not db.skill_writes and not db.writes and db.skills == before


@pytest.mark.parametrize('mutation', [
    lambda b: b.pop('profession_setup'),
    lambda b: b.pop('profession_equipment'),
    lambda b: b['profession_setup'].update(requirements=[]),
    lambda b: b['profession_setup']['requirements'][0].update(native_skill_id=999),
    lambda b: b['profession_setup']['requirements'][0].update(provisioned_value=500),
    lambda b: b['profession_setup']['requirements'][0].update(provisioned_max=600),
    lambda b: b['profession_setup']['requirements'][0].update(source_enchant_ids=[]),
])
@pytest.mark.parametrize('dry_run', [False, True])
def test_invalid_profession_requirements_main_rejects_before_any_mutation(tmp_path, monkeypatch, mutation, dry_run):
    path = mutated_catalog(tmp_path, mutation)
    db = Database([])
    with pytest.raises(ValueError):
        replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path, dry_run=dry_run)
    assert db.preparation_order == []
    assert db.connections == 0
    assert not db.writes and not db.skill_writes
    assert db.commits == db.rollbacks == 0


def test_profession_outside_frozen_authority_rejects_before_mutation(tmp_path, monkeypatch):
    catalog = json.loads(TARGETS.read_text())
    enhancement = next(t['provisioning_bot'] for t in catalog['targets'] if t['spec_target_id'] == 'enhancement_shaman')
    def leatherworking(bot):
        bot['profession_setup'] = enhancement['profession_setup']
        bot['profession_equipment'] = enhancement['profession_equipment']
    path = mutated_catalog(tmp_path, leatherworking)
    db = Database(expected_spells(tmp_path), skills={})
    with pytest.raises(ValueError, match='unknown permanent enchant: 4190'):
        replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path)
    assert db.connections == 0 and not db.skill_writes and not db.writes



@pytest.mark.parametrize('dry_run', [False, True])
def test_actual_both_absent_canonical_target_main_preserves_no_profession_path(tmp_path, monkeypatch, dry_run):
    spec = 'beast_mastery_hunter'
    target = next(t for t in json.loads(TARGETS.read_text())['targets'] if t['spec_target_id'] == spec)
    assert 'profession_setup' not in target['provisioning_bot']
    assert 'profession_equipment' not in target['provisioning_bot']
    db = Database([], spec=spec)
    before = copy.deepcopy(db.skills)
    result = replay_main_preparation(tmp_path, monkeypatch, db, dry_run=dry_run)['calibration_known_spells']
    assert result['expected_profession_skills'] == []
    assert db.skills == before and not db.skill_writes
    assert db.connections == int(not dry_run)
    if not dry_run:
        assert db.writes and result['readback']['passed']
        assert result['profession_skills_readback'] == []
        assert db.commits == 1 and not db.rollbacks


def test_session_does_not_add_profession_preflight_owner(tmp_path, monkeypatch):
    path = mutated_catalog(tmp_path, lambda bot: bot.pop('profession_setup'))
    db = Database([])
    result = replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path, transport='session')
    assert 'calibration_known_spells' not in result
    assert db.connections == 0 and not db.skill_writes


@pytest.mark.parametrize('spec', sorted(load_materialized_fixture_contract()[0]['specs']))
def test_every_frozen_cohort_target_passes_readonly_preflight(tmp_path, monkeypatch, spec):
    monkeypatch.setattr(live, 'connect_mysql', lambda _: pytest.fail('preflight connected to database'))
    monkeypatch.setattr(live, 'database_url_from_worldserver_conf',
                        lambda *_: pytest.fail('preflight resolved database configuration'))
    (tmp_path / "world.conf").write_text(f'DataDir = "{ROOT / "data"}"\n')
    result = live.prepare_calibration_known_spells(
        tmp_path, tmp_path/'world.conf', spec, TARGETS,
        apply=False, pool_tag='all_spec_candidate_pool',
    )
    assert result['target_spec'] == spec and result['applied'] is False


class SocketDatabase(Database):
    def __init__(self, spells, item_rows, *, discard_items=False):
        super().__init__(spells, skills={})
        self.actor.update(guid=1294, **{'class': 3})
        self.spec, self.name = 'marksmanship_hunter', 'Markshunter'
        self.items = copy.deepcopy(item_rows)
        self.original_items = copy.deepcopy(item_rows)
        self.item_writes = []
        self.discard_items = discard_items
    def execute(self, sql, params):
        if sql.startswith('SELECT ci.slot'):
            assert params == (1294, 8, 9)
            assert 'ci.bag = 0' in sql and 'FOR UPDATE' in sql
            self.rows = copy.deepcopy(self.items)
        elif sql.startswith('UPDATE item_instance'):
            fields, item_guid, owner = params
            assert owner == 1294
            self.item_writes.append(params)
            if not self.discard_items:
                next(row for row in self.items if row['item_guid'] == item_guid)['enchantments'] = fields
        else:
            super().execute(sql, params)
    def rollback(self):
        super().rollback()
        self.items = copy.deepcopy(self.original_items)


def dps011_preparation_fixture(tmp_path):
    (tmp_path / "world.conf").write_text(f'DataDir = "{ROOT / "data"}"\n')
    from test_profession_enchant_setup import dps011_corrected_documents
    from tools.bot_ml.build_validation_provisioning import load_gear_profiles
    paths, catalog, _ = dps011_corrected_documents(tmp_path)
    target = next(row for row in catalog['targets'] if row['spec_target_id'] == 'marksmanship_hunter')
    items = load_gear_profiles(paths[1])[target['gear_profile_id']]['equipment']
    rows = []
    for item in items:
        if item['slot'] not in (8, 9):
            continue
        fields = item['enchantments'].split()
        fields[18] = '0'
        rows.append(dict(slot=item['slot'], item_guid=90000+item['slot'], item_entry=item['item_id'],
                         owner_guid=1294, enchantments=' '.join(fields)))
    expected = live.prepare_calibration_known_spells(tmp_path, tmp_path/'world.conf', 'marksmanship_hunter',
        paths[0], pool_tag='all_spec_candidate_pool')
    return paths[0], target, rows, expected


def test_dps011_actual_main_repairs_socket_items_and_skill_atomically_then_noop(tmp_path, monkeypatch):
    path, target, rows, expected = dps011_preparation_fixture(tmp_path)
    db = SocketDatabase(expected['expected_spell_ids'], rows)
    db.name = target['provisioning_bot']['name']
    report = replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path)['calibration_known_spells']
    assert db.commits == 1 and not db.rollbacks
    assert db.skill_writes == [(1294, 164, 525, 525)]
    assert report['reconciled_socket_item_guids'] == [90008, 90009]
    assert [int(row['enchantments'].split()[18]) for row in report['socket_items_readback']] == [3717, 3723]
    assert len(report['socket_items_readback_sha256']) == 64
    assert all(report['readback'][key] for key in ('passed', 'profession_skills_passed', 'socket_items_passed'))
    again = replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path)['calibration_known_spells']
    assert again['reconciled_socket_item_guids'] == again['reconciled_profession_skills'] == []
    assert len(db.item_writes) == 2 and len(db.skill_writes) == 1


@pytest.mark.parametrize('failure', ['owner', 'entry', 'duplicate', 'missing', 'other_field', 'item_readback', 'skill_readback'])
def test_dps011_item_identity_and_combined_readback_fail_closed(tmp_path, monkeypatch, failure):
    path, target, rows, expected = dps011_preparation_fixture(tmp_path)
    if failure == 'owner': rows[0]['owner_guid'] = 99
    if failure == 'entry': rows[0]['item_entry'] = 1
    if failure == 'duplicate': rows[1]['item_guid'] = rows[0]['item_guid']
    if failure == 'missing': rows.pop()
    if failure == 'other_field':
        fields = rows[0]['enchantments'].split(); fields[0] = '1'; rows[0]['enchantments'] = ' '.join(fields)
    db = SocketDatabase([], rows, discard_items=failure == 'item_readback')
    db.name = target['provisioning_bot']['name']
    db.discard_skills = failure == 'skill_readback'
    with pytest.raises(RuntimeError):
        replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path)
    assert db.commits == 0 and db.rollbacks == 1
    assert db.items == rows and db.spells == {} and db.skills == {}
    if failure not in ('item_readback', 'skill_readback'):
        assert not db.item_writes and not db.writes and not db.skill_writes


def test_dps011_profile_drift_preflight_has_no_database_or_reset(tmp_path, monkeypatch):
    path, target, rows, _ = dps011_preparation_fixture(tmp_path)
    catalog = json.loads(path.read_text())
    next(row for row in catalog['targets'] if row['spec_target_id'] == 'marksmanship_hunter')['provisioning_bot']['profession_equipment'][0]['id'] = 1
    path.write_text(json.dumps(catalog))
    db = SocketDatabase([], rows)
    db.name = target['provisioning_bot']['name']
    with pytest.raises(ValueError):
        replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path)
    assert db.preparation_order == [] and db.connections == 0 and not db.item_writes


def test_dps011_dry_run_socket_plan_has_no_database_access(tmp_path, monkeypatch):
    path, target, rows, _ = dps011_preparation_fixture(tmp_path)
    db = SocketDatabase([], rows); db.name = target['provisioning_bot']['name']
    result = replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path, dry_run=True)['calibration_known_spells']
    assert len(result['expected_socket_items']) == 2
    assert not db.connections and not db.item_writes and not db.skill_writes and not db.writes


def test_dps011_correct_creators_with_native_trailing_separator_are_noop(tmp_path, monkeypatch):
    path, target, rows, expected = dps011_preparation_fixture(tmp_path)
    by_slot = {item['slot']: item for item in expected['expected_socket_items']}
    for row in rows:
        row['enchantments'] = by_slot[row['slot']]['enchantments'] + ' '
    db = SocketDatabase(expected['expected_spell_ids'], rows)
    db.name = target['provisioning_bot']['name']
    db.skills = {164: {'skill': 164, 'value': 525, 'max': 525}}
    report = replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path)['calibration_known_spells']
    assert not db.item_writes and not db.skill_writes and not db.writes
    assert report['socket_items_readback'] == rows


def test_dps011_profile_manifest_hash_drift_rejects_before_reset(tmp_path, monkeypatch):
    path, target, rows, _ = dps011_preparation_fixture(tmp_path)
    profile_path = tmp_path/'wowsims_cata_p4_gear_profiles.json'
    profiles = json.loads(profile_path.read_text())
    profiles['profiles'][target['gear_profile_id']]['transformed_manifest_sha256'] = '0' * 64
    profile_path.write_text(json.dumps(profiles))
    db = SocketDatabase([], rows); db.name = target['provisioning_bot']['name']
    with pytest.raises(ValueError, match='manifest hash mismatch'):
        replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path)
    assert db.connections == 0 and db.preparation_order == []


def test_dps011_missing_both_profession_fields_cannot_hide_profile_socket_requirement(tmp_path, monkeypatch):
    path, target, rows, _ = dps011_preparation_fixture(tmp_path)
    catalog = json.loads(path.read_text())
    bot = next(row for row in catalog['targets'] if row['spec_target_id'] == 'marksmanship_hunter')['provisioning_bot']
    bot.pop('profession_setup'); bot.pop('profession_equipment')
    path.write_text(json.dumps(catalog))
    db = SocketDatabase([], rows); db.name = target['provisioning_bot']['name']
    with pytest.raises(ValueError, match='profile/catalog equipment mismatch'):
        replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path)
    assert db.connections == 0 and db.preparation_order == []


@pytest.mark.parametrize('dry_run', [True, False])
def test_frozen_socket_preparation_uses_validated_authority_without_ambient_data(tmp_path, monkeypatch, dry_run):
    from tools.bot_ml import wowsims_gear_binding as binding
    from tools.bot_ml import build_validation_provisioning as provisioning
    from tools.bot_ml.phase8_fixture_contract import load_materialized_fixture_contract
    path, target, rows, expected = dps011_preparation_fixture(tmp_path)
    contract, digest = load_materialized_fixture_contract()
    def forbidden(*args, **kwargs):
        pytest.fail('frozen preparation attempted ambient DBC access')
    monkeypatch.setattr(binding, 'native_socket_authority', forbidden)
    monkeypatch.setattr(binding, 'profession_enchant_rows', forbidden)
    monkeypatch.setattr(binding, 'load_wdbc', forbidden)
    for loader in ('gem_item_enchant_map', 'item_socket_metadata', 'gem_enchant_color_map'):
        original = getattr(provisioning, loader)
        def bound_reader(dbc_dir=None, *, original=original):
            assert dbc_dir == ROOT / 'data/dbc/enUS'
            return original(dbc_dir)
        monkeypatch.setattr(provisioning, loader, bound_reader)
    monkeypatch.setattr(binding, 'REPO_ROOT', tmp_path / 'frozen_without_data')
    db = SocketDatabase(expected['expected_spell_ids'], rows)
    db.name = target['provisioning_bot']['name']
    report = replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path,
                                     dry_run=dry_run)['calibration_known_spells']
    assert report['profession_fixture_contract_sha256'] == digest
    assert report['profession_socket_authority_sha256'] == contract['materialization']['profession_enchant_authority']['socket_authority']['content_sha256']
    assert len(report['expected_socket_items']) == 2
    if dry_run:
        assert not db.connections and not db.item_writes and not db.skill_writes
    else:
        assert db.commits == 1 and not db.rollbacks
        assert db.skill_writes == [(1294, 164, 525, 525)]
        assert all(report['readback'][key] for key in ('passed', 'profession_skills_passed', 'socket_items_passed'))


@pytest.mark.parametrize('damage', ['missing', 'wrong_hash'])
def test_configured_socket_data_rejects_before_database_access(tmp_path, monkeypatch, damage):
    path, target, rows, _ = dps011_preparation_fixture(tmp_path)
    data = tmp_path / 'configured_data'
    dbc = data / 'dbc/enUS'
    dbc.mkdir(parents=True)
    if damage == 'wrong_hash':
        (dbc / 'Item-sparse.db2').write_bytes(b'wrong client data')
    # Exercise the existing config-relative DataDir parser.
    (tmp_path / 'world.conf').write_text('DataDir = "configured_data"\n')
    db = SocketDatabase([], rows)
    db.name = target['provisioning_bot']['name']
    with pytest.raises(ValueError, match='configured socket data'):
        replay_main_preparation(tmp_path, monkeypatch, db, catalog_path=path)
    assert db.connections == 0 and not db.preparation_order


@pytest.mark.parametrize('spec', [
    spec for spec, row in load_materialized_fixture_contract()[0]['materialization']['live_target_catalog']['selected_rows'].items()
    if any(requirement.get('socket_creators') for requirement in
           row['provisioning_bot'].get('profession_setup', {}).get('requirements', []))
])
def test_selected_frozen_socket_materialization_preserves_all_native_enchantment_fields(tmp_path, spec):
    from tools.bot_ml.build_validation_provisioning import load_gear_profiles
    catalog = json.loads(TARGETS.read_text())
    target = next(row for row in catalog['targets'] if row['spec_target_id'] == spec)
    profiles = TARGETS.parent / 'wowsims_cata_p4_gear_profiles.json'
    profile_id = target['gear_profile_id']
    canonical = load_gear_profiles(profiles)[profile_id]['equipment']
    (tmp_path / 'world.conf').write_text(f'DataDir = "{ROOT / "data"}"\n')
    report = live.prepare_calibration_known_spells(tmp_path, tmp_path/'world.conf', spec,
        TARGETS, pool_tag='all_spec_candidate_pool')
    expected = {row['slot']: row for row in canonical}
    assert len(report['expected_socket_items']) == 2
    for item in report['expected_socket_items']:
        assert item == {'slot': item['slot'], 'item_entry': expected[item['slot']]['item_id'],
                        'enchantments': expected[item['slot']]['enchantments']}
        assert len(item['enchantments'].split()) == 45
    assert set(report['runtime_socket_data']['source_sha256']) == {
        'Item-sparse.db2', 'SpellItemEnchantment.dbc', 'GemProperties.dbc'}
