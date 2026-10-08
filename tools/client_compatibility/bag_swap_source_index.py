"""Byte-bound flat source views for the excluded UI173 stopped entry.

Legacy caches remain opaque history. Ancestor proofs consume original raw
receipts, images and complete journals in independent logical keyspaces.
"""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import tarfile
import tempfile

from . import bag_swap_sources as original
from . import bag_swap_fresh_sources as fresh
from . import bag_swap_failed_evidence as failed
from . import item_actionbar_evidence as item
from .item_actionbar_contract import require, finite, strict_equal
from .review_bag_swap_failed_checkpoint import (GzipReader, _name, _json,
    _journal, manifest, MAX_JSON)

ROOT = fresh.ROOT
SCHEMA = 'client442_bag_swap_source_index_v1'
CHUNK = 256 * 1024
MAX_INDEX = 16 * 1024 * 1024
MAX_CACHE = original.MAX_RUNTIME_BYTES * 512
_OPAQUE_SOURCES = {
    'ui172_authority': {'source': {'path': str(ROOT / 'evidence/client_interactions_20261008_ui173/scout_resume01/authority.json'),
        'sha256': 'baca07049635f31a380c798c104063a5f6b9b60ee1db9a48f892c4f753ed1706'},
        'bytes': 494298735, 'core_sha256': 'b99834743d5d21cb0b9594cdcb0ed3bcd31d9b327f679539eeec1b7041917d2e'},
    'ui171_authority': {'source': {'path': str(ROOT / 'evidence/client_interactions_20261008_ui172/scout_resume01/authority.json'),
        'sha256': 'fca93a6ce19abd9b048aaa8d9c7712a9aeab5db778887c400b9d297edfc86d14'},
        'bytes': 182522777, 'core_sha256': None}}


def _opaque_kind(sha, size):
    matches = [kind for kind, row in _OPAQUE_SOURCES.items() if row['source']['sha256'] == sha and row['bytes'] == size]
    require(len(matches) <= 1, 'opaque cache categories must be unambiguous')
    return matches[0] if matches else None


def _ordinary_kind(member):
    return {'.json': 'json', '.png': 'png', '.jsonl': 'journal'}.get(Path(member).suffix, 'binary')


def _file(path):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'ordinary immutable raw source required')
    return path


def _header(raw, kind):
    expected = _OPAQUE_SOURCES[kind]['core_sha256']
    if expected is not None:
        match = re.match(rb'^\{"core_sha256":"([0-9a-f]{64})","graph":', raw)
        require(match is not None and match[1].decode() == expected, 'actual admitted canonical opaque core header differs')
    return expected


def _retained_index_bound(value, size):
    if type(value) is dict and value.get('schema') == SCHEMA:
        require(type(size) is int and 0 < size <= MAX_INDEX,
            'retained raw source index exceeds its unchanged byte bound')


def _source_json(raw):
    value = _json(raw)
    # The bound belongs to the retained source bytes, including whitespace.
    # A small canonical serialization cannot replace that original identity.
    _retained_index_bound(value, len(raw))
    return value


def validate_index(value, *, root=None):
    root = Path(root or ROOT)
    require(type(value) is dict and set(value) == {'schema', 'blobs', 'scopes', 'aliases'} and
        value['schema'] == SCHEMA and all(type(value[k]) is list for k in ('blobs', 'scopes', 'aliases')) and
        0 < len(value['blobs']) <= 100000, 'bounded distinct flat source index required')
    total = 1  # The canonical writer retains its final newline.
    try:
        for chunk in json.JSONEncoder(sort_keys=True, separators=(',', ':'), allow_nan=False).iterencode(value):
            total += len(chunk.encode())
            require(total <= MAX_INDEX, 'in-memory source index exceeds its unchanged byte bound')
    except (TypeError, ValueError, RecursionError) as error:
        raise RuntimeError('bounded JSON source index required') from error
    blobs, hashes = {}, set()
    for row in value['blobs']:
        require(type(row) is dict and set(row) == {'sha256', 'bytes', 'member', 'source_member', 'kind'} and
            type(row['sha256']) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']) and
            type(row['bytes']) is int and row['bytes'] >= 0 and row['kind'] in
                ('json', 'png', 'journal', 'binary', 'ui171_authority', 'ui172_authority') and
            type(row['member']) is str, 'typed content-bound flat blob required')
        _name(row['member'])
        _name(row['source_member'])
        require(row['member'] not in blobs and row['sha256'] not in hashes, 'one physical blob per SHA required')
        if row['kind'].endswith('_authority'):
            require(_opaque_kind(row['sha256'], row['bytes']) == row['kind'], 'only exact admitted caches may be opaque')
        else:
            require(row['kind'] == _ordinary_kind(row['source_member']),
                'ordinary source class must follow its actual original member, including JSON bounds')
        blobs[row['member']] = row
        hashes.add(row['sha256'])
    ids = []
    for row in value['scopes']:
        require(type(row) is dict and set(row) == {'id', 'parent'} and type(row['id']) is str and
            row['id'] in ('ui171', 'ui172', 'ui173') and (row['parent'] is None or row['parent'] in ids),
            'ordered nonrecursive logical source scopes required')
        ids.append(row['id'])
    require(strict_equal(value['scopes'], [{'id': 'ui171', 'parent': None}, {'id': 'ui172', 'parent': 'ui171'},
        {'id': 'ui173', 'parent': 'ui172'}]), 'three separate exact source scopes required')
    seen = set()
    for row in value['aliases']:
        require(type(row) is dict and set(row) == {'scope', 'original_path', 'original_member', 'sha256', 'bytes', 'blob'} and
            row['scope'] in ids and row['blob'] in blobs and
            row['sha256'] == blobs[row['blob']]['sha256'] and type(row['bytes']) is int and
            row['bytes'] == blobs[row['blob']]['bytes'], 'exact logical alias must bind one actual raw blob')
        _name(row['original_member'])
        kind = blobs[row['blob']]['kind']
        require(kind.endswith('_authority') or row['original_member'].endswith('.blob') or
            kind == _ordinary_kind(row['original_member']), 'logical original member cannot evade its ordinary source class')
        require(type(row['original_path']) is str and row['original_path'] == str(root / row['original_member']) and
            Path(row['original_path']).is_absolute() and '..' not in Path(row['original_path']).parts and
            (row['scope'], row['original_member']) not in seen, 'unique canonical scope provenance required')
        seen.add((row['scope'], row['original_member']))
    return blobs


class Sources:
    def __init__(self, data, digests, raw_journals=None, *, paths=None, root=None, index=None):
        require(type(data) is dict and type(digests) is dict, 'byte-verified raw source maps required')
        self.data, self.digests, self.raw_journals = data, digests, raw_journals or {}
        self.paths, self.root, self.local = paths or {}, Path(root or ROOT), False
        candidates = [v for v in data.values() if type(v) is dict and v.get('schema') == SCHEMA]
        require(index is not None or len(candidates) <= 1, 'one current flat source index required')
        index = index if index is not None else (candidates[0] if candidates else None)
        self.index = index
        self.aliases, self.index_aliases = [], []
        self.maps = [v for v in data.values() if type(v) is dict and v.get('schema') in
            ('client442_bag_swap_ancestry_v1', fresh.ANCESTRY_SCHEMA)]
        for value in self.maps:
            for row in [*value.get('members', []), *value.get('authorities', [])]:
                if type(row) is dict and {'original_path', 'sha256', 'copy_member'} <= set(row):
                    self.aliases.append((row['original_path'], row['sha256'], row['copy_member']))
        for value in data.values():
            if type(value) is dict and value.get('schema') == item.ANCESTRY_SCHEMA:
                for row in value.get('sources', []):
                    self.aliases.append((row['original_path'], row['sha256'], str(Path(row['copy_path']).relative_to(self.root))))
        if index is not None:
            blobs = validate_index(index, root=self.root)
            require(all(digests.get(member) == row['sha256'] for member, row in blobs.items()),
                'every indexed physical payload must exist with its actual raw source digest')
            self.index_aliases = [(r['original_path'], r['sha256'], r['blob']) for r in index['aliases']]

    def member(self, ref, seen=None):
        original.reference(ref)
        path = Path(ref['path'])
        require(path.is_relative_to(self.root / 'evidence') and str(path) == ref['path'], 'original source must remain private evidence')
        member = str(path.relative_to(self.root))
        if self.digests.get(member) == ref['sha256']:
            return member
        seen = set() if seen is None else seen
        identity = (ref['path'], ref['sha256'])
        require(identity not in seen and len(seen) < 8, 'source alias cycle or exact ancestry bound exceeded')
        seen.add(identity)
        candidates = {copy for path, sha, copy in self.index_aliases if path == ref['path'] and sha == ref['sha256']}
        if not candidates:
            candidates = {copy for path, sha, copy in self.aliases if path == ref['path'] and sha == ref['sha256']}
        require(candidates, 'original source alias absent')
        resolved = set()
        for copy in candidates:
            _name(copy)
            # Flat blobs can lie outside evidence/, unlike immutable originals.
            resolved.add(copy if self.digests.get(copy) == ref['sha256'] else
                self.member({'path': str(self.root / copy), 'sha256': ref['sha256']}, set(seen)))
        require(len(resolved) == 1, 'original source alias resolves to ambiguous actual bytes')
        return resolved.pop()

    def get(self, ref, successful=True):
        member = self.member(ref)
        require(member in self.data and type(self.data[member]) is dict,
            'ordinary source JSON absent; opaque caches cannot be loaded as parsed documents')
        value = self.data[member]
        if successful:
            require(value.get('completed') is True and value.get('failure') is None, 'successful immutable source required')
        return value

    def journal(self, ref):
        member = self.member(ref)
        rows = self.raw_journals.get(member)
        require(type(rows) is list and all(type(r) is dict and finite(r.get('time')) for r in rows),
            'complete byte-bound journal with finite typed timestamps required')
        return rows

    def source_ref(self, value):
        members = [m for m, v in self.data.items() if v is value]
        require(len(members) == 1, 'one exact logical source-owned object required')
        return {'path': str(self.root / members[0]), 'sha256': self.digests[members[0]]}

    def scope(self, rows, *, manifest_rows=None):
        data, digests, journals, paths = {}, {}, {}, {}
        for row in rows:
            require(type(row) is dict and type(row.get('original_member')) is str and
                type(row.get('sha256')) is str and type(row.get('bytes')) is int, 'typed scoped raw binding required')
            member = _name(row['original_member'])
            require(member not in digests, 'one raw source per logical scope key required')
            physical = row.get('copy_member', row.get('blob'))
            if physical not in self.digests or self.digests[physical] != row['sha256']:
                physical = self.member({'path': str(self.root / physical), 'sha256': row['sha256']})
            require(self.digests.get(physical) == row['sha256'], 'scoped raw source digest differs')
            if manifest_rows is not None:
                expected = manifest_rows.get(member)
                require(type(expected) is dict and row['sha256'] == expected['sha256'] and row['bytes'] == expected['bytes'],
                    'scoped raw source differs from actual parent checkpoint manifest')
            digests[member] = row['sha256']
            if physical in self.data:
                value = self.data[physical]
                data[member] = dict(value) if type(value) is dict else deepcopy(value)
            if physical in self.raw_journals: journals[member] = self.raw_journals[physical]
            if physical in self.paths: paths[member] = self.paths[physical]
        return Sources(data, digests, journals, paths=paths, root=self.root)


def source_ref(store, value):
    return store.source_ref(value)


def preload_ancestor_sources(store, ready):
    """Load the actual missing old compact before a read-only ancestor preflight.

    Return the exact external refs the writer must subsequently carry. Already
    indexed copies need no additional file and are resolved normally.
    """
    c = store.get(ready['predecessor']['closure'], False)
    previous = store.get(c['original_preparation_source'], False)
    ref = previous['runtime_authority_source']
    original.reference(ref)
    try:
        store.get(ref, False)
        return ()
    except RuntimeError:
        path = _file(ref['path'])
        require(path.is_relative_to(store.root / 'evidence') and path.suffix == '.json' and
            path.stat().st_size <= original.MAX_RUNTIME_BYTES and original.bound(path) == ref,
            'actual missing ancestor compact must retain its whole raw source digest')
        with path.open('rb') as handle: value = _json(handle.read(original.MAX_RUNTIME_BYTES + 1))
        require(type(value) is dict and value.get('schema') == original.RUNTIME_SCHEMA and original.bound(path) == ref,
            'actual missing old compact JSON changed or has the wrong source role')
        member = str(path.relative_to(store.root))
        store.data[member], store.digests[member], store.paths[member] = value, ref['sha256'], str(path)
        return (ref,)


def verify_opaque(store, ref, kind):
    expected = _OPAQUE_SOURCES[kind]
    require(ref == expected['source'], 'exact admitted opaque source reference required')
    member = store.member(ref)
    path = _file(store.paths.get(member, ''))
    require(0 < path.stat().st_size == expected['bytes'] <= MAX_CACHE and original.bound(path)['sha256'] == ref['sha256'],
        'complete opaque cache SHA or bytes differ')
    with path.open('rb') as handle: header = handle.read(1024)
    return {'source': ref, 'bytes': expected['bytes'], 'core_sha256': _header(header, kind)}


class _Cursor:
    """Select real cache fields while skipping the graph, without JSON loading it."""
    def __init__(self, handle):
        self.handle, self.buffer, self.pos = handle, b'', 0

    def get(self):
        if self.pos == len(self.buffer):
            self.buffer, self.pos = self.handle.read(CHUNK), 0
        require(bool(self.buffer), 'complete opaque JSON field boundary required')
        value = self.buffer[self.pos]
        self.pos += 1
        return value

    def nonspace(self):
        value = self.get()
        while value in b' \t\r\n': value = self.get()
        return value

    def value(self, first, capture):
        if not capture:
            return self.skip_value(first)
        out, stack, string, escape = bytearray(), [], first == 34, False
        if first in (123, 91): stack.append(125 if first == 123 else 93)
        if capture: out.append(first)
        if not stack and not string:
            # Selected scalar fields are strings; opaque graph/values are objects.
            raise RuntimeError('opaque selected field must be object, array or string')
        while stack or string:
            char = self.get()
            if capture:
                out.append(char)
                require(len(out) <= MAX_JSON, 'bounded extracted opaque field exceeded')
            if string:
                if escape: escape = False
                elif char == 92: escape = True
                elif char == 34: string = False
            elif char == 34: string = True
            elif char in (123, 91): stack.append(125 if char == 123 else 93)
            elif char in (125, 93):
                require(stack and stack.pop() == char, 'opaque JSON container boundary differs')
        return bytes(out)

    def skip_value(self, first):
        stack, string = [], first == 34
        if first in (123, 91): stack.append(125 if first == 123 else 93)
        require(stack or string, 'opaque skipped field must be object, array or string')
        structural, quoted = re.compile(rb'["{}\[\]]'), re.compile(rb'["\\]')
        while stack or string:
            if self.pos == len(self.buffer):
                char = self.get()
            else:
                match = (quoted if string else structural).search(self.buffer, self.pos)
                if match is None:
                    self.pos = len(self.buffer)
                    continue
                char, self.pos = self.buffer[match.start()], match.end()
            if string:
                if char == 92: self.get()
                elif char == 34: string = False
            elif char == 34: string = True
            elif char in (123, 91): stack.append(125 if char == 123 else 93)
            elif char in (125, 93):
                require(stack and stack.pop() == char, 'opaque JSON container boundary differs')
        return b''

    def fields(self, names, nested=None):
        require(self.nonspace() == 123, 'opaque cache object required')
        found, seen = {}, set()
        first = self.nonspace()
        while first != 125:
            require(first == 34, 'opaque cache field name required')
            key = _json(self.value(first, True))
            require(type(key) is str and key not in seen, 'unique opaque cache field required')
            seen.add(key)
            require(self.nonspace() == 58, 'opaque cache field colon required')
            if nested is not None and key == nested[0]:
                found[key] = self.fields(nested[1])
            else:
                raw = self.value(self.nonspace(), key in names)
                if key in names: found[key] = _json(raw)
            first = self.nonspace()
            if first == 125: break
            require(first == 44, 'opaque cache field delimiter required')
            first = self.nonspace()
        return found


def legacy_fields(store, ref):
    verify_opaque(store, ref, 'ui171_authority')
    path = _file(store.paths[store.member(ref)])
    with path.open('rb') as handle:
        result = _Cursor(handle).fields({'schema', 'values', 'refs'}, ('graph', {'journal_manifest'}))
    require(set(result) == {'schema', 'values', 'refs', 'graph'} and result['schema'] == original.CACHE_SCHEMA and
        type(result['graph']) is dict and set(result['graph']) == {'journal_manifest'}, 'actual selected legacy cache fields required')
    require(original.bound(path)['sha256'] == ref['sha256'], 'legacy cache changed during field extraction')
    return result


def _only(data, schema):
    values = [v for v in data.values() if type(v) is dict and v.get('schema') == schema]
    require(len(values) == 1, 'one exact scoped source required: ' + schema)
    return values[0]


def _ui171(store, ready172):
    extracted = legacy_fields(store, ready172['authority_source'])
    values, refs = extracted['values'], extracted['refs']
    require(type(values) is dict and set(values) == original.VALUE_ROLES and type(refs) is dict and set(refs) == original.ROLES,
        'actual legacy values and source roles required')
    mapping = _only(store.data, 'client442_bag_swap_ancestry_v1')
    require(mapping.get('authority_source') == ready172['authority_source'], 'actual UI171 carry and legacy cache differ')
    cp, remote = values['checkpoint'], values['remote']
    item.accepted(values['closure'], item.PHASE)
    item.accepted(values['primary_stop'], 'user_requested_primary_client_stopped')
    require(Path(refs['closure']['path']).name == 'episode.json' and
        Path(refs['checkpoint']['path']) == Path(refs['closure']['path']).parent.parent / 'checkpoint_receipt.json' and
        values['closure'].get('primary_stop_source') == refs['primary_stop'] and
        values['closure'].get('predecessor', {}).get('primary_stop') == refs['primary_stop'],
        'exact original UI171 batch and inherited primary stop required')
    original._pointer_bytes(values['dvc_pointer'], values['pointer_raw_hex'], cp, remote)
    prefix = str(Path(original._member(refs['closure'], store.root)).parent.parent) + '/'
    selected = original._manifest(cp, prefix)
    require(strict_equal(mapping.get('archive'), {'file': cp['file'], 'bytes': cp['bytes'], 'sha256': cp['sha256'],
        'manifest': cp['file_manifest']}) and mapping.get('actual_remote_verified') is True and
        mapping.get('local_archive_created') is False and mapping.get('compressed_md5') == values['dvc_pointer']['oid'],
        'actual UI171 raw carry and compressed source identity differ')
    view = store.scope(mapping['members'], manifest_rows=selected)
    for row in mapping['authorities']:
        ref = {'path': row['original_path'], 'sha256': row['sha256']}
        require(ref == refs[row['role']] and strict_equal(store.get(ref, False), values[row['role']]),
            'raw UI171 authority differs from actual opaque values')
    for role in ('closure', 'primary_stop'):
        require(strict_equal(item.Sources(view.data, view.digests).get(refs[role]), values[role]),
            'actual legacy closure/primary-stop bytes differ')
    journal_manifest = extracted['graph']['journal_manifest']
    original._journal_manifest(journal_manifest, cp)
    require(type(mapping.get('journals')) is list and len(mapping['journals']) == 2, 'two full original UI171 journals required')
    tracking = item.tracking_state()
    tracking.update(digests=view.digests, manifest=selected)
    seen = set()
    for row in mapping['journals']:
        member, physical = row['original_member'], row['copy_member']
        require(member in item.TRACKING_MEMBERS and member not in seen and
            {k: row[k] for k in ('sha256', 'bytes')} == journal_manifest[member], 'first-stream full UI171 journal binding differs')
        seen.add(member)
        ref = {'path': str(store.root / physical), 'sha256': row['sha256']}
        rows = store.journal(ref)
        path = store.paths.get(store.member(ref))
        require(path is not None and _file(path).stat().st_size == row['bytes'], 'complete original journal byte count differs')
        item.collect(member, rows, view.data, tracking)
    require(seen == set(item.TRACKING_MEMBERS), 'both original full UI171 journals required')
    computed = item.proof(view.data, view.digests, tracking)
    require(strict_equal(computed, remote.get('proof')) and remote.get('schema') == 'client442_item_actionbar_remote_review_v1' and
        remote.get('actual_remote_verified') is True and remote.get('complete_json_png_verified') is True and
        remote.get('qualification_added') is False and remote.get('local_archive_created') is False and
        finite(remote.get('reviewed_at')) and remote['reviewed_at'] >= values['closure']['finished_at'] and
        type(remote.get('json_members')) is int and remote['json_members'] == sum(m.endswith('.json') for m in selected) and
        type(remote.get('png_members')) is int and remote['png_members'] == sum(m.endswith('.png') for m in selected),
        'independent raw UI171 proof differs from actual complete remote review')
    c = values['closure']
    semantic = {k: v for k, v in computed.items() if k not in ('shutdown_checks', 'both_owned_clients_stopped',
        'actual_packet_journals_verified', 'actual_journal_counts', 'runtime_code_commit', 'proof_code_commit')}
    require(strict_equal(c.get('proof'), semantic), 'actual UI171 closed semantic proof differs')
    core = {'closure': c, 'snapshot': c['after'], 'predecessor': refs, 'primary_stop_source': refs['primary_stop'],
        'dvc_pointer': values['dvc_pointer'], 'runtime': c['runtime'], 'origin_actor': c['actor']}
    original._runtime_core(core)
    stop = values['primary_stop']
    require(strict_equal(c.get('before'), c['after']) and strict_equal(c.get('all_offline_snapshot'), c['after']) and
        strict_equal(stop.get('before'), c['after']['1']) and strict_equal(stop.get('after'), c['after']['1']),
        'actual all-six UI171 snapshot and original stopped primary differ')
    compact = store.get(ready172['runtime_authority_source'], False)
    expected = {'schema': original.RUNTIME_SCHEMA, 'authority_source': ready172['authority_source'], 'core': core}
    require(strict_equal(compact, expected), 'actual old compact authority differs from raw replay and selected cache values')
    return {**core, 'values': values, 'remote_proof': computed, 'journal_manifest': journal_manifest}


def prove_ancestors(store, ready):
    """Recompute UI171/UI172 from raw sources, never from the opaque graph."""
    opaque = verify_opaque(store, ready['authority_source'], 'ui172_authority')
    compact = store.get(ready['runtime_authority_source'], False)
    require(compact.get('schema') == fresh.RUNTIME_SCHEMA and compact.get('authority_source') == ready['authority_source'],
        'retained actual compact and opaque authority differ')
    mapping = _only(store.data, fresh.ANCESTRY_SCHEMA)
    require(mapping.get('authority_source') == ready['authority_source'] and
        mapping.get('local_archive_created') is False and mapping.get('actual_remote_verified') is True,
        'actual UI172 raw carry required')
    refs = ready['predecessor']
    require(refs.get('closure') == failed._CLOSURE_SOURCE and refs.get('remote') == fresh._ACCEPTED_REMOTE_SOURCE,
        'actual accepted excluded UI172 boundary required')
    cp, remote = (store.get(refs[role], False) for role in ('checkpoint', 'remote'))
    fresh._pointer_bytes(mapping['dvc_pointer'], mapping['pointer_raw_hex'], cp, remote)
    prefix = str(Path(original._member(refs['closure'], store.root)).parent.parent) + '/'
    selected = manifest(cp, prefix)
    require(strict_equal(mapping['archive'], {'file': cp['file'], 'bytes': cp['bytes'], 'sha256': cp['sha256'],
        'manifest': cp['file_manifest']}), 'actual UI172 compressed manifest identity differs')
    view = store.scope(mapping['members'], manifest_rows=selected)
    # The old compact is an explicit additional raw dependency, absent from the
    # previous proof-only carry. It must be supplied as actual bytes.
    c = view.get(refs['closure'], False)
    ready172 = view.get(c['original_preparation_source'], False)
    old_compact = store.get(ready172['runtime_authority_source'], False)
    key = str(Path(ready172['runtime_authority_source']['path']).relative_to(store.root))
    view.data[key], view.digests[key] = dict(old_compact), ready172['runtime_authority_source']['sha256']
    ui171 = _ui171(view, ready172)
    excluded = failed.sources.validate_failed_pause(view, c)
    receipt = _only(view.data, failed.JOURNAL_SCHEMA)
    tracking = failed.tracking_state()
    tracking.update(manifest=selected, digests=view.digests, batch_prefix=prefix,
        raw_journals=view.raw_journals, archived_metadata=view.data.get('tracking/checkpoint.json'))
    require(strict_equal(tracking['archived_metadata'].get('files'),
        [r for r in cp['file_manifest'] if not r['path'].startswith('tracking/')]), 'actual UI172 metadata manifest partition differs')
    for member in failed.TRACKING_MEMBERS:
        rows = view.raw_journals.get(member)
        require(type(rows) is list and view.digests.get(member) == selected[member]['sha256'], 'complete UI172 generic journal absent')
        failed.collect(member, rows, view.data, tracking)
        tracking['journal_counts'][member] = {'rows': len(rows), 'bytes': selected[member]['bytes'], 'sha256': selected[member]['sha256']}
    computed = {'schema': failed.PROOF_SCHEMA, **excluded,
        **failed.validate_journal_receipt(view, receipt, c, ready172), **failed._metadata(view, receipt, tracking),
        **failed._generic_journals(view, receipt, c, ready172, tracking), 'qualification_added': False,
        'closed_pause_source': view.source_ref(c), 'journal_receipt_source': view.source_ref(receipt),
        'original_ui171_raw_journals_verified': True}
    require(remote.get('checkpoint_source') == refs['checkpoint'] and strict_equal(computed, remote.get('proof')) and
        remote.get('complete_manifest_verified') is True and remote.get('complete_json_png_jsonl_verified') is True and
        remote.get('actual_remote_verified') is True and remote.get('operations_admitted') == 0,
        'independent complete raw UI172 proof differs from actual byte-bound remote review')
    core = {'closure': c, 'snapshot': c['after'], 'predecessor': refs, 'primary_stop_source': refs['primary_stop'],
        'dvc_pointer': mapping['dvc_pointer'], 'runtime': c['runtime'], 'origin_actor': c['actor']}
    fresh._runtime_core(core, store.root)
    require(strict_equal(compact.get('core'), core) and
        hashlib.sha256(fresh._encode(core)).hexdigest() == opaque['core_sha256'], 'opaque header/compact core differs from raw ancestor replay')
    return {'ui171': ui171, 'ui172': {**core, 'remote_proof': computed, 'values': {'closure': c, 'remote': remote,
        'checkpoint': cp, 'primary_stop': ui171['values']['primary_stop'], 'dvc_pointer': mapping['dvc_pointer'],
        'pointer_raw_hex': mapping['pointer_raw_hex']}}, 'opaque_authority': opaque}


def inspect_archive(raw, checkpoint, prefix, *, paths=None, index=None):
    selected = manifest(checkpoint, prefix)
    blobs = validate_index(index) if index is not None else {}
    data, digests, seen, all_members = {}, {}, set(), set()
    tracking = failed.tracking_state()
    spool = tempfile.TemporaryDirectory(prefix='client442-source-index-')
    tracking.update(paths=dict(paths or {}), opaque_sources={}, raw_journals={}, _spool=spool,
        manifest=selected, digests=digests, batch_prefix=prefix)
    reader, last_end = GzipReader(raw), 0
    try:
        with tarfile.open(fileobj=reader, mode='r|', bufsize=512) as archive:
            for member in archive:
                name = _name(member.name)
                require(name not in all_members and (member.isfile() or member.isdir()), 'archive duplicate/link/special file forbidden')
                all_members.add(name)
                last_end = member.offset_data + ((member.size + 511) // 512) * 512
                if name.endswith(('.json', '.png', '.jsonl', '.blob')) or member.isfile() and name.startswith('tracking/'):
                    require(name in selected, 'unmanifested JSON/PNG/journal/blob/tracking source forbidden')
                if name not in selected: continue
                expected = selected[name]
                require(member.isfile() and member.size == expected['bytes'], 'actual manifest file type or bytes differ')
                kind = _opaque_kind(expected['sha256'], expected['bytes'])
                descriptor = blobs.get(name)
                if name.endswith('.blob'):
                    require(descriptor is not None and all(descriptor[k] == expected[k] for k in ('sha256', 'bytes')),
                        'every flat blob requires an exact byte-bound source-index class')
                    kind = descriptor['kind'] if kind is None else kind
                with archive.extractfile(member) as handle:
                    if kind in _OPAQUE_SOURCES or name.endswith('.blob'):
                        target = Path(spool.name) / (expected['sha256'] + '.blob')
                        sha, total, header = hashlib.sha256(), 0, b''
                        output = target.open('xb') if not target.exists() else None
                        try:
                            while chunk := handle.read(CHUNK):
                                sha.update(chunk); total += len(chunk)
                                if len(header) < 1024: header += chunk[:1024-len(header)]
                                if output is not None: output.write(chunk)
                        finally:
                            if output is not None: output.close()
                        digest = sha.hexdigest()
                        tracking['paths'][name] = str(target)
                        if kind in _OPAQUE_SOURCES:
                            tracking['opaque_sources'][name] = {'kind': kind, 'sha256': digest, 'bytes': total,
                                'core_sha256': _header(header, kind)}
                        elif kind == 'json':
                            require(total <= MAX_JSON, 'ordinary JSON cannot evade its bound through a blob')
                            with target.open('rb') as source: data[name] = _source_json(source.read(MAX_JSON + 1))
                        elif kind == 'journal':
                            with target.open('rb') as source: rows, _, _ = _journal(source, total)
                            require(all(finite(r.get('time')) for r in rows), 'every raw blob journal timestamp must be finite typed')
                            tracking['raw_journals'][name] = rows
                        elif kind == 'png': require(header[:8] == b'\x89PNG\r\n\x1a\n', 'actual blob PNG signature differs')
                    elif name.endswith('.jsonl'):
                        target = Path(spool.name) / (expected['sha256'] + '.jsonl')
                        output = target.open('xb') if not target.exists() else None
                        class Tee:
                            def read(self, size):
                                chunk = handle.read(size)
                                if output is not None: output.write(chunk)
                                return chunk
                        try:
                            rows, total, digest = _journal(Tee(), member.size)
                        finally:
                            if output is not None: output.close()
                        require(all(finite(r.get('time')) for r in rows), 'every raw journal timestamp must be finite typed')
                        tracking['raw_journals'][name] = rows
                        tracking['paths'][name] = str(target)
                        if name in failed.TRACKING_MEMBERS:
                            failed.collect(name, rows, data, tracking)
                            tracking['journal_counts'][name] = {'rows': len(rows), 'bytes': total, 'sha256': digest}
                    else:
                        sha, total, parts, first = hashlib.sha256(), 0, [], b''
                        require(not name.endswith('.json') or member.size <= MAX_JSON, 'ordinary JSON declared size exceeds unchanged limit')
                        while chunk := handle.read(CHUNK):
                            sha.update(chunk); total += len(chunk); first = first or chunk[:8]
                            if name.endswith('.json'): parts.append(chunk)
                        digest = sha.hexdigest()
                        if name.endswith('.json'): data[name] = _source_json(b''.join(parts))
                        elif name.endswith('.png'): require(first == b'\x89PNG\r\n\x1a\n', 'actual PNG signature differs')
                require(total == expected['bytes'] and digest == expected['sha256'], 'every actual manifest SHA/bytes must match')
                digests[name] = digest; seen.add(name)
            require(archive.fileobj.tell() == reader.delivered, 'unread tar buffer cannot hide payload')
        while chunk := reader.read(CHUNK): require(not chunk.strip(b'\0'), 'hidden nonzero tar tail forbidden')
    except (tarfile.TarError, EOFError) as error:
        spool.cleanup()
        raise RuntimeError('malformed complete source archive') from error
    except BaseException:
        spool.cleanup()
        raise
    require(reader.complete and reader.delivered % 512 == 0 and reader.delivered >= last_end + 1024 and
        seen == set(selected) and reader.bytes == checkpoint['bytes'] and reader.digest.hexdigest() == checkpoint['sha256'],
        'complete compressed archive identity/EOF/manifest differs')
    metadata = data.get('tracking/checkpoint.json')
    require(type(metadata) is dict and metadata.get('schema') == 'client442_interaction_checkpoint_v1' and
        strict_equal(metadata.get('files'), [r for r in checkpoint['file_manifest'] if not r['path'].startswith('tracking/')]),
        'actual archived metadata manifest partition differs')
    indexes = [value for value in data.values() if type(value) is dict and value.get('schema') == SCHEMA]
    require(len(indexes) <= 1, 'one byte-bound current source index required')
    if indexes:
        for member, row in validate_index(indexes[0]).items():
            require(member in selected and all(row[key] == selected[member][key] for key in ('sha256', 'bytes')),
                'every physical source-index payload must match the actual complete archive manifest')
    tracking.update(archived_metadata=metadata, compressed_md5=reader.md5.hexdigest())
    return data, digests, tracking, reader.bytes


def local_sources(directory, *, index=None):
    directory = _file(directory) if Path(directory).is_file() else Path(directory)
    require(directory.is_dir() and directory.is_relative_to(ROOT / 'evidence') and
        str(directory.resolve()) == str(directory) and not any(p.is_symlink() for p in (directory, *directory.parents)),
        'ordinary canonical private source directory required')
    data, digests, journals, paths, parsed_json, parsed_journals = {}, {}, {}, {}, {}, {}
    blobs = validate_index(index) if index is not None else {}
    for path in sorted(directory.rglob('*')):
        if not path.is_file(): continue
        path = _file(path)
        member, ref, size = str(path.relative_to(ROOT)), original.bound(path), path.stat().st_size
        digests[member], paths[member] = ref['sha256'], str(path)
        if _opaque_kind(ref['sha256'], size): continue
        descriptor = blobs.get(member)
        json_blob = path.suffix == '.blob' and descriptor is not None and descriptor['kind'] == 'json'
        if json_blob:
            require(descriptor['sha256'] == ref['sha256'] and descriptor['bytes'] == size,
                'local JSON blob must retain its exact declared raw source identity')
        if path.suffix == '.json' or json_blob:
            require(size <= MAX_JSON, 'ordinary local JSON exceeds unchanged bound')
            if ref['sha256'] not in parsed_json:
                with path.open('rb') as handle: parsed_json[ref['sha256']] = _source_json(handle.read(MAX_JSON + 1))
                require(original.bound(path) == ref, 'ordinary local JSON changed while parsing')
            value = parsed_json[ref['sha256']]
            _retained_index_bound(value, size)
            data[member] = dict(value) if type(value) is dict else deepcopy(value)
        elif path.suffix == '.jsonl':
            if ref['sha256'] not in parsed_journals:
                with path.open('rb') as handle: rows, total, digest = _journal(handle, size)
                require(total == size and digest == ref['sha256'] and all(finite(r.get('time')) for r in rows),
                    'complete local journal changed or has malformed timestamps')
                parsed_journals[ref['sha256']] = rows
            rows = parsed_journals[ref['sha256']]
            journals[member] = rows
        elif path.suffix == '.png':
            with path.open('rb') as handle: require(handle.read(8) == b'\x89PNG\r\n\x1a\n', 'actual local PNG signature differs')
    return Sources(data, digests, journals, paths=paths, root=ROOT, index=index)


def build_source_index(directory, output, *, extra_sources=()):
    directory, output = Path(directory), Path(output)
    require(output.suffix == '.json' and output.is_relative_to(directory) and
        directory.is_relative_to(ROOT / 'evidence') and str(output.resolve()) == str(output) and
        output.parent.is_dir() and not output.exists() and not output.is_symlink() and
        not any(p.is_symlink() for p in output.parents), 'exclusive canonical private source-index output required')
    destination = output.parent / 'source_blobs'
    require(not destination.exists() or destination.is_dir() and not destination.is_symlink(),
        'additional raw source directory must be ordinary and private')
    prepared = []
    for ref in extra_sources:
        original.reference(ref)
        path = _file(ref['path'])
        require(path.is_relative_to(ROOT / 'evidence') and path.suffix == '.json' and
            path.stat().st_size <= original.MAX_RUNTIME_BYTES and original.bound(path) == ref and
            ref['sha256'] not in {v['sha256'] for v in prepared}, 'distinct actual additional ancestor compact required')
        prepared.append(ref)
    store = local_sources(directory)
    extra_aliases = []
    for ref in prepared:
        path = _file(ref['path'])
        destination.mkdir(mode=0o700, exist_ok=True)
        target = destination / (ref['sha256'] + '.json')
        require(not target.exists(), 'additional raw source copy must be exclusive')
        with path.open('rb') as source, target.open('xb') as out:
            while chunk := source.read(CHUNK): out.write(chunk)
        os.chmod(target, 0o600)
        require(original.bound(path) == ref and original.bound(target)['sha256'] == ref['sha256'],
            'additional actual raw source changed during copying')
        member = str(target.relative_to(ROOT))
        store.paths[member], store.digests[member] = str(target), ref['sha256']
        extra_aliases.append((ref, member))
    blobs, aliases = {}, []
    for member, path in sorted(store.paths.items()):
        sha, size = store.digests[member], Path(path).stat().st_size
        kind = _opaque_kind(sha, size) or _ordinary_kind(member)
        blobs.setdefault(sha, {'sha256': sha, 'bytes': size, 'member': member,
            'source_member': member, 'kind': kind})
        require(blobs[sha]['bytes'] == size and blobs[sha]['kind'] == kind, 'identical blob SHA has inconsistent size or source class')
        aliases.append({'scope': 'ui173', 'original_path': str(ROOT / member), 'original_member': member,
            'sha256': sha, 'bytes': size, 'blob': blobs[sha]['member']})
    for scope, schema in (('ui172', fresh.ANCESTRY_SCHEMA), ('ui171', 'client442_bag_swap_ancestry_v1')):
        mapping = _only(store.data, schema)
        for row in [*mapping.get('members', []), *mapping.get('authorities', []), *mapping.get('journals', [])]:
            physical = row['copy_member']
            if physical not in store.digests:
                physical = store.member({'path': str(ROOT / physical), 'sha256': row['sha256']})
            require(store.digests[physical] == row['sha256'], 'every original alias must bind actual source bytes')
            member = row.get('original_member', str(Path(row['original_path']).relative_to(ROOT))) if 'original_path' in row else row['original_member']
            aliases.append({'scope': scope, 'original_path': row.get('original_path', str(ROOT / member)),
                'original_member': member, 'sha256': row['sha256'], 'bytes': row['bytes'], 'blob': blobs[row['sha256']]['member']})
    for ref, physical in extra_aliases:
        aliases.append({'scope': 'ui172', 'original_path': ref['path'], 'original_member': str(Path(ref['path']).relative_to(ROOT)),
            'sha256': ref['sha256'], 'bytes': Path(store.paths[physical]).stat().st_size, 'blob': blobs[ref['sha256']]['member']})
    value = {'schema': SCHEMA, 'blobs': sorted(blobs.values(), key=lambda r: r['member']),
        'scopes': [{'id': 'ui171', 'parent': None}, {'id': 'ui172', 'parent': 'ui171'}, {'id': 'ui173', 'parent': 'ui172'}],
        'aliases': sorted(aliases, key=lambda r: (r['scope'], r['original_member']))}
    validate_index(value)
    raw = fresh._encode(value)
    require(len(raw) <= MAX_INDEX, 'bounded flat index exceeded')
    return fresh._write(Path(output), raw, ROOT)
