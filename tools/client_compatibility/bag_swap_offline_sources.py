"""Pinned crash-recovery authority over the unchanged flat UI173 proof.

The small runtime core projects the historical client solely for the next
launch's freshness comparison. Current services are separately named in the
closure; no current client is asserted while the owned scout is absent.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

from . import bag_swap_indexed_sources as parent
from .bag_swap_contract import require, strict_equal
from .bag_swap_sources import bound, reference
from . import bag_swap_offline_boundary as boundary

CACHE_SCHEMA = 'client442_bag_swap_offline_predecessor_authority_v1'
RUNTIME_SCHEMA = 'client442_bag_swap_offline_runtime_authority_v1'
EPOCH_SCHEMA = 'client442_bag_swap_offline_code_epoch_v1'
CARRY_SCHEMA = 'client442_bag_swap_offline_ancestry_v1'
LOGIN_SYNC_SCHEMA = 'client442_bag_swap_login_sync_v2'
CORE_FIELDS = parent.CORE_FIELDS
read_admission_pins = parent.read_admission_pins
MAX_DESCRIPTOR_BYTES = MAX_RUNTIME_BYTES = 1024 * 1024
DEPENDENCIES = ('src/server/worldserver/Main.cpp', 'tools/client_compatibility/world/control.py',
    'tools/client_compatibility/world/joins.py', 'tools/client_compatibility/bounded_run.py')


def _encode(value):
    return parent._encode(value)


def _write(path, value, root=None):
    from .bag_swap_fresh_sources import _write as write
    return write(Path(path), _encode(value), parent._root(root))


def validate_manifest(value, root=None):
    root = parent._root(root)
    require(type(value) is dict and set(value) == {'schema', 'members', 'authorities', 'boundary_source', 'indexed_carry_source'} and
        value.get('schema') == CARRY_SCHEMA and value.get('authorities') == [] and type(value.get('members')) is list and
        0 < len(value['members']) <= 32, 'small exact crash source map required')
    for key in ('boundary_source', 'indexed_carry_source'): reference(value[key])
    identities, copies = set(), {}
    for row in value['members']:
        require(type(row) is dict and set(row) == {'original_path', 'sha256', 'bytes', 'copy_member', 'kind'},
            'typed current crash source row required')
        reference({'path': row['original_path'], 'sha256': row['sha256']})
        require(Path(row['original_path']).is_relative_to(root / 'evidence') and type(row['bytes']) is int and
            0 < row['bytes'] <= (2 * 1024 * 1024 if row['kind'] == 'json' else 128 * 1024 * 1024) and
            row['kind'] in ('json', 'journal', 'png', 'binary') and
            type(row['copy_member']) is str and not Path(row['copy_member']).is_absolute() and
            '..' not in Path(row['copy_member']).parts and Path(row['copy_member']).parent.name == 'crash_sources' and
            str(root / row['copy_member']) == str((root / row['copy_member']).resolve()), 'canonical bounded crash source copy required')
        identity = (row['original_path'], row['sha256'])
        require(identity not in identities, 'duplicate original crash source identity')
        identities.add(identity)
        copy = (row['sha256'], row['bytes'], row['kind'])
        require(row['copy_member'] not in copies or copies[row['copy_member']] == copy, 'conflicting crash source copy type')
        copies[row['copy_member']] = copy
    wanted = value['boundary_source']
    require((wanted['path'], wanted['sha256']) in identities, 'actual closed crash source must be carried')
    return value


def _descriptor(value, root=None):
    root = parent._root(root)
    require(type(value) is dict and set(value) == {'schema', 'indexed_authority_source', 'carry_source', 'boundary_source', 'core_sha256'} and
        value.get('schema') == CACHE_SCHEMA and type(value.get('core_sha256')) is str and
        len(value['core_sha256']) == 64 and all(c in '0123456789abcdef' for c in value['core_sha256']) and
        len(_encode(value)) <= MAX_DESCRIPTOR_BYTES, 'small exact crash authority descriptor required')
    for key in ('indexed_authority_source', 'carry_source', 'boundary_source'):
        parent._member(value[key], root)
    return value


def _runtime_core(core):
    require(type(core) is dict and set(core) == set(CORE_FIELDS) and all(type(v) is dict for v in core.values()),
        'typed complete crash runtime core required')
    closed = core['closure']
    boundary.validate_runtime(closed)
    require(closed.get('phase') == boundary.PHASE and closed.get('completed') is True and closed.get('failure') is None and
        closed.get('excluded_failed_entry') is True and type(closed.get('operations_admitted')) is int and
        closed['operations_admitted'] == 0 and all(closed.get(k) is False for k in
            ('qualification_added', 'input_sent', 'mutation_sent', 'bag_input_sent', 'normal_logout_input_sent')) and
        core['snapshot'] == closed.get('all_offline_snapshot') and core['origin_actor'] == closed.get('actor') and
        core['runtime'] == {**closed['current_services'], 'client': closed['previous_client']} and
        core['primary_stop_source'] == closed.get('sources', {}).get('primary_stop') == core['predecessor'].get('primary_stop'),
        'source-owned zero-admission offline core differs')
    from .bag_swap_contract import owned_snapshot
    owned_snapshot(core['snapshot'])
    return core


def _core(old, closed):
    current = closed['current_services']
    result = {k: deepcopy(old[k]) for k in CORE_FIELDS}
    result.update(closure=deepcopy(closed), snapshot=deepcopy(closed['all_offline_snapshot']),
        runtime={**deepcopy(current), 'client': deepcopy(closed['previous_client'])})
    _runtime_core(result)
    require(strict_equal(closed['ready_baseline'], old['snapshot']) and
        all(strict_equal(closed['previous_runtime'][k], old['runtime'][k]) for k in ('worldserver', 'modern_world')) and
        closed['actor'] == old['origin_actor'],
        'crash recovery must extend the exact indexed predecessor and original actor')
    return result


def preflight_bundle(closure, remote, checkpoint, *, pins, offline_boundary, root=None, repo=None):
    old = parent.preflight_bundle(closure, remote, checkpoint, pins=pins, root=root, repo=repo)
    closed, ref = parent._json_file(offline_boundary, MAX_RUNTIME_BYTES, root=root)
    require(closed.get('schema') == boundary.SCHEMA and closed.get('phase') == boundary.PHASE,
        'fresh launch requires the actual closed crash restart boundary')
    return _core(old, closed)


def _journal(store, ref):
    if hasattr(store, 'journal'):
        return store.journal(ref)
    member = store.member(ref)
    rows = getattr(store, 'raw_journals', {}).get(member)
    require(type(rows) is list, 'portable complete crash journal required')
    return rows


def replay(store, closed):
    refs = closed['sources']
    values = [store.get(refs[k], False) for k in ('preparation', 'failed_entry', 'precision', 'idle')]
    diagnostic = store.get(refs['diagnostic'], False)
    before = store.get(refs['before_capture'], False)
    require(before.get('phase') == boundary.BEFORE_PHASE and before.get('completed') is True and
        before.get('stale_snapshot') == closed.get('stale_snapshot') and
        before.get('exact_precision', {}).get('before_row') == closed.get('exact_precision', {}).get('before_row') and
        before.get('service_files') == closed.get('service_files') and
        before.get('finished_at', 0) < closed.get('started_at', 0), 'actual pre-start observation differs')
    require(diagnostic.get('all_offline_snapshot') == before['stale_snapshot'] and
        diagnostic.get('exact_precision', {}).get('row') == before['exact_precision']['before_row'],
        'original crash diagnostic differs from the fresh pre-start observation')
    proof = boundary.validate(closed, *values, _journal(store, closed['journal_sources']['packets']),
        _journal(store, closed['journal_sources']['events']))
    require(proof == closed.get('proof'), 'portable excluded crash proof differs from the retained proof')
    for role, observed in closed['journal_observations'].items():
        rows = _journal(store, observed['source'])
        require(observed['source'] == closed['journal_sources'][role] and observed['rows'] == len(rows) and
            observed['first_time'] == min(row['time'] for row in rows) and
            observed['last_time'] == max(row['time'] for row in rows), 'closed interval journal observations differ')
    store.member(closed['original_failed_image'])
    return proof


def source_bundle(closure, remote, checkpoint, *, pins, offline_boundary, root=None, repo=None):
    old = parent.source_bundle(closure, remote, checkpoint, pins=pins, root=root, repo=repo)
    closed, boundary_ref = parent._json_file(offline_boundary, MAX_RUNTIME_BYTES, root=root)
    from .bag_swap_evidence import Sources
    data, digests, journals = {}, {}, {}
    def add(ref, kind='json'):
        reference(ref)
        member = str(Path(ref['path']).relative_to(parent._root(root)))
        require(bound(ref['path']) == ref, 'immutable current crash source changed')
        digests[member] = ref['sha256']
        if kind == 'json': data[member] = parent._json_file(ref['path'], 2 * 1024 * 1024, root=root, expected_ref=ref)[0]
        elif kind == 'journal':
            from .interaction_bag_swap_offline_boundary import journal_rows
            journals[member] = journal_rows(ref)
    add(boundary_ref)
    for role, ref in closed['sources'].items():
        if role != 'primary_stop': add(ref)
    add(closed['original_failed_image'], 'png')
    for ref in closed['journal_sources'].values(): add(ref, 'journal')
    store = Sources(data, digests, local=False)
    store.root, store.raw_journals = parent._root(root), journals
    replay(store, closed)
    result = _core(old, closed)
    result.update(_parent=old, boundary_source=boundary_ref)
    return result


def carry_authority(batch, *, admitted, root=None, repo=None):
    """Reuse the unchanged indexed raw carry and retain only UI174 dependencies."""
    parent_ref = parent.carry_authority(batch, admitted=admitted['_parent'], root=root, repo=repo)
    closed = admitted['closure']
    references = {(admitted['boundary_source']['path'], admitted['boundary_source']['sha256']): admitted['boundary_source']}
    kinds = {}
    def add(ref, kind='json'):
        references[(ref['path'], ref['sha256'])] = ref
        kinds[(ref['path'], ref['sha256'])] = kind
    add(admitted['boundary_source'])
    for role, ref in closed['sources'].items():
        if role != 'primary_stop': add(ref)
    for ref in closed['journal_sources'].values(): add(ref, 'journal')
    add(closed['original_failed_image'], 'png')
    before = parent._json_file(closed['sources']['before_capture']['path'], MAX_RUNTIME_BYTES, root=root)[0]
    for ref in before['journal_sources'].values(): add(ref, 'journal')
    for row in before['old_run_metadata'].values(): add(row['copy_source'], 'binary')
    for role in ('preparation', 'idle'):
        value, _ = parent._json_file(closed['sources'][role]['path'], 2 * 1024 * 1024, root=root)
        frame = value.get('frame')
        if frame:
            add({'path': str(Path(closed['sources'][role]['path']).parent / frame['file']), 'sha256': frame['sha256']}, 'png')
    destination = Path(batch) / 'crash_sources'
    require(not destination.exists(), 'current crash carry never overwrites earlier bytes')
    destination.mkdir(mode=0o700)
    from .interaction_bag_swap_offline_boundary import copy_file
    rows = []
    for identity, ref in sorted(references.items()):
        kind = kinds[identity]
        suffix = {'json': '.json', 'journal': '.jsonl', 'png': '.png', 'binary': '.bin'}[kind]
        target = destination / (ref['sha256'] + suffix)
        if not target.exists(): copy_file(ref['path'], target, 128 * 1024 * 1024)
        rows.append({'original_path': ref['path'], 'sha256': ref['sha256'], 'bytes': target.stat().st_size,
            'copy_member': str(target.relative_to(parent._root(root))), 'kind': kind})
    carry = {'schema': CARRY_SCHEMA, 'members': rows, 'authorities': [],
        'boundary_source': admitted['boundary_source'], 'indexed_carry_source': parent_ref}
    validate_manifest(carry, root)
    return _write(Path(batch) / 'crash_ancestry.json', carry, root)


def write_cache(directory, old, carry_source, *, root=None):
    carry = parent._json_file(carry_source['path'], MAX_DESCRIPTOR_BYTES, root=root, expected_ref=carry_source)[0]
    indexed_carry = carry['indexed_carry_source']
    previous = old['_parent']
    desc = {'schema': parent.CACHE_SCHEMA, 'core_sha256': hashlib.sha256(_encode({k: previous[k] for k in CORE_FIELDS})).hexdigest(),
        'refs': previous['predecessor'], 'source_index_source': previous['source_index_source'],
        'carry_source': indexed_carry, 'dvc_pointer': previous['dvc_pointer'], 'pointer_raw_hex': previous['pointer_raw_hex']}
    parent._descriptor(desc, root=root)
    parent_ref = _write(Path(directory) / 'indexed_authority.json', desc, root)
    descriptor = {'schema': CACHE_SCHEMA, 'indexed_authority_source': parent_ref, 'carry_source': carry_source,
        'boundary_source': old['boundary_source'], 'core_sha256': hashlib.sha256(_encode({k: old[k] for k in CORE_FIELDS})).hexdigest()}
    _descriptor(descriptor, root)
    actual = validate_cache(descriptor, store=local_store(Path(directory).parent, root=root), root=root)
    require(actual == {k: old[k] for k in CORE_FIELDS}, 'new raw crash carry differs from the admitted pre-launch core')
    return _write(Path(directory) / 'authority.json', descriptor, root)


def validate_cache(value, *, store, root=None):
    _descriptor(value, root or store.root)
    carry = store.get(value['carry_source'], False)
    validate_manifest(carry, root or store.root)
    for row in carry['members']:
        member = store.member({'path': row['original_path'], 'sha256': row['sha256']})
        if getattr(store, 'paths', {}).get(member) is not None:
            require(Path(store.paths[member]).stat().st_size == row['bytes'], 'actual raw crash source byte count differs')
    indexed_descriptor = store.get(value['indexed_authority_source'], False)
    require(carry.get('boundary_source') == value['boundary_source'] and
        carry['indexed_carry_source'] == indexed_descriptor.get('carry_source'),
        'source-owned crash carry differs')
    old = parent.validate_cache(indexed_descriptor, store=store, root=root)
    closed = store.get(value['boundary_source'], False)
    replay(store, closed)
    core = _core(old, closed)
    require(hashlib.sha256(_encode(core)).hexdigest() == value['core_sha256'], 'crash authority differs from complete raw replay')
    return core


def compact_authority(old, full_ref, *, root=None):
    reference(full_ref)
    core = {k: deepcopy(old[k]) for k in CORE_FIELDS}
    _runtime_core(core)
    result = {'schema': RUNTIME_SCHEMA, 'authority_source': full_ref, 'core': core}
    require(len(_encode(result)) <= MAX_RUNTIME_BYTES, 'crash runtime exceeds one MiB')
    return result


def write_runtime(directory, old, full_ref, *, root=None):
    return _write(Path(directory) / 'runtime_authority.json', compact_authority(old, full_ref, root=root), root)


def cached_runtime(path, full_ref, *, root=None, compact_ref=None):
    descriptor, _ = parent._json_file(full_ref['path'], MAX_DESCRIPTOR_BYTES, root=root, expected_ref=full_ref)
    _descriptor(descriptor, root)
    value, _ = parent._json_file(path, MAX_RUNTIME_BYTES, root=root, expected_ref=compact_ref)
    require(value.get('schema') == RUNTIME_SCHEMA and value.get('authority_source') == full_ref and
        hashlib.sha256(_encode(value['core'])).hexdigest() == descriptor['core_sha256'],
        'small source-owned crash runtime differs')
    _runtime_core(value['core'])
    return value['core']


def local_store(batch, root=None):
    from .bag_swap_indexed_archive import local_sources
    from .bag_swap_evidence import Sources
    source = local_sources(batch, root=root)
    store = Sources(source.data, source.digests, local=True, paths=source.paths)
    store.root, store.raw_journals = source.root, source.raw_journals
    return store


def cached_bundle(path, *, root=None):
    value, _ = parent._json_file(path, MAX_DESCRIPTOR_BYTES, root=root)
    return validate_cache(value, store=local_store(Path(path).parent.parent, root=root), root=root)


def validate_carry(store, ready):
    return validate_cache(store.get(ready['authority_source'], False), store=store)


def current_code_epoch(directory, old):
    from .bag_swap_projection import source_identities
    from .bag_swap_failed_sources import CODE_SCHEMA, MAX_SOURCE_BYTES, MAX_TOTAL_BYTES
    refs = source_identities(parent.REPO)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=parent.REPO, text=True).strip()
    require(commit == old['closure']['code_commit'] and refs == old['closure']['committed_sources'],
        'fresh crash successor must use its actual closed committed source epoch')
    target = Path(directory) / 'code_sources'
    require(not target.exists(), 'current crash epoch never overwrites source envelopes')
    target.mkdir(mode=0o700)
    copies, total = [], 0
    for i, ref in enumerate(refs):
        member = str(Path(ref['path']).relative_to(parent.REPO))
        raw = subprocess.check_output(['git', 'show', commit + ':' + member], cwd=parent.REPO)
        total += len(raw)
        require(len(raw) <= MAX_SOURCE_BYTES and total <= MAX_TOTAL_BYTES and
            hashlib.sha256(raw).hexdigest() == ref['sha256'], 'current crash source bytes differ from committed code')
        copies.append(_write(target / (f'{i:03d}_' + ref['sha256'] + '.json'), {'schema': CODE_SCHEMA,
            'code_commit': commit, 'original_path': ref['path'], 'sha256': ref['sha256'], 'bytes': len(raw), 'raw_hex': raw.hex()}))
    return _write(Path(directory) / 'current_code_epoch.json', {'schema': EPOCH_SCHEMA, 'code_commit': commit,
        'committed_sources': refs, 'carried_sources': copies})


def validate_current_code_epoch(store, resume, ready, closure):
    ref = ready['current_code_epoch_source']
    epoch = store.get(ref, False)
    require(resume.get('current_code_epoch_source') == ref and epoch.get('schema') == EPOCH_SCHEMA and
        epoch.get('code_commit') == closure.get('code_commit') == ready.get('code_commit') and
        epoch.get('committed_sources') == closure.get('committed_sources') == ready.get('committed_sources'),
        'crash successor current source epoch differs')
    parent.stopped._envelopes(store, epoch, epoch['committed_sources'], epoch['code_commit'])
    return {'code_commit': epoch['code_commit'], 'complete_raw_source_members': len(epoch['committed_sources'])}
