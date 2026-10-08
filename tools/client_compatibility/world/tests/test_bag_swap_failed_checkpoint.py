"""The excluded collector retains source bytes without inputs or old upgrades."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tarfile

import pytest

from tools.client_compatibility import checkpoint_bag_swap_failed as collector
from tools.client_compatibility import bag_swap_failed_sources as sources
from tools.client_compatibility import bag_swap_projection as projection
from tools.client_compatibility import interaction_bag_swap_failed_entry_pause as runtime
from tools.client_compatibility.observation import journal


@pytest.mark.parametrize('attribution', ['native', 'physical', 'account', 'guid'])
@pytest.mark.parametrize('bad', ['missing', None, float('nan'), float('inf'), float('-inf')])
def test_complete_collector_rejects_attributable_malformed_time_before_filtering(monkeypatch, attribution, bad):
    row = {'event': 'instance_authenticated', 'session': 'foreign'}
    row.update({'native': {'session': 'native'}, 'physical': {'session': 'physical'},
        'account': {'account_id': 2}, 'guid': {'guid': 2}}[attribution])
    if bad != 'missing':
        row['time'] = bad
    monkeypatch.setattr(journal, 'entries', lambda path: iter([row]))
    with pytest.raises(RuntimeError, match='cannot be filtered'):
        collector.selected_rows(Path('/unused'), 10, 30, {'native', 'physical'})


def test_collector_keeps_all_complete_interval_rows_and_does_not_rewrite_them(monkeypatch):
    rows = [{'time': 9, 'session': 'native'}, {'time': 10, 'session': 'other', 'opaque': [1, 2]},
        {'time': 20, 'session': 'native', 'name': 'SMSG_UPDATE_OBJECT', 'body': '0012'},
        {'time': 30, 'session': 'native', 'event': 'native_stream_closed', 'error': 'actual EOF'},
        {'time': 31, 'session': 'native'}]
    before = deepcopy(rows)
    monkeypatch.setattr(journal, 'entries', lambda path: iter(rows))
    assert collector.selected_rows(Path('/unused'), 10, 30, {'native'}) == rows[1:4]
    assert rows == before


def test_collector_never_carries_authentication_bodies(monkeypatch):
    monkeypatch.setattr(journal, 'entries', lambda path: iter([
        {'time': 20, 'session': 'native', 'name': 'CMSG_AUTH_SESSION', 'body': 'private'}]))
    with pytest.raises(RuntimeError, match='authentication bodies'):
        collector.selected_rows(Path('/unused'), 10, 30, {'native'})


@pytest.mark.parametrize('rows', [[], [None], ['not a journal object']])
def test_collector_refuses_missing_or_nonobject_journal(monkeypatch, rows):
    monkeypatch.setattr(journal, 'entries', lambda path: iter(rows))
    with pytest.raises(RuntimeError):
        collector.selected_rows(Path('/unused'), 10, 30, {'native'})


def test_prior_pause_journal_rejects_unterminated_tail(tmp_path, monkeypatch):
    monkeypatch.setattr(collector.lab, 'ROOT', tmp_path)
    path = tmp_path / 'evidence/packet.jsonl'
    path.parent.mkdir()
    path.write_text('{"time": 10}\n{"time": 20}')
    with pytest.raises(RuntimeError, match='complete.*lines'):
        collector.load_journal(collector.bound(path))


def test_prior_pause_journal_keeps_full_rows_and_rejects_changed_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(collector.lab, 'ROOT', tmp_path)
    path = tmp_path / 'evidence/packet.jsonl'
    path.parent.mkdir()
    path.write_text('{"time":10,"body":"00","session":"native"}\n')
    ref = collector.bound(path)
    assert collector.load_journal(ref) == [{'time': 10, 'body': '00', 'session': 'native'}]
    path.write_text('{"time":10,"body":"01","session":"native"}\n')
    with pytest.raises(RuntimeError, match='immutable'):
        collector.load_journal(ref)


def package_fixture(tmp_path, monkeypatch, *, changed=False, dependency=False):
    repo = tmp_path / 'repo'
    repo.mkdir()
    monkeypatch.setattr(collector.lab, 'REPO', repo)
    members = ['old.py', 'new.py'] + (['dependency.py'] if dependency else [])
    bodies = {str(repo / member): ('original old' if member == 'old.py' else 'new collector').encode() for member in members}
    refs = [{'path': path, 'sha256': hashlib.sha256(raw).hexdigest()} for path, raw in sorted(bodies.items())]
    for path, raw in bodies.items():
        Path(path).write_bytes(raw)
    old_ref = next(ref for ref in refs if ref['path'].endswith('old.py'))
    closure = {'code_commit': '1' * 40, 'committed_sources': [old_ref.copy()]}
    if changed:
        closure['committed_sources'][0]['sha256'] = 'a' * 64
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.bag_swap_failed_evidence',
        SimpleNamespace(PUBLICATION_FILES=('new.py',),
            PUBLICATION_DEPENDENCIES=('dependency.py',) if dependency else ()))
    monkeypatch.setattr(projection, 'source_identities', lambda path:
        deepcopy([ref for ref in refs if not ref['path'].endswith('dependency.py')]))
    def git(command, **kwargs):
        if command[1:3] == ['rev-parse', 'HEAD']:
            return '2' * 40 + '\n'
        member = command[2].split(':', 1)[1]
        return bodies[str(repo / member)]
    monkeypatch.setattr(collector.subprocess, 'check_output', git)
    output = tmp_path / 'copies'
    output.mkdir()
    return closure, output, refs


def test_new_code_epoch_carries_exact_raw_committed_bytes_without_upgrading_pause(tmp_path, monkeypatch):
    closure, output, refs = package_fixture(tmp_path, monkeypatch)
    before = deepcopy(closure)
    epoch = collector.code_epoch(output, closure)
    assert epoch['committed_sources'] == refs and epoch['code_commit'] == '2' * 40
    for source, copy in zip(refs, epoch['carried_sources']):
        value = json.loads(Path(copy['path']).read_text())
        assert value['original_path'] == source['path'] and value['sha256'] == source['sha256']
        assert hashlib.sha256(bytes.fromhex(value['raw_hex'])).hexdigest() == source['sha256']
        assert value['bytes'] == len(bytes.fromhex(value['raw_hex']))
    assert closure == before


def test_new_package_rejects_changed_existing_pause_source_before_carry(tmp_path, monkeypatch):
    closure, output, _ = package_fixture(tmp_path, monkeypatch, changed=True)
    with pytest.raises(RuntimeError, match='preserve the exact'):
        collector.code_epoch(output, closure)
    assert list(output.iterdir()) == []


def test_new_code_epoch_pins_direct_publication_dependency_outside_old_vector(tmp_path, monkeypatch):
    closure, output, refs = package_fixture(tmp_path, monkeypatch, dependency=True)
    value = collector.code_epoch(output, closure)
    assert value['committed_sources'] == refs and len(value['carried_sources']) == 3


def test_new_code_epoch_refuses_dependency_checkout_different_from_committed_bytes(tmp_path, monkeypatch):
    closure, output, refs = package_fixture(tmp_path, monkeypatch, dependency=True)
    Path(next(ref['path'] for ref in refs if ref['path'].endswith('dependency.py'))).write_text('different parser')
    with pytest.raises(RuntimeError, match='dependency differs'):
        collector.code_epoch(output, closure)
    assert list(output.iterdir()) == []


def collection_fixture(tmp_path, monkeypatch):
    root = tmp_path / 'lab'
    directory = root / 'evidence/batch'
    directory.mkdir(parents=True)
    monkeypatch.setattr(collector.lab, 'ROOT', root)
    closure = directory / 'pause/episode.json'
    closure.parent.mkdir()
    closure.write_text('{"immutable":"original pause bytes"}\n')
    # Only this internal unit fixture replaces the fixed real pause authority.
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.bag_swap_failed_evidence',
        SimpleNamespace(_CLOSURE_SOURCE=collector.bound(closure)))
    ready_ref = {'path': str(directory / 'ready/episode.json'), 'sha256': 'a' * 64}
    failed_ref = {'path': str(directory / 'failed/episode.json'), 'sha256': 'b' * 64}
    ready = {'started_at': 10, 'native_session': 'native'}
    failed = {'started_at': 15}
    pause = {'finished_at': 30, 'original_preparation_source': ready_ref,
        'original_entry_source': failed_ref, 'failed_history': {'instance_session': 'physical'},
        'journal_sources': {'packets': {'role': 'packets'}, 'events': {'role': 'events'}},
        'actor': {'guid': 2}, 'runtime': {'client': 'stopped'}}
    data = {str(closure): pause, ready_ref['path']: ready, failed_ref['path']: failed}
    monkeypatch.setattr(runtime, 'LocalSources', lambda: SimpleNamespace(get=lambda ref: deepcopy(data[ref['path']])))
    preflight = []
    monkeypatch.setattr(sources, 'validate_failed_pause', lambda store, value: preflight.append(deepcopy(value)))
    rows = {'packets': [{'time': 20, 'session': 'native', 'body': '00'}],
        'events': [{'time': 30, 'session': 'native', 'event': 'native_stream_closed'}]}
    monkeypatch.setattr(collector, 'selected_rows', lambda path, start, end, sessions:
        deepcopy(rows['packets' if path.name == 'world_packets.jsonl' else 'events']))
    monkeypatch.setattr(collector, 'load_journal', lambda ref: [{'prior': ref['role']}])
    calls = []
    def validate(*args):
        calls.append(deepcopy(args))
        return {'complete': True, 'qualification_added': False}
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.bag_swap_failed_journals',
        SimpleNamespace(validate_journals=validate))
    monkeypatch.setattr(collector, 'code_epoch', lambda *args:
        {'code_commit': '2' * 40, 'committed_sources': [], 'carried_sources': []})
    times = iter([40, 41])
    monkeypatch.setattr(collector.time, 'time', lambda: next(times))
    return directory, closure, directory / 'new_journals', data, rows, calls, preflight


def test_journal_snapshot_creates_distinct_excluded_receipt_and_preserves_closed_source(tmp_path, monkeypatch):
    directory, closure, output, data, rows, calls, preflight = collection_fixture(tmp_path, monkeypatch)
    before = closure.read_bytes(), deepcopy(data)
    value = collector.journal_snapshot(directory, closure, output)
    assert value['journal_interval'] == {'from': 10, 'until': 30}
    assert (value['started_at'], value['finished_at']) == (40, 41)
    assert value['completed'] is True and value['failure'] is None
    assert value['qualification_added'] is value['input_sent'] is value['mutation_sent'] is False
    assert value['operations_admitted'] == 0 and value['excluded_failed_entry'] is True
    assert len(preflight) == len(calls) == 1
    assert calls[0][:2] == (rows['packets'], rows['events'])
    assert calls[0][-2:] == ([{'prior': 'packets'}], [{'prior': 'events'}])
    assert json.loads((output / 'journal_receipt.json').read_text()) == value
    assert not (output / 'episode.json').exists()
    assert (closure.read_bytes(), data) == before


def test_closed_source_refusal_precedes_new_evidence_output(tmp_path, monkeypatch):
    directory, closure, output, *_ = collection_fixture(tmp_path, monkeypatch)
    def reject(*args):
        raise RuntimeError('original source cannot be reproved')
    monkeypatch.setattr(sources, 'validate_failed_pause', reject)
    with pytest.raises(RuntimeError, match='cannot be reproved'):
        collector.journal_snapshot(directory, closure, output)
    assert not output.exists()


def test_collector_refuses_to_overwrite_any_previous_capture_attempt(tmp_path, monkeypatch):
    directory, closure, output, *_ = collection_fixture(tmp_path, monkeypatch)
    output.mkdir()
    with pytest.raises(RuntimeError, match='one new private'):
        collector.journal_snapshot(directory, closure, output)


def test_post_stop_journal_refusal_precedes_copying_or_packaging(tmp_path, monkeypatch):
    directory, closure, output, *_ = collection_fixture(tmp_path, monkeypatch)
    def reject(*args):
        raise RuntimeError('unmatched post-stop packet')
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.bag_swap_failed_journals',
        SimpleNamespace(validate_journals=reject))
    with pytest.raises(RuntimeError, match='unmatched post-stop'):
        collector.journal_snapshot(directory, closure, output)
    assert not output.exists()


def test_collector_rejects_changed_actual_closed_authority_before_source_read(tmp_path, monkeypatch):
    directory, closure, output, *_ = collection_fixture(tmp_path, monkeypatch)
    closure.write_text('{"immutable":"substituted pause bytes"}\n')
    with pytest.raises(RuntimeError, match='actual immutable'):
        collector.journal_snapshot(directory, closure, output)
    assert not output.exists()


def test_collector_rejects_lexical_parent_traversal_before_reading_sources(tmp_path, monkeypatch):
    directory, closure, output, *_ = collection_fixture(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match='one new private'):
        collector.journal_snapshot(directory, closure, directory / '..' / 'escaped')
    assert not output.exists()


def checkpoint_fixture(tmp_path, monkeypatch, files=None, *, wrong_archived_manifest=False,
    float_archived_bytes=False):
    root, repo = tmp_path / 'lab', tmp_path / 'repo'
    directory = root / 'evidence/batch'
    directory.mkdir(parents=True)
    target = repo / 'artifacts/client_harness/excluded.tar.gz'
    target.parent.mkdir(parents=True)
    monkeypatch.setattr(collector.lab, 'ROOT', root)
    monkeypatch.setattr(collector.lab, 'REPO', repo)
    files = files if files is not None else [('tracking/packets.jsonl', b'{"packet":"actual"}\n'),
        ('tracking/events.jsonl', b'{"event":"actual"}\n')]
    manifest = [{'path': 'evidence/batch/original.json', 'sha256': 'a' * 64, 'bytes': 20}]
    metadata = {'schema': 'client442_interaction_checkpoint_v1',
        'files': [] if wrong_archived_manifest else deepcopy(manifest)}
    if float_archived_bytes:
        metadata['files'][0]['bytes'] = float(metadata['files'][0]['bytes'])
    files = [*files, ('tracking/checkpoint.json', json.dumps(metadata).encode())]
    with tarfile.open(target, 'w:gz') as archive:
        for name, raw in files:
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            archive.addfile(member, io.BytesIO(raw))
    value = {'file': str(target.relative_to(repo)), 'bytes': target.stat().st_size,
        'sha256': collector.bound(target)['sha256'], 'cloud_verified': True,
        'file_manifest': manifest}
    receipt = directory / 'checkpoint_receipt.json'
    receipt.write_text(json.dumps(value))
    return directory, target, value, files


def test_checkpoint_wrapper_binds_both_actual_full_journals_and_keeps_archive_unchanged(tmp_path, monkeypatch):
    directory, target, old, files = checkpoint_fixture(tmp_path, monkeypatch)
    before = target.read_bytes()
    result = collector.complete_tracking_manifest(directory)
    assert result['file_manifest'][0] == old['file_manifest'][0]
    assert result['file_manifest'][1:] == sorted([{'path': name, 'bytes': len(raw),
        'sha256': hashlib.sha256(raw).hexdigest()} for name, raw in files], key=lambda row: row['path'])
    assert result['sha256'] == old['sha256'] and result['bytes'] == old['bytes']
    assert json.loads((directory / 'checkpoint_receipt.json').read_text()) == result
    assert target.read_bytes() == before
    assert not (directory / 'checkpoint_receipt_complete.tmp').exists()


def test_checkpoint_wrapper_binds_real_optional_probe_and_dvclive_tracking_outputs(tmp_path, monkeypatch):
    files = [('tracking/packets.jsonl', b'packet\n'), ('tracking/events.jsonl', b'event\n'),
        ('tracking/owned_tame_request_packets.jsonl', b''),
        ('tracking/live/metrics.json', b'{"closed_runs":9}\n'), ('tracking/live/params.yaml', b'controller: code\n')]
    directory, target, old, files = checkpoint_fixture(tmp_path, monkeypatch, files)
    before = target.read_bytes()
    result = collector.complete_tracking_manifest(directory)
    assert result['file_manifest'][1:] == sorted([{'path': name, 'bytes': len(raw),
        'sha256': hashlib.sha256(raw).hexdigest()} for name, raw in files], key=lambda row: row['path'])
    assert target.read_bytes() == before and result['sha256'] == old['sha256']


@pytest.mark.parametrize('fault', ['missing_packets', 'missing_events', 'duplicate_packets',
    'archive_bytes_changed', 'unsynchronized', 'already_added', 'archived_manifest_changed',
    'archived_manifest_float_bytes'])
def test_checkpoint_full_tracking_manifest_refuses_missing_changed_or_repeated_source(tmp_path, monkeypatch, fault):
    files = [('tracking/packets.jsonl', b'packet\n'), ('tracking/events.jsonl', b'event\n')]
    if fault == 'missing_packets':
        files = files[1:]
    elif fault == 'missing_events':
        files = files[:-1]
    elif fault == 'duplicate_packets':
        files += [files[0]]
    directory, target, value, _ = checkpoint_fixture(tmp_path, monkeypatch, files,
        wrong_archived_manifest=fault == 'archived_manifest_changed',
        float_archived_bytes=fault == 'archived_manifest_float_bytes')
    if fault == 'archive_bytes_changed':
        target.write_bytes(target.read_bytes() + b'changed')
    elif fault == 'unsynchronized':
        value['cloud_verified'] = False
    elif fault == 'already_added':
        value['file_manifest'].append({'path': files[0][0], 'bytes': 1, 'sha256': 'b' * 64})
    receipt = directory / 'checkpoint_receipt.json'
    receipt.write_text(json.dumps(value))
    before = receipt.read_bytes()
    with pytest.raises(RuntimeError):
        collector.complete_tracking_manifest(directory)
    assert receipt.read_bytes() == before
