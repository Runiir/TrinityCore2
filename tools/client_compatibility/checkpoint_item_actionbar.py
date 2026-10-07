"""Carry exact UI170 authority bytes before using the unchanged publisher.

Only the explicit ``checkpoint`` action publishes. ``carry`` performs local
private file copies, without launching, SQL, game inputs, or ledger admission.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat

from . import lab_runtime as lab
from .item_actionbar_contract import require
from .item_actionbar_sources import bound, closed, private_json, reference
from .item_actionbar_evidence import ANCESTRY_SCHEMA

MAX_SOURCES = 128
PREDECESSOR_ROLES = frozenset(('closure', 'pause', 'remote', 'checkpoint', 'primary_stop'))
EPISODE_REFS = frozenset(('source', 'fixture_source', 'entry_source', 'purchase_source',
    'preparation_source', 'restoration_source', 'park_source', 'precision_source',
    'creator_normalization_source', 'rest_baseline_source', 'cleaned_source',
    'original_finish_source', 'previous_preparation_source', 'action_cleanup_source',
    'capture_source', 'observation_settlement_source', 'cleanup_failed_source',
    'failed_source', 'failed_repair_source'))
OPAQUE_REFS = frozenset(('remote_source', 'checkpoint_source', 'primary_stop_source'))
NESTED_REFS = {
    'baseline': ('entry_source', 'rest_baseline_source', 'precision_source'),
    'trainer_identity': ('entry_source', 'spawn_source'),
    'observation_reconciliation': ('source', 'selected_source'),
    'reconciliation_preconditions': ('source', 'selected_source'),
}


def source_graph(predecessor, resolver, *, root=None, limit=MAX_SOURCES):
    """Derive only known JSON edges; verified earlier authorities remain opaque.

    ``resolver(ref)`` must return the JSON object from its exact original bytes.
    Archive callers can supply a digest-checked store, without local reads.
    """
    from .item_actionbar_sources import ROLES
    root = Path(root or lab.ROOT)
    require(type(predecessor) is dict and set(predecessor) == PREDECESSOR_ROLES and callable(resolver) and
        type(limit) is int and 0 < limit <= MAX_SOURCES, 'complete bounded predecessor graph arguments are required')

    def checked(ref):
        reference(ref)
        path = Path(ref['path'])
        require(path.is_relative_to(root / 'evidence') and path.suffix == '.json' and
            str(path) == ref['path'], 'ancestry edges must be original private absolute JSON references')
        return ref

    for ref in predecessor.values():
        checked(ref)
    batch = Path(predecessor['closure']['path']).parent.parent
    queue = [(ref, role in ('closure', 'pause')) for role, ref in predecessor.items()]
    seen, values, expanded = {}, {}, set()

    def add(ref, expand=True):
        checked(ref)
        queue.append((ref, expand))

    while queue:
        ref, expand = queue.pop(0)
        checked(ref)
        path, digest = ref['path'], ref['sha256']
        require(path not in seen or seen[path] == digest, 'one ancestry source path has conflicting digests')
        if path not in seen:
            require(len(seen) < limit, 'UI170 JSON ancestry exceeds the bounded source count')
            try:
                value = resolver(ref)
            except (FileNotFoundError, KeyError, ValueError) as error:
                raise RuntimeError('required source-bound UI170 JSON ancestry is absent or malformed') from error
            require(type(value) is dict, 'source-bound ancestry JSON must be an object')
            seen[path], values[path] = digest, value
        if not expand or path in expanded or not Path(path).is_relative_to(batch):
            continue
        expanded.add(path)
        value = values[path]
        if path == predecessor['closure']['path']:
            roles = value.get('sources')
            require(type(roles) is dict and ROLES <= set(roles) <= ROLES | {'first_normalization', 'final_normalization'},
                'complete current learning closure source roles are required')
            for child in roles.values():
                add(child)
        elif 'sources' in value:
            children = value['sources']
            require(type(children) is list or type(children) is dict and not children,
                'episode sources must be an explicit reference list')
            for child in children:
                add(child)
        for key in EPISODE_REFS:
            if value.get(key) is not None:
                add(value[key])
        for key in OPAQUE_REFS:
            if value.get(key) is not None:
                add(value[key], False)
        if 'accepted_previous_sources' in value:
            require(type(value['accepted_previous_sources']) is list, 'accepted prior authority must be a reference list')
            for child in value['accepted_previous_sources']:
                add(child, False)
        screen = value.get('screen_review')
        if screen is not None:
            require(type(screen) is dict and {'path', 'sha256'} <= set(screen) <= {'path', 'sha256', 'frame'},
                'owned screen review requires its exact JSON path and digest')
            add({k: screen[k] for k in ('path', 'sha256')})
        for container, keys in NESTED_REFS.items():
            nested = value.get(container)
            if nested is None:
                continue
            require(type(nested) is dict, 'known ancestry reference container must be an object')
            for key in keys:
                if nested.get(key) is not None:
                    add(nested[key], key != 'spawn_source')
    return [{'path': path, 'sha256': seen[path]} for path in sorted(seen)]


def write_exclusive(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    require(path.read_bytes() == raw and stat.S_IMODE(path.stat().st_mode) == 0o600,
        'private carried bytes or mode differ')


def carry(directory, preparation):
    directory = Path(directory)
    require(directory.is_absolute() and directory.parent == lab.ROOT / 'evidence' and directory.is_dir() and
        not any(p.is_symlink() for p in (directory, *directory.parents)), 'requires the named private UI171 batch')
    ready = closed(preparation)
    require(ready.get('phase') == 'item_actionbar_scout_ready' and ready.get('actor', {}).get('guid') == 2,
        'carrying requires the closed original scout ready source')
    from .item_actionbar_sources import source_bundle
    refs = ready.get('predecessor', {})
    require(set(refs) == {'closure', 'pause', 'remote', 'checkpoint', 'primary_stop'}, 'complete actual UI170 source roles are required')
    old = source_bundle(*[Path(refs[k]['path']) for k in ('closure', 'pause', 'remote', 'checkpoint', 'primary_stop')])
    require(ready.get('all_offline_snapshot') == old['snapshot'] and
        ready.get('predecessor_dvc_pointer') == old['dvc_pointer'], 'ready actual UI170 authority differs')
    ancestry, target = directory / 'ancestry', directory / 'ancestry_manifest.json'
    require(not ancestry.exists() and not target.exists(), 'carry never overwrites immutable ancestry')
    pending, rows, originals = {}, [], set()
    def resolve(ref):
        value = private_json(ref['path'], False)
        require(bound(ref['path']) == ref, 'source graph resolver requires exact original JSON bytes')
        return value

    graph = source_graph(refs, resolve)
    for ref in graph:
        reference(ref)
        source = Path(ref['path'])
        private_json(source, False)
        require(not source.is_relative_to(directory) and bound(source) == ref and str(source) not in originals,
            'exact distinct predecessor JSON bytes must lie outside the current batch')
        raw = source.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'original predecessor changed while carrying')
        copy = ancestry / (ref['sha256'] + '.json')
        rows.append({'original_path': str(source), 'sha256': ref['sha256'], 'copy_path': str(copy), 'bytes': len(raw)})
        pending[copy] = raw
        originals.add(str(source))
    pointer = old['dvc_pointer']
    pointer_path = Path(pointer['source']['path'])
    require(bound(pointer_path) == pointer['source'], 'actual UI170 DVC pointer changed')
    pointer_value = {'schema': 'client442_item_actionbar_predecessor_pointer_v1',
        'descriptor': pointer, 'raw_hex': pointer_path.read_bytes().hex()}
    ancestry.mkdir(mode=0o700)
    require(stat.S_IMODE(ancestry.stat().st_mode) == 0o700, 'ancestry directory is not private')
    for copy, raw in pending.items():
        write_exclusive(copy, raw)
    pointer_copy = ancestry / 'predecessor_dvc_pointer.json'
    write_exclusive(pointer_copy, (json.dumps(pointer_value, indent=2) + '\n').encode())
    manifest = {'schema': ANCESTRY_SCHEMA, 'sources': sorted(rows, key=lambda r: r['original_path']),
        'pointer_observation': bound(pointer_copy)}
    write_exclusive(target, (json.dumps(manifest, indent=2) + '\n').encode())
    return manifest


def checkpoint(directory, name):
    # All current receipt producers retain the ordinary Trial identity/cases.
    # The original publisher already archives these packet names and PNG/JSON.
    from .checkpoint_interactions import checkpoint as publish
    return publish(Path(directory), name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['carry', 'checkpoint'])
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--preparation', type=Path)
    parser.add_argument('--name')
    a = parser.parse_args()
    if a.action == 'carry':
        require(a.preparation is not None, 'carry requires the closed ready source')
        result = carry(a.directory, a.preparation)
        print(json.dumps({'carried_sources': len(result['sources']), 'qualification_added': False}), flush=True)
    else:
        require(type(a.name) is str and a.name, 'checkpoint requires its explicit archive name')
        checkpoint(a.directory, a.name)


if __name__ == '__main__':
    main()
