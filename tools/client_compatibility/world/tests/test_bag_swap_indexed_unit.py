"""Future entry policy and complete event context at controller boundaries."""
from copy import deepcopy
import json

import pytest

from tools.client_compatibility import interaction_bag_swap_continuation as continuation
from tools.client_compatibility import interaction_bag_swap as operation
from tools.client_compatibility import bag_swap_contract as contract
from tools.client_compatibility import bag_swap_login_sync as historical
from tools.client_compatibility import bag_swap_login_sync_v2 as current
from tools.client_compatibility import bag_swap_indexed_sources as provider
from tools.client_compatibility.world.tests.test_bag_swap_login_sync import fresh_login


def entry_fixture():
    value = fresh_login()
    keys = ('rows', 'events', 'session', 'since', 'until', 'baseline_pose')
    boot = current.login_sync(*(value[k] for k in keys))
    native = dict(zip(('position_x', 'position_y', 'position_z', 'orientation'), value['baseline_pose']))
    entry = {'login_sync': boot, 'native_before_entry': native, 'native_session': value['session'],
        'started_at': value['since'], 'finished_at': value['until']}
    return value, entry


def ready(tmp_path, monkeypatch):
    path = tmp_path / 'evidence/runtime.json'
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({'schema': provider.RUNTIME_SCHEMA}) + '\n')
    monkeypatch.setattr(continuation.lab, 'ROOT', tmp_path)
    read = continuation.sources().private_json
    monkeypatch.setattr(continuation.sources(), 'private_json', lambda path, successful=True:
        read(path, successful, root=tmp_path))
    return {'runtime_authority_source': continuation.sources().bound(path)}


def test_indexed_provider_requires_v2_and_unknown_authority_cannot_select_classifier(tmp_path, monkeypatch):
    selected = ready(tmp_path, monkeypatch)
    assert continuation.fresh_authority(selected) is True
    assert continuation.login_sync_schema(selected) == current.SCHEMA
    assert continuation.authority_sources(provider.RUNTIME_SCHEMA) is provider
    with pytest.raises(RuntimeError): continuation.authority_sources('unknown')
    with pytest.raises(RuntimeError): continuation.login_sync_provider('unknown')


def test_indexed_complete_entry_rederivation_and_serialization_keep_v2(tmp_path, monkeypatch):
    value, entry = entry_fixture()
    entry['login_sync'] = json.loads(json.dumps(entry['login_sync']))
    actual = continuation.entry_settlement(entry, value['rows'], value['events'], required=True,
        required_schema=continuation.login_sync_schema(ready(tmp_path, monkeypatch)))
    assert actual['schema'] == current.SCHEMA
    assert actual == entry['login_sync']
    contract.native_replay(value['rows'], value['session'], value['since'], value['until'],
        login_sync=actual, events=value['events'])


@pytest.mark.parametrize('fault', ['missing', 'genuine_v1', 'unknown', 'omitted_context'])
def test_source_bound_future_entry_cannot_downgrade_or_drop_request_context(tmp_path, monkeypatch, fault):
    value, entry = entry_fixture()
    if fault == 'missing': entry.pop('login_sync')
    elif fault == 'genuine_v1':
        entry['login_sync'] = historical.login_sync(*(value[k] for k in
            ('rows', 'events', 'session', 'since', 'until', 'baseline_pose')))
    elif fault == 'unknown': entry['login_sync']['schema'] = 'unrecognized'
    else:
        target = next(e for e in entry['login_sync']['source_events'] if e.get('event') == 'modern_packet' and
            e.get('direction') == 'from_client')
        entry['login_sync']['source_events'].remove(target)
    with pytest.raises(RuntimeError):
        continuation.entry_settlement(entry, value['rows'], value['events'], required=True,
            required_schema=continuation.login_sync_schema(ready(tmp_path, monkeypatch)))


def test_complete_event_ingress_rejects_serialized_proof_with_new_interleaved_request():
    value, entry = entry_fixture()
    effect = next(e for e in value['events'] if e.get('event') == 'movement_forwarded')
    request = next(r for r in value['rows'] if r.get('name') == effect.get('name') and r.get('direction') == 'from_client')
    inserted = {'event': 'modern_packet', 'session': entry['login_sync']['instance_session'],
        'name': 'CMSG_SERVER_TIME_OFFSET_REQUEST', 'direction': 'from_client', 'bytes': 0,
        'time': (request['time'] + effect['time']) / 2}
    actual_events = sorted([*value['events'], inserted], key=lambda r: r['time'])
    with pytest.raises(RuntimeError):
        contract.native_replay(value['rows'], value['session'], value['since'], value['until'],
            login_sync=entry['login_sync'], events=actual_events)


def test_bag_guard_forwards_complete_unfiltered_events_to_native_replay(monkeypatch):
    value, entry = entry_fixture()
    events = [*value['events'], {'event': 'unrelated', 'session': 'other', 'time': value['since'] + .01}]
    monkeypatch.setattr(operation, 'linked', lambda path: entry)
    monkeypatch.setattr(operation, 'packets', lambda *a: value['rows'])
    monkeypatch.setattr(continuation, 'history_events', lambda *a: events)
    entry['native_owner_proof'] = {'rest_threshold': 0}
    seen = []
    def native(*args, **kwargs):
        seen.append(kwargs['events'])
        return {'packets': []}
    monkeypatch.setattr(contract, 'native_replay', native)
    operation.guard({'entry_source': {'path': 'entry'}}, value['session'], value['until'])
    assert seen == [events]
    assert seen[0] is events


def test_bootless_historical_controller_replay_keeps_metadata_unsupplied(tmp_path, monkeypatch):
    from tools.client_compatibility.world.tests.test_bag_swap_evidence import fixture
    _, _, _, current_receipts, _, wire, _ = fixture(tmp_path, monkeypatch)
    _, entry, _, _, _, _ = current_receipts
    assert entry.get('login_sync') is None
    monkeypatch.setattr(operation, 'linked', lambda path: entry)
    monkeypatch.setattr(operation, 'packets', lambda *args: wire)
    monkeypatch.setattr(continuation, 'history_events', lambda *args: pytest.fail('historical proofless replay has no classifier'))
    assert operation.guard({'entry_source': {'path': 'entry'}}, 'scout', 1103.2)
    ordered = continuation.logout_packets(wire, 'scout', 1103, 1103.3)
    continuation.whole_logout_history(wire, entry, 'scout', ordered, required_schema=historical.SCHEMA)
    with pytest.raises(RuntimeError, match='exact stationary login settlement'):
        continuation.whole_logout_history(wire, entry, 'scout', ordered, required_schema=current.SCHEMA)


@pytest.mark.parametrize('consumer', ['fresh_authority', 'login_sync_schema', 'source_report', 'live_evidence'])
def test_all_live_runtime_schema_ingress_enforces_raw_cap_before_decode(tmp_path, monkeypatch, consumer):
    from tools.client_compatibility import bag_swap_evidence as evidence
    from tools.client_compatibility import review_bag_swap_failed_checkpoint as reader
    path = tmp_path / 'evidence/runtime_authority.json'
    path.parent.mkdir()
    with path.open('wb') as handle:
        handle.write(b'{}')
        handle.truncate(continuation.sources().MAX_RUNTIME_BYTES + 1)
    monkeypatch.setattr(continuation.lab, 'ROOT', tmp_path)
    monkeypatch.setattr(reader, '_json', lambda *a: pytest.fail('oversized runtime must fail before JSON decode'))
    ref = {'path': str(path), 'sha256': 'a' * 64}
    selected = {'runtime_authority_source': ref,
        'authority_source': {'path': str(tmp_path / 'evidence/authority.json'), 'sha256': 'b' * 64}}
    with pytest.raises(RuntimeError, match='one-MiB raw byte bound before decode'):
        if consumer == 'live_evidence':
            class Unread:
                local = True
                def get(self, *args): pytest.fail('live compact must be bounded before store.get')
            evidence.predecessor(Unread(), selected, live=True)
        else: getattr(continuation, consumer)(selected)


def test_changed_runtime_source_cannot_select_v2_after_ready_hash(tmp_path, monkeypatch):
    selected = ready(tmp_path, monkeypatch)
    (tmp_path / 'evidence/runtime.json').write_text('{"schema":"client442_bag_swap_fresh_runtime_authority_v1"}\n')
    with pytest.raises(RuntimeError): continuation.login_sync_schema(selected)


def test_indexed_start_pin_cap_precedes_decode_admission_and_launch(tmp_path, monkeypatch):
    from tools.client_compatibility import review_bag_swap_failed_checkpoint as reader
    pins = tmp_path / 'evidence/ui174_pins.json'
    pins.parent.mkdir()
    with pins.open('wb') as handle:
        handle.write(b'{}')
        handle.truncate(provider.MAX_DESCRIPTOR_BYTES + 1)
    monkeypatch.setattr(provider, 'ROOT', tmp_path)
    monkeypatch.setattr(continuation, 'available_memory_kib', lambda: 12 * 1024 * 1024)
    monkeypatch.setattr(continuation.sources(), 'private_json', lambda *a, **k:
        pytest.fail('indexed start must not first parse a historical closure or unbounded pin file'))
    monkeypatch.setattr(reader, '_json', lambda *a: pytest.fail('oversized pins must fail before decode'))
    monkeypatch.setattr(provider, 'source_bundle', lambda *a, **k: pytest.fail('oversized pins cannot admit'))
    monkeypatch.setattr(continuation, 'launch', lambda: pytest.fail('oversized pins cannot launch'))
    with pytest.raises(RuntimeError, match='exact byte cap'):
        continuation.start(tmp_path / 'evidence/ui174/resume', tmp_path / 'evidence/ui174/start',
            tmp_path / 'evidence/closure.json', tmp_path / 'evidence/remote.json',
            tmp_path / 'evidence/checkpoint.json', indexed_pins=pins)
    assert not (tmp_path / 'evidence/ui174').exists()


def test_historical_classifier_module_remains_v1_and_replay_default_is_valid():
    value = fresh_login()
    proof = historical.login_sync(*(value[k] for k in ('rows', 'events', 'session', 'since', 'until', 'baseline_pose')))
    assert proof['schema'] == 'client442_bag_swap_login_sync_v1'
    assert contract.native_replay(value['rows'], value['session'], value['since'], value['until'],
        login_sync=proof)['owner'] == 2


@pytest.mark.parametrize('fault', ['monitor', 'fresh_client', 'private_input'])
def test_indexed_start_preserves_final_physical_monitor_and_fresh_client_guards(tmp_path, monkeypatch, fault):
    from tools.client_compatibility.world.tests.test_bag_swap_continuation import initialized_start
    _, old, _, state, writes, _, start, _ = initialized_start(tmp_path, monkeypatch)
    if fault == 'fresh_client':
        monkeypatch.setattr(continuation, 'runtime', lambda: old['runtime'])
    else:
        monkeypatch.setattr(continuation, 'focus', lambda: {'second_monitor_verified': fault != 'monitor',
            'monitor': {'name': 'DP-1' if fault == 'monitor' else 'HDMI-1'},
            'input_isolation': {'actor': 'primary' if fault == 'private_input' else 'scout',
                'host_activation_sent': False}})
    with pytest.raises(RuntimeError, match='fresh scout HDMI-1'): start()
    assert state['launches'] == 1 and writes[-1]['completed'] is False and writes[-1]['installed'] is False


@pytest.mark.parametrize('name', ['batch.json', 'native_server_before.json'])
def test_original_batch_caps_are_enforced_before_decode_or_admission(tmp_path, monkeypatch, name):
    from tools.client_compatibility.world.tests.test_bag_swap_continuation import initialized_start
    from tools.client_compatibility import review_bag_swap_failed_checkpoint as reader
    batch, _, calls, state, _, _, start, _ = initialized_start(tmp_path, monkeypatch)
    with (batch / name).open('wb') as handle:
        handle.write(b'{}')
        handle.truncate(provider.MAX_RUNTIME_BYTES + 1)
    decoded = []
    original = reader._json
    monkeypatch.setattr(reader, '_json', lambda raw: decoded.append(len(raw)) or original(raw))
    with pytest.raises(RuntimeError, match='exact byte cap'): start()
    assert provider.MAX_RUNTIME_BYTES + 1 not in decoded
    assert 'parent_stream' not in calls and state['launches'] == 0


def test_runtime_shared_reader_detects_changes_made_during_decode(tmp_path, monkeypatch):
    from tools.client_compatibility import review_bag_swap_failed_checkpoint as reader
    selected = ready(tmp_path, monkeypatch)
    path = tmp_path / 'evidence/runtime.json'
    original = reader._json
    def replace(raw):
        value = original(raw)
        path.write_text(path.read_text() + ' ')
        return value
    monkeypatch.setattr(reader, '_json', replace)
    with pytest.raises(RuntimeError, match='changed while parsing'):
        continuation.read_runtime_authority(selected['runtime_authority_source'])
