"""Read the failed scout's crash state before and after ordinary service recovery.

These commands never start a process, send client input, or change SQL. The
coordinator performs native and bridge startup between ``before`` and ``after``.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import time

from . import lab_runtime as lab
from . import interaction_bag_swap_continuation as c
from .bag_swap_contract import require, strict_equal, finite
from .bag_swap_preservation import PRECISION_QUERY, exact_precision, float32_bits
from .bag_swap_sources import bound

SCHEMA = 'client442_bag_swap_offline_boundary_v1'
BEFORE_PHASE = 'bags_swap_crash_stale_captured'
PHASE = 'bags_swap_crash_restart_closed_excluded'
MAX_JSON = 2 * 1024 * 1024
MAX_JOURNAL = 128 * 1024 * 1024
CHUNK = 256 * 1024


def read(path, limit=MAX_JSON, expected=None):
    """One stable capped ordinary read, including the temporary crash diagnostic."""
    path = Path(path)
    require(path.is_absolute() and str(path.resolve()) == str(path) and
        not any(p.is_symlink() for p in (path, *path.parents)), 'ordinary absolute recovery source required')
    before = path.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit, 'recovery source exceeds byte bound')
    with path.open('rb') as handle:
        require(identity(os.fstat(handle.fileno())) == identity(before), 'recovery source changed before read')
        raw = handle.read(limit + 1)
        require(len(raw) == before.st_size and identity(os.fstat(handle.fileno())) == identity(before) and
            identity(path.stat()) == identity(before), 'recovery source changed during read')
    ref = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
    require(expected is None or ref == expected, 'immutable recovery source differs')
    value = json.loads(raw)
    require(type(value) is dict, 'ordinary recovery JSON object required')
    return value, ref


def write(path, value):
    path = Path(path)
    require(not path.exists(), 'recovery never overwrites an earlier receipt')
    with path.open('x') as handle:
        os.chmod(path, 0o600)
        json.dump(value, handle, sort_keys=True, separators=(',', ':'), allow_nan=False)
        handle.write('\n')
    return bound(path)


def copy_file(source, target, limit):
    source, target = Path(source), Path(target)
    require(source.is_file() and not any(p.is_symlink() for p in (source, *source.parents)) and
        not target.exists() and 0 < source.stat().st_size <= limit, 'bounded immutable recovery copy required')
    initial = source.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    digest, count = hashlib.sha256(), 0
    with source.open('rb') as src, target.open('xb') as dst:
        os.chmod(target, 0o600)
        for raw in iter(lambda: src.read(CHUNK), b''):
            count += len(raw)
            require(count <= limit, 'recovery copy exceeded byte bound')
            digest.update(raw)
            dst.write(raw)
    require(count == initial.st_size and identity(source.stat()) == identity(initial) and
        bound(source)['sha256'] == digest.hexdigest(),
        'source changed during recovery copy')
    return {'original_source': bound(source), 'copy_source': bound(target), 'bytes': count}


def absent(ready):
    previous = ready['runtime']
    game = ready['frame']['monitor']['input_isolation']['game_pid']
    require(type(game) is int and game > 0, 'source-owned old game PID required')
    checks = {k: c.gone(previous[k]['pid'], previous[k]['start_ticks']) for k in ('worldserver', 'modern_world')}
    checks['previous_client'] = c.gone(previous['client']['pid'], previous['client']['start_ticks'])
    checks['owned_game_pid'] = not Path('/proc', str(game)).exists()
    require(all(checks.values()), 'old owned service/client lifetimes must be absent')
    # A vanished launcher cannot authorize a surviving descendant in its group.
    groups = {v['pid'] for v in previous.values()}
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
        except (FileNotFoundError, ProcessLookupError):
            continue
        require(fields[0] == 'Z' or int(fields[2]) not in groups, 'old owned process group still has a live child')
    with c.scout_peer_primary():
        require(lab.owned_process('client') is None, 'primary client must remain absent')
    require(lab.owned_process('client') is None, 'scout client must remain absent')
    return checks, {'pid': game, 'source': bound(Path(ready['preparation_path']))}


def precision(snapshot):
    started = time.time()
    with lab.connection() as con, con.cursor() as q:
        q.execute(PRECISION_QUERY)
        rows = q.fetchall()
        require(len(rows) == 1, 'one actual original-scout FLOAT row required')
        row = dict(zip([column[0] for column in q.description], rows[0]))
    row = json.loads(json.dumps(row))
    row['exact_rest_bonus_float32_bits'] = float32_bits(row.get('exact_rest_bonus'))
    exact_precision(row, snapshot)
    return row, {'started_at': started, 'finished_at': time.time()}


def sources(arguments, out):
    values, refs = {}, {}
    for role, name in (('preparation', 'ready'), ('failed_entry', 'failed'), ('precision', 'precision'), ('idle', 'idle')):
        path = getattr(arguments, name)
        values[role], refs[role] = read(path)
        require(Path(path).is_relative_to(lab.ROOT / 'evidence'), 'actual private failed scout source required')
    diagnostic, original = read(arguments.diagnostic)
    copied = copy_file(arguments.diagnostic, out / 'crash_diagnostic.json', MAX_JSON)
    refs['diagnostic'] = copied['copy_source']
    refs['primary_stop'] = values['preparation']['predecessor']['primary_stop']
    c.primary_stopped(Path(refs['primary_stop']['path']))
    require(bound(refs['primary_stop']['path']) == refs['primary_stop'], 'original primary stop changed')
    require(diagnostic.get('source_refs', {}).get('actual_ready', {}).get('sha256') == refs['preparation']['sha256'] and
        diagnostic.get('source_refs', {}).get('immutable_original_failed_entry', {}).get('sha256') == refs['failed_entry']['sha256'],
        'crash diagnostic must retain the actual ready and failure sources')
    return values, refs, diagnostic, original


def journals(out, since, until):
    """Freeze the complete interval across every retained journal rotation."""
    from .observation.journal import entries, paths
    refs, observations = {}, {}
    for role, path in (('packets', lab.ROOT / 'evidence/world_packets.jsonl'),
            ('events', lab.ROOT / 'logs/modern_world.jsonl')):
        members = paths(path)
        require(members, 'complete available recovery journal required')
        originals = []
        for member in members:
            require(member.is_file() and not any(p.is_symlink() for p in (member, *member.parents)),
                'ordinary retained journal rotation required')
            if member.stat().st_size:
                with member.open('rb') as handle:
                    handle.seek(-1, os.SEEK_END)
                    require(handle.read(1) == b'\n', 'partial journal row cannot close a recovery boundary')
            originals.append({'source': bound(member), 'bytes': member.stat().st_size})
        target = out / (role + '.jsonl')
        count, size, first, last = 0, 0, None, None
        with target.open('xb') as handle:
            os.chmod(target, 0o600)
            for row in entries(path):
                require(type(row) is dict and finite(row.get('time')), 'complete journal rows require finite source times')
                if not since <= row['time'] <= until:
                    continue
                raw = (json.dumps(row, separators=(',', ':'), allow_nan=False) + '\n').encode()
                count += 1
                size += len(raw)
                require(count <= 250000 and len(raw) <= MAX_JSON and size <= MAX_JOURNAL,
                    'closed recovery journal interval exceeds its bound')
                handle.write(raw)
                first = row['time'] if first is None else min(first, row['time'])
                last = row['time'] if last is None else max(last, row['time'])
        require(count > 0 and paths(path) == members and all(bound(row['source']['path']) == row['source'] and
            Path(row['source']['path']).stat().st_size == row['bytes'] for row in originals),
            'retained journal rotations changed during interval capture')
        refs[role] = bound(target)
        observations[role] = {'source': refs[role], 'rows': count, 'bytes': size,
            'first_time': first, 'last_time': last, 'since': since, 'audit_until': until, 'rotations': originals}
    return refs, observations


def journal_rows(ref):
    require(bound(ref['path']) == ref, 'closed recovery journal changed')
    rows = []
    with Path(ref['path']).open('rb') as handle:
        for line in handle:
            require(line.endswith(b'\n') and len(line) <= MAX_JSON, 'complete bounded recovery journal row required')
            row = json.loads(line)
            require(type(row) is dict, 'recovery journal rows must be objects')
            rows.append(row)
            require(len(rows) <= 250000, 'recovery journal row bound exceeded')
    require(bound(ref['path']) == ref, 'closed recovery journal changed during replay')
    return rows


def service_files():
    from .world import control
    return {key: bound(path) for key, path in (
        ('native_binary', lab.ROOT / 'bin/worldserver'), ('native_config', lab.ROOT / 'config/worldserver.conf'),
        ('bridge_binary', control.BINARY), ('bridge_build_receipt', control.RECEIPT))}


def common(ready, refs):
    return {'schema': SCHEMA, 'controller': 'code', 'model': None, 'revision': None,
        'actor': deepcopy(ready['actor']), 'sources': refs, 'previous_runtime': deepcopy(ready['runtime']),
        'previous_client': deepcopy(ready['runtime']['client']), 'ready_baseline': ready['all_offline_snapshot'],
        'excluded_failed_entry': True, 'qualification_added': False, 'operations_admitted': 0,
        'input_sent': False, 'mutation_sent': False, 'bag_input_sent': False, 'normal_logout_input_sent': False,
        'custom_script_permission': 'blocked_by_user', 'softTargetInteract': deepcopy(c.SCRIPT_BOUNDARY),
        'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip()}


def before(arguments):
    from .bag_swap_offline_boundary import validate
    out = arguments.output
    require(out.is_absolute() and out.is_relative_to(lab.ROOT / 'evidence') and str(out.resolve()) == str(out) and
        not any(p.is_symlink() for p in out.parents) and not out.exists(),
        'new private crash observation directory required')
    out.mkdir(parents=True, mode=0o700)
    started = time.time()
    values, refs, diagnostic, original = sources(arguments, out)
    ready = values['preparation']
    ready['preparation_path'] = refs['preparation']['path']
    checks, game = absent(ready)
    require(not any(lab.owned_process(k) for k in ('worldserver', 'modern_world')), 'capture must precede owned service restart')
    snapshot = c.snapshot()
    require(strict_equal(snapshot, diagnostic['all_offline_snapshot']), 'fresh stale snapshot differs from crash diagnostic')
    row, query = precision(snapshot)
    require(strict_equal(row, diagnostic['exact_precision']['row']), 'fresh exact stale FLOAT differs from crash diagnostic')
    value = common(ready, refs)
    cutoff = time.time()
    journal_refs, journal_observations = journals(out, ready['finished_at'], cutoff)
    value.update(phase=BEFORE_PHASE, started_at=started, stale_snapshot=snapshot,
        old_process_absence=checks, owned_game_identity=game, diagnostic_original_source=original,
        exact_precision={'query': PRECISION_QUERY, 'before_row': row, 'after_row': deepcopy(row), 'before_query': query},
        journal_sources=journal_refs, journal_observations=journal_observations,
        journal_interval={'since': ready['finished_at'], 'audit_until': cutoff},
        current_services={},
        service_files=service_files(), completed=True, failure=None)
    # Raw run metadata is retained without exposing command/environment fields.
    value['old_run_metadata'] = {kind: copy_file(path, out / (kind + '.blob'), 1024 * 1024)
        for kind, path in (('worldserver', lab.ROOT / 'run/worldserver.json'),
            ('modern_world', lab.ROOT / 'run/modern_world.json'), ('client', lab.client_root() / 'run/client.json'))}
    require(strict_equal(c.snapshot(), snapshot), 'before observation changed persisted state')
    failed_image = Path(refs['failed_entry']['path']).parent / 'bags_swap_entered.png'
    value['original_failed_image'] = bound(failed_image)
    value['source_preservation'] = {role: {'before': ref, 'after': bound(ref['path'])} for role, ref in refs.items()}
    value['source_preservation']['failed_image'] = {'before': value['original_failed_image'], 'after': bound(failed_image)}
    value['finished_at'] = time.time()
    value['proof'] = validate(value, values['preparation'], values['failed_entry'], values['precision'], values['idle'],
        journal_rows(value['journal_sources']['packets']), journal_rows(value['journal_sources']['events']))
    result = write(out / 'boundary.json', value)
    print(json.dumps({'completed': True, 'phase': BEFORE_PHASE, 'source': result}))


def after(arguments):
    from .bag_swap_offline_boundary import validate
    from .bag_swap_projection import source_identities
    from .world import control
    out = arguments.output
    require(out.is_absolute() and out.is_relative_to(lab.ROOT / 'evidence') and str(out.resolve()) == str(out) and
        not any(p.is_symlink() for p in out.parents) and not out.exists(),
        'new private recovered observation directory required')
    original, original_ref = read(arguments.before)
    require(original.get('schema') == SCHEMA and original.get('phase') == BEFORE_PHASE and original.get('completed') is True,
        'actual completed pre-start crash observation required')
    out.mkdir(parents=True, mode=0o700)
    started = time.time()
    values = {role: read(original['sources'][role]['path'], expected=original['sources'][role])[0]
        for role in ('preparation', 'failed_entry', 'precision', 'idle')}
    ready = values['preparation']
    ready['preparation_path'] = original['sources']['preparation']['path']
    checks, game = absent(ready)
    current = {k: c.identity(k) for k in ('worldserver', 'modern_world')}
    control.native_command()
    require(all(current[k] != ready['runtime'][k] for k in current), 'both recovered services require new actual lifetimes')
    files = service_files()
    require(files == original['service_files'], 'ordinary recovery cannot replace binaries, build receipt or native config')
    snapshot = c.snapshot()
    row, query = precision(snapshot)
    cutoff = time.time()
    journal_refs, journal_observations = journals(out, original['journal_interval']['since'], cutoff)
    value = deepcopy(original)
    value.update(phase=PHASE, started_at=started, before_capture_source=original_ref,
        recovery_started_after=original['finished_at'],
        current_services=current, all_offline_snapshot=snapshot, old_process_absence=checks,
        owned_game_identity=game, journal_sources=journal_refs, journal_observations=journal_observations, service_files=files,
        committed_sources=source_identities(lab.REPO),
        code_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip())
    value['sources']['before_capture'] = original_ref
    value['source_preservation'] = {role: {'before': ref, 'after': bound(ref['path'])} for role, ref in value['sources'].items()}
    image = value['original_failed_image']
    value['source_preservation']['failed_image'] = {'before': image, 'after': bound(image['path'])}
    value['exact_precision'].update(after_row=row, after_query=query)
    value['journal_interval']['audit_until'] = cutoff
    value['finished_at'] = time.time()
    value['proof'] = validate(value, values['preparation'], values['failed_entry'], values['precision'],
        values['idle'], journal_rows(value['journal_sources']['packets']), journal_rows(value['journal_sources']['events']))
    require(strict_equal(c.snapshot(), snapshot) and {k: c.identity(k) for k in current} == current,
        'recovered observation changed saved state or service identity')
    print(json.dumps({'completed': True, 'phase': PHASE, 'source': write(out / 'boundary.json', value)}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='stage', required=True)
    capture = sub.add_parser('before')
    for name in ('ready', 'failed', 'precision', 'idle', 'diagnostic', 'output'):
        capture.add_argument('--' + name, type=Path, required=True)
    finish = sub.add_parser('after')
    for name in ('before', 'output'):
        finish.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    with c.scout():
        (before if args.stage == 'before' else after)(args)


if __name__ == '__main__':
    main()
