"""Retain complete journals for the excluded, actually stopped UI172 entry.

The journals action is read only apart from new private evidence copies. The
checkpoint action delegates to the existing DVCLive/DVC publisher. Neither
action changes qualification counts or the immutable failed closure.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time

from . import lab_runtime as lab
from .bag_swap_sources import bound, reference
from .item_actionbar_contract import finite, require, strict_equal
from .checkpoint_item_actionbar import write_exclusive

SCHEMA = 'client442_bag_swap_failed_journals_v1'
MAX_ROWS, MAX_BYTES = 250000, 128 * 1024 * 1024


def load_journal(ref):
    reference(ref)
    path = Path(ref['path'])
    require(path.is_relative_to(lab.ROOT / 'evidence') and bound(path) == ref and
        path.stat().st_size <= MAX_BYTES, 'immutable bounded failed-closure journal required')
    rows = []
    with path.open() as handle:
        for line in handle:
            require(line.endswith('\n'), 'complete failed-closure journal lines required')
            rows.append(json.loads(line))
            require(len(rows) <= MAX_ROWS, 'failed-closure journal exceeds bounded rows')
    require(bound(path) == ref, 'failed-closure journal changed during reading')
    return rows


def selected_rows(path, since, until, sessions):
    from .observation.journal import entries
    rows = []
    for row in entries(path):
        require(type(row) is dict, 'journal rows must be objects')
        if row.get('session') in sessions or row.get('account_id') == 2 or row.get('guid') == 2:
            require(finite(row.get('time')), 'malformed attributable journal time cannot be filtered out')
        if finite(row.get('time')) and since <= row['time'] <= until:
            require(not ('AUTH_SESSION' in str(row.get('name', '')) and 'body' in row),
                'failed-closure journals cannot retain authentication bodies')
            rows.append(row)
            require(len(rows) <= MAX_ROWS, 'complete failed-closure journal exceeds bounded rows')
    require(rows, 'complete failed-closure journal is absent')
    return rows


def code_epoch(directory, closure):
    """Copy the actual new committed package; never relabel the old pause epoch."""
    from .bag_swap_projection import source_identities
    from .bag_swap_failed_evidence import PUBLICATION_FILES, PUBLICATION_DEPENDENCIES
    from .bag_swap_failed_sources import CODE_SCHEMA, MAX_SOURCE_BYTES, MAX_TOTAL_BYTES
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip()
    refs = source_identities(lab.REPO)
    paths = {ref['path'] for ref in refs}
    for member in PUBLICATION_DEPENDENCIES:
        path = lab.REPO / member
        if str(path) in paths:
            continue
        raw = subprocess.check_output(['git', 'show', 'HEAD:' + member], cwd=lab.REPO)
        ref = bound(path)
        require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'publication dependency differs from actual Git HEAD')
        refs.append(ref)
    refs.sort(key=lambda ref: ref['path'])
    old = {ref['path']: ref['sha256'] for ref in closure['committed_sources']}
    expected = set(old) | {str(lab.REPO / member) for member in (*PUBLICATION_FILES, *PUBLICATION_DEPENDENCIES)}
    require(commit != closure['code_commit'] and [ref['path'] for ref in refs] == sorted(expected) and
        all(ref['sha256'] == old[ref['path']] for ref in refs if ref['path'] in old),
        'new publication epoch must preserve the exact stopped closure source package')
    prepared, total = [], 0
    for ref in refs:
        member = str(Path(ref['path']).relative_to(lab.REPO))
        raw = subprocess.check_output(['git', 'show', commit + ':' + member], cwd=lab.REPO)
        total += len(raw)
        require(len(raw) <= MAX_SOURCE_BYTES and total <= MAX_TOTAL_BYTES and
            hashlib.sha256(raw).hexdigest() == ref['sha256'], 'publication code must match actual committed Git bytes')
        prepared.append((ref, raw))
    target = directory / 'code_sources'
    target.mkdir(mode=0o700)
    copies = []
    for index, (ref, raw) in enumerate(prepared):
        value = {'schema': CODE_SCHEMA, 'code_commit': commit, 'original_path': ref['path'],
            'sha256': ref['sha256'], 'bytes': len(raw), 'raw_hex': raw.hex()}
        path = target / (f'{index:03d}_' + ref['sha256'] + '.json')
        write_exclusive(path, (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode())
        copies.append(bound(path))
    return {'code_commit': commit, 'committed_sources': refs, 'carried_sources': copies}


def journal_snapshot(directory, closure, output):
    from .interaction_bag_swap_failed_entry_pause import LocalSources
    from .bag_swap_failed_evidence import _CLOSURE_SOURCE
    from .bag_swap_failed_sources import validate_failed_pause
    from .bag_swap_failed_journals import validate_journals
    directory, closure, output = Path(directory), Path(closure), Path(output)
    require(directory.is_absolute() and directory.parent == lab.ROOT / 'evidence' and directory.is_dir() and
        closure.is_absolute() and output.is_absolute() and closure.is_relative_to(directory) and
        not any('..' in path.parts for path in (directory, closure, output)) and
        output.parent == directory and not output.exists() and
        not any(p.is_symlink() for p in (directory, *directory.parents)),
        'one new private excluded-closure journal directory required')
    started = time.time()
    closure_ref = bound(closure)
    require(closure_ref == _CLOSURE_SOURCE, 'collector requires the actual immutable stopped UI172 closure')
    store = LocalSources()
    pause = store.get(closure_ref)
    validate_failed_pause(store, pause)
    ready_ref = pause['original_preparation_source']
    ready = store.get(ready_ref)
    failed = store.get(pause['original_entry_source'])
    require(started > pause['finished_at'], 'journals must be captured after the actual stopped closure')
    sessions = {ready['native_session'], pause['failed_history']['instance_session']}
    interval = {'from': ready['started_at'], 'until': pause['finished_at']}
    paths = {'packets': lab.ROOT / 'evidence/world_packets.jsonl', 'events': lab.ROOT / 'logs/modern_world.jsonl'}
    rows = {role: selected_rows(path, interval['from'], interval['until'], sessions) for role, path in paths.items()}
    prior = {role: load_journal(pause['journal_sources'][role]) for role in paths}
    proof = validate_journals(rows['packets'], rows['events'], ready, failed, pause,
        prior['packets'], prior['events'])
    # Preflight all original source/native guards before creating this new copy.
    output.mkdir(mode=0o700)
    refs = {}
    for role, values in rows.items():
        raw = ''.join(json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n' for row in values).encode()
        require(len(raw) <= MAX_BYTES, 'complete failed-closure journal exceeds bounded bytes')
        target = output / (role + '.jsonl')
        write_exclusive(target, raw)
        refs[role] = bound(target)
    epoch = code_epoch(output, pause)
    receipt = {'schema': SCHEMA, 'completed': True, 'failure': None, 'closure_source': closure_ref,
        'preparation_source': ready_ref, 'started_at': started, 'finished_at': time.time(),
        'controller': 'code', 'model': None, 'revision': None, 'actor': pause['actor'], 'runtime': pause['runtime'],
        'code_commit': epoch['code_commit'], 'code_source_epoch': epoch, 'input_sent': False, 'mutation_sent': False,
        'qualification_added': False, 'operations_admitted': 0, 'excluded_failed_entry': True,
        'journal_interval': interval, 'journal_sources': refs, 'journal_proof': proof}
    require(bound(closure) == closure_ref, 'immutable failed closure changed during journal capture')
    write_exclusive(output / 'journal_receipt.json', (json.dumps(receipt, indent=2, allow_nan=False) + '\n').encode())
    return receipt


def checkpoint(directory, name):
    from .checkpoint_interactions import checkpoint as publish
    directory = Path(directory)
    publish(directory, name)
    return complete_tracking_manifest(directory)


def complete_tracking_manifest(directory):
    """Bind every actual generic tracking file, including both full journals."""
    directory = Path(directory)
    require(directory.is_absolute() and directory.parent == lab.ROOT / 'evidence' and directory.is_dir() and
        '..' not in directory.parts and
        not any(p.is_symlink() for p in (directory, *directory.parents)), 'actual named private checkpoint required')
    receipt = directory / 'checkpoint_receipt.json'
    before = bound(receipt)
    value = json.loads(receipt.read_text())
    require(bound(receipt) == before and value.get('cloud_verified') is True,
        'new actual checkpoint must already be synchronized')
    require(type(value.get('file')) is str and not Path(value['file']).is_absolute() and
        '..' not in Path(value['file']).parts and value['file'].startswith('artifacts/client_harness/') and
        value['file'].endswith('.tar.gz'), 'actual repository checkpoint archive path required')
    archive_path = lab.REPO / value['file']
    require(archive_path.is_file() and not any(p.is_symlink() for p in (archive_path, *archive_path.parents)) and
        archive_path.stat().st_size == value['bytes'] and bound(archive_path)['sha256'] == value['sha256'],
        'actual just-published archive identity changed')
    tracking = {'tracking/packets.jsonl', 'tracking/events.jsonl'}
    require(not any(row.get('path', '').startswith('tracking/') for row in value['file_manifest']),
        'complete tracking manifest may be added only once to the new checkpoint')
    rows, seen, metadata = [], set(), None
    with tarfile.open(archive_path, 'r|gz') as archive:
        for member in archive:
            if not member.name.startswith('tracking/') or member.isdir():
                continue
            require(member.isfile() and member.name not in seen and '..' not in Path(member.name).parts,
                'unique ordinary actual tracking files required')
            is_metadata = member.name == 'tracking/checkpoint.json'
            require(not is_metadata or (metadata is None and member.size <= 16 * 1024 * 1024),
                'one bounded actual generic checkpoint metadata member required')
            digest, size, chunks = hashlib.sha256(), 0, []
            with archive.extractfile(member) as handle:
                while raw := handle.read(1024 * 1024):
                    digest.update(raw)
                    size += len(raw)
                    if is_metadata:
                        require(size <= 16 * 1024 * 1024, 'bounded actual generic metadata required')
                        chunks.append(raw)
            require(size == member.size, 'actual complete tracking journal size differs')
            if is_metadata:
                metadata = json.loads(b''.join(chunks))
            rows.append({'path': member.name, 'bytes': size, 'sha256': digest.hexdigest()})
            seen.add(member.name)
    require(type(metadata) is dict and metadata.get('schema') == 'client442_interaction_checkpoint_v1' and
        strict_equal(metadata.get('files'), value['file_manifest']),
        'actual archived generic manifest must equal the original external manifest before tracking extension')
    require(tracking <= seen and bound(archive_path)['sha256'] == value['sha256'] and bound(receipt) == before,
        'complete actual archive or checkpoint changed during journal hashing')
    value['file_manifest'] += sorted(rows, key=lambda row: row['path'])
    temporary = directory / 'checkpoint_receipt_complete.tmp'
    write_exclusive(temporary, (json.dumps(value, indent=2) + '\n').encode())
    os.replace(temporary, receipt)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('journals', 'checkpoint'))
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--closure', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--name')
    args = parser.parse_args()
    if args.action == 'journals':
        require(args.closure is not None and args.output is not None, 'journals requires actual closure and new output')
        result = journal_snapshot(args.directory, args.closure, args.output)
        print(json.dumps({'closure_source': result['closure_source'], 'journal_sources': result['journal_sources'],
            'qualification_added': False, 'operations_admitted': 0}), flush=True)
    else:
        require(type(args.name) is str and args.name, 'checkpoint requires its explicit archive name')
        checkpoint(args.directory, args.name)


if __name__ == '__main__':
    main()
