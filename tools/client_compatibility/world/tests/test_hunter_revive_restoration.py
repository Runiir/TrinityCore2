"""Replay UI168's living maximum change and authoritative cleanup Focus."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.client_compatibility import lab_runtime as lab
from tools.client_compatibility import interaction_hunter_revive as controller
from tools.client_compatibility.hunter_revive_lifecycle import RevivePresence
from tools.client_compatibility.hunter_revive_restoration import focus_identity, living_snapshot, restored_maximum
from tools.client_compatibility.world.objects import INDEX


TRACE = json.loads((Path(__file__).parent / 'fixtures/hunter_revive_restoration_ui168.json').read_text())


@pytest.fixture
def native_restoration(tmp_path, monkeypatch):
    monkeypatch.setattr(lab, 'ROOT', tmp_path)
    journal = tmp_path / 'evidence/world_packets.jsonl'
    journal.parent.mkdir()
    journal.write_text(''.join(json.dumps(p) + '\n' for p in TRACE['packets'] if p['time'] < TRACE['cast_started_at']))
    oracle = RevivePresence(TRACE['session'], 6, TRACE['entry_started_at']).poll()
    baseline = controller.hunter_vitals(oracle)
    dead = deepcopy(oracle.pet)
    remaining = [p for p in TRACE['packets'] if p['time'] >= TRACE['cast_started_at']]
    def through(until):
        with journal.open('a') as handle:
            while remaining and remaining[0]['time'] <= until:
                handle.write(json.dumps(remaining.pop(0)) + '\n')
        return oracle.poll()
    through(TRACE['capture_at'])
    return oracle, baseline, dead, through


def test_actual_dynamic_max_rest_then_cleanup_preserves_native_focus_guard(native_restoration, monkeypatch):
    oracle, baseline, dead, through = native_restoration
    capture = deepcopy(oracle.pet)
    clock = {'now': TRACE['capture_at']}
    actions = []
    trial = SimpleNamespace(receipt={}, persist=lambda: None, clean_panels=lambda: None)
    monkeypatch.setattr(controller.time, 'time', lambda: clock['now'])
    monkeypatch.setattr(controller.time, 'monotonic', lambda: clock['now'])
    def sleep(seconds):
        clock['now'] += seconds
        through(clock['now'])
    monkeypatch.setattr(controller.time, 'sleep', sleep)
    assert focus_identity(oracle, TRACE['class_power_rows'], TRACE['dbc_source'])['power_index'] == 0
    assert controller.rest_living_pet(trial, oracle, TRACE['pet_guid'], baseline) == 278
    assert [r['max_health'] for r in oracle.pet_max_health_updates] == [198, 207, 278]
    assert oracle.pet['fields'][INDEX['UNIT_FIELD_HEALTH']] == 278
    # Normal rest must not gate mandatory clear-target on the bridge's stale
    # object Focus69; full Focus is established by the actual later packet.
    assert controller.hunter_vitals(oracle)['UNIT_FIELD_POWER1'] == 69
    assert controller.hunter_vitals(oracle) != baseline
    def execute(action):
        assert action == {'kind': 'chat', 'value': '/cleartarget'}
        assert controller.hunter_vitals(oracle)['UNIT_FIELD_POWER1'] == 69
        actions.append(action['value'])
        clock['now'] = TRACE['cleared_at']
        through(clock['now'])
    trial.execute = execute
    trial.observe = lambda label: ({'target': {'exists': False}}, {'file': label + '.png'})
    monkeypatch.setattr(controller, 'read_page', lambda *args: None)
    state, _ = controller.clear_restored_target(trial)
    assert actions == ['/cleartarget'] and not state['target']['exists']
    assert controller.hunter_vitals(oracle) == baseline
    maximum, source = restored_maximum(oracle, TRACE['pet_guid'])
    assert maximum == 278 and source['packet']['time'] == 1791398588.6974256
    assert living_snapshot(oracle, TRACE['pet_guid'], baseline)['full_health']
    assert dead['fields'].get(INDEX['UNIT_FIELD_HEALTH'], 0) == 0
    assert dead['fields'][INDEX['UNIT_FIELD_MAXHEALTH']] == 198
    assert capture['fields'][INDEX['UNIT_FIELD_HEALTH']] == 29
    assert capture['fields'][INDEX['UNIT_FIELD_MAXHEALTH']] == 198
    source['packet']['body'] = 'mutated local receipt'
    assert oracle.pet_max_health_updates[-1]['packet']['body'] != source['packet']['body']


@pytest.mark.parametrize('change', ['different_pet', 'removed_pet', 'not_full', 'maximum_differs',
    'missing_stat_source', 'foreign_stat_source', 'modern_stat_source'])
def test_final_full_maximum_requires_same_present_pet_and_actual_native_source(native_restoration, change):
    oracle, _, _, through = native_restoration
    through(TRACE['cleared_at'])
    if change == 'different_pet': oracle.pet['guid'] += 1
    elif change == 'removed_pet': oracle.removed.add(TRACE['pet_guid'])
    elif change == 'not_full': oracle.pet['fields'][INDEX['UNIT_FIELD_HEALTH']] = 277
    elif change == 'maximum_differs': oracle.pet['fields'][INDEX['UNIT_FIELD_MAXHEALTH']] = 279
    elif change == 'missing_stat_source': oracle.pet_max_health_updates.clear()
    elif change == 'foreign_stat_source': oracle.pet_max_health_updates[-1]['packet']['session'] = 'foreign'
    elif change == 'modern_stat_source': oracle.pet_max_health_updates[-1]['packet']['direction'] = 'from_client'
    with pytest.raises(RuntimeError, match='actual native stat update'):
        restored_maximum(oracle, TRACE['pet_guid'])


@pytest.mark.parametrize('change', ['changed_pet', 'changed_owner', 'overfull_pet', 'invalid_focus'])
def test_normal_rest_cannot_accept_actor_or_vital_drift(native_restoration, change):
    oracle, baseline, _, through = native_restoration
    through(TRACE['full_health_at'])
    if change == 'changed_pet': oracle.pet['fields'][INDEX['UNIT_FIELD_PETNUMBER']] = 17
    elif change == 'changed_owner': oracle.player[INDEX['UNIT_FIELD_HEALTH']] -= 1
    elif change == 'overfull_pet': oracle.pet['fields'][INDEX['UNIT_FIELD_HEALTH']] = 279
    elif change == 'invalid_focus': oracle.player[INDEX['UNIT_FIELD_POWER1']] = 101
    with pytest.raises(RuntimeError, match='changed during ordinary rest'):
        living_snapshot(oracle, TRACE['pet_guid'], baseline)


def test_elapsed_rest_cannot_substitute_for_native_full_health(native_restoration, monkeypatch):
    oracle, baseline, _, through = native_restoration
    through(1791398588.6974256)
    clock = {'now': 0}
    trial = SimpleNamespace(receipt={}, persist=lambda: None)
    monkeypatch.setattr(controller.time, 'time', lambda: clock['now'])
    monkeypatch.setattr(controller.time, 'monotonic', lambda: clock['now'])
    monkeypatch.setattr(controller.time, 'sleep', lambda seconds: clock.update(now=clock['now'] + seconds))
    with pytest.raises(RuntimeError, match='actual full living pet health'):
        controller.rest_living_pet(trial, oracle, TRACE['pet_guid'], baseline)
    assert 'quiet_rest_finished_at' not in trial.receipt
