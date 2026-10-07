"""Beast Lore learning proves the owned new event, never a stale login caption."""
from copy import deepcopy
import struct

import pytest

from tools.client_compatibility import hunter_learn_contract as contract
from tools.client_compatibility import hunter_learn_preservation as preservation
from tools.client_compatibility.hunter_rest_accrual import native_rest


def packets():
    return [{'session': 'hunter', 'time': 10 + i * .1, 'direction': d, 'name': n, 'body': body.hex()}
        for i, (d, n, body) in enumerate((
            ('to_native', 'CMSG_TRAINER_BUY_SPELL', struct.pack('<QII', contract.TRAINER_GUID, 40, 1462)),
            ('from_native', 'SMSG_LEARNED_SPELL', struct.pack('<II', 1462, 0)),
            ('to_client', 'SMSG_LEARNED_SPELLS', struct.pack('<IIBIB', 1, 0, 0, 1462, 0))))]


def learned(rows=None, before=None, after=None):
    return contract.learned_checks(rows if rows is not None else packets(),
        contract.BASE_SPELLS, sorted(contract.BASE_SPELLS + [[1462, 1, 0]]),
        before if before is not None else {'money': 8708, 'items': [6948]},
        after if after is not None else {'money': 8062, 'items': [6948]}, 'hunter', 10, 11)


def probe(learned):
    return {'visible': True, 'book_type': 'spell', 'skill_line': 2,
        'tabs': [{'index': 2, 'name': 'Beast Mastery', 'checked': True}],
        'rows': [{'id': 1462, 'api_id': 1462, 'action': 1462, 'kind': 'SPELL' if learned else 'FUTURESPELL',
            'api_kind': 'SPELL' if learned else 'FUTURESPELL', 'known': learned, 'trainer': not learned,
            'shown_name': '|cffffffffBeast Lore|r', 'name': 'Beast Lore', 'button': 'SpellButton9'}]}


def test_exact_native_learn_reconciles_login_authority_without_replacing_other_spells():
    checks = learned()
    assert all(checks.values())
    assert contract.reconciled_known([1515, 93321, 982], packets(), checks) == {1515, 93321, 982, 1462}
    assert contract.book_row(probe(False), False)['kind'] == 'FUTURESPELL'
    after = probe(True)
    after['rows'][0]['button'] = 'SpellButton10'
    assert contract.book_row(after, True)['known'] is True  # Slot ordering may change after learning.


@pytest.mark.parametrize('fault', ['guid', 'trainer', 'spell', 'session', 'before_window', 'duplicate_buy',
    'duplicate_native', 'missing_delivery', 'extra_spell', 'unordered', 'late_delivery', 'charge', 'inventory', 'failed'])
def test_learn_requires_one_owned_direct_purchase_and_exact_resources(fault):
    rows = packets()
    after = {'money': 8062, 'items': [6948]}
    if fault == 'guid': rows[0]['body'] = struct.pack('<QII', contract.TRAINER_GUID + 1, 40, 1462).hex()
    elif fault == 'trainer': rows[0]['body'] = struct.pack('<QII', contract.TRAINER_GUID, 154, 1462).hex()
    elif fault == 'spell': rows[1]['body'] = struct.pack('<II', 93321, 0).hex()
    elif fault == 'session': rows[1]['session'] = 'other'
    elif fault == 'before_window': rows[0]['time'] = 9.99
    elif fault == 'duplicate_buy': rows.append(deepcopy(rows[0]))
    elif fault == 'duplicate_native': rows.append(deepcopy(rows[1]))
    elif fault == 'missing_delivery': rows.pop()
    elif fault == 'extra_spell': rows.append({**rows[1], 'body': struct.pack('<II', 1515, 0).hex()})
    elif fault == 'unordered': rows[1]['time'] = 10.3
    elif fault == 'late_delivery': rows[2]['time'] = 20
    elif fault == 'charge': after['money'] -= 1
    elif fault == 'inventory': after['items'] = []
    else: rows.append({**rows[1], 'name': 'SMSG_TRAINER_BUY_FAILED', 'body': ''})
    assert not all(learned(rows=rows, after=after).values())


@pytest.mark.parametrize('fault', ['stale_login', 'failed_checks', 'missing_event'])
def test_stale_login_or_unproven_learn_never_becomes_known_authority(fault):
    checks, ids, rows = learned(), [1515, 93321], packets()
    if fault == 'stale_login': ids.append(1462)
    elif fault == 'failed_checks': checks['exact_charge_resources'] = False
    else: rows.pop(1)
    with pytest.raises(RuntimeError): contract.reconciled_known(ids, rows, checks)


@pytest.mark.parametrize('key,value', [('api_id', 1515), ('action', 93321), ('known', False),
    ('trainer', True), ('kind', 'FUTURESPELL'), ('api_kind', 'FUTURESPELL'), ('shown_name', 'Other'), ('button', '')])
def test_stock_caption_requires_exact_api_rendered_and_learned_identity(key, value):
    p = probe(True)
    p['rows'][0][key] = value
    with pytest.raises(RuntimeError): contract.book_row(p, True)


def native_login():
    exact_before = 168.58815002441406
    exact_after, text = native_rest(exact_before, 100, 7600, 1)
    before = {'guid': 6, 'account': 2, 'name': 'Harnesshunt', 'race': 1, 'class': 3, 'level': 10,
        'xp': 45, 'is_logout_resting': 0, 'rest_bonus': 168.588, 'logout_time': 1000, 'online': 0}
    after = {**before, 'rest_bonus': text, 'logout_time': 1200}
    b = {**before, 'exact_rest_bonus': exact_before, 'exact_rest_bonus_float32_bits': struct.pack('<f', exact_before).hex()}
    a = {**after, 'exact_rest_bonus': exact_after, 'exact_rest_bonus_float32_bits': struct.pack('<f', exact_after).hex()}
    entry = {'phase': 'owned_class_entered', 'actor': {'guid': 6}, 'native_session': 'hunter',
        'started_at': 1099, 'finished_at': 1101, 'native_before_entry': before,
        'entered_native': {**before, 'online': 1}, 'state': {'xp_max': 7600, 'xp': 45, 'player': 'Harnesshunt', 'level': 10,
            'xp_exhaustion': 2 * int(exact_after)},
        'login_packets': [{'name': n, 'direction': d, 'session': 'hunter', 'time': t} for n, d, t in (
            ('CMSG_PLAYER_LOGIN', 'to_native', 1100.2), ('SMSG_LOGIN_VERIFY_WORLD', 'from_native', 1100.3))]}
    return before, after, entry, b, a


def test_exact_float_before_and_after_attribute_one_native_login_second():
    data = native_login()
    proof = preservation.login_rest(*data)
    assert proof['matches'][0]['offline_seconds'] == 100
    assert proof['rounded_baseline_reconstruction'] is False
    data[-2]['exact_rest_bonus'] = 168.588
    with pytest.raises(RuntimeError): preservation.login_rest(*data)


@pytest.mark.parametrize('fault', ['boolean_rate', 'public_exhaustion', 'nan_time', 'bool_time', 'duplicate_request',
    'foreign_session', 'wrong_bits', 'ambiguous_cap', 'single_second_cap', 'float_logout', 'infinite_logout', 'bool_logout'])
def test_rest_preservation_refuses_lossy_or_ambiguous_native_attribution(fault):
    before, after, entry, b, a = native_login()
    rate = 1
    if fault == 'boolean_rate': rate = True
    elif fault == 'public_exhaustion': entry['state']['xp_exhaustion'] += 2
    elif fault == 'nan_time': entry['login_packets'][0]['time'] = float('nan')
    elif fault == 'bool_time': entry['login_packets'][0]['time'] = True
    elif fault == 'duplicate_request': entry['login_packets'].append(deepcopy(entry['login_packets'][0]))
    elif fault == 'foreign_session': entry['login_packets'][0]['session'] = 'foreign'
    elif fault == 'wrong_bits': a['exact_rest_bonus_float32_bits'] = '00000000'
    elif fault in ('float_logout', 'infinite_logout', 'bool_logout'):
        after['logout_time'] = {'float_logout': 1200.0, 'infinite_logout': float('inf'), 'bool_logout': True}[fault]
    else:
        for row in (before, after, b, a): row['rest_bonus'] = 5700
        for row in (b, a):
            row.update(exact_rest_bonus=5700, exact_rest_bonus_float32_bits=struct.pack('<f', 5700).hex())
        entry['entered_native'] = {**before, 'online': 1}
        entry['state']['xp_exhaustion'] = 11400
        if fault == 'ambiguous_cap':
            entry['login_packets'][1]['time'] = 1102.2
            entry['finished_at'] = 1103
    with pytest.raises(RuntimeError): preservation.login_rest(before, after, entry, b, a, rate)


@pytest.mark.parametrize('fault', [None, 'trainer_spawn', 'wrong_price', 'skill_step', 'dependency', 'pet_aura', 'linked'])
def test_native_prerequisite_fingerprint_is_readonly_and_refuses_hidden_side_effects(monkeypatch, fault):
    queries = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query):
            assert query.startswith('SELECT ')
            queries.append(query)
            self.query = query
        def fetchall(self):
            if 'creature c JOIN' in self.query:
                row = list(contract.TRAINER_ROW)
                if fault == 'trainer_spawn': row[0] += 1
                return [row]
            if 'trainer_spell' in self.query:
                row = [40, 1462, 680, 0, 0, 0, 0, 0, 10]
                if fault == 'wrong_price': row[2] += 1
                if fault == 'skill_step': row[3:5] = [50, 1]
                return [row]
            for key, query in contract.RELATION_QUERIES.items():
                if query == self.query:
                    return [[1462, 42, 1]] if key == {'dependency': 'learn', 'pet_aura': 'pet', 'linked': 'linked'}.get(fault) else []
            raise AssertionError(self.query)
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()
    monkeypatch.setattr(contract.lab, 'connection', Connection)
    monkeypatch.setattr(contract, 'static_prerequisites', lambda: {'pinned_dbc': True})
    if fault:
        with pytest.raises(RuntimeError): contract.native_prerequisites()
    else:
        proof = contract.native_prerequisites()
        assert proof['sha256'] == contract.fingerprint({k: v for k, v in proof.items() if k != 'sha256'})
    assert len(queries) == 6
