"""Preserve source-bound native rest accrual without allowing arbitrary stat repair."""
from copy import deepcopy
import json
import struct
import pytest
from tools.client_compatibility import hunter_rest_accrual as rest


@pytest.fixture
def native_login():
    before = {'guid': 6, 'account': 2, 'name': 'Harnesshunt', 'race': 1, 'class': 3, 'level': 10,
        'xp': 45, 'is_logout_resting': 0, 'rest_bonus': 148.981, 'logout_time': 1791391544}
    after = {**before, 'rest_bonus': 154.469}
    entry = {'completed': True, 'failure': None, 'phase': 'owned_class_entered', 'actor': {'guid': 6},
        'native_session': 'entry01', 'started_at': 1791393213, 'finished_at': 1791393225,
        'entered_native': deepcopy(before),
        'state': {'xp_max': 7600, 'xp': 45, 'level': 10, 'player': 'Harnesshunt', 'xp_exhaustion': 308},
        'login_packets': [
            {'time': 1791393221.1431983, 'session': 'entry01', 'name': 'CMSG_PLAYER_LOGIN', 'direction': 'to_native'},
            {'time': 1791393221.1993692, 'session': 'entry01', 'name': 'SMSG_LOGIN_VERIFY_WORLD', 'direction': 'from_native'}]}
    return before, after, entry


def test_native_float_calculation_matches_observed_sql_value(native_login):
    before, after, entry = native_login
    original = deepcopy(native_login)
    proof = rest.accrual(before, after, entry, 1)
    assert proof['offline_seconds'] == 1677
    assert proof['expected_native_float32'] == 154.46852111816406
    assert proof['expected_db_rest_bonus'] == proof['preserved_rest_bonus'] == 154.469
    assert proof['input_sent'] is False and native_login == original


@pytest.mark.parametrize('key,value', [('rest_bonus', 148.981), ('rest_bonus', 154.468), ('rest_bonus', 155),
    ('rest_bonus', float('nan')), ('rest_bonus', 5701), ('xp', 46), ('level', 11),
    ('guid', 4), ('account', 1), ('is_logout_resting', 1)])
def test_wrong_bonus_or_hunter_progression_is_rejected(native_login, key, value):
    before, after, entry = native_login
    after[key] = value
    with pytest.raises(RuntimeError): rest.accrual(before, after, entry, 1)


@pytest.mark.parametrize('key,value', [('xp_max', 7601), ('xp', 46), ('xp_exhaustion', 310),
    ('player', 'OtherHunter'), ('level', 11)])
def test_public_entry_must_prove_the_exact_cap_and_exhaustion(native_login, key, value):
    before, after, entry = native_login
    entry['state'][key] = value
    with pytest.raises(RuntimeError): rest.accrual(before, after, entry, 1)


@pytest.mark.parametrize('fault', ['missing', 'duplicate', 'other_session', 'wrong_direction', 'late', 'nonfinite'])
def test_native_request_and_verify_interval_is_required(native_login, fault):
    before, after, entry = native_login
    packets = entry['login_packets']
    if fault == 'missing': packets.pop(0)
    elif fault == 'duplicate': packets.append(deepcopy(packets[0]))
    elif fault == 'other_session': packets[0]['session'] = 'other'
    elif fault == 'wrong_direction': packets[1]['direction'] = 'to_client'
    elif fault == 'late': packets[1]['time'] += 10
    else: packets[0]['time'] = float('nan')
    with pytest.raises(RuntimeError): rest.accrual(before, after, entry, 1)


@pytest.mark.parametrize('rate', [0, 2, True, float('nan')])
def test_only_verified_native_rate_is_supported(native_login, rate):
    with pytest.raises(RuntimeError): rest.accrual(*native_login, rate)


def test_proof_binds_entry_runtime_config_and_native_formula(tmp_path, monkeypatch, native_login):
    monkeypatch.setattr(rest.lab, 'ROOT', tmp_path)
    monkeypatch.setattr(rest.lab, 'REPO', tmp_path / 'repo')
    path = tmp_path / 'evidence' / 'entry' / 'episode.json'
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(native_login[2]))
    config = tmp_path / 'config/worldserver.conf'
    config.parent.mkdir()
    config.write_text('Rate.Rest.Offline.InWilderness = 1\n')
    source = rest.lab.REPO / rest.FORMULA_SOURCE
    source.parent.mkdir(parents=True)
    source.write_text('float bubble0 = 0.031f;\n'
        'bubble0*sWorld->getRate(RATE_REST_OFFLINE_IN_WILDERNESS)\n'
        'SetRestBonus(GetRestBonus() + time_diff*((float)GetUInt32Value(PLAYER_NEXT_LEVEL_XP) / 72000)*bubble);\n')
    ref = rest.bound(path)
    proof = rest.preservation(*native_login[:2], ref)
    assert proof['entry_source'] == ref
    assert proof['config_source'] == rest.bound(config)
    assert proof['native_formula_source'] == rest.bound(source)
    config.write_text('Rate.Rest.Offline.InWilderness = 2\n')
    with pytest.raises(RuntimeError): rest.preservation(*native_login[:2], ref)
    config.write_text('Rate.Rest.Offline.InWilderness = 1\n')
    source.write_text('different native formula')
    with pytest.raises(RuntimeError): rest.preservation(*native_login[:2], ref)
    path.write_text(json.dumps({**native_login[2], 'completed': False}))
    with pytest.raises(RuntimeError): rest.preservation(*native_login[:2], ref)


@pytest.fixture
def precision_login(native_login):
    before, after, entry = deepcopy(native_login)
    before.update(rest_bonus=162.211, logout_time=1791398835, online=0)
    after.update(rest_bonus=168.588, logout_time=1791401197, online=0)
    entry.update(started_at=1791400777.8741577, finished_at=1791400792.745641, entered_native=deepcopy(before))
    entry['state']['xp_exhaustion'] = 336
    entry['login_packets'][0]['time'] = 1791400784.579115
    entry['login_packets'][1]['time'] = 1791400784.677467
    row = {**after, 'exact_rest_bonus': 168.58815002441406, 'exact_rest_bonus_float32_bits': '91962843'}
    return before, after, entry, row


def test_exact_sql_float_observation_resolves_lossy_baseline_without_tolerance(precision_login):
    before, after, entry, row = precision_login
    unchanged = deepcopy(precision_login)
    with pytest.raises(RuntimeError): rest.accrual(before, after, entry, 1)
    proof = rest.accrual(before, after, entry, 1, row)
    assert proof['offline_seconds'] == 1949
    assert proof['original_native_float32'] == 162.21058654785156
    assert proof['original_native_float32_bits'] == 'e9352243'
    assert proof['expected_native_float32'] == 168.58815002441406
    assert proof['exact_after_float32_bits'] == '91962843'
    assert proof['expected_db_rest_bonus'] == proof['preserved_rest_bonus'] == 168.588
    assert proof['exact_baseline_candidates'] == 65
    assert proof['precision_method'] == 'unique_float32_inverse_of_exact_sql_double'
    assert precision_login == unchanged


def test_float_preimage_is_complete_and_exact():
    values = rest.native_baselines(162.211)
    bits = sorted(struct.unpack('<I', struct.pack('<f', value))[0] for value in values)
    assert len(values) == len(set(values)) == 65
    assert bits == list(range(bits[0], bits[-1] + 1))
    assert all(float(format(value, '.6g')) == 162.211 for value in values)
    assert all(float(format(struct.unpack('<f', struct.pack('<I', bit))[0], '.6g')) != 162.211
        for bit in (bits[0] - 1, bits[-1] + 1))


@pytest.mark.parametrize('value', [162.211123, True, float('nan'), -1, 5701])
def test_unobserved_baseline_digits_are_rejected(value):
    with pytest.raises(RuntimeError): rest.native_baselines(value)


@pytest.mark.parametrize('key,value', [('exact_rest_bonus', 168.588), ('exact_rest_bonus', True),
    ('exact_rest_bonus', float('nan')), ('exact_rest_bonus', 5701),
    ('exact_rest_bonus_float32_bits', '92962843'), ('rest_bonus', 168.589)])
def test_precision_requires_exact_float_bits_and_empirical_text(precision_login, key, value):
    before, after, entry, row = precision_login
    row[key] = value
    with pytest.raises(RuntimeError): rest.accrual(before, after, entry, 1, row)


def test_exact_observation_with_no_native_preimage_is_rejected(precision_login):
    before, after, entry, row = precision_login
    exact = rest.float32(168.590)
    after['rest_bonus'] = row['rest_bonus'] = float(format(exact, '.6g'))
    row.update(exact_rest_bonus=exact, exact_rest_bonus_float32_bits=struct.pack('<f', exact).hex())
    with pytest.raises(RuntimeError): rest.accrual(before, after, entry, 1, row)


def test_capped_rest_cannot_impute_a_nonunique_original_float(precision_login):
    before, after, entry, row = precision_login
    before['rest_bonus'] = after['rest_bonus'] = row['rest_bonus'] = 5700
    entry['entered_native'] = deepcopy(before)
    entry['state']['xp_exhaustion'] = 11400
    row.update(exact_rest_bonus=5700.0, exact_rest_bonus_float32_bits=struct.pack('<f', 5700).hex())
    with pytest.raises(RuntimeError): rest.accrual(before, after, entry, 1, row)


@pytest.fixture
def precision_sources(tmp_path, monkeypatch, precision_login):
    monkeypatch.setattr(rest.lab, 'ROOT', tmp_path)
    before, after, entry, row = precision_login
    entry.update(runtime={'bridge': 'owned'}, fixture_source={'path': 'preparation', 'sha256': 'bound'})
    snapshot = {str(n): {'native': {'guid': n, 'online': 0}, 'saved': {}, 'pets': []} for n in range(1, 7)}
    snapshot['6']['native'] = deepcopy(after)

    def write(name, value):
        path = tmp_path / 'evidence' / name / 'episode.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return rest.bound(path)

    entry_ref = write('entry', entry)
    park = {'completed': True, 'failure': None, 'phase': 'await_original_selection_review',
        'runtime': entry['runtime'], 'actor': entry['actor'], 'fixture_source': entry['fixture_source'],
        'checks': {str(n): True for n in range(4)}, 'retained_class_fixture': deepcopy(after),
        'started_at': 1791401167.7030647, 'finished_at': 1791401197.6937659}
    park_ref = write('park', park)
    normalization = {'completed': True, 'failure': None, 'phase': 'owned_revive_fixture_normalized',
        'runtime': entry['runtime'], 'actor': entry['actor'], 'after': deepcopy(snapshot), 'sources': [park_ref],
        'input_sent': False, 'qualification_added': False,
        'started_at': 1791401283.1123688, 'finished_at': 1791401283.7855744}
    normalization_ref = write('normalize', normalization)
    failed = {'completed': False, 'failure': rest.REST_FAILURE, 'phase': None,
        'runtime': entry['runtime'], 'fixture_source': entry['fixture_source'], 'cases': [], 'model': None,
        'started_at': 1791401323.5783243, 'finished_at': 1791401324.0485463}
    failed_ref = write('failed', failed)
    precision = {'completed': True, 'schema': 'client442_owned_hunter_readonly_rest_precision_v1',
        'phase': 'owned_hunter_readonly_rest_precision_complete',
        'input_sent': False, 'mutation_sent': False, 'qualification_added': False, 'query': rest.PRECISION_QUERY,
        'checks': {name: True for name in ('all_six_offline', 'all_saved_state_unchanged', 'hunter_identity',
            'snapshot_rest_matches', 'exact_float32')}, 'row': row,
        'sources': [entry_ref, park_ref, normalization_ref, failed_ref], 'before': snapshot, 'after': deepcopy(snapshot),
        'started_at': 1791401567.7743945, 'finished_at': 1791401568.216017}
    ref = write('precision', precision)
    return ref, precision, entry_ref, after, write


def test_precision_source_binds_unchanged_six_offline_and_failed_close(precision_sources):
    ref, precision, entry_ref, after, _ = precision_sources
    raw = rest.Path(ref['path']).read_bytes()
    assert rest.precision_source(rest.Path(ref['path']), entry_ref, after) == precision
    assert rest.Path(ref['path']).read_bytes() == raw
    assert all(name not in precision for name in ('controller', 'model', 'cases'))


@pytest.mark.parametrize('fault', ['query', 'mutation', 'input', 'qualification', 'extra_source', 'source_hash',
    'online', 'after_changed', 'extra_check', 'false_check', 'row_identity', 'bits', 'non_float32', 'chronology'])
def test_precision_source_rejects_forged_observation(precision_sources, fault):
    ref, precision, entry_ref, after, write = precision_sources
    if fault == 'query': precision['query'] += ' FOR UPDATE'
    elif fault in ('mutation', 'input'): precision[fault + '_sent'] = True
    elif fault == 'qualification': precision['qualification_added'] = True
    elif fault == 'extra_source': precision['sources'].append(deepcopy(entry_ref))
    elif fault == 'source_hash': precision['sources'][1]['sha256'] = '0' * 64
    elif fault == 'online': precision['before']['1']['native']['online'] = precision['after']['1']['native']['online'] = 1
    elif fault == 'after_changed': precision['after']['1']['saved']['new'] = 1
    elif fault == 'extra_check': precision['checks']['new'] = True
    elif fault == 'false_check': precision['checks']['exact_float32'] = False
    elif fault == 'row_identity': precision['row']['guid'] = 4
    elif fault == 'bits': precision['row']['exact_rest_bonus_float32_bits'] = '92962843'
    elif fault == 'non_float32': precision['row']['exact_rest_bonus'] = 168.588
    else: precision['started_at'] = 1791401300
    write('precision', precision)
    with pytest.raises(RuntimeError): rest.precision_source(rest.Path(ref['path']), entry_ref, after)


@pytest.mark.parametrize('role,fault', [(1, 'runtime'), (1, 'fixture_source'), (1, 'completed'),
    (1, 'checks'), (2, 'after'), (2, 'sources'), (3, 'failure'), (3, 'completed'), (3, 'cases'), (3, 'runtime')])
def test_precision_source_rejects_rebound_wrong_ancestry(precision_sources, role, fault):
    ref, precision, entry_ref, after, write = precision_sources
    source = rest.json_source(rest.Path(precision['sources'][role]['path']))
    if fault == 'completed': source['completed'] = not source['completed']
    elif fault == 'checks': source['checks']['0'] = False
    elif fault == 'after': source['after']['1']['native']['online'] = 1
    elif fault == 'sources': source['sources'] = [entry_ref]
    elif fault == 'failure': source['failure'] = 'RuntimeError: unrelated failure'
    elif fault == 'cases': source['cases'] = [{'qualification': True}]
    else: source[fault] = {'other': 'identity'}
    precision['sources'][role] = write(f'rebound_{role}', source)
    write('precision', precision)
    with pytest.raises(RuntimeError): rest.precision_source(rest.Path(ref['path']), entry_ref, after)


def test_precision_source_rejects_foreign_copied_episode(precision_sources, tmp_path):
    ref, precision, entry_ref, after, write = precision_sources
    source = rest.Path(precision['sources'][3]['path'])
    foreign = tmp_path / 'foreign' / 'episode.json'
    foreign.parent.mkdir()
    foreign.write_bytes(source.read_bytes())
    precision['sources'][3] = rest.bound(foreign)
    write('precision', precision)
    with pytest.raises(RuntimeError): rest.precision_source(rest.Path(ref['path']), entry_ref, after)


def test_precision_source_rejects_symlink_to_owned_episode(precision_sources, tmp_path):
    ref, precision, entry_ref, after, write = precision_sources
    alias = tmp_path / 'evidence' / 'alias' / 'episode.json'
    alias.parent.mkdir()
    alias.symlink_to(precision['sources'][3]['path'])
    precision['sources'][3] = {'path': str(alias), 'sha256': precision['sources'][3]['sha256']}
    write('precision', precision)
    with pytest.raises(RuntimeError): rest.precision_source(rest.Path(ref['path']), entry_ref, after)


@pytest.mark.parametrize('key,value', [('guid', 4), ('account', 1), ('name', 'OtherHunter'),
    ('race', 2), ('class', 1), ('level', 11), ('xp', 46), ('is_logout_resting', 1)])
def test_precision_source_rejects_coherent_foreign_hunter(precision_sources, key, value):
    ref, precision, entry_ref, after, write = precision_sources
    after[key] = value
    for state in (precision['before'], precision['after']): state['6']['native'][key] = value
    precision['row'][key] = value
    park = rest.json_source(rest.Path(precision['sources'][1]['path']))
    park['retained_class_fixture'][key] = value
    precision['sources'][1] = write('park', park)
    normalize = rest.json_source(rest.Path(precision['sources'][2]['path']))
    normalize['after'] = deepcopy(precision['before'])
    normalize['sources'] = [precision['sources'][1]]
    precision['sources'][2] = write('normalize', normalize)
    write('precision', precision)
    with pytest.raises(RuntimeError): rest.precision_source(rest.Path(ref['path']), entry_ref, after)


def test_explicit_precision_proof_binds_exact_observation_and_float_storage_sources(precision_sources):
    ref, precision, entry_ref, after, _ = precision_sources
    config = rest.lab.ROOT / 'config/worldserver.conf'
    config.parent.mkdir()
    config.write_text('Rate.Rest.Offline.InWilderness = 1\n')
    entry = rest.json_source(rest.Path(entry_ref['path']))
    proof = rest.preservation(entry['entered_native'], after, entry_ref, rest.Path(ref['path']))
    assert proof['precision_source'] == ref
    assert proof['exact_after_float32_bits'] == '91962843'
    assert len(proof['native_float_storage_sources']) == 4
    assert all(rest.bound(rest.Path(source['path'])) == source for source in proof['native_float_storage_sources'])
