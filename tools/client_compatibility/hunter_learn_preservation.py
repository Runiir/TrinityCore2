"""Exact native accounting and pet reload guards for cast-free Beast Lore work."""
from copy import deepcopy
import math
from pathlib import Path
import re
import struct

from . import lab_runtime as lab
from .hunter_learn_contract import require, owned_snapshot
from .hunter_rest_accrual import native_rest, exact_row, RATE, FORMULA_SOURCE, bound

PRECISION_QUERY = ('SELECT guid,account,name,class,level,xp,online,rest_bonus,'
    'CAST(rest_bonus AS DOUBLE) AS exact_rest_bonus,logout_time,is_logout_resting '
    'FROM client442_characters.characters WHERE guid=6 AND account=2')
ACCOUNTING = {'totaltime', 'leveltime', 'logout_time', 'latency'}
POSE_KEYS = ('position_x', 'position_y', 'position_z', 'orientation', 'map')


def rest_sources():
    """Read the exact configured/native formula sources; no runtime SQL or input."""
    config = lab.ROOT / 'config/worldserver.conf'
    formula = lab.REPO / FORMULA_SOURCE
    rates = re.findall(r'^\s*' + re.escape(RATE) + r'\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(?:#.*)?$',
        config.read_text(), re.MULTILINE)
    require(len(rates) == 1 and float(rates[0]) == 1, 'exact native wilderness rest rate must be1')
    snippets = ['float bubble0 = 0.031f;', 'bubble0*sWorld->getRate(RATE_REST_OFFLINE_IN_WILDERNESS)',
        'SetRestBonus(GetRestBonus() + time_diff*((float)GetUInt32Value(PLAYER_NEXT_LEVEL_XP) / 72000)*bubble);']
    text = formula.read_text()
    require(all(v in text for v in snippets), 'native Hunter rest formula source differs')
    return {'rate': 1, 'config_source': bound(config), 'native_formula_source': bound(formula),
        'formula_snippets': snippets, 'native_float_storage_sources': [bound(lab.REPO / p) for p in (
            'src/server/database/Database/Field.cpp', 'src/server/database/Database/QueryResult.cpp',
            'src/server/database/Database/MySQLPreparedStatement.cpp', 'sql/base/characters_database.sql')]}


def precision(row, snapshot):
    hunter = owned_snapshot(snapshot)['native']
    require(all(row.get(k) == hunter.get(k) for k in ('guid', 'account', 'name', 'class', 'level', 'xp',
        'online', 'rest_bonus', 'logout_time', 'is_logout_resting')), 'exact FLOAT row differs from owned saved snapshot')
    exact_row(row, hunter['rest_bonus'])
    return row


def login_rest(before, after, entry, exact_before, exact_after, rate=1):
    """Each ordinary login has its own exact before/after SQL FLOAT observations."""
    exact_row(exact_before, before['rest_bonus'])
    exact_row(exact_after, after['rest_bonus'])
    require(exact_before['exact_rest_bonus'] < 5700 and exact_after['exact_rest_bonus'] < 5700,
        'capped rest cannot attribute an exact ordinary login interval')
    identity = ('guid', 'account', 'name', 'race', 'class', 'level', 'xp', 'is_logout_resting')
    require(tuple(before.get(k) for k in identity) == (6, 2, 'Harnesshunt', 1, 3, 10, 45, 0) and
        all(after.get(k) == before[k] for k in identity) and type(rate) in (int, float) and math.isfinite(rate) and rate == 1 and
        type(before.get('logout_time')) is int and before['logout_time'] > 0 and
        type(after.get('logout_time')) is int and after['logout_time'] >= before['logout_time'] and
        entry.get('phase') == 'owned_class_entered' and entry.get('actor', {}).get('guid') == 6 and
        entry.get('state', {}).get('xp_max') == 7600 and entry.get('state', {}).get('xp') == 45 and
        entry.get('state', {}).get('player') == 'Harnesshunt' and entry.get('state', {}).get('level') == 10 and
        entry.get('native_before_entry') == before and entry.get('entered_native') == {**before, 'online': 1} and
        type(entry.get('state', {}).get('xp_exhaustion')) is int and
        entry['state']['xp_exhaustion'] == 2 * int(exact_after['exact_rest_bonus']),
        'exact owned Hunter login baseline differs')
    packets = entry.get('login_packets', [])
    requests = [p for p in packets if p.get('name') == 'CMSG_PLAYER_LOGIN' and p.get('direction') == 'to_native']
    completions = [p for p in packets if p.get('name') == 'SMSG_LOGIN_VERIFY_WORLD' and p.get('direction') == 'from_native']
    require(len(requests) == len(completions) == 1 and
        all(type(p.get('time')) in (int, float) and math.isfinite(p['time']) for p in requests + completions) and
        type(entry.get('started_at')) in (int, float) and math.isfinite(entry['started_at']) and
        type(entry.get('finished_at')) in (int, float) and math.isfinite(entry['finished_at']) and
        all(p.get('session') == entry.get('native_session') for p in requests + completions) and
        entry['started_at'] <= requests[0]['time'] <= completions[0]['time'] <= entry['finished_at'] and
        0 <= completions[0]['time'] - requests[0]['time'] < 10,
        'one exact native login interval is required for rest preservation')
    matches = []
    for timestamp in range(math.floor(requests[0]['time']), math.floor(completions[0]['time']) + 1):
        seconds = timestamp - before['logout_time']
        if seconds < 0:
            continue
        exact, text = native_rest(exact_before['exact_rest_bonus'], seconds, 7600, rate)
        if exact == exact_after['exact_rest_bonus'] and text == after['rest_bonus']:
            matches.append({'native_login_second': timestamp, 'offline_seconds': seconds,
                'before_float32_bits': exact_before['exact_rest_bonus_float32_bits'],
                'after_float32_bits': exact_after['exact_rest_bonus_float32_bits'], 'exact_after': exact})
    require(len(matches) == 1, 'Hunter rest change lacks one exact source-bound ordinary login second')
    return {'matches': matches, 'rate': rate, 'rounded_baseline_reconstruction': False}


def parked_preservation(before, after, entry, exact_before, exact_after, money, saved, expected_pose=None):
    old, current = owned_snapshot(before), owned_snapshot(after)
    require(all(after[str(g)] == before[str(g)] for g in range(1, 6)), 'protected actors changed during learning')
    allowed = ACCOUNTING | {'rest_bonus', 'money'}
    expected_pose = expected_pose or [old['native'][k] for k in POSE_KEYS]
    require(set(current['native']) == set(old['native']) and
        [current['native'][k] for k in POSE_KEYS] == expected_pose and
        {k for k, v in old['native'].items() if current['native'].get(k) != v} <= allowed and
        all(type(snapshot['native'].get(k)) is int and snapshot['native'][k] >= 0
            for snapshot in (old, current) for k in ACCOUNTING) and
        all(current['native'][k] >= old['native'][k] for k in ('totaltime', 'leveltime', 'logout_time')) and
        current['native']['money'] == money and current['saved'] == saved and
        current['inventory'] == old['inventory'], 'Hunter saved, home pose or native accounting changed beyond the contract')
    old_pets, pets = {p['id']: p for p in old['pets']}, {p['id']: p for p in current['pets']}
    require(len(old['pets']) == len(current['pets']) == 2 and set(old_pets) == set(pets) == {4, 16} and pets[4] == old_pets[4] and
        pets[16]['curhealth'] == old_pets[16]['curhealth'] == 278 and
        pets[16]['CreatedBySpell'] == old_pets[16]['CreatedBySpell'] == 13481 and
        pets[16]['savetime'] >= old_pets[16]['savetime'] and
        {k: v for k, v in pets[16].items() if k not in ('CreatedBySpell', 'savetime')} ==
        {k: v for k, v in old_pets[16].items() if k not in ('CreatedBySpell', 'savetime')},
        'learning changed pet health, named identity or unrelated disposable metadata')
    return login_rest(old['native'], current['native'], entry, exact_before, exact_after)


def creator_expected(before, current, reload_proof):
    """Cast-free learning preserves the saved tame creator; no blind883 repair."""
    h = owned_snapshot(current)
    old = owned_snapshot(before)
    named, wolf = {p['id']: p for p in h['pets']}.get(4), {p['id']: p for p in h['pets']}.get(16)
    source = {p['id']: p for p in old['pets']}
    require(set(source) == {4, 16} and len(old['pets']) == len(h['pets']) == 2 and named == source[4] and
        wolf['CreatedBySpell'] == source[16]['CreatedBySpell'] == 13481 and
        wolf['curhealth'] == source[16]['curhealth'] == 278 and wolf['savetime'] >= source[16]['savetime'] and
        {k: v for k, v in wolf.items() if k not in ('CreatedBySpell', 'savetime')} ==
        {k: v for k, v in source[16].items() if k not in ('CreatedBySpell', 'savetime')} and
        reload_proof.get('owner') == 6 and reload_proof.get('pet_number') == 16 and
        reload_proof.get('created_by_spell') == 13481 and reload_proof.get('health') == 278 and
        reload_proof.get('native_reload_source_verified') is True,
        'cast-free learning cannot repair an unexplained disposable creator or health change')
    return deepcopy(current)
