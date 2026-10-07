"""A failed cast cannot qualify; cleanup can restore only the exact dead fixture."""
from copy import deepcopy
from contextlib import nullcontext
import json
from types import SimpleNamespace
import pytest
from tools.client_compatibility import hunter_revive_failed_fixture as guard
from tools.client_compatibility.hunter_revive_fixture import dead_snapshot, restored_pets
from tools.client_compatibility.interaction_hunter_revive_failed_normalize import restore_sql, PET_COLUMNS
from tools.client_compatibility import interaction_hunter_revive_failed_close as closer
from tools.client_compatibility.interaction_pet_summon import cast_identity
from tools.client_compatibility.world.objects import INDEX


@pytest.fixture
def failed():
    packets = [
        {'time': 120, 'session': 'entry01', 'direction': 'from_client', 'name': 'CMSG_CAST_SPELL',
         'body': '01830482f5bc0000000000000000d6030000069d030000000000000000000000000000000000000000000000000000000000000000000000'},
        {'time': 121, 'session': 'entry01', 'direction': 'to_native', 'name': 'CMSG_CAST_SPELL',
         'body': '04d6030000000000000000000000'},
        {'time': 131, 'session': 'entry01', 'direction': 'from_native', 'name': 'SMSG_SPELL_GO',
         'body': '0106010604d603000000090000000000001329400001060000000000000000420000000000f8e513c65ed23f42894c63424100000000'}]
    parsed = json.loads(json.dumps([cast_identity(p) for p in packets]))
    fields = {str(INDEX[k]): v for k, v in {'UNIT_FIELD_PETNUMBER': 16, 'OBJECT_FIELD_ENTRY': 299,
        'UNIT_FIELD_SUMMONEDBY': 6, 'UNIT_FIELD_MAXHEALTH': 198}.items()}
    pet = {'guid': 123456, 'fields': fields}
    return {'schema': 'client442_laya_interactions_v1', 'started_at': 100, 'cast_started_at': 110,
        'cast_finished_at': 140, 'finished_at': 150, 'completed': False, 'failure': guard.FAILURE,
        'controller': 'code_diagnostic_ordinary_inputs', 'model': None, 'revision': None, 'fine_tuned': False,
        'cases': [], 'input_sent': True, 'qualification_added': False, 'native_session': 'entry01',
        'ordinary_input': {'kind': 'chat', 'value': '/cast Revive Pet'},
        'custom_script_permission': 'blocked_by_user', 'softTargetInteract': guard.SCRIPT_BOUNDARY,
        'actor': {'actor': 'scout', 'guid': 6, 'account_id': 2, 'character_name': 'Harnesshunt',
            'race': 1, 'class': 3, 'level': 10},
        'capture_checks': deepcopy(guard.CAPTURE_CHECKS), 'cast_packets': packets,
        'native_cast_requests': [parsed[1]], 'modern_cast_requests': [parsed[0]],
        'native_completions': [parsed[2]], 'failure_packets': [],
        'native_pet_before': deepcopy(pet), 'native_pet_after': deepcopy(pet),
        'outcome_state': {'target': {'exists': False, 'health': 0}}}


@pytest.fixture
def offline():
    named = dict(id=4, owner=6, entry=42717, modelid=903, CreatedBySpell=883, PetType=1, level=10,
        exp=0, Reactstate=3, name='Harnesswolf', renamed=1, active=0, slot=5, curhealth=278,
        curmana=0, savetime=20, abdata='named controls')
    pet = dict(id=16, owner=6, entry=299, modelid=18156, CreatedBySpell=13481, PetType=1, level=10,
        exp=0, Reactstate=3, name='Wolf', renamed=0, active=1, slot=0, curhealth=278,
        curmana=0, savetime=30, abdata='disposable controls')
    original = {str(n): {'native': {'online': 0}, 'pets': [], 'saved': {'spells': []}, 'inventory': []}
        for n in range(1, 7)}
    original['6']['native'].update(guid=6, account=2, name='Harnesshunt', race=1, **{'class': 3},
        level=10, health=209, position_x=1, position_y=2, position_z=3, orientation=4, map=0,
        totaltime=10, leveltime=10, logout_time=30, latency=40)
    original['6']['pets'] = [named, pet]
    current = deepcopy(original)
    current['6']['pets'][1].update(curhealth=0, CreatedBySpell=883, active=0, savetime=50)
    current['6']['native'].update(totaltime=20, leveltime=20, logout_time=50, latency=41)
    fixture = {'before': original, 'after': dead_snapshot(original)}
    park = {'retained_class_fixture': deepcopy(current['6']['native']),
        'retained_class_saved': deepcopy(current['6']['saved']), 'retained_class_pets': deepcopy(current['6']['pets'])}
    return original, current, fixture, park


def test_closed_failure_is_admitted_without_changing_evidence(failed):
    original = deepcopy(failed)
    assert guard.validate_failed_cast(failed) is failed
    assert failed == original and failed['completed'] is False and failed['qualification_added'] is False


@pytest.mark.parametrize('key,value', [('completed', True), ('finished_at', None), ('failure', 'interrupted'),
    ('phase', 'owned_revive_cast_complete'), ('controller', 'laya'), ('model', 'model'), ('revision', 'rev'),
    ('fine_tuned', True), ('cases', [{}]), ('input_sent', False), ('qualification_added', True),
    ('cast_finished_at', 110), ('finished_at', float('nan')), ('custom_script_permission', 'enabled'),
    ('ordinary_input', {'kind': 'chat', 'value': '/cast Call Pet 1'}), ('restoration_checks', {})])
def test_partial_successful_or_different_failure_is_rejected(failed, key, value):
    failed[key] = value
    with pytest.raises(RuntimeError): guard.validate_failed_cast(failed)


@pytest.mark.parametrize('key', list(guard.CAPTURE_CHECKS))
def test_exact_outcome_failure_pattern_is_required(failed, key):
    failed['capture_checks'][key] = not failed['capture_checks'][key]
    with pytest.raises(RuntimeError): guard.validate_failed_cast(failed)


def test_truthy_integer_is_not_a_check_result(failed):
    failed['capture_checks']['one_native_cast'] = 1
    with pytest.raises(RuntimeError): guard.validate_failed_cast(failed)


@pytest.mark.parametrize('kind', ['duplicate_request', 'missing_go', 'wrong_session', 'outside_window', 'fake_summary', 'failure_packet'])
def test_actual_packets_are_required_not_only_summary_checks(failed, kind):
    if kind == 'duplicate_request': failed['cast_packets'].append(deepcopy(failed['cast_packets'][1]))
    elif kind == 'missing_go': failed['cast_packets'].pop()
    elif kind == 'wrong_session': failed['cast_packets'][1]['session'] = 'other'
    elif kind == 'outside_window': failed['cast_packets'][1]['time'] = 160
    elif kind == 'fake_summary': failed['native_cast_requests'][0]['counter'] = 9
    else: failed['cast_packets'].append({'time': 130, 'session': 'entry01', 'direction': 'from_native',
        'name': 'SMSG_CAST_FAILED', 'body': '04d603000001'})
    with pytest.raises(RuntimeError): guard.validate_failed_cast(failed)


@pytest.mark.parametrize('column,value', [('UNIT_FIELD_HEALTH', 1), ('UNIT_FIELD_PETNUMBER', 4),
    ('UNIT_FIELD_SUMMONEDBY', 1), ('OBJECT_FIELD_ENTRY', 42717), ('UNIT_FIELD_MAXHEALTH', 0)])
def test_living_or_different_pet_cannot_enter_failure_cleanup(failed, column, value):
    failed['native_pet_after']['fields'][str(INDEX[column])] = value
    with pytest.raises(RuntimeError): guard.validate_failed_cast(failed)


def test_cleanup_restores_only_three_fields_with_source_clock_preserved(offline):
    original, current, fixture, park = offline
    unchanged = deepcopy(current)
    expected = guard.offline_restore(current, fixture, park)
    assert current == unchanged
    assert restored_pets(original['6']['pets'], expected['6']['pets'])
    expected['6']['pets'][1].update(curhealth=0, CreatedBySpell=883, active=0)
    assert expected == current


@pytest.mark.parametrize('guid', ['1', '2', '3', '4', '5', '6'])
def test_every_online_character_blocks_cleanup(offline, guid):
    _, current, fixture, park = offline
    current[guid]['native']['online'] = 1
    with pytest.raises(RuntimeError): guard.offline_restore(current, fixture, park)


@pytest.mark.parametrize('pet,key,value', [(0, 'savetime', 21), (0, 'curhealth', 277), (0, 'slot', 0),
    (1, 'owner', 1), (1, 'name', 'Other'), (1, 'slot', 5), (1, 'modelid', 9), (1, 'abdata', 'changed'),
    (1, 'curhealth', 198), (1, 'CreatedBySpell', 982), (1, 'active', 1), (1, 'savetime', 29)])
def test_named_or_unrecorded_disposable_difference_blocks_cleanup(offline, pet, key, value):
    _, current, fixture, park = offline
    current['6']['pets'][pet][key] = value
    park['retained_class_pets'] = deepcopy(current['6']['pets'])
    with pytest.raises(RuntimeError): guard.offline_restore(current, fixture, park)


@pytest.mark.parametrize('guid,key', [('1', 'inventory'), ('2', 'saved'), ('3', 'pets'),
    ('4', 'saved'), ('5', 'inventory'), ('6', 'inventory'), ('6', 'saved')])
def test_protected_saved_state_changes_block_cleanup(offline, guid, key):
    _, current, fixture, park = offline
    current[guid][key] = {'changed': True}
    with pytest.raises(RuntimeError): guard.offline_restore(current, fixture, park)


def test_native_health_or_pose_cannot_be_repaired_by_fixture_cleanup(offline):
    _, current, fixture, park = offline
    current['6']['native']['health'] = 208
    park['retained_class_fixture'] = deepcopy(current['6']['native'])
    with pytest.raises(RuntimeError): guard.offline_restore(current, fixture, park)


def rest_proof_fixture(offline):
    original, current, fixture, park = offline
    original['6']['native']['rest_bonus'] = fixture['before']['6']['native']['rest_bonus'] = 148.981
    current['6']['native']['rest_bonus'] = park['retained_class_fixture']['rest_bonus'] = 154.469
    proof = {'schema': 'client442_owned_hunter_native_offline_rest_v1', 'input_sent': False,
        'original_rest_bonus': 148.981, 'expected_db_rest_bonus': 154.469, 'preserved_rest_bonus': 154.469}
    return current, fixture, park, proof


def test_rest_bonus_is_preserved_only_with_its_exact_native_proof(offline):
    current, fixture, park, proof = rest_proof_fixture(offline)
    with pytest.raises(RuntimeError): guard.offline_restore(current, fixture, park)
    restored = guard.offline_restore(current, fixture, park, proof)
    assert restored['6']['native']['rest_bonus'] == current['6']['native']['rest_bonus'] == 154.469


@pytest.mark.parametrize('key,value', [('schema', 'different'), ('input_sent', True),
    ('original_rest_bonus', 149), ('expected_db_rest_bonus', 155), ('preserved_rest_bonus', 155)])
def test_arbitrary_rest_proof_cannot_allow_native_stat_repair(offline, key, value):
    current, fixture, park, proof = rest_proof_fixture(offline)
    proof[key] = value
    with pytest.raises(RuntimeError): guard.offline_restore(current, fixture, park, proof)


def test_exact_rest_proof_cannot_allow_any_other_hunter_native_change(offline):
    current, fixture, park, proof = rest_proof_fixture(offline)
    current['6']['native']['position_x'] += 1
    park['retained_class_fixture'] = deepcopy(current['6']['native'])
    with pytest.raises(RuntimeError): guard.offline_restore(current, fixture, park, proof)


def test_exact_sql_compares_both_full_rows_and_all_six_offline_flags(offline):
    _, current, fixture, park = offline
    expected = guard.offline_restore(current, fixture, park)
    recorded = []
    cursor = SimpleNamespace(rowcount=1, execute=lambda sql, args: recorded.append((sql, args)))
    restore_sql(cursor, current, expected)
    sql, args = recorded[0]
    assert 'JOIN client442_characters.character_pet AS n ON n.id=4 AND n.owner=6' in sql
    assert 'guid IN (1,2,3,4,5,6) AND online<>0' in sql
    assert args[:3] == (278, 13481, 1)
    assert args[3:3 + len(PET_COLUMNS)] == tuple(current['6']['pets'][1][k] for k in PET_COLUMNS)
    assert args[3 + len(PET_COLUMNS):] == tuple(current['6']['pets'][0][k] for k in PET_COLUMNS)


@pytest.mark.parametrize('rowcount', [0, 2])
def test_update_must_match_exactly_one_disposable_row(offline, rowcount):
    _, current, fixture, park = offline
    expected = guard.offline_restore(current, fixture, park)
    cursor = SimpleNamespace(rowcount=rowcount, execute=lambda *args: None)
    with pytest.raises(RuntimeError): restore_sql(cursor, current, expected)


def test_failed_receipt_path_requires_private_closed_file(tmp_path, monkeypatch, failed):
    monkeypatch.setattr(guard.lab, 'ROOT', tmp_path)
    folder = tmp_path / 'evidence' / 'failed'
    folder.mkdir(parents=True)
    path = folder / 'episode.json'
    path.write_text(json.dumps(failed))
    assert guard.failed_cast(path)['completed'] is False
    link = folder / 'linked.json'
    link.symlink_to(path)
    with pytest.raises(ValueError): guard.failed_cast(link)
    with pytest.raises(ValueError): guard.failed_cast(tmp_path / 'outside' / 'episode.json')


@pytest.fixture
def chain(tmp_path, monkeypatch, failed, offline):
    monkeypatch.setattr(guard.lab, 'ROOT', tmp_path)
    original, current, fixture, park = deepcopy(offline)
    evidence = tmp_path / 'evidence'
    def write(name, receipt):
        path = evidence / name / 'episode.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(receipt))
        return path
    def successful(**values): return dict(completed=True, failure=None, **values)
    runtime = {k: {'pid': i, 'start_ticks': str(i * 100)}
        for i, k in enumerate(('worldserver', 'modern_world', 'client'), 1)}
    actor = failed['actor']
    origin = {'guid': 2, 'actor': 'scout', 'account_id': 2, 'character_name': 'Harnesstwo'}
    fixture.update(successful(schema='client442_owned_revive_dead_fixture_v1',
        phase='owned_revive_dead_fixture_staged', expected_after=fixture['after'],
        checks={str(n): True for n in range(7)}, runtime={k: runtime[k] for k in ('worldserver', 'modern_world')},
        started_at=1, finished_at=2))
    fixture_path = write('fixture', fixture)
    old = successful(phase='await_owned_class_lobby_review', fixture_source=guard.bound(fixture_path),
        runtime=runtime, actor=origin, class_actor=actor, origin_actor=origin,
        natural_native=fixture['after']['6']['native'], natural_saved=fixture['after']['6']['saved'],
        retained_class_pets=fixture['after']['6']['pets'],
        protected_baseline={g: original[g] for g in ('1', '2', '3', '4', '5')},
        checks={k: True for k in guard.ORIGIN_CHECKS | {f'actor_{g}_unchanged' for g in ('1', '2', '3', '4', '5')}},
        started_at=3, finished_at=4)
    preparation_path = write('preparation', old)
    ref = guard.bound(preparation_path)
    entry_path = write('entry', successful(phase='owned_class_entered', fixture_source=ref,
        actor=actor, runtime=runtime, native_session=failed['native_session'], started_at=10, finished_at=20))
    recon_path = write('recon', successful(phase='await_owned_revive_cast_review', fixture_source=ref,
        actor=actor, runtime=runtime, native_session=failed['native_session'], revive_spell={'id': 982, 'known': True},
        entry_source=guard.bound(entry_path), dead_fixture_source=guard.bound(fixture_path), started_at=30, finished_at=40))
    failed.update(fixture_source=ref, dead_fixture_source=guard.bound(fixture_path),
        entry_source=guard.bound(entry_path), recon_source=guard.bound(recon_path), runtime=runtime)
    cast_path = write('cast', failed)
    park.update(successful(phase='await_original_selection_review', fixture_source=ref,
        actor=actor, runtime=runtime, checks={k: True for k in guard.ORIGIN_CHECKS | {'class_offline'}},
        started_at=160, finished_at=170))
    park_path = write('park', park)
    return SimpleNamespace(paths=(preparation_path, fixture_path, cast_path, park_path),
        entry_path=entry_path, recon_path=recon_path, write=write, old=old, fixture=fixture,
        cast=failed, park=park, current=current, runtime=runtime)


def test_exact_sources_bind_the_failed_cast_to_normal_offline_park(chain):
    old, fixture, cast, park = guard.sources(*chain.paths)
    assert old == chain.old and fixture == chain.fixture and cast == chain.cast and park == chain.park
    restored = guard.offline_restore(chain.current, fixture, park)
    assert restored_pets(fixture['before']['6']['pets'], restored['6']['pets'])


@pytest.mark.parametrize('key,value', [('actor', {'guid': 4}), ('runtime', {}), ('fixture_source', {}),
    ('phase', 'owned_class_entered'), ('started_at', 140), ('checks', {'class_offline': True}),
    ('completed', False), ('failure', 'failure')])
def test_another_or_partial_park_cannot_authorize_cleanup(chain, key, value):
    chain.park[key] = value
    chain.write('park', chain.park)
    with pytest.raises(RuntimeError): guard.sources(*chain.paths)


@pytest.mark.parametrize('dependency', ['preparation', 'fixture', 'entry', 'recon'])
def test_closed_dependency_hash_changes_cannot_be_rebound_silently(chain, dependency):
    path = chain.paths[0] if dependency == 'preparation' else chain.paths[1] if dependency == 'fixture' else (
        chain.entry_path if dependency == 'entry' else chain.recon_path)
    receipt = json.loads(path.read_text())
    receipt['extra'] = 'modified after source binding'
    path.write_text(json.dumps(receipt))
    with pytest.raises(RuntimeError): guard.sources(*chain.paths)


@pytest.fixture
def closure(chain, monkeypatch):
    preparation, fixture_path, cast_path, park_path = chain.paths
    expected = guard.offline_restore(chain.current, chain.fixture, chain.park)
    stop_path = chain.write('primary_stop', {'completed': True, 'failure': None, 'finished_at': 1,
        'before': chain.fixture['before']['1'], 'after': chain.fixture['before']['1']})
    chain.fixture['primary_stop_source'] = guard.bound(stop_path)
    finish = {'completed': True, 'failure': None, 'started_at': 171, 'finished_at': 172,
        'runtime': chain.runtime, 'actor': chain.old['origin_actor'], 'fixture_source': guard.bound(preparation),
        'checks': {k: True for k in guard.ORIGIN_CHECKS | {'origin_registration', 'class_offline'}}}
    finish_path = chain.write('finish', finish)
    cleanup = {'completed': True, 'failure': None, 'started_at': 172, 'finished_at': 173,
        'schema': 'client442_failed_revive_offline_cleanup_v1', 'phase': 'owned_failed_revive_fixture_normalized',
        'sources': [guard.bound(p) for p in chain.paths], 'failed_cast_source': guard.bound(cast_path),
        'failed_cast_excluded': True, 'qualification_added': False, 'input_sent': False,
        'runtime': chain.runtime, 'actor': chain.cast['actor'], 'before': chain.current,
        'expected_after': expected, 'after': deepcopy(expected)}
    cleanup_path = chain.write('cleanup', cleanup)
    monkeypatch.setattr(closer, 'prepared', lambda *args: chain.old)
    monkeypatch.setattr(closer, 'sources', lambda *args: (chain.old, chain.fixture, chain.cast, chain.park))
    monkeypatch.setattr(closer, 'snapshot', lambda: deepcopy(expected))
    monkeypatch.setattr(closer, 'shot', lambda *args: {'file': 'mocked_no_input.png'})
    monkeypatch.setattr(closer, 'actor', lambda *args: nullcontext())
    monkeypatch.setattr(closer.actors, 'load', lambda: chain.old['origin_actor'])
    monkeypatch.setattr(closer.lab, 'owned_process', lambda *args: None)
    out = preparation.parent.parent / 'closed'
    out.mkdir()
    trial = SimpleNamespace(receipt={'runtime': chain.runtime}, out=out)
    args = (*chain.paths, finish_path, cleanup_path)
    return SimpleNamespace(trial=trial, args=args, finish=finish, cleanup=cleanup, chain=chain)


def test_failure_boundary_preserves_exclusion_without_rewriting_failure(closure):
    before = closure.args[2].read_bytes()
    closer.close(closure.trial, *closure.args)
    receipt = closure.trial.receipt
    assert receipt['completed'] is True and receipt['phase'] == 'owned_failed_revive_parked_boundary'
    assert receipt['qualification_added'] is False and receipt['failed_cast_excluded'] is True
    assert len(receipt['checks']) == 21 and all(receipt['checks'].values())
    assert closure.args[2].read_bytes() == before


@pytest.mark.parametrize('key,value', [('phase', 'owned_revive_fixture_normalized'), ('failed_cast_excluded', False),
    ('qualification_added', True), ('input_sent', True), ('failed_cast_source', {}), ('sources', []),
    ('runtime', {}), ('actor', {'guid': 4}), ('started_at', 159), ('expected_after', {})])
def test_success_cleanup_or_incomplete_failure_cleanup_cannot_close(closure, key, value):
    closure.cleanup[key] = value
    closure.args[-1].write_text(json.dumps(closure.cleanup))
    with pytest.raises(RuntimeError): closer.close(closure.trial, *closure.args)


def test_failed_boundary_requires_the_whole_normal_selection_receipt(closure):
    closure.finish['checks']['origin_registration'] = False
    closure.args[-2].write_text(json.dumps(closure.finish))
    with pytest.raises(RuntimeError): closer.close(closure.trial, *closure.args)
