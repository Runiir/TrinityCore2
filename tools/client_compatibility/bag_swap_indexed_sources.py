"""Bounded authority for a fresh swap after the excluded UI173 system stop.

Admission and portable publication replay complete raw predecessor sources.
Live helpers read only source-bound descriptor/compact/carry identities. No
legacy cache graph is parsed and no future publication source is assumed.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess

from . import bag_swap_sources as original
from . import bag_swap_stopped_evidence as stopped
from .item_actionbar_contract import require, finite, strict_equal
from .bag_swap_preservation import exact_precision, PRECISION_QUERY

ROOT = original.lab.ROOT
REPO = original.lab.REPO
POINTER = 'artifacts/client_harness/442_interactions_20261008_173.tar.gz.dvc'
CACHE_SCHEMA = 'client442_bag_swap_indexed_predecessor_authority_v1'
RUNTIME_SCHEMA = 'client442_bag_swap_indexed_runtime_authority_v1'
EPOCH_SCHEMA = 'client442_bag_swap_indexed_code_epoch_v1'
LOGIN_SYNC_SCHEMA = 'client442_bag_swap_login_sync_v2'
CORE_FIELDS, ROLES = original.CORE_FIELDS, original.ROLES
MAX_DESCRIPTOR_BYTES = MAX_RUNTIME_BYTES = 1024 * 1024
MAX_CARRY_BYTES = 16 * 1024 * 1024
INDEXED_DEPENDENCIES = (
    'tools/client_compatibility/native_bridge/service.cpp',
    'tools/client_compatibility/native_bridge/session_auth.cpp',
    'tools/client_compatibility/native_bridge/events.cpp',
)
NEW_FILES = (
    'tools/client_compatibility/bag_swap_indexed_sources.py',
    'tools/client_compatibility/bag_swap_indexed_archive.py',
    'tools/client_compatibility/world/tests/test_bag_swap_indexed_sources.py',
    'tools/client_compatibility/world/tests/test_bag_swap_indexed_archive.py',
    'tools/client_compatibility/world/tests/test_bag_swap_indexed_unit.py',
    'tools/client_compatibility/world/tests/test_bag_swap_indexed_publication.py',
    'tools/client_compatibility/bag_swap_login_sync_v2.py',
    'tools/client_compatibility/world/tests/test_bag_swap_login_sync_v2.py',
)
CHANGED_OLD = frozenset((
    'tools/client_compatibility/interaction_bag_swap_continuation.py',
    'tools/client_compatibility/interaction_bag_swap.py',
    'tools/client_compatibility/bag_swap_contract.py',
    'tools/client_compatibility/world/tests/test_bag_swap_contract.py',
    'tools/client_compatibility/world/tests/test_bag_swap_continuation.py',
    'tools/client_compatibility/world/tests/test_bag_swap_projection.py',
    'tools/client_compatibility/world/tests/test_bag_swap_full_unit.py',
    'tools/client_compatibility/world/tests/test_bag_swap_operation.py',
    'tools/client_compatibility/bag_swap_evidence.py',
    'tools/client_compatibility/checkpoint_bag_swap.py',
    'tools/client_compatibility/review_bag_swap_checkpoint.py',
    'tools/client_compatibility/bag_swap_projection.py',
    'experiments/configs/client_harness/442_bag_swap_roundtrip_v1.json',
))
bound, reference = original.bound, original.reference


def _root(root=None):
    root = Path(root or ROOT)
    require(root.is_absolute() and str(root.resolve()) == str(root) and '..' not in root.parts,
        'canonical private authority root required')
    return root


def _member(ref, root):
    reference(ref)
    path = Path(ref['path'])
    require(path.is_relative_to(root / 'evidence') and str(path) == ref['path'] and path.suffix == '.json',
        'original ordinary private JSON authority source required')
    return str(path.relative_to(root))


def _json_file(path, limit, *, root=None, expected_ref=None, allow_raw_json=False):
    """Decode only the exact bytes read once from a stable capped ordinary file."""
    root, path = _root(root), Path(path)
    if allow_raw_json and path.suffix == '.blob':
        reference({'path': str(path), 'sha256': '0' * 64})
        require(path.is_relative_to(root / 'evidence') and str(path) == str(path.resolve()),
            'ordinary private typed raw JSON copy required')
    else:
        _member({'path': str(path), 'sha256': '0' * 64}, root)
    require(type(limit) is int and limit > 0 and
        not any(p.is_symlink() for p in (path, *path.parents)), 'ordinary private authority JSON required')
    if expected_ref is not None:
        reference(expected_ref)
        require(expected_ref['path'] == str(path), 'pinned JSON source path differs')
    def identity(value):
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= limit,
        'retained authority JSON exceeds its exact byte cap')
    from .review_bag_swap_failed_checkpoint import _json
    with path.open('rb') as handle:
        opened = os.fstat(handle.fileno())
        require(stat.S_ISREG(opened.st_mode) and identity(opened) == identity(before),
            'authority source changed before reading')
        raw = handle.read(limit + 1)
        require(0 < len(raw) <= limit and len(raw) == before.st_size,
            'retained authority JSON exceeds its exact read-length cap')
        require(identity(os.fstat(handle.fileno())) == identity(before) and
            identity(path.lstat()) == identity(before), 'authority source changed while reading')
        ref = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
        require(expected_ref is None or ref == expected_ref, 'decoded JSON bytes differ from the pinned source')
        if limit > MAX_RUNTIME_BYTES:
            # A generic local JSON lookup may not yet have loaded the receipt
            # that declares a renamed authority role. Reuse the bounded
            # lexical schema pass before the complete document decoder.
            from .bag_swap_indexed_archive import _role_fields, SCHEMA as CARRY_SCHEMA
            fields, _, recognized, _ = _role_fields(raw)
            limits = {CACHE_SCHEMA: MAX_DESCRIPTOR_BYTES, RUNTIME_SCHEMA: MAX_RUNTIME_BYTES,
                CARRY_SCHEMA: MAX_CARRY_BYTES}
            caps = [limits[schema] for schema in recognized if schema in limits]
            require(not caps or len(raw) <= min(caps), 'indexed JSON exceeds its exact raw byte bound before decode')
            require(not caps or len(fields.get('schema', [])) == 1,
                'indexed schema declaration must be unambiguous before decode')
        value = _json(raw)
        require(identity(os.fstat(handle.fileno())) == identity(before) and
            identity(path.lstat()) == identity(before) and
            not any(p.is_symlink() for p in (path, *path.parents)), 'authority source changed while parsing')
    require(type(value) is dict, 'ordinary authority JSON object required')
    return value, ref


def admission_pins(value, *, root=None):
    """The coordinator supplies only actual closed publication identities."""
    root = _root(root)
    require(type(value) is dict and set(value) == {'closure', 'remote', 'checkpoint'},
        'three actual UI173 publication source pins are required; future pins are unavailable')
    for ref in value.values():
        _member(ref, root)
    batch = root / stopped.BATCH.rstrip('/')
    require(Path(value['closure']['path']).is_relative_to(batch) and
        Path(value['checkpoint']['path']) == batch / 'checkpoint_receipt.json' and
        not Path(value['remote']['path']).is_relative_to(batch),
        'latest actual stopped closure, batch checkpoint and external remote review required')
    return deepcopy(value)


def read_admission_pins(path, *, root=None):
    """Read the coordinator's small actual-role file before any admission work."""
    value, _ = _json_file(path, MAX_DESCRIPTOR_BYTES, root=root)
    return admission_pins(value, root=root)


def read_runtime_source(ref, *, root=None):
    reference(ref)
    require(0 < Path(ref['path']).stat().st_size <= MAX_RUNTIME_BYTES,
        'runtime authority exceeds its one-MiB raw byte bound before decode')
    value, _ = _json_file(ref['path'], MAX_RUNTIME_BYTES, root=root, expected_ref=ref)
    return value


def _pointer(pointer, raw_hex, checkpoint, remote):
    require(type(checkpoint) is dict and checkpoint.get('cloud_verified') is True and
        checkpoint.get('file') == POINTER.removesuffix('.dvc') and
        type(checkpoint.get('bytes')) is int and checkpoint['bytes'] > 0 and
        type(checkpoint.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', checkpoint['sha256']) and
        type(remote) is dict and remote.get('pointer') == POINTER and
        remote.get('bytes') == checkpoint['bytes'] and remote.get('archive_sha256') == checkpoint['sha256'],
        'actual stopped checkpoint/remote compressed identity differs')
    require(type(pointer) is dict and set(pointer) == {'source', 'pointer', 'oid', 'bytes'} and
        pointer.get('pointer') == POINTER and pointer.get('oid') == remote.get('object_md5') and
        type(pointer['oid']) is str and re.fullmatch('[0-9a-f]{32}', pointer['oid']) and
        type(pointer['bytes']) is int and pointer['bytes'] == checkpoint['bytes'],
        'actual stopped DVC object descriptor differs')
    reference(pointer['source'])
    require(pointer['source']['sha256'] == remote.get('pointer_sha256') and
        Path(pointer['source']['path']).as_posix().endswith('/' + POINTER) and
        type(raw_hex) is str and 0 < len(raw_hex) <= 8192 and len(raw_hex) % 2 == 0 and
        re.fullmatch('[0-9a-f]+', raw_hex), 'bounded exact actual stopped pointer bytes required')
    raw = bytes.fromhex(raw_hex)
    require(hashlib.sha256(raw).hexdigest() == pointer['source']['sha256'], 'actual pointer SHA differs')
    try:
        text = raw.decode('utf-8')
    except UnicodeError as error:
        raise RuntimeError('actual pointer must be UTF-8') from error
    require(re.findall(r'^\s*-?\s*md5:\s*([0-9a-f]{32})\s*$', text, re.MULTILINE) == [pointer['oid']] and
        re.findall(r'^\s*size:\s*([0-9]+)\s*$', text, re.MULTILINE) == [str(checkpoint['bytes'])] and
        re.findall(r'^\s*path:\s*(\S+)\s*$', text, re.MULTILINE) == [Path(checkpoint['file']).name] and
        re.search(r'^\s*hash:\s*md5\s*$', text, re.MULTILINE), 'actual pointer object bytes differ')


def _runtime_core(core, root):
    from .bag_swap_contract import owned_snapshot
    require(type(core) is dict and set(core) == set(CORE_FIELDS) and
        all(type(core[k]) is dict for k in CORE_FIELDS), 'exact typed indexed compact core required')
    c, snapshot, refs, actor = (core[k] for k in ('closure', 'snapshot', 'predecessor', 'origin_actor'))
    require(c.get('schema') == stopped.SCHEMA and c.get('phase') == stopped.PHASE and
        c.get('completed') is True and c.get('failure') is None and c.get('controller') == 'code' and
        c.get('model') is None and c.get('revision') is None and c.get('excluded_failed_entry') is True and
        type(c.get('operations_admitted')) is int and c['operations_admitted'] == 0 and
        all(c.get(k) is False for k in ('input_sent', 'mutation_sent', 'qualification_added',
            'bag_input_sent', 'normal_logout_input_sent')) and c.get('entry_input_sent') is True and
        c.get('cases') == c.get('cleanup') == [] and c.get('custom_script_permission') == 'blocked_by_user' and
        strict_equal(c.get('softTargetInteract'), stopped.SCRIPT) and
        strict_equal(c.get('stop_checks'), dict.fromkeys(stopped.STOP_CHECKS, True)),
        'actually excluded observed system-stop boundary required')
    require(all(finite(c.get(k)) for k in ('started_at', 'audit_until', 'finished_at')) and
        0 < c['started_at'] <= c['audit_until'] < c['finished_at'] and
        c.get('sources') == stopped.SOURCES and
        strict_equal(c.get('before'), snapshot) and strict_equal(c.get('after'), snapshot) and
        strict_equal(c.get('all_offline_snapshot'), snapshot) and strict_equal(c.get('actor'), actor) and
        strict_equal(c.get('runtime'), core['runtime']), 'honest latest stopped snapshot and source identity required')
    require(not any(k in c for k in ('game_before', 'game_start_ticks', 'sigterm_at', 'stop_finished_at')),
        'unobserved predecessor game lifetime or system-stop times cannot be invented')
    owned_snapshot(snapshot)
    require(set(refs) == ROLES and core['primary_stop_source'] == refs['primary_stop'] ==
        c.get('predecessor', {}).get('primary_stop'), 'latest role set and inherited primary stop differ')
    admission_pins({k: refs[k] for k in ('closure', 'remote', 'checkpoint')}, root=root)
    for ref in refs.values():
        _member(ref, root)
    require(type(actor.get('guid')) is int and actor['guid'] == 2 and type(actor.get('account_id')) is int and
        actor['account_id'] == 2 and actor.get('actor') == 'scout', 'original owned scout actor2 required')
    precision = c.get('exact_precision')
    require(type(precision) is dict and precision.get('query') == PRECISION_QUERY and
        precision.get('input_sent') is False and precision.get('mutation_sent') is False and
        strict_equal(precision.get('before'), snapshot) and strict_equal(precision.get('after'), snapshot) and
        strict_equal(precision.get('before_row'), precision.get('after_row')),
        'both actual exact stopped FLOAT observations required')
    exact_precision(precision['before_row'], snapshot)
    exact_precision(precision['after_row'], snapshot)
    times = [precision.get(k) for k in ('before_query_started_at', 'before_query_finished_at',
        'after_query_started_at', 'after_query_finished_at')]
    require(all(finite(v) for v in times) and finite(c.get('source_validation_finished_at')) and
        c['started_at'] <= times[0] <= times[1] <= c['audit_until'] < c['source_validation_finished_at'] <=
        times[2] <= times[3] < c['finished_at'], 'actual final precision must follow predecessor source replay')
    game = c.get('owned_game_identity')
    require(type(game) is dict and set(game) == {'pid', 'source', 'frame'} and
        type(game['pid']) is int and game['pid'] > 0 and game['source'] == stopped.SOURCES['preparation'] and
        game.get('frame', {}).get('monitor', {}).get('input_isolation', {}).get('game_pid') == game['pid'],
        'source-owned observed predecessor game PID required')
    pointer = core['dvc_pointer']
    require(set(pointer) == {'source', 'pointer', 'oid', 'bytes'} and pointer.get('pointer') == POINTER and
        type(pointer.get('oid')) is str and re.fullmatch('[0-9a-f]{32}', pointer['oid']) and
        type(pointer.get('bytes')) is int and pointer['bytes'] > 0, 'typed actual compact stopped object required')
    reference(pointer['source'])
    require(Path(pointer['source']['path']).as_posix().endswith('/' + POINTER), 'compact stopped pointer path differs')
    for lifetime in (core['runtime'].get(k) for k in ('worldserver', 'modern_world', 'client')):
        require(type(lifetime) is dict and type(lifetime.get('pid')) is int and lifetime['pid'] > 0 and
            type(lifetime.get('start_ticks')) is str and re.fullmatch('[1-9][0-9]*', lifetime['start_ticks']),
            'retained native, bridge and launcher process lifetimes required')


def preflight_bundle(closure, remote, checkpoint, *, pins, root=None, repo=None):
    """Read the pinned stopped core before any full remote admission or journal work.

    The remote review is deliberately retained as a role reference here. Its
    complete proof is checked only by source_bundle after current offline state
    has been verified against these exact small source-owned observations.
    """
    root, repo = _root(root), Path(repo or REPO)
    pins = admission_pins(pins, root=root)
    require(all(str(path) == pins[role]['path'] for role, path in
        (('closure', closure), ('remote', remote), ('checkpoint', checkpoint))),
        'preflight role paths differ from actual publication pins')
    c, _ = _json_file(closure, MAX_RUNTIME_BYTES, root=root, expected_ref=pins['closure'])
    cp, _ = _json_file(checkpoint, MAX_DESCRIPTOR_BYTES, root=root, expected_ref=pins['checkpoint'])
    require(cp.get('cloud_verified') is True and cp.get('file') == POINTER.removesuffix('.dvc') and
        type(cp.get('bytes')) is int and cp['bytes'] > 0 and type(cp.get('sha256')) is str and
        re.fullmatch('[0-9a-f]{64}', cp['sha256']), 'actual pinned stopped checkpoint identity required')
    pointer_path = repo / POINTER
    require(str(pointer_path.resolve()) == str(pointer_path) and
        not any(p.is_symlink() for p in (pointer_path, *pointer_path.parents)),
        'canonical ordinary actual DVC pointer required')
    def identity(value):
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    before = pointer_path.lstat()
    require(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 4096,
        'bounded actual stopped pointer required')
    with pointer_path.open('rb') as handle:
        require(identity(os.fstat(handle.fileno())) == identity(before), 'actual pointer changed before reading')
        raw = handle.read(4097)
        require(0 < len(raw) <= 4096 and len(raw) == before.st_size and
            identity(os.fstat(handle.fileno())) == identity(before) and
            identity(pointer_path.lstat()) == identity(before), 'actual pointer changed while reading')
    try:
        text = raw.decode('utf-8')
    except UnicodeError as error:
        raise RuntimeError('actual pointer must be UTF-8') from error
    md5 = re.findall(r'^\s*-?\s*md5:\s*([0-9a-f]{32})\s*$', text, re.MULTILINE)
    require(len(md5) == 1 and
        re.findall(r'^\s*size:\s*([0-9]+)\s*$', text, re.MULTILINE) == [str(cp['bytes'])] and
        re.findall(r'^\s*path:\s*(\S+)\s*$', text, re.MULTILINE) == [Path(cp['file']).name] and
        re.search(r'^\s*hash:\s*md5\s*$', text, re.MULTILINE), 'actual pointer/checkpoint preflight differs')
    pointer = {'source': {'path': str(pointer_path), 'sha256': hashlib.sha256(raw).hexdigest()},
        'pointer': POINTER, 'oid': md5[0], 'bytes': cp['bytes']}
    stop_ref = c.get('predecessor', {}).get('primary_stop')
    core = {'closure': c, 'snapshot': c.get('after'), 'predecessor': {**pins, 'primary_stop': stop_ref},
        'primary_stop_source': stop_ref, 'dvc_pointer': pointer,
        'runtime': c.get('runtime'), 'origin_actor': c.get('actor')}
    _runtime_core(core, root)
    return core


def validate_parent(data, digests, tracking, pins, pointer, pointer_raw_hex, *, root=None):
    """Pure complete UI173 replay; references are supplied from actual publication."""
    from .bag_swap_source_index import Sources
    root = _root(root)
    pins = admission_pins(pins, root=root)
    store = Sources(data, digests, tracking.get('raw_journals', {}), paths=tracking.get('paths', {}), root=root)
    c = store.get(pins['closure'], False)
    remote = store.get(pins['remote'], False)
    checkpoint = store.get(pins['checkpoint'], False)
    _pointer(pointer, pointer_raw_hex, checkpoint, remote)
    require(remote.get('schema') == 'client442_bag_swap_stopped_remote_review_v1' and
        remote.get('checkpoint_source') == pins['checkpoint'] and
        all(remote.get(k) is True for k in ('actual_remote_verified', 'complete_manifest_verified',
            'complete_json_png_jsonl_verified', 'opaque_legacy_authorities_verified', 'excluded_failed_entry')) and
        remote.get('local_archive_created') is False and remote.get('qualification_added') is False and
        type(remote.get('operations_admitted')) is int and remote['operations_admitted'] == 0 and
        finite(remote.get('reviewed_at')) and remote['reviewed_at'] >= c['finished_at'],
        'actual complete zero-admission stopped remote review required')
    selected = tracking.get('manifest', {})
    require(all(type(remote.get(key)) is int and remote[key] == sum(member.endswith(suffix) for member in selected)
        for key, suffix in (('json_members', '.json'), ('png_members', '.png'), ('journal_members', '.jsonl'))),
        'actual stopped remote source counts differ from the complete raw checkpoint manifest')
    computed = stopped.proof(data, digests, tracking)
    require(strict_equal(computed, remote.get('proof')), 'actual complete stopped proof differs from remote review')
    ancestors = computed['ancestors']
    stop_ref = ancestors['ui171']['primary_stop_source']
    require(c['predecessor']['primary_stop'] == stop_ref, 'primary stop must come from proved UI171 raw ancestry')
    refs = {**pins, 'primary_stop': stop_ref}
    core = {'closure': c, 'snapshot': c['after'], 'predecessor': refs, 'primary_stop_source': stop_ref,
        'dvc_pointer': pointer, 'runtime': c['runtime'], 'origin_actor': c['actor']}
    _runtime_core(core, root)
    require(type(tracking.get('manifest')) is dict and set(tracking['manifest']) ==
        {row['path'] for row in checkpoint['file_manifest']}, 'complete actual parent manifest required')
    return {**core, 'source_index_source': c['source_index_source'], 'pointer_raw_hex': pointer_raw_hex,
        'archive': {'file': checkpoint['file'], 'bytes': checkpoint['bytes'], 'sha256': checkpoint['sha256'],
            'manifest': checkpoint['file_manifest']},
        'remote_proof_sha256': hashlib.sha256(_encode(computed)).hexdigest()}


def source_bundle(closure, remote, checkpoint, *, pins, root=None, repo=None):
    from urllib.request import urlopen
    from .review_hunter_learn_checkpoint import remote_options, remote_request
    from .bag_swap_source_index import inspect_archive
    root, repo = _root(root), Path(repo or REPO)
    pins = admission_pins(pins, root=root)
    values = {}
    for role, path in (('closure', closure), ('remote', remote), ('checkpoint', checkpoint)):
        values[role], ref = _json_file(path, original.MAX_JSON_BYTES, root=root, expected_ref=pins[role])
    pointer_path = repo / POINTER
    require(pointer_path.stat().st_size <= 4096, 'bounded actual stopped pointer required')
    pointer_ref = bound(pointer_path)
    raw = pointer_path.read_bytes()
    pointer = {'source': pointer_ref, 'pointer': POINTER, 'oid': values['remote'].get('object_md5'),
        'bytes': values['checkpoint'].get('bytes')}
    _pointer(pointer, raw.hex(), values['checkpoint'], values['remote'])
    tracking = None
    try:
        with urlopen(remote_request(remote_options(repo), pointer['oid']), timeout=60) as stream:
            data, digests, tracking, count = inspect_archive(stream, values['checkpoint'], stopped.BATCH)
        require(count == pointer['bytes'] and tracking.get('compressed_md5') == pointer['oid'],
            'complete actual compressed stopped object differs')
        # Checkpoint/remote are external to the parent archive. Retain their
        # exact original bindings without manufacturing archive manifest rows.
        for role in ('checkpoint', 'remote'):
            member = _member(pins[role], root)
            data[member], digests[member] = values[role], pins[role]['sha256']
        result = validate_parent(data, digests, tracking, pins, pointer, raw.hex(), root=root)
    finally:
        if tracking is not None and tracking.get('_spool') is not None:
            tracking['_spool'].cleanup()
    require(all(bound(path) == pins[role] for role, path in
        (('closure', closure), ('remote', remote), ('checkpoint', checkpoint))) and
        bound(pointer_path) == pointer_ref, 'publication source changed during complete admission')
    return result


def carry_authority(batch, *, admitted, root=None, repo=None):
    from urllib.request import urlopen
    from .review_hunter_learn_checkpoint import remote_options, remote_request
    from .bag_swap_indexed_archive import carry_archive
    root, repo = _root(root), Path(repo or REPO)
    _runtime_core({k: admitted[k] for k in CORE_FIELDS}, root)
    cp, cp_ref = _json_file(admitted['predecessor']['checkpoint']['path'], original.MAX_JSON_BYTES, root=root)
    require(cp_ref == admitted['predecessor']['checkpoint'], 'actual checkpoint changed before carry')
    authorities = {role: admitted['predecessor'][role] for role in ('checkpoint', 'remote')}
    with urlopen(remote_request(remote_options(repo), admitted['dvc_pointer']['oid']), timeout=60) as stream:
        return carry_archive(stream, cp, stopped.BATCH, Path(batch), admitted['predecessor'],
            admitted['source_index_source'], admitted['dvc_pointer'], admitted['pointer_raw_hex'], authorities, root=root)


def _encode(value):
    from .bag_swap_fresh_sources import _encode as encode
    return encode(value)


def _descriptor(value, *, root=None):
    root = _root(root)
    fields = {'schema', 'core_sha256', 'refs', 'source_index_source', 'carry_source', 'dvc_pointer', 'pointer_raw_hex'}
    require(type(value) is dict and set(value) == fields and value['schema'] == CACHE_SCHEMA and
        type(value['core_sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['core_sha256']) and
        type(value.get('refs')) is dict and set(value['refs']) == ROLES and
        len(_encode(value)) <= MAX_DESCRIPTOR_BYTES, 'bounded distinct indexed descriptor required')
    admission_pins({k: value['refs'][k] for k in ('closure', 'remote', 'checkpoint')}, root=root)
    for ref in [*value['refs'].values(), value['source_index_source'], value['carry_source']]:
        _member(ref, root)
    pointer = value['dvc_pointer']
    require(type(pointer) is dict and set(pointer) == {'source', 'pointer', 'oid', 'bytes'} and
        pointer.get('pointer') == POINTER and type(pointer.get('oid')) is str and
        re.fullmatch('[0-9a-f]{32}', pointer['oid']) and type(pointer.get('bytes')) is int and pointer['bytes'] > 0,
        'indexed descriptor pointer namespace differs')
    reference(pointer['source'])
    require(type(value['pointer_raw_hex']) is str and 0 < len(value['pointer_raw_hex']) <= 8192 and
        len(value['pointer_raw_hex']) % 2 == 0 and re.fullmatch('[0-9a-f]+', value['pointer_raw_hex']),
        'bounded exact descriptor pointer bytes required')
    return value


def read_descriptor(ref, *, root=None):
    value, actual = _json_file(ref['path'], MAX_DESCRIPTOR_BYTES, root=root, expected_ref=ref)
    return _descriptor(value, root=root)


def read_carry(ref, *, root=None):
    value, actual = _json_file(ref['path'], MAX_CARRY_BYTES, root=root, expected_ref=ref)
    from .bag_swap_indexed_archive import validate_carry_manifest
    validate_carry_manifest(value, root=_root(root))
    return value


def cached_bundle(path, *, root=None):
    from .bag_swap_indexed_archive import local_sources
    value, descriptor_ref = _json_file(path, MAX_DESCRIPTOR_BYTES, root=root)
    store = local_sources(Path(path).parent.parent, root=_root(root), role_refs={'descriptor': descriptor_ref})
    return validate_cache(value, store=store, root=root)


def _carry(store, descriptor):
    from .bag_swap_indexed_archive import validate_carry_manifest, parent_view, Sources as CarrySources
    carry = store.get(descriptor['carry_source'], False)
    validate_carry_manifest(carry, root=store.root)
    require(carry['predecessor'] == descriptor['refs'] and
        carry['source_index_source'] == descriptor['source_index_source'] and
        carry['dvc_pointer'] == descriptor['dvc_pointer'] and
        carry['pointer_raw_hex'] == descriptor['pointer_raw_hex'], 'descriptor and source-owned carry identity differ')
    # Generic evidence stores have historical ancestry dispatch, but they do
    # not own the new carry's separately typed JSON/journal views. Restore the
    # strict outer carry store before reconstructing the parent keyspace.
    carried = CarrySources(store.data, store.digests, getattr(store, 'raw_journals', {}),
        store.paths, store.root, carry, local=store.local)
    return carry, parent_view(carried, carry)


def validate_cache(value, *, store, root=None):
    root = _root(root or store.root)
    descriptor = _descriptor(value, root=root)
    _, (data, digests, tracking) = _carry(store, descriptor)
    pins = {k: descriptor['refs'][k] for k in ('closure', 'remote', 'checkpoint')}
    old = validate_parent(data, digests, tracking, pins, descriptor['dvc_pointer'],
        descriptor['pointer_raw_hex'], root=root)
    require(hashlib.sha256(_encode({k: old[k] for k in CORE_FIELDS})).hexdigest() == descriptor['core_sha256'],
        'indexed descriptor core differs from complete raw parent replay')
    return old


def write_cache(directory, old, carry_source, *, root=None):
    from .bag_swap_indexed_archive import local_sources
    from .bag_swap_fresh_sources import _write
    root = _root(root)
    value = {'schema': CACHE_SCHEMA, 'core_sha256': hashlib.sha256(_encode({k: old[k] for k in CORE_FIELDS})).hexdigest(),
        'refs': old['predecessor'], 'source_index_source': old['source_index_source'], 'carry_source': carry_source,
        'dvc_pointer': old['dvc_pointer'], 'pointer_raw_hex': old['pointer_raw_hex']}
    _descriptor(value, root=root)
    store = local_sources(Path(directory).parent, root=root)
    actual = validate_cache(value, store=store, root=root)
    require(strict_equal({k: actual[k] for k in CORE_FIELDS}, {k: old[k] for k in CORE_FIELDS}),
        'descriptor writer requires actual newly verified raw carry')
    del store
    return _write(Path(directory) / 'authority.json', _encode(value), root)


def compact_authority(old, full_ref, *, root=None):
    root = _root(root)
    _member(full_ref, root)
    core = {k: old[k] for k in CORE_FIELDS}
    _runtime_core(core, root)
    value = {'schema': RUNTIME_SCHEMA, 'authority_source': full_ref, 'core': core}
    require(len(_encode(value)) <= MAX_RUNTIME_BYTES, 'indexed compact exceeds one MiB')
    return deepcopy(value)


def cached_runtime(path, full_ref, *, root=None, compact_ref=None):
    root = _root(root)
    require(Path(path) != Path(full_ref['path']), 'indexed descriptor and compact must be distinct')
    descriptor, actual = _json_file(full_ref['path'], MAX_DESCRIPTOR_BYTES, root=root, expected_ref=full_ref)
    _descriptor(descriptor, root=root)
    if compact_ref is not None:
        require(_member(compact_ref, root) == str(Path(path).relative_to(root)),
            'indexed compact read must retain its exact source path')
    value, _ = _json_file(path, MAX_RUNTIME_BYTES, root=root, expected_ref=compact_ref)
    require(set(value) == {'schema', 'authority_source', 'core'} and value['schema'] == RUNTIME_SCHEMA and
        value['authority_source'] == full_ref, 'source-owned indexed compact schema differs')
    _runtime_core(value['core'], root)
    require(value['core']['predecessor'] == descriptor['refs'] and
        value['core']['closure']['source_index_source'] == descriptor['source_index_source'] and
        value['core']['dvc_pointer'] == descriptor['dvc_pointer'] and
        hashlib.sha256(_encode(value['core'])).hexdigest() == descriptor['core_sha256'],
        'indexed compact differs from admitted descriptor core')
    # Only small identity sources are read while an input is pending. The raw
    # predecessor journals/opaque artifacts remain offline proof concerns.
    carry, carry_ref = _json_file(descriptor['carry_source']['path'], MAX_CARRY_BYTES,
        root=root, expected_ref=descriptor['carry_source'])
    from .bag_swap_indexed_archive import validate_carry_manifest
    validate_carry_manifest(carry, root=root)
    require(carry['predecessor'] == descriptor['refs'] and carry['source_index_source'] == descriptor['source_index_source'] and
        carry['dvc_pointer'] == descriptor['dvc_pointer'] and carry['pointer_raw_hex'] == descriptor['pointer_raw_hex'],
        'live source-owned carry differs from indexed descriptor')
    return value['core']


def write_runtime(directory, old, full_ref, *, root=None):
    from .bag_swap_fresh_sources import _write
    root = _root(root)
    value = compact_authority(old, full_ref, root=root)
    descriptor, actual = _json_file(full_ref['path'], MAX_DESCRIPTOR_BYTES, root=root, expected_ref=full_ref)
    require(actual == full_ref and _descriptor(descriptor, root=root)['core_sha256'] ==
        hashlib.sha256(_encode(value['core'])).hexdigest(), 'runtime writer differs from admitted descriptor')
    return _write(Path(directory) / 'runtime_authority.json', _encode(value), root)


def validate_carry(store, ready):
    ref = ready['authority_source']
    old = validate_cache(store.get(ref, False), store=store)
    require(ready['predecessor'] == old['predecessor'], 'latest indexed ready predecessor roles differ')
    return old


def _epoch_paths(closure, repo):
    old = closure['code_source_epoch']
    require(old['schema'] == stopped.EPOCH_SCHEMA and old['committed_sources'] == closure['committed_sources'] and
        old['code_commit'] == closure['code_commit'], 'actual stopped publication epoch required')
    wanted = sorted(set(stopped._vector(old['committed_sources'], repo)) | set(NEW_FILES) | set(INDEXED_DEPENDENCIES))
    return old, wanted


def current_code_epoch(directory, old):
    from .bag_swap_projection import source_identities
    from .bag_swap_failed_sources import CODE_SCHEMA, MAX_SOURCE_BYTES, MAX_TOTAL_BYTES
    from .bag_swap_fresh_sources import _write
    directory = Path(directory)
    root = _root()
    require(directory.is_dir() and directory.is_relative_to(root / 'evidence'), 'new private indexed code epoch required')
    previous, wanted = _epoch_paths(old['closure'], REPO)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    refs = source_identities(REPO)
    old_hashes = {r['path']: r['sha256'] for r in previous['committed_sources']}
    require(commit != previous['code_commit'] and stopped._vector(refs, REPO) == wanted and
        all(r['sha256'] == old_hashes[r['path']] for r in refs if r['path'] in old_hashes and
            str(Path(r['path']).relative_to(REPO)) not in CHANGED_OLD),
        'indexed successor must extend the actual stopped publication with one exact bounded source transition')
    target = directory / 'code_sources'
    require(not target.exists(), 'indexed epoch never overwrites retained source bytes')
    target.mkdir(mode=0o700)
    copies, total = [], 0
    for index, ref in enumerate(refs):
        member = str(Path(ref['path']).relative_to(REPO))
        raw = subprocess.check_output(['git', 'show', commit + ':' + member], cwd=REPO)
        total += len(raw)
        require(len(raw) <= MAX_SOURCE_BYTES and total <= MAX_TOTAL_BYTES and
            hashlib.sha256(raw).hexdigest() == ref['sha256'], 'current indexed source differs from committed Git bytes')
        value = {'schema': CODE_SCHEMA, 'code_commit': commit, 'original_path': ref['path'], 'sha256': ref['sha256'],
            'bytes': len(raw), 'raw_hex': raw.hex()}
        copies.append(_write(target / (f'{index:03d}_' + ref['sha256'] + '.json'), _encode(value), root))
    value = {'schema': EPOCH_SCHEMA, 'code_commit': commit, 'committed_sources': refs, 'carried_sources': copies}
    return _write(directory / 'current_code_epoch.json', _encode(value), root)


def validate_current_code_epoch(store, resume, ready, closure):
    ref = ready.get('current_code_epoch_source')
    reference(ref)
    require(resume.get('current_code_epoch_source') == ref, 'indexed resume/ready source epoch differs')
    epoch = store.get(ref, False)
    require(type(epoch) is dict and set(epoch) == {'schema', 'code_commit', 'committed_sources', 'carried_sources'} and
        epoch['schema'] == EPOCH_SCHEMA and epoch['code_commit'] == ready.get('code_commit') and
        epoch['committed_sources'] == ready.get('committed_sources'), 'indexed current raw source epoch differs')
    repo = stopped._repo(closure['committed_sources'])
    previous, wanted = _epoch_paths(closure, repo)
    stopped._commit(epoch['code_commit'])
    remote = store.get(ready['predecessor']['remote'], False)
    require(remote.get('proof', {}).get('code_epochs', {}).get('code_commit') == previous['code_commit'] and
        epoch['code_commit'] != previous['code_commit'] and stopped._vector(epoch['committed_sources'], repo) == wanted,
        'indexed freshness must compare against validated stopped publication epoch')
    hashes = {r['path']: r['sha256'] for r in previous['committed_sources']}
    require(all(r['sha256'] == hashes[r['path']] for r in epoch['committed_sources'] if r['path'] in hashes and
        str(Path(r['path']).relative_to(repo)) not in CHANGED_OLD), 'unrelated stopped source cannot change')
    stopped._envelopes(store, epoch, epoch['committed_sources'], epoch['code_commit'])
    return {'code_commit': epoch['code_commit'], 'complete_raw_source_members': len(wanted),
        'predecessor_publication_code_commit': previous['code_commit']}
