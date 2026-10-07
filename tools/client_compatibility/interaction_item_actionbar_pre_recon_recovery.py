"""Excluded ordinary bag cleanup after a source-bound UI171 reconnaissance failure.

Importing this module is pure. Runtime helpers are used only by the explicit
recovery command; neither drag nor action-bar clear is a recovery input here.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import time

from . import interaction_item_actionbar as op
from . import item_actionbar_sources as sources
from .item_actionbar_contract import ACTION, INDEX, body, records, require

LAYOUT_CHECKS = frozenset(('public_bar', 'bags', 'panels', 'target', 'pose', 'afk',
    'position', 'cursor_empty', 'ui_clean'))
ATTEMPT_FIELDS = ('drag_attempt_source', 'clear_attempt_source', 'drag_intent', 'clear_intent',
    'drag_started_at', 'clear_started_at', 'placement', 'clear_request_proof')


def empty_bag_state(state):
    require(state.get('bags') == [0] or not state.get('bags'), 'only the observed backpack may be open')
    require(not any(state.get(key) for key in ('panels', 'cursor_info', 'spell_targeting',
        'chat_edit_open', 'pending_glyph', 'lua_errors', 'blocked_actions')),
        'pre-recon cleanup refuses other panels, a cursor or targeting')


def unconsumed(entry_ref):
    path = Path(entry_ref['path'])
    require(op.bound(path) == entry_ref, 'original entry source changed')
    for kind in ('drag', 'clear'):
        marker = path.parent / ('item_actionbar_' + kind + '_attempt.json')
        require(not marker.exists() and not marker.is_symlink(),
            'pre-recon cleanup requires no consumed drag or clear attempt')


def authority(t, preparation, failed_source):
    old, session = op.context(t, preparation)
    failed = op.closed(failed_source, successful=False)
    failed_ref, prep_ref = op.bound(failed_source), op.bound(preparation)
    require(failed.get('schema') == 'client442_laya_interactions_v1' and
        failed.get('actor') == t.fixture and failed.get('runtime') == t.receipt['runtime'] and
        failed.get('preparation_source') == failed.get('fixture_source') == prep_ref and
        failed.get('native_session') == session and failed['finished_at'] <= t.receipt['started_at'] and
        failed.get('controller') in ('code', 'code_diagnostic_ordinary_inputs') and failed.get('model') is None and
        failed.get('qualification_added') is False and failed.get('mutation_sent') is False and
        failed.get('input_sent') is True and failed.get('phase') is None and
        failed.get('failure') == 'RuntimeError: actionbars diagnostic did not become visible' and
        failed.get('cases') == [] and failed.get('cleanup') == [] and
        all(key not in failed for key in ATTEMPT_FIELDS) and
        all(key not in failed or failed[key] is False for key in ('drag_input_sent', 'clear_input_sent')),
        'requires the actual closed pre-drag backpack reconnaissance failure')
    base = failed['baseline']
    entry_ref = base['entry_source']
    require(failed.get('entry_source') == entry_ref and base['snapshot'] == old['all_offline_snapshot'],
        'failed recon baseline or original entry authority differs')
    unconsumed(entry_ref)
    entered = op.entry_source(t, preparation, Path(entry_ref['path']), old, session)
    op.baseline_authority(base, entered, old)
    require(not base['state'].get('bags') and not base['state'].get('panels'),
        'original pre-recon layout must have closed bags and panels')
    review_ref = failed.get('backpack_open_review')
    sources.reference(review_ref)
    require(op.bound(Path(review_ref['path'])) == review_ref,
        'original reviewed backpack click source changed')
    reviewed = sources.private_json(Path(review_ref['path']), False)
    point = reviewed.get('point')
    require(reviewed.get('reviewed') is True and reviewed.get('control') == 'MainMenuBarBackpackButton' and
        reviewed.get('source') == entry_ref and reviewed.get('frame') == entered['frame'] and
        reviewed.get('fixture_source_sha256') == prep_ref['sha256'] and
        reviewed.get('pickup_point_inside_button') is True and type(point) is list and len(point) == 2 and
        all(type(value) is int for value in point) and 0 <= point[0] < 1280 and 0 <= point[1] < 720 and
        failed.get('backpack_open_input') == {'kind': 'click', 'value': point} and
        failed.get('backpack_geometry', {}).get('exact_pixels') is True,
        'failed recon requires its sole exact source-bound ordinary backpack click')
    raw = failed.get('raw_stage_failure', {})
    require(raw.get('saved') == base['saved'] and raw.get('resources') == base['resources'] and
        raw.get('native_state') == base['native_state'] and raw.get('input_replayed') is False and
        raw.get('state', {}).get('bags') == [0] and not raw.get('state', {}).get('cursor_info'),
        'retained failed recon facts must prove unchanged saved, native and resource state')
    empty_bag_state(raw['state'])
    t.receipt.update(source=failed_ref, first_failure_source=failed_ref, first_failure=failed['failure'],
        baseline=deepcopy(base), entry_source=entry_ref, recovery_only=True, failed_whole_excluded=True,
        drag_input_sent=False, clear_input_sent=False, gameplay_input_replayed=False, input_sent=False,
        mutation_sent=False, qualification_added=False, pre_recon_recovery=True,
        phase='item_actionbar_pre_recon_recovery_started')
    t.persist()
    return base, session, failed_ref, prep_ref


def zero_mutations(t, base, session):
    unconsumed(base['entry_source'])
    entry = op.closed(Path(base['entry_source']['path']))
    until = time.time()
    rows = op.packet_rows(session, entry['started_at'], until)
    require(not any(row.get('name') == ACTION for row in rows),
        'pre-recon cleanup refuses every item action-bar request')
    proof = op.no_forbidden(base, session, until, t)
    t.receipt['pre_recon_no_mutation_proof'] = {'since': entry['started_at'], 'until': until,
        'native_action_requests': 0, 'packets_checked': len(rows), 'forbidden_input_proof': proof,
        'drag_attempt_consumed': False, 'clear_attempt_consumed': False}
    t.persist()


def stand_chain(rows, wanted):
    """A unique observed request/delivery chain, without inferring its cause."""
    names = ('CMSG_STAND_STATE_CHANGE', 'CMSG_STANDSTATECHANGE', 'SMSG_STAND_STATE_UPDATE')
    relevant = [row for row in rows if row.get('name') in names]
    expected = [('CMSG_STAND_STATE_CHANGE', 'from_client', bytes([wanted])),
        ('CMSG_STANDSTATECHANGE', 'to_native', wanted.to_bytes(4, 'little')),
        ('SMSG_STAND_STATE_UPDATE', 'from_native', bytes([wanted])),
        ('SMSG_STAND_STATE_UPDATE', 'to_client', bytes([wanted]) + b'\0' * 4)]
    matches = [[row for row in relevant if (row.get('name'), row.get('direction'), body(row)) == value]
        for value in expected]
    require(len(relevant) == 4 and all(len(match) == 1 for match in matches),
        'one exact observed sit/stand packet quartet is required')
    result = [match[0] for match in matches]
    require([row['time'] for row in result] == sorted(row['time'] for row in result) and
        result[-1]['time'] - result[0]['time'] < 2, 'observed sit/stand packet timing differs')
    return result


def observed_idle(t, base, session, native, state, frame, failed_source):
    original = base['native_state']
    movement = frame.get('movement', {})
    require(movement.get('speed') == 0 and movement.get('dead') is False and
        movement.get('in_combat') is False and movement.get('on_taxi') is False,
        'pre-recon recovery requires a fresh rendered idle living owner')
    result = {'native_before_observation': native, 'original': original, 'state': state, 'frame': frame,
        'mismatch_observed': native != original, 'qualification_added': False}
    if native != original:
        require(original['pose']['stand'] == 0 and original['afk'] is False and
            native == {**original, 'pose': {**original['pose'], 'stand': 1}, 'afk': True},
            'only the exact observed post-failure seated and AFK mismatch is permitted')
        failed = op.closed(failed_source, successful=False)
        until = time.time()
        rows = op.packet_rows(session, failed['finished_at'], until)
        quartet = stand_chain(rows, 1)
        updates = []
        for row in rows:
            if row.get('direction') == 'from_native' and row.get('name') == 'SMSG_UPDATE_OBJECT':
                for record in records(body(row)):
                    fields = record.get('fields', {})
                    if (record.get('guid') == 2 and fields.get(INDEX['UNIT_FIELD_BYTES_1']) == 1 and
                            fields.get(INDEX['PLAYER_FLAGS']) == 2):
                        updates.append(row)
        require(len(updates) == 1 and quartet[2]['time'] <= updates[0]['time'] and
            updates[0]['time'] - quartet[2]['time'] < 2,
            'one exact owner seated/AFK flags update must follow the observed native sit')
        result.update(label='unattributed_observed_post_failure_idle_state_mismatch',
            since=failed['finished_at'], until=until, observed_stand_packets=quartet,
            observed_owner_flags_packet=updates[0])
    t.receipt['pre_recon_idle_observation'] = result
    t.persist()
    return result


def consume_cleanup(t, base, session, kind, intent):
    """Never replay any cleanup input after a partial or interrupted attempt."""
    entry = Path(base['entry_source']['path'])
    require(op.bound(entry) == base['entry_source'], 'original entry changed before cleanup input')
    marker = entry.parent / ('item_actionbar_pre_recon_' + kind + '_attempt.json')
    value = {'schema': 'client442_item_actionbar_pre_recon_consumed_input_v1', 'kind': kind,
        'created_at': time.time(), 'entry_source': base['entry_source'],
        'preparation_source': t.receipt['preparation_source'], 'first_failure_source': t.receipt['first_failure_source'],
        'actor': t.fixture, 'runtime': t.receipt['runtime'], 'native_session': session,
        'operation_output': str(t.out / 'episode.json'), 'input_intent': intent, 'input_replay_allowed': False}
    directory = os.open(entry.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            descriptor = os.open(marker.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=directory)
        except FileExistsError as error:
            raise RuntimeError('this pre-recon ' + kind + ' input is already consumed; refusing replay') from error
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write((json.dumps(value, indent=2) + '\n').encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)
    t.receipt[kind + '_attempt_source'] = op.bound(marker)
    t.persist()


class LayoutOnly:
    """Allow the existing nine-check restorer only observed stand/AFK cleanup."""
    def __init__(self, t, base, session, public, idle):
        self.t, self.base, self.session, self.idle = t, base, session, idle
        keys = public.get('keys', {}).get('SITORSTAND')
        self.stand = None
        if keys:
            self.stand = {'kind': 'key', 'value': op.binding_key(keys[0]), 'hold': .4}

    def __getattr__(self, name):
        return getattr(self.t, name)

    def clean_panels(self):
        state, frame = self.t.observe('item_pre_recon_clean_confirm')
        empty_bag_state(state)
        require(not state.get('bags'), 'layout verification cannot repeat backpack closure')

    def execute(self, action):
        require(self.idle['mismatch_observed'] is True,
            'an exact original native state permits no pose or AFK cleanup input')
        current, original = op.native_state(self.session), self.base['native_state']
        require({key: value for key, value in current.items() if key not in ('pose', 'afk')} ==
            {key: value for key, value in original.items() if key not in ('pose', 'afk')} and
            current['pose']['sheath'] == original['pose']['sheath'],
            'idle cleanup cannot restore unrelated native state')
        if action == self.stand:
            require(current['pose']['stand'] == 1 and original['pose']['stand'] == 0,
                'only the observed installed standing restoration is permitted')
            kind = 'stand'
        else:
            require(action == {'kind': 'chat', 'value': '/afk'} and current['afk'] is True and
                current['pose'] == original['pose'] and original['afk'] is False,
                'only the still-observed AFK flag may be cleared')
            kind = 'afk'
        consume_cleanup(self.t, self.base, self.session, kind, action)
        self.t.receipt.update(input_sent=True)
        self.t.receipt[kind + '_cleanup_started_at'] = time.time()
        self.t.persist()
        self.t.execute(action)


def recover(t, preparation, failed_source):
    base, session, failed_ref, prep_ref = authority(t, preparation, failed_source)
    zero_mutations(t, base, session)
    _, _, native, _, state, frame = op.assert_live(base, session, base['saved'], t=t,
        label='item_pre_recon_recovery_before')
    empty_bag_state(state)
    idle = observed_idle(t, base, session, native, state, frame, failed_source)
    t.receipt.update(bag_close_before_state=state, bag_close_before_frame=frame, bag_close_input_sent=False)
    t.persist()
    if state.get('bags'):
        action = {'kind': 'key', 'value': 'Escape'}
        consume_cleanup(t, base, session, 'escape', action)
        t.receipt.update(bag_close_input=action, bag_close_input_sent=True, input_sent=True)
        t.persist()
        t.execute(action)
        deadline = time.monotonic() + 16
        while True:
            state, frame = t.observe('item_pre_recon_bag_close_wait')
            t.receipt.update(bag_close_state=state, bag_close_frame=frame)
            t.persist()
            empty_bag_state(state)
            if not state.get('bags'):
                break
            require(time.monotonic() < deadline, 'backpack did not close; refusing Escape replay')
            time.sleep(.2)
    zero_mutations(t, base, session)
    public = op.detail(t, 'item_pre_recon_closed_bars')
    op.contract().public_assignments(public, base['saved']['actions'], base['active_spec'])
    require(op.public_same(public, base['public']), 'pre-recon cleanup requires every original public action')
    current = op.native_state(session)
    original = base['native_state']
    allowed = [original]
    if idle['mismatch_observed']:
        allowed.extend([{**original, 'pose': {**original['pose'], 'stand': 1}, 'afk': flag} for flag in (False, True)])
    require(current in allowed and all(state.get('target', {}).get(key) == base['state'].get('target', {}).get(key)
        for key in ('exists', 'guid', 'name')), 'closed layout cannot restore unrelated target, pose or AFK state')
    checks = op.restore_layout(LayoutOnly(t, base, session, public, idle), base, session)
    require(set(checks) == LAYOUT_CHECKS and all(value is True for value in checks.values()),
        'pre-recon recovery requires all nine original layout checks')
    after_saved, after_resources, native, protected = op.assert_live(base, session, base['saved'])
    require(native == base['native_state'], 'pre-recon recovery native baseline differs')
    if t.receipt.get('stand_cleanup_started_at') is not None:
        t.receipt['stand_cleanup_packets'] = stand_chain(op.packet_rows(session,
            t.receipt['stand_cleanup_started_at'], time.time()), 0)
    zero_mutations(t, base, session)
    require(op.bound(failed_source) == failed_ref and op.bound(preparation) == prep_ref,
        'immutable first failure or preparation changed during cleanup')
    t.receipt.update(after_saved=after_saved, after_resources=after_resources, after_native_state=native,
        protected_checks=protected, restoration_checks={**checks, 'full_saved_baseline': True,
            'full_resources_baseline': True, 'protected_actors': all(protected.values()),
            'zero_native_mutation': True}, layout_restoration_checks=checks, placement_absent=True,
        actionbar_restored=True, completed=True, phase='item_actionbar_restored')
    t.persist()


def retain_failure(t):
    """Retain available facts without asking an open bag for a passive bar page."""
    session = t.receipt.get('native_session')
    facts = {'observed_at': time.time(), 'input_replayed': False}
    for key, read in (('saved', op.saved), ('resources', lambda: op.resources(session)),
            ('native_state', lambda: op.native_state(session)),
            ('packets', lambda: op.packet_rows(session,
                op.closed(Path(t.receipt['entry_source']['path']))['started_at'], time.time())),
            ('rendered', lambda: t.observe('item_pre_recon_recovery_failure'))):
        try:
            value = read()
            if key == 'rendered':
                facts['state'], facts['frame'] = value
            else:
                facts[key] = value
        except BaseException as error:
            facts.setdefault('errors', {})[key] = type(error).__name__ + ': ' + str(error)
        t.receipt['raw_pre_recon_recovery_failure'] = deepcopy(facts)
        t.persist()


def run(t, preparation, failed_source):
    try:
        recover(t, preparation, failed_source)
    except BaseException as error:
        t.receipt.update(completed=False, failure=t.receipt.get('failure') or type(error).__name__ + ': ' + str(error))
        t.persist()
        if t.receipt.get('baseline') and t.receipt.get('native_session'):
            retain_failure(t)
        if not isinstance(error, Exception):
            raise
    finally:
        t.receipt['finished_at'] = time.time()
        t.persist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('preparation', 'source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    from .interaction_social import actor
    from .interaction_trial import Trial
    from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
    with actor('scout'):
        trial = Trial(args.output, controller='code')
        trial.receipt.update(custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY,
            qualification_added=False, input_sent=False, mutation_sent=False)
        run(trial, args.preparation, args.source)
        print(json.dumps({key: trial.receipt.get(key) for key in ('completed', 'phase', 'failure')}), flush=True)


if __name__ == '__main__':
    main()
