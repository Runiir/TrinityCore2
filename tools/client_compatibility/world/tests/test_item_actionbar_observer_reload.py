"""Ordinary observer reload guards without a client, SQL, install or subprocess."""
from copy import deepcopy
from contextlib import nullcontext
import importlib
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

import pytest

from tools.client_compatibility import interaction_item_actionbar_observer_reload as reload
from tools.client_compatibility.world.buffer import Writer, player_high

OLD, CLEANUP, CURRENT = '1' * 40, '2' * 40, '3' * 40
ACTOR = {'guid': 2, 'account_id': 2, 'character_name': 'Harnesstwo', 'race': 1, 'class': 1, 'level': 1}
RUNTIME = {name: {'pid': number, 'start_ticks': str(number)}
    for name, number in (('client', 2), ('modern_world', 3), ('worldserver', 4))}


def login_rows():
    native = struct.pack('<i4f', 0, 1, 2, 3, 0)
    modern = Writer().guid(2, player_high()).pack('f', 1000).finish()
    return [{'session': 'owned', 'time': 3.1 + n * .1, 'name': name, 'direction': direction, 'body': raw.hex()}
        for n, (name, direction, raw) in enumerate((('CMSG_PLAYER_LOGIN', 'from_client', modern),
            ('CMSG_PLAYER_LOGIN', 'to_native', bytes.fromhex('2003')),
            ('SMSG_LOGIN_VERIFY_WORLD', 'from_native', native), ('SMSG_LOGIN_VERIFY_WORLD', 'to_client', native + bytes(4))))]


@pytest.fixture
def scene(tmp_path, monkeypatch):
    op = reload.op
    monkeypatch.setattr(op.lab, 'ROOT', tmp_path)
    monkeypatch.setattr(op.lab, 'REPO', tmp_path / 'repo')
    before_native = {'pose': {'stand': 0, 'sheath': 0}, 'afk': False, 'selection': 0,
        'health': 60, 'max_health': 60, 'power': 0, 'xp': 0, 'next_xp': 400, 'summon': 0}
    state = {'player': 'Harnesstwo', 'level': 1, 'world_position': [1, 2, 3, 0],
        'target': {'exists': False, 'guid': None, 'name': None}, 'bags': [], 'panels': [], 'cursor_info': [],
        'spell_targeting': False, 'pending_glyph': False, 'chat_edit_open': False, 'lua_errors': [], 'blocked_actions': []}
    public = {'active_spec': 1, 'page': 1, 'effective_page': 1, 'bonus_offset': 0,
        'viewport': {'width': 1280, 'height': 720}, 'frames': {'MainMenuBar': True},
        'keys': {'SITORSTAND': ['X']}, 'actions': [{'button': 'ActionButton' + str(i), 'slot': i,
            'kind': '', 'id': 0, 'visible': False} for i in range(1, 13)]}
    base = {'saved': {'actions': [], 'spells': [], 'quests': []}, 'resources': {'money': 0, 'backpack': []},
        'native_state': before_native, 'state': state, 'public': public, 'active_spec': 0, 'snapshot': {}}
    protected = {name: True for name in ('protected_1', 'protected_3', 'protected_4', 'protected_5',
        'protected_6', 'owner_inventory', 'owner_pets', 'owner_position')}
    rows = login_rows()

    def write(name, value):
        path = tmp_path / 'evidence' / name / 'episode.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path

    prep = write('prep', {'completed': True, 'failure': None, 'started_at': 1, 'finished_at': 2, 'code_commit': OLD})
    entry = write('entry', {'completed': True, 'failure': None, 'started_at': 3, 'finished_at': 5,
        'code_commit': OLD, 'login_packets': rows, 'native_owner_proof': {'rest_threshold': 0}})
    base['entry_source'] = op.bound(entry)
    failed = write('failed', {'completed': False, 'failure': 'RuntimeError: actionbars diagnostic did not become visible',
        'started_at': 6, 'finished_at': 7, 'code_commit': OLD})
    restored = {'completed': True, 'failure': None, 'started_at': 8, 'finished_at': 9,
        'code_commit': CLEANUP, 'actor': ACTOR, 'runtime': RUNTIME, 'phase': 'item_actionbar_restored',
        'source': op.bound(failed), 'first_failure_source': op.bound(failed),
        'first_failure': 'RuntimeError: actionbars diagnostic did not become visible',
        'preparation_source': op.bound(prep), 'fixture_source': op.bound(prep), 'native_session': 'owned',
        'entry_source': op.bound(entry), 'baseline': deepcopy(base), 'pre_recon_recovery': True,
        'recovery_only': True, 'failed_whole_excluded': True, 'gameplay_input_replayed': False,
        'drag_input_sent': False, 'clear_input_sent': False, 'mutation_sent': False, 'qualification_added': False,
        'cases': [], 'model': None, 'revision': None, 'controller': 'code_diagnostic_ordinary_inputs',
        'actionbar_restored': True, 'placement_absent': True,
        'restoration_checks': {name: True for name in reload.RESTORATION_CHECKS},
        'layout_restoration_checks': {name: True for name in reload.recovery.LAYOUT_CHECKS},
        'after_saved': deepcopy(base['saved']), 'after_resources': deepcopy(base['resources']),
        'after_native_state': deepcopy(before_native), 'protected_checks': protected}
    source = write('restored', restored)

    class Trial:
        fixture = ACTOR
        def __init__(self):
            self.receipt = {'code_commit': CURRENT, 'started_at': 10, 'runtime': RUNTIME, 'cases': [],
                'controller': 'code_diagnostic_ordinary_inputs', 'model': None, 'revision': None,
                'failure': None, 'completed': False, 'custom_script_permission': 'blocked_by_user'}
            self.out = tmp_path / 'evidence' / 'reload'
            self.out.mkdir(parents=True, exist_ok=True)
            self.version, self.events, self.persisted, self.fault = 145, [], [], None
            self.native = deepcopy(before_native)
        def persist(self):
            self.persisted.append(deepcopy(self.receipt))
        def observe(self, label, **kwargs):
            current = {**deepcopy(state), 'observer_version': self.version}
            if self.version == 146 and self.fault in ('bags', 'panels', 'cursor_info', 'chat_edit_open', 'spell_targeting'):
                current[self.fault] = [0] if self.fault in ('bags', 'panels', 'cursor_info') else True
            if self.version == 146 and self.fault == 'position': current['world_position'][0] += 1
            if self.version == 146 and self.fault == 'target': current['target']['exists'] = True
            return current, {'file': label + '.png', 'sha256': 'b' * 64}
        def execute(self, action, **kwargs):
            assert self.persisted[-1]['ordinary_inputs'][-1]['input'] == action
            assert self.persisted[-1]['ordinary_inputs'][-1]['input_sent'] is True
            self.events.append(deepcopy(action))
            if action['value'] == '/reload':
                if self.fault == 'interrupt': raise KeyboardInterrupt('ordinary reload interrupted')
                self.version = 145 if self.fault == 'wrong_version' else 146
                self.native['afk'] = False
                if self.fault == 'native': self.native['pose']['stand'] = 1
                if self.fault == 'unexpected_afk': self.native['afk'] = True
                if self.fault == 'saved': base['saved']['quests'].append(1)
                if self.fault == 'mutation': rows.append({'session': 'owned', 'time': 11,
                    'name': op.ACTION, 'direction': 'to_native', 'body': ''})
                if self.fault == 'lifetime': live_runtime['client']['pid'] += 1
            else:
                self.native['afk'] = True
        def clean_panels(self):
            pytest.fail('existing direct input cleanup must be replaced with a read-only layout check')

    trial = Trial()
    def authority(t, preparation, failed_path):
        assert preparation == prep and failed_path == failed
        t.receipt.update(preparation_source=op.bound(prep), fixture_source=op.bound(prep), native_session='owned',
            entry_source=base['entry_source'], first_failure_source=op.bound(failed),
            first_failure=restored['first_failure'], recovery_only=True, failed_whole_excluded=True,
            drag_input_sent=False, clear_input_sent=False, gameplay_input_replayed=False, mutation_sent=False,
            qualification_added=False)
        return deepcopy(base), 'owned', op.bound(failed), op.bound(prep)
    monkeypatch.setattr(reload.recovery, 'authority', authority)
    monkeypatch.setattr(op, 'saved', lambda: deepcopy(base['saved']))
    monkeypatch.setattr(op, 'resources', lambda session: deepcopy(base['resources']))
    monkeypatch.setattr(op, 'native_state', lambda session: deepcopy(trial.native))
    monkeypatch.setattr(op, 'peers', lambda baseline: deepcopy(protected))
    monkeypatch.setattr(op, 'detail', lambda *args: deepcopy(public))
    monkeypatch.setattr(op, 'session_entry', lambda fixture: {'session': 'owned'})
    monkeypatch.setattr(op, 'packet_rows', lambda *args: deepcopy(rows))
    def forbidden(baseline, session, until, t=None):
        return op.contract().forbidden_packets(rows, session, 3, until)
    monkeypatch.setattr(op, 'no_forbidden', forbidden)
    live_runtime = deepcopy(RUNTIME)
    monkeypatch.setattr(op.lab, 'owned_process', lambda name: live_runtime[name])
    monkeypatch.setattr(reload.time, 'time', lambda: 12)
    monkeypatch.setattr(reload.time, 'sleep', lambda _: None)
    clock = iter(range(0, 10000, 30))
    monkeypatch.setattr(reload.time, 'monotonic', lambda: next(clock))
    addon_paths = [reload.ADDON / name for name in ('ClientInteractions.lua', 'ClientMovementHarness.toc')]
    committed = {}
    for relative in addon_paths + list(reload.REPAIR_FILES):
        path = op.lab.REPO / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('observer_version=146' if path.name == 'ClientInteractions.lua' else 'committed source ' + path.name)
        committed[str(relative)] = path.read_bytes()
    def git(args, **kwargs):
        assert args[:1] == ['git'] and kwargs['cwd'] == op.lab.REPO
        if args[1:3] == ['rev-parse', 'HEAD']: return CURRENT
        if args[1] == 'ls-files': return '\n'.join(str(p) for p in addon_paths)
        revision, relative = args[2].split(':', 1)
        assert revision in (CLEANUP, CURRENT)
        return committed[relative]
    monkeypatch.setattr(reload.subprocess, 'check_output', git)
    def install(t):
        trial.events.append('install')
        files = t.receipt['observer_deployment']['source']
        t.receipt['parked_observer_installation'] = {'version': 146, 'source': deepcopy(files),
            'before': {'ClientInteractions.lua': 'a' * 64}, 'after': deepcopy(files), 'input_sent': False,
            'load_on': 'next ordinary owned class entry'}
        t.persist()
    monkeypatch.setattr(reload, 'install_observer', install)
    return trial, prep, source, restored, base, rows, committed, write


def test_import_is_pure_and_does_not_load_auth():
    before = set(sys.modules)
    importlib.reload(reload)
    assert not any(name.startswith(('google.protobuf', 'tools.client_compatibility.auth')) for name in set(sys.modules) - before)


def test_truthful_two_commit_cleanup_then_one_ordinary_reload_preserves_failure(scene):
    trial, prep, source, restored, base, _, _, _ = scene
    failed_path = Path(restored['first_failure_source']['path'])
    failed_bytes = failed_path.read_bytes()
    reload.run(trial, prep, source)
    assert trial.receipt['completed'] is True
    assert trial.receipt['phase'] == 'item_actionbar_passive_observer_loaded'
    assert trial.events == ['install', {'kind': 'chat', 'value': '/reload'}]
    assert trial.receipt['previous_code_commit'] == OLD
    assert trial.receipt['restoration_code_commit'] == CLEANUP
    assert trial.receipt['code_commit'] == CURRENT
    assert trial.receipt['repair_code_transition']['restoration_source'] == reload.op.bound(source)
    assert trial.receipt['committed_sources'] == trial.receipt['repair_code_transition']['committed_sources']
    assert trial.receipt['committed_sources'] == trial.receipt['observer_deployment']['committed_sources']
    assert trial.receipt['entry_source'] == base['entry_source']
    assert trial.receipt['after_native_state'] == base['native_state']
    assert trial.receipt['observer_deployment']['source'] == trial.receipt['observer_deployment']['installed']
    assert len(trial.receipt['layout_restoration_checks']) == 9 and all(trial.receipt['checks'].values())
    assert trial.receipt['cases'] == [] and trial.receipt['qualification_added'] is False
    assert trial.receipt['recovery_only'] is True and trial.receipt['failed_whole_excluded'] is True
    assert failed_path.read_bytes() == failed_bytes


def test_original_afk_only_is_restored_with_one_logged_housekeeping_input(scene):
    trial, prep, source, restored, base, _, _, write = scene
    base['native_state']['afk'] = trial.native['afk'] = True
    restored['baseline'] = deepcopy(base)
    restored['after_native_state'] = deepcopy(base['native_state'])
    write('restored', restored)
    reload.run(trial, prep, source)
    assert trial.receipt['completed'] is True
    assert trial.events == ['install', {'kind': 'chat', 'value': '/reload'}, {'kind': 'chat', 'value': '/afk'}]
    assert [row['input'] for row in trial.receipt['ordinary_inputs']] == trial.events[1:]
    assert trial.receipt['after_native_state']['afk'] is True


@pytest.mark.parametrize('key,value', [('recovery_only', False), ('failed_whole_excluded', False),
    ('gameplay_input_replayed', True), ('drag_input_sent', True), ('clear_input_sent', True),
    ('mutation_sent', True), ('qualification_added', True), ('placement_absent', False),
    ('pre_recon_recovery', False), ('code_commit', 'invalid'), ('cases', [{'admitted': True}]),
    ('model', 'laya'), ('revision', 'learned'), ('controller', 'unreviewed_actor'),
    ('phase', 'item_actionbar_placed'), ('first_failure', 'different failure')])
def test_wrong_restoration_authority_cannot_install_or_reload(scene, key, value):
    trial, prep, source, restored, _, _, _, write = scene
    restored[key] = value
    write('restored', restored)
    reload.run(trial, prep, source)
    assert trial.receipt['completed'] is False and trial.events == []


@pytest.mark.parametrize('kind', ['drag', 'clear'])
def test_consumed_entry_attempt_refuses_observer_deployment(scene, kind):
    trial, prep, source, _, base, _, _, _ = scene
    marker = Path(base['entry_source']['path']).parent / ('item_actionbar_' + kind + '_attempt.json')
    marker.write_text('interrupted consumed attempt')
    reload.run(trial, prep, source)
    assert trial.receipt['completed'] is False and trial.events == [] and marker.exists()


@pytest.mark.parametrize('fault', ['dirty_addon', 'extra_addon', 'dirty_module', 'old_cleanup_bytes'])
def test_uncommitted_or_different_cleanup_code_cannot_install(scene, fault):
    trial, prep, source, _, _, _, committed, _ = scene
    repo = reload.op.lab.REPO
    cleanup = str(reload.REPAIR_FILES[1])
    if fault == 'extra_addon': (repo / reload.ADDON / 'extra.lua').write_text('uncommitted')
    elif fault == 'dirty_addon': (repo / reload.ADDON / 'ClientInteractions.lua').write_text('observer_version=145')
    elif fault == 'dirty_module': (repo / reload.REPAIR_FILES[0]).write_text('uncommitted reload')
    else:
        actual_git = reload.subprocess.check_output
        def git(args, **kwargs):
            if args[1] == 'show' and args[2] == CLEANUP + ':' + cleanup: return b'different cleanup guard'
            return actual_git(args, **kwargs)
        from unittest.mock import patch
        with patch.object(reload.subprocess, 'check_output', git):
            reload.run(trial, prep, source)
        assert trial.receipt['completed'] is False and trial.events == []
        return
    reload.run(trial, prep, source)
    assert trial.receipt['completed'] is False and trial.events == []


@pytest.mark.parametrize('fault', ['bags', 'panels', 'cursor_info', 'chat_edit_open', 'spell_targeting',
    'position', 'target', 'native', 'unexpected_afk', 'saved', 'mutation', 'lifetime', 'wrong_version'])
def test_bad_post_reload_state_is_retained_without_replaying_reload(scene, fault):
    trial, prep, source, _, _, _, _, _ = scene
    trial.fault = fault
    reload.run(trial, prep, source)
    assert trial.receipt['completed'] is False and trial.receipt['failure']
    assert trial.events == ['install', {'kind': 'chat', 'value': '/reload'}]
    assert len(trial.receipt['ordinary_inputs']) == 1 and trial.receipt['cases'] == []


def test_interrupted_reload_retains_durable_intent_and_never_replays(scene):
    trial, prep, source, _, _, _, _, _ = scene
    trial.fault = 'interrupt'
    with pytest.raises(KeyboardInterrupt): reload.run(trial, prep, source)
    assert trial.receipt['completed'] is False and trial.receipt['finished_at'] == 12
    assert trial.events == ['install', {'kind': 'chat', 'value': '/reload'}]
    assert len(trial.receipt['ordinary_inputs']) == 1
    assert trial.receipt['ordinary_inputs'][0]['finished_at'] == 12
    marker = Path(trial.receipt['reload_attempt_source']['path'])
    before = marker.read_bytes()
    again = type(trial)()
    again.out = trial.out.parent / 'retry'
    reload.run(again, prep, source)
    assert again.receipt['completed'] is False and 'already consumed' in again.receipt['failure']
    assert again.events == [] and marker.read_bytes() == before


@pytest.mark.parametrize('key,value', [('controller', 'laya_candidate_selection'), ('revision', 'unreviewed'),
    ('model', 'learned'), ('cases', [{'success': True}]), ('custom_script_permission', 'enabled')])
def test_new_stage_refuses_non_code_or_permission_drift(scene, key, value):
    trial, prep, source, _, _, _, _, _ = scene
    trial.receipt[key] = value
    reload.run(trial, prep, source)
    assert trial.receipt['completed'] is False and trial.events == []


@pytest.mark.parametrize('fault', ['saved', 'resources', 'native', 'layout_checks', 'protected', 'first_hash'])
def test_false_or_incomplete_restored_facts_cannot_authorize_reload(scene, fault):
    trial, prep, source, restored, _, _, _, write = scene
    if fault == 'saved': restored['after_saved']['quests'].append(1)
    elif fault == 'resources': restored['after_resources']['money'] = 1
    elif fault == 'native': restored['after_native_state']['pose']['stand'] = 1
    elif fault == 'layout_checks': restored['layout_restoration_checks']['pose'] = False
    elif fault == 'protected':
        restored['protected_checks']['foreign'] = restored['protected_checks'].pop('protected_1')
    else: restored['first_failure_source']['sha256'] = 'f' * 64
    write('restored', restored)
    reload.run(trial, prep, source)
    assert trial.receipt['completed'] is False and trial.events == []


@pytest.mark.parametrize('name', [reload.op.ACTION, 'CMSG_USE_ITEM', 'CMSG_TRAINER_BUY_SPELL', 'CMSG_PET_UNKNOWN'])
def test_original_entry_to_now_mutation_blocks_every_deployment(scene, name):
    trial, prep, source, _, _, rows, _, _ = scene
    rows.append({'session': 'owned', 'time': 11, 'name': name, 'direction': 'to_native', 'body': ''})
    reload.run(trial, prep, source)
    assert trial.receipt['completed'] is False and trial.events == []


def test_added_login_refuses_lifetime_borrowing_before_install(scene):
    trial, prep, source, _, _, rows, _, _ = scene
    rows.append({**rows[0], 'time': 11})
    reload.run(trial, prep, source)
    assert trial.receipt['completed'] is False and trial.events == []


def test_reload_marker_is_terminal_even_when_its_durable_write_is_interrupted(scene, monkeypatch):
    trial, prep, source, _, _, _, _, _ = scene
    def interrupted(fd):
        raise KeyboardInterrupt('reload marker fsync interrupted')
    monkeypatch.setattr(reload.os, 'fsync', interrupted)
    with pytest.raises(KeyboardInterrupt): reload.run(trial, prep, source)
    marker = source.parent / 'item_actionbar_observer_reload_attempt.json'
    assert marker.is_file() and trial.events == ['install']
    again = type(trial)()
    reload.run(again, prep, source)
    assert again.receipt['completed'] is False and 'already consumed' in again.receipt['failure']
    assert again.events == []


def test_cli_truthfully_serializes_scoped_code_controller(monkeypatch, tmp_path):
    trials = []
    class Constructor:
        def __init__(self, output, **kwargs):
            assert kwargs == {'controller': 'code', 'chat_key_hold': 1.2, 'chat_open_retry': True}
            # These are the actual Trial(controller='code') serialization values.
            self.receipt = {'controller': 'code_diagnostic_ordinary_inputs', 'model': None, 'revision': None,
                'code_commit': CURRENT, 'cases': []}
            trials.append(self)
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.interaction_social', SimpleNamespace(actor=lambda name: nullcontext()))
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.interaction_trial', SimpleNamespace(Trial=Constructor))
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.interaction_owned_class_fixture',
        SimpleNamespace(SCRIPT_BOUNDARY={'user_blocked': True}))
    def run(t, preparation, source):
        assert t.receipt['controller'] == 'code' and t.receipt['model'] is None and t.receipt['revision'] is None
        assert t.receipt['code_commit'] == CURRENT and t.receipt['cases'] == []
        assert t.receipt['custom_script_permission'] == 'blocked_by_user'
    monkeypatch.setattr(reload, 'run', run)
    monkeypatch.setattr(sys, 'argv', ['reload', '--preparation', str(tmp_path / 'prep.json'),
        '--source', str(tmp_path / 'source.json'), '--output', str(tmp_path / 'output')])
    reload.main()
    assert len(trials) == 1
