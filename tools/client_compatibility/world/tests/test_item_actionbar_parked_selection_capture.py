"""Mocked proof-code transition and fresh parked selection; no live surfaces."""
from copy import deepcopy
from contextlib import contextmanager
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools.client_compatibility import interaction_item_actionbar_parked_selection_capture as cap
from tools.client_compatibility import interaction_item_actionbar_continuation as continuation
from tools.client_compatibility import item_actionbar_sources as sources
from tools.client_compatibility.world.tests.test_item_actionbar_evidence import repaired_fixture


def fixture(tmp_path, monkeypatch):
    """Explicit synthetic proof-only D, preserving the completed runtime C chain."""
    batch, paths, values, wire, events = repaired_fixture(tmp_path, monkeypatch, renewed=True, cursor_value={})
    ref = lambda name: sources.bound(paths[name])
    screen = values['entry_screen']
    refs = {name: ref(key) for name, key in [('preparation', 'ready'), ('park', 'park'),
        ('after_precision', 'after_precision'), ('operation', 'operation'), ('entry_screen', 'entry_screen')]}
    failed = deepcopy(values['final'])
    failed.update(completed=False, failure='RuntimeError: actual observed item icon and empty action destination review differs',
        started_at=1121.2, finished_at=1121.4, phase=None, code_commit='c' * 40,
        input_sent=False, mutation_sent=False, qualification_added=False, stop_attempted=False)
    for key in ('game_before', 'stop_finished_at', 'shutdown_checks', 'action', 'proof', 'frame', 'sources'):
        failed.pop(key, None)
    failed_path = batch / 'failed_close/episode.json'
    failed_path.parent.mkdir()
    failed_path.write_text(json.dumps(failed, indent=2) + '\n')
    paths['failed_close'], values['failed_close'] = failed_path, failed
    refs['failed_close'] = ref('failed_close')
    changes = []
    existing = {row['path']: row for row in screen['code_source_bytes']}
    new_names = {'interaction_item_actionbar_parked_selection_capture.py', 'test_item_actionbar_parked_selection_capture.py'}
    for relative in cap.PROOF_FILES:
        path = Path(relative)
        if not path.is_absolute(): path = continuation.lab.REPO / path
        path = str(path)
        old = None if Path(path).name in new_names else bytes.fromhex(existing[path]['raw_hex']) \
            if path in existing else ('synthetic committed C proof bytes: ' + path).encode()
        raw = ('synthetic reviewed D proof bytes: ' + path).encode()
        changes.append({'path': path, 'before_sha256': None if old is None else hashlib.sha256(old).hexdigest(),
            'before_raw_hex': None if old is None else old.hex(), 'sha256': hashlib.sha256(raw).hexdigest(),
            'raw_hex': raw.hex()})
    transition = {'schema': 'client442_item_actionbar_pure_proof_code_transition_v1',
        'runtime_code_commit': 'c' * 40, 'code_commit': 'f' * 40, 'park_source': refs['park'],
        'precision_source': refs['after_precision'], 'operation_source': refs['operation'],
        'entry_screen_source': refs['entry_screen'], 'preparation_source': refs['preparation'],
        'failed_close_source': refs['failed_close'], 'read_only': True, 'gameplay_input_replayed': False,
        'source_changes': changes, 'changed_paths': sorted(cap.PROOF_FILES),
        'unchanged_runtime_sources': [row for row in screen['committed_sources'] if
            Path(row['path']).name != 'item_actionbar_evidence.py']}
    out = batch / 'parked_selection'
    out.mkdir()
    raw_png = (paths['park'].parent / values['park']['frame']['file']).read_bytes()
    (out / 'parked_selection.png').write_bytes(raw_png)
    value = {key: deepcopy(values['final'][key]) for key in ('schema', 'actor', 'runtime', 'controller', 'model',
        'revision', 'custom_script_permission', 'softTargetInteract')}
    value.update(phase=cap.PHASE, code_commit='f' * 40, started_at=1122, finished_at=1123,
        completed=True, failure=None, native_session='scout', source=refs['park'], park_source=refs['park'],
        preparation_source=refs['preparation'], precision_source=refs['after_precision'],
        operation_source=refs['operation'], entry_screen_source=refs['entry_screen'],
        failed_close_source=refs['failed_close'], all_offline_snapshot=deepcopy(values['park']['all_offline_snapshot']),
        frame={**deepcopy(values['park']['frame']), 'file': 'parked_selection.png'},
        proof_code_transition=transition, input_sent=False, mutation_sent=False, qualification_added=False,
        stop_attempted=False, cases=[], cleanup=[], observer_only=True, read_only=True,
        requires_fresh_selection_review=True)
    path = out / 'episode.json'
    path.write_text(json.dumps(value, indent=2) + '\n')
    paths['parked_selection'], values['parked_selection'] = path, value
    return batch, paths, values, wire, events, refs


def validate(values, refs):
    return cap.validate_capture(values['parked_selection'], values['ready'], values['park'], values['after_precision'],
        values['operation'], values['entry_screen'], values['failed_close'], refs)


def test_proof_only_d_capture_preserves_all_runtime_c_bytes_and_original_entry(tmp_path, monkeypatch):
    _, paths, values, _, _, refs = fixture(tmp_path, monkeypatch)
    original = {name: path.read_bytes() for name, path in paths.items() if name != 'parked_selection'}
    validate(values, refs)
    assert values['parked_selection']['code_commit'] == 'f' * 40
    assert all(values[name]['code_commit'] == 'c' * 40 for name in ('operation', 'park', 'after_precision', 'entry_screen'))
    assert values['entry']['code_commit'] == 'd' * 40
    assert values['failed_close']['completed'] is False and values['failed_close']['stop_attempted'] is False
    assert all(path.read_bytes() == original[name] for name, path in paths.items() if name in original)


@pytest.mark.parametrize('field,replacement', [('game_pid', 22), ('display', ':3'), ('window_id', 37748738)])
def test_pure_capture_cannot_borrow_another_game_child_display_or_window(tmp_path, monkeypatch, field, replacement):
    _, _, values, _, _, refs = fixture(tmp_path, monkeypatch)
    validate(values, refs)
    values['parked_selection']['frame']['monitor']['input_isolation'][field] = replacement
    with pytest.raises(RuntimeError, match='original game PID, private display and window'):
        validate(values, refs)


@pytest.mark.parametrize('fault', ['missing_transition', 'runtime_commit', 'closure_commit', 'park_ref', 'precision_ref',
    'operation_ref', 'screen_ref', 'old_evidence_bytes', 'new_bytes', 'new_hash', 'new_before', 'missing_change',
    'runtime_path', 'changed_paths', 'changed_runtime', 'readonly', 'replay', 'capture_code', 'capture_source',
    'precision_source', 'entry_screen_source', 'failed_close_source', 'failed_completed', 'failed_stop',
    'failed_input', 'snapshot', 'protected_actor', 'input', 'mutation', 'qualification', 'stop', 'review', 'controller'])
def test_parked_capture_rejects_unbound_code_sources_or_mutated_runtime_and_inputs(tmp_path, monkeypatch, fault):
    _, _, v, _, _, refs = fixture(tmp_path, monkeypatch)
    validate(v, refs)
    value, transition = v['parked_selection'], v['parked_selection']['proof_code_transition']
    if fault == 'missing_transition': value.pop('proof_code_transition')
    elif fault == 'runtime_commit': transition['runtime_code_commit'] = 'b' * 40
    elif fault == 'closure_commit': transition['code_commit'] = 'a' * 40
    elif fault.endswith('_ref'): transition[{'park_ref': 'park_source', 'precision_ref': 'precision_source',
        'operation_ref': 'operation_source', 'screen_ref': 'entry_screen_source'}[fault]] = refs['failed_close']
    elif fault == 'old_evidence_bytes':
        row = next(row for row in transition['source_changes'] if Path(row['path']).name == 'item_actionbar_evidence.py')
        old = b'borrowed old C bytes'
        row.update(before_raw_hex=old.hex(), before_sha256=hashlib.sha256(old).hexdigest())
    elif fault == 'new_bytes': transition['source_changes'][0]['raw_hex'] += '00'
    elif fault == 'new_hash': transition['source_changes'][0]['sha256'] = 'a' * 64
    elif fault == 'new_before':
        row = next(row for row in transition['source_changes'] if Path(row['path']).name == 'interaction_item_actionbar_parked_selection_capture.py')
        row.update(before_raw_hex='00', before_sha256=hashlib.sha256(b'\0').hexdigest())
    elif fault == 'missing_change': transition['source_changes'].pop()
    elif fault == 'runtime_path': transition['source_changes'][0]['path'] = str(
        continuation.lab.REPO / 'tools/client_compatibility/interaction_item_actionbar.py')
    elif fault == 'changed_paths': transition['changed_paths'].pop()
    elif fault == 'changed_runtime': transition['unchanged_runtime_sources'][0] = {**transition['unchanged_runtime_sources'][0], 'sha256': 'a' * 64}
    elif fault == 'readonly': transition['read_only'] = False
    elif fault == 'replay': transition['gameplay_input_replayed'] = True
    elif fault == 'capture_code': value['code_commit'] = 'c' * 40
    elif fault == 'capture_source': value['source'] = refs['after_precision']
    elif fault == 'precision_source': value['precision_source'] = refs['park']
    elif fault == 'entry_screen_source': value['entry_screen_source'] = refs['operation']
    elif fault == 'failed_close_source': value['failed_close_source'] = refs['park']
    elif fault == 'failed_completed': v['failed_close']['completed'] = True
    elif fault == 'failed_stop': v['failed_close']['stop_attempted'] = True
    elif fault == 'failed_input': v['failed_close']['input_sent'] = True
    elif fault == 'snapshot': value['all_offline_snapshot']['2']['native']['health'] = 59
    elif fault == 'protected_actor': value['all_offline_snapshot']['6']['pets'][0]['curhealth'] += 1
    elif fault == 'review': value['requires_fresh_selection_review'] = False
    elif fault == 'controller': value['controller'] = 'laya'
    else: value[{'input': 'input_sent', 'mutation': 'mutation_sent', 'qualification': 'qualification_added', 'stop': 'stop_attempted'}[fault]] = True
    with pytest.raises((RuntimeError, KeyError)):
        validate(v, refs)


class Trial:
    def __init__(self, out, source):
        self.out, self.fixture = out, deepcopy(source['actor'])
        self.receipt = {key: deepcopy(source[key]) for key in ('actor', 'runtime', 'controller', 'code_commit', 'model',
            'revision', 'custom_script_permission', 'softTargetInteract')}
        self.receipt.update(started_at=1122, completed=False, failure=None, cases=[], cleanup=[])
        self.persisted, self.inputs = [], []
    def persist(self): self.persisted.append(deepcopy(self.receipt))
    def execute(self, action): self.inputs.append(action); raise AssertionError('parked capture attempted input')


def runtime_fixture(tmp_path, monkeypatch):
    batch, paths, values, wire, events, refs = fixture(tmp_path, monkeypatch)
    out = batch / 'producer_capture'
    out.mkdir()
    t = Trial(out, values['parked_selection'])
    frames = []
    def shot(path):
        frames.append(Path(path))
        raw = (paths['parked_selection'].parent / values['parked_selection']['frame']['file']).read_bytes()
        Path(path).write_bytes(raw)
        return {**deepcopy(values['parked_selection']['frame']), 'file': Path(path).name}
    monkeypatch.setattr(continuation, 'registration', lambda: deepcopy(t.fixture))
    monkeypatch.setattr(continuation, 'runtime', lambda: deepcopy(t.receipt['runtime']))
    monkeypatch.setattr(continuation, 'snapshot', lambda: deepcopy(values['park']['all_offline_snapshot']))
    monkeypatch.setattr(continuation, 'focus', lambda: deepcopy(values['park']['frame']['monitor']))
    monkeypatch.setattr(continuation, 'shot', shot)
    monkeypatch.setattr(continuation, 'primary_stopped', lambda _: {'after': values['park']['all_offline_snapshot']['1']})
    monkeypatch.setattr(continuation.lab, 'stop', lambda _: (_ for _ in ()).throw(AssertionError('capture attempted stop')))
    monkeypatch.setattr(cap, 'proof_transition', lambda *_: deepcopy(values['parked_selection']['proof_code_transition']))
    monkeypatch.setattr(cap.time, 'time', lambda: 1123)
    return t, paths, values, refs, frames


def test_runtime_capture_observes_one_fresh_frame_without_input_stop_or_source_rewrites(tmp_path, monkeypatch):
    t, paths, values, refs, frames = runtime_fixture(tmp_path, monkeypatch)
    original = {name: path.read_bytes() for name, path in paths.items()}
    cap.run(t, paths['ready'], paths['park'], paths['after_precision'], paths['failed_close'])
    assert t.receipt['completed'] is True and t.receipt['phase'] == cap.PHASE
    assert t.receipt['requires_fresh_selection_review'] is True and t.receipt['input_sent'] is False
    assert t.receipt['stop_attempted'] is False and not t.inputs and len(frames) == 1
    assert t.receipt['proof_code_transition']['runtime_code_commit'] == 'c' * 40
    assert t.receipt['code_commit'] == 'f' * 40 and t.receipt['source'] == refs['park']
    assert all(path.read_bytes() == original[name] for name, path in paths.items())


@pytest.mark.parametrize('when', ['before_capture', 'after_capture'])
@pytest.mark.parametrize('field,replacement', [('game_pid', 22), ('display', ':3'), ('window_id', 37748738)])
def test_runtime_capture_refuses_changed_original_game_child_before_or_after_its_fresh_shot(
        tmp_path, monkeypatch, when, field, replacement):
    t, paths, values, _, frames = runtime_fixture(tmp_path, monkeypatch)
    original = {name: path.read_bytes() for name, path in paths.items()}
    focus_calls = []
    def focus():
        monitor = deepcopy(values['park']['frame']['monitor'])
        focus_calls.append(monitor)
        if when == 'before_capture' or len(focus_calls) == 2:
            monitor['input_isolation'][field] = replacement
        return monitor
    monkeypatch.setattr(continuation, 'focus', focus)
    cap.run(t, paths['ready'], paths['park'], paths['after_precision'], paths['failed_close'])
    assert t.receipt['completed'] is False and 'original game PID, private display and window' in t.receipt['failure']
    assert not t.inputs and t.receipt.get('stop_attempted', False) is False
    assert len(focus_calls) == (1 if when == 'before_capture' else 2)
    assert len(frames) == (0 if when == 'before_capture' else 1)
    if when == 'after_capture': assert (t.out / t.receipt['frame']['file']).is_file()
    assert all(path.read_bytes() == original[name] for name, path in paths.items())


@pytest.mark.parametrize('failure', [KeyboardInterrupt, SystemExit, RuntimeError])
def test_runtime_capture_seals_fresh_observation_failure_without_inputs_or_rewriting_sources(tmp_path, monkeypatch, failure):
    t, paths, _, _, frames = runtime_fixture(tmp_path, monkeypatch)
    original = {name: path.read_bytes() for name, path in paths.items()}
    def lost(_): raise failure('fresh parked frame interrupted')
    monkeypatch.setattr(continuation, 'shot', lost)
    if failure is RuntimeError:
        cap.run(t, paths['ready'], paths['park'], paths['after_precision'], paths['failed_close'])
    else:
        with pytest.raises(failure): cap.run(t, paths['ready'], paths['park'], paths['after_precision'], paths['failed_close'])
    assert t.receipt['completed'] is False and t.receipt['failure'] == failure.__name__ + ': fresh parked frame interrupted'
    assert t.receipt['finished_at'] == 1123 and not t.inputs
    assert all(path.read_bytes() == original[name] for name, path in paths.items())


@pytest.mark.parametrize('fault', ['offline_snapshot', 'proof_source'])
def test_runtime_capture_retains_its_fresh_frame_when_a_later_read_only_recheck_fails(tmp_path, monkeypatch, fault):
    t, paths, values, _, frames = runtime_fixture(tmp_path, monkeypatch)
    original = {name: path.read_bytes() for name, path in paths.items()}
    observed = continuation.shot
    def shot(path):
        frame = observed(path)
        if fault == 'offline_snapshot':
            changed = deepcopy(values['park']['all_offline_snapshot'])
            changed['2']['native']['health'] = 59
            monkeypatch.setattr(continuation, 'snapshot', lambda: changed)
        else:
            changed = deepcopy(values['parked_selection']['proof_code_transition'])
            changed['source_changes'][0]['sha256'] = 'a' * 64
            monkeypatch.setattr(cap, 'proof_transition', lambda *_: changed)
        return frame
    monkeypatch.setattr(continuation, 'shot', shot)
    cap.run(t, paths['ready'], paths['park'], paths['after_precision'], paths['failed_close'])
    assert t.receipt['completed'] is False and t.receipt['failure']
    assert len(frames) == 1 and not t.inputs and t.receipt['stop_attempted'] is False
    assert (t.out / t.receipt['frame']['file']).is_file()
    assert any(row.get('frame') == t.receipt['frame'] for row in t.persisted)
    assert all(path.read_bytes() == original[name] for name, path in paths.items())


def test_capture_module_import_does_not_load_ui_auth_pillow_or_protocol_dependencies():
    code = """import importlib,sys
class Block:
 def find_spec(self,name,path=None,target=None):
  if name.startswith(('PIL','google','Crypto','tools.second_client','tools.client_compatibility.auth','tools.client_compatibility.interaction_trial','tools.client_compatibility.world.control')): raise RuntimeError(name)
sys.meta_path.insert(0,Block())
importlib.import_module('tools.client_compatibility.interaction_item_actionbar_parked_selection_capture')
print('pure parked selection import passed')
"""
    result = subprocess.run([sys.executable, '-B', '-c', code], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'pure parked selection import passed'


def test_cli_help_does_not_load_runtime_dependencies():
    code = """import runpy,sys
class Block:
 def find_spec(self,name,path=None,target=None):
  if name.startswith(('PIL','google','Crypto','tools.second_client','tools.client_compatibility.auth','tools.client_compatibility.interaction_trial','tools.client_compatibility.interaction_owned_class_fixture','tools.client_compatibility.interaction_item_actionbar_continuation','tools.client_compatibility.world.control')): raise RuntimeError(name)
sys.meta_path.insert(0,Block())
sys.argv=['parked_selection_capture','--help']
runpy.run_module('tools.client_compatibility.interaction_item_actionbar_parked_selection_capture',run_name='__main__')
"""
    result = subprocess.run([sys.executable, '-B', '-c', code], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert '--failed-close' in result.stdout and '--after-precision' in result.stdout


def test_cli_keeps_truthful_code_controller_and_never_claims_input_before_read_only_capture(tmp_path, monkeypatch):
    @contextmanager
    def scout(): yield
    calls = []
    instance = SimpleNamespace(receipt={'controller': 'code_diagnostic_ordinary_inputs', 'code_commit': 'f' * 40})
    monkeypatch.setattr(continuation, 'scout', scout)
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.interaction_trial', SimpleNamespace(Trial=lambda *_a, **_k: instance))
    boundary = {'custom': 'blocked'}
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.interaction_owned_class_fixture', SimpleNamespace(SCRIPT_BOUNDARY=boundary))
    monkeypatch.setattr(cap, 'run', lambda *args: calls.append(args))
    names = ('preparation', 'park', 'after-precision', 'failed-close', 'output')
    monkeypatch.setattr(sys, 'argv', ['parked_capture', *[arg for name in names for arg in ('--' + name, str(tmp_path / name))]])
    cap.main()
    assert len(calls) == 1 and calls[0][0] is instance
    assert instance.receipt['controller'] == 'code' and instance.receipt['code_commit'] == 'f' * 40
    assert all(instance.receipt[key] is False for key in ('input_sent', 'mutation_sent', 'qualification_added', 'stop_attempted'))


def git_fixture(tmp_path, monkeypatch):
    """The generator sees explicit mocked C/D Git objects and temporary D files."""
    _, paths, values, _, _, refs = fixture(tmp_path, monkeypatch)
    transition = values['parked_selection']['proof_code_transition']
    objects = {}
    for row in transition['source_changes']:
        path = Path(row['path'])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(bytes.fromhex(row['raw_hex']))
        relative = str(path.relative_to(cap.lab.REPO))
        objects['f' * 40 + ':' + relative] = bytes.fromhex(row['raw_hex'])
        if row['before_raw_hex'] is not None:
            objects['c' * 40 + ':' + relative] = bytes.fromhex(row['before_raw_hex'])
    for row in values['entry_screen']['code_source_bytes']:
        if Path(row['path']).name == 'item_actionbar_evidence.py': continue
        path = Path(row['path'])
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = bytes.fromhex(row['raw_hex'])
        path.write_bytes(raw)
        relative = str(path.relative_to(cap.lab.REPO))
        for commit in ('c' * 40, 'f' * 40): objects[commit + ':' + relative] = raw
    settings = {'head': 'f' * 40, 'changed': list(cap.PROOF_FILES), 'new_exists': False}
    calls = []
    def check_output(command, **kwargs):
        calls.append(command)
        assert kwargs.get('cwd') == cap.lab.REPO
        if command == ['git', 'rev-parse', 'HEAD']: return settings['head'] + '\n'
        if command[:3] == ['git', 'diff', '--name-only']: return '\n'.join(settings['changed']) + '\n'
        if command[:2] == ['git', 'show']: return objects[command[2]]
        raise AssertionError('unexpected mocked Git command: ' + repr(command))
    def run(command, **kwargs):
        calls.append(command)
        assert command[:3] == ['git', 'cat-file', '-e'] and kwargs.get('cwd') == cap.lab.REPO
        return SimpleNamespace(returncode=0 if settings['new_exists'] else 1)
    monkeypatch.setattr(cap.subprocess, 'check_output', check_output)
    monkeypatch.setattr(cap.subprocess, 'run', run)
    trial = Trial(paths['parked_selection'].parent, values['parked_selection'])
    return trial, values, refs, transition, objects, settings, calls


@pytest.mark.parametrize('fault', [None, 'head_identity', 'runtime_changed', 'working_bytes', 'new_existed',
    'runtime_git_bytes', 'runtime_working_bytes'])
def test_proof_transition_generator_admits_only_committed_proof_files_and_unchanged_c_runtime(tmp_path, monkeypatch, fault):
    t, values, refs, expected, objects, settings, calls = git_fixture(tmp_path, monkeypatch)
    runtime_ref = expected['unchanged_runtime_sources'][0]
    if fault == 'head_identity': settings['head'] = 'b' * 40
    elif fault == 'runtime_changed': settings['changed'].append('tools/client_compatibility/interaction_item_actionbar.py')
    elif fault == 'working_bytes': Path(expected['source_changes'][0]['path']).write_bytes(b'uncommitted D source')
    elif fault == 'new_existed': settings['new_exists'] = True
    elif fault == 'runtime_git_bytes':
        relative = str(Path(runtime_ref['path']).relative_to(cap.lab.REPO))
        objects['f' * 40 + ':' + relative] = b'changed runtime D bytes'
    elif fault == 'runtime_working_bytes': Path(runtime_ref['path']).write_bytes(b'dirty C runtime implementation')
    call = lambda: cap.proof_transition(t, refs, values['park'], values['after_precision'], values['entry_screen'])
    if fault:
        with pytest.raises(RuntimeError): call()
    else:
        assert call() == expected and not t.inputs
        assert any(command[:3] == ['git', 'cat-file', '-e'] for command in calls)
