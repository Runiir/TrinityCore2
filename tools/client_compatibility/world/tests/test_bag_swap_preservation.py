"""The only saved inventory delta is the exchange; rest accrues at one fresh login."""
from copy import deepcopy

import pytest

from tools.client_compatibility import bag_swap_contract as c
from tools.client_compatibility import bag_swap_preservation as p
from tools.client_compatibility.world.tests.test_bag_swap_contract import inventory
from tools.client_compatibility.world.tests.test_item_actionbar_preservation import fixture as item_fixture


def fixture(swapped=False):
    before, after, entry, exact_before, exact_after = item_fixture()
    before['2']['inventory'] = inventory()
    after['2']['inventory'] = c.expected_inventory(inventory(), swapped=swapped)
    entry['phase'] = c.ENTRY_PHASE
    return before, after, entry, exact_before, exact_after


@pytest.mark.parametrize('swapped', [False, True])
def test_six_actor_full_projection_and_exact_once_only_native_rest_are_preserved(swapped):
    proof = p.preserve_six(*fixture(swapped), swapped=swapped)
    assert proof['all_six_preserved'] is True
    assert proof['native_rest']['matches'][0]['offline_seconds'] == 100
    assert proof['native_rest']['rounded_baseline_reconstruction'] is False
    assert proof['all_item_instance_fields_unchanged'] is True
    assert proof['swapped'] is swapped


def test_online_saveall_preserves_all_columns_but_cannot_admit_operation():
    before, after, *_ = fixture(True)
    after['2']['native']['online'] = 1
    proof = p.online_preservation(before, after, swapped=True)
    assert proof['operations_admitted'] == 0
    assert proof['rest_attribution_pending'] is True


@pytest.mark.parametrize('fault', ['health', 'power', 'xp', 'money', 'pose', 'spec', 'pet', 'peer_pet',
    'peer_inventory', 'item_count', 'item_charges', 'saved_spell', 'saved_skill', 'saved_quest',
    'saved_actions', 'missing_native', 'missing_peer', 'bool_time', 'backward_time', 'bool_online',
    'wrong_phase', 'reused_login', 'rounded_precision', 'wrong_bits', 'rest_more_than_once',
    'public_exhaustion', 'wrong_actor'])
def test_full_preservation_rejects_unrelated_changes_reused_entry_and_inexact_rest(fault):
    before, after, entry, exact_before, exact_after = fixture(True)
    own = after['2']
    if fault == 'health': own['native']['health'] -= 1
    elif fault == 'power': own['native']['power1'] = 1
    elif fault == 'xp': own['native']['xp'] = 1
    elif fault == 'money': own['native']['money'] = 1
    elif fault == 'pose': own['native']['orientation'] += .1
    elif fault == 'spec': own['native']['activeTalentGroup'] = 1
    elif fault == 'pet': own['pets'] = [{'id': 16}]
    elif fault == 'peer_pet': after['6']['pets'][0]['curhealth'] += 1
    elif fault == 'peer_inventory': after['3']['inventory'] = [['extra']]
    elif fault == 'item_count': own['inventory'][0][9] = 2
    elif fault == 'item_charges': own['inventory'][0][11] = '1 0 0 0 0 '
    elif fault == 'saved_spell': own['saved']['spells'] = [[1462, 1, 0]]
    elif fault == 'saved_skill': own['saved']['skills'] = [[1, 1]]
    elif fault == 'saved_quest': own['saved']['quests'] = [[1, 1]]
    elif fault == 'saved_actions': own['saved']['actions'].append([0, 0, 6948, 128])
    elif fault == 'missing_native': own['native'].pop('latency')
    elif fault == 'missing_peer': after.pop('5')
    elif fault == 'bool_time': own['native']['totaltime'] = True
    elif fault == 'backward_time': own['native']['leveltime'] = 99
    elif fault == 'bool_online': own['native']['online'] = False
    elif fault == 'wrong_phase': entry['phase'] = 'item_actionbar_entered'
    elif fault == 'reused_login': entry['login_packets'] += deepcopy(entry['login_packets'])
    elif fault == 'rounded_precision': exact_before['exact_rest_bonus'] = exact_before['rest_bonus']
    elif fault == 'wrong_bits': exact_after['exact_rest_bonus_float32_bits'] = '00000000'
    elif fault == 'rest_more_than_once':
        exact, text = p.native_rest(exact_after['exact_rest_bonus'], 100)
        own['native']['rest_bonus'] = exact_after['rest_bonus'] = text
        exact_after['exact_rest_bonus'] = exact
        exact_after['exact_rest_bonus_float32_bits'] = p.float32_bits(exact)
    elif fault == 'public_exhaustion': entry['state']['xp_exhaustion'] += 2
    else: exact_before['guid'] = 6
    with pytest.raises(RuntimeError):
        p.preserve_six(before, after, entry, exact_before, exact_after, swapped=True)


@pytest.mark.parametrize('flag', [0, 1, None])
def test_swap_flags_require_actual_booleans(flag):
    values = fixture()
    with pytest.raises(RuntimeError): p.preserve_six(*values, swapped=flag)


def test_protected_actor_comparison_does_not_equate_boolean_to_numeric_zero():
    before, after, entry, exact_before, exact_after = fixture()
    before['3']['saved']['skills'] = [[0, 1, 1]]
    after['3']['saved']['skills'] = [[False, 1, 1]]
    with pytest.raises(RuntimeError): p.preserve_six(before, after, entry, exact_before, exact_after)


def renewed_fixture(tmp_path):
    from tools.client_compatibility.world.tests.test_bag_swap_renewal import fixture as renewal_fixture
    from tools.client_compatibility.world.tests.test_item_actionbar_preservation import precision
    v = renewal_fixture(tmp_path)
    entry = v['entry']
    before = deepcopy(v['ready']['all_offline_snapshot'])
    after = deepcopy(entry['current_snapshot'])
    after['2']['native'].update(online=0, logout_time=int(entry['finished_at']) + 10)
    exact = p.native_rest(v['precision']['row']['exact_rest_bonus'],
        int(entry['login_packets'][1]['time']) - before['2']['native']['logout_time'])[0]
    return before, after, entry, v['precision']['row'], precision(after['2']['native'], exact)


def test_renewed_rest_uses_original_wire_time_and_actual_creation_without_inventing_old_sql(tmp_path):
    values = renewed_fixture(tmp_path)
    original = deepcopy(values[2])
    result = p.preserve_six(*values)
    match = result['native_rest']['matches'][0]
    assert match['native_login_second'] == 1791421132
    assert match['offline_seconds'] == 4151
    assert match['exact_after'] == values[4]['exact_rest_bonus']
    assert values[2] == original and 'entered_native' not in values[2]
    assert values[2]['started_at'] > result['native_rest']['login']['delivered']['time']


@pytest.mark.parametrize('fault', ['invented_old_sql', 'receipt_as_login', 'current_rest', 'current_health',
    'current_pet', 'native_threshold', 'public_exhaustion', 'missing_original_events', 'changed_original_pose'])
def test_renewed_rest_rejects_retiming_fabricated_old_sql_and_present_state_drift(tmp_path, fault):
    before, after, entry, exact_before, exact_after = renewed_fixture(tmp_path)
    if fault == 'invented_old_sql': entry['entered_native'] = {**before['2']['native'], 'online': 1}
    elif fault == 'receipt_as_login': entry['original_login_interval'] = {'since': entry['started_at'], 'until': entry['finished_at']}
    elif fault == 'current_rest': entry['current_snapshot']['2']['native']['rest_bonus'] += .01
    elif fault == 'current_health': entry['current_snapshot']['2']['native']['health'] -= 1
    elif fault == 'current_pet': entry['current_snapshot']['6']['pets'][0]['curhealth'] -= 1
    elif fault == 'native_threshold': entry['native_owner_proof']['rest_threshold'] += 1
    elif fault == 'public_exhaustion': entry['state']['xp_exhaustion'] += 2
    elif fault == 'missing_original_events': entry.pop('raw_entry_events')
    else: entry['native_before_entry']['orientation'] += .1
    with pytest.raises(RuntimeError): p.preserve_six(before, after, entry, exact_before, exact_after)
