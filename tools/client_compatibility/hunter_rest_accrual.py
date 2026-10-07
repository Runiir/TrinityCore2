"""Attribute only the owned Hunter's exact native offline login rest accrual."""
import json
import math
from pathlib import Path
import re
import struct
from . import lab_runtime as lab


RATE = 'Rate.Rest.Offline.InWilderness'
FORMULA_SOURCE = Path('src/server/game/Entities/Player/Player.cpp')
PRECISION_QUERY = ('SELECT guid,account,name,class,level,xp,online,rest_bonus,CAST(rest_bonus AS DOUBLE) AS exact_rest_bonus,'
    'logout_time,is_logout_resting FROM client442_characters.characters WHERE guid=6 AND account=2')
REST_FAILURE = 'RuntimeError: Hunter rest bonus differs from exact source-bound native offline accrual'


def bound(path):
    path = Path(path)
    return {'path': str(path.resolve()), 'sha256': lab.sha256(path)}


def private_episode(path):
    path = Path(path)
    if path.is_symlink() or path.name != 'episode.json' or not path.resolve().is_relative_to(lab.ROOT / 'evidence'):
        raise RuntimeError('requires a private owned rest source episode')
    return path


def closed(path):
    value = json_source(private_episode(path))
    if value.get('completed') is not True or value.get('failure') is not None or not value.get('finished_at'):
        raise RuntimeError('rest source is not closed and successful')
    return value


def float32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def native_rest(before, seconds, xp_cap, rate):
    """Match native float operations and the SQL FLOAT text representation."""
    coefficient = float32(float32(xp_cap) / 72000)
    bubble = float32(float32(.031) * float32(rate))
    gained = float32(float32(seconds * coefficient) * bubble)
    result = min(float32(float32(before) + gained), float32(float32(xp_cap) * 1.5 / 2))
    return result, float(format(result, '.6g'))


def native_baselines(text_value):
    """Enumerate the complete IEEE float32 preimage of a six-digit SQL FLOAT value."""
    if (type(text_value) not in (int, float) or not math.isfinite(text_value) or not 0 <= text_value <= 5700 or
        float(format(text_value, '.6g')) != text_value):
        raise RuntimeError('requires the observed six-digit SQL FLOAT baseline')
    center, = struct.unpack('<I', struct.pack('<f', text_value))
    text = format(text_value, '.6g')
    result = []
    for direction in (-1, 1):
        for offset in range(1024):
            bits = center + direction * offset
            if bits < 0: break
            value, = struct.unpack('<f', struct.pack('<I', bits))
            if format(value, '.6g') != text: break
            if direction == -1 or offset: result.append(value)
        else: raise RuntimeError('SQL FLOAT preimage exceeds exact enumeration bound')
    return result


def exact_row(row, text_value):
    exact = row.get('exact_rest_bonus')
    if (type(exact) not in (float, int) or not math.isfinite(exact) or not 0 <= exact <= 5700 or
        float32(exact) != exact or row.get('exact_rest_bonus_float32_bits') != struct.pack('<f', exact).hex() or
        row.get('rest_bonus') != text_value or float(format(exact, '.6g')) != text_value):
        raise RuntimeError('exact SQL FLOAT bits or its observed text representation differ')


def accrual(before, after, entry, rate, precise_after=None):
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
    if precise_after is not None:
        exact_row(precise_after, after['rest_bonus'])
    matches = []
    baselines = native_baselines(before['rest_bonus']) if precise_after is not None else [before['rest_bonus']]
    for timestamp in range(math.floor(request[0]['time']), math.floor(verify[0]['time']) + 1):
        seconds = timestamp - before['logout_time']
        if seconds < 0: continue
        for baseline in baselines:
            native, stored = native_rest(baseline, seconds, state['xp_max'], rate)
            if (after['rest_bonus'] != stored or state.get('xp_exhaustion') != 2 * int(native) or
                precise_after is not None and native != precise_after['exact_rest_bonus']): continue
            proof = {'schema': 'client442_owned_hunter_native_offline_rest_v1', 'input_sent': False,
                'field_changed': after['rest_bonus'] != before['rest_bonus'], 'original_rest_bonus': before['rest_bonus'],
                'expected_db_rest_bonus': stored, 'expected_native_float32': native,
                'preserved_rest_bonus': after['rest_bonus'], 'previous_logout_time': before['logout_time'],
                'native_login_second': timestamp, 'offline_seconds': seconds, 'xp_cap': state['xp_max'],
                'wilderness_bubble': .031, 'rate': rate, 'public_xp_exhaustion': state['xp_exhaustion'],
                'login_packets': request + verify,
                'scope': 'Preserve exact automatic native offline login rest accrual; no rest bonus update or gameplay qualification.'}
            if precise_after is None: return proof
            proof.update(original_native_float32=baseline, original_native_float32_bits=struct.pack('<f', baseline).hex(),
                exact_after_float32_bits=precise_after['exact_rest_bonus_float32_bits'],
                exact_baseline_candidates=len(baselines), precision_method='unique_float32_inverse_of_exact_sql_double')
            matches.append(proof)
    if precise_after is not None and len(matches) == 1: return matches[0]
    raise RuntimeError('Hunter rest bonus differs from exact source-bound native offline accrual')


def precision_source(path, entry_ref, after):
    """Bind an immutable, read-only exact FLOAT observation to its offline closure."""
    p = closed(path)
    expected_checks = {'all_six_offline', 'all_saved_state_unchanged', 'hunter_identity', 'snapshot_rest_matches', 'exact_float32'}
    refs = p.get('sources', [])
    if (p.get('schema') != 'client442_owned_hunter_readonly_rest_precision_v1' or
        p.get('phase') != 'owned_hunter_readonly_rest_precision_complete' or
        p.get('input_sent') is not False or p.get('mutation_sent') is not False or p.get('qualification_added') is not False or
        p.get('query') != PRECISION_QUERY or set(p.get('checks', {})) != expected_checks or
        not all(v is True for v in p['checks'].values()) or len(refs) != 4 or refs[0] != entry_ref or
        p.get('before') != p.get('after') or set(p.get('before', {})) != {str(n) for n in range(1, 7)} or
        any(v['native']['online'] != 0 or v['native']['guid'] != int(n) for n, v in p['before'].items()) or
        p['before']['6']['native'] != after or
        tuple(after.get(k) for k in ('guid', 'account', 'name', 'race', 'class', 'level', 'xp', 'is_logout_resting')) !=
        (6, 2, 'Harnesshunt', 1, 3, 10, 45, 0)):
        raise RuntimeError('exact rest precision snapshot or source roles differ')
    values = []
    for ref in refs:
        source = private_episode(ref.get('path', ''))
        if bound(source) != ref: raise RuntimeError('exact rest precision source hash differs')
        values.append(json_source(source))
    entry, park, normalization, failed = values
    if (entry.get('phase') != 'owned_class_entered' or park.get('phase') != 'await_original_selection_review' or
        normalization.get('phase') != 'owned_revive_fixture_normalized' or
        any(v.get('completed') is not True or v.get('failure') is not None for v in (entry, park, normalization)) or
        park.get('runtime') != entry.get('runtime') or normalization.get('runtime') != entry.get('runtime') or
        park.get('actor') != entry.get('actor') or normalization.get('actor') != entry.get('actor') or
        park.get('fixture_source') != entry.get('fixture_source') or len(park.get('checks', {})) != 4 or
        not all(v is True for v in park['checks'].values()) or park.get('retained_class_fixture') != after or
        normalization.get('after') != p['before'] or normalization.get('sources', [])[-1:] != [refs[1]] or
        normalization.get('input_sent') is not False or normalization.get('qualification_added') is not False or
        failed.get('completed') is not False or failed.get('failure') != REST_FAILURE or failed.get('phase') is not None or
        failed.get('runtime') != entry.get('runtime') or failed.get('fixture_source') != entry.get('fixture_source') or
        failed.get('cases') != [] or failed.get('model') is not None or
        not entry['started_at'] < entry['finished_at'] <= park['started_at'] < park['finished_at'] <=
        normalization['started_at'] < normalization['finished_at'] <= failed['started_at'] <
        failed['finished_at'] <= p['started_at'] < p['finished_at']):
        raise RuntimeError('exact rest precision normal parking, normalization or failed-closure binding differs')
    row = p.get('row', {})
    if (any(row.get(k) != after.get(k) for k in ('guid', 'account', 'name', 'class', 'level', 'xp', 'online',
        'rest_bonus', 'logout_time', 'is_logout_resting'))):
        raise RuntimeError('exact rest precision owned SQL row differs from the preserved snapshot')
    exact_row(row, after['rest_bonus'])
    return p


def json_source(path):
    return json.loads(path.read_text())


def preservation(before, after, entry_ref, precision_path=None):
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
    precision = precision_source(precision_path, entry_ref, after) if precision_path is not None else None
    proof = accrual(before, after, entry, float(matches[0]), precision['row'] if precision else None)
    proof.update(entry_source=entry_ref, config_source=bound(config), native_formula_source=bound(source))
    if precision:
        proof['precision_source'] = bound(precision_path)
        proof['native_float_storage_sources'] = [bound(lab.REPO / p) for p in (
            'src/server/database/Database/Field.cpp', 'src/server/database/Database/QueryResult.cpp',
            'src/server/database/Database/MySQLPreparedStatement.cpp', 'sql/base/characters_database.sql')]
    return proof
