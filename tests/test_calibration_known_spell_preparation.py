"""Replay the actual process-runner preparation branch with an existing actor."""
import inspect
from pathlib import Path
from types import SimpleNamespace

import pytest
from tools.bot_ml import run_live_bot_validation as live

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT/'experiments/configs/all_spec_targets_cata_p4_v1.json'


class Database:
    def __init__(self, spells, *, online=0, in_use=0, enabled=1, discard=False):
        self.spells = {s: {'spell': s, 'active': 1, 'disabled': 0} for s in spells}
        self.actor = {'guid': 1304, 'class': 8, 'online': online, 'in_use': in_use, 'enabled': enabled}
        self.rows = []
        self.writes = []
        self.commits = self.rollbacks = 0
        self.discard = discard
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def close(self): pass
    def commit(self): self.commits += 1
    def rollback(self): self.rollbacks += 1
    def fetchall(self): return self.rows
    def execute(self, sql, params):
        if sql.startswith('SELECT c.guid'):
            assert params == ('Firemage', 'fire_mage', 'all_spec_candidate_pool')
            self.rows = [self.actor]
        elif sql.startswith('SELECT spell'):
            assert params == (1304,)
            self.rows = list(self.spells.values())
        else:
            assert sql == ('INSERT INTO character_spell (guid, spell, active, disabled) VALUES (%s, %s, 1, 0) '
                           'ON DUPLICATE KEY UPDATE active = 1, disabled = 0')
            assert params[0] == 1304
            self.writes.append(params)
            if not self.discard:
                self.spells[params[1]] = {'spell': params[1], 'active': 1, 'disabled': 0}


def replay_main_preparation(tmp_path, monkeypatch, db, *, pool_tags=None, dry_run=False, runtime_pool="all_spec_candidate_pool", transport="process"):
    # Extract the unchanged actual main preparation statements, including its
    # flag predicates and call ordering. No hand-written dispatch surrogate.
    source = inspect.getsource(live.main)
    start = source.index('\n', source.index('    scenario_reports =', source.index('    preparation:'))) + 1
    end = source.index('    if validation_route and ', start)
    import textwrap
    branch = textwrap.dedent(source[start:end])
    order = []
    monkeypatch.setattr(live, 'connect_mysql', lambda _: db)
    monkeypatch.setattr(live, 'database_url_from_worldserver_conf', lambda *_: 'mysql://fixture/characters')
    db.preparation_order = order
    namespace = dict(vars(live))
    namespace.update(
        args=SimpleNamespace(reset_bot_pool=True, calibration_only=True,
            calibration_self_provided_baseline=True, transport=transport, dry_run=dry_run,
            output_dir=tmp_path, config=tmp_path/'world.conf',
            calibration_target_spec='fire_mage', all_spec_target_catalog=TARGETS,
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
