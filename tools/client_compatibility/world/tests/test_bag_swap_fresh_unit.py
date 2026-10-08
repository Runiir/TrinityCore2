"""Fresh UI173 producers replay real startup bytes and the admitted UI172 ancestry.

The archive is synthetic and local: authority fixtures reconstruct both prior
proofs, while the startup fixture retains its exact immutable wire layout.
"""
from copy import deepcopy
import hashlib
import io
import json
import math
from pathlib import Path
import struct
import tarfile

import pytest

from tools.client_compatibility import bag_swap_contract as contract
from tools.client_compatibility import bag_swap_evidence as evidence
from tools.client_compatibility import bag_swap_login_sync as sync
from tools.client_compatibility import bag_swap_failed_sources as failed_sources
from tools.client_compatibility import bag_swap_failed_evidence as failed_evidence
from tools.client_compatibility import checkpoint_bag_swap as publication
from tools.client_compatibility import review_bag_swap_checkpoint as reviewer
from tools.client_compatibility.world.buffer import Reader, Writer
from tools.client_compatibility.world.native_objects import guid, movement, records, values
from tools.client_compatibility.world.tests.test_bag_swap_contract import resources
from tools.client_compatibility.world.tests.test_bag_swap_login_sync import fresh_login, packet
from tools.client_compatibility.world.tests.test_bag_swap_fresh_sources import fixture as fresh_authority
from tools.client_compatibility.world.tests.test_bag_swap_full_unit import complete_fixture, rebound_current_receipts


def native_rest_word(raw, threshold):
    """Preserve all record/movement bytes and every present field except login rest."""
    reader = Reader(raw)
    map_id, count = reader.unpack('HI')
    assert map_id == 0 and 0 < count <= 10000 and type(threshold) is int and 0 <= threshold < 300
    writer, patched = Writer().pack('HI', map_id, count), 0
    original = records(raw)
    for _ in range(count):
        begin = reader.pos
        kind, = reader.unpack('B')
        if kind == 3:
            number, = reader.unpack('I')
            assert number <= 10000
            for _ in range(number):
                guid(reader)
            writer.raw(raw[begin:reader.pos])
            continue
        identity = guid(reader)
        if kind in (1, 2):
            reader.unpack('B')
            movement(reader)
        reader.align()
        value_start = reader.pos
        mask_count = raw[value_start]
        fields = values(reader)
        if identity == 2 and kind in (1, 2):
            assert contract.INDEX['PLAYER_REST_STATE_EXPERIENCE'] in fields
            fields[contract.INDEX['PLAYER_REST_STATE_EXPERIENCE']] = threshold
            patched += 1
        writer.raw(raw[begin:value_start]).pack('B', mask_count)
        for index in range(mask_count):
            writer.pack('I', sum(1 << (field % 32) for field in fields if field // 32 == index))
        for field in sorted(fields):
            writer.pack('I', fields[field])
    reader.end()
    rebuilt = writer.finish()
    expected = deepcopy(original)
    for record in expected:
        if record.get('guid') == 2 and record['update_type'] in (1, 2):
            record['fields'][contract.INDEX['PLAYER_REST_STATE_EXPERIENCE']] = threshold
    assert patched == 1 and records(rebuilt) == expected
    return rebuilt


def boot_builder(baseline, exact_after, verify_second, since, until):
    value = fresh_login()
    delta = verify_second - math.floor(packet(value, 'SMSG_LOGIN_VERIFY_WORLD', 'from_native')['time'])
    names = {value['session']: 'scout', 'fresh-physical-instance': 'physical'}
    for row in [*value['rows'], *value['events']]:
        row['session'] = names.get(row['session'], row['session'])
        row['time'] += delta
    value.update(session='scout', since=since, until=until)
    creation = next(row for row in value['rows'] if row['name'] == 'SMSG_UPDATE_OBJECT' and
        row['direction'] == 'from_native' and any(record.get('guid') == 2 and
            record['update_type'] in (1, 2) for record in records(bytes.fromhex(row['body']))))
    creation['body'] = native_rest_word(bytes.fromhex(creation['body']), int(exact_after)).hex()
    # Full entry metadata retains every wire row, plus the exact drop and effect
    # events. Matching boot rows keep their actual metadata byte counts/order.
    for row in value['rows']:
        physical = 'scout' if row['direction'] in ('to_native', 'from_native') or row['name'] in (
            'CMSG_PLAYER_LOGIN', 'SMSG_LOGOUT_COMPLETE') else 'physical'
        if any(event.get('session') == physical and event.get('name') == row['name'] and
            event.get('direction') == row['direction'] and event.get('bytes') == len(bytes.fromhex(row['body'])) and
            0 <= row['time'] - event['time'] < .1 for event in value['events']):
            continue
        value['events'].append({'event': 'native_packet' if row['direction'] in ('to_native', 'from_native') else 'modern_packet',
            'session': physical, 'time': row['time'] - .01, 'name': row['name'],
            'direction': row['direction'], 'bytes': len(bytes.fromhex(row['body']))})
    value['events'].sort(key=lambda row: row['time'])
    result = sync.login_sync(*(value[key] for key in ('rows', 'events', 'session', 'since', 'until', 'baseline_pose')))
    value.update(proof=result, login_packets=result['login_packets'])
    native = resources()
    native['money'] = baseline['2']['native']['money']
    for row in baseline['2']['inventory']:
        item = {'guid': (0x4000 << 48) | row[3], 'id': row[5], 'count': row[9]}
        assert row[1] == 0 and 0 <= row[2] < 39
        target, index = (native['equipment'], row[2]) if row[2] < 19 else (native['backpack'], row[2] - 23)
        assert 0 <= index < len(target)
        target[index] = item
    return value, native


def code_epoch_builder(old, repo, write):
    source_root = Path(__file__).resolve().parents[4]
    members = sorted({str(Path(row['path']).relative_to(repo)) for row in old['closure']['committed_sources']} |
        set(failed_evidence.PUBLICATION_FILES) | set(failed_evidence.PUBLICATION_DEPENDENCIES) |
        set(publication.FRESH_CODE_FILES))
    originals, carried = [], []
    for index, member in enumerate(members):
        raw = (source_root / member).read_bytes()
        path = repo / member
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        original = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
        originals.append(original)
        carried.append(write('current_code/member_%03d.json' % index, {
            'schema': failed_sources.CODE_SCHEMA, 'code_commit': 'd' * 40, 'original_path': str(path),
            'sha256': original['sha256'], 'bytes': len(raw), 'raw_hex': raw.hex()}))
    ref = write('current_code/epoch.json', {'schema': publication.CURRENT_CODE_SCHEMA, 'code_commit': 'd' * 40,
        'committed_sources': originals, 'carried_sources': carried})
    return originals, ref


def fixture(tmp_path, monkeypatch):
    authority = fresh_authority(tmp_path, monkeypatch)
    return complete_fixture(tmp_path, monkeypatch, authority=authority,
        boot_builder=boot_builder, code_epoch_builder=code_epoch_builder)


@pytest.fixture(scope='module')
def complete_fresh(tmp_path_factory):
    # Each negative rebinds an independent deep copy of the admitted sources.
    # Keep the expensive immutable parent graph once per focused test module.
    with pytest.MonkeyPatch.context() as patch:
        yield fixture(tmp_path_factory.mktemp('fresh_full_unit'), patch)


def archive(files, prefix):
    rows = [{'path': member, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        for member, raw in sorted(files.items()) if not member.startswith('tracking/')]
    files = dict(files)
    files['tracking/checkpoint.json'] = (json.dumps({'schema': 'client442_interaction_checkpoint_v1',
        'files': rows}, indent=2) + '\n').encode()
    manifest = [{'path': member, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        for member, raw in sorted(files.items())]
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as output:
        # Source receipts precede tracking so collect() can attribute the window.
        for member, raw in sorted(files.items(), key=lambda pair: (pair[0].startswith('tracking/'), pair[0])):
            info = tarfile.TarInfo(member)
            info.size = len(raw)
            output.addfile(info, io.BytesIO(raw))
    raw = stream.getvalue()
    return raw, {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'file_manifest': manifest}, prefix


def test_fresh_boot_full_lifecycle_and_complete_serialized_tar_prove_the_same_closed_swap(complete_fresh):
    data, digests, tracking, files, lifecycle, prefix = complete_fresh
    expected = evidence.proof(data, digests, tracking)
    entry = data[prefix + 'entry/episode.json']
    assert len(entry['raw_entry_packets']) == 921
    assert entry['login_sync']['instance_session'] == 'physical'
    assert entry['login_sync']['initialization']['clock'] == 710000
    assert entry['native_owner_proof']['rest_threshold'] >= 53
    assert expected['native_swap_pairs'] == lifecycle['native_swap_pairs'] == 2
    assert expected['shutdown_checks'] == 8 and expected['both_owned_clients_stopped']
    assert expected['all_item_instance_fields_unchanged'] and expected['actual_packet_journals_verified']
    raw, checkpoint, _ = archive(files, prefix)
    archived, hashes, actual, count = reviewer.inspect_archive(io.BytesIO(raw), checkpoint, prefix)
    assert count == len(raw)
    assert evidence.proof(archived, hashes, actual) == expected


@pytest.mark.parametrize('fault', ['missing_boot', 'foreign_instance', 'changed_native_body', 'extra_qualification',
    'restored_cursor', 'missing_stop_check', 'changed_current_code'])
def test_fresh_full_portable_proof_rejects_rebound_source_and_lifecycle_drift(complete_fresh, fault):
    data, digests, tracking, files, _, prefix = complete_fresh
    def mutate(changed):
        entry = changed[prefix + 'entry/episode.json']
        if fault == 'missing_boot': entry.pop('login_sync')
        elif fault == 'foreign_instance':
            next(row for row in entry['raw_entry_events'] if row['event'] == 'instance_authenticated')['session'] = 'foreign'
        elif fault == 'changed_native_body':
            next(row for row in entry['raw_entry_packets'] if row['name'] == 'MSG_MOVE_HEARTBEAT')['body'] += '00'
        elif fault == 'extra_qualification': changed[prefix + 'forward/episode.json']['qualification_added'] = True
        elif fault == 'restored_cursor': changed[prefix + 'operation/episode.json']['state']['cursor_info'] = ['item', 6948]
        elif fault == 'missing_stop_check': changed[prefix + 'final/episode.json']['shutdown_checks'].popitem()
        else: changed[prefix + 'current_code/member_000.json']['raw_hex'] += '00'
    changed, hashes, actual, _ = rebound_current_receipts(data, digests, tracking, files, prefix, mutate)
    with pytest.raises(RuntimeError):
        evidence.proof(changed, hashes, actual)


def test_all_current_source_labels_cannot_reuse_the_admitted_parent_publication_epoch(complete_fresh):
    data, digests, tracking, files, _, prefix = complete_fresh
    ready = data[prefix + 'ready/episode.json']
    store = evidence.Sources(data, digests)
    old_commit = store.get(ready['predecessor']['remote'], False)['proof']['publication_code']['code_commit']
    assert old_commit != ready['code_commit']
    def mutate(changed):
        envelopes = []
        for member, value in changed.items():
            if member.startswith(prefix) and value.get('code_commit') == ready['code_commit']:
                value['code_commit'] = old_commit
                if value.get('schema') == failed_sources.CODE_SCHEMA:
                    envelopes.append(value)
        assert len(envelopes) == len(ready['committed_sources']) == 89
    changed, hashes, actual, _ = rebound_current_receipts(data, digests, tracking, files, prefix, mutate)
    with pytest.raises(RuntimeError, match='distinct publication epoch'):
        evidence.proof(changed, hashes, actual)
