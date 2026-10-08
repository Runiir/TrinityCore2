"""Full six-actor preservation and once-only exact FLOAT attribution for a bag swap."""
from copy import deepcopy
import math

from . import bag_swap_contract as contract
from . import item_actionbar_preservation as shared

ACCOUNTING, PRECISION_QUERY = shared.ACCOUNTING, shared.PRECISION_QUERY
float32, float32_bits, exact_precision, native_rest = (
    shared.float32, shared.float32_bits, shared.exact_precision, shared.native_rest)
require, finite, strict_equal = contract.require, contract.finite, contract.strict_equal


def login_rest(before, after, entry, exact_before, exact_after, rate=1):
    if type(entry) is dict and entry.get('phase') == 'bags_swap_entry_renewed':
        return _renewed_login_rest(before, after, entry, exact_before, exact_after, rate)
    require(type(entry) is dict and entry.get('phase') == contract.ENTRY_PHASE,
        'fresh bag-swap ordinary entry receipt is required')
    normalized = deepcopy(entry)
    normalized['phase'] = 'item_actionbar_entered'
    return shared.login_rest(before, after, normalized, exact_before, exact_after, rate)


def _renewed_login_rest(before, after, entry, exact_before, exact_after, rate):
    """Use original wire times, actual creation and present SQL; no old SQL fiction."""
    from .bag_swap_renewal import login_interval
    from .bag_swap_login_sync import login_sync
    interval = login_interval(entry)
    exact_precision(exact_before, before)
    exact_precision(exact_after, after)
    keys = ('guid', 'account', 'name', 'race', 'class', 'level', 'xp', 'is_logout_resting')
    expected = tuple(contract.ACTOR[k] for k in keys[:6]) + (0, 0)
    require(all(type(before.get(k)) is type(v) and before[k] == v for k, v in zip(keys, expected)) and
        all(type(after.get(k)) is type(before[k]) and after[k] == before[k] for k in keys) and
        finite(rate) and rate == 1 and type(before.get('logout_time')) is int and before['logout_time'] > 0 and
        type(after.get('logout_time')) is int and after['logout_time'] >= before['logout_time'] and
        entry.get('actor', {}).get('guid') == 2 and strict_equal(entry.get('native_before_entry'), before) and
        'entered_native' not in entry and entry.get('input_sent') is False and entry.get('mutation_sent') is False,
        'renewed rest must retain the actual original native/preprecision baseline')
    baseline = entry.get('all_offline_snapshot')
    contract.owned_snapshot(baseline)
    require(strict_equal(baseline['2']['native'], before), 'renewed rest changed its original six-actor baseline')
    current = entry.get('current_snapshot')
    online_preservation(baseline, current)
    pose = [before[k] for k in ('position_x', 'position_y', 'position_z', 'orientation')]
    raw = entry.get('raw_entry_packets')
    sync = login_sync(raw, entry.get('raw_entry_events'), entry.get('native_session'),
        interval['since'], interval['until'], pose)
    require(strict_equal(entry.get('login_sync'), sync), 'renewed rest requires exact original login settlement')
    kwargs = {'login_sync': sync}
    if 'idle_housekeeping' in entry:
        kwargs['idle_housekeeping'] = entry['idle_housekeeping']
    owner = contract.native_replay(raw, entry.get('native_session'), interval['since'], entry['finished_at'], **kwargs)
    require(strict_equal(entry.get('native_owner_proof'), owner) and strict_equal(entry.get('owner_packets'), owner['packets']) and
        strict_equal(entry.get('native_original', {}).get('pose'), {'stand': 0, 'sheath': 0}) and
        entry.get('native_original', {}).get('afk') is False, 'renewed rest requires whole actual native creation/history and restored pose')
    chain = contract.login_packets(entry.get('login_packets'), entry.get('native_session'), interval['since'], interval['until'])
    require(strict_equal(entry['login_packets'], sync['login_packets']) and
        strict_equal(chain, contract.login_packets(raw, entry.get('native_session'), interval['since'], entry['finished_at'])),
        'renewed rest must retain exactly one original login quartet through current observation')
    state = entry.get('state', {})
    require(all(type(state.get(k)) is type(v) and state[k] == v for k, v in
        {'player': 'Harnesstwo', 'level': 1, 'xp': 0, 'xp_max': contract.XP_CAP}.items()) and
        type(state.get('xp_exhaustion')) is int, 'renewed public level1 XP state differs')
    matches = []
    for second in range(math.floor(chain['request']['time']), math.floor(chain['verify']['time']) + 1):
        seconds = second - before['logout_time']
        if seconds < 0:
            continue
        exact, text = native_rest(exact_before['exact_rest_bonus'], seconds, contract.XP_CAP, rate)
        if (exact == exact_after['exact_rest_bonus'] and text == after['rest_bonus'] == current['2']['native']['rest_bonus'] and
                exact < contract.REST_CAP and owner['rest_threshold'] == int(exact) and state['xp_exhaustion'] == 2 * int(exact)):
            matches.append({'native_login_second': second, 'offline_seconds': seconds,
                'before_float32_bits': exact_before['exact_rest_bonus_float32_bits'],
                'after_float32_bits': exact_after['exact_rest_bonus_float32_bits'], 'exact_after': exact})
    require(len(matches) == 1, 'renewed rest requires one original uncapped native login second and actual creation threshold')
    return {'matches': matches, 'rate': rate, 'xp_cap': contract.XP_CAP, 'rest_cap': contract.REST_CAP,
        'wilderness_bubble': .031, 'rounded_baseline_reconstruction': False, 'login': chain}


def _preserved(before, after, *, swapped=False, offline=True):
    old = contract.owned_snapshot(before)
    now = contract.owned_snapshot(after, offline=offline, swapped=swapped)
    require(all(strict_equal(after[g], before[g]) for g in ('1', '3', '4', '5', '6')),
        'a protected actor changed during the bag swap')
    require(set(now['native']) == set(old['native']), 'the complete native projection changed shape')
    changed = {k for k in old['native'] if not strict_equal(now['native'][k], old['native'][k])}
    require(changed <= ACCOUNTING | {'rest_bonus', 'online'} and
        all(type(v['native'].get(k)) is int and v['native'][k] >= 0 for v in (old, now) for k in ACCOUNTING) and
        all(now['native'][k] >= old['native'][k] for k in ('totaltime', 'leveltime', 'logout_time')) and
        now['pets'] == old['pets'] == [] and strict_equal(now['saved'], old['saved']),
        'bag swap changed health/power/pose, pets, saved spells/skills/quests/actions or unrelated native fields')
    shared.action_rows(old['saved'].get('actions'))
    inventory = contract.inventory_rows(old['inventory'], now['inventory'], swapped=swapped)
    return old, now, inventory


def online_preservation(before, after, *, swapped=False):
    """SaveAll is diagnostic; admission still requires the normal offline closure."""
    old, now, inventory = _preserved(before, after, swapped=swapped, offline=False)
    require(now['native']['online'] == 1 and finite(now['native'].get('rest_bonus')) and
        old['native']['rest_bonus'] <= now['native']['rest_bonus'] < contract.REST_CAP,
        'online ordinary accounting/rest state differs')
    return {'owner': 2, 'protected_actors': [1, 3, 4, 5, 6], 'swapped': swapped,
        'inventory': inventory, 'health_power_pose_preserved': True,
        'saved_actions_preserved': True, 'rest_attribution_pending': True, 'operations_admitted': 0}


def preserve_six(before, after, entry, exact_before, exact_after, *, swapped=False, offline=True):
    old, now, inventory = _preserved(before, after, swapped=swapped, offline=offline)
    rest = login_rest(old['native'], now['native'], entry, exact_before, exact_after)
    return {'owner': 2, 'protected_actors': [1, 3, 4, 5, 6], 'all_six_preserved': True,
        'swapped': swapped, 'inventory': inventory, 'native_rest': rest,
        'all_item_instance_fields_unchanged': True, 'health_power_pose_preserved': True,
        'saved_actions_preserved': True, 'pets_absent': True}
