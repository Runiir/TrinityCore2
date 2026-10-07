"""Full six-actor projection and exact actor2 login FLOAT attribution."""
from copy import deepcopy
import struct

import pytest

from tools.client_compatibility import item_actionbar_contract as c
from tools.client_compatibility import item_actionbar_preservation as p
from tools.client_compatibility.world.tests.test_item_actionbar_contract import login_packets


def snapshot():
    result = {str(g): {'native': {'guid': g, 'account': 1 if g == 1 else 2, 'online': 0},
        'saved': {'actions': [], 'spells': [], 'skills': [], 'quests': []}, 'pets': [], 'inventory': []} for g in range(1, 7)}
    result['2']['native'].update({**c.ACTOR, 'xp': 0, 'health': 60, 'is_logout_resting': 0,
        'rest_bonus': 24.8683, 'logout_time': 1000, 'totaltime': 100, 'leveltime': 100, 'latency': 4451,
        'activeTalentGroup': 0, 'position_x': -8914.86, 'position_y': -135.609, 'position_z': 80.4425,
        'orientation': 5.83261, 'map': 0, **{'power' + str(i): 0 for i in range(1, 6)}})
    result['2']['inventory'] = [[2, 0, 23, 41, 41, 6948, 2, 0, 0, 1, 0, '0 0 0 0 0 ', 1, '', 0, 0, 0, 0, '']]
    result['2']['saved']['actions'] = [[0, 72, 88163, 0], [0, 73, 88161, 0], [1, 0, 6603, 0]]
    result['6']['pets'] = [{'id': 4, 'owner': 6, 'curhealth': 278}, {'id': 16, 'owner': 6, 'curhealth': 278}]
    return result


def precision(native, exact):
    return {**{k: native[k] for k in ('guid', 'account', 'name', 'class', 'level', 'xp', 'online',
        'rest_bonus', 'logout_time', 'is_logout_resting')}, 'exact_rest_bonus': exact,
        'exact_rest_bonus_float32_bits': struct.pack('<f', exact).hex()}


def fixture():
    before = snapshot()
    n = before['2']['native']
    exact_before = p.float32(24.8683)
    exact_after, text = p.native_rest(exact_before, 100)
    after = deepcopy(before)
    after['2']['native'].update(rest_bonus=text, logout_time=1200, totaltime=200, leveltime=200, latency=100)
    entry = {'phase': 'item_actionbar_entered', 'actor': {'guid': 2}, 'native_session': 'scout',
        'started_at': 1099, 'finished_at': 1101, 'native_before_entry': deepcopy(n),
        'entered_native': {**n, 'online': 1}, 'state': {'player': 'Harnesstwo', 'level': 1, 'xp': 0,
            'xp_max': 400, 'xp_exhaustion': 2 * int(exact_after)}, 'login_packets': login_packets()}
    return before, after, entry, precision(n, exact_before), precision(after['2']['native'], exact_after)


def test_exact_original_scout_rest_and_accounting_are_preserved_without_reset():
    values = fixture()
    proof = p.preserve_six(*values)
    assert proof['native_rest']['matches'][0]['offline_seconds'] == 100
    assert proof['native_rest']['rounded_baseline_reconstruction'] is False
    assert proof['pets_absent'] is True


@pytest.mark.parametrize('fault', ['health', 'power', 'xp', 'money', 'pose', 'spec', 'pet', 'hunter_pet',
    'peer_inventory', 'inventory', 'saved_spell', 'saved_skill', 'saved_quest', 'saved_other_spec',
    'missing_native', 'missing_peer', 'extra_projection', 'bool_time', 'backward_time', 'bool_online'])
def test_full_snapshot_refuses_unrelated_fields_and_preserves_other_hunters_pets(fault):
    before, after, entry, b, a = fixture()
    own = after['2']
    if fault == 'health': own['native']['health'] = 59
    elif fault == 'power': own['native']['power1'] = 1
    elif fault == 'xp': own['native']['xp'] = 1
    elif fault == 'money': own['native']['money'] = 1
    elif fault == 'pose': own['native']['orientation'] += .1
    elif fault == 'spec': own['native']['activeTalentGroup'] = 1
    elif fault == 'pet': own['pets'] = [{'id': 16}]
    elif fault == 'hunter_pet': after['6']['pets'][0]['curhealth'] = 279
    elif fault == 'peer_inventory': after['3']['inventory'] = [['new']]
    elif fault == 'inventory': own['inventory'][0][9] = 2
    elif fault == 'saved_spell': own['saved']['spells'] = [[1462, 1, 0]]
    elif fault == 'saved_skill': own['saved']['skills'] = [[1, 1]]
    elif fault == 'saved_quest': own['saved']['quests'] = [[1, 1]]
    elif fault == 'saved_other_spec': own['saved']['actions'].append([1, 1, 6948, 128])
    elif fault == 'missing_native': own['native'].pop('latency')
    elif fault == 'missing_peer': after.pop('5')
    elif fault == 'extra_projection': own['omitted_table'] = []
    elif fault == 'bool_time': own['native']['totaltime'] = True
    elif fault == 'backward_time': own['native']['leveltime'] = 99
    else: own['native']['online'] = False
    with pytest.raises(RuntimeError): p.preserve_six(before, after, entry, b, a)


def test_sole_saved_item_row_uses_pinned_actual_active_spec():
    before, after, entry, b, a = fixture()
    after['2']['saved']['actions'] = c.saved_actions(before, 74, placed=True)
    assert p.preserve_six(before, after, entry, b, a, slot=74, placed=True)['placed'] is True
    after['2']['saved']['actions'][2][0] = 1
    with pytest.raises(RuntimeError): p.preserve_six(before, after, entry, b, a, slot=74, placed=True)


@pytest.mark.parametrize('fault', ['rounded', 'wrong_bits', 'missing_bits', 'capped', 'bool_exact',
    'foreign_actor', 'public_exhaustion', 'public_cap', 'ambiguous', 'bool_rate', 'float_logout'])
def test_exact_float_proof_refuses_reconstruction_capping_wrong_owner_and_ambiguous_seconds(fault):
    before, after, entry, b, a = fixture()
    rate = 1
    if fault == 'rounded': b['exact_rest_bonus'] = 24.8683
    elif fault == 'wrong_bits': a['exact_rest_bonus_float32_bits'] = '00000000'
    elif fault == 'missing_bits': b.pop('exact_rest_bonus_float32_bits')
    elif fault == 'capped': a['exact_rest_bonus'] = 300
    elif fault == 'bool_exact': b['exact_rest_bonus'] = True
    elif fault == 'foreign_actor': b['guid'] = 6
    elif fault == 'public_exhaustion': entry['state']['xp_exhaustion'] += 2
    elif fault == 'public_cap': entry['state']['xp_max'] = 7600
    elif fault == 'ambiguous':
        entry['login_packets'][1]['time'] = 1099.99
        entry['login_packets'][0]['time'] = 1099.98
        entry['login_packets'][2]['time'] = 1101.01
        entry['login_packets'][3]['time'] = 1101.02
        # An observed value unconnected to every candidate native second must fail.
        a['exact_rest_bonus'] = p.float32(a['exact_rest_bonus'] + .5)
        a['exact_rest_bonus_float32_bits'] = p.float32_bits(a['exact_rest_bonus'])
        after['2']['native']['rest_bonus'] = a['rest_bonus'] = float(format(a['exact_rest_bonus'], '.6g'))
    elif fault == 'bool_rate': rate = True
    else: after['2']['native']['logout_time'] = 1200.0
    with pytest.raises(RuntimeError): p.login_rest(before['2']['native'], after['2']['native'], entry, b, a, rate)


def test_online_saveall_candidate_is_not_offline_rest_or_operation_admission():
    before, after, _, _, _ = fixture()
    after['2']['native']['online'] = 1
    after['2']['saved']['actions'] = c.saved_actions(before, 74, placed=True)
    proof = p.online_preservation(before, after, slot=74, placed=True)
    assert proof['operations_admitted'] == 0 and proof['rest_attribution_pending'] is True


def test_multiple_matching_native_seconds_are_refused_even_with_valid_raw_login_packets(monkeypatch):
    before, after, entry, b, a = fixture()
    entry['login_packets'][0]['time'] = 1099.9
    entry['login_packets'][1]['time'] = 1099.95
    entry['login_packets'][2]['time'] = 1100.2
    entry['login_packets'][3]['time'] = 1100.3
    monkeypatch.setattr(p, 'native_rest', lambda *args: (a['exact_rest_bonus'], a['rest_bonus']))
    with pytest.raises(RuntimeError): p.login_rest(before['2']['native'], after['2']['native'], entry, b, a)


@pytest.mark.parametrize('section,key', [('native', 'map'), ('saved', 'skills')])
def test_full_projection_comparison_never_equates_booleans_to_native_zero(section, key):
    before, after, entry, b, a = fixture()
    if section == 'native': after['2']['native'][key] = False
    else:
        before['2']['saved'][key] = [[0, 1, 1]]
        after['2']['saved'][key] = [[False, 1, 1]]
    with pytest.raises(RuntimeError): p.preserve_six(before, after, entry, b, a)
