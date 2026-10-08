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
