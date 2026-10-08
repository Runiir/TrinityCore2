"""Admit the reviewed UI172 offline baseline without replay during live input.

Full admission and portable carry replay the unchanged excluded parent proof.
The bounded runtime cache only stream-checks the admitted full-cache digest.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tarfile
from urllib.request import urlopen

from . import bag_swap_failed_evidence as parent
from . import bag_swap_sources as original
from .item_actionbar_contract import require, finite, strict_equal

ROOT = parent.ROOT
REPO = Path(__file__).resolve().parents[2]
POINTER = 'artifacts/client_harness/442_interactions_20261008_172.tar.gz.dvc'
CACHE_SCHEMA = 'client442_bag_swap_fresh_predecessor_authority_v1'
RUNTIME_SCHEMA = 'client442_bag_swap_fresh_runtime_authority_v1'
ANCESTRY_SCHEMA = 'client442_bag_swap_fresh_ancestry_v1'
CORE_FIELDS = original.CORE_FIELDS
ROLES = original.ROLES
VALUE_ROLES = original.VALUE_ROLES
MAX_RUNTIME_BYTES = 1024 * 1024
MAX_CACHE_BYTES = 512 * 1024 * 1024
MAX_MEMBERS = 100000
CURRENT_FILES = ('tools/client_compatibility/bag_swap_fresh_sources.py',
    'tools/client_compatibility/world/tests/test_bag_swap_fresh_sources.py')
_ACCEPTED_REMOTE_SOURCE = {
    'path': str(ROOT / 'evidence/ui172_failed_entry_remote_review01.json'),
    'sha256': '0ac9d684b073b553fa2d4c127f4e44bf81b7a6783a55feae71c7fc4fd0645b98'}
bound, reference = original.bound, original.reference


def _root(root=None):
    root = Path(root or ROOT)
    require(root.is_absolute() and '..' not in root.parts and root == parent.ROOT,
        'one actual private parent authority root required')
    return root


def _member(ref, root):
    reference(ref)
    path = Path(ref['path'])
    require(path.is_relative_to(root / 'evidence') and str(path) == ref['path'] and path.suffix == '.json',
        'ordinary original private authority JSON required')
    return str(path.relative_to(root))


def _json_file(path, *, root=None, limit=MAX_CACHE_BYTES):
    root, path = _root(root), Path(path)
    _member({'path': str(path), 'sha256': '0' * 64}, root)
    source = bound(path)
    require(path.stat().st_size <= limit, 'bounded immutable authority JSON required')
    try:
        def invalid(value): raise ValueError(value)
        with path.open('r') as handle:
            value = json.load(handle, parse_constant=invalid)
    except (ValueError, UnicodeError) as error:
        raise RuntimeError('authority source must contain complete finite JSON') from error
    require(type(value) is dict and bound(path) == source, 'authority JSON changed during admission')
    return value, source


def _pointer_bytes(pointer, raw_hex, cp, remote):
    require(type(cp) is dict and cp.get('cloud_verified') is True and
        cp.get('file') == POINTER.removesuffix('.dvc') and type(cp.get('bytes')) is int and cp['bytes'] > 0 and
        type(cp.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', cp['sha256']) and
        remote.get('pointer') == POINTER and type(remote.get('bytes')) is int and remote['bytes'] == cp['bytes'] and
        remote.get('archive_sha256') == cp['sha256'] and type(pointer) is dict and
        set(pointer) == {'source', 'pointer', 'oid', 'bytes'} and pointer.get('pointer') == POINTER and
        pointer.get('oid') == remote.get('object_md5') and type(pointer['oid']) is str and
        re.fullmatch('[0-9a-f]{32}', pointer['oid']) and type(pointer['bytes']) is int and pointer['bytes'] == cp['bytes'],
        'actual reviewed UI172 compressed checkpoint and DVC identity differ')
    reference(pointer['source'])
    require(Path(pointer['source']['path']).as_posix().endswith('/' + POINTER) and
        pointer['source']['sha256'] == remote.get('pointer_sha256') and type(raw_hex) is str and
        0 < len(raw_hex) <= 8192 and len(raw_hex) % 2 == 0 and re.fullmatch('[0-9a-f]+', raw_hex),
        'bounded exact original UI172 DVC pointer bytes required')
    raw = bytes.fromhex(raw_hex)
    require(hashlib.sha256(raw).hexdigest() == pointer['source']['sha256'], 'UI172 DVC pointer source bytes changed')
    try:
        text = raw.decode('utf-8')
    except UnicodeError as error:
        raise RuntimeError('UI172 DVC pointer must be UTF-8') from error
    require(re.findall(r'^\s*-?\s*md5:\s*([0-9a-f]{32})\s*$', text, re.MULTILINE) == [pointer['oid']] and
        re.findall(r'^\s*size:\s*([0-9]+)\s*$', text, re.MULTILINE) == [str(cp['bytes'])] and
        re.findall(r'^\s*path:\s*(\S+)\s*$', text, re.MULTILINE) == [Path(cp['file']).name] and
        re.search(r'^\s*hash:\s*md5\s*$', text, re.MULTILINE), 'actual UI172 pointer object descriptor differs')


def _tracking(graph, cp, prefix):
    from .review_bag_swap_failed_checkpoint import manifest
    selected = manifest(cp, prefix)
    require(type(graph) is dict and set(graph) == {'data', 'digests', 'journals'} and
        type(graph['data']) is dict and type(graph['digests']) is dict and type(graph['journals']) is dict and
        0 < len(selected) <= MAX_MEMBERS and
        set(graph['data']) == {p for p in selected if p.endswith('.json')} and
        set(graph['journals']) == {p for p in selected if p.endswith('.jsonl')} and
        set(graph['digests']) == set(selected) and
        all(graph['digests'][p] == selected[p]['sha256'] for p in selected),
        'complete first-stream UI172 graph, raw journals and manifest hashes required')
    metadata = graph['data'].get('tracking/checkpoint.json')
    require(type(metadata) is dict and strict_equal(metadata.get('files'),
        [r for r in cp['file_manifest'] if not r['path'].startswith('tracking/')]),
        'actual UI172 archived metadata partition differs')
    tracking = parent.tracking_state()
    tracking.update(manifest=selected, digests=graph['digests'], batch_prefix=prefix,
        raw_journals=graph['journals'], archived_metadata=metadata)
    for member in parent.TRACKING_MEMBERS:
        rows = graph['journals'][member]
        require(type(rows) is list, 'complete original UI172 tracking rows required')
        parent.collect(member, rows, graph['data'], tracking)
        tracking['journal_counts'][member] = {'rows': len(rows), 'bytes': selected[member]['bytes'],
            'sha256': selected[member]['sha256']}
    return tracking


def validate_bundle(values, refs, graph, *, root=None):
    root = _root(root)
    require(type(values) is dict and set(values) == VALUE_ROLES and type(refs) is dict and set(refs) == ROLES and
        all(type(values[k]) is dict for k in ROLES | {'dvc_pointer'}), 'exact latest UI172 authority roles required')
    members = {role: _member(ref, root) for role, ref in refs.items()}
    c, remote, cp, stop = (values[k] for k in ('closure', 'remote', 'checkpoint', 'primary_stop'))
    require(refs['closure'] == parent._CLOSURE_SOURCE and refs['remote'] == _ACCEPTED_REMOTE_SOURCE and
        remote.get('checkpoint_source') == refs['checkpoint'] and
        Path(refs['checkpoint']['path']) == Path(refs['closure']['path']).parent.parent / 'checkpoint_receipt.json',
        'actual immutable admitted UI172 closure, remote review and checkpoint required')
    _pointer_bytes(values['dvc_pointer'], values['pointer_raw_hex'], cp, remote)
    prefix = str(Path(members['closure']).parent.parent) + '/'
    tracking = _tracking(graph, cp, prefix)
    require(graph['digests'].get(members['closure']) == refs['closure']['sha256'] and
        strict_equal(graph['data'].get(members['closure']), c), 'latest closed UI172 bytes or values differ')
    computed = parent.proof(graph['data'], graph['digests'], tracking)
    store = parent.Sources(graph['data'], graph['digests'], graph['journals'], root=root)
    old_cache = store.get(c['authority_source'], False)
    require(old_cache.get('schema') == original.CACHE_SCHEMA and
        old_cache.get('refs', {}).get('primary_stop') == refs['primary_stop'] == c.get('primary_stop_source') ==
            c.get('predecessor', {}).get('primary_stop') and
        strict_equal(old_cache.get('values', {}).get('primary_stop'), stop),
        'original primary stop must remain inherited from the independently proven UI171 graph')
    require(remote.get('schema') == 'client442_bag_swap_failed_remote_review_v1' and
        all(remote.get(k) is True for k in ('actual_remote_verified', 'complete_manifest_verified',
            'complete_json_png_jsonl_verified')) and remote.get('local_archive_created') is False and
        remote.get('qualification_added') is False and type(remote.get('operations_admitted')) is int and
        remote['operations_admitted'] == 0 and finite(remote.get('reviewed_at')) and
        remote['reviewed_at'] > c['finished_at'] and
        type(remote.get('json_members')) is int and remote['json_members'] == len(graph['data']) and
        type(remote.get('png_members')) is int and remote['png_members'] == sum(p.endswith('.png') for p in graph['digests']) and
        type(remote.get('journal_members')) is int and remote['journal_members'] == len(graph['journals']) and
        strict_equal(remote.get('proof'), computed), 'actual complete remote UI172 proof or member counts differ')
    core = {'closure': c, 'snapshot': c['after'], 'predecessor': refs, 'primary_stop_source': refs['primary_stop'],
        'dvc_pointer': values['dvc_pointer'], 'runtime': c['runtime'], 'origin_actor': c['actor']}
    _runtime_core(core, root)
    return {**core, 'values': values, 'graph': graph, 'remote_proof': computed,
        'pointer_raw_hex': values['pointer_raw_hex'], 'archive': {'file': cp['file'], 'bytes': cp['bytes'],
            'sha256': cp['sha256'], 'manifest': cp['file_manifest']}}


def source_bundle(closure, remote, checkpoint, *, root=None, repo=None):
    from .review_hunter_learn_checkpoint import remote_options, remote_request
    from .review_bag_swap_failed_checkpoint import inspect_archive
    root, repo = _root(root), Path(repo or REPO)
    values, refs = {}, {}
    for role, path in (('closure', closure), ('remote', remote), ('checkpoint', checkpoint)):
        values[role], refs[role] = _json_file(path, root=root)
    require(refs['closure'] == parent._CLOSURE_SOURCE and refs['remote'] == _ACCEPTED_REMOTE_SOURCE,
        'only the actual admitted latest UI172 sources may be streamed')
    pointer_path = repo / POINTER
    pointer_ref = bound(pointer_path)
    require(pointer_path.stat().st_size <= 4096, 'bounded actual UI172 pointer required')
    raw_pointer = pointer_path.read_bytes()
    pointer = {'source': pointer_ref, 'pointer': POINTER, 'oid': values['remote'].get('object_md5'),
        'bytes': values['checkpoint'].get('bytes')}
    values.update(dvc_pointer=pointer, pointer_raw_hex=raw_pointer.hex())
    _pointer_bytes(pointer, raw_pointer.hex(), values['checkpoint'], values['remote'])
    prefix = str(Path(_member(refs['closure'], root)).parent.parent) + '/'
    with urlopen(remote_request(remote_options(repo), pointer['oid']), timeout=60) as stream:
        data, digests, tracking, count = inspect_archive(stream, values['checkpoint'], prefix)
    require(count == pointer['bytes'] and tracking['compressed_md5'] == pointer['oid'],
        'actual complete UI172 compressed remote MD5 differs')
    graph = {'data': data, 'digests': digests, 'journals': tracking['raw_journals']}
    refs['primary_stop'] = values['closure']['primary_stop_source']
    cache = parent.Sources(data, digests, graph['journals'], root=root).get(values['closure']['authority_source'], False)
    values['primary_stop'] = cache['values']['primary_stop']
    result = validate_bundle(values, refs, graph, root=root)
    require(all(bound(path) == refs[role] for role, path in
        (('closure', closure), ('remote', remote), ('checkpoint', checkpoint))) and
        bound(pointer_path) == pointer_ref, 'UI172 admission sources changed during streaming')
    return result


def cache_value(old):
    require(type(old) is dict and all(k in old for k in ('values', 'predecessor', 'graph', 'remote_proof')),
        'strict admitted UI172 source bundle required')
    actual = validate_bundle(old['values'], old['predecessor'], old['graph'])
    require(all(k in old and strict_equal(old[k], value) for k, value in actual.items()),
        'cache writer requires the exact independently admitted source bundle')
    return {'schema': CACHE_SCHEMA, 'core_sha256': hashlib.sha256(_encode({k: old[k] for k in CORE_FIELDS})).hexdigest(),
        'values': old['values'], 'refs': old['predecessor'], 'graph': old['graph']}


def validate_cache(cache, *, root=None):
    require(type(cache) is dict and set(cache) == {'schema', 'core_sha256', 'values', 'refs', 'graph'} and
        cache['schema'] == CACHE_SCHEMA, 'distinct full latest UI172 authority cache required')
    old = validate_bundle(cache['values'], cache['refs'], cache['graph'], root=root)
    require(cache['core_sha256'] == hashlib.sha256(_encode({k: old[k] for k in CORE_FIELDS})).hexdigest(),
        'source-owned full-cache core commitment differs')
    return old


def cached_bundle(path, *, root=None):
    value, _ = _json_file(path, root=root)
    return validate_cache(value, root=root)


def _runtime_core(core, root):
    from .bag_swap_contract import owned_snapshot
    from .bag_swap_preservation import exact_precision
    require(type(core) is dict and set(core) == set(CORE_FIELDS) and
        all(type(core[k]) is dict for k in CORE_FIELDS), 'exact typed fresh compact core required')
    c, snapshot, refs, pointer, runtime, actor = (core[k] for k in
        ('closure', 'snapshot', 'predecessor', 'dvc_pointer', 'runtime', 'origin_actor'))
    require(c.get('phase') == parent.sources.PHASE and c.get('schema') == parent.sources.SCHEMA and
        c.get('completed') is True and c.get('failure') is None and finite(c.get('started_at')) and
        finite(c.get('finished_at')) and 0 < c['started_at'] < c['finished_at'] and
        c.get('controller') == 'code' and c.get('model') is None and c.get('revision') is None and
        all(c.get(k) is False for k in ('input_sent', 'mutation_sent', 'qualification_added')) and
        c.get('excluded_failed_entry') is True and type(c.get('operations_admitted')) is int and
        c['operations_admitted'] == 0 and c.get('cases') == c.get('cleanup') == [] and
        strict_equal(c.get('shutdown_checks'), dict.fromkeys(parent.sources.STOP_CHECKS, True)),
        'fresh compact closure requires the actually excluded all-eight stopped UI172 identity')
    owned_snapshot(snapshot)
    require(strict_equal(c.get('before'), snapshot) and strict_equal(c.get('after'), snapshot) and
        strict_equal(c.get('all_offline_snapshot'), snapshot) and strict_equal(c.get('runtime'), runtime) and
        strict_equal(c.get('actor'), actor), 'latest compact all-six snapshot, runtime or actor differs')
    require(set(refs) == ROLES and refs['closure'] == parent._CLOSURE_SOURCE and
        refs['remote'] == _ACCEPTED_REMOTE_SOURCE and Path(refs['checkpoint']['path']) ==
            Path(refs['closure']['path']).parent.parent / 'checkpoint_receipt.json', 'fresh latest authority roles differ')
    for ref in refs.values():
        _member(ref, root)
    require(core['primary_stop_source'] == refs['primary_stop'] == c.get('primary_stop_source') ==
        c.get('predecessor', {}).get('primary_stop'), 'fresh primary stop ancestry differs')
    require(type(actor.get('guid')) is int and actor['guid'] == 2 and type(actor.get('account_id')) is int and
        actor['account_id'] == 2 and actor.get('actor') == 'scout', 'fresh original actor2 authority required')
    exact = c.get('exact_precision')
    require(type(exact) is dict and exact.get('query') == parent.sources.preservation.PRECISION_QUERY and
        exact.get('source') == c.get('capture_source') and exact.get('input_sent') is False and
        exact.get('mutation_sent') is False and strict_equal(exact.get('before'), snapshot) and
        strict_equal(exact.get('after'), snapshot), 'actual latest offline FLOAT source boundary required')
    exact_precision(exact['row'], snapshot)
    require(type(pointer) is dict and set(pointer) == {'source', 'pointer', 'oid', 'bytes'} and
        pointer.get('pointer') == POINTER and type(pointer.get('oid')) is str and
        re.fullmatch('[0-9a-f]{32}', pointer['oid']) and type(pointer.get('bytes')) is int and pointer['bytes'] > 0,
        'compact actual UI172 DVC object identity required')
    reference(pointer['source'])
    require(Path(pointer['source']['path']).as_posix().endswith('/' + POINTER), 'compact pointer path differs')
    require({'worldserver', 'modern_world', 'client'} <= set(runtime), 'all owned original lifetimes required')
    for lifetime in [*(runtime[k] for k in ('worldserver', 'modern_world', 'client')), c.get('game_before')]:
        require(type(lifetime) is dict and type(lifetime.get('pid')) is int and lifetime['pid'] > 0 and
            type(lifetime.get('start_ticks')) is str and re.fullmatch('[1-9][0-9]*', lifetime['start_ticks']),
            'canonical actually stopped process lifetime required')


def _runtime_value(value, full_ref, root):
    require(type(value) is dict and set(value) == {'schema', 'authority_source', 'core'} and
        value['schema'] == RUNTIME_SCHEMA and value['authority_source'] == full_ref,
        'distinct compact latest UI172 authority must bind its admitted full-cache source')
    _member(full_ref, root)
    _runtime_core(value['core'], root)
    require(len(_encode(value)) <= MAX_RUNTIME_BYTES, 'fresh compact authority exceeds one MiB')


def compact_authority(old, full_ref, *, root=None):
    value = {'schema': RUNTIME_SCHEMA, 'authority_source': full_ref, 'core': {k: old[k] for k in CORE_FIELDS}}
    require(strict_equal(old['closure'], old['values']['closure']) and
        strict_equal(old['values']['remote'].get('proof'), old['remote_proof']) and
        strict_equal(old['dvc_pointer'], old['values']['dvc_pointer']), 'fresh compact core must derive from admitted values')
    _runtime_value(value, full_ref, _root(root))
    return deepcopy(value)


def cached_runtime(path, full_ref, *, root=None):
    root = _root(root)
    _member(full_ref, root)
    require(Path(path) != Path(full_ref['path']), 'compact runtime cache must be distinct from full authority')
    value, _ = _json_file(path, root=root, limit=MAX_RUNTIME_BYTES)
    _runtime_value(value, full_ref, root)
    commitment = _full_commitment(full_ref, root)
    require(commitment == hashlib.sha256(_encode(value['core'])).hexdigest(),
        'compact core differs from source-owned admitted full-cache commitment')
    return value['core']


def _full_commitment(ref, root):
    """Hash the full file once while retaining only its canonical small header."""
    _member(ref, root)
    path = Path(ref['path'])
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
        'ordinary source-owned full authority required')
    def identity(value):
        return tuple(getattr(value, k) for k in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
    before, digest, prefix = path.stat(), hashlib.sha256(), b''
    require(0 < before.st_size <= MAX_CACHE_BYTES, 'bounded admitted full authority required')
    with path.open('rb') as handle:
        require(identity(os.fstat(handle.fileno())) == identity(before), 'full authority changed before stream hashing')
        while chunk := handle.read(original.HASH_CHUNK_BYTES):
            digest.update(chunk)
            if len(prefix) < 1024:
                prefix += chunk[:1024 - len(prefix)]
        require(identity(os.fstat(handle.fileno())) == identity(before), 'full authority changed while stream hashing')
    require(not any(p.is_symlink() for p in (path, *path.parents)) and identity(path.stat()) == identity(before) and
        digest.hexdigest() == ref['sha256'], 'admitted full fresh cache bytes changed')
    header = re.match(rb'^\{"core_sha256":"([0-9a-f]{64})","graph":', prefix)
    require(header is not None, 'canonical source-owned full-cache core header required')
    return header[1].decode()


def _encode(value):
    try:
        return (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
    except (TypeError, ValueError, UnicodeError) as error:
        raise RuntimeError('authority must contain finite portable JSON') from error


def _write(path, raw, root):
    _member({'path': str(path), 'sha256': '0' * 64}, root)
    require(path.parent.is_dir() and not path.exists() and
        not any(p.is_symlink() for p in path.parents), 'new ordinary private authority file required')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    result = bound(path)
    require(result['sha256'] == hashlib.sha256(raw).hexdigest(), 'new source authority write differs')
    return result


def write_cache(directory, old, *, root=None):
    root = _root(root)
    raw = _encode(cache_value(old))
    require(len(raw) <= MAX_CACHE_BYTES, 'bounded fresh full cache exceeded')
    return _write(Path(directory) / 'authority.json', raw, root)


def write_runtime(directory, old, full_ref, *, root=None):
    root = _root(root)
    value = compact_authority(old, full_ref, root=root)
    require(_full_commitment(full_ref, root) == hashlib.sha256(_encode(value['core'])).hexdigest(),
        'runtime writer core differs from admitted full authority')
    return _write(Path(directory) / 'runtime_authority.json', _encode(value), root)


class _Observed(dict):
    def __init__(self, value, used):
        super().__init__(value)
        self.used = used

    def get(self, key, default=None):
        if key in self:
            self.used.add(key)
        return super().get(key, default)

    def __getitem__(self, key):
        self.used.add(key)
        return super().__getitem__(key)


def required_members(old):
    """Record actual parent proof JSON, frame and complete-journal accesses."""
    graph, used = old['graph'], set(parent.TRACKING_MEMBERS) | {'tracking/checkpoint.json'}
    saved = parent.Sources
    class ObservedSources(saved):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.data = _Observed(self.data, used)
            self.digests = _Observed(self.digests, used)
            self.raw_journals = _Observed(self.raw_journals, used)
    try:
        parent.Sources = ObservedSources
        tracking = _tracking(graph, old['values']['checkpoint'], str(Path(_member(old['predecessor']['closure'], _root())).parent.parent) + '/')
        require(strict_equal(parent.proof(graph['data'], graph['digests'], tracking), old['remote_proof']),
            'required source collection must retain the exact admitted parent proof')
    finally:
        parent.Sources = saved
    for member, value in graph['data'].items():
        if type(value) is dict and (value.get('schema') in (parent.ANCESTRY_SCHEMA, parent.JOURNAL_SCHEMA) or
            value.get('phase') == parent.sources.PHASE):
            used.add(member)
    require(used <= set(graph['digests']), 'required source collection escaped the verified full manifest')
    return sorted(used)


def carry_authority(batch, full_ref, *, admitted=None, root=None, repo=None):
    """Re-stream only proof-owned raw files; never retain a compressed archive."""
    from .review_hunter_learn_checkpoint import remote_options, remote_request
    from .review_bag_swap_failed_checkpoint import GzipReader, _name
    root, repo, batch = _root(root), Path(repo or REPO), Path(batch)
    _member(full_ref, root)
    require(bound(full_ref['path']) == full_ref and batch.parent == root / 'evidence' and batch.is_dir() and
        '..' not in batch.parts and not any(p.is_symlink() for p in (batch, *batch.parents)),
        'actual admitted fresh cache and ordinary outer batch required')
    old = admitted if admitted is not None else cached_bundle(full_ref['path'], root=root)
    wanted = required_members(old)
    manifest = {row['path']: row for row in old['archive']['manifest']}
    destination = batch / 'predecessor_ui172'
    require(not destination.exists(), 'new source-owned UI172 carry directory required')
    destination.mkdir(mode=0o700)
    rows, seen = [], set()
    pointer = old['dvc_pointer']
    with urlopen(remote_request(remote_options(repo), pointer['oid']), timeout=60) as stream:
        reader = GzipReader(stream)
        with tarfile.open(fileobj=reader, mode='r|', bufsize=512) as archive:
            for member in archive:
                name = _name(member.name)
                if name not in wanted:
                    continue
                expected = manifest[name]
                require(member.isfile() and name not in seen and member.size == expected['bytes'],
                    'required raw parent member multiplicity or bytes differ')
                target = destination / (expected['sha256'] + Path(name).suffix)
                digest, total = hashlib.sha256(), 0
                output = target.open('xb') if not target.exists() else None
                if output is not None:
                    os.chmod(target, 0o600)
                try:
                    with archive.extractfile(member) as source:
                        while chunk := source.read(256 * 1024):
                            digest.update(chunk)
                            total += len(chunk)
                            if output is not None:
                                output.write(chunk)
                finally:
                    if output is not None:
                        output.flush()
                        os.fsync(output.fileno())
                        output.close()
                require(total == expected['bytes'] and digest.hexdigest() == expected['sha256'],
                    'required raw UI172 parent member SHA256 differs')
                require(bound(target)['sha256'] == expected['sha256'] and target.stat().st_size == expected['bytes'],
                    'same-hash source-owned parent copies differ')
                seen.add(name)
                rows.append({'original_path': str(root / name), 'original_member': name, **{k: expected[k] for k in ('sha256', 'bytes')},
                    'copy_member': str(target.relative_to(root))})
            require(archive.fileobj.tell() == reader.delivered, 'unread parent tar buffer cannot hide payload')
        while chunk := reader.read(1024 * 1024):
            require(not chunk.strip(b'\0'), 'hidden parent tar tail differs')
    require(seen == set(wanted) and reader.complete and reader.bytes == old['archive']['bytes'] and
        reader.digest.hexdigest() == old['archive']['sha256'] and reader.md5.hexdigest() == pointer['oid'],
        'complete actual parent compressed SHA256/bytes/MD5 differ')
    authorities = []
    for role in ('remote', 'checkpoint'):
        ref = old['predecessor'][role]
        require(bound(ref['path']) == ref, 'actual remote/checkpoint source changed before carrying')
        raw = Path(ref['path']).read_bytes()
        target = destination / (ref['sha256'] + '.json')
        _write(target, raw, root)
        authorities.append({'role': role, 'original_path': ref['path'], 'sha256': ref['sha256'],
            'bytes': len(raw), 'copy_member': str(target.relative_to(root))})
    value = {'schema': ANCESTRY_SCHEMA, 'authority_source': full_ref, 'archive': old['archive'],
        'dvc_pointer': pointer, 'pointer_raw_hex': old['pointer_raw_hex'], 'members': sorted(rows, key=lambda r: r['original_member']),
        'authorities': authorities, 'actual_remote_verified': True, 'compressed_md5': pointer['oid'],
        'local_archive_created': False}
    _write(batch / 'predecessor_ui172.json', _encode(value), root)
    return value


def validate_carry(store, ready, *, root=None):
    """Rebind copied raw parent members before replaying the original keyspace."""
    root = _root(root)
    maps = [v for v in store.data.values() if type(v) is dict and v.get('schema') == ANCESTRY_SCHEMA]
    require(len(maps) == 1, 'one distinct latest UI172 carry map required')
    value = maps[0]
    cache = store.get(ready['authority_source'], False)
    old = validate_cache(cache, root=root)
    require(value.get('authority_source') == ready['authority_source'] and
        strict_equal(value.get('archive'), old['archive']) and strict_equal(value.get('dvc_pointer'), old['dvc_pointer']) and
        value.get('pointer_raw_hex') == old['pointer_raw_hex'] and value.get('actual_remote_verified') is True and
        value.get('local_archive_created') is False and value.get('compressed_md5') == old['dvc_pointer']['oid'] and
        strict_equal(ready.get('predecessor'), old['predecessor']), 'actual latest parent carry authority differs')
    rows = value.get('members')
    require(type(rows) is list and [r.get('original_member') for r in rows] == required_members(old),
        'exact proof-owned latest UI172 raw member set required')
    manifest = {r['path']: r for r in old['archive']['manifest']}
    graph = {'data': dict(old['graph']['data']), 'digests': dict(old['graph']['digests']),
        'journals': dict(old['graph']['journals'])}
    for row in rows:
        name, copy = row.get('original_member'), row.get('copy_member')
        require(set(row) == {'original_path', 'original_member', 'sha256', 'bytes', 'copy_member'} and
            name in manifest and row['original_path'] == str(root / name) and type(copy) is str and
            not Path(copy).is_absolute() and '..' not in Path(copy).parts and
            type(row['bytes']) is int and row['bytes'] == manifest[name]['bytes'] and
            row['sha256'] == manifest[name]['sha256'] == store.digests.get(copy),
            'actual raw carried UI172 member differs from immutable full manifest')
        if name.endswith('.json'):
            require(strict_equal(store.data.get(copy), graph['data'][name]), 'carried raw parent JSON semantics differ')
            graph['data'][name] = store.data[copy]
        elif name.endswith('.jsonl'):
            actual = getattr(store, 'raw_journals', {}).get(copy)
            require(type(actual) is list and strict_equal(actual, graph['journals'][name]),
                'carried full ordered original parent journal differs')
            graph['journals'][name] = actual
    authorities = value.get('authorities')
    require(type(authorities) is list and len(authorities) == 2 and {r.get('role') for r in authorities} == {'remote', 'checkpoint'},
        'both actual latest remote/checkpoint raw source copies required')
    for row in authorities:
        require(set(row) == {'role', 'original_path', 'sha256', 'bytes', 'copy_member'} and
            {'path': row['original_path'], 'sha256': row['sha256']} == old['predecessor'][row['role']] and
            type(row['bytes']) is int and row['bytes'] > 0 and store.digests.get(row['copy_member']) == row['sha256'] and
            strict_equal(store.data.get(row['copy_member']), old['values'][row['role']]),
            'actual carried latest authority source bytes differ')
    validate_bundle(old['values'], old['predecessor'], graph, root=root)
    return old
