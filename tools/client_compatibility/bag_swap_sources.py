"""Read-only admission of the actual remotely reviewed UI171 closed item pause.

The first admission streams the actual DVC object. Later input helpers consume a
hash-bound private cache of that derived authority; they never need to fetch an
archive while a game input is pending. Runtime/UI/SQL imports are unnecessary.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tarfile
from urllib.request import urlopen

from . import lab_runtime as lab
from .item_actionbar_contract import require, finite, owned_snapshot, strict_equal
from .item_actionbar_sources import (closed, private_json, linked, reference,
    rest_sources)

POINTER = 'artifacts/client_harness/442_interactions_20261008_171.tar.gz.dvc'
CACHE_SCHEMA = 'client442_bag_swap_predecessor_authority_v1'
RUNTIME_SCHEMA = 'client442_bag_swap_runtime_authority_v1'
CORE_FIELDS = ('closure', 'snapshot', 'predecessor', 'primary_stop_source', 'dvc_pointer', 'runtime', 'origin_actor')
MAX_RUNTIME_BYTES = 1024 * 1024
HASH_CHUNK_BYTES = 256 * 1024
ROLES = frozenset(('closure', 'remote', 'checkpoint', 'primary_stop'))
VALUE_ROLES = ROLES | {'dvc_pointer', 'pointer_raw_hex'}
MAX_GRAPH_MEMBERS = 4096
MAX_JSON_BYTES = 256 * 1024 * 1024
MAX_FULL_JOURNAL_BYTES = 512 * 1024 * 1024
HEX64, HEX32 = '[0-9a-f]{64}', '[0-9a-f]{32}'


def bound(path):
    """Hash ordinary immutable source bytes in bounded chunks, including caches."""
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
        'source must be an ordinary immutable file')
    def identity(value):
        return tuple(getattr(value, key) for key in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        require(identity(os.fstat(handle.fileno())) == identity(before), 'source changed before streaming its digest')
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
        require(identity(os.fstat(handle.fileno())) == identity(before), 'source changed while streaming its digest')
    require(not any(p.is_symlink() for p in (path, *path.parents)) and identity(path.stat()) == identity(before),
        'source changed after streaming its digest')
    return {'path': str(path.resolve()), 'sha256': digest.hexdigest()}


def _pointer_identity(checkpoint, remote):
    require(type(checkpoint) is dict and type(remote) is dict and
        remote.get('pointer') == POINTER and checkpoint.get('file') == POINTER.removesuffix('.dvc') and
        checkpoint.get('cloud_verified') is True and type(checkpoint.get('bytes')) is int and
        checkpoint['bytes'] > 0 and type(checkpoint.get('sha256')) is str and
        re.fullmatch(HEX64, checkpoint['sha256']) and type(remote.get('bytes')) is int and
        remote['bytes'] == checkpoint['bytes'] and remote.get('archive_sha256') == checkpoint['sha256'],
        'actual UI171 compressed checkpoint and remote identity differ')


def _pointer_bytes(pointer, raw_hex, checkpoint, remote):
    _pointer_identity(checkpoint, remote)
    require(type(pointer) is dict and set(pointer) == {'source', 'pointer', 'oid', 'bytes'} and
        pointer['pointer'] == POINTER and type(pointer['oid']) is str and re.fullmatch(HEX32, pointer['oid']) and
        type(pointer['bytes']) is int and pointer['bytes'] == checkpoint['bytes'],
        'actual UI171 DVC pointer descriptor differs')
    reference(pointer['source'])
    require(Path(pointer['source']['path']).as_posix().endswith('/' + POINTER) and
        type(raw_hex) is str and 0 < len(raw_hex) <= 8192 and len(raw_hex) % 2 == 0 and
        re.fullmatch('[0-9a-f]+', raw_hex), 'bounded original UI171 DVC pointer bytes are required')
    raw = bytes.fromhex(raw_hex)
    require(hashlib.sha256(raw).hexdigest() == pointer['source']['sha256'],
        'original UI171 DVC pointer bytes differ from their source digest')
    try:
        text = raw.decode('utf-8')
    except UnicodeError as error:
        raise RuntimeError('original UI171 DVC pointer is not UTF-8') from error
    hashes = re.findall(r'^\s*-?\s*md5:\s*([0-9a-f]{32})\s*$', text, re.MULTILINE)
    sizes = re.findall(r'^\s*size:\s*([0-9]+)\s*$', text, re.MULTILINE)
    paths = re.findall(r'^\s*path:\s*(\S+)\s*$', text, re.MULTILINE)
    require(hashes == [pointer['oid']] and sizes == [str(checkpoint['bytes'])] and
        paths == [Path(checkpoint['file']).name] and re.search(r'^\s*hash:\s*md5\s*$', text, re.MULTILINE),
        'original UI171 DVC pointer object identity differs')


def dvc_pointer(checkpoint, remote, *, repo=None):
    """Read actual current pointer bytes; never assume a future archive digest."""
    _pointer_identity(checkpoint, remote)
    path = Path(repo or lab.REPO) / POINTER
    source = bound(path)
    raw = path.read_bytes()
    hashes = re.findall(rb'^\s*-?\s*md5:\s*([0-9a-f]{32})\s*$', raw, re.MULTILINE)
    require(len(hashes) == 1, 'published UI171 DVC pointer requires one real object hash')
    pointer = {'source': source, 'pointer': POINTER, 'oid': hashes[0].decode(), 'bytes': checkpoint['bytes']}
    _pointer_bytes(pointer, raw.hex(), checkpoint, remote)
    require(bound(path) == source, 'UI171 DVC pointer changed during admission')
    return pointer, raw.hex()


def _member(ref, root):
    reference(ref)
    path = Path(ref['path'])
    require(path.is_relative_to(root / 'evidence') and path.suffix == '.json' and
        str(path) == ref['path'], 'authority references must be original private absolute JSON files')
    return str(path.relative_to(root))


def _manifest(checkpoint, prefix):
    rows = checkpoint.get('file_manifest')
    require(type(rows) is list and 0 < len(rows) <= 100000 and all(type(row) is dict for row in rows),
        'bounded complete original UI171 checkpoint manifest is required')
    for row in rows:
        path = row.get('path')
        require(type(path) is str and path and not Path(path).is_absolute() and '..' not in Path(path).parts and
            str(Path(path)) == path and type(row.get('bytes')) is int and row['bytes'] >= 0 and
            type(row.get('sha256')) is str and re.fullmatch(HEX64, row['sha256']),
            'original UI171 manifest path, bytes or SHA256 differ')
    require(len({row['path'] for row in rows}) == len(rows), 'original UI171 manifest contains duplicate paths')
    selected = {row['path']: row for row in rows if row['path'].startswith(prefix) and
        Path(row['path']).suffix in ('.json', '.png')}
    require(0 < len(selected) <= MAX_GRAPH_MEMBERS and any(p.endswith('.png') for p in selected) and
        any(p.endswith('/episode.json') for p in selected) and
        sum(row['bytes'] for p, row in selected.items() if p.endswith('.json')) <= MAX_JSON_BYTES,
        'bounded complete original UI171 JSON and PNG manifest is required')
    return selected


def _journal_manifest(value, checkpoint):
    from .item_actionbar_evidence import TRACKING_MEMBERS
    require(type(value) is dict and set(value) == set(TRACKING_MEMBERS),
        'both first-stream-bound complete original UI171 journal identities are required')
    for member, row in value.items():
        require(type(row) is dict and set(row) == {'sha256', 'bytes'} and
            type(row['sha256']) is str and re.fullmatch(HEX64, row['sha256']) and
            type(row['bytes']) is int and 0 < row['bytes'] <= MAX_FULL_JOURNAL_BYTES,
            'first-stream-bound complete original UI171 journal SHA256 or bytes differ')
        # A future publisher may also manifest tracking bytes. Preserve agreement
        # when present; current UI171 manifests omit these two raw members.
        listed = [r for r in checkpoint['file_manifest'] if r['path'] == member]
        require(not listed or len(listed) == 1 and
            listed[0]['sha256'] == row['sha256'] and listed[0]['bytes'] == row['bytes'],
            'first-stream-bound UI171 journal differs from its checkpoint manifest')
    return value


def _inspect_archive(raw, checkpoint, prefix):
    """Hash complete original journals before filtering their semantic window.

    This mirrors the unchanged UI171 reader's JSON/PNG and compressed-byte
    admission, adding the raw journal identities absent from its checkpoint.
    """
    from . import item_actionbar_evidence as evidence
    from .review_hunter_learn_checkpoint import DigestReader
    selected = _manifest(checkpoint, prefix)
    data, digests, seen, journals = {}, {}, set(), {}
    tracking = evidence.tracking_state()
    tracking.update(digests=digests, manifest=selected)
    reader = DigestReader(raw)
    with tarfile.open(fileobj=reader, mode='r|gz') as archive:
        for member in archive:
            if member.name.startswith(prefix) and Path(member.name).suffix in ('.json', '.png'):
                require(member.name in selected, 'actual UI171 batch contains unmanifested JSON or PNG')
            if member.name in evidence.TRACKING_MEMBERS:
                require(member.isfile() and member.name not in journals and
                    0 < member.size <= MAX_FULL_JOURNAL_BYTES,
                    'actual complete UI171 journal is duplicate, not a file or outside its byte bound')
                digest, total = hashlib.sha256(), 0

                def rows(handle):
                    nonlocal total
                    for line in handle:
                        total += len(line)
                        digest.update(line)
                        yield json.loads(line)

                with archive.extractfile(member) as handle:
                    evidence.collect(member.name, rows(handle), data, tracking)
                require(total == member.size, 'complete original UI171 journal bytes were not consumed')
                journals[member.name] = {'sha256': digest.hexdigest(), 'bytes': total}
            if member.name not in selected:
                continue
            row = selected[member.name]
            require(member.isfile() and member.name not in seen and member.size == row['bytes'],
                'actual selected UI171 member type, multiplicity or size differs')
            digest, total, chunks, first = hashlib.sha256(), 0, [], b''
            with archive.extractfile(member) as handle:
                while chunk := handle.read(1024 * 1024):
                    first = first or chunk[:8]
                    total += len(chunk)
                    digest.update(chunk)
                    if member.name.endswith('.json'):
                        require(total <= 64 * 1024 * 1024, 'private UI171 JSON exceeds its bounded review size')
                        chunks.append(chunk)
            require(total == row['bytes'] and digest.hexdigest() == row['sha256'],
                'actual complete UI171 JSON/PNG bytes or SHA256 differ')
            if member.name.endswith('.json'):
                data[member.name] = json.loads(b''.join(chunks))
            else:
                require(first == b'\x89PNG\r\n\x1a\n', 'actual manifest UI171 PNG is not a PNG image')
            digests[member.name] = row['sha256']
            seen.add(member.name)
    while reader.read(1024 * 1024):
        pass
    require(seen == set(selected) and reader.bytes == checkpoint['bytes'] and
        reader.digest.hexdigest() == checkpoint['sha256'],
        'actual compressed UI171 archive identity or complete manifest differs')
    require(tracking['members'] == set(evidence.TRACKING_MEMBERS), 'actual UI171 archive lacks one journal')
    _journal_manifest(journals, checkpoint)
    return data, digests, tracking, journals, reader.bytes


def validate_bundle(values, refs, graph, *, root=None):
    """Re-evaluate a portable graph already derived from exact archive bytes.

    Callers must retain the cache/source digest. Final archive proofs independently
    rebind copied original raw members to this graph's original file manifest.
    """
    from . import item_actionbar_evidence as evidence
    root = Path(root or lab.ROOT)
    require(root == lab.ROOT and type(values) is dict and set(values) == VALUE_ROLES and
        type(refs) is dict and set(refs) == ROLES and all(type(v) is dict for k, v in values.items()
            if k != 'pointer_raw_hex'), 'complete original UI171 authority values and references are required')
    members = {role: _member(ref, root) for role, ref in refs.items()}
    c, r, cp, stop = (values[k] for k in ('closure', 'remote', 'checkpoint', 'primary_stop'))
    evidence.accepted(c, evidence.PHASE)
    evidence.accepted(stop, 'user_requested_primary_client_stopped')
    require(Path(refs['closure']['path']).name == 'episode.json' and
        Path(refs['checkpoint']['path']) == Path(refs['closure']['path']).parent.parent / 'checkpoint_receipt.json',
        'UI171 closure must use its actual original batch checkpoint receipt')
    require(c.get('primary_stop_source') == refs['primary_stop'] and
        c.get('predecessor', {}).get('primary_stop') == refs['primary_stop'],
        'original stopped primary must be inherited from the closed-pause predecessor graph')
    _pointer_bytes(values['dvc_pointer'], values['pointer_raw_hex'], cp, r)
    prefix = str(Path(members['closure']).parent.parent) + '/'
    selected = _manifest(cp, prefix)
    require(type(graph) is dict and set(graph) == {'data', 'digests', 'tracking', 'journal_manifest'} and
        type(graph['data']) is dict and type(graph['digests']) is dict and type(graph['tracking']) is dict,
        'complete portable UI171 graph is required')
    data, digests, tracking = graph['data'], graph['digests'], graph['tracking']
    _journal_manifest(graph['journal_manifest'], cp)
    require(set(data) == {p for p in selected if p.endswith('.json')} and set(digests) == set(selected) and
        all(type(digests[p]) is str and digests[p] == selected[p]['sha256'] for p in selected) and
        strict_equal(tracking.get('manifest'), selected) and strict_equal(tracking.get('digests'), digests) and
        type(tracking.get('members')) is list and tracking['members'] == sorted(evidence.TRACKING_MEMBERS),
        'portable UI171 graph omits or substitutes complete original JSON, PNG or journal members')
    require(members['closure'] in data and digests[members['closure']] == refs['closure']['sha256'] and
        strict_equal(data[members['closure']], c), 'supplied successful closure differs from the original archived bytes')
    portable_tracking = deepcopy(tracking)
    portable_tracking['members'] = set(portable_tracking['members'])
    computed = evidence.proof(deepcopy(data), dict(digests), portable_tracking)
    store = evidence.Sources(data, digests)
    require(strict_equal(store.get(refs['primary_stop']), stop), 'inherited original primary stop bytes differ')
    own = owned_snapshot(c.get('after'))
    require(strict_equal(c.get('before'), c['after']) and strict_equal(c.get('all_offline_snapshot'), c['after']) and
        strict_equal(stop.get('before'), c['after']['1']) and strict_equal(stop.get('after'), c['after']['1']) and
        type(own['native'].get('activeTalentGroup')) is int and own['native']['activeTalentGroup'] in (0, 1),
        'complete all-six offline closed-pause snapshot or original stopped primary differs')
    semantic = {k: v for k, v in computed.items() if k not in ('shutdown_checks', 'both_owned_clients_stopped',
        'actual_packet_journals_verified', 'actual_journal_counts', 'runtime_code_commit', 'proof_code_commit')}
    require(strict_equal(c.get('proof'), semantic), 'closed UI171 semantic proof has nonexact typed values')
    require(r.get('schema') == 'client442_item_actionbar_remote_review_v1' and
        r.get('actual_remote_verified') is True and r.get('complete_json_png_verified') is True and
        r.get('qualification_added') is False and r.get('local_archive_created') is False and
        finite(r.get('reviewed_at')) and r['reviewed_at'] >= c['finished_at'] and
        type(r.get('json_members')) is int and r['json_members'] == len(data) and
        type(r.get('png_members')) is int and r['png_members'] == len(digests) - len(data) and
        strict_equal(r.get('proof'), computed), 'actual complete UI171 remote review or whole portable proof differs')
    return deepcopy({'closure': c, 'snapshot': c['after'], 'predecessor': refs,
        'primary_stop_source': refs['primary_stop'], 'dvc_pointer': values['dvc_pointer'],
        'pointer_raw_hex': values['pointer_raw_hex'], 'runtime': c['runtime'], 'origin_actor': c['actor'],
        'remote_proof': computed, 'values': values, 'graph': graph, 'journal_manifest': graph['journal_manifest'],
        'archive': {'file': cp['file'], 'sha256': cp['sha256'], 'bytes': cp['bytes'], 'manifest': cp['file_manifest']}})


class _ObjectDigest:
    """Verify the DVC MD5 object key as the existing reader hashes compressed SHA."""
    def __init__(self, stream):
        self.stream, self.digest = stream, hashlib.md5()

    def read(self, size=-1):
        raw = self.stream.read(size)
        self.digest.update(raw)
        return raw


def source_bundle(closure, remote, checkpoint, *, root=None, repo=None):
    """Stream the actual supplied reviewed UI171 archive without storing it."""
    from . import item_actionbar_evidence as evidence
    from .review_hunter_learn_checkpoint import remote_options, remote_request
    root, repo = Path(root or lab.ROOT), Path(repo or lab.REPO)
    c = closed(closure, root=root)
    r, cp = (private_json(path, False, root=root) for path in (remote, checkpoint))
    require(root == lab.ROOT and c.get('phase') == evidence.PHASE and
        r.get('schema') == 'client442_item_actionbar_remote_review_v1' and
        r.get('actual_remote_verified') is True and r.get('complete_json_png_verified') is True and
        r.get('qualification_added') is False and r.get('local_archive_created') is False and
        finite(r.get('reviewed_at')) and r['reviewed_at'] >= c['finished_at'],
        'actual successful UI171 closed pause and completed remote review are required')
    refs = {role: bound(path) for role, path in {'closure': closure, 'remote': remote, 'checkpoint': checkpoint}.items()}
    reference(c.get('primary_stop_source'))
    refs['primary_stop'] = c['primary_stop_source']
    require(Path(checkpoint) == Path(closure).parent.parent / 'checkpoint_receipt.json' and
        c.get('predecessor', {}).get('primary_stop') == refs['primary_stop'],
        'actual batch checkpoint or inherited original primary stop source differs')
    pointer, pointer_raw_hex = dvc_pointer(cp, r, repo=repo)
    prefix = str(Path(_member(refs['closure'], root)).parent.parent) + '/'
    _manifest(cp, prefix)
    with urlopen(remote_request(remote_options(repo), pointer['oid']), timeout=60) as raw:
        hashed = _ObjectDigest(raw)
        data, digests, tracking, journals, count = _inspect_archive(hashed, cp, prefix)
        require(count == cp['bytes'] and hashed.digest.hexdigest() == pointer['oid'],
            'actual compressed UI171 DVC MD5 object identity differs')
    tracking['members'] = sorted(tracking['members'])
    graph = {'data': data, 'digests': digests, 'tracking': tracking, 'journal_manifest': journals}
    stop = evidence.Sources(data, digests).get(refs['primary_stop'])
    values = {'closure': c, 'remote': r, 'checkpoint': cp, 'primary_stop': stop,
        'dvc_pointer': pointer, 'pointer_raw_hex': pointer_raw_hex}
    result = validate_bundle(values, refs, graph, root=root)
    require(all(bound(path) == refs[role] for role, path in
        {'closure': closure, 'remote': remote, 'checkpoint': checkpoint}.items()) and
        bound(pointer['source']['path']) == pointer['source'], 'UI171 authority bytes changed during admission')
    return result


def cached_bundle(path, *, root=None):
    """Validate one immutable derived private cache; callers bind its source SHA."""
    root = Path(root or lab.ROOT)
    value = private_json(path, False, root=root)
    source = bound(path)
    require(set(value) == {'schema', 'values', 'refs', 'graph'} and value['schema'] == CACHE_SCHEMA,
        'exact derived UI171 bag-swap authority cache is required')
    result = validate_bundle(value['values'], value['refs'], value['graph'], root=root)
    require(bound(path) == source, 'derived UI171 authority cache changed during admission')
    return result


def _runtime_core(core):
    """Check the compact continuation fields without replaying a full graph."""
    from .item_actionbar_evidence import PHASE, SHUTDOWN_CHECKS
    require(type(core) is dict and set(core) == set(CORE_FIELDS) and
        all(type(core[key]) is dict for key in CORE_FIELDS), 'exact typed compact runtime core is required')
    c, snapshot, refs, pointer, runtime, actor = (core[key] for key in
        ('closure', 'snapshot', 'predecessor', 'dvc_pointer', 'runtime', 'origin_actor'))
    require(c.get('phase') == PHASE and c.get('completed') is True and c.get('failure') is None and
        finite(c.get('started_at')) and finite(c.get('finished_at')) and 0 < c['started_at'] < c['finished_at'] and
        c.get('controller') == 'code' and c.get('model') is None and c.get('revision') is None and
        c.get('input_sent') is False and c.get('mutation_sent') is False and c.get('qualification_added') is False,
        'compact closure must retain its successful ordinary stopped UI171 identity')
    require(type(c.get('shutdown_checks')) is dict and set(c['shutdown_checks']) == SHUTDOWN_CHECKS and
        all(value is True for value in c['shutdown_checks'].values()), 'compact closure requires all eight typed shutdown checks')
    own = owned_snapshot(snapshot)
    require(type(own['native'].get('activeTalentGroup')) is int and own['native']['activeTalentGroup'] in (0, 1),
        'compact runtime requires the exact typed active specialization')
    require(strict_equal(c.get('before'), snapshot) and strict_equal(c.get('after'), snapshot) and
        strict_equal(c.get('all_offline_snapshot'), snapshot) and strict_equal(c.get('runtime'), runtime) and
        strict_equal(c.get('actor'), actor), 'compact closure snapshot, runtime or actor differs from its source core')
    require(type(actor.get('guid')) is int and actor['guid'] == 2 and type(actor.get('account_id')) is int and
        actor['account_id'] == 2 and actor.get('actor') == 'scout' and
        actor.get('character_name', actor.get('name')) == 'Harnesstwo', 'compact runtime must belong to the original scout')
    require(set(refs) == ROLES, 'compact runtime requires all exact predecessor reference roles')
    for ref in refs.values():
        _member(ref, lab.ROOT)
    reference(core['primary_stop_source'])
    require(type(c.get('predecessor')) is dict and
        core['primary_stop_source'] == refs['primary_stop'] == c.get('primary_stop_source') ==
        c.get('predecessor', {}).get('primary_stop') and Path(refs['closure']['path']).name == 'episode.json' and
        Path(refs['checkpoint']['path']) == Path(refs['closure']['path']).parent.parent / 'checkpoint_receipt.json',
        'compact original primary stop or batch checkpoint source differs')
    require(set(pointer) == {'source', 'pointer', 'oid', 'bytes'} and pointer.get('pointer') == POINTER and
        type(pointer.get('oid')) is str and re.fullmatch(HEX32, pointer['oid']) and
        type(pointer.get('bytes')) is int and pointer['bytes'] > 0, 'compact actual UI171 DVC pointer identity differs')
    reference(pointer.get('source'))
    require(Path(pointer['source']['path']).as_posix().endswith('/' + POINTER), 'compact DVC pointer source path differs')
    require({'worldserver', 'modern_world', 'client'} <= set(runtime), 'compact runtime requires all three owned lifetimes')
    for lifetime in [*(runtime[key] for key in ('worldserver', 'modern_world', 'client')), c.get('game_before')]:
        require(type(lifetime) is dict and type(lifetime.get('pid')) is int and lifetime['pid'] > 0 and
            type(lifetime.get('start_ticks')) is str and re.fullmatch('[1-9][0-9]*', lifetime['start_ticks']),
            'compact runtime must retain every canonical stopped process lifetime')


def _runtime_value(value, full_ref):
    require(type(value) is dict and set(value) == {'schema', 'authority_source', 'core'} and
        value['schema'] == RUNTIME_SCHEMA, 'exact compact runtime authority schema is required')
    _member(full_ref, lab.ROOT)
    require(value['authority_source'] == full_ref, 'compact runtime authority must bind the exact admitted full-cache source')
    reference(value['authority_source'])
    _runtime_core(value['core'])
    try:
        size = len(json.dumps(value, separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()) + 1
    except (TypeError, ValueError, UnicodeError) as error:
        raise RuntimeError('compact runtime authority must contain finite portable JSON values') from error
    require(size <= MAX_RUNTIME_BYTES, 'compact runtime authority exceeds its one-MiB bound')


def compact_authority(old, full_ref):
    """Derive an exact small core from an already strictly admitted full bundle."""
    require(type(old) is dict and set(CORE_FIELDS) <= set(old) and type(old.get('values')) is dict and
        type(old.get('graph')) is dict and type(old.get('remote_proof')) is dict,
        'compact runtime authority requires an already admitted strict source bundle')
    value = {'schema': RUNTIME_SCHEMA, 'authority_source': full_ref, 'core': {key: old[key] for key in CORE_FIELDS}}
    _runtime_value(value, full_ref)
    require(strict_equal(old['closure'], old['values'].get('closure')) and
        strict_equal(old['values'].get('remote', {}).get('proof'), old['remote_proof']) and
        strict_equal(old['dvc_pointer'], old['values'].get('dvc_pointer')),
        'compact runtime core differs from its admitted strict source values')
    return deepcopy(value)


def cached_runtime(path, full_ref):
    """Parse only <=1 MiB compact JSON and stream-check the admitted full-cache SHA."""
    _member(full_ref, lab.ROOT)
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(lab.ROOT / 'evidence') and
        path.suffix == '.json' and path != Path(full_ref.get('path', '')) and path.is_file() and
        not any(p.is_symlink() for p in (path, *path.parents)) and path.stat().st_size <= MAX_RUNTIME_BYTES,
        'compact runtime authority must be a distinct bounded private ordinary JSON file')
    with path.open('rb') as handle:
        raw = handle.read(MAX_RUNTIME_BYTES + 1)
    require(len(raw) <= MAX_RUNTIME_BYTES, 'compact runtime authority exceeds its one-MiB bound')
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError) as error:
        raise RuntimeError('compact runtime authority is not valid JSON') from error
    _runtime_value(value, full_ref)
    require(bound(full_ref['path']) == full_ref, 'admitted full-cache source SHA differs from compact runtime authority')
    require(bound(path)['sha256'] == hashlib.sha256(raw).hexdigest(), 'compact runtime authority bytes changed during admission')
    return deepcopy(value['core'])


def prepared(value):
    require(type(value) is dict and value.get('phase') == 'bags_swap_scout_ready' and
        value.get('completed') is True and value.get('failure') is None and value.get('actor', {}).get('guid') == 2 and
        finite(value.get('started_at')) and finite(value.get('finished_at')) and value['started_at'] < value['finished_at'],
        'closed original-scout bag-swap ready preparation is required')
    own = owned_snapshot(value.get('all_offline_snapshot'))
    require(type(own['native'].get('activeTalentGroup')) is int and own['native']['activeTalentGroup'] in (0, 1) and
        type(value.get('predecessor')) is dict and set(value['predecessor']) == ROLES,
        'bag-swap ready active spec or predecessor roles differ')
    for ref in value['predecessor'].values():
        reference(ref)
    reference(value.get('authority_source'))
    return deepcopy(value)
