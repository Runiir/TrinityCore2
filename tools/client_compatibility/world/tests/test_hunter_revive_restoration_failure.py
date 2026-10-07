"""The recorded max-health mismatch permits creator cleanup, never admission."""
from copy import deepcopy
from contextlib import nullcontext
import json
import struct
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.client_compatibility import hunter_revive_restoration_failure as failure
from tools.client_compatibility import interaction_hunter_revive_failed_close as closer
from tools.client_compatibility.hunter_revive_failed_fixture import validate_failed_cast, offline_restore
from tools.client_compatibility.hunter_revive_fixture import dead_snapshot
from tools.client_compatibility.interaction_hunter_revive_failed_normalize import restore_sql
from tools.client_compatibility.world.objects import INDEX


@pytest.fixture
def recorded():
    return json.loads((Path(__file__).parent / 'fixtures/hunter_revive_restoration_failed_ui168.json').read_text())


def test_exact_failed_cast_and_native_max_transition_remain_excluded(recorded):
    old = deepcopy(recorded)
    cast, packets = recorded['cast'], recorded['packets']
    proof = failure.proof(cast, packets)
    assert validate_failed_cast(cast, packets) is cast
    assert proof['pre_cast_max'] == 198 and proof['restored_max'] == 278
    assert proof['failed_cast_excluded'] is True and proof['qualification_added'] is False
    assert cast['completed'] is False and recorded == old


@pytest.mark.parametrize('key,value', [('failure', 'different failure'), ('completed', True), ('qualification_added', True),
    ('cast_input_sent', False), ('offline_fixture_normalization_pending', False), ('native_pet_max_health', 278),
    ('cases', []), ('model', 'model'), ('phase', 'owned_revive_cast_complete')])
def test_other_partial_or_successful_failure_shape_is_rejected(recorded, key, value):
    recorded['cast'][key] = value
    with pytest.raises(RuntimeError): failure.proof(recorded['cast'], recorded['packets'])


@pytest.mark.parametrize('key', sorted(failure.CAPTURE_KEYS))
def test_every_native_public_outcome_check_must_be_true(recorded, key):
    recorded['cast']['capture_checks'][key] = False
    with pytest.raises(RuntimeError): failure.proof(recorded['cast'], recorded['packets'])


@pytest.mark.parametrize('key', sorted(failure.RESTORATION_KEYS))
def test_the_single_restoration_failure_cannot_hide_another_loss(recorded, key):
    recorded['cast']['restoration_checks'][key] = key == 'living_disposable_pet'
    with pytest.raises(RuntimeError): failure.proof(recorded['cast'], recorded['packets'])


@pytest.mark.parametrize('name,key,value', [('native_pet_before', 'UNIT_FIELD_HEALTH', 1),
    ('native_pet_before', 'UNIT_FIELD_MAXHEALTH', 278), ('native_pet_after', 'UNIT_FIELD_HEALTH', 0),
    ('restored_native_pet', 'UNIT_FIELD_HEALTH', 277), ('restored_native_pet', 'UNIT_FIELD_MAXHEALTH', 198),
    ('restored_native_pet', 'UNIT_FIELD_PETNUMBER', 4), ('restored_native_pet', 'UNIT_CREATED_BY_SPELL', 13481)])
def test_raw_transition_cannot_reinterpret_another_pet_or_health_mismatch(recorded, name, key, value):
    recorded['cast'][name]['fields'][str(INDEX[key])] = value
    with pytest.raises(RuntimeError): failure.proof(recorded['cast'], recorded['packets'])


@pytest.mark.parametrize('fault', ['missing_max', 'missing_alive', 'duplicate', 'other_session', 'cast_failure',
    'cancel', 'missing_call', 'fake_budget', 'missing_prior_destruction'])
def test_actual_raw_packets_and_original_call_lifetime_are_required(recorded, fault):
    cast, packets = recorded['cast'], recorded['packets']
    proven = failure.proof(cast, packets)
    if fault == 'missing_max': packets.remove(proven['max_transition_packet'])
    elif fault == 'missing_alive': packets.remove(proven['alive_packet'])
    elif fault == 'duplicate': packets.append(deepcopy(packets[-1]))
    elif fault == 'other_session': packets[-1]['session'] = 'other'
    elif fault == 'cancel': packets.append({'time': cast['cast_started_at'] + 1, 'session': cast['native_session'],
        'name': 'CMSG_CANCEL_CAST', 'direction': 'from_client', 'body': ''})
    elif fault == 'cast_failure':
        packet = {'time': cast['cast_started_at'] + 1, 'session': cast['native_session'],
            'name': 'SMSG_CAST_FAILED', 'direction': 'from_native', 'body': '04d603000001'}
        packets.append(packet)
        cast['cast_packets'].append(deepcopy(packet))
    elif fault == 'missing_call': packets.remove(cast['final_submission_corpse_budget']['lifetime_source']['native_request'])
    elif fault == 'fake_budget': cast['final_submission_corpse_budget']['remaining_seconds'] += 1
    else: packets.remove(cast['final_submission_corpse_budget']['lifetime_source']['destruction_packet'])
    with pytest.raises(RuntimeError): failure.proof(cast, packets)


def offline(cast):
    rows = deepcopy(cast['retained_pet_after'])
    original = {str(n): {'native': {'online': 0}, 'pets': [], 'saved': {}, 'inventory': []} for n in range(1, 7)}
    original['6']['native'].update(guid=6, account=2, name='Harnesshunt', race=1, **{'class': 3}, level=10)
    original['6']['pets'] = deepcopy(rows)
    original['6']['pets'][1].update(CreatedBySpell=13481, savetime=rows[1]['savetime'] - 10)
    current = deepcopy(original)
    current['6']['pets'] = rows
    current['6']['pets'][1]['savetime'] += 20
    fixture = {'before': original, 'after': dead_snapshot(original)}
    park = {'retained_class_fixture': deepcopy(current['6']['native']),
        'retained_class_saved': deepcopy(current['6']['saved']), 'retained_class_pets': deepcopy(current['6']['pets'])}
    return current, fixture, park


def test_post_revive_cleanup_changes_creator_only_and_requires_the_actual_saved_capture(recorded):
    cast = recorded['cast']
    current, fixture, park = offline(cast)
    expected = offline_restore(current, fixture, park, cast=cast)
    diff = {k for k, v in expected['6']['pets'][1].items() if current['6']['pets'][1][k] != v}
    assert diff == {'CreatedBySpell'}
    assert expected['6']['pets'][0] == current['6']['pets'][0]
    captured = []
    cursor = SimpleNamespace(rowcount=1, execute=lambda sql, args: captured.append((sql, args)))
    restore_sql(cursor, current, expected)
    sql, args = captured[0]
    assert 'SET p.CreatedBySpell=%s WHERE' in sql and args[0] == 13481
    assert 'SET p.curhealth=' not in sql and 'SET p.active=' not in sql


@pytest.mark.parametrize('column,value', [('curhealth', 0), ('curhealth', 277), ('active', 0),
    ('CreatedBySpell', 982), ('slot', 5), ('savetime', 0), ('name', 'OtherWolf')])
def test_creator_cleanup_cannot_restore_another_dead_or_changed_offline_pet(recorded, column, value):
    cast = recorded['cast']
    current, fixture, park = offline(cast)
    current['6']['pets'][1][column] = value
    park['retained_class_pets'] = deepcopy(current['6']['pets'])
    with pytest.raises(RuntimeError): offline_restore(current, fixture, park, cast=cast)


def test_living_restoration_variant_cannot_use_the_old_dead_expiry_cleanup(recorded):
    current, fixture, park = offline(recorded['cast'])
    with pytest.raises(RuntimeError): offline_restore(current, fixture, park)


@pytest.mark.parametrize('name,direction,body', [('CMSG_CAST_SPELL', 'to_native', '04d6030000000000000000000000'),
    ('CMSG_CAST_SPELL', 'from_client', '01830482f5bc0000000000000000d6030000069d030000000000000000000000000000000000000000000000000000000000000000000000'),
    ('SMSG_CAST_FAILED', 'from_native', '04d603000001'), ('SMSG_SPELL_FAILURE', 'from_native', ''),
    ('SMSG_SPELL_FAILED_OTHER', 'from_native', '')])
def test_an_extra_request_or_failure_during_restoration_cannot_be_hidden(recorded, name, direction, body):
    cast = recorded['cast']
    recorded['packets'].append({'time': cast['cast_finished_at'] + 1, 'session': cast['native_session'],
        'name': name, 'direction': direction, 'body': body})
    with pytest.raises(RuntimeError): failure.proof(cast, recorded['packets'])


@pytest.mark.parametrize('name,body', [('SMSG_DESTROY_OBJECT', struct.pack('<Q', 6).hex()),
    ('SMSG_UPDATE_OBJECT', (struct.pack('<HI', 0, 1) + b'\x03' + struct.pack('<I', 1) + b'\x01\x06').hex())])
def test_owner_loss_cannot_leave_a_cached_full_owner_proof(recorded, name, body):
    cast = recorded['cast']
    recorded['packets'].append({'time': cast['cast_finished_at'] + 1, 'session': cast['native_session'],
        'name': name, 'direction': 'from_native', 'body': body})
    with pytest.raises(RuntimeError): failure.proof(cast, recorded['packets'])


@pytest.mark.parametrize('name', ['SMSG_SPELL_START', 'SMSG_SPELL_GO'])
def test_an_extra_native982_execution_during_restoration_is_rejected(recorded, name):
    cast = recorded['cast']
    timing_key = 'starts' if name == 'SMSG_SPELL_START' else 'completions'
    packet = next(p for p in cast['cast_packets'] if p['name'] == name and p['direction'] == 'from_native' and
        p['time'] == cast['native_cast_timing'][timing_key][0]['time'])
    packet = {**packet, 'time': cast['cast_finished_at'] + 1}
    recorded['packets'].append(packet)
    with pytest.raises(RuntimeError): failure.proof(cast, recorded['packets'])


def test_new_failed_boundary_closes_creator_only_cleanup_without_admission(tmp_path, monkeypatch, recorded):
    monkeypatch.setattr(closer.lab, 'ROOT', tmp_path)
    cast = recorded['cast']
    cast['runtime'] = {'worldserver': {'pid': 1}, 'modern_world': {'pid': 2}, 'client': {'pid': 3}}
    current, fixture, park = offline(cast)
    fixture['runtime'] = {k: cast['runtime'][k] for k in ('worldserver', 'modern_world')}
    for state in (fixture['before']['6']['native'], current['6']['native']):
        state.update(health=209, position_x=1, position_y=2, position_z=3, orientation=4, map=0)
    park['retained_class_fixture'] = deepcopy(current['6']['native'])
    expected = offline_restore(current, fixture, park, cast=cast)
    proof = failure.proof(cast, recorded['packets'])
    origin = {'guid': 2}
    old = {'origin_actor': origin}
    def write(name, value):
        path = tmp_path / 'evidence' / name / 'episode.json'
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(value))
        return path
    preparation = write('preparation', old)
    fixture_path = write('fixture', fixture)
    cast_path = write('cast', cast)
    park['finished_at'] = cast['finished_at'] + 2
    park_path = write('park', park)
    stop_path = write('stop', dict(completed=True, failure=None, finished_at=1,
        before=fixture['before']['1'], after=fixture['before']['1']))
    fixture['primary_stop_source'] = closer.bound(stop_path)
    finish_path = write('finish', dict(completed=True, failure=None, started_at=park['finished_at'] + 1,
        finished_at=park['finished_at'] + 2, runtime=cast['runtime'], actor=origin,
        fixture_source=closer.bound(preparation), checks={k: True for k in
            closer.ORIGIN_CHECKS | {'origin_registration', 'class_offline'}}))
    cleanup = dict(completed=True, failure=None, started_at=park['finished_at'] + 3, finished_at=park['finished_at'] + 4,
        schema='client442_failed_revive_offline_cleanup_v1', phase='owned_revive_restoration_failure_fixture_normalized',
        sources=[closer.bound(p) for p in (preparation, fixture_path, cast_path, park_path)],
        failed_cast_source=closer.bound(cast_path), failed_cast_excluded=True, qualification_added=False, input_sent=False,
        runtime=cast['runtime'], actor=cast['actor'], before=current, after=expected, expected_after=expected,
        post_revive_restoration_failure_proof=proof, failed_cast_variant=failure.VARIANT, normalized_columns=['CreatedBySpell'])
    cleanup_path = write('cleanup', cleanup)
    monkeypatch.setattr(closer, 'prepared', lambda *args: old)
    monkeypatch.setattr(closer, 'sources', lambda *args: (old, fixture, cast, park))
    monkeypatch.setattr(closer, 'snapshot', lambda: deepcopy(expected))
    monkeypatch.setattr(closer, 'shot', lambda *args: {'file': 'mocked_no_input.png'})
    monkeypatch.setattr(closer, 'actor', lambda *args: nullcontext())
    monkeypatch.setattr(closer.actors, 'load', lambda: origin)
    monkeypatch.setattr(closer.lab, 'owned_process', lambda *args: None)
    trial = SimpleNamespace(receipt={'runtime': cast['runtime']}, out=tmp_path)
    original_failed = cast_path.read_bytes()
    closer.close(trial, preparation, fixture_path, cast_path, park_path, finish_path, cleanup_path)
    assert trial.receipt['phase'] == 'owned_revive_restoration_failed_parked_boundary'
    assert trial.receipt['completed'] is True and len(trial.receipt['checks']) == 21
    assert trial.receipt['qualification_added'] is False and trial.receipt['failed_cast_excluded'] is True
    assert cast_path.read_bytes() == original_failed
