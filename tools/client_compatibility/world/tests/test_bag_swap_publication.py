"""Bounded archive streaming and the exact, minimal carried UI171 proof graph."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace

import pytest

from tools.client_compatibility import checkpoint_bag_swap as publication
from tools.client_compatibility import item_actionbar_evidence as predecessor
from tools.client_compatibility import review_bag_swap_checkpoint as reviewer
from tools.client_compatibility import bag_swap_sources as sources
from tools.client_compatibility.world.tests.test_bag_swap_sources import fixture as authority_fixture, admit


def authority(tmp_path, monkeypatch, *, transition=False, journal_edges=False):
    batch, paths, values, _, _, _ = authority_fixture(tmp_path, monkeypatch,
        transition=transition, journal_edges=journal_edges)
    return batch, paths, values, admit(paths)


def current_epoch_inputs(tmp_path, monkeypatch):
    from tools.client_compatibility import bag_swap_failed_sources as failed
    from tools.client_compatibility import bag_swap_failed_evidence as parent
    from tools.client_compatibility import bag_swap_projection as projection
    repo, root = tmp_path / 'repo', tmp_path / 'lab'
    out = root / 'evidence/ui173/resume'
    out.mkdir(parents=True)
    monkeypatch.setattr(publication.lab, 'REPO', repo)
    monkeypatch.setattr(publication.lab, 'ROOT', root)
    prior = sorted(set(failed.CURRENT_REQUIRED) | set(failed.OLD_MEMBERS) |
        set(parent.PUBLICATION_FILES) | set(parent.PUBLICATION_DEPENDENCIES))
    members = sorted(set(prior) | set(publication.FRESH_CODE_FILES))
    raw = {member: ('actual Git adapter bytes for ' + member + '\n').encode() for member in members}
    refs = [{'path': str(repo / member), 'sha256': hashlib.sha256(raw[member]).hexdigest()} for member in members]
    prior_refs = [ref for ref in refs if str(Path(ref['path']).relative_to(repo)) in prior]
    old = {'graph': {'data': {'parent.json': {'schema': 'client442_bag_swap_failed_journals_v1',
        'code_commit': 'a' * 40, 'code_source_epoch': {'committed_sources': prior_refs}}}}}
    monkeypatch.setattr(projection, 'source_identities', lambda path: refs)
    def git(args, **kwargs):
        assert kwargs['cwd'] == repo
        if args == ['git', 'rev-parse', 'HEAD']:
            return 'b' * 40
        assert args[:2] == ['git', 'show'] and args[2].startswith('b' * 40 + ':')
        return raw[args[2].split(':', 1)[1]]
    monkeypatch.setattr(publication.subprocess, 'check_output', git)
    return out, old, refs, raw


def test_current_epoch_writer_carries_every_actual_git_member_before_launch_and_never_overwrites(tmp_path, monkeypatch):
    out, old, refs, raw = current_epoch_inputs(tmp_path, monkeypatch)
    result = publication.current_code_epoch(out, old)
    epoch = json.loads(Path(result['path']).read_text())
    assert publication.bound(result['path']) == result
    assert epoch['code_commit'] == 'b' * 40 and epoch['committed_sources'] == refs
    assert len(refs) == len(epoch['carried_sources']) == 89
    for original, copy in zip(refs, epoch['carried_sources']):
        envelope = json.loads(Path(copy['path']).read_text())
        member = str(Path(original['path']).relative_to(publication.lab.REPO))
        assert bytes.fromhex(envelope['raw_hex']) == raw[member]
        assert envelope['bytes'] == len(raw[member]) and envelope['sha256'] == original['sha256']
        assert publication.bound(copy['path']) == copy
    with pytest.raises(RuntimeError, match='never overwrites'):
        publication.current_code_epoch(out, old)


@pytest.mark.parametrize('fault', ['same_parent_commit', 'uncommitted_bytes', 'missing_member', 'extra_member'])
def test_current_epoch_writer_refuses_reused_publication_or_uncommitted_incomplete_package(tmp_path, monkeypatch, fault):
    out, old, refs, raw = current_epoch_inputs(tmp_path, monkeypatch)
    if fault == 'same_parent_commit':
        monkeypatch.setattr(publication.subprocess, 'check_output', lambda *args, **kwargs: 'a' * 40)
    elif fault == 'uncommitted_bytes':
        raw[next(iter(raw))] += b'changed in Git adapter'
    elif fault == 'missing_member':
        refs.pop()
    else:
        refs.append({'path': str(publication.lab.REPO / 'unrelated.py'), 'sha256': 'c' * 64})
    with pytest.raises(RuntimeError):
        publication.current_code_epoch(out, old)
    assert not (out / 'code_sources').exists() and not (out / 'current_code_epoch.json').exists()


@pytest.mark.parametrize('transition', [False, True], ids=['ordinary', 'pure_C_to_D'])
def test_required_members_retains_closure_ancestry_and_proof_frames_but_excludes_unused_png(tmp_path, monkeypatch, transition):
    _, paths, _, old = authority(tmp_path, monkeypatch, transition=transition)
    graph = old['graph']
    unused = 'evidence/client_interactions_20990101_ui171/unused/screen.png'
    graph['digests'][unused] = 'a' * 64
    graph['tracking']['digests'][unused] = 'a' * 64
    original_sources, original_frame = predecessor.Sources, predecessor.frame
    required = publication.required_members(graph)
    assert required == sorted(set(required)) and unused not in required
    assert str(paths['final'].relative_to(predecessor.lab.ROOT)) in required
    ancestry = next(value for value in graph['data'].values() if value.get('schema') == predecessor.ANCESTRY_SCHEMA)
    assert all(str(Path(row['copy_path']).relative_to(predecessor.lab.ROOT)) in required for row in ancestry['sources'])
    assert str(Path(ancestry['pointer_observation']['path']).relative_to(predecessor.lab.ROOT)) in required
    assert str(paths['park'].with_name('screen.png').relative_to(predecessor.lab.ROOT)) in required
    if transition:
        assert str(paths['parked_selection'].with_name('parked_selection.png').relative_to(predecessor.lab.ROOT)) in required
    assert predecessor.Sources is original_sources and predecessor.frame is original_frame


def test_required_members_restores_source_instrumentation_when_the_strict_proof_fails(tmp_path, monkeypatch):
    _, _, _, old = authority(tmp_path, monkeypatch)
    original_sources, original_frame = predecessor.Sources, predecessor.frame
    old['graph']['tracking']['members'].pop()
    with pytest.raises(RuntimeError):
        publication.required_members(old['graph'])
    assert predecessor.Sources is original_sources and predecessor.frame is original_frame


def carried_fixture(tmp_path, monkeypatch):
    _, paths, _, old = authority(tmp_path, monkeypatch, journal_edges=True)
    root = predecessor.lab.ROOT
    batch = root / 'evidence/client_interactions_20990101_ui172'
    cache_path = batch / 'authority.json'
    cache_path.parent.mkdir(parents=True)
    cache = {'schema': sources.CACHE_SCHEMA, 'values': old['values'], 'refs': old['predecessor'], 'graph': old['graph']}
    cache_raw = (json.dumps(cache, indent=2) + '\n').encode()
    cache_path.write_bytes(cache_raw)
    ready = {'authority_source': sources.bound(cache_path)}
    data = {str(cache_path.relative_to(root)): cache}
    digests = {str(cache_path.relative_to(root)): hashlib.sha256(cache_raw).hexdigest()}
    rows, journals, authorities, raw_journals = [], [], [], {}
    wanted = publication.required_members(old['graph'])

    def copy(original, raw, suffix):
        digest = hashlib.sha256(raw).hexdigest()
        member = str(batch.relative_to(root)) + '/predecessor/' + digest + suffix
        digests[member] = digest
        return digest, member

    for original in wanted:
        raw = (root / original).read_bytes()
        digest, member = copy(original, raw, Path(original).suffix)
        if original.endswith('.json'):
            data[member] = json.loads(raw)
        rows.append({'original_path': str(root / original), 'original_member': original,
            'sha256': digest, 'bytes': len(raw), 'copy_member': member})
    for role in ('remote', 'checkpoint'):
        ref = old['predecessor'][role]
        raw = Path(ref['path']).read_bytes()
        digest, member = copy(ref['path'], raw, '.json')
        data[member] = json.loads(raw)
        authorities.append({'role': role, 'original_path': ref['path'], 'sha256': digest,
            'bytes': len(raw), 'copy_member': member})
    for original, kind in zip(predecessor.TRACKING_MEMBERS, ('packets', 'events')):
        raw = paths['raw_' + kind].read_bytes()
        lines = [json.loads(line) for line in raw.splitlines()]
        digest, member = copy(original, raw, '.jsonl')
        raw_journals[member] = lines
        journals.append({'original_member': original, 'sha256': digest, 'bytes': len(raw), 'copy_member': member})
    mapping = {'schema': publication.ANCESTRY_SCHEMA, 'authority_source': ready['authority_source'],
        'archive': old['archive'], 'dvc_pointer': old['dvc_pointer'], 'pointer_raw_hex': old['pointer_raw_hex'],
        'members': rows, 'journals': journals, 'authorities': authorities, 'actual_remote_verified': True,
        'compressed_md5': old['dvc_pointer']['oid'], 'local_archive_created': False}
    store = SimpleNamespace(maps=[mapping], data=data, digests=digests, raw_journals=raw_journals, local=False)
    store.get = lambda ref, successful=True: data[str(Path(ref['path']).relative_to(root))]
    return store, ready, mapping


def test_validate_carry_replays_actual_predecessor_journals_against_raw_copied_sources(tmp_path, monkeypatch):
    store, ready, _ = carried_fixture(tmp_path, monkeypatch)
    assert publication.validate_carry(store, ready) is True


@pytest.mark.parametrize('kind', ['packets', 'events'])
@pytest.mark.parametrize('removed', ['prefix', 'suffix', 'both'])
def test_validate_carry_rejects_truncated_raw_journal_even_when_the_whole_ui171_window_is_unchanged(
        tmp_path, monkeypatch, kind, removed):
    store, ready, mapping = carried_fixture(tmp_path, monkeypatch)
    row = next(row for row in mapping['journals'] if row['original_member'].endswith(kind + '.jsonl'))
    lines = store.raw_journals[row['copy_member']]
    retained = [line for line in lines if not (line['time'] == 1079 and removed in ('prefix', 'both')) and
        not (line['time'] == 1127 and removed in ('suffix', 'both'))]
    assert [line for line in retained if 1080 <= line['time'] <= 1126] == \
        [line for line in lines if 1080 <= line['time'] <= 1126]
    raw = b''.join((json.dumps(line) + '\n').encode() for line in retained)
    row.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
    store.digests[row['copy_member']] = row['sha256']
    store.raw_journals[row['copy_member']] = retained
    with pytest.raises(RuntimeError, match='first-stream authority'):
        publication.validate_carry(store, ready)


@pytest.mark.parametrize('fault', ['missing_member', 'substituted_digest', 'json_semantics', 'missing_authority',
    'wrong_archive', 'wrong_pointer_bytes', 'not_remote', 'missing_journal', 'missing_raw', 'changed_packet'])
def test_validate_carry_rejects_incomplete_changed_or_unattributable_predecessor_bytes(tmp_path, monkeypatch, fault):
    store, ready, mapping = carried_fixture(tmp_path, monkeypatch)
    if fault == 'missing_member': mapping['members'].pop()
    elif fault == 'substituted_digest':
        store.digests[mapping['members'][0]['copy_member']] = 'a' * 64
    elif fault == 'json_semantics':
        member = next(row['copy_member'] for row in mapping['members'] if row['original_member'].endswith('.json'))
        store.data[member] = {'changed': True}
    elif fault == 'missing_authority': mapping['authorities'].pop()
    elif fault == 'wrong_archive': mapping['archive'] = {**mapping['archive'], 'sha256': 'a' * 64}
    elif fault == 'wrong_pointer_bytes': mapping['pointer_raw_hex'] = '00'
    elif fault == 'not_remote': mapping['actual_remote_verified'] = False
    elif fault == 'missing_journal': mapping['journals'].pop()
    elif fault == 'missing_raw': store.raw_journals.clear()
    else:
        packets = next(row['copy_member'] for row in mapping['journals'] if row['original_member'].endswith('packets.jsonl'))
        next(row for row in store.raw_journals[packets] if row['name'] == 'CMSG_SET_ACTION_BUTTON')['body'] = '00'
    with pytest.raises(RuntimeError):
        publication.validate_carry(store, ready)


PREFIX = 'evidence/client_interactions_20990101_ui172/'
BASE_FILES = [(PREFIX + 'pause/episode.json', b'{"phase":"fixture_closed"}\n'),
    (PREFIX + 'pause/screen.png', b'\x89PNG\r\n\x1a\nfixture'),
    (PREFIX + 'journals/packets.jsonl', b'{"time":2,"name":"fixture"}\n'),
    (PREFIX + 'journals/events.jsonl', b'{"time":3,"event":"fixture"}\n')]
TRACKING_FILES = [(member, b'{"time":4,"journal":"' + member.encode() + b'"}\n')
    for member in reviewer.evidence.TRACKING_MEMBERS]


def archive(files):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as handle:
        for name, raw in files:
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            handle.addfile(member, io.BytesIO(raw))
    raw = stream.getvalue()
    selected = {name: body for name, body in files if name.startswith(PREFIX)}
    checkpoint = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
        'file_manifest': [{'path': name, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
            for name, body in selected.items()]}
    return raw, checkpoint


@pytest.fixture
def collect(monkeypatch):
    calls = []

    def retained(member, lines, data, tracking):
        rows = list(lines)
        tracking['members'].add(member)
        tracking['packets' if member.endswith('packets.jsonl') else 'events'].extend(rows)
        calls.append((member, rows, deepcopy(data)))

    monkeypatch.setattr(reviewer.evidence, 'collect', retained)
    return calls


def test_stream_checks_exact_json_png_and_both_source_owned_and_generic_journals(collect):
    raw, checkpoint = archive(BASE_FILES + TRACKING_FILES)
    data, digests, tracking, count = reviewer.inspect_archive(io.BytesIO(raw), checkpoint, PREFIX)
    assert count == len(raw) and data == {BASE_FILES[0][0]: {'phase': 'fixture_closed'}}
    assert set(digests) == {name for name, _ in BASE_FILES}
    assert tracking['raw_journals'][BASE_FILES[2][0]] == [{'time': 2, 'name': 'fixture'}]
    assert tracking['raw_journals'][BASE_FILES[3][0]] == [{'time': 3, 'event': 'fixture'}]
    assert {member for member, _, _ in collect} == set(reviewer.evidence.TRACKING_MEMBERS)
    assert all(data_at_collection == data for _, _, data_at_collection in collect)


@pytest.mark.parametrize('fault', ['digest', 'duplicate_source', 'missing_source', 'duplicate_generic',
    'missing_generic', 'unmanifested', 'not_png', 'compressed_sha', 'compressed_bytes', 'trailer'])
def test_stream_refuses_changed_duplicate_missing_or_unmanifested_actual_archive_members(collect, fault):
    files = BASE_FILES + TRACKING_FILES
    _, checkpoint = archive(files)
    if fault == 'digest': checkpoint['file_manifest'][0]['sha256'] = 'a' * 64
    elif fault == 'duplicate_source': files += [BASE_FILES[0]]
    elif fault == 'missing_source': files = files[1:]
    elif fault == 'duplicate_generic': files += [TRACKING_FILES[0]]
    elif fault == 'missing_generic': files = files[:-1]
    elif fault == 'unmanifested': files += [(PREFIX + 'unreviewed.json', b'{}')]
    elif fault == 'not_png':
        files = [(name, b'invalid' if name.endswith('.png') else body) for name, body in files]
    raw, current = archive(files)
    # Preserve the original selected manifest while updating actual compression;
    # each structural fault is evaluated independently of compressed identity.
    checkpoint.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    if fault == 'not_png': checkpoint['file_manifest'] = current['file_manifest']
    elif fault == 'compressed_sha': checkpoint['sha256'] = 'a' * 64
    elif fault == 'compressed_bytes': checkpoint['bytes'] += 1
    elif fault == 'trailer': raw += b'bound-compressed-trailer'
    with pytest.raises(RuntimeError):
        reviewer.inspect_archive(io.BytesIO(raw), checkpoint, PREFIX)


def test_stream_accounts_for_every_compressed_byte_including_a_retained_trailer(collect):
    raw, checkpoint = archive(BASE_FILES + TRACKING_FILES)
    raw += b'bound-compressed-trailer'
    checkpoint.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    assert reviewer.inspect_archive(io.BytesIO(raw), checkpoint, PREFIX)[3] == len(raw)


def test_source_owned_journal_row_bound_fails_without_dropping_tail_rows(collect):
    files = [(name, b'{}\n' * 250001 if name == BASE_FILES[2][0] else body)
        for name, body in BASE_FILES + TRACKING_FILES]
    raw, checkpoint = archive(files)
    with pytest.raises(RuntimeError, match='bounded rows'):
        reviewer.inspect_archive(io.BytesIO(raw), checkpoint, PREFIX)


def test_source_owned_json_byte_bound_fails_without_allocating_the_declared_member(monkeypatch, collect):
    chunk = b' ' * (1024 * 1024)

    class RepeatedChunks:
        def __init__(self): self.count = 0
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self, _size):
            self.count += 1
            return chunk if self.count <= 257 else b''

    member = tarfile.TarInfo(BASE_FILES[0][0])
    member.size = 257 * len(chunk)

    class OversizedArchive:
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def __iter__(self): return iter([member])
        def extractfile(self, _member): return RepeatedChunks()

    _, checkpoint = archive(BASE_FILES + TRACKING_FILES)
    checkpoint['file_manifest'][0]['bytes'] = member.size
    monkeypatch.setattr(reviewer.tarfile, 'open', lambda **_kwargs: OversizedArchive())
    with pytest.raises(RuntimeError, match='bounded size'):
        reviewer.inspect_archive(io.BytesIO(b''), checkpoint, PREFIX)
