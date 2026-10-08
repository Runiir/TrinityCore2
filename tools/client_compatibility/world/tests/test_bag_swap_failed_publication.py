"""Strict complete failed-pause archive, code packages and byte-bound journals."""
from copy import deepcopy
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

from tools.client_compatibility import bag_swap_failed_evidence as e
from tools.client_compatibility import bag_swap_failed_sources as s
from tools.client_compatibility import bag_swap_failed_contract as history
from tools.client_compatibility import bag_swap_failed_journals as journals
from tools.client_compatibility import review_bag_swap_failed_checkpoint as reviewer
from tools.client_compatibility.world.tests.test_bag_swap_failed_sources import fixture as closure_fixture
from tools.client_compatibility.world.tests.test_bag_swap_failed_journals import fixture as wire_fixture
from tools.client_compatibility.world.tests.test_bag_swap_publication import carried_fixture


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def refresh(store):
    """Rebind only this explicit synthetic unit DAG after adding its cache refs."""
    def references(value):
        if type(value) is dict:
            if set(value) == {'path', 'sha256'}:
                path = Path(value['path'])
                if path.is_relative_to(store.root):
                    member = str(path.relative_to(store.root))
                    if member in store.data:
                        value['sha256'] = store.digests[member]
            for child in value.values(): references(child)
        elif type(value) is list:
            for child in value: references(child)
    for _ in range(32):
        before = deepcopy(store.digests)
        for member, value in store.data.items():
            if member.startswith('evidence/unit/'):
                store.files[member] = encoded(value)
                store.digests[member] = hashlib.sha256(store.files[member]).hexdigest()
        for member, value in store.data.items():
            if member.startswith('evidence/unit/'):
                references(value)
        if store.digests == before:
            return
    raise AssertionError('unit source DAG did not converge')


def fixture(tmp_path, monkeypatch):
    old_store, _, mapping = carried_fixture(tmp_path / 'old', monkeypatch)
    old_root = Path(mapping['members'][0]['original_path']).parents
    # The exact synthetic UI171 fixture owns its own root used by its strict
    # proof. Current failed-entry sources use a separate virtual private root.
    from tools.client_compatibility import item_actionbar_evidence as predecessor
    old_root = predecessor.lab.ROOT
    store, capture, pause, ready_ref = closure_fixture(tmp_path / 'current', monkeypatch)
    ready = store.get(ready_ref, False)
    failed = store.get(pause['original_entry_source'], False)
    wire = wire_fixture()
    pause.update(started_at=wire['pause']['started_at'], finished_at=wire['pause']['finished_at'],
        stop_finished_at=wire['pause']['stop_finished_at'], fine_tuned=False, action='stop_expired_failed_entry_scout')
    pause['journal_sources'] = {'packets': store.journal('pause_full/packets.jsonl', wire['capture_packets']),
        'events': store.journal('pause_full/events.jsonl', wire['capture_events'])}
    pause['failed_history'] = history.failed_history(wire['capture_packets'], wire['capture_events'],
        ready, failed, wire['pause']['failed_history']['audit_until'])
    for member, value in old_store.data.items():
        store.data[member] = deepcopy(value)
    for member, digest in old_store.digests.items(): store.digests[member] = digest
    for row in mapping['members'] + mapping['authorities']:
        store.files[row['copy_member']] = Path(row['original_path']).read_bytes()
    cache_member = next(m for m, v in old_store.data.items() if v.get('schema') == 'client442_bag_swap_predecessor_authority_v1')
    cache_path = old_root / cache_member
    store.files[cache_member] = cache_path.read_bytes()
    for row in mapping['journals']:
        kind = Path(row['original_member']).name
        raw = (old_root / 'evidence/fixture_original_journals' / kind).read_bytes()
        store.files[row['copy_member']] = raw
        store.raw_journals[row['copy_member']] = deepcopy(old_store.raw_journals[row['copy_member']])
    authority_ref = {'path': str(store.root / cache_member), 'sha256': store.digests[cache_member]}
    ready['authority_source'] = authority_ref
    capture['authority_source'] = pause['authority_source'] = deepcopy(authority_ref)
    mapping = deepcopy(mapping)
    mapping['authority_source'] = authority_ref
    store.put('predecessor_map.json', mapping)
    original = pause['code_epochs']['epochs'][3]
    old_raw = {ref['path']: bytes.fromhex(store.get(copy, False)['raw_hex'])
        for ref, copy in zip(original['committed_sources'], original['carried_sources'])}
    repo = s._repo(ready)
    members = sorted(set(str(Path(ref['path']).relative_to(repo)) for ref in original['committed_sources']) |
        set(e.PUBLICATION_FILES) | set(e.PUBLICATION_DEPENDENCIES))
    refs, copies = [], []
    for index, member in enumerate(members):
        path = str(repo / member)
        raw = old_raw.get(path, b'unit publication source\n' + member.encode())
        if member == 'tools/client_compatibility/checkpoint_interactions.py':
            raw = b'SAFE_BODY_NAMES = {"CMSG_LOADING_SCREEN_NOTIFY"}\n'
        elif member == e.PLAN:
            # Explicit synthetic plan with the actual ledger schema/counts;
            # it is not a historical or newly qualified experiment receipt.
            raw = encoded(plan_fixture())
        ref = {'path': path, 'sha256': hashlib.sha256(raw).hexdigest()}
        refs.append(ref)
        copies.append(store.put(f'publication_code/{index:03d}.json', {'schema': s.CODE_SCHEMA, 'code_commit': 'e' * 40,
            'original_path': path, 'sha256': ref['sha256'], 'bytes': len(raw), 'raw_hex': raw.hex()}))
    result = journals.validate_journals(wire['packets'], wire['events'], ready, failed, pause,
        wire['capture_packets'], wire['capture_events'])
    receipt = {'schema': e.JOURNAL_SCHEMA, 'closure_source': {'path': str(store.root / 'evidence/unit/closed/episode.json'),
        'sha256': '0' * 64}, 'preparation_source': ready_ref, 'started_at': pause['finished_at'] + 10,
        'finished_at': pause['finished_at'] + 20, 'completed': True, 'failure': None, 'controller': 'code',
        'model': None, 'revision': None, 'actor': ready['actor'], 'runtime': ready['runtime'], 'code_commit': 'e' * 40,
        'code_source_epoch': {'code_commit': 'e' * 40, 'committed_sources': refs, 'carried_sources': copies},
        'input_sent': False, 'mutation_sent': False, 'qualification_added': False, 'operations_admitted': 0,
        'excluded_failed_entry': True, 'journal_interval': {'from': ready['started_at'], 'until': pause['finished_at']},
        'journal_sources': {'packets': store.journal('complete/packets.jsonl', wire['packets']),
            'events': store.journal('complete/events.jsonl', wire['events'])}, 'journal_proof': result}
    store.put('complete/journal_receipt.json', receipt)
    for name in ('scout_capture', 'scout_realm'):
        store.put(name + '/episode.json', {'schema': 'client442_laya_interactions_v1',
            'phase': 'unit_readonly_diagnostic', 'started_at': ready['started_at'] - 2,
            'finished_at': ready['started_at'] - 1, 'completed': True, 'failure': None,
            'controller': 'code', 'model': None, 'revision': None, 'cases': [], 'cleanup': [],
            'qualification_added': False})
    refresh(store)
    expected = {role: {'path': ref['path'], 'sha256': store.digests[str(Path(ref['path']).relative_to(store.root))]}
        for role, ref in s._HISTORICAL_SOURCES.items()}
    monkeypatch.setattr(s, '_HISTORICAL_SOURCES', expected)
    monkeypatch.setattr(e, 'ROOT', store.root)
    monkeypatch.setattr(e, '_CLOSURE_SOURCE', {'path': str(store.root / 'evidence/unit/closed/episode.json'),
        'sha256': store.digests['evidence/unit/closed/episode.json']})
    generic_packets = [row for row in wire['packets'] if 'body' not in row or row['name'] == 'CMSG_LOADING_SCREEN_NOTIFY']
    store.files['tracking/packets.jsonl'] = b''.join(encoded(row) + b'\n' for row in generic_packets)
    store.files['tracking/events.jsonl'] = b''.join(encoded(row) + b'\n' for row in wire['events'])
    return store, pause


def plan_fixture():
    cases = [{'id': 'unit.operation.' + str(i)} for i in range(915)]
    cases.append({'id': 'bags.swap_item', 'family': 'bags', 'operation': 'swap_item', 'automation': 'pending_adapter'})
    return {'schema': 'client442_interactions_v1', 'client_build': 60895, 'cases': cases,
        'qualified_operations': 453, 'qualification_records': [{'id': 'unit_existing_qualifications',
            'operations': [case['id'] for case in cases[:453]]}]}


def archive(files, prefix='evidence/unit/', *, code_commit='e' * 40, extra=(), actual_overrides=None, metadata_changes=None):
    rows = [{'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        for name, raw in files.items() if not name.startswith('tracking/')]
    files = dict(files)
    runs = []
    for member in sorted(files):
        if member.startswith(prefix) and member.endswith('/episode.json'):
            run = json.loads(files[member])
            runs.append({'path': member, **{key: run.get(key) for key in ('completed', 'failure', 'controller', 'model', 'revision')}})
    metadata = {'schema': 'client442_interaction_checkpoint_v1', 'code_commit': code_commit, 'files': rows,
        'runs': runs, 'counts': {}, 'qualified_fixture_operations': 453, 'interaction_plan_operations': 916}
    metadata.update(metadata_changes or {})
    files['tracking/checkpoint.json'] = encoded(metadata)
    rows += [{'path': name, 'bytes': len(files[name]), 'sha256': hashlib.sha256(files[name]).hexdigest()}
        for name in sorted(files) if name.startswith('tracking/')]
    files.update(actual_overrides or {})
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as handle:
        for name, raw in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(raw)
            handle.addfile(member, io.BytesIO(raw))
        for member, raw in extra:
            handle.addfile(member, io.BytesIO(raw) if raw is not None else None)
    raw = stream.getvalue()
    return raw, {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'file_manifest': rows}, prefix


def test_complete_serialized_failed_pause_tar_reproves_ui171_and_actual_post_stop_suffix(tmp_path, monkeypatch):
    store, pause = fixture(tmp_path, monkeypatch)
    # All copied predecessor members are selected despite their distinct unit
    # prefix; production places these in the same actual UI172 batch.
    raw, cp, prefix = archive(store.files, 'evidence/')
    data, digests, tracking, size = reviewer.inspect_archive(io.BytesIO(raw), cp, prefix)
    before = deepcopy(data)
    result = e.proof(data, digests, tracking)
    assert size == len(raw) and result['operations_admitted'] == 0 and result['qualification_added'] is False
    assert result['original_ui171_raw_journals_verified'] is True and result['both_owned_clients_stopped'] is True
    assert result['journal_proof']['post_stop_boundaries']['actual_SIGTERM_time_retained'] is False
    assert len(result['journal_proof']['post_stop_boundaries']['events']) == 2
    assert result['publication_code']['member_count'] == len(pause['committed_sources']) + 18
    assert result['current_batch_episode_count'] == 9 and result['current_batch_cases'] == 0
    assert result['qualified_fixture_operations'] == 453 and result['interaction_plan_operations'] == 916
    assert result['bags_swap_item_unqualified'] is True
    assert data == before


@pytest.mark.parametrize('fault', ['generic_bad_time', 'generic_foreign_actor', 'changed_current_prefix',
    'extra_owned_login', 'missing_ready_image', 'missing_closing_image', 'missing_ui171_image',
    'truncated_ui171_journal', 'missing_publication_source', 'wrong_publisher_epoch', 'false_qualification_total'])
def test_full_tar_refuses_unbound_history_images_and_generic_only_activity(tmp_path, monkeypatch, fault):
    store, pause = fixture(tmp_path, monkeypatch)
    receipt = next(v for v in store.data.values() if v.get('schema') == e.JOURNAL_SCHEMA)
    def member(ref): return str(Path(ref['path']).relative_to(store.root))
    if fault in ('generic_bad_time', 'generic_foreign_actor'):
        row = {'time': 'invalid' if fault == 'generic_bad_time' else pause['finished_at'] - .01,
            'session': 'unowned', 'account_id': 2, 'guid': 2, 'event': 'modern_authenticated'}
        store.files['tracking/events.jsonl'] += encoded(row) + b'\n'
    elif fault in ('changed_current_prefix', 'extra_owned_login'):
        path = member(receipt['journal_sources']['packets'])
        rows = deepcopy(store.raw_journals[path])
        if fault == 'changed_current_prefix':
            rows.pop(0)
        else:
            row = deepcopy(next(r for r in rows if r['name'] == 'CMSG_PLAYER_LOGIN'))
            row['time'] = pause['failed_history']['audit_until'] + .5
            rows.append(row)
        raw = b''.join(encoded(row) + b'\n' for row in rows)
        store.files[path], store.digests[path] = raw, hashlib.sha256(raw).hexdigest()
        refresh(store)
    elif fault == 'missing_ready_image':
        ready = store.get(pause['original_preparation_source'], False)
        store.files.pop(str(Path(member(pause['original_preparation_source'])).with_name(ready['frame']['file'])))
    elif fault == 'missing_closing_image': store.files.pop(member(pause['closing_frame_source']))
    elif fault in ('missing_ui171_image', 'truncated_ui171_journal'):
        mapping = next(v for v in store.data.values() if v.get('schema') == e.ANCESTRY_SCHEMA)
        if fault == 'missing_ui171_image':
            store.files.pop(next(r['copy_member'] for r in mapping['members'] if r['original_member'].endswith('.png')))
        else:
            row = mapping['journals'][0]
            lines = store.raw_journals[row['copy_member']]
            retained = [line for line in lines if line['time'] not in (1079, 1127)]
            assert [r for r in retained if 1080 <= r['time'] <= 1126] == [r for r in lines if 1080 <= r['time'] <= 1126]
            raw = b''.join(encoded(line) + b'\n' for line in retained)
            row.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
            store.files[row['copy_member']], store.digests[row['copy_member']] = raw, row['sha256']
            refresh(store)
    elif fault == 'missing_publication_source':
        epoch = receipt['code_source_epoch']
        index = next(i for i, ref in enumerate(epoch['committed_sources']) if ref['path'].endswith('/' + e.PUBLICATION_FILES[0]))
        epoch['committed_sources'].pop(index)
        epoch['carried_sources'].pop(index)
        refresh(store)
    raw, cp, prefix = archive(store.files, 'evidence/', code_commit='d' * 40 if fault == 'wrong_publisher_epoch' else 'e' * 40,
        metadata_changes={'qualified_fixture_operations': 454} if fault == 'false_qualification_total' else None)
    with pytest.raises(RuntimeError):
        data, digests, tracking, _ = reviewer.inspect_archive(io.BytesIO(raw), cp, prefix)
        e.proof(data, digests, tracking)


BASE = {'evidence/unit/pause/episode.json': b'{"phase":"fixture"}\n',
    'evidence/unit/pause/screen.png': b'\x89PNG\r\n\x1a\nfixture',
    'evidence/unit/journal/events.jsonl': b'{"time":1,"event":"fixture"}\n',
    'tracking/packets.jsonl': b'{"time":1,"name":"fixture"}\n',
    'tracking/events.jsonl': b'{"time":1,"event":"fixture"}\n'}


def test_stream_verifies_actual_whole_tracking_digest_and_metadata_manifest_relation():
    raw, cp, prefix = archive(BASE)
    data, digests, tracking, count = reviewer.inspect_archive(io.BytesIO(raw), cp, prefix)
    assert count == len(raw) and 'tracking/checkpoint.json' in data
    assert tracking['compressed_md5'] == hashlib.md5(raw).hexdigest()
    assert set(BASE) <= set(digests)


def test_stream_hashes_every_manifested_reference_json_outside_the_batch():
    files = {**BASE, 'reference/outside.json': b'{"value":1}'}
    raw, cp, prefix = archive(files)
    data, digests, _, _ = reviewer.inspect_archive(io.BytesIO(raw), cp, prefix)
    assert data['reference/outside.json'] == {'value': 1} and 'reference/outside.json' in digests
    raw, cp, prefix = archive(files, actual_overrides={'reference/outside.json': b'{"value":2}'})
    with pytest.raises(RuntimeError, match='manifest member SHA256'):
        reviewer.inspect_archive(io.BytesIO(raw), cp, prefix)


def test_stream_hashes_binary_log_and_all_generated_tracking_files():
    files = {**BASE, 'reference/code.bin': b'\x00\xff\x00\xff', 'reference/diagnostic.log': b'\xffdiagnostic',
        'tracking/owned_pet_abandon_packets.jsonl': b'', 'tracking/owned_tame_request_packets.jsonl': b'{"time":2}\n',
        'tracking/owned_entry_request_packets.jsonl': b'', 'tracking/live/metrics.json': b'{"closed_runs":9}',
        'tracking/live/params.yaml': b'controller: attributed_interaction_trials\n'}
    raw, cp, prefix = archive(files)
    data, digests, tracking, _ = reviewer.inspect_archive(io.BytesIO(raw), cp, prefix)
    assert set(files) <= set(digests) and tracking['raw_journals']['tracking/owned_entry_request_packets.jsonl'] == []
    assert data['tracking/live/metrics.json'] == {'closed_runs': 9}
    raw, cp, prefix = archive(files, actual_overrides={'reference/code.bin': b'\x00\xff\x00\x00'})
    with pytest.raises(RuntimeError, match='manifest member SHA256'):
        reviewer.inspect_archive(io.BytesIO(raw), cp, prefix)


@pytest.mark.parametrize('name', ['reference/unmanifested.json', 'tracking/owned_entry_request_packets.jsonl', 'tracking/live/params.yaml'])
def test_stream_refuses_unmanifested_global_json_and_any_generated_tracking_file(name):
    member, raw = tarfile.TarInfo(name), b'{}\n'
    member.size = len(raw)
    raw, cp, prefix = archive(BASE, extra=[(member, raw)])
    with pytest.raises(RuntimeError, match='unmanifested'):
        reviewer.inspect_archive(io.BytesIO(raw), cp, prefix)


@pytest.mark.parametrize('fault', ['missing', 'untyped_bytes'])
def test_stream_requires_honest_typed_unmodified_archived_metadata_manifest(fault):
    files = [] if fault == 'missing' else [{'path': name, 'bytes': float(len(raw)),
        'sha256': hashlib.sha256(raw).hexdigest()} for name, raw in BASE.items() if not name.startswith('tracking/')]
    raw, cp, prefix = archive(BASE, metadata_changes={'files': files})
    with pytest.raises(RuntimeError, match='actual archived metadata files'):
        reviewer.inspect_archive(io.BytesIO(raw), cp, prefix)


def test_remote_review_rejects_lexical_output_escape_before_reading_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(e, 'ROOT', tmp_path)
    with pytest.raises(RuntimeError, match='new ordinary private remote review'):
        reviewer.review(tmp_path / 'evidence/batch', tmp_path / 'evidence/../escaped_review.json')
    assert not (tmp_path / 'escaped_review.json').exists()


def metadata_fixture(tmp_path):
    raw = encoded(plan_fixture())
    member, episode = 'evidence/unit/code.json', 'evidence/unit/trial/episode.json'
    original = {'path': '/unit/repo/' + e.PLAN, 'sha256': hashlib.sha256(raw).hexdigest()}
    envelope = {'schema': s.CODE_SCHEMA, 'code_commit': 'e' * 40, 'original_path': original['path'],
        'raw_hex': raw.hex(), 'sha256': original['sha256'], 'bytes': len(raw)}
    ref = {'path': str(tmp_path / member), 'sha256': hashlib.sha256(encoded(envelope)).hexdigest()}
    run = {'completed': True, 'failure': None, 'started_at': 1, 'finished_at': 2, 'controller': 'code',
        'model': None, 'revision': None, 'cases': [], 'cleanup': [], 'qualification_added': False}
    store = e.Sources({member: envelope, episode: run}, {member: ref['sha256']}, root=tmp_path)
    value = {'code_commit': 'e' * 40, 'code_source_epoch': {'committed_sources': [original],
        'carried_sources': [ref]}}
    metadata = {'code_commit': value['code_commit'], 'runs': [{'path': episode,
        **{key: run[key] for key in ('completed', 'failure', 'controller', 'model', 'revision')}}],
        'counts': {}, 'qualified_fixture_operations': 453, 'interaction_plan_operations': 916}
    tracking = {'archived_metadata': metadata, 'batch_prefix': 'evidence/unit/', 'manifest': {episode: {}}}
    return store, value, tracking, run, envelope


def test_metadata_plan_and_dynamic_trial_projection_preserve_existing_qualification_total(tmp_path):
    store, value, tracking, _, _ = metadata_fixture(tmp_path)
    result = e._metadata(store, value, tracking)
    assert result == {'qualified_fixture_operations': 453, 'interaction_plan_operations': 916,
        'bags_swap_item_unqualified': True, 'current_batch_episode_count': 1, 'current_batch_cases': 0}


@pytest.mark.parametrize('fault', ['added_case', 'cleanup', 'qualification', 'boolean_operations', 'false_run',
    'missing_run', 'false_count', 'false_total', 'plan_swap_qualified', 'plan_case_count'])
def test_metadata_refuses_cases_false_aggregates_or_coedited_plan_qualification(tmp_path, fault):
    store, value, tracking, run, envelope = metadata_fixture(tmp_path)
    metadata = tracking['archived_metadata']
    if fault == 'added_case': run['cases'] = [{'id': 'bags.swap_item', 'status': 'pass'}]
    elif fault == 'cleanup': run['cleanup'] = [{}]
    elif fault == 'qualification': run['qualification_added'] = True
    elif fault == 'boolean_operations': run['operations_admitted'] = False
    elif fault == 'false_run': metadata['runs'][0]['completed'] = False
    elif fault == 'missing_run': metadata['runs'] = []
    elif fault == 'false_count': metadata['counts'] = {'pass': 1}
    elif fault == 'false_total': metadata['interaction_plan_operations'] = 917
    else:
        plan = plan_fixture()
        if fault == 'plan_case_count': plan['cases'].pop(0)
        else: plan['qualification_records'][0]['operations'][0] = 'bags.swap_item'
        raw = encoded(plan)
        envelope.update(raw_hex=raw.hex(), sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        copy = value['code_source_epoch']['carried_sources'][0]
        copy['sha256'] = hashlib.sha256(encoded(envelope)).hexdigest()
        store.digests[str(Path(copy['path']).relative_to(store.root))] = copy['sha256']
        value['code_source_epoch']['committed_sources'][0]['sha256'] = envelope['sha256']
    with pytest.raises(RuntimeError): e._metadata(store, value, tracking)


@pytest.mark.parametrize('fault', ['duplicate', 'noncanonical', 'symlink'])
def test_stream_rejects_unsafe_members_even_outside_the_selected_batch(fault):
    member = tarfile.TarInfo('tracking/events.jsonl' if fault == 'duplicate' else
        'unselected/../hidden' if fault == 'noncanonical' else 'unselected/link')
    raw = b'{}\n'
    if fault == 'symlink':
        member.type, member.linkname, raw = tarfile.SYMTYPE, 'target', None
    else: member.size = len(raw)
    raw, cp, prefix = archive(BASE, extra=[(member, raw)])
    with pytest.raises(RuntimeError): reviewer.inspect_archive(io.BytesIO(raw), cp, prefix)


@pytest.mark.parametrize('fault', ['missing', 'digest', 'tracking_digest', 'missing_tracking_manifest',
    'partial_jsonl', 'nonfinite_jsonl', 'declared_oversize', 'unmanifested', 'wrong_compressed_sha',
    'trailing_compressed', 'concatenated_gzip', 'hidden_tar_payload', 'gzip_crc', 'missing_tar_padding'])
def test_stream_refuses_incomplete_rehashed_or_hidden_archive_bytes(fault):
    files = dict(BASE)
    raw, cp, prefix = archive(files)
    if fault == 'digest': cp['file_manifest'][0]['sha256'] = '0' * 64
    elif fault == 'tracking_digest': next(r for r in cp['file_manifest'] if r['path'] == 'tracking/events.jsonl')['sha256'] = '0' * 64
    elif fault == 'missing_tracking_manifest': cp['file_manifest'] = [r for r in cp['file_manifest'] if r['path'] != 'tracking/events.jsonl']
    elif fault == 'missing':
        files.pop('evidence/unit/pause/screen.png')
        raw, _, _ = archive(files)
    elif fault in ('partial_jsonl', 'nonfinite_jsonl', 'unmanifested'):
        if fault == 'partial_jsonl': files['evidence/unit/journal/events.jsonl'] = b'{"time":1}'
        elif fault == 'nonfinite_jsonl': files['tracking/events.jsonl'] = b'{"time":NaN}\n'
        else: files['evidence/unit/unmanifested.json'] = b'{}'
        raw, current, _ = archive(files)
        if fault != 'unmanifested': cp = current
    elif fault == 'declared_oversize':
        next(row for row in cp['file_manifest'] if row['path'].endswith('/events.jsonl'))['bytes'] = reviewer.MAX_JOURNAL + 1
    elif fault == 'wrong_compressed_sha': cp['sha256'] = '0' * 64
    elif fault == 'trailing_compressed': raw += b'coherently-hashed-trailer'
    elif fault == 'concatenated_gzip': raw += gzip.compress(b'additional gzip member')
    elif fault == 'hidden_tar_payload': raw = gzip.compress(gzip.decompress(raw) + b'hidden-nonzero-member')
    elif fault == 'gzip_crc': raw = raw[:-8] + bytes([raw[-8] ^ 1]) + raw[-7:]
    elif fault == 'missing_tar_padding':
        expanded = gzip.decompress(raw).rstrip(b'\0')
        raw = gzip.compress(expanded)
    if fault != 'wrong_compressed_sha': cp.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    with pytest.raises(RuntimeError): reviewer.inspect_archive(io.BytesIO(raw), cp, prefix)


def test_pure_import_and_help_do_not_load_ui_sql_protobuf_or_publishers():
    code = '''
import sys,runpy
class Block:
 def find_spec(self,fullname,path=None,target=None):
  if fullname.startswith(('pymysql','google.protobuf','PIL','tools.client_compatibility.interaction_',
   'tools.client_compatibility.checkpoint_interactions','tools.client_compatibility.review_hunter_learn_checkpoint')):
   raise AssertionError('live dependency: '+fullname)
sys.meta_path.insert(0,Block())
sys.argv=['review_bag_swap_failed_checkpoint','--help']
runpy.run_module('tools.client_compatibility.review_bag_swap_failed_checkpoint',run_name='__main__')
'''
    subprocess.run([sys.executable, '-B', '-c', code], check=True, capture_output=True,
        cwd=Path(__file__).resolve().parents[4])
