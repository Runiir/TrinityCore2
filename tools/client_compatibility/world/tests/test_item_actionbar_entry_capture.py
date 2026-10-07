"""Fresh capture and explicit repair authority; only mocked or temporary inputs."""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from tools.client_compatibility import interaction_item_actionbar_entry_capture as cap
from tools.client_compatibility import interaction_item_actionbar as op
from tools.client_compatibility import item_actionbar_contract as c
from tools.client_compatibility import item_actionbar_evidence as e
from tools.client_compatibility import item_actionbar_preservation as p
from tools.client_compatibility import item_actionbar_sources as s
from tools.client_compatibility.world.tests.test_item_actionbar_evidence import fixture as full_fixture


def repair_fixture(tmp_path, monkeypatch):
    batch, paths, values, wire, events = full_fixture(tmp_path, monkeypatch)
    ready, entry, base = values['ready'], values['entry'], deepcopy(values['recon']['baseline'])
    ref = lambda name: s.bound(paths[name])
    raw_png = (paths['entry'].parent / 'screen.png').read_bytes()

    def write(name, value, review=False):
        path = batch / name / ('review.json' if review else 'episode.json')
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + '\n')
        paths[name], values[name] = path, value
        return s.bound(path)

    def frame(name):
        image = batch / name / 'screen.png'
        image.parent.mkdir(exist_ok=True)
        image.write_bytes(raw_png)
        return {**deepcopy(entry['frame']), 'file': 'screen.png'}

    def trial(name, phase, start, finish, commit='b' * 40, **fields):
        value = deepcopy(entry)
        for key in ('login_packets', 'owner_packets', 'native_owner_proof', 'native_before_entry',
                'entered_native', 'all_offline_snapshot', 'native_original'):
            value.pop(key, None)
        value.update({'phase': phase, 'started_at': start, 'finished_at': finish, 'code_commit': commit,
            'completed': True, 'failure': None, 'frame': frame(name), 'entry_source': ref('entry'),
            'fixture_source': ref('ready'), 'preparation_source': ref('ready'), 'baseline': deepcopy(base), **fields})
        return value

    protected = dict.fromkeys(cap.PROTECTED_CHECKS, True)
    old_review = {'reviewed': True, 'control': 'MainMenuBarBackpackButton', 'source': ref('entry'),
        'frame': entry['frame'], 'fixture_source_sha256': ref('ready')['sha256'],
        'point': [1210, 690], 'pickup_point_inside_button': True}
    review_ref = write('failed_backpack_review', old_review, True)
    frame('failed_backpack_review')
    failed = trial('failed_recon', None, 1101.01, 1101.05, commit=entry['code_commit'],
        input_sent=True, completed=False, failure='RuntimeError: actionbars diagnostic did not become visible',
        backpack_open_review=review_ref, backpack_open_input={'kind': 'click', 'value': old_review['point']},
        backpack_geometry={'exact_pixels': True, 'reviewed_frame': entry['frame']})
    failed['raw_stage_failure'] = {'saved': base['saved'], 'resources': base['resources'],
        'native_state': base['native_state'], 'state': {**deepcopy(entry['state']), 'bags': [0]},
        'frame': failed['frame'], 'input_replayed': False, 'errors': {'public': failed['failure']}}
    failed_ref = write('failed_recon', failed)
    recovery = trial('recovery', 'item_actionbar_restored', 1101.06, 1101.10, commit='a' * 40,
        source=failed_ref, first_failure_source=failed_ref, first_failure=failed['failure'],
        pre_recon_recovery=True, recovery_only=True, failed_whole_excluded=True,
        gameplay_input_replayed=False, drag_input_sent=False, clear_input_sent=False,
        after_saved=base['saved'], after_resources=base['resources'], after_native_state=base['native_state'],
        protected_checks=protected, layout_restoration_checks=dict.fromkeys(cap.LAYOUT_CHECKS, True),
        actionbar_restored=True, placement_absent=True, bag_close_input_sent=True,
        bag_close_input={'kind': 'key', 'value': 'Escape'}, input_sent=True,
        pre_recon_no_mutation_proof={'native_action_requests': 0})
    recovery['restored_frame'] = recovery['frame']
    recovery['pre_recon_idle_observation'] = {'native_before_observation': base['native_state'],
        'original': base['native_state'], 'state': failed['raw_stage_failure']['state'], 'frame': recovery['frame'],
        'mismatch_observed': False, 'qualification_added': False}
    escape_path = paths['entry'].parent / 'item_actionbar_pre_recon_escape_attempt.json'
    escape = {'schema': 'client442_item_actionbar_pre_recon_consumed_input_v1', 'kind': 'escape',
        'created_at': 1101.065, 'entry_source': ref('entry'), 'preparation_source': ref('ready'),
        'first_failure_source': failed_ref, 'actor': entry['actor'], 'runtime': entry['runtime'], 'native_session': 'scout',
        'operation_output': str(batch / 'recovery/episode.json'), 'input_intent': {'kind': 'key', 'value': 'Escape'},
        'input_replay_allowed': False}
    escape_path.write_text(json.dumps(escape))
    recovery['escape_attempt_source'] = s.bound(escape_path)
    recovery_ref = write('recovery', recovery)
    source_refs, code_bytes = [], []
    for name in cap.MODULES:
        raw = ('synthetic reviewed code for ' + name).encode()
        source = {'path': str(op.lab.REPO / 'tools/client_compatibility' / name),
            'sha256': hashlib.sha256(raw).hexdigest()}
        source_refs.append(source)
        code_bytes.append({**source, 'raw_hex': raw.hex()})
    raw = b'local observer_version=146; passive source fixture'
    observer = {'path': str(op.lab.REPO / 'tools/client_compatibility/observation/addon/ClientMovementHarness/ClientInteractions.lua'),
        'sha256': hashlib.sha256(raw).hexdigest()}
    source_refs.append(observer)
    code_bytes.append({**observer, 'raw_hex': raw.hex()})
    files = {'ClientInteractions.lua': observer['sha256']}
    transition = {'previous_code_commit': entry['code_commit'], 'restoration_code_commit': recovery['code_commit'],
        'code_commit': 'b' * 40, 'entry_source': ref('entry'), 'first_failure_source': failed_ref,
        'restoration_source': recovery_ref, 'committed_sources': source_refs}
    reload = trial('observer_reload', cap.RELOAD_PHASE, 1101.11, 1101.15,
        source=recovery_ref, restoration_source=recovery_ref, first_failure_source=failed_ref,
        recovery_only=True, failed_whole_excluded=True, gameplay_input_replayed=False,
        drag_input_sent=False, clear_input_sent=False, after_saved=base['saved'], after_resources=base['resources'],
        after_native_state=base['native_state'], after_public=entry['public'],
        after_state={**deepcopy(entry['state']), 'observer_version': 146},
        protected_checks=protected, layout_restoration_checks=dict.fromkeys(cap.LAYOUT_CHECKS, True),
        previous_code_commit=entry['code_commit'], restoration_code_commit=recovery['code_commit'],
        repair_code_transition=transition, committed_sources=source_refs,
        observer_deployment={'version': 146, 'source': files, 'installed': files,
            'code_commit': 'b' * 40, 'committed_sources': source_refs,
            'installer_source': source_refs[-2], 'load_on': 'ordinary /reload'},
        parked_observer_installation={'version': 146, 'before': {'ClientInteractions.lua': 'f' * 64},
            'after': files, 'source': files, 'input_sent': False, 'load_on': 'next ordinary owned class entry'})
    reload['after_frame'] = reload['frame']
    reload['reload_intent'] = {'kind': 'chat', 'value': '/reload'}
    reload['ordinary_inputs'] = [{'input': reload['reload_intent'], 'started_at': 1101.12, 'finished_at': 1101.13,
        'input_sent': True, 'input_replayed': False}]
    reload_path = paths['recovery'].parent / 'item_actionbar_observer_reload_attempt.json'
    reload_attempt = {'schema': 'client442_item_actionbar_observer_reload_attempt_v1', 'consumed': True,
        'input_replay_allowed': False, 'created_at': 1101.115, 'input': reload['reload_intent'],
        'restoration_source': recovery_ref, 'entry_source': ref('entry'), 'first_failure_source': failed_ref,
        'code_commit': reload['code_commit'], 'actor': entry['actor'], 'runtime': entry['runtime'], 'native_session': 'scout',
        'operation_output': str(batch / 'observer_reload/episode.json')}
    reload_path.write_text(json.dumps(reload_attempt))
    reload['reload_attempt_source'] = s.bound(reload_path)
    reload_ref = write('observer_reload', reload)
    refs = {'preparation': ref('ready'), 'entry': ref('entry'), 'failed': failed_ref,
        'recovery': recovery_ref, 'reload': reload_ref}
    now = deepcopy(ready['all_offline_snapshot'])
    now['2']['native']['online'] = 1
    packets = [row for row in wire if entry['started_at'] <= row['time'] <= 1101.20]
    replay = c.native_replay(packets, entry['native_session'], entry['started_at'], 1101.20,
        rest_threshold=entry['native_owner_proof']['rest_threshold'])
    captured = trial('entry_screen', cap.PHASE, 1101.16, 1101.20, source=reload_ref,
        first_failure_source=failed_ref, pre_recon_recovery_source=recovery_ref, observer_reload_source=reload_ref,
        repair_code_transition=transition, committed_sources=source_refs, code_source_bytes=code_bytes,
        housekeeping_attempts=[{'source': recovery['escape_attempt_source'], 'value': escape},
            {'source': reload['reload_attempt_source'], 'value': reload_attempt}],
        native_state=base['native_state'], saved=entry['saved'], resources=entry['resources'],
        public=entry['public'], active_spec=entry['active_spec'], state=reload['after_state'],
        all_online_snapshot=now, online_preservation=p.online_preservation(ready['all_offline_snapshot'], now),
        protected_checks=protected, capture_packets=packets, native_owner_proof=replay, owner_packets=replay['packets'])
    write('entry_screen', captured)
    return batch, paths, values, wire, events, refs


def test_fresh_capture_pure_chain_preserves_original_login_times_bytes_and_distinct_truthful_commits(tmp_path, monkeypatch):
    _, paths, values, _, _, refs = repair_fixture(tmp_path, monkeypatch)
    original = paths['entry'].read_bytes()
    transition = cap.validate_capture(values['entry_screen'], values['ready'], values['entry'],
        values['failed_recon'], values['recovery'], values['observer_reload'], refs)
    assert transition['previous_code_commit'] == 'd' * 40
    assert transition['restoration_code_commit'] == 'a' * 40 and transition['code_commit'] == 'b' * 40
    assert (values['entry']['started_at'], values['entry']['finished_at']) == (1099, 1101)
    assert values['entry_screen']['started_at'] > values['entry']['finished_at']
    assert paths['entry'].read_bytes() == original


@pytest.mark.parametrize('fault', ['entry_timestamp', 'old_code', 'cleanup_flag', 'reload_flag', 'failed_success',
    'failed_raw_count', 'cursor', 'bags', 'observer', 'rest', 'health', 'peer_pet', 'slot', 'source_bytes',
    'installed', 'deployment_code', 'deployment_sources', 'raw_install_label', 'transition', 'extra_login', 'prior_action', 'foreign_controller'])
def test_fresh_capture_rejects_unbound_or_mutated_housekeeping_and_protected_state(tmp_path, monkeypatch, fault):
    _, _, v, _, _, refs = repair_fixture(tmp_path, monkeypatch)
    value = v['entry_screen']
    if fault == 'entry_timestamp': v['entry']['finished_at'] = 1101.18
    elif fault == 'old_code': value['code_commit'] = 'd' * 40
    elif fault == 'cleanup_flag': v['recovery']['failed_whole_excluded'] = False
    elif fault == 'reload_flag': v['observer_reload']['recovery_only'] = False
    elif fault == 'failed_success': v['failed_recon']['completed'] = True
    elif fault == 'failed_raw_count': v['failed_recon']['raw_stage_failure']['resources']['backpack'][0]['count'] = 2
    elif fault == 'cursor': value['state']['cursor_info'] = ['item', 6948]
    elif fault == 'bags': value['state']['bags'] = [0]
    elif fault == 'observer': value['state']['observer_version'] = 145
    elif fault == 'rest': value['state']['xp_exhaustion'] += 2
    elif fault == 'health': value['all_online_snapshot']['2']['native']['health'] = 59
    elif fault == 'peer_pet': value['all_online_snapshot']['6']['pets'][0]['curhealth'] += 1
    elif fault == 'slot': value['public']['actions'][0]['slot'] += 1
    elif fault == 'source_bytes': value['code_source_bytes'][0]['raw_hex'] += '00'
    elif fault == 'installed': v['observer_reload']['observer_deployment']['installed'] = {'ClientInteractions.lua': 'f' * 64}
    elif fault == 'deployment_code': v['observer_reload']['observer_deployment']['code_commit'] = 'a' * 40
    elif fault == 'deployment_sources': v['observer_reload']['observer_deployment']['committed_sources'] = []
    elif fault == 'raw_install_label': v['observer_reload']['parked_observer_installation']['load_on'] = 'ordinary /reload'
    elif fault == 'transition': value['repair_code_transition']['restoration_code_commit'] = 'c' * 40
    elif fault == 'extra_login': value['capture_packets'].append(deepcopy(value['capture_packets'][0]))
    elif fault == 'prior_action': value['capture_packets'].append({'session': 'scout', 'time': 1101.1, 'name': c.ACTION})
    else: v['recovery']['controller'] = 'laya'
    with pytest.raises((RuntimeError, KeyError)):
        cap.validate_capture(value, v['ready'], v['entry'], v['failed_recon'], v['recovery'], v['observer_reload'], refs)


@pytest.mark.parametrize('kind,shape', [('drag', 'complete'), ('drag', 'partial'), ('clear', 'complete'), ('clear', 'symlink')])
def test_fresh_capture_marker_is_consumed_even_when_partial_or_dangling(tmp_path, monkeypatch, kind, shape):
    _, paths, _, _, _, refs = repair_fixture(tmp_path, monkeypatch)
    # Existing full_fixture intentionally contains later successful markers.
    for name in ('drag', 'clear'):
        (paths['entry'].parent / ('item_actionbar_' + name + '_attempt.json')).unlink()
    marker = paths['entry'].parent / ('item_actionbar_' + kind + '_attempt.json')
    if shape == 'symlink': marker.symlink_to(marker.parent / 'absent.json')
    else: marker.write_text('{"consumed":true}' if shape == 'complete' else '{')
    with pytest.raises(RuntimeError, match='consumed'):
        cap.unconsumed(refs['entry'])


class Trial:
    def __init__(self, output, value):
        self.out, self.fixture = output, value['actor']
        self.receipt = {k: deepcopy(value[k]) for k in ('actor', 'runtime', 'code_commit', 'controller', 'model',
            'revision', 'custom_script_permission', 'softTargetInteract')}
        self.receipt.update(started_at=1101.16, completed=False, failure=None, cases=[])
        self.persisted, self.inputs = [], []
    def persist(self): self.persisted.append(deepcopy(self.receipt))
    def execute(self, action): self.inputs.append(action); raise AssertionError('capture submitted input')


def runtime(tmp_path, monkeypatch):
    _, paths, v, _, _, refs = repair_fixture(tmp_path, monkeypatch)
    for name in ('drag', 'clear'):
        (paths['entry'].parent / ('item_actionbar_' + name + '_attempt.json')).unlink()
    trial = Trial(tmp_path, v['entry_screen'])
    base = v['failed_recon']['baseline']
    monkeypatch.setattr(op, 'context', lambda *a: (v['ready'], 'scout'))
    monkeypatch.setattr(op, 'entry_source', lambda *a: deepcopy(v['entry']))
    monkeypatch.setattr(cap, 'verify_current_sources', lambda *a: deepcopy(v['entry_screen']['code_source_bytes']))
    monkeypatch.setattr(op, 'assert_live', lambda *a, **k: (base['saved'], base['resources'], base['native_state'],
        deepcopy(v['entry_screen']['protected_checks']), deepcopy(v['entry_screen']['state']), deepcopy(v['entry_screen']['frame'])))
    monkeypatch.setattr(op, 'detail', lambda *a: deepcopy(v['entry']['public']))
    monkeypatch.setattr(op, 'snapshot', lambda: deepcopy(v['entry_screen']['all_online_snapshot']))
    monkeypatch.setattr(op, 'packet_rows', lambda *a: deepcopy(v['entry_screen']['capture_packets']))
    monkeypatch.setattr(cap.time, 'time', lambda: 1101.20)
    return trial, paths, v, refs


def test_runtime_capture_never_inputs_and_keeps_original_entry_bytes(tmp_path, monkeypatch):
    t, paths, v, _ = runtime(tmp_path, monkeypatch)
    original = paths['entry'].read_bytes()
    cap.run(t, paths['ready'], paths['entry'], paths['recovery'], paths['observer_reload'])
    assert t.receipt['completed'] is True and t.receipt['phase'] == cap.PHASE
    assert t.inputs == [] and paths['entry'].read_bytes() == original
    assert t.receipt['entry_source'] == s.bound(paths['entry'])
    assert t.receipt['capture_packets'] == v['entry_screen']['capture_packets']


def test_baseexception_capture_retains_failure_facts_without_rewriting_sources(tmp_path, monkeypatch):
    t, paths, _, _ = runtime(tmp_path, monkeypatch)
    old = {name: path.read_bytes() for name, path in paths.items()}
    def interrupt(*a, **k): raise KeyboardInterrupt('capture interrupted')
    monkeypatch.setattr(op, 'assert_live', interrupt)
    monkeypatch.setattr(op, 'retain_raw', lambda trial, *a: trial.receipt.update(raw_entry_capture_failure={'interrupted': True}))
    with pytest.raises(KeyboardInterrupt): cap.run(t, paths['ready'], paths['entry'], paths['recovery'], paths['observer_reload'])
    assert t.receipt['completed'] is False and 'KeyboardInterrupt' in t.receipt['failure']
    assert t.receipt['raw_entry_capture_failure'] == {'interrupted': True} and t.inputs == []
    assert all(path.read_bytes() == old[name] for name, path in paths.items())


def test_capture_import_stays_lazy_without_auth_or_protobuf():
    before = set(sys.modules)
    importlib.reload(cap)
    assert not any(n.startswith(('google.protobuf', 'tools.client_compatibility.auth')) for n in set(sys.modules) - before)


def test_cli_records_exact_code_identity_even_when_trial_serializes_diagnostic_alias(tmp_path, monkeypatch):
    @contextmanager
    def actor(name): assert name == 'scout'; yield
    instance = SimpleNamespace(receipt={'controller': 'code_diagnostic_ordinary_inputs'})
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.interaction_social', SimpleNamespace(actor=actor))
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.interaction_trial', SimpleNamespace(Trial=lambda *a, **k: instance))
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.interaction_owned_class_fixture', SimpleNamespace(SCRIPT_BOUNDARY=e.SCRIPT_BOUNDARY))
    monkeypatch.setattr(cap, 'run', lambda trial, *a: None)
    monkeypatch.setattr(sys, 'argv', ['entry_capture', *[arg for name in
        ('preparation', 'entry', 'recovery', 'observer-reload', 'output') for arg in ('--' + name, str(tmp_path / name))]])
    cap.main()
    assert instance.receipt['controller'] == 'code' and instance.receipt['input_sent'] is False


@pytest.mark.parametrize('fault', [None, 'source_hash', 'working_bytes', 'commit', 'retained_bytes'])
def test_cleanup_git_object_isolation_pins_original_reviewed_bytes(monkeypatch, fault):
    raw = b'exact original cleanup operation fixture'
    digest = hashlib.sha256(raw).hexdigest()
    monkeypatch.setattr(cap, 'ISOLATED_OPERATION_SHA', digest)
    source = {'path': str(op.lab.REPO / 'tools/client_compatibility/interaction_item_actionbar.py'), 'sha256': digest}
    recovery = {'code_commit': 'a' * 40, 'runtime_source_isolation': {
        'code_commit': 'a' * 40, 'operation_source': source,
        'loaded_from': 'git_object_bytes', 'working_candidate_inputs_used': False}}
    retained = {**source, 'raw_hex': raw.hex()}
    calls = []
    def read_git(args, **kwargs):
        calls.append((args, kwargs))
        return raw
    monkeypatch.setattr(cap.subprocess, 'check_output', read_git)
    if fault == 'source_hash': recovery['runtime_source_isolation']['operation_source']['sha256'] = 'c' * 64
    elif fault == 'working_bytes': recovery['runtime_source_isolation']['working_candidate_inputs_used'] = True
    elif fault == 'commit': recovery['runtime_source_isolation']['code_commit'] = 'b' * 40
    elif fault == 'retained_bytes': retained['raw_hex'] = b'borrowed later operation'.hex()
    if fault:
        with pytest.raises(RuntimeError): cap.restoration_runtime_source(recovery, retained)
        assert calls == []
    else:
        assert cap.restoration_runtime_source(recovery) == retained
        assert calls[0][0] == ['git', 'show', 'a' * 40 + ':tools/client_compatibility/interaction_item_actionbar.py']
        assert cap.restoration_runtime_source(recovery, retained) == retained
        assert len(calls) == 1
