"""Complete raw UI173 carry and separately keyed successor archive views.

The original v1 index is parsed only in its reconstructed parent keyspace.
Opaque legacy JSON is streamed as the two exact retained cache identities.
"""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile

from . import bag_swap_source_index as index
from . import bag_swap_indexed_sources as provider
from . import bag_swap_failed_evidence as failed
from .bag_swap_fresh_sources import _encode, _write
from .item_actionbar_contract import require, finite, strict_equal
from .review_bag_swap_failed_checkpoint import GzipReader, _name, _journal, manifest, MAX_JSON, MAX_JOURNAL

SCHEMA = 'client442_bag_swap_indexed_ancestry_v1'
CARRY_NAME, RAW_DIRECTORY = 'predecessor_ui173.json', 'predecessor_ui173_raw'
FIELDS = frozenset(('schema', 'predecessor', 'source_index_source', 'archive', 'dvc_pointer',
    'pointer_raw_hex', 'members', 'authorities', 'actual_remote_verified', 'compressed_md5',
    'local_archive_created'))
ROW_FIELDS = frozenset(('original_path', 'original_member', 'sha256', 'bytes', 'copy_member', 'kind'))
KINDS = frozenset(('json', 'png', 'journal', 'binary', *index._OPAQUE_SOURCES))
ROLE_FIELDS = {'descriptor': 'authority_source', 'runtime': 'runtime_authority_source'}
CRASH_DESCRIPTOR_SCHEMA = 'client442_bag_swap_offline_predecessor_authority_v1'
CRASH_RUNTIME_SCHEMA = 'client442_bag_swap_offline_runtime_authority_v1'
CLOSED_DESCRIPTOR_SCHEMA = 'client442_bag_swap_closed_logout_authority_v1'
CLOSED_RUNTIME_SCHEMA = 'client442_bag_swap_closed_logout_runtime_v1'
CLOSED_CARRY_SCHEMA = 'client442_bag_swap_closed_logout_ancestry_v1'
_JSON_TOKEN = re.compile(rb'"[^"\\]*(?:\\.[^"\\]*)*"|[{}\[\],:]|[^{}\[\],:\s"]+')
_JSON_TEXT_TOKEN = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"|[{}\[\],:]|[^{}\[\],:\s"]+')


def _role_fields(raw):
    """Locate top-level identity fragments without decoding the JSON document.

    Complete JSON syntax/values still belong to the normal source decoder. This
    pass skips nested and unrelated values, including large ordinary payloads.
    """
    encoding = json.detect_encoding(raw)
    try:
        source = raw if encoding in ('utf-8', 'utf-8-sig') else raw.decode(encoding, errors='surrogatepass')
    except UnicodeError:
        return {}, raw, set(), False
    tokens = _JSON_TOKEN if type(source) is bytes else _JSON_TEXT_TOKEN
    mark = (lambda value: value.encode()) if type(source) is bytes else (lambda value: value)
    offset = 3 if encoding == 'utf-8-sig' else 0
    wanted = {'schema', 'phase', *ROLE_FIELDS.values()}
    fields, depth, state, key, start = {}, 0, 'root', None, None
    recognized, ready = set(), False

    def record(span):
        nonlocal ready
        if key not in wanted: return
        spans = fields.setdefault(key, [])
        if len(spans) < 2: spans.append(span)
        else: spans[-1] = span  # Duplicate diagnostics use bounded memory.
        if key in ('schema', 'phase') and span[1] - span[0] <= 4096:
            try: value = json.loads(source[span[0]:span[1]])
            except (UnicodeDecodeError, json.JSONDecodeError): return
            if type(value) is str:
                if key == 'schema' and value in (SCHEMA, provider.CACHE_SCHEMA,
                        provider.RUNTIME_SCHEMA, CRASH_DESCRIPTOR_SCHEMA, CRASH_RUNTIME_SCHEMA,
                        CLOSED_DESCRIPTOR_SCHEMA, CLOSED_RUNTIME_SCHEMA, CLOSED_CARRY_SCHEMA,
                        'client442_bag_swap_scout_resume_v1',
                        'client442_laya_interactions_v1'):
                    recognized.add(value)
                if key == 'phase' and value == 'bags_swap_scout_ready': ready = True

    def result(): return fields, source, recognized, ready

    for token in tokens.finditer(source, offset):
        value = source[token.start():token.start() + 1]
        if state == 'root':
            if value != mark('{'): return result()
            depth, state = 1, 'key'
            continue
        if value in (mark('{'), mark('[')):
            if depth == 1:
                if state != 'value': return result()
                start = token.start()
            depth += 1
        elif value in (mark('}'), mark(']')):
            depth -= 1
            if depth == 0: return result()
            if depth == 1:
                record((start, token.end()))
                state = 'comma'
        elif depth == 1:
            if state == 'key':
                if value != mark('"'): return result()
                # Every wanted ASCII key has a bounded escaped spelling.
                try:
                    key = json.loads(source[token.start():token.end()]) if token.end() - token.start() <= 6 * 24 + 2 else None
                except (UnicodeDecodeError, json.JSONDecodeError):
                    return result()
                state = 'colon'
            elif state == 'colon':
                if value != mark(':'): return result()
                state = 'value'
            elif state == 'value':
                record((token.start(), token.end()))
                state = 'comma'
            else:
                if value != mark(','): return result()
                state = 'key'
    return result()


def _fragment(raw, fields, name, limit, occurrence=-1):
    spans = fields.get(name)
    if not spans: return None
    start, end = spans[occurrence]
    if end - start > limit: return None
    try:
        return json.loads(raw[start:end])
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None  # The unchanged complete JSON decoder rejects bad syntax.


def _receipt_roles(fields, lexical, maximum):
    require(all(len(spans) == 1 for spans in fields.values()),
        'source-owned indexed receipt must have unambiguous role declarations')
    refs = {}
    for role, field in ROLE_FIELDS.items():
        ref = _fragment(lexical, fields, field, maximum[role])
        require(ref is not None, 'source-owned indexed receipt must bind both descriptor/runtime roles')
        provider.reference(ref)
        refs[role] = ref
    return refs


def _role_limits(paths, digests, copies, root, role_refs, sizes=None, crash_copies=None):
    """Bind all current roles and schema caps before any document is decoded."""
    limits, refs = {}, {}
    maximum = {'descriptor': provider.MAX_DESCRIPTOR_BYTES, 'runtime': provider.MAX_RUNTIME_BYTES}

    def bind(role, ref):
        member = provider._member(ref, root)
        require(member in paths and digests.get(member) == ref['sha256'],
            'indexed role must bind its exact original source path and SHA')
        require(role not in refs or refs[role] == ref,
            'explicit and source-owned indexed role references differ')
        require(all(other == role or previous != ref for other, previous in refs.items()),
            'indexed descriptor and runtime roles must remain distinct')
        refs[role] = ref
        limits[member] = min(limits.get(member, maximum[role]), maximum[role])
        require(0 < Path(paths[member]).stat().st_size <= maximum[role],
            'current descriptor/runtime raw source exceeds its exact raw byte bound before decode')

    require(role_refs is None or type(role_refs) is dict and set(role_refs) <= set(ROLE_FIELDS),
        'indexed role refs require only descriptor/runtime identities')
    for role, ref in (role_refs or {}).items(): bind(role, ref)
    schemas = {SCHEMA: provider.MAX_CARRY_BYTES, provider.CACHE_SCHEMA: provider.MAX_DESCRIPTOR_BYTES,
        provider.RUNTIME_SCHEMA: provider.MAX_RUNTIME_BYTES,
        CRASH_DESCRIPTOR_SCHEMA: provider.MAX_DESCRIPTOR_BYTES, CRASH_RUNTIME_SCHEMA: provider.MAX_RUNTIME_BYTES,
        CLOSED_DESCRIPTOR_SCHEMA: provider.MAX_DESCRIPTOR_BYTES, CLOSED_RUNTIME_SCHEMA: provider.MAX_RUNTIME_BYTES,
        CLOSED_CARRY_SCHEMA: provider.MAX_CARRY_BYTES}
    for member, path in paths.items():
        size = sizes[member] if sizes is not None else Path(path).stat().st_size
        kinds = copies[member][2] if member in copies else (
            index._opaque_kind(digests[member], size) or index._ordinary_kind(member),)
        if 'json' not in kinds: continue
        require(size <= MAX_JSON, 'ordinary JSON retains its unchanged raw byte bound')
        with _opened(path, size, MAX_JSON, digests[member]) as handle:
            raw = handle.read(size + 1)
            handle.verify()
            fields, lexical, recognized, ready = _role_fields(raw)
        applicable = [schemas[s] for s in recognized if s in schemas]
        limit = min(applicable) if applicable else None
        require(limit is None or 0 < size <= limit,
            'retained indexed JSON exceeds its exact raw byte bound before decode')
        require(limit is None or len(fields.get('schema', [])) == 1,
            'indexed schema declaration must be unambiguous before decode')
        if limit is not None: limits[member] = min(limits.get(member, limit), limit)
        owner = 'client442_bag_swap_scout_resume_v1' in recognized or (
            'client442_laya_interactions_v1' in recognized and ready)
        if member in copies:
            if member in (crash_copies or {}) and owner:
                batch = root / Path(member).parent.parent
                for ref in _receipt_roles(fields, lexical, maximum).values():
                    provider._member(ref, root)
                    require(not Path(ref['path']).is_relative_to(batch),
                        'historical crash receipt cannot bind current-batch descriptor/runtime roles')
            continue  # Parent roles keep their original keyspace.
        if owner:
            for role, ref in _receipt_roles(fields, lexical, maximum).items(): bind(role, ref)
    return limits


def _json(raw):
    require(len(raw) <= MAX_JSON, 'ordinary JSON retains its unchanged raw byte bound')
    fields, _, recognized, _ = _role_fields(raw)
    limits = {SCHEMA: provider.MAX_CARRY_BYTES, provider.CACHE_SCHEMA: provider.MAX_DESCRIPTOR_BYTES,
        provider.RUNTIME_SCHEMA: provider.MAX_RUNTIME_BYTES,
        CRASH_DESCRIPTOR_SCHEMA: provider.MAX_DESCRIPTOR_BYTES, CRASH_RUNTIME_SCHEMA: provider.MAX_RUNTIME_BYTES,
        CLOSED_DESCRIPTOR_SCHEMA: provider.MAX_DESCRIPTOR_BYTES, CLOSED_RUNTIME_SCHEMA: provider.MAX_RUNTIME_BYTES,
        CLOSED_CARRY_SCHEMA: provider.MAX_CARRY_BYTES}
    applicable = [limits[s] for s in recognized if s in limits]
    require(not applicable or 0 < len(raw) <= min(applicable),
        'retained indexed JSON exceeds its exact raw byte bound before decode')
    require(not applicable or len(fields.get('schema', [])) == 1,
        'indexed schema declaration must be unambiguous before decode')
    value = index._source_json(raw)
    schema = value.get('schema') if type(value) is dict else None
    limit = limits.get(schema) if type(schema) is str else None
    require(limit is None or 0 < len(raw) <= limit,
        'retained indexed JSON exceeds its exact raw byte bound')
    return value


def _pointer(carry):
    pointer, archive, raw_hex = (carry[k] for k in ('dvc_pointer', 'archive', 'pointer_raw_hex'))
    require(type(pointer) is dict and set(pointer) == {'source', 'pointer', 'oid', 'bytes'} and
        pointer.get('pointer') == provider.POINTER and type(pointer.get('oid')) is str and
        re.fullmatch('[0-9a-f]{32}', pointer['oid']) and type(pointer.get('bytes')) is int and
        pointer['bytes'] == archive['bytes'] and pointer['oid'] == carry['compressed_md5'],
        'carry must bind the exact stopped DVC object namespace and compressed identity')
    provider.reference(pointer['source'])
    require(Path(pointer['source']['path']).as_posix().endswith('/' + provider.POINTER) and
        type(raw_hex) is str and 0 < len(raw_hex) <= 8192 and len(raw_hex) % 2 == 0 and
        re.fullmatch('[0-9a-f]+', raw_hex), 'bounded original DVC pointer bytes required')
    raw = bytes.fromhex(raw_hex)
    require(hashlib.sha256(raw).hexdigest() == pointer['source']['sha256'], 'carry pointer raw SHA differs')
    try:
        text = raw.decode('utf-8')
    except UnicodeError as error:
        raise RuntimeError('carry pointer must be UTF-8') from error
    require(re.findall(r'^\s*-?\s*md5:\s*([0-9a-f]{32})\s*$', text, re.MULTILINE) == [pointer['oid']] and
        re.findall(r'^\s*size:\s*([0-9]+)\s*$', text, re.MULTILINE) == [str(archive['bytes'])] and
        re.findall(r'^\s*path:\s*(\S+)\s*$', text, re.MULTILINE) == [Path(archive['file']).name] and
        re.search(r'^\s*hash:\s*md5\s*$', text, re.MULTILINE), 'carry pointer object descriptor differs')


def _prefix(carry, root):
    member = provider._member(carry['predecessor']['closure'], root)
    return str(Path(member).parent.parent) + '/'


def validate_carry_manifest(carry, root=None):
    """Validate identities/classes without pretending to replay absent raw data."""
    root = provider._root(root)
    require(type(carry) is dict and set(carry) == FIELDS and carry['schema'] == SCHEMA and
        len(_encode(carry)) <= provider.MAX_CARRY_BYTES and carry['actual_remote_verified'] is True and
        carry['local_archive_created'] is False, 'bounded distinct completed raw carry manifest required')
    refs = carry['predecessor']
    require(type(refs) is dict and set(refs) == provider.ROLES, 'exact latest predecessor role set required')
    provider.admission_pins({k: refs[k] for k in ('closure', 'remote', 'checkpoint')}, root=root)
    provider._member(refs['primary_stop'], root)
    source_member = provider._member(carry['source_index_source'], root)
    archive = carry['archive']
    require(type(archive) is dict and set(archive) == {'file', 'bytes', 'sha256', 'manifest'} and
        archive['file'] == provider.POINTER.removesuffix('.dvc'), 'exact stopped parent archive required')
    selected = manifest({'bytes': archive['bytes'], 'sha256': archive['sha256'],
        'file_manifest': archive['manifest']}, _prefix(carry, root))
    closure_member = provider._member(refs['closure'], root)
    require(closure_member in selected and selected[closure_member]['sha256'] == refs['closure']['sha256'],
        'latest stopped closure must retain its original complete manifest digest')
    require(source_member in selected and selected[source_member]['sha256'] == carry['source_index_source']['sha256'] and
        0 < selected[source_member]['bytes'] <= index.MAX_INDEX,
        'unchanged original parent source index must be a full manifest member')
    require(type(carry['members']) is list and len(carry['members']) == len(selected) and
        type(carry['authorities']) is list and len(carry['authorities']) == 2,
        'complete parent manifest and exactly two external authorities required')
    seen, copies, hashes, authority_roles, batches = set(), {}, {}, set(), set()
    for external, row in [(False, r) for r in carry['members']] + [(True, r) for r in carry['authorities']]:
        require(type(row) is dict and set(row) == ROW_FIELDS | ({'role'} if external else set()) and
            type(row.get('bytes')) is int and row['bytes'] >= 0 and type(row.get('sha256')) is str and
            re.fullmatch('[0-9a-f]{64}', row['sha256']) and row.get('kind') in KINDS,
            'exact typed raw carry binding required')
        member, copy = _name(row['original_member']), _name(row['copy_member'])
        require(row['original_path'] == str(root / member), 'original raw carry path differs from its logical member')
        if external:
            role = row['role']
            require(role in ('checkpoint', 'remote') and role not in authority_roles and member not in selected and
                {'path': row['original_path'], 'sha256': row['sha256']} == refs[role] and row['kind'] == 'json',
                'exact external checkpoint/remote source roles required')
            authority_roles.add(role)
        else:
            require(member in selected and member not in seen and all(row[k] == selected[member][k] for k in ('bytes', 'sha256')),
                'every actual parent manifest member must occur exactly once')
            seen.add(member)
        opaque = index._opaque_kind(row['sha256'], row['bytes'])
        require(row['kind'] == opaque if opaque is not None else
            row['kind'] == index._ordinary_kind(member) or member.endswith('.blob') and row['kind'] in KINDS - set(index._OPAQUE_SOURCES),
            'raw carry source class cannot disguise an ordinary JSON/journal or invent an opaque cache')
        if row['kind'] == 'json': require(row['bytes'] <= MAX_JSON, 'ordinary carried JSON exceeds its bound')
        if row['kind'] == 'journal': require(row['bytes'] <= MAX_JOURNAL, 'carried journal exceeds its unchanged bound')
        if opaque: require(row['bytes'] <= index.MAX_CACHE, 'opaque carried cache exceeds its unchanged bound')
        target = Path(copy)
        require(target.parent.name == RAW_DIRECTORY and target.name == row['sha256'] + '.blob' and
            target.parent.parent.as_posix().startswith('evidence/') and not target.parent.parent.as_posix().endswith('/'),
            'one canonical SHA-named physical carry copy required')
        batches.add(str(target.parent.parent))
        identity = (row['sha256'], row['bytes'])
        require(copy not in copies or copies[copy][:2] == identity, 'physical raw copy has inconsistent identity/size')
        require(row['sha256'] not in hashes or hashes[row['sha256']] == (copy, row['bytes']),
            'one physical copy and byte size per SHA required')
        kinds = copies[copy][2] if copy in copies else frozenset()
        copies[copy], hashes[row['sha256']] = (*identity, kinds | {row['kind']}), (copy, row['bytes'])
    require(seen == set(selected) and authority_roles == {'checkpoint', 'remote'} and len(batches) == 1 and
        next(iter(batches)) != _prefix(carry, root).rstrip('/'), 'complete distinct successor carry namespace required')
    _pointer(carry)
    return copies


def _stream(raw, checkpoint, prefix, destination):
    """Verify all gzip/tar/manifest bytes and retain each raw SHA once."""
    selected = manifest(checkpoint, prefix)
    reader, seen, all_members, last_end, paths = GzipReader(raw), set(), set(), 0, {}
    try:
        with tarfile.open(fileobj=reader, mode='r|', bufsize=512) as archive:
            for member in archive:
                name = _name(member.name)
                require(name not in all_members and (member.isfile() or member.isdir()),
                    'archive duplicate/link/special file forbidden')
                all_members.add(name)
                last_end = member.offset_data + ((member.size + 511) // 512) * 512
                if member.isdir():
                    require(name not in selected, 'manifest payload cannot be a directory')
                    continue
                require(name in selected and member.size == selected[name]['bytes'],
                    'every archive file must match the complete manifest type/size')
                expected, sha, total = selected[name], hashlib.sha256(), 0
                opaque = index._opaque_kind(expected['sha256'], member.size)
                require(opaque is not None or not name.endswith('.json') or member.size <= MAX_JSON,
                    'ordinary archive JSON declared bytes exceed unchanged bound')
                require(not name.endswith('.jsonl') or member.size <= MAX_JOURNAL,
                    'archive journal declared bytes exceed unchanged bound')
                require(name != prefix + CARRY_NAME or 0 < member.size <= provider.MAX_CARRY_BYTES,
                    'one fixed raw-bounded successor carry manifest required')
                target = destination / (expected['sha256'] + '.blob')
                output = target.open('xb') if not target.exists() else None
                try:
                    with archive.extractfile(member) as handle:
                        while chunk := handle.read(index.CHUNK):
                            total += len(chunk); sha.update(chunk)
                            if output is not None: output.write(chunk)
                finally:
                    if output is not None: output.close()
                require(total == expected['bytes'] and sha.hexdigest() == expected['sha256'],
                    'every actual manifest SHA/bytes must match')
                paths[name] = str(target); seen.add(name)
            require(archive.fileobj.tell() == reader.delivered, 'unread tar buffer cannot hide payload')
        while chunk := reader.read(index.CHUNK):
            require(not chunk.strip(b'\0'), 'hidden nonzero tar tail forbidden')
    except (tarfile.TarError, EOFError) as error:
        raise RuntimeError('malformed complete indexed source archive') from error
    require(reader.complete and reader.delivered % 512 == 0 and reader.delivered >= last_end + 1024 and
        seen == set(selected) and reader.bytes == checkpoint['bytes'] and reader.digest.hexdigest() == checkpoint['sha256'],
        'complete compressed archive identity/EOF/manifest differs')
    return selected, paths, reader


@contextmanager
def _opened(path, size, limit, expected_sha):
    """Bind one ordinary opened file to exactly the bytes given to its consumer."""
    path = index._file(path)
    require(type(size) is int and 0 <= size <= limit, 'retained raw source size exceeds its bound')
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_size == size, 'retained raw source size differs')
    def identity(value):
        return (value.st_dev, value.st_ino, value.st_mode, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    with path.open('rb') as raw_handle:
        def check():
            opened, current = os.fstat(raw_handle.fileno()), path.lstat()
            require(stat.S_ISREG(opened.st_mode) and identity(opened) == identity(before) and
                identity(current) == identity(before) and not any(p.is_symlink() for p in (path, *path.parents)),
                'retained source changed while decoding its actual raw bytes')
        class Reader:
            name = raw_handle.name
            def __init__(self): self.total, self.digest = 0, hashlib.sha256()
            def read(self, count=-1):
                check()
                remaining = size - self.total + 1
                chunk = raw_handle.read(remaining if count < 0 else min(count, remaining))
                self.total += len(chunk); self.digest.update(chunk)
                require(self.total <= size and self.total <= limit,
                    'retained JSON/journal actual bytes exceed their exact raw byte bound before decode')
                check()
                return chunk
            def verify(self):
                require(self.total == size, 'retained typed source actual read length differs')
                require(expected_sha is None or self.digest.hexdigest() == expected_sha,
                    'decoded raw bytes differ from the pinned source SHA')
                check()
        check()
        handle = Reader()
        yield handle
        handle.verify()


def _read(path, kind, size, raw_limit=None, expected_sha=None):
    limit = index.MAX_CACHE if kind in index._OPAQUE_SOURCES else MAX_JOURNAL if kind == 'journal' else MAX_JSON if kind == 'json' else size
    if raw_limit is not None: limit = min(limit, raw_limit)
    with _opened(path, size, limit, expected_sha) as handle:
        if kind == 'json':
            raw = handle.read(size + 1)
            handle.verify()  # Check the exact document bytes before JSON decode.
            return _json(raw)
        if kind == 'journal':
            rows, total, digest = _journal(handle, size)
            require(total == size and digest == handle.digest.hexdigest() and
                all(finite(r.get('time')) for r in rows), 'whole raw journal time/bytes differ')
            handle.verify()
            return rows
        if kind in index._OPAQUE_SOURCES:
            require(size > 0, 'opaque source exceeds unchanged cache bound')
            index._header(handle.read(1024), kind)
        elif kind == 'png':
            require(handle.read(8) == b'\x89PNG\r\n\x1a\n', 'actual PNG signature differs')
        while handle.read(index.CHUNK): pass
        return None


def _parent_classes(carry, source_index, root):
    blobs = index.validate_index(source_index, root=root)
    selected = {row['path']: row for row in carry['archive']['manifest']}
    for member, row in blobs.items():
        require(member in selected and all(row[k] == selected[member][k] for k in ('sha256', 'bytes')),
            'unchanged parent v1 index payload differs from the original full manifest')
    for row in carry['members']:
        member = row['original_member']
        if member.endswith('.blob'):
            require(member in blobs and row['kind'] == blobs[member]['kind'],
                'original blob class must come from the unchanged parent v1 index')


def _metadata(data, checkpoint):
    metadata = data.get('tracking/checkpoint.json')
    require(type(metadata) is dict and metadata.get('schema') == 'client442_interaction_checkpoint_v1' and
        strict_equal(metadata.get('files'), [r for r in checkpoint['file_manifest'] if not r['path'].startswith('tracking/')]),
        'actual archived metadata manifest partition differs')
    return metadata


def carry_archive(raw, checkpoint, prefix, batch, predecessor, source_index_source,
        dvc_pointer, pointer_raw_hex, authorities, *, root=None):
    root, batch = provider._root(root), Path(batch)
    require(batch.is_dir() and batch.is_relative_to(root / 'evidence') and str(batch.resolve()) == str(batch) and
        not any(p.is_symlink() for p in (batch, *batch.parents)) and
        not (batch / CARRY_NAME).exists() and not (batch / RAW_DIRECTORY).exists(),
        'exclusive ordinary successor raw carry destination required')
    require(type(authorities) is dict and set(authorities) == {'checkpoint', 'remote'} and
        all(authorities[k] == predecessor[k] for k in authorities), 'exact external predecessor authority pins required')
    external, values = {}, {}
    for role, ref in authorities.items():
        provider._member(ref, root)
        path = index._file(ref['path'])
        size = path.stat().st_size
        with _opened(path, size, MAX_JSON, ref['sha256']) as handle:
            raw_bytes = handle.read(size + 1)
            handle.verify()
            values[role] = _json(raw_bytes)
        external[role] = (raw_bytes, path)
    cp, remote = (values[k] for k in ('checkpoint', 'remote'))
    require(strict_equal(cp, checkpoint) and remote.get('schema') == 'client442_bag_swap_stopped_remote_review_v1' and
        remote.get('actual_remote_verified') is True and remote.get('complete_manifest_verified') is True and
        remote.get('checkpoint_source') == predecessor['checkpoint'], 'actual closed stopped remote/checkpoint required')
    provider._pointer(dvc_pointer, pointer_raw_hex, cp, remote)
    index_member = provider._member(source_index_source, root)
    declared = manifest(checkpoint, prefix)
    require(index_member in declared and declared[index_member]['sha256'] == source_index_source['sha256'] and
        0 < declared[index_member]['bytes'] <= index.MAX_INDEX, 'actual raw-bounded unchanged parent index required')
    destination = batch / RAW_DIRECTORY
    with tempfile.TemporaryDirectory(prefix='.ui173-carry-', dir=batch) as staged:
        staging = Path(staged)
        raw_directory = staging / RAW_DIRECTORY
        raw_directory.mkdir(mode=0o700)
        carry = _carry_payload(raw, checkpoint, prefix, batch, predecessor, source_index_source,
            dvc_pointer, pointer_raw_hex, authorities, external, root, raw_directory, index_member)
        staged_ref = _write(staging / CARRY_NAME, _encode(carry), root)
        published_directory, published_manifest = False, False
        try:
            destination.mkdir(mode=0o700)
            published_directory = True
            for path in raw_directory.iterdir(): os.link(path, destination / path.name)
            os.link(staged_ref['path'], batch / CARRY_NAME)
            published_manifest = True
            result = provider.bound(batch / CARRY_NAME)
            require(result['sha256'] == staged_ref['sha256'], 'published carry differs from its fully validated staging bytes')
            return result
        except BaseException:
            if published_manifest: (batch / CARRY_NAME).unlink()
            if published_directory: shutil.rmtree(destination)
            raise


def _carry_payload(raw, checkpoint, prefix, batch, predecessor, source_index_source,
        dvc_pointer, pointer_raw_hex, authorities, external, root, destination, index_member):
    selected, paths, reader = _stream(raw, checkpoint, prefix, destination)
    require(reader.md5.hexdigest() == dvc_pointer['oid'] and prefix ==
        str(Path(provider._member(predecessor['closure'], root)).parent.parent) + '/',
        'whole parent stream must match the actual stopped object and keyspace')
    require(index_member in selected and selected[index_member]['sha256'] == source_index_source['sha256'] and
        0 < selected[index_member]['bytes'] <= index.MAX_INDEX,
        'actual unchanged parent index source required')
    source_index = _read(paths[index_member], 'json', selected[index_member]['bytes'], index.MAX_INDEX, selected[index_member]['sha256'])
    blobs = index.validate_index(source_index, root=root)
    members = []
    for member, expected in selected.items():
        kind = index._opaque_kind(expected['sha256'], expected['bytes']) or index._ordinary_kind(member)
        if member.endswith('.blob'):
            require(member in blobs and all(blobs[member][k] == expected[k] for k in ('sha256', 'bytes')),
                'parent blob needs its unchanged byte-bound source class')
            kind = blobs[member]['kind']
        members.append({'original_path': str(root / member), 'original_member': member, 'sha256': expected['sha256'],
            'bytes': expected['bytes'], 'copy_member': str((batch / RAW_DIRECTORY / Path(paths[member]).name).relative_to(root)), 'kind': kind})
    authority_rows = []
    for role, ref in authorities.items():
        raw_bytes, path = external[role]
        target = destination / (ref['sha256'] + '.blob')
        if not target.exists():
            with target.open('xb') as out: out.write(raw_bytes)
        require(provider.bound(path) == ref and provider.bound(target)['sha256'] == ref['sha256'],
            'actual external raw authority changed during carry')
        authority_rows.append({'role': role, 'original_path': ref['path'], 'original_member': provider._member(ref, root),
            'sha256': ref['sha256'], 'bytes': len(raw_bytes),
            'copy_member': str((batch / RAW_DIRECTORY / target.name).relative_to(root)), 'kind': 'json'})
    carry = {'schema': SCHEMA, 'predecessor': deepcopy(predecessor), 'source_index_source': deepcopy(source_index_source),
        'archive': {'file': checkpoint['file'], 'bytes': checkpoint['bytes'], 'sha256': checkpoint['sha256'],
            'manifest': deepcopy(checkpoint['file_manifest'])}, 'dvc_pointer': deepcopy(dvc_pointer),
        'pointer_raw_hex': pointer_raw_hex, 'members': members, 'authorities': authority_rows,
        'actual_remote_verified': True, 'compressed_md5': reader.md5.hexdigest(), 'local_archive_created': False}
    validate_carry_manifest(carry, root)
    _parent_classes(carry, source_index, root)
    metadata = _read(paths['tracking/checkpoint.json'], 'json', selected['tracking/checkpoint.json']['bytes'], MAX_JSON, selected['tracking/checkpoint.json']['sha256'])
    _metadata({'tracking/checkpoint.json': metadata}, checkpoint)
    for path in destination.iterdir(): os.chmod(path, 0o600)
    return carry


class Sources:
    """Outer physical store: carry aliases only, never v1 index autodetection."""
    def __init__(self, data, digests, raw_journals, paths, root, carry, *, local=False):
        self.data, self.digests, self.raw_journals, self.paths = data, digests, raw_journals, paths
        self.root, self.local, self.carry = provider._root(root), local, carry
        validate_carry_manifest(carry, self.root)
        self.aliases = {(r['original_path'], r['sha256']): r['copy_member']
            for r in [*carry['members'], *carry['authorities']]}
        self.logical_kinds = {(r['original_path'], r['sha256']): frozenset((r['kind'],))
            for r in [*carry['members'], *carry['authorities']]}
        self.copy_kinds = {member: kinds for member, (_, _, kinds) in validate_carry_manifest(carry, self.root).items()}

    def member(self, ref):
        provider.reference(ref)
        path = Path(ref['path'])
        require(path.is_relative_to(self.root / 'evidence') and str(path) == ref['path'], 'private original source required')
        member = str(path.relative_to(self.root))
        if self.digests.get(member) == ref['sha256']: return member
        member = self.aliases.get((ref['path'], ref['sha256']))
        require(member is not None and self.digests.get(member) == ref['sha256'], 'exact indexed carry source alias absent')
        return member

    def get(self, ref, successful=True):
        member = self.member(ref)
        kinds = self.logical_kinds.get((ref['path'], ref['sha256']), self.copy_kinds.get(member))
        require(kinds is None or 'json' in kinds, 'logical source is not an ordinary JSON view')
        value = self.data.get(member)
        require(type(value) is dict, 'ordinary JSON source absent; opaque caches cannot be parsed')
        if successful: require(value.get('completed') is True and value.get('failure') is None, 'successful immutable source required')
        return value

    def journal(self, ref):
        member = self.member(ref)
        kinds = self.logical_kinds.get((ref['path'], ref['sha256']), self.copy_kinds.get(member))
        require(kinds is None or 'journal' in kinds, 'logical source is not a journal view')
        rows = self.raw_journals.get(member)
        require(type(rows) is list and all(type(r) is dict and finite(r.get('time')) for r in rows),
            'complete finite byte-bound journal required')
        return rows


def _crash_copies(paths, digests, copies, root, sizes):
    """Classify only byte-bound historical copies in the separate crash map."""
    from . import bag_swap_offline_sources as offline
    batch = Path(next(iter(copies))).parent.parent
    member = (batch / 'crash_ancestry.json').as_posix()
    retained = {name for name in paths if Path(name).parent == batch / 'crash_sources'}
    if member not in paths:
        require(not retained, 'crash source copies require their exact ancestry map')
        return {}
    value = _read(paths[member], 'json', sizes[member], offline.MAX_DESCRIPTOR_BYTES, digests[member])
    offline.validate_manifest(value, root)
    indexed_member = (batch / CARRY_NAME).as_posix()
    require(value['indexed_carry_source'] == {'path': str(root / indexed_member),
        'sha256': digests.get(indexed_member)}, 'crash map must bind this exact indexed carry')
    classified = {}
    suffixes = {'json': '.json', 'journal': '.jsonl', 'png': '.png', 'binary': '.bin'}
    for row in value['members']:
        name = row['copy_member']
        require(Path(name).parent == batch / 'crash_sources' and
            Path(name).name == row['sha256'] + suffixes[row['kind']] and
            not Path(row['original_path']).is_relative_to(root / batch),
            'crash copies must preserve a separate historical source keyspace')
        require(name in paths and digests[name] == row['sha256'] and sizes[name] == row['bytes'] and
            Path(paths[name]).stat().st_size == row['bytes'], 'every crash copy must bind its exact raw bytes')
        classified[name] = (row['sha256'], row['bytes'], frozenset((row['kind'],)))
    require(retained == set(classified), 'crash source directory must match its complete typed map')
    require(any(row['original_path'] == value['boundary_source']['path'] and
        row['sha256'] == value['boundary_source']['sha256'] and row['kind'] == 'json'
        for row in value['members']), 'closed crash boundary must retain its JSON view')
    return classified


def _materialize(paths, digests, carry, root, *, role_refs=None, sizes=None):
    copies = validate_carry_manifest(carry, root)
    require(all(member in paths and digests.get(member) == sha and Path(paths[member]).stat().st_size == size
        for member, (sha, size, _) in copies.items()), 'every raw carry copy must exist with exact source bytes')
    sizes = {member: copies[member][1] if member in copies else
        sizes[member] if sizes is not None else Path(path).stat().st_size for member, path in paths.items()}
    # Current role discovery applies to current receipts. The two independently
    # validated historical maps retain their original roles in separate keys.
    crash_copies = _crash_copies(paths, digests, copies, root, sizes)
    copies.update(crash_copies)
    limits = _role_limits(paths, digests, copies, root, role_refs, sizes, crash_copies)
    data, journals, decoded, checked = {}, {}, {}, set()
    for member, path in paths.items():
        size = sizes[member]
        if member in copies: kinds = copies[member][2]
        else:
            require(not member.endswith('.blob'), 'unclassified blob outside the exact carried source map')
            kinds = (index._opaque_kind(digests[member], size) or index._ordinary_kind(member),)
        require(member not in limits or size <= limits[member],
            'current descriptor/runtime raw source exceeds its exact raw byte bound before decode')
        for kind in sorted(kinds):
            key = (digests[member], size, kind)
            if key not in decoded:
                decoded[key] = _read(path, kind, size, limits.get(member), digests[member])
            value = decoded[key]
            if kind == 'json': data[member] = dict(value) if type(value) is dict else deepcopy(value)
            elif kind == 'journal': journals[member] = value
        if path not in checked:
            require(provider.bound(path)['sha256'] == digests[member] and Path(path).stat().st_size == size,
                'retained source changed while decoding its actual raw bytes')
            checked.add(path)
    index_value = data.get(next(r['copy_member'] for r in carry['members']
        if r['original_path'] == carry['source_index_source']['path']))
    _parent_classes(carry, index_value, root)
    return data, journals


def local_sources(batch, root=None, *, role_refs=None):
    root, batch = provider._root(root), Path(batch)
    require(batch.is_dir() and batch.is_relative_to(root / 'evidence') and str(batch.resolve()) == str(batch) and
        not any(p.is_symlink() for p in (batch, *batch.parents)), 'ordinary canonical private successor batch required')
    carry_path = index._file(batch / CARRY_NAME)
    require(carry_path.stat().st_size <= provider.MAX_CARRY_BYTES, 'raw successor carry exceeds its cap')
    with _opened(carry_path, carry_path.stat().st_size, provider.MAX_CARRY_BYTES, None) as handle:
        raw_carry = handle.read(carry_path.stat().st_size + 1)
        handle.verify()
        carry_ref = {'path': str(carry_path), 'sha256': handle.digest.hexdigest()}
        carry = _json(raw_carry)
    copies = validate_carry_manifest(carry, root)
    paths, digests, sizes = {}, {}, {}
    for path in sorted(batch.rglob('*')):
        require(not path.is_symlink(), 'local source links forbidden')
        if not path.is_file(): continue
        path = index._file(path)
        member, ref = str(path.relative_to(root)), provider.bound(path)
        require(path != carry_path or ref == carry_ref, 'local carry source differs from its exact decoded raw bytes')
        paths[member], digests[member] = str(path), ref['sha256']
        sizes[member] = path.stat().st_size
    require(all(Path(member).parent.parent == Path(str(batch.relative_to(root))) for member in copies),
        'local carry copies must remain in the owned successor batch')
    data, journals = _materialize(paths, digests, carry, root, role_refs=role_refs, sizes=sizes)
    return Sources(data, digests, journals, paths, root, carry, local=True)


def parent_view(store, carry):
    """Restore ALL original parent members/tracking before any v1 replay."""
    root = store.root
    copies = validate_carry_manifest(carry, root)
    data, digests, journals, paths = {}, {}, {}, {}
    checked = set()
    for row in [*carry['members'], *carry['authorities']]:
        member, copy = row['original_member'], row['copy_member']
        require(store.digests.get(copy) == row['sha256'] and copy in store.paths,
            'complete physical carry digest/path absent')
        path = index._file(store.paths[copy])
        if copy not in checked:
            require(path.stat().st_size == row['bytes'] and provider.bound(path)['sha256'] == row['sha256'],
                'raw carried parent changed after ingestion')
            checked.add(copy)
        digests[member], paths[member] = row['sha256'], str(path)
        if row['kind'] == 'json':
            require(copy in store.data, 'parsed ordinary parent JSON absent')
            value = store.data[copy]
            data[member] = dict(value) if type(value) is dict else deepcopy(value)
        elif row['kind'] == 'journal': journals[member] = store.journal({'path': str(root / copy), 'sha256': row['sha256']})
    cp = data[provider._member(carry['predecessor']['checkpoint'], root)]
    remote = data[provider._member(carry['predecessor']['remote'], root)]
    require(strict_equal(carry['archive'], {'file': cp['file'], 'bytes': cp['bytes'], 'sha256': cp['sha256'],
        'manifest': cp['file_manifest']}), 'carried actual external checkpoint differs from parent manifest')
    provider._pointer(carry['dvc_pointer'], carry['pointer_raw_hex'], cp, remote)
    selected = manifest(cp, _prefix(carry, root))
    source_index = data[provider._member(carry['source_index_source'], root)]
    _parent_classes(carry, source_index, root)
    # Only now are the original physical blob names and logical scopes present.
    index.Sources(data, digests, journals, paths=paths, root=root, index=source_index)
    tracking = failed.tracking_state()
    tracking.update(manifest=selected, digests=digests, paths=paths, raw_journals=journals,
        batch_prefix=_prefix(carry, root), archived_metadata=_metadata(data, cp),
        compressed_md5=carry['compressed_md5'], complete_manifest_verified=True)
    for member in failed.TRACKING_MEMBERS:
        require(member in journals, 'both original complete parent tracking journals required')
        failed.collect(member, journals[member], data, tracking)
        tracking['journal_counts'][member] = {'rows': len(journals[member]),
            'bytes': selected[member]['bytes'], 'sha256': selected[member]['sha256']}
    return data, digests, tracking


def _disk_backed_parent(parent):
    """Fail closed unless mount discovery identifies supported disk storage."""
    try:
        observed = subprocess.run(['findmnt', '--noheadings', '--raw', '--output', 'FSTYPE',
            '--target', str(parent)], check=True, capture_output=True, encoding='ascii', timeout=5)
    except (OSError, subprocess.SubprocessError, UnicodeError) as error:
        raise RuntimeError('disk-backed evidence filesystem discovery failed') from error
    require(observed.stdout.strip() in ('ext2', 'ext3', 'ext4', 'xfs', 'btrfs', 'f2fs', 'zfs', 'bcachefs'),
        'supported disk-backed evidence filesystem required for raw source staging')


def _private_spool(root, prefix):
    """Keep full raw evidence on its owned filesystem, with scoped cleanup."""
    root = provider._root(root)
    parent = root / 'evidence'
    require(parent.is_dir() and parent.resolve() == parent and
        not any(path.is_symlink() for path in (parent, *parent.parents)) and
        parent.stat().st_uid == os.getuid(),
        'private canonical existing evidence filesystem required for raw source staging')
    _disk_backed_parent(parent)
    spool = tempfile.TemporaryDirectory(prefix=prefix, dir=parent)
    try:
        path = Path(spool.name); identity = path.lstat()
        require(path.parent == parent and path.resolve() == path and stat.S_ISDIR(identity.st_mode) and
            not path.is_symlink() and identity.st_uid == os.getuid() and stat.S_IMODE(identity.st_mode) == 0o700 and
            (path.stat().st_dev, path.stat().st_ino) == (identity.st_dev, identity.st_ino),
            'raw source staging must retain its exclusive private directory identity')
    except BaseException:
        spool.cleanup()
        raise
    return spool


def inspect_archive(raw, cp, prefix, *, role_refs=None):
    """Read the whole successor archive without applying its carried v1 index."""
    root = provider._root()
    spool = _private_spool(root, '.client442-indexed-carry-')
    try:
        selected, paths, reader = _stream(raw, cp, prefix, Path(spool.name))
        from . import bag_swap_closed_logout_sources as closed
        closed_member = prefix + closed.CARRY_NAME
        if closed_member in selected:
            carry = _read(paths[closed_member], 'json', selected[closed_member]['bytes'],
                closed.MAX_CARRY_BYTES, selected[closed_member]['sha256'])
            digests = {member: row['sha256'] for member, row in selected.items()}
            store = closed.materialize(paths, digests, {m: row['bytes'] for m, row in selected.items()},
                carry, root, role_refs=role_refs)
            data, digests, journals, paths = store.data, store.digests, store.raw_journals, store.paths
        else:
            store = None
        carry_member = prefix + CARRY_NAME
        require(store is not None or carry_member in selected and 0 < selected[carry_member]['bytes'] <= provider.MAX_CARRY_BYTES,
            'one fixed raw-bounded successor carry manifest required')
        if store is None:
            carry = _read(paths[carry_member], 'json', selected[carry_member]['bytes'], provider.MAX_CARRY_BYTES, selected[carry_member]['sha256'])
            copies = validate_carry_manifest(carry, root)
            require(all(member.startswith(prefix) and member in selected and
                selected[member]['sha256'] == sha and selected[member]['bytes'] == size
                for member, (sha, size, _) in copies.items()), 'raw carry copies must belong to this complete successor archive')
            digests = {member: row['sha256'] for member, row in selected.items()}
            data, journals = _materialize(paths, digests, carry, root, role_refs=role_refs,
                sizes={member: row['bytes'] for member, row in selected.items()})
        tracking = failed.tracking_state()
        tracking.update(manifest=selected, digests=digests, paths=paths, raw_journals=journals,
            batch_prefix=prefix, archived_metadata=_metadata(data, cp), compressed_md5=reader.md5.hexdigest(),
            complete_manifest_verified=True, _spool=spool)
        for member in failed.TRACKING_MEMBERS:
            require(member in journals, 'both complete successor tracking journals required')
            failed.collect(member, journals[member], data, tracking)
            tracking['journal_counts'][member] = {'rows': len(journals[member]),
                'bytes': selected[member]['bytes'], 'sha256': selected[member]['sha256']}
        return data, digests, tracking, reader.bytes
    except BaseException:
        spool.cleanup()
        raise
