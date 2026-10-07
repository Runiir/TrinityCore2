"""Load committed passive observer146 after excluded pre-recon bag cleanup.

Only an ordinary /reload and, when required, exact AFK restoration are inputs.
The original entry and failed reconnaissance remain immutable authority.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

from . import interaction_item_actionbar as op
from . import interaction_item_actionbar_pre_recon_recovery as recovery
from .item_actionbar_contract import require, strict_equal

VERSION = 146
ADDON = Path('tools/client_compatibility/observation/addon/ClientMovementHarness')
INSTALLER = Path('tools/client_compatibility/interaction_retained_class_reentry.py')
REPAIR_FILES = (Path('tools/client_compatibility/interaction_item_actionbar_observer_reload.py'),
    Path('tools/client_compatibility/interaction_item_actionbar_pre_recon_recovery.py'),
    Path('tools/client_compatibility/interaction_item_actionbar_idle_renewal.py'),
    Path('tools/client_compatibility/interaction_item_actionbar_entry_capture.py'),
    Path('tools/client_compatibility/interaction_item_actionbar.py'),
    Path('tools/client_compatibility/item_actionbar_evidence.py'), INSTALLER)
RESTORATION_CHECKS = recovery.LAYOUT_CHECKS | {'full_saved_baseline', 'full_resources_baseline',
    'protected_actors', 'zero_native_mutation'}
PROTECTED_CHECKS = frozenset(('protected_1', 'protected_3', 'protected_4', 'protected_5', 'protected_6',
    'owner_inventory', 'owner_pets', 'owner_position'))


def install_observer(t):
    from .interaction_retained_class_reentry import install_observer as install
    install(t, VERSION)


def committed_observer(t):
    """Fingerprint every deployed file and the bounded committed installer/code."""
    repo = op.lab.REPO
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
    require(re.fullmatch('[0-9a-f]{40}', head) and t.receipt.get('code_commit') == head,
        'observer deployment requires the truthful current Trial code commit')
    names = subprocess.check_output(['git', 'ls-files', '--', str(ADDON)], cwd=repo, text=True).splitlines()
    paths = [Path(name) for name in names]
    directory = repo / ADDON
    require(paths and set(paths) == {path.relative_to(repo) for path in directory.rglob('*') if path.is_file()} and
        all(path.parent == ADDON for path in paths), 'every observer file must be committed without extra files')
    sources = []
    for relative in sorted(set(paths) | set(REPAIR_FILES)):
        path = repo / relative
        require(not any(p.is_symlink() for p in (path, *path.parents)), 'committed observer source cannot be a symlink')
        committed = subprocess.check_output(['git', 'show', head + ':' + str(relative)], cwd=repo)
        require(hashlib.sha256(committed).hexdigest() == op.bound(path)['sha256'],
            'observer deployment refuses uncommitted source changes')
        sources.append(op.bound(path))
    cleanup_path = Path('tools/client_compatibility/interaction_item_actionbar_pre_recon_recovery.py')
    cleanup_at_restoration = subprocess.check_output(['git', 'show',
        t.receipt['restoration_code_commit'] + ':' + str(cleanup_path)], cwd=repo)
    require(hashlib.sha256(cleanup_at_restoration).hexdigest() == op.bound(repo / cleanup_path)['sha256'],
        'restoration commit must contain the same reviewed cleanup guard')
    text = (directory / 'ClientInteractions.lua').read_text()
    require(re.search(r'\bobserver_version=146\b', text), 'requires committed passive observer146')
    return {'code_commit': head, 'committed_sources': sources,
        'source': {relative.name: op.bound(repo / relative)['sha256'] for relative in paths},
        'installer_source': op.bound(repo / INSTALLER)}


def authority(t, preparation, source):
    require(t.receipt.get('controller') in ('code', 'code_diagnostic_ordinary_inputs') and
        t.receipt.get('model') is None and t.receipt.get('revision') is None and t.receipt.get('cases') == [] and
        t.receipt.get('custom_script_permission') == 'blocked_by_user',
        'passive observer stage requires blocked scripts and an empty code-only observation receipt')
    restored = op.closed(source)
    first_ref = restored.get('first_failure_source', {})
    op.require(op.bound(Path(first_ref.get('path', ''))) == first_ref, 'original failed reconnaissance digest differs')
    base, session, failed_ref, prep_ref = recovery.authority(t, preparation, Path(first_ref['path']))
    entry = op.closed(Path(base['entry_source']['path']))
    failed = op.closed(Path(first_ref['path']), successful=False)
    old_code = entry.get('code_commit')
    require(re.fullmatch('[0-9a-f]{40}', old_code or '') and
        failed.get('code_commit') == op.closed(preparation).get('code_commit') == old_code and
        re.fullmatch('[0-9a-f]{40}', restored.get('code_commit', '')) and
        restored.get('actor') == t.fixture and restored.get('runtime') == t.receipt['runtime'] and
        restored.get('phase') == 'item_actionbar_restored' and
        restored.get('preparation_source') == restored.get('fixture_source') == prep_ref and
        restored.get('native_session') == session and restored.get('entry_source') == base['entry_source'] and
        strict_equal(restored.get('baseline'), base) and restored['finished_at'] <= t.receipt['started_at'] and
        restored.get('pre_recon_recovery') is True and restored.get('recovery_only') is True and
        restored.get('failed_whole_excluded') is True and restored.get('source') == failed_ref and
        restored.get('first_failure') == failed['failure'] and restored.get('gameplay_input_replayed') is False and
        restored.get('drag_input_sent') is False and restored.get('clear_input_sent') is False and
        restored.get('mutation_sent') is False and restored.get('qualification_added') is False and
        restored.get('cases') == [] and restored.get('model') is None and restored.get('revision') is None and
        restored.get('controller') in ('code', 'code_diagnostic_ordinary_inputs') and
        restored.get('actionbar_restored') is True and restored.get('placement_absent') is True and
        not any(key in restored for key in recovery.ATTEMPT_FIELDS) and
        set(restored.get('restoration_checks', {})) == RESTORATION_CHECKS and
        all(value is True for value in restored['restoration_checks'].values()) and
        set(restored.get('layout_restoration_checks', {})) == recovery.LAYOUT_CHECKS and
        all(value is True for value in restored['layout_restoration_checks'].values()) and
        strict_equal(restored.get('after_saved'), base['saved']) and
        strict_equal(restored.get('after_resources'), base['resources']) and
        strict_equal(restored.get('after_native_state'), base['native_state']) and
        set(restored.get('protected_checks', {})) == PROTECTED_CHECKS and
        all(value is True for value in restored['protected_checks'].values()),
        'requires exact closed excluded pre-recon restoration and source-backed code transition')
    recovery.unconsumed(base['entry_source'])
    if restored.get('idle_renewal') is True:
        from .interaction_item_actionbar_idle_renewal import validate_restored_renewal
        validate_restored_renewal(restored, source)
    else:
        require(not any(key in restored for key in ('idle_renewal', 'prior_restoration_source', 'failed_observer_source')),
            'ordinary observer source has unrecognized idle renewal ancestry')
    marker = Path(source).parent / 'item_actionbar_observer_reload_attempt.json'
    require(not marker.exists() and not marker.is_symlink(), 'ordinary observer reload is already consumed for this restoration')
    require(not base['state'].get('bags') and not base['state'].get('panels'), 'original bags and panels must be closed')
    t.receipt.update(source=op.bound(source), restoration_source=op.bound(source), previous_code_commit=old_code,
        restoration_code_commit=restored['code_commit'],
        baseline=deepcopy(base), observer_only=True, ordinary_inputs=[], input_sent=False,
        phase='item_actionbar_passive_observer_prepared')
    t.persist()
    return base, session, entry, restored


def consume_reload(t, source):
    """Consume this source's sole ordinary reload, including interrupted submission."""
    source, output = Path(source), t.out / 'episode.json'
    require(output.is_absolute() and output.is_relative_to(op.lab.ROOT / 'evidence') and
        all(not p.is_symlink() for p in (output, *output.parents)), 'reload output must be private owned evidence')
    value = {'schema': 'client442_item_actionbar_observer_reload_attempt_v1', 'consumed': True,
        'input_replay_allowed': False, 'created_at': time.time(), 'input': t.receipt['reload_intent'],
        'restoration_source': t.receipt['restoration_source'], 'entry_source': t.receipt['entry_source'],
        'first_failure_source': t.receipt['first_failure_source'], 'code_commit': t.receipt['code_commit'],
        'actor': t.fixture, 'runtime': t.receipt['runtime'], 'native_session': t.receipt['native_session'],
        'operation_output': str(output)}
    marker = source.parent / 'item_actionbar_observer_reload_attempt.json'
    directory = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            descriptor = os.open(marker.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=directory)
        except FileExistsError as error:
            raise RuntimeError('ordinary observer reload is already consumed for this restoration') from error
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write((json.dumps(value, indent=2, sort_keys=True) + '\n').encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)
    t.receipt['reload_attempt_source'] = op.bound(marker)
    t.persist()


def unchanged_authority(t, preparation, source, base, session, entry, source_ref, failed_ref):
    require(op.bound(source) == source_ref and op.bound(preparation) == t.receipt['preparation_source'] and
        op.bound(Path(failed_ref['path'])) == failed_ref and
        op.bound(Path(base['entry_source']['path'])) == base['entry_source'], 'immutable observer ancestry changed')
    require(op.session_entry(t.fixture)['session'] == session, 'ordinary reload changed the native session')
    for kind, expected in t.receipt['runtime'].items():
        process = op.lab.owned_process(kind)
        require(process and {key: process[key] for key in expected} == expected,
            'ordinary reload changed a client, bridge or native lifetime')
    recovery.unconsumed(base['entry_source'])
    if t.receipt.get('reload_attempt_source'):
        ref = t.receipt['reload_attempt_source']
        require(op.bound(Path(ref['path'])) == ref, 'consumed ordinary reload authority changed')
    until = time.time()
    rows = op.packet_rows(session, entry['started_at'], until)
    require(not any(row.get('name') == op.ACTION for row in rows), 'passive observer refuses every action-bar mutation')
    login = op.contract().login_packets(rows, session, entry['started_at'], until)
    require(entry['login_packets'] == [login[key] for key in ('modern', 'request', 'verify', 'delivered')],
        'ordinary reload changed the original sealed login')
    proof = op.no_forbidden(base, session, until, t)
    t.receipt['observer_no_mutation_proof'] = {'since': entry['started_at'], 'until': until,
        'native_action_requests': 0, 'packets_checked': len(rows), 'forbidden_input_proof': proof,
        'login_packets': entry['login_packets'], 'drag_attempt_consumed': False, 'clear_attempt_consumed': False}
    t.persist()


def layout_state(state, base):
    require(not any(state.get(key) for key in ('bags', 'panels', 'cursor_info', 'chat_edit_open',
        'spell_targeting', 'pending_glyph', 'lua_errors', 'blocked_actions')) and
        strict_equal(state.get('world_position'), base['state'].get('world_position')) and
        all(state.get('target', {}).get(key) == base['state'].get('target', {}).get(key)
            for key in ('exists', 'guid', 'name')), 'passive reload requires the exact closed original layout')


def reload_observer(t, preparation, source):
    base, session, entry, restored = authority(t, preparation, source)
    source_ref, failed_ref = op.bound(source), t.receipt['first_failure_source']
    seal = lambda: unchanged_authority(t, preparation, source, base, session, entry, source_ref, failed_ref)
    seal()
    before_saved, before_resources, native, protected, state, frame = op.assert_live(base, session, base['saved'],
        t=t, label='item_observer_before')
    layout_state(state, base)
    require(strict_equal(native, base['native_state']), 'passive observer native baseline differs before reload')
    public = op.detail(t, 'item_observer_before_bars')
    op.contract().public_assignments(public, base['saved']['actions'], base['active_spec'])
    require(op.public_same(public, base['public']), 'passive observer original public action bar differs')
    deployment = committed_observer(t)
    transition = {'previous_code_commit': t.receipt['previous_code_commit'], 'code_commit': t.receipt['code_commit'],
        'restoration_code_commit': t.receipt['restoration_code_commit'],
        'entry_source': base['entry_source'], 'first_failure_source': failed_ref, 'restoration_source': source_ref,
        'committed_sources': deployment['committed_sources']}
    t.receipt.update(before_saved=before_saved, before_resources=before_resources, before_native_state=native,
        before_public=public, before_state=state, before_frame=frame, protected_checks=protected,
        committed_sources=deployment['committed_sources'], repair_code_transition=transition,
        observer_deployment={**deployment, 'version': VERSION,
            'load_on': 'ordinary /reload'}, reload_intent={'kind': 'chat', 'value': '/reload'})
    t.persist()
    seal()
    install_observer(t)
    installation = t.receipt['parked_observer_installation']
    require(installation.get('version') == VERSION and installation.get('source') == deployment['source'] and
        installation.get('input_sent') is False and installation.get('after') == deployment['source'],
        'installed passive observer files differ from committed sources')
    t.receipt['observer_deployment']['installed'] = {name: installation['after'][name] for name in deployment['source']}
    t.persist()
    seal()
    _, _, immediate_native, _, immediate_state, _ = op.assert_live(base, session, base['saved'],
        t=t, label='item_observer_reload_preflight')
    layout_state(immediate_state, base)
    require(strict_equal(immediate_native, base['native_state']), 'native baseline changed before ordinary reload')
    consume_reload(t, source)
    original_execute = t.execute
    original_clean_panels = t.clean_panels

    def ordinary(action, **kwargs):
        permitted = action == {'kind': 'chat', 'value': '/reload'} and not t.receipt['ordinary_inputs']
        permitted = permitted or (action == {'kind': 'chat', 'value': '/afk'} and base['native_state']['afk'] is True and
            [row['input'] for row in t.receipt['ordinary_inputs']] == [{'kind': 'chat', 'value': '/reload'}] and
            op.native_state(session)['afk'] is False)
        require(permitted, 'passive observer refuses another ordinary or gameplay input')
        row = {'input': deepcopy(action), 'started_at': time.time(), 'input_sent': True, 'input_replayed': False}
        t.receipt['ordinary_inputs'].append(row)
        t.receipt.update(input_sent=True, reload_input_sent=True)
        t.persist()
        try:
            return original_execute(action, **kwargs)
        finally:
            row['finished_at'] = time.time()
            t.persist()

    t.execute = ordinary
    def closed_panels_only():
        current, _ = t.observe('item_observer_closed_layout')
        layout_state(current, base)
    t.clean_panels = closed_panels_only
    try:
        t.receipt['phase'] = 'item_actionbar_passive_observer_reload_started'
        t.persist()
        t.execute(t.receipt['reload_intent'])
        deadline = time.monotonic() + 60
        while True:
            after_state, after_frame = t.observe('item_observer_loaded', seconds=60)
            t.receipt.update(after_state=after_state, after_frame=after_frame)
            t.persist()
            if after_state.get('observer_version') == VERSION:
                break
            require(time.monotonic() < deadline, 'ordinary reload did not load passive observer146; refusing replay')
            time.sleep(.2)
        layout_state(after_state, base)
        _, _, after_native, _ = op.assert_live(base, session, base['saved'])
        allowed = deepcopy(base['native_state'])
        allowed['afk'] = after_native['afk']
        require(strict_equal(after_native, allowed) and (after_native['afk'] is base['native_state']['afk'] or
            base['native_state']['afk'] is True and after_native['afk'] is False),
            'ordinary reload changed native state beyond clearing original AFK')
        public_after = op.detail(t, 'item_observer_loaded_bars')
        op.contract().public_assignments(public_after, base['saved']['actions'], base['active_spec'])
        require(op.public_same(public_after, base['public']), 'ordinary reload changed public action assignments')
        layout_checks = op.restore_layout(t, base, session)
    finally:
        t.execute = original_execute
        t.clean_panels = original_clean_panels
    require(set(layout_checks) == recovery.LAYOUT_CHECKS and all(value is True for value in layout_checks.values()),
        'passive observer requires all nine exact layout restoration checks')
    after_saved, after_resources, after_native, protected, after_state, after_frame = op.assert_live(
        base, session, base['saved'], t=t, label='item_observer_restored')
    layout_state(after_state, base)
    require(after_state.get('observer_version') == VERSION and strict_equal(after_native, base['native_state']),
        'fresh observer146 or restored native state differs')
    seal()
    t.receipt.update(after_saved=after_saved, after_resources=after_resources, after_native_state=after_native,
        after_public=t.receipt['restored_public'], after_state=after_state, after_frame=after_frame,
        layout_restoration_checks=layout_checks, protected_checks=protected,
        checks={**layout_checks, 'observer146': True, 'full_saved_baseline': True, 'full_resources_baseline': True,
            'native_baseline': True, 'protected_actors': all(protected.values()), 'same_runtime_session': True,
            'original_entry_login': True, 'zero_native_mutation': True, 'unconsumed_attempts': True},
        completed=True, phase='item_actionbar_passive_observer_loaded', qualification_added=False,
        mutation_sent=False, drag_input_sent=False, clear_input_sent=False, gameplay_input_replayed=False)
    t.persist()


def run(t, preparation, source):
    try:
        reload_observer(t, preparation, source)
    except BaseException as error:
        t.receipt.update(completed=False, failure=t.receipt.get('failure') or type(error).__name__ + ': ' + str(error))
        t.persist()
        if not isinstance(error, Exception):
            raise
    finally:
        t.receipt['finished_at'] = time.time()
        t.persist()


def main():
    from .interaction_social import actor
    from .interaction_trial import Trial
    from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('preparation', 'source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    with actor('scout'):
        trial = Trial(args.output, controller='code', chat_key_hold=1.2, chat_open_retry=True)
        trial.receipt.update(controller='code', custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY,
            qualification_added=False, input_sent=False, mutation_sent=False)
        run(trial, args.preparation, args.source)
        print({key: trial.receipt.get(key) for key in ('completed', 'phase', 'failure')}, flush=True)


if __name__ == '__main__':
    main()
