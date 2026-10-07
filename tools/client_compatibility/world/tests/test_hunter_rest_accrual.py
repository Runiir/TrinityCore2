"""Preserve source-bound native rest accrual without allowing arbitrary stat repair."""
from copy import deepcopy
import json
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
