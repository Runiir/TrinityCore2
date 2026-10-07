"""Restore one newly observed idle pose after an input-free observer rejection."""
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
from . import interaction_item_actionbar_observer_reload as observer
from . import interaction_item_actionbar_pre_recon_recovery as recovery
from .item_actionbar_contract import INDEX, body, records, require, strict_equal
from .observation.journal import entries

HELPER = Path('tools/client_compatibility/interaction_item_actionbar_idle_renewal.py')
OLD_HELPER = Path('tools/client_compatibility/interaction_item_actionbar_pre_recon_recovery.py')
OLD_HELPER_SHA = '71466835679802375f78039b4509df56cdfbe6afe7f6c2a99e086e26a6c97d3e'
OPERATION = Path('tools/client_compatibility/interaction_item_actionbar.py')
ROUTINE = frozenset(('CMSG_QUEST_GIVER_STATUS_QUERY', 'CMSG_TIME_SYNC_RESPONSE',
    'CMSG_TIME_SYNC_RESP', 'CMSG_SERVER_TIME_OFFSET_REQUEST'))


def source_bytes(t, prior):
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=op.lab.REPO, text=True).strip()
    require(head == t.receipt['code_commit'], 'renewal requires the truthful committed Trial code')
    refs = []
    for relative in (HELPER, OLD_HELPER, OPERATION):
        committed = subprocess.check_output(['git', 'show', head + ':' + str(relative)], cwd=op.lab.REPO)
        ref = op.bound(op.lab.REPO / relative)
        require(hashlib.sha256(committed).hexdigest() == ref['sha256'], 'renewal refuses working candidate source bytes')
        refs.append(ref)
    require(refs[1]['sha256'] == OLD_HELPER_SHA, 'the original pre-recon cleanup helper must remain unchanged')
    isolation = prior.get('runtime_source_isolation', {})
    old_operation = subprocess.check_output(['git', 'show', prior['code_commit'] + ':' + str(OPERATION)], cwd=op.lab.REPO)
    require(set(isolation) == {'code_commit', 'operation_source', 'loaded_from', 'working_candidate_inputs_used'} and
        isolation['code_commit'] == prior['code_commit'] and isolation['loaded_from'] == 'git_object_bytes' and
        isolation['working_candidate_inputs_used'] is False and isolation['operation_source'] ==
        {'path': str(op.lab.REPO / OPERATION), 'sha256': hashlib.sha256(old_operation).hexdigest()},
        'original completed restoration must retain its actual git-object operation identity')
    t.receipt.update(renewal_code_sources=refs, renewal_runtime_source={'code_commit': head,
        'operation_source': refs[2], 'loaded_from': 'committed_working_bytes', 'working_candidate_inputs_used': False})
    t.persist()


def marker(t, kind):
    failed = t.receipt['failed_observer_source']
    return Path(failed['path']).parent / ('item_actionbar_idle_renewal_' + failed['sha256'] + '_' + kind + '_attempt.json')


def authority(t, preparation, restoration_source, failed_observer_source):
    base, session, entry, prior = observer.authority(t, preparation, restoration_source)
    failed = op.closed(failed_observer_source, successful=False)
    prior_ref, failed_ref = op.bound(restoration_source), op.bound(failed_observer_source)
    require(prior.get('idle_renewal') is not True and failed.get('phase') == 'item_actionbar_passive_observer_prepared' and
        failed.get('failure') == 'RuntimeError: native baseline changed before ordinary reload' and
        failed.get('actor') == t.fixture and failed.get('runtime') == t.receipt['runtime'] and
        failed.get('native_session') == session and failed.get('preparation_source') == failed.get('fixture_source') ==
        t.receipt['preparation_source'] and failed.get('source') == failed.get('restoration_source') == prior_ref and
        failed.get('first_failure_source') == t.receipt['first_failure_source'] and
        failed.get('entry_source') == base['entry_source'] and strict_equal(failed.get('baseline'), base) and
        failed.get('controller') in ('code', 'code_diagnostic_ordinary_inputs') and
        failed.get('model') is None and failed.get('revision') is None and failed.get('cases') == [] and
        re.fullmatch('[0-9a-f]{40}', failed.get('code_commit', '')) and
        failed.get('restoration_code_commit') == prior['code_commit'] and
        failed.get('previous_code_commit') == entry['code_commit'] and failed.get('first_failure') == prior['first_failure'] and
        failed.get('cleanup') == [] and failed.get('input_sent') is False and failed.get('ordinary_inputs') == [] and
        failed.get('mutation_sent') is False and failed.get('qualification_added') is False and
        failed.get('drag_input_sent') is False and failed.get('clear_input_sent') is False and
        failed.get('gameplay_input_replayed') is False and failed.get('observer_only') is True and
        'reload_attempt_source' not in failed and 'reload_input_sent' not in failed and
        prior['finished_at'] <= failed['started_at'] < failed['finished_at'] <= t.receipt['started_at'] and
        strict_equal(failed.get('before_saved'), base['saved']) and
        strict_equal(failed.get('before_resources'), base['resources']) and
        strict_equal(failed.get('before_native_state'), base['native_state']) and
        op.public_same(failed.get('before_public', {}), base['public']) and
        set(failed.get('protected_checks', {})) == observer.PROTECTED_CHECKS and
        all(value is True for value in failed['protected_checks'].values()),
        'renewal requires the exact input-free failed observer and original completed restoration')
    require(base['public'].get('keys', {}).get('SITORSTAND') == entry.get('public', {}).get('keys', {}).get('SITORSTAND'),
        'renewal standing binding must match the immutable original entry')
    reload_marker = Path(restoration_source).parent / 'item_actionbar_observer_reload_attempt.json'
    require(not reload_marker.exists() and not reload_marker.is_symlink(), 'failed observer must have no consumed reload')
    prior_inputs = {key: prior[key] for key in ('escape_attempt_source', 'stand_attempt_source', 'afk_attempt_source')}
    for ref in prior_inputs.values():
        require(op.bound(Path(ref['path'])) == ref, 'original consumed cleanup input changed')
    t.receipt.update(source=t.receipt['first_failure_source'], prior_restoration_source=prior_ref,
        failed_observer_source=failed_ref, prior_input_sources=prior_inputs, baseline=deepcopy(base),
        pre_recon_recovery=True, idle_renewal=True, observer_only=False, input_sent=False,
        ordinary_inputs=[], phase='item_actionbar_idle_renewal_prepared')
    for kind in ('stand', 'afk'):
        require(not marker(t, kind).exists() and not marker(t, kind).is_symlink(),
            'idle renewal source is already consumed; refusing replay')
    source_bytes(t, prior)
    return base, session, entry, prior, failed


def validate_restored_renewal(value, source_path):
    """Admit only the explicitly typed renewal ancestry to the ordinary loader."""
    source_path = Path(source_path)
    require(source_path.name == 'episode.json' and source_path.is_absolute() and
        source_path.is_relative_to(op.lab.ROOT / 'evidence') and
        all(not path.is_symlink() for path in (source_path, *source_path.parents)),
        'renewal admission requires its actual private source output')
    prior_ref, failed_ref = value.get('prior_restoration_source', {}), value.get('failed_observer_source', {})
    for ref in (prior_ref, failed_ref):
        require(op.bound(Path(ref.get('path', ''))) == ref, 'renewal ancestor digest differs')
    prior, failed = op.closed(Path(prior_ref['path'])), op.closed(Path(failed_ref['path']), successful=False)
    require(value.get('idle_renewal') is True and prior.get('idle_renewal') is not True and
        prior.get('phase') == 'item_actionbar_restored' and prior.get('pre_recon_recovery') is True and
        prior.get('recovery_only') is True and prior.get('failed_whole_excluded') is True and
        set(prior.get('restoration_checks', {})) == observer.RESTORATION_CHECKS and
        all(check is True for check in prior['restoration_checks'].values()) and
        failed.get('phase') == 'item_actionbar_passive_observer_prepared' and
        failed.get('failure') == 'RuntimeError: native baseline changed before ordinary reload' and
        failed.get('input_sent') is False and failed.get('ordinary_inputs') == [] and
        failed.get('cases') == [] and failed.get('mutation_sent') is False and
        failed.get('qualification_added') is False and 'reload_attempt_source' not in failed and
        failed.get('restoration_code_commit') == prior['code_commit'] and
        failed.get('source') == failed.get('restoration_source') == prior_ref and
        all(row.get(key) == value.get(key) for row in (prior, failed)
            for key in ('actor', 'runtime', 'native_session', 'preparation_source', 'entry_source', 'first_failure_source')) and
        strict_equal(prior.get('baseline'), value.get('baseline')) and strict_equal(failed.get('baseline'), value.get('baseline')) and
        prior['finished_at'] <= failed['started_at'] < failed['finished_at'] <= value['started_at'] < value['finished_at'],
        'restored idle renewal requires the complete original restoration and input-free observer chain')
    require(not (Path(prior_ref['path']).parent / 'item_actionbar_observer_reload_attempt.json').exists(),
        'renewal cannot follow a consumed original observer input')
    for key, ref in value.get('prior_input_sources', {}).items():
        require(key in ('escape_attempt_source', 'stand_attempt_source', 'afk_attempt_source') and
            prior.get(key) == ref and op.bound(Path(ref['path'])) == ref, 'renewal original input authority differs')
    require(set(value.get('prior_input_sources', {})) == {'escape_attempt_source', 'stand_attempt_source', 'afk_attempt_source'},
        'renewal must preserve all three original cleanup input authorities')
    idle, base = value.get('pre_recon_idle_observation', {}), value['baseline']
    require(idle.get('label') == 'unattributed_observed_post_restoration_idle_state_mismatch' and
        idle.get('mismatch_observed') is True and idle.get('qualification_added') is False and
        idle.get('prior_restoration_source') == prior_ref and idle.get('failed_observer_source') == failed_ref and
        idle.get('since') == prior['finished_at'] and value['started_at'] <= idle.get('until', 0) <= value['finished_at'] and
        strict_equal(idle.get('original'), base['native_state']) and
        strict_equal(idle.get('native_before_observation'), {**base['native_state'],
            'pose': {**base['native_state']['pose'], 'stand': 1}, 'afk': True}), 'renewal idle observation authority differs')
    actual = idle_packets(op.packet_rows(value['native_session'], idle['since'], idle['until']),
        value['native_session'], idle['since'], idle['until'], failed['finished_at'])
    require(all(strict_equal(idle.get(key), actual[key]) for key in actual),
        'renewal observed native transition differs from the actual source journal')
    entry = op.closed(Path(value['entry_source']['path']))
    keys = entry.get('public', {}).get('keys', {}).get('SITORSTAND')
    require(type(keys) is list and keys and base['public'].get('keys', {}).get('SITORSTAND') == keys,
        'renewal restored authority must retain the immutable original standing binding')
    standing = {'kind': 'key', 'value': op.binding_key(keys[0]), 'hold': .4}
    actions = value.get('ordinary_inputs', [])
    require(len(actions) in (1, 2) and [row.get('kind') for row in actions] == ['stand', 'afk'][:len(actions)],
        'renewal must contain one standing restoration and at most one AFK cleanup')
    require(actions[0].get('input') == standing and
        (len(actions) == 1 or actions[1].get('input') == {'kind': 'chat', 'value': '/afk'}),
        'renewal consumed inputs must be the original standing key and optional AFK cleanup')
    for row in actions:
        kind = row['kind']
        ref = value.get(kind + '_attempt_source', {})
        expected = Path(failed_ref['path']).parent / ('item_actionbar_idle_renewal_' + failed_ref['sha256'] + '_' + kind + '_attempt.json')
        require(ref.get('path') == str(expected) and op.bound(expected) == ref, 'renewal consumed input namespace or digest differs')
        intent = json.loads(expected.read_text())
        require(intent.get('schema') == 'client442_item_actionbar_idle_renewal_consumed_input_v1' and
            intent.get('kind') == kind and intent.get('input_replay_allowed') is False and
            intent.get('operation_output') == str(source_path) and
            intent.get('input_intent') == row.get('input') and
            all(intent.get(key) == value.get(key) for key in ('prior_restoration_source', 'failed_observer_source',
                'entry_source', 'first_failure_source', 'preparation_source', 'actor', 'runtime', 'native_session', 'code_commit')),
            'renewal consumed input must bind its exact source and current code')
    require(recovery.stand_chain(op.packet_rows(value['native_session'], value['stand_cleanup_started_at'],
        value['finished_at']), 0) == value.get('stand_cleanup_packets'),
        'renewal ordinary standing restoration differs from the actual native journal')
    return value


def idle_packets(rows, session, since, until, failed_finished):
    """Replay the exact two sparse native updates of this newly observed mismatch."""
    rows = op.contract().packet_rows(rows, session, since, until)
    quartet = recovery.stand_chain(rows, 1)
    require(quartet[0]['time'] > since and quartet[-1]['time'] <= failed_finished,
        'new idle transition must occur after restoration and inside the failed observer interval')
    allowed_requests = ROUTINE | {'CMSG_STAND_STATE_CHANGE', 'CMSG_STANDSTATECHANGE'}
    require(not any(row.get('direction') in ('from_client', 'to_native') and
        row.get('name') not in allowed_requests for row in rows), 'new idle renewal refuses other client requests')
    wanted = (INDEX['UNIT_FIELD_BYTES_1'], INDEX['PLAYER_FLAGS'])
    updates = []
    for row in rows:
        if row.get('name') == 'SMSG_UPDATE_OBJECT' and row.get('direction') == 'from_native':
            for record in records(body(row)):
                if record.get('guid') == 2:
                    fields = {key: value for key, value in record.get('fields', {}).items() if key in wanted}
                    if fields:
                        updates.append({'packet': row, 'fields': fields})
    require(len(updates) == 2 and updates[0]['fields'] == {wanted[0]: 1} and updates[1]['fields'] == {wanted[1]: 2} and
        quartet[2]['time'] <= updates[0]['packet']['time'] < updates[1]['packet']['time'] <= failed_finished and
        updates[1]['packet']['time'] - quartet[2]['time'] < 2,
        'new idle renewal requires exactly ordered seated then AFK sparse owner updates')
    return {'observed_stand_packets': quartet, 'observed_owner_flags_packets': [update['packet'] for update in updates],
        'observed_owner_fields': {'UNIT_FIELD_BYTES_1': 1, 'PLAYER_FLAGS': 2},
        'source_original_owner_fields': {'UNIT_FIELD_BYTES_1': 0, 'PLAYER_FLAGS': 0}, 'since': since, 'until': until}


def consume(t, kind, action):
    path = marker(t, kind)
    output = t.out / 'episode.json'
    require(output.is_absolute() and output.is_relative_to(op.lab.ROOT / 'evidence') and
        all(not p.is_symlink() for p in (output, *output.parents)), 'renewal output must be private owned evidence')
    value = {'schema': 'client442_item_actionbar_idle_renewal_consumed_input_v1', 'kind': kind,
        'created_at': time.time(), 'input_intent': action, 'input_replay_allowed': False,
        'prior_restoration_source': t.receipt['prior_restoration_source'],
        'failed_observer_source': t.receipt['failed_observer_source'], 'entry_source': t.receipt['entry_source'],
        'first_failure_source': t.receipt['first_failure_source'], 'preparation_source': t.receipt['preparation_source'],
        'actor': t.fixture, 'runtime': t.receipt['runtime'], 'native_session': t.receipt['native_session'],
        'code_commit': t.receipt['code_commit'], 'operation_output': str(output)}
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            descriptor = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        except FileExistsError as error:
            raise RuntimeError('idle renewal input is already consumed; refusing replay') from error
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write((json.dumps(value, indent=2) + '\n').encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)
    t.receipt[kind + '_attempt_source'] = op.bound(path)
    t.persist()


class RenewalLayout(recovery.LayoutOnly):
    def __init__(self, t, base, session, public, idle):
        super().__init__(t, base, session, public, idle)
        keys = base['public'].get('keys', {}).get('SITORSTAND')
        require(type(keys) is list and keys and public.get('keys', {}).get('SITORSTAND') == keys,
            'renewal requires the immutable original stock standing binding')
        self.stand = {'kind': 'key', 'value': op.binding_key(keys[0]), 'hold': .4}

    def execute(self, action):
        current_saved, current_resources, current, protected, state, frame = op.assert_live(
            self.base, self.session, self.base['saved'], t=self.t, label='item_idle_renewal_input_preflight')
        observer.layout_state(state, self.base)
        original = self.base['native_state']
        require(strict_equal({key: value for key, value in current.items() if key not in ('pose', 'afk')},
            {key: value for key, value in original.items() if key not in ('pose', 'afk')}) and
            current['pose']['sheath'] == original['pose']['sheath'], 'renewal cannot repair another native field')
        if action == self.stand:
            require(current['pose']['stand'] == 1 and original['pose']['stand'] == 0, 'renewal requires the observed seated owner')
            kind = 'stand'
        else:
            require(action == {'kind': 'chat', 'value': '/afk'} and current['afk'] is True and
                strict_equal(current['pose'], original['pose']) and original['afk'] is False,
                'renewal may only clear the still-observed original AFK mismatch')
            kind = 'afk'
        self.t.receipt.setdefault('renewal_input_preflights', []).append({'kind': kind, 'state': state,
            'frame': frame, 'native_state': current, 'saved': current_saved, 'resources': current_resources,
            'protected_checks': protected, 'observed_at': time.time()})
        self.t.persist()
        consume(self.t, kind, action)
        row = {'kind': kind, 'input': deepcopy(action), 'started_at': time.time(), 'input_replayed': False}
        self.t.receipt['ordinary_inputs'].append(row)
        self.t.receipt.update(input_sent=True)
        self.t.receipt[kind + '_cleanup_started_at'] = row['started_at']
        self.t.persist()
        try:
            self.t.execute(action)
        finally:
            row['finished_at'] = time.time()
            self.t.persist()


def renew(t, preparation, restoration_source, failed_observer_source):
    base, session, entry, prior, failed = authority(t, preparation, restoration_source, failed_observer_source)
    seal = lambda: observer.unchanged_authority(t, preparation, restoration_source, base, session, entry,
        t.receipt['prior_restoration_source'], t.receipt['first_failure_source'])
    seal()
    _, _, native, _, state, frame = op.assert_live(base, session, base['saved'], t=t, label='item_idle_renewal_before')
    observer.layout_state(state, base)
    movement = frame.get('movement', {})
    original = base['native_state']
    require(original['pose']['stand'] == 0 and original['afk'] is False and
        strict_equal(native, {**original, 'pose': {**original['pose'], 'stand': 1}, 'afk': True}) and
        movement.get('speed') == 0 and movement.get('dead') is False and movement.get('in_combat') is False and
        movement.get('on_taxi') is False, 'renewal requires only the fresh exact seated AFK idle mismatch')
    until = time.time()
    idle = idle_packets(op.packet_rows(session, prior['finished_at'], until), session, prior['finished_at'], until, failed['finished_at'])
    metadata = [row for row in entries(op.lab.ROOT / 'logs/modern_world.jsonl') if row.get('session') == session and
        prior['finished_at'] < row.get('time', 0) <= until]
    require(not any(row.get('event') in ('native_player_created', 'world_connection_closed', 'native_stream_closed')
        for row in metadata), 'renewal refuses a recreated or disconnected realm owner')
    idle.update(label='unattributed_observed_post_restoration_idle_state_mismatch', mismatch_observed=True,
        native_before_observation=native, original=original, state=state, frame=frame, qualification_added=False,
        prior_restoration_source=t.receipt['prior_restoration_source'], failed_observer_source=t.receipt['failed_observer_source'],
        native_lifecycle_events=[], native_metadata_rows_checked=len(metadata))
    t.receipt['pre_recon_idle_observation'] = idle
    t.persist()
    public = op.detail(t, 'item_idle_renewal_before_bars')
    op.contract().public_assignments(public, base['saved']['actions'], base['active_spec'])
    require(op.public_same(public, base['public']), 'renewal refuses changed original public action assignments')
    seal()
    checks = op.restore_layout(RenewalLayout(t, base, session, public, idle), base, session)
    require(set(checks) == recovery.LAYOUT_CHECKS and all(value is True for value in checks.values()),
        'renewal requires all nine exact restored layout checks')
    after_saved, after_resources, after_native, protected, state, frame = op.assert_live(base, session, base['saved'],
        t=t, label='item_idle_renewal_restored')
    observer.layout_state(state, base)
    require(strict_equal(after_native, original), 'renewal final native baseline differs')
    t.receipt['stand_cleanup_packets'] = recovery.stand_chain(op.packet_rows(session,
        t.receipt['stand_cleanup_started_at'], time.time()), 0)
    require(op.bound(failed_observer_source) == t.receipt['failed_observer_source'], 'failed observer source changed during renewal')
    for ref in t.receipt['prior_input_sources'].values():
        require(op.bound(Path(ref['path'])) == ref, 'original consumed cleanup markers changed during renewal')
    seal()
    t.receipt.update(after_saved=after_saved, after_resources=after_resources, after_native_state=after_native,
        restored_state=state, restored_frame=frame, protected_checks=protected, layout_restoration_checks=checks,
        restoration_checks={**checks, 'full_saved_baseline': True, 'full_resources_baseline': True,
            'protected_actors': all(protected.values()), 'zero_native_mutation': True},
        actionbar_restored=True, placement_absent=True, completed=True, phase='item_actionbar_restored',
        qualification_added=False, mutation_sent=False, drag_input_sent=False, clear_input_sent=False,
        gameplay_input_replayed=False, recovery_only=True, failed_whole_excluded=True)
    t.persist()


def run(t, preparation, restoration_source, failed_observer_source):
    try:
        renew(t, preparation, restoration_source, failed_observer_source)
    except BaseException as error:
        t.receipt.update(completed=False, failure=t.receipt.get('failure') or type(error).__name__ + ': ' + str(error))
        t.persist()
        if t.receipt.get('baseline') and t.receipt.get('native_session'):
            recovery.retain_failure(t)
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
    for name in ('preparation', 'restoration-source', 'failed-observer-source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    with actor('scout'):
        t = Trial(args.output, controller='code')
        t.receipt.update(controller='code', custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY,
            qualification_added=False, input_sent=False, mutation_sent=False)
        run(t, args.preparation, args.restoration_source, args.failed_observer_source)
        print({key: t.receipt.get(key) for key in ('completed', 'phase', 'failure')}, flush=True)


if __name__ == '__main__':
    main()
