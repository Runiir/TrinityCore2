"""Prevent the recorded expired corpse from reaching another Revive submission."""
from copy import deepcopy
import json
import struct
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.client_compatibility import lab_runtime as lab
from tools.client_compatibility import hunter_revive_lifecycle as lifecycle
from tools.client_compatibility import interaction_hunter_revive as controller
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.interaction_pet_command_probe import expected_guid


TRACE = json.loads((Path(__file__).parent / 'fixtures/hunter_revive_expiry_ui167.json').read_text())


@pytest.fixture
def native_corpse(tmp_path, monkeypatch):
    monkeypatch.setattr(lab, 'ROOT', tmp_path)
    path = tmp_path / 'evidence/world_packets.jsonl'
    path.parent.mkdir()
    packets = [p for p in TRACE['packets'] if p['time'] < 1791394497]
    path.write_text(''.join(json.dumps(p) + '\n' for p in packets))
    oracle = lifecycle.RevivePresence(TRACE['session'], 6, 1791394430).poll()
    lifecycle.bind_call_lifetime(oracle, TRACE['call_fixture_chat_setup_started_at'], TRACE['call_fixture_native_requests'])
    return oracle, path


def test_actual_failed_cast_was_already_too_old_at_chat_setup(native_corpse):
    oracle, _ = native_corpse
    assert oracle.present()
    budget = lifecycle.corpse_budget(oracle, TRACE['chat_setup_started_at'])
    assert budget['created_at'] == 1791394437.9178283
    assert budget['age_seconds'] == pytest.approx(53.2761929)
    assert not budget['setup_budget'] and not budget['submission_budget']
    assert budget['remaining_seconds'] < 6


def test_actual_destroy_cleared_owner_before_the_single_native_request(native_corpse):
    oracle, path = native_corpse
    with path.open('a') as handle:
        handle.write(''.join(json.dumps(p) + '\n' for p in TRACE['packets'] if p['time'] >= 1791394497))
    oracle.poll()
    assert not oracle.present()
    assert oracle.destructions[TRACE['pet_guid']]['time'] == 1791394497.0079226
    assert lifecycle.corpse_budget(oracle, TRACE['native_request_at'])['remaining_seconds'] < 0
    timing = lifecycle.native_revive_timing(TRACE['packets'], {'counter': 4}, TRACE['call_fixture_chat_setup_started_at'])
    assert timing['one_matching_start_and_completion'] and timing['native_ten_second_cast']
    assert timing['actual_cast_seconds'] == pytest.approx(10.0005589)
    assert not timing['completion_within_conservative_corpse_deadline']


def test_repeated_creation_and_pet_name_timestamp_never_restart_corpse_clock(native_corpse, monkeypatch):
    oracle, _ = native_corpse
    first = deepcopy(oracle.creations[oracle.pet['guid']])
    duplicate = deepcopy(first['object'])
    duplicate['fields'][INDEX['UNIT_FIELD_PET_NAME_TIMESTAMP']] = 1791394999
    monkeypatch.setattr(lifecycle, 'records', lambda body: [duplicate])
    oracle.inspect_packet({**first['packet'], 'time': first['packet']['time'] + 50})
    assert oracle.creations[oracle.pet['guid']] == first
    assert not lifecycle.corpse_budget(oracle, first['packet']['time'] + 50)['setup_budget']


@pytest.mark.parametrize('change', ('missing', 'foreign_session', 'modern', 'sparse', 'future', 'nonfinite', 'alive_creation'))
def test_unsupported_clock_or_creation_cannot_prove_budget(native_corpse, change):
    oracle, _ = native_corpse
    creation = oracle.creations[oracle.pet['guid']]
    if change == 'missing': oracle.creations.clear()
    elif change == 'foreign_session': creation['packet']['session'] = 'foreign'
    elif change == 'modern': creation['packet']['direction'] = 'from_client'
    elif change == 'sparse': creation['packet']['name'] = 'SMSG_SPELL_GO'
    elif change == 'future': creation['packet']['time'] += 100
    elif change == 'nonfinite': creation['packet']['time'] = float('nan')
    elif change == 'alive_creation': creation['object']['fields'][INDEX['UNIT_FIELD_HEALTH']] = 198
    with pytest.raises(RuntimeError, match='creation timing'):
        lifecycle.corpse_budget(oracle, 1791394440)


@pytest.mark.parametrize('basis,age,setup,submit', [('creation', 0, True, True), ('creation', 25, True, True),
    ('creation', 25.01, False, True), ('input', 44, False, True),
    ('input', 44.01, False, False), ('input', 59, False, False)])
def test_setup_and_final_return_have_separate_conservative_budgets(native_corpse, basis, age, setup, submit):
    oracle, _ = native_corpse
    created = oracle.creations[oracle.pet['guid']]['packet']['time']
    clock = created if basis == 'creation' else TRACE['call_fixture_chat_setup_started_at']
    budget = lifecycle.corpse_budget(oracle, clock + age)
    assert budget['setup_budget'] is setup and budget['submission_budget'] is submit


def test_slow_bridge_receipt_does_not_extend_native_lifetime(native_corpse):
    oracle, _ = native_corpse
    oracle.creations[oracle.pet['guid']]['packet']['time'] += 30
    budget = lifecycle.corpse_budget(oracle, TRACE['call_fixture_chat_setup_started_at'] + 45)
    assert budget['age_seconds'] < 25
    assert budget['remaining_seconds'] == 14
    assert not budget['setup_budget'] and not budget['submission_budget']


def test_unbound_login_creation_never_proves_a_submission_clock(native_corpse):
    oracle, _ = native_corpse
    oracle.lifetime_lower_bounds.clear()
    budget = lifecycle.corpse_budget(oracle, oracle.creations[oracle.pet['guid']]['packet']['time'])
    assert budget['native_present'] and budget['age_seconds'] == 0
    assert budget['remaining_seconds'] is None
    assert not budget['setup_budget'] and not budget['submission_budget']


@pytest.mark.parametrize('change', ('missing_request', 'foreign_request', 'late_setup', 'before_entry', 'not_call_creation'))
def test_fixture_clock_requires_earlier_bound_input_and_the_actual_native883(native_corpse, change):
    oracle, _ = native_corpse
    requests = deepcopy(TRACE['call_fixture_native_requests'])
    started = TRACE['call_fixture_chat_setup_started_at']
    if change == 'missing_request': requests.clear()
    elif change == 'foreign_request': requests[0]['session'] = 'foreign'
    elif change == 'late_setup': started = requests[0]['time'] + .1
    elif change == 'before_entry': started = oracle.started - .1
    elif change == 'not_call_creation': oracle.creations[oracle.pet['guid']]['object']['fields'][INDEX['UNIT_CREATED_BY_SPELL']] = 13481
    with pytest.raises(RuntimeError, match='earlier one-CallPet fixture clock'):
        lifecycle.bind_call_lifetime(oracle, started, requests)


def fake_trial():
    return SimpleNamespace(receipt={'baseline_resources': {}, 'input_sent': False, 'cast_input_sent': False}, persist=lambda: None)


def public_dead(oracle):
    return {'target': {'guid': expected_guid(oracle.pet), 'name': 'Wolf', 'health': 0}}


@pytest.mark.parametrize('change', ('none', 'expired', 'too_late', 'wrong_target', 'changed_owner', 'second_return'))
def test_final_return_cannot_submit_an_expired_or_changed_corpse(native_corpse, monkeypatch, change):
    oracle, _ = native_corpse
    trial = fake_trial()
    guid = oracle.pet['guid']
    state = public_dead(oracle)
    fields = oracle.player
    fields[INDEX['UNIT_FIELD_TARGET']], fields[INDEX['UNIT_FIELD_TARGET'] + 1] = guid & 0xffffffff, guid >> 32
    created = oracle.creations[guid]['packet']['time']
    monkeypatch.setattr(controller, 'guard_fixture', lambda *args: None)
    clock = TRACE['call_fixture_chat_setup_started_at']
    monkeypatch.setattr(controller.time, 'time', lambda: clock + (45 if change == 'too_late' else 43))
    if change == 'expired': oracle.removed.add(guid)
    elif change == 'wrong_target': state['target']['guid'] = 'Pet-foreign'
    elif change == 'changed_owner': fields[INDEX['UNIT_FIELD_TARGET']] = 0
    elif change == 'second_return': trial.receipt['input_sent'] = True
    if change != 'none':
        with pytest.raises(RuntimeError): controller.final_submission(trial, oracle, {}, {}, None, {}, guid, state)
        if change != 'second_return': assert not trial.receipt['input_sent'] and not trial.receipt['cast_input_sent']
    else:
        controller.final_submission(trial, oracle, {}, {}, None, {}, guid, state)
        assert trial.receipt['input_sent'] and trial.receipt['cast_input_sent']
        assert trial.receipt['final_submission_corpse_budget']['remaining_seconds'] == 16


def test_old_present_corpse_waits_without_input_then_loads_once(native_corpse, monkeypatch):
    oracle, _ = native_corpse
    trial = fake_trial()
    old_guid = oracle.pet['guid']
    old_created = oracle.creations[old_guid]['packet']['time']
    clock = {'now': old_created + 40}
    actions = []
    trial.execute = lambda action: actions.append(action)
    monkeypatch.setattr(controller.time, 'time', lambda: clock['now'])
    monkeypatch.setattr(controller.time, 'monotonic', lambda: clock['now'])
    def sleep(seconds):
        clock['now'] = old_created + 59.1
        oracle.removed.add(old_guid)
        oracle.player[INDEX['UNIT_FIELD_SUMMON']] = oracle.player[INDEX['UNIT_FIELD_SUMMON'] + 1] = 0
        oracle.destructions[old_guid] = {'time': clock['now']}
        assert actions == []
    monkeypatch.setattr(controller.time, 'sleep', sleep)
    monkeypatch.setattr(controller, 'guard_fixture', lambda *args: None)
    def load(t, o, session, fixture_guard=None):
        assert not o.present() and old_guid in o.removed
        actions.append('one CallPet fixture')
        pet = deepcopy(o.pet)
        pet['guid'] += 1
        o.pet = pet
        o.player[INDEX['UNIT_FIELD_SUMMON']], o.player[INDEX['UNIT_FIELD_SUMMON'] + 1] = pet['guid'] & 0xffffffff, pet['guid'] >> 32
        packet = {**o.creations[old_guid]['packet'], 'time': clock['now']}
        o.creations[pet['guid']] = {'packet': packet, 'object': deepcopy(pet)}
        o.lifetime_lower_bounds[pet['guid']] = {'started_at': clock['now'], 'source': 'mocked one ordinary CallPet fixture'}
    monkeypatch.setattr(controller, 'load_dead', load)
    monkeypatch.setattr(controller, 'ready', lambda t, o: (public_dead(o), {}))
    controller.prepare_cast_corpse(trial, oracle, oracle.session, {}, {}, None, {})
    assert actions == ['one CallPet fixture']
    assert trial.receipt['natural_corpse_expiry_wait']['inputs_sent'] is False
    assert trial.receipt['pre_chat_corpse_budget']['age_seconds'] == 0
    assert not trial.receipt['input_sent']


def test_call_fixture_rechecks_absence_immediately_before_its_one_return(native_corpse, monkeypatch):
    oracle, _ = native_corpse
    guid = oracle.pet['guid']
    oracle.removed.add(guid)
    oracle.player[INDEX['UNIT_FIELD_SUMMON']] = oracle.player[INDEX['UNIT_FIELD_SUMMON'] + 1] = 0
    trial = fake_trial()
    monkeypatch.setattr(controller, 'wire_known', lambda *args: {883})
    def execute(action, before_submit=None):
        assert action == {'kind': 'chat', 'value': '/cast Call Pet 1'}
        assert before_submit is not None
        # Another native summon arriving during chat setup cannot be dismissed
        # or replaced by the pending CallPet command.
        oracle.removed.discard(guid)
        oracle.player[INDEX['UNIT_FIELD_SUMMON']], oracle.player[INDEX['UNIT_FIELD_SUMMON'] + 1] = guid & 0xffffffff, guid >> 32
        before_submit({})
        pytest.fail('changed native absence must prevent the final Return')
    trial.execute = execute
    with pytest.raises(RuntimeError, match='no CallPet submitted'):
        controller.load_dead(trial, oracle, oracle.session)
    assert trial.receipt['call_dead_pet_input_sent'] is False


def test_one_absent_fixture_call_binds_its_earlier_setup_clock(native_corpse, monkeypatch):
    oracle, _ = native_corpse
    old_guid = oracle.pet['guid']
    oracle.removed.add(old_guid)
    oracle.player[INDEX['UNIT_FIELD_SUMMON']] = oracle.player[INDEX['UNIT_FIELD_SUMMON'] + 1] = 0
    trial = fake_trial()
    clock = {'now': 1791394500}
    actions = []
    request = {**TRACE['call_fixture_native_requests'][0], 'time': 1791394501}
    monkeypatch.setattr(controller.time, 'time', lambda: clock['now'])
    monkeypatch.setattr(controller, 'wire_known', lambda *args: {883})
    monkeypatch.setattr(controller, 'entries', lambda path: [request])
    def execute(action, before_submit=None):
        if action['value'] == '/cast Call Pet 1':
            assert before_submit is not None
            before_submit({})
            assert trial.receipt['call_dead_pet_input_sent'] is True
            assert not oracle.present()
            actions.append('one CallPet final Return')
            pet = deepcopy(oracle.pet)
            pet['guid'] += 1
            oracle.pet = pet
            oracle.player[INDEX['UNIT_FIELD_SUMMON']], oracle.player[INDEX['UNIT_FIELD_SUMMON'] + 1] = pet['guid'] & 0xffffffff, pet['guid'] >> 32
            oracle.call_requests.append(request)
            packet = {**oracle.creations[old_guid]['packet'], 'time': 1791394501.1}
            oracle.creations[pet['guid']] = {'packet': packet, 'object': deepcopy(pet)}
            clock['now'] = 1791394501.5
        else:
            assert action['value'] == '/targetexact Wolf' and before_submit is None
            actions.append('select fresh dead pet')
    trial.execute = execute
    controller.load_dead(trial, oracle, oracle.session)
    assert actions == ['one CallPet final Return', 'select fresh dead pet']
    assert oracle.lifetime_lower_bounds[oracle.pet['guid']]['started_at'] == 1791394500


def test_receipt_jitter_is_diagnostic_not_an_exact_native_cast_duration_requirement():
    packets = deepcopy(TRACE['packets'])
    start = next(p for p in packets if p['name'] == 'SMSG_SPELL_START' and p['time'] > 1791394498)
    go = next(p for p in packets if p['name'] == 'SMSG_SPELL_GO' and p['time'] > 1791394508)
    go['time'] = start['time'] + 9.999
    timing = lifecycle.native_revive_timing(packets, {'counter': 4}, TRACE['call_fixture_chat_setup_started_at'])
    assert timing['native_ten_second_cast'] and timing['native_completion_ordered']
    assert timing['actual_cast_seconds'] == pytest.approx(9.999)


def test_later_native_regeneration_cannot_rewrite_the_closed_outcome_window(native_corpse):
    oracle, path = native_corpse
    trial = fake_trial()
    guid = oracle.pet['guid']
    def append_health(health, at):
        octets = struct.pack('<Q', guid)
        packed_guid = bytes([sum(bool(v) << n for n, v in enumerate(octets))]) + bytes(v for v in octets if v)
        index = INDEX['UNIT_FIELD_HEALTH']
        masks = [0] * (index // 32 + 1)
        masks[index // 32] = 1 << (index % 32)
        body = struct.pack('<HIB', 0, 1, 0) + packed_guid + bytes([len(masks)]) + struct.pack('<' + 'I' * len(masks), *masks) + struct.pack('<I', health)
        packet = {'name': 'SMSG_UPDATE_OBJECT', 'direction': 'from_native', 'session': oracle.session, 'time': at, 'body': body.hex()}
        with path.open('a') as handle: handle.write(json.dumps(packet) + '\n')
        oracle.poll()
    append_health(120, 1791394480)
    controller.capture_outcome(trial, oracle, cast_finished_at=1791394480.5)
    append_health(198, 1791394482)
    assert oracle.pet['fields'][INDEX['UNIT_FIELD_HEALTH']] == 198
    assert trial.receipt['native_pet_after']['fields'][INDEX['UNIT_FIELD_HEALTH']] == 120
    assert trial.receipt['cast_finished_at'] == 1791394480.5


def test_fresh_present_corpse_never_sends_fixture_call(native_corpse, monkeypatch):
    oracle, _ = native_corpse
    trial = fake_trial()
    trial.execute = lambda action: pytest.fail('fresh present corpse requires no fixture input')
    created = oracle.creations[oracle.pet['guid']]['packet']['time']
    monkeypatch.setattr(controller.time, 'time', lambda: created + 10)
    monkeypatch.setattr(controller, 'guard_fixture', lambda *args: None)
    monkeypatch.setattr(controller, 'ready', lambda t, o: (public_dead(o), {}))
    controller.prepare_cast_corpse(trial, oracle, oracle.session, {}, {}, None, {})
    assert not trial.receipt['reviewed_same_pet_fixture_recovery']


def test_slow_readiness_fails_before_chat_without_reloading(native_corpse, monkeypatch):
    oracle, _ = native_corpse
    trial = fake_trial()
    trial.execute = lambda action: pytest.fail('no gameplay input before budget admission')
    created = oracle.creations[oracle.pet['guid']]['packet']['time']
    clock = {'now': created + 10}
    monkeypatch.setattr(controller.time, 'time', lambda: clock['now'])
    monkeypatch.setattr(controller, 'guard_fixture', lambda *args: None)
    def ready(t, o):
        clock['now'] += 20
        return public_dead(o), {}
    monkeypatch.setattr(controller, 'ready', ready)
    with pytest.raises(RuntimeError, match='readiness exhausted'):
        controller.prepare_cast_corpse(trial, oracle, oracle.session, {}, {}, None, {})
    assert not trial.receipt['input_sent']


@pytest.mark.parametrize('change', ('named_clock', 'named_health', 'wrong_disposable', 'renamed', 'health', 'creator', 'backward_clock'))
def test_named_or_disposable_saved_row_change_rejects_lifecycle_recovery(change):
    before = [dict(id=4, curhealth=278, savetime=100, CreatedBySpell=883, active=0, slot=5),
        dict(id=16, curhealth=278, savetime=200, CreatedBySpell=13481, active=1, slot=0, renamed=0)]
    current = deepcopy(before)
    current[1].update(curhealth=0, CreatedBySpell=883, active=0, savetime=201)
    fixture = {'before': {'6': {'pets': before}}}
    assert lifecycle.dead_pet_rows(fixture, current)
    if change == 'named_clock': current[0]['savetime'] += 1
    elif change == 'named_health': current[0]['curhealth'] = 0
    elif change == 'wrong_disposable': current[1]['id'] = 17
    elif change == 'renamed': current[1]['renamed'] = 1
    elif change == 'health': current[1]['curhealth'] = 1
    elif change == 'creator': current[1]['CreatedBySpell'] = 982
    elif change == 'backward_clock': current[1]['savetime'] = 199
    assert not lifecycle.dead_pet_rows(fixture, current)
