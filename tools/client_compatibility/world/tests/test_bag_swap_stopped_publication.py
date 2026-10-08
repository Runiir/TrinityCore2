"""Whole-stream integrity and publisher environment boundaries for UI173."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

from tools.client_compatibility import bag_swap_stopped_evidence as evidence
from tools.client_compatibility import checkpoint_bag_swap_stopped as publisher


def stream_fixture(extra=None):
    files = {evidence.BATCH + 'entry01/episode.json': b'{"completed":false}\n',
        evidence.BATCH + 'selected.png': b'\x89PNG\r\n\x1a\nfixture',
        evidence.BATCH + 'source.log': b'excluded old failure\n',
        'tracking/packets.jsonl': b'{"session":"owned","time":1.0}\n',
        'tracking/events.jsonl': b'{"session":"owned","time":1.0}\n'}
    rows = [{'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        for name, raw in sorted(files.items())]
    nontracking = [row for row in rows if not row['path'].startswith('tracking/')]
    metadata = {'schema': 'client442_interaction_checkpoint_v1', 'files': nontracking}
    files['tracking/checkpoint.json'] = (json.dumps(metadata) + '\n').encode()
    raw = files['tracking/checkpoint.json']
    rows.append({'path': 'tracking/checkpoint.json', 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    if extra:
        files.update(extra)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name, raw in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
    compressed = buffer.getvalue()
    return compressed, {'bytes': len(compressed), 'sha256': hashlib.sha256(compressed).hexdigest(), 'file_manifest': rows}


def inspect(raw, cp):
    from tools.client_compatibility.bag_swap_source_index import inspect_archive
    value = inspect_archive(io.BytesIO(raw), cp, evidence.BATCH)
    value[2]['_spool'].cleanup()
    return value


def test_complete_stream_hashes_manifested_logs_as_well_as_source_types():
    raw, cp = stream_fixture()
    data, digests, tracking, count = inspect(raw, cp)
    assert count == len(raw)
    assert evidence.BATCH + 'source.log' in digests
    assert tracking['archived_metadata']['files'] == [row for row in cp['file_manifest'] if not row['path'].startswith('tracking/')]
    assert data[evidence.BATCH + 'entry01/episode.json']['completed'] is False


@pytest.mark.parametrize('name', ('outside/extra.json', 'outside/extra.jsonl', 'outside/extra.png', 'outside/extra.blob'))
def test_rehashed_outside_scope_data_cannot_hide_from_complete_manifest(name):
    raw, cp = stream_fixture({name: b'{}\n'})
    with pytest.raises(RuntimeError, match='unmanifested'):
        inspect(raw, cp)


def test_log_hash_is_checked_even_when_compressed_identity_is_coherently_rehashed():
    raw, cp = stream_fixture()
    next(row for row in cp['file_manifest'] if row['path'].endswith('/source.log'))['sha256'] = 'f' * 64
    with pytest.raises(RuntimeError, match='manifest SHA'):
        inspect(raw, cp)


def test_ordinary_large_json_has_no_opaque_permission_by_name_or_size():
    from tools.client_compatibility import bag_swap_source_index as indexed
    assert indexed._opaque_kind('f' * 64, 494298735) is None


@pytest.mark.parametrize('module', ('checkpoint_bag_swap_stopped', 'review_bag_swap_stopped_checkpoint'))
def test_default_pixi_cli_help_is_pure(module):
    run = subprocess.run([sys.executable, '-m', 'tools.client_compatibility.' + module, '--help'],
        cwd=Path(__file__).resolve().parents[4], text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    assert 'usage:' in run.stdout


def test_checkpoint_preflights_excluded_closure_before_publisher(monkeypatch):
    from tools.client_compatibility import bag_swap_source_index as indexed
    from tools.client_compatibility import checkpoint_interactions as generic
    class Empty:
        data = {}
    calls = []
    monkeypatch.setattr(indexed, 'local_sources', lambda path: Empty())
    monkeypatch.setattr(generic, 'checkpoint', lambda *a: calls.append(a))
    with pytest.raises(RuntimeError, match='one validated'):
        publisher.checkpoint(evidence.lab.ROOT / evidence.BATCH.rstrip('/'), 'synthetic')
    assert calls == []


def _complete_actual_archive(tmp_path):
    """Actual carried ancestors plus an explicitly synthetic new closure epoch.

    All new bytes live in the test's temporary directory. The failed batch and
    its original receipts remain untouched; no publisher or DVC call runs.
    """
    from tools.client_compatibility import bag_swap_source_index as indexed
    from tools.client_compatibility import checkpoint_interactions as generic
    from tools.client_compatibility.world.tests.test_bag_swap_stopped_evidence import fixture
    directory = evidence.lab.ROOT / evidence.BATCH.rstrip('/')
    base = indexed.local_sources(directory)
    synthetic, closure = fixture()
    ready = base.get(evidence.SOURCES['preparation'], False)
    extra = indexed.preload_ancestor_sources(base, ready)
    files = dict(base.paths)
    extra_aliases = []
    for ref in extra:
        old = str(Path(ref['path']).relative_to(base.root))
        physical = evidence.BATCH + 'synthetic_stopped_fixture/source_blobs/' + ref['sha256'] + '.json'
        files[physical] = files.pop(old)
        extra_aliases.append((ref, physical))
    for member, value in synthetic.data.items():
        if member.startswith(evidence.BATCH + 'synthetic_stopped_fixture/'):
            target = tmp_path / ('json_' + hashlib.sha256(member.encode()).hexdigest())
            target.write_bytes(publisher._encoded(value))
            files[member] = str(target)
    for member, values in synthetic.raw_journals.items():
        target = tmp_path / ('journal_' + hashlib.sha256(member.encode()).hexdigest())
        target.write_bytes(b''.join(publisher._encoded(row) for row in values))
        files[member] = str(target)
    log_member = str(Path(closure['stop_log_source']['path']).relative_to(base.root))
    files[log_member] = '/tmp/ui173_failed_entry_stop01.log'
    index_member = str(Path(closure['source_index_source']['path']).relative_to(base.root))
    # The source index cannot include its own hash or the future closure hash.
    files.pop(index_member)
    blobs, aliases = {}, []
    for member, path in sorted(files.items()):
        path = Path(path)
        sha, size = indexed.original.bound(path)['sha256'], path.stat().st_size
        kind = indexed._opaque_kind(sha, size) or {'.json': 'json', '.png': 'png', '.jsonl': 'journal'}.get(
            Path(member).suffix, 'binary')
        blobs.setdefault(sha, {'sha256': sha, 'bytes': size, 'member': member, 'source_member': member, 'kind': kind})
        aliases.append({'scope': 'ui173', 'original_path': str(base.root / member), 'original_member': member,
            'sha256': sha, 'bytes': size, 'blob': blobs[sha]['member']})
    for scope, schema in (('ui172', indexed.fresh.ANCESTRY_SCHEMA), ('ui171', 'client442_bag_swap_ancestry_v1')):
        mapping = indexed._only(base.data, schema)
        for row in (*mapping.get('members', []), *mapping.get('authorities', []), *mapping.get('journals', [])):
            member = row.get('original_member') or str(Path(row['original_path']).relative_to(base.root))
            aliases.append({'scope': scope, 'original_path': row.get('original_path', str(base.root / member)),
                'original_member': member, 'sha256': row['sha256'], 'bytes': row['bytes'],
                'blob': blobs[row['sha256']]['member']})
    for ref, physical in extra_aliases:
        aliases.append({'scope': 'ui172', 'original_path': ref['path'],
            'original_member': str(Path(ref['path']).relative_to(base.root)), 'sha256': ref['sha256'],
            'bytes': Path(files[physical]).stat().st_size, 'blob': blobs[ref['sha256']]['member']})
    index = {'schema': indexed.SCHEMA, 'blobs': sorted(blobs.values(), key=lambda row: row['member']),
        'scopes': [{'id': 'ui171', 'parent': None}, {'id': 'ui172', 'parent': 'ui171'}, {'id': 'ui173', 'parent': 'ui172'}],
        'aliases': sorted(aliases, key=lambda row: (row['scope'], row['original_member']))}
    indexed.validate_index(index)
    target = tmp_path / 'source_index.json'
    target.write_bytes(publisher._encoded(index))
    files[index_member] = str(target)
    closure['source_index_source']['sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
    closure_member = evidence.BATCH + 'synthetic_stopped_fixture/closure.json'
    target = tmp_path / 'closure.json'
    target.write_bytes(publisher._encoded(closure))
    files[closure_member] = str(target)
    current = {key: synthetic.journal(ref) for key, ref in closure['journal_sources'].items()}
    for role in ('packets', 'events'):
        values = current[role] if role == 'events' else [row for row in current[role]
            if 'body' not in row or row.get('name') in generic.SAFE_BODY_NAMES]
        target = tmp_path / ('tracking_' + role + '.jsonl')
        target.write_bytes(b''.join(publisher._encoded(row) for row in values))
        files['tracking/' + role + '.jsonl'] = str(target)
    rows = [{'path': member, 'bytes': Path(path).stat().st_size, 'sha256': indexed.original.bound(path)['sha256']}
        for member, path in sorted(files.items())]
    runs = []
    for member in sorted(name for name in files if name.startswith(evidence.BATCH) and name.endswith('/episode.json')):
        value = json.loads(Path(files[member]).read_bytes())
        runs.append({'path': member, **{key: value[key] for key in ('completed', 'failure', 'controller', 'model', 'revision')}})
    metadata = {'schema': 'client442_interaction_checkpoint_v1', 'code_commit': closure['code_commit'],
        'files': [row for row in rows if not row['path'].startswith('tracking/')], 'runs': runs, 'counts': {},
        'qualified_fixture_operations': 453, 'interaction_plan_operations': 916}
    target = tmp_path / 'metadata.json'
    target.write_bytes(publisher._encoded(metadata))
    files['tracking/checkpoint.json'] = str(target)
    rows.append({'path': 'tracking/checkpoint.json', 'bytes': target.stat().st_size,
        'sha256': indexed.original.bound(target)['sha256']})
    path = tmp_path / 'explicitly_synthetic_closed_archive.tar.gz'
    with tarfile.open(path, mode='w:gz', compresslevel=1) as archive:
        for member, source in sorted(files.items()):
            info = tarfile.TarInfo(member)
            info.size = Path(source).stat().st_size
            with Path(source).open('rb') as stream:
                archive.addfile(info, stream)
    cp = {'bytes': path.stat().st_size, 'sha256': indexed.original.bound(path)['sha256'],
        'file_manifest': sorted(rows, key=lambda row: row['path'])}
    return path, cp, index


def test_full_tar_replays_actual_ancestors_and_serialized_stopped_lifecycle(tmp_path):
    from tools.client_compatibility import bag_swap_source_index as indexed
    path, checkpoint, index = _complete_actual_archive(tmp_path)
    with path.open('rb') as raw:
        data, digests, tracking, size = indexed.inspect_archive(raw, checkpoint, evidence.BATCH)
    try:
        assert size == checkpoint['bytes'] and set(digests) == {row['path'] for row in checkpoint['file_manifest']}
        result = evidence.proof(data, digests, tracking)
        assert result['history']['source_packet_count'] == 5444
        assert result['history']['source_event_count'] == 6731
        assert result['history']['rest']['native_login_second'] == 1791431430
        assert result['ancestors']['ui171']['remote_proof']['actual_packet_journals_verified'] is True
        assert result['ancestors']['ui172']['remote_proof']['operations_admitted'] == 0
        assert result['current_batch_episode_count'] == 5 and result['current_batch_cases'] == 0
        assert result['operations_admitted'] == 0 and result['qualified_fixture_operations'] == 453
        opaque = [row for row in index['blobs'] if row['kind'].endswith('_authority')]
        assert len(opaque) == 2 and all(row['member'] == row['source_member'] for row in opaque)
        assert not any(member in data for member in tracking['opaque_sources'])
    finally:
        tracking['_spool'].cleanup()
