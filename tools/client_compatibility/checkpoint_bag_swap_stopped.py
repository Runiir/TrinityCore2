"""Close and publish the already system-stopped, excluded UI173 entry.

The close action makes fresh read-only SQL/process observations and new private
evidence copies. It never opens a client, sends input or stops a process. Use the
auth Pixi environment for close and the main Pixi environment for checkpoint.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from . import lab_runtime as lab
from .bag_swap_sources import bound, reference
from .item_actionbar_contract import require, finite, strict_equal
from .checkpoint_item_actionbar import write_exclusive
from . import bag_swap_stopped_evidence as evidence

MAX_ROWS, MAX_BYTES = 250000, 256 * 1024 * 1024
STOP_LOG_SHA = '821e6ce553a2ec6c1026a9e87d6b64d767a86f16f84e4985b7be43920597860c'


def _encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()


def _out(directory, output):
    directory, output = Path(directory), Path(output)
    require(directory == lab.ROOT / evidence.BATCH.rstrip('/') and directory.is_dir() and
        output.is_absolute() and output.parent == directory and not output.exists() and
        '..' not in output.parts and not any(p.is_symlink() for p in (directory, *directory.parents)),
        'one new immutable private stopped-entry output directory required')
    return directory, output


def current_checks(ready, observation, current):
    from . import interaction_bag_swap_continuation as continuation
    old, now = ready['all_offline_snapshot'], current
    require(strict_equal(now, observation['after']), 'fresh all-six offline snapshot changed since the actual stop observation')
    own = evidence.owned_snapshot(now)
    game = ready['frame']['monitor']['input_isolation']['game_pid']
    with continuation.scout_peer_primary():
        primary_absent = lab.owned_process('client') is None
    changes = {k for k in old['2']['native'] if not strict_equal(old['2']['native'][k], own['native'][k])}
    from .bag_swap_preservation import ACCOUNTING
    checks = {'scout_launcher_absent': lab.owned_process('client') is None,
        'observed_owned_game_pid_absent': not Path('/proc', str(game)).exists(),
        'all_characters_offline': all(value['native']['online'] == 0 for value in now.values()),
        'primary_still_stopped': primary_absent and strict_equal(now['1'], old['1']),
        'native_lifetime': continuation.identity('worldserver') == ready['runtime']['worldserver'],
        'bridge_lifetime': continuation.identity('modern_world') == ready['runtime']['modern_world'],
        'origin_registration': continuation.registration() == ready['actor'],
        'protected_five_snapshots_unchanged': all(strict_equal(now[g], old[g]) for g in ('1', '3', '4', '5', '6')),
        'all_saved_inventory_pets_unchanged': all(strict_equal(now[g][k], old[g][k])
            for g in old for k in ('saved', 'inventory', 'pets')),
        'actor2_native_changes_confined_to_accounting_rest': set(old['2']['native']) == set(own['native']) and
            changes <= ACCOUNTING | {'rest_bonus'}}
    require(strict_equal(checks, dict.fromkeys(evidence.STOP_CHECKS, True)),
        'fresh system-stop verification must pass all ten actual source-shaped checks')
    require(not any((lab.ROOT / 'run' / name).exists() for name in (
        'owned_pet_abandon_probe.json', 'owned_tame_request_probe.json',
        'owned_stable_request_probe.json', 'owned_entry_request_probe.json')),
        'stopped-entry proof cannot coexist with an armed gameplay probe')
    return checks


def code_epoch(output, ready):
    from .bag_swap_projection import source_identities, STOPPED_SOURCE_FILES
    from .bag_swap_failed_sources import CODE_SCHEMA, MAX_SOURCE_BYTES, MAX_TOTAL_BYTES
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip()
    refs = source_identities(lab.REPO)
    old = {row['path']: row['sha256'] for row in ready['committed_sources']}
    expected = sorted(set(old) | {str(lab.REPO / member) for member in (*evidence.NEW_FILES, *STOPPED_SOURCE_FILES)})
    require(commit != evidence.OLD_COMMIT and [row['path'] for row in refs] == expected and
        all(row['sha256'] == old[row['path']] for row in refs if row['path'] in old and
            str(Path(row['path']).relative_to(lab.REPO)) not in evidence.CHANGED_OLD),
        'current committed package must preserve the bounded original epoch transition')
    prepared, total = [], 0
    for ref in refs:
        member = str(Path(ref['path']).relative_to(lab.REPO))
        raw = subprocess.check_output(['git', 'show', commit + ':' + member], cwd=lab.REPO)
        total += len(raw)
        require(len(raw) <= MAX_SOURCE_BYTES and total <= MAX_TOTAL_BYTES and
            hashlib.sha256(raw).hexdigest() == ref['sha256'], 'complete source bytes must match actual committed Git objects')
        prepared.append((ref, raw))
    target = output / 'code_sources'
    target.mkdir(mode=0o700)
    copies = []
    for index, (ref, raw) in enumerate(prepared):
        value = {'schema': CODE_SCHEMA, 'code_commit': commit, 'original_path': ref['path'],
            'sha256': ref['sha256'], 'bytes': len(raw), 'raw_hex': raw.hex()}
        path = target / (f'{index:03d}_' + ref['sha256'] + '.json')
        write_exclusive(path, _encoded(value))
        copies.append(bound(path))
    return {'schema': evidence.EPOCH_SCHEMA, 'code_commit': commit, 'committed_sources': refs, 'carried_sources': copies}


def journal_rows(path, since, until, sessions):
    from .observation.journal import entries
    rows = []
    for row in entries(path):
        require(type(row) is dict, 'all journal rows must be dictionaries')
        if row.get('session') in sessions or row.get('account_id') == 2 or row.get('guid') == 2:
            require(finite(row.get('time')), 'malformed attributable time cannot be filtered out')
        if finite(row.get('time')) and since <= row['time'] <= until:
            require(not ('AUTH_SESSION' in str(row.get('name', '')) and 'body' in row),
                'closed journals cannot retain authentication bodies')
            rows.append(row)
            require(len(rows) <= MAX_ROWS, 'complete stopped journal exceeds its bounded rows')
    require(rows, 'complete stopped-entry journal is absent')
    return rows


def retain_journals(output, ready, failed, until):
    physical = {row['session'] for row in failed['raw_entry_events'] if
        row.get('event') == 'instance_authenticated' and row.get('account_id') == 2}
    require(len(physical) == 1, 'one original physical login instance required')
    sessions = physical | {ready['native_session']}
    paths = {'packets': lab.ROOT / 'evidence/world_packets.jsonl', 'events': lab.ROOT / 'logs/modern_world.jsonl'}
    rows, refs = {}, {}
    for role, path in paths.items():
        values = journal_rows(path, ready['started_at'], until, sessions)
        target = output / (role + '.jsonl')
        raw = b''.join(_encoded(value) for value in values)
        require(len(raw) <= MAX_BYTES, 'bounded stopped journal bytes exceeded')
        write_exclusive(target, raw)
        rows[role], refs[role] = values, bound(target)
    return rows, refs


def close(directory, output, stop_log):
    from .bag_swap_source_index import local_sources, preload_ancestor_sources, prove_ancestors, build_source_index
    from .bag_swap_stopped_contract import stopped_history
    from . import interaction_bag_swap_continuation as continuation
    from .interaction_bag_swap_failed_entry_pause import read_precision
    directory, output = _out(directory, output)
    started = time.time()
    store = local_sources(directory)
    old = evidence.historical(store, evidence.SOURCES)
    ready, failed, observation, precision = (old[k] for k in ('preparation', 'failed_entry', 'observation', 'precision'))
    require(started > observation['observed_at'], 'the new closure must be captured after the actual stop observation')
    extra_sources = preload_ancestor_sources(store, ready)
    prove_ancestors(store, ready)
    # The builder and final validator each load their own byte-verified view.
    # Retain only the small historical boundary documents between those reads.
    del store
    stop_log = Path(stop_log)
    require(stop_log.is_file() and not stop_log.is_symlink() and stop_log.stat().st_size <= 4096 and
        bound(stop_log)['sha256'] == STOP_LOG_SHA, 'the actual committed stop-client output bytes required')
    stop_bytes = stop_log.read_bytes()
    require(stop_bytes == f"Sent SIGTERM to owned client process group {ready['runtime']['client']['pid']}\n".encode(),
        'system-stop output must bind the original owned launcher PID')
    with continuation.scout():
        before = continuation.snapshot()
        checks = current_checks(ready, observation, before)
        before_query_started = time.time()
        row = read_precision(before)
        before_query_finished = time.time()
        require(strict_equal(row, observation['exact_after_precision']['row']),
            'fresh exact FLOAT differs from the actual one-login stopped observation')
        require(strict_equal(continuation.snapshot(), before), 'read-only exact query changed the current all-six snapshot')
        until = time.time()
        output.mkdir(mode=0o700)
        try:
            rows, refs = retain_journals(output, ready, failed, until)
            history = stopped_history(rows['packets'], rows['events'], ready, failed, observation, precision, audit_until=until)
            epoch = code_epoch(output, ready)
            log_path = output / 'owned_stop_output.log'
            write_exclusive(log_path, stop_bytes)
            index_ref = build_source_index(directory, output / 'source_index.json', extra_sources=extra_sources)
            closure = {'schema': evidence.SCHEMA, 'phase': evidence.PHASE,
                'controller': 'code', 'model': None, 'revision': None, 'actor': ready['actor'], 'runtime': ready['runtime'],
                'started_at': started, 'audit_until': until,
                'code_commit': epoch['code_commit'], 'committed_sources': epoch['committed_sources'], 'code_source_epoch': epoch,
                'prior_code_epoch_source': ready['current_code_epoch_source'], 'sources': deepcopy(evidence.SOURCES),
                'authority_source': ready['authority_source'], 'runtime_authority_source': ready['runtime_authority_source'],
                'source_index_source': index_ref, 'predecessor': ready['predecessor'],
                'before': before,
                'journal_interval': {'from': ready['started_at'], 'until': until}, 'journal_sources': refs, 'history': history,
                'owned_game_identity': {'pid': observation['observed_owned_game_pid'],
                    'source': evidence.SOURCES['preparation'], 'frame': ready['frame']},
                'stop_log_source': bound(log_path), 'stop_action': observation['stop_action'],
                'entry_input_sent': True, 'bag_input_sent': False, 'normal_logout_input_sent': False,
                'input_sent': False, 'mutation_sent': False, 'qualification_added': False, 'operations_admitted': 0,
                'excluded_failed_entry': True, 'cases': [], 'cleanup': [],
                'custom_script_permission': 'blocked_by_user', 'softTargetInteract': evidence.SCRIPT}
            fresh_store = local_sources(directory)
            final_old = evidence.historical(fresh_store, closure['sources'])
            evidence._source_proof(fresh_store, closure, final_old)
            del fresh_store
            validated_at = time.time()
            final_before = continuation.snapshot()
            require(strict_equal(final_before, before),
                'full proof/source replay cannot stale the current offline precondition')
            after_query_started = time.time()
            final_row = read_precision(final_before)
            after_query_finished = time.time()
            require(strict_equal(final_row, row) and strict_equal(final_row, observation['exact_after_precision']['row']),
                'fresh final exact FLOAT differs after the complete source replay')
            after = continuation.snapshot()
            require(strict_equal(after, before), 'the final exact query changed the current all-six snapshot')
            final_checks = current_checks(ready, observation, after)
            require(checks == final_checks, 'process/runtime/offline checks changed after the final exact query')
            closure.update(completed=True, failure=None, finished_at=time.time(), source_validation_finished_at=validated_at,
                after=after, all_offline_snapshot=after, stop_checks=final_checks,
                exact_precision={'query': evidence.PRECISION_QUERY, 'before_row': row, 'after_row': final_row,
                    'before': before, 'after': after, 'input_sent': False, 'mutation_sent': False,
                    'before_query_started_at': before_query_started, 'before_query_finished_at': before_query_finished,
                    'after_query_started_at': after_query_started, 'after_query_finished_at': after_query_finished})
            evidence._boundary(closure, final_old)
            path = output / 'closure.json'
            write_exclusive(path, _encoded(closure))
            return bound(path)
        except BaseException as error:
            path = output / 'failed_collection.json'
            if not path.exists():
                write_exclusive(path, _encoded({'schema': 'client442_bag_swap_stopped_collection_failure_v1',
                    'started_at': started, 'finished_at': time.time(), 'completed': False,
                    'failure': f'{type(error).__name__}: {error}', 'input_sent': False, 'mutation_sent': False,
                    'qualification_added': False, 'operations_admitted': 0}))
            raise


def checkpoint(directory, name):
    from .bag_swap_source_index import local_sources
    from .checkpoint_bag_swap_failed import complete_tracking_manifest
    from .checkpoint_interactions import checkpoint as publish
    directory = Path(directory)
    require(directory == lab.ROOT / evidence.BATCH.rstrip('/'), 'only the actual excluded UI173 batch may be checkpointed')
    store = local_sources(directory)
    values = [value for value in store.data.values() if type(value) is dict and
        value.get('schema') == evidence.SCHEMA and value.get('phase') == evidence.PHASE]
    require(len(values) == 1, 'one validated completed stopped boundary required before publication')
    evidence.validate_closure(store, values[0])
    publish(directory, name)
    complete_tracking_manifest(directory)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='stage', required=True)
    cap = sub.add_parser('close')
    cap.add_argument('--directory', type=Path, required=True)
    cap.add_argument('--output', type=Path, required=True)
    cap.add_argument('--stop-log', type=Path, required=True)
    publish = sub.add_parser('checkpoint')
    publish.add_argument('--directory', type=Path, required=True)
    publish.add_argument('--name', required=True)
    args = parser.parse_args()
    result = close(args.directory, args.output, args.stop_log) if args.stage == 'close' else checkpoint(args.directory, args.name)
    if result is not None:
        print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
