"""Pure exact FLOAT and six-actor preservation checks for the original scout."""
from copy import deepcopy
import math
import struct

from .item_actionbar_contract import (ACTOR, XP_CAP, REST_CAP, require, finite, owned_snapshot,
    action_rows, saved_actions, login_packets, strict_equal)

ACCOUNTING = frozenset(('totaltime', 'leveltime', 'logout_time', 'latency'))
PRECISION_QUERY = ('SELECT guid,account,name,class,level,xp,online,rest_bonus,'
    'CAST(rest_bonus AS DOUBLE) AS exact_rest_bonus,logout_time,is_logout_resting '
    'FROM client442_characters.characters WHERE guid=2 AND account=2')


def float32(value):
    require(finite(value), 'native FLOAT must be finite and numeric')
    try:
        return struct.unpack('<f', struct.pack('<f', value))[0]
    except (OverflowError, struct.error) as error:
        raise RuntimeError('native FLOAT overflows float32') from error


def float32_bits(value):
    return struct.pack('<f', float32(value)).hex()


def exact_precision(row, snapshot):
    native = snapshot['2']['native'] if type(snapshot) is dict and '2' in snapshot else snapshot
    require(type(row) is dict and type(native) is dict, 'exact precision and native rows are required')
    for key in ('guid', 'account', 'name', 'class', 'level', 'xp', 'online', 'rest_bonus', 'logout_time', 'is_logout_resting'):
        require(key in native and type(row.get(key)) is type(native[key]) and row[key] == native[key],
            'exact FLOAT row differs from the source-bound actor2 snapshot')
    exact = row.get('exact_rest_bonus')
    require(finite(exact) and 0 <= exact < REST_CAP and float32(exact) == exact and
        row.get('exact_rest_bonus_float32_bits') == float32_bits(exact) and
        finite(native.get('rest_bonus')) and float(format(exact, '.6g')) == native['rest_bonus'],
        'exact uncapped FLOAT bits and SQL representation are required; reconstruction is forbidden')
    return deepcopy(row)


def native_rest(before, seconds, xp_cap=XP_CAP, rate=1):
    require(finite(before) and 0 <= before < REST_CAP and float32(before) == before and
        type(seconds) is int and 0 <= seconds <= 0xffffffff and type(xp_cap) is int and xp_cap == XP_CAP and
        finite(rate) and rate == 1, 'original-scout native rest inputs differ')
    coefficient = float32(float32(xp_cap) / 72000)
    bubble = float32(float32(.031) * float32(rate))
    gained = float32(float32(seconds * coefficient) * bubble)
    exact = min(float32(float32(before) + gained), float32(float32(xp_cap) * 1.5 / 2))
    return exact, float(format(exact, '.6g'))


def login_rest(before, after, entry, exact_before, exact_after, rate=1):
    exact_precision(exact_before, before)
    exact_precision(exact_after, after)
    keys = ('guid', 'account', 'name', 'race', 'class', 'level', 'xp', 'is_logout_resting')
    expected = tuple(ACTOR[k] for k in keys[:6]) + (0, 0)
    require(all(type(before.get(k)) is type(v) and before[k] == v for k, v in zip(keys, expected)) and
        all(type(after.get(k)) is type(before[k]) and after[k] == before[k] for k in keys) and
        finite(rate) and rate == 1 and type(before.get('logout_time')) is int and before['logout_time'] > 0 and
        type(after.get('logout_time')) is int and after['logout_time'] >= before['logout_time'] and
        type(entry) is dict and entry.get('phase') == 'item_actionbar_entered' and entry.get('actor', {}).get('guid') == 2 and
        strict_equal(entry.get('native_before_entry'), before) and strict_equal(entry.get('entered_native'), {**before, 'online': 1}),
        'exact original-scout ordinary login baseline differs')
    state = entry.get('state', {})
    require(all(type(state.get(k)) is type(v) and state[k] == v for k, v in
        {'player': 'Harnesstwo', 'level': 1, 'xp': 0, 'xp_max': XP_CAP}.items()) and
        type(state.get('xp_exhaustion')) is int, 'public level1 XP state differs')
    chain = login_packets(entry.get('login_packets'), entry.get('native_session'),
        entry.get('started_at'), entry.get('finished_at'))
    matches = []
    for second in range(math.floor(chain['request']['time']), math.floor(chain['verify']['time']) + 1):
        seconds = second - before['logout_time']
        if seconds < 0:
            continue
        exact, text = native_rest(exact_before['exact_rest_bonus'], seconds, XP_CAP, rate)
        if exact == exact_after['exact_rest_bonus'] and text == after['rest_bonus'] and exact < REST_CAP:
            matches.append({'native_login_second': second, 'offline_seconds': seconds,
                'before_float32_bits': exact_before['exact_rest_bonus_float32_bits'],
                'after_float32_bits': exact_after['exact_rest_bonus_float32_bits'], 'exact_after': exact})
    require(len(matches) == 1 and state['xp_exhaustion'] == 2 * int(matches[0]['exact_after']),
        'rest change needs one exact uncapped native login second and matching public exhaustion')
    return {'matches': matches, 'rate': rate, 'xp_cap': XP_CAP, 'rest_cap': REST_CAP,
        'wilderness_bubble': .031, 'rounded_baseline_reconstruction': False, 'login': chain}


def online_preservation(before, after, *, slot=None, placed=False):
    """Guard live saved state; exact accrued FLOAT remains an offline closure obligation."""
    require(type(placed) is bool, 'placement flag must be boolean')
    old, now = owned_snapshot(before), owned_snapshot(after, offline=False)
    require(now['native']['online'] == 1 and all(strict_equal(after[g], before[g]) for g in ('1', '3', '4', '5', '6')),
        'owner must be online and every protected actor unchanged')
    require(set(now['native']) == set(old['native']) and
        {k for k in old['native'] if not strict_equal(now['native'][k], old['native'][k])} <= ACCOUNTING | {'online', 'rest_bonus'} and
        all(type(v['native'].get(k)) is int and v['native'][k] >= 0 for v in (old, now) for k in ACCOUNTING) and
        all(now['native'][k] >= old['native'][k] for k in ('totaltime', 'leveltime', 'logout_time')) and
        finite(now['native'].get('rest_bonus')) and old['native']['rest_bonus'] <= now['native']['rest_bonus'] < REST_CAP and
        strict_equal(now['inventory'], old['inventory']) and now['pets'] == old['pets'] == [],
        'online SaveAll changed health, power, pose, inventory, pets or unrelated native fields')
    saved = deepcopy(old['saved'])
    action_rows(saved.get('actions'))
    if placed:
        saved['actions'] = saved_actions(before, slot, placed=True)
    require(strict_equal(now['saved'], saved), 'online saved state differs beyond the sole permitted item row')
    return {'owner': 2, 'protected_actors': [1, 3, 4, 5, 6], 'saved_inventory_preserved': True,
        'health_power_pose_preserved': True, 'placed': placed, 'rest_attribution_pending': True,
        'operations_admitted': 0}


def preserve_six(before, after, entry, exact_before, exact_after, *, slot=None, placed=False, offline=True):
    require(type(placed) is bool and type(offline) is bool, 'preservation flags must be booleans')
    old, now = owned_snapshot(before), owned_snapshot(after, offline=offline)
    require(all(strict_equal(after[g], before[g]) for g in ('1', '3', '4', '5', '6')), 'a protected actor changed')
    require(set(now['native']) == set(old['native']), 'the complete native projection changed shape')
    changed = {k for k in old['native'] if not strict_equal(now['native'][k], old['native'][k])}
    require(changed <= ACCOUNTING | {'rest_bonus', 'online'} and
        all(type(v['native'].get(k)) is int and v['native'][k] >= 0 for v in (old, now) for k in ACCOUNTING) and
        all(now['native'][k] >= old['native'][k] for k in ('totaltime', 'leveltime', 'logout_time')) and
        now['pets'] == old['pets'] == [] and strict_equal(now['inventory'], old['inventory']),
        'native health/power/pose/resources, pets or inventory changed beyond ordinary accounting/rest')
    require(set(now['saved']) == set(old['saved']), 'complete saved projection changed shape')
    expected_saved = deepcopy(old['saved'])
    action_rows(expected_saved.get('actions'))
    if placed:
        expected_saved['actions'] = saved_actions(before, slot, placed=True)
    require(strict_equal(now['saved'], expected_saved), 'saved rows differ beyond the sole permitted item action')
    rest = login_rest(old['native'], now['native'], entry, exact_before, exact_after)
    return {'owner': 2, 'protected_actors': [1, 3, 4, 5, 6], 'all_six_preserved': True,
        'placed': placed, 'slot0': slot if placed else None, 'native_rest': rest,
        'saved_inventory_preserved': True, 'health_power_pose_preserved': True, 'pets_absent': True}
