"""Attribute only the owned Hunter's exact native offline login rest accrual."""
import math
from pathlib import Path
import re
import struct
from . import lab_runtime as lab
from .interaction_hunter_stable_slots import bound
from .interaction_retained_class_fixture import closed


RATE = 'Rate.Rest.Offline.InWilderness'
FORMULA_SOURCE = Path('src/server/game/Entities/Player/Player.cpp')


def float32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def native_rest(before, seconds, xp_cap, rate):
    """Match native float operations and the SQL FLOAT text representation."""
    coefficient = float32(float32(xp_cap) / 72000)
    bubble = float32(float32(.031) * float32(rate))
    gained = float32(float32(seconds * coefficient) * bubble)
    result = min(float32(float32(before) + gained), float32(float32(xp_cap) * 1.5 / 2))
    return result, float(format(result, '.6g'))


def accrual(before, after, entry, rate):
    """Accept the exact observed value from a native login interval, without mutation."""
    identity = ('guid', 'account', 'name', 'race', 'class', 'level', 'xp', 'is_logout_resting')
    if (tuple(before.get(k) for k in identity) != (6, 2, 'Harnesshunt', 1, 3, 10, 45, 0) or
        any(after.get(k) != before[k] for k in identity) or
        not all(type(v) in (float, int) and math.isfinite(v) and 0 <= v <= 5700 for v in
            (before.get('rest_bonus'), after.get('rest_bonus'))) or type(rate) not in (float, int) or rate != 1 or
        type(before.get('logout_time')) is not int or before['logout_time'] <= 0 or
        entry.get('phase') != 'owned_class_entered' or entry.get('actor', {}).get('guid') != 6):
        raise RuntimeError('requires exact owned wilderness Hunter login rest accrual')
    loaded = entry.get('entered_native', {})
    state = entry.get('state', {})
    if (any(loaded.get(k) != before[k] for k in identity + ('rest_bonus', 'logout_time')) or
        state.get('xp_max') != 7600 or state.get('xp') != 45 or state.get('level') != 10 or
        state.get('player') != 'Harnesshunt' or not entry.get('native_session')):
        raise RuntimeError('native pre-login rest baseline or public XP cap differs')
    packets = entry.get('login_packets', [])
    request = [p for p in packets if p.get('name') == 'CMSG_PLAYER_LOGIN' and p.get('direction') == 'to_native']
    verify = [p for p in packets if p.get('name') == 'SMSG_LOGIN_VERIFY_WORLD' and p.get('direction') == 'from_native']
    if (len(request) != 1 or len(verify) != 1 or any(p.get('session') != entry['native_session'] for p in packets) or
        not all(type(p.get('time')) in (int, float) and math.isfinite(p['time']) for p in request + verify) or
        not entry['started_at'] <= request[0]['time'] <= verify[0]['time'] <= entry['finished_at'] or
        not 0 <= verify[0]['time'] - request[0]['time'] < 10):
        raise RuntimeError('exact native login request and completion window differs')
    for timestamp in range(math.floor(request[0]['time']), math.floor(verify[0]['time']) + 1):
        seconds = timestamp - before['logout_time']
        if seconds < 0: continue
        native, stored = native_rest(before['rest_bonus'], seconds, state['xp_max'], rate)
        if after['rest_bonus'] == stored and state.get('xp_exhaustion') == 2 * int(native):
            return {'schema': 'client442_owned_hunter_native_offline_rest_v1', 'input_sent': False,
                'field_changed': after['rest_bonus'] != before['rest_bonus'], 'original_rest_bonus': before['rest_bonus'],
                'expected_db_rest_bonus': stored, 'expected_native_float32': native,
                'preserved_rest_bonus': after['rest_bonus'], 'previous_logout_time': before['logout_time'],
                'native_login_second': timestamp, 'offline_seconds': seconds, 'xp_cap': state['xp_max'],
                'wilderness_bubble': .031, 'rate': rate, 'public_xp_exhaustion': state['xp_exhaustion'],
                'login_packets': request + verify,
                'scope': 'Preserve exact automatic native offline login rest accrual; no rest bonus update or gameplay qualification.'}
    raise RuntimeError('Hunter rest bonus differs from exact source-bound native offline accrual')


def preservation(before, after, entry_ref):
    path = Path(entry_ref.get('path', ''))
    if path.is_symlink() or bound(path) != entry_ref:
        raise RuntimeError('rest accrual native entry source hash differs')
    entry = closed(path)
    config = lab.ROOT / 'config/worldserver.conf'
    matches = re.findall(r'^\s*' + re.escape(RATE) + r'\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(?:#.*)?$',
        config.read_text(), re.MULTILINE)
    if len(matches) != 1:
        raise RuntimeError('rest accrual requires one explicit native wilderness rate')
    source = lab.REPO / FORMULA_SOURCE
    text = source.read_text()
    if not all(value in text for value in ('float bubble0 = 0.031f;',
        'bubble0*sWorld->getRate(RATE_REST_OFFLINE_IN_WILDERNESS)',
        'SetRestBonus(GetRestBonus() + time_diff*((float)GetUInt32Value(PLAYER_NEXT_LEVEL_XP) / 72000)*bubble);')):
        raise RuntimeError('native rest accrual formula source changed')
    proof = accrual(before, after, entry, float(matches[0]))
    proof.update(entry_source=entry_ref, config_source=bound(config), native_formula_source=bound(source))
    return proof
