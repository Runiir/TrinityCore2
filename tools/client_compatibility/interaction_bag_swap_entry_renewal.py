"""Read-only same-login entry renewal after the immutable initial guard failure.

The original wire interval and C1 sources remain unchanged. This new receipt
captures current C3 facts, carrying exact Git bytes for both code epochs and any
separately reviewed, excluded idle housekeeping. No input or login is submitted.
"""
import argparse
from copy import deepcopy
import json
import hashlib
from pathlib import Path
import subprocess
import time

from . import lab_runtime as lab
from . import bag_swap_contract as contract
from .bag_swap_login_sync import login_sync
from .bag_swap_renewal import (PHASE, C1_COMMIT, TRANSITION_SCHEMA,
    carry_code_sources, validate_entry)
from .bag_swap_sources import bound, closed
from .item_actionbar_contract import require, strict_equal, public_assignments


def retain_failed_captures(t, paths):
    from .interaction_bag_swap_idle_housekeeping import OWN_FILES, DEPENDENCIES
    refs, epochs = [], []
    for path in paths:
        value, ref = closed(path, False), bound(path)
        rows = []
        for name in OWN_FILES + DEPENDENCIES:
            raw = subprocess.check_output(['git', 'show', value['code_commit'] + ':' + name], cwd=lab.REPO)
            rows.append({'path': str(lab.REPO / name), 'sha256': hashlib.sha256(raw).hexdigest(),
                'bytes': len(raw), 'raw_hex': raw.hex()})
        refs.append(ref)
        epochs.append({'source': ref, 'code_commit': value['code_commit'], 'committed_source_bytes': rows})
    t.receipt.update(excluded_idle_capture_sources=refs, excluded_idle_capture_code_sources=epochs)
    t.persist()


def renewal(t, preparation, failed_path, precision_path, housekeeping_path=None, excluded_captures=()):
    from . import interaction_bag_swap_continuation as continuation
    from . import interaction_bag_swap as operation
    from .bag_swap_evidence import local_store
    from .bag_swap_projection import source_identities
    from .bag_swap_preservation import online_preservation
    from .interaction_item_actionbar_parked_selection_capture import frame_identity, game_identity
    ready = continuation.prepared(t, preparation, online=True)
    failed = closed(failed_path, False)
    ready_ref, failed_ref, precision_ref = map(bound, (preparation, failed_path, precision_path))
    exact = continuation.precision_source(precision_path, ready_ref, ready['all_offline_snapshot'])
    require(ready['code_commit'] == failed.get('code_commit') == exact.get('code_commit') == C1_COMMIT and
        failed.get('preparation_source') == ready_ref and failed.get('precision_source') == precision_ref and
        failed.get('actor') == t.fixture and failed.get('runtime') == t.receipt['runtime'] and
        failed.get('native_session') == ready['native_session'] and failed['finished_at'] < t.receipt['started_at'] and
        t.receipt['code_commit'] != C1_COMMIT and t.receipt['committed_sources'] == source_identities(lab.REPO),
        'renewal requires unchanged failed C1 source and actual committed current controller')
    owner, baseline = ready['native_session'], ready['all_offline_snapshot']
    since, login_until = failed['started_at'], failed['entry_input_finished_at']
    t.receipt.update(phase='bags_swap_entry_renewal_started', original_entry_source=failed_ref,
        original_preparation_source=ready_ref, preparation_source=ready_ref, precision_source=precision_ref,
        native_session=owner, all_offline_snapshot=baseline, native_before_entry=baseline['2']['native'],
        authority_source=ready['authority_source'], runtime_authority_source=ready['runtime_authority_source'],
        predecessor=ready['predecessor'], predecessor_dvc_pointer=ready['predecessor_dvc_pointer'],
        original_login_interval={'since': since, 'until': login_until},
        original_failure_excluded=True, login_input_replayed=False, input_sent=False, mutation_sent=False)
    t.persist()
    retain_failed_captures(t, excluded_captures)
    old_sources = carry_code_sources(ready, t.out / 'original_code_sources')
    new_sources = carry_code_sources(t.receipt, t.out / 'current_code_sources')
    t.receipt['repair_code_transition'] = {'schema': TRANSITION_SCHEMA, 'from_code_commit': C1_COMMIT,
        'to_code_commit': t.receipt['code_commit'], 'original_sources': deepcopy(ready['committed_sources']),
        'carried_sources': old_sources, 'committed_sources': deepcopy(t.receipt['committed_sources']),
        'current_carried_sources': new_sources}
    t.persist()
    game_identity(continuation.focus(), ready['frame'])
    state, frame = t.observe('bags_swap_entry_renewed')
    frame_identity(frame, t.receipt['runtime'], ready['frame'])
    now, resources, native = operation.snapshot(), operation.resources(owner), operation.native_state(owner)
    online_preservation(baseline, now)
    contract.item_resources(resources)
    require(strict_equal(native, {'pose': {'stand': 0, 'sheath': 0}, 'afk': False, 'selection': 0,
        'health': 60, 'max_health': 60, 'power': 0, 'xp': 0, 'next_xp': 400, 'summon': 0}),
        'renewal requires exact actual original standing/non-AFK/target/resource state')
    from .item_actionbar_evidence import empty_cursor
    require(state.get('guid') == t.guid and 'cursor_info' in state and empty_cursor(state['cursor_info']) and
        not any(state.get(k) for k in ('bags', 'panels', 'spell_targeting', 'lua_errors', 'blocked_actions', 'chat_edit_open')) and
        frame['movement'].get('speed') == 0 and all(frame['movement'].get(k) is False for k in ('dead', 'in_combat', 'on_taxi')),
        'renewal requires its fresh source-owned closed, idle ordinary UI')
    public = continuation.bars(t, 'renewed_original_layout')
    active = baseline['2']['native']['activeTalentGroup']
    public_assignments(public, baseline['2']['saved']['actions'], active)
    original = continuation.native_baseline(t)
    require(original['pose'] == native['pose'] and original['afk'] is False and original['selection']['native_guid'] == 0,
        'fresh renewed native baseline differs')
    until = time.time()
    raw = contract.packet_rows(list(continuation.packets()), owner, since, until)
    events = [r for r in continuation.metadata() if since <= r.get('time', 0) <= until]
    pose = [baseline['2']['native'][k] for k in ('position_x', 'position_y', 'position_z', 'orientation')]
    sync = login_sync(raw, events, owner, since, login_until, pose)
    events = [r for r in events if r.get('session') in (owner, sync['instance_session'])]
    t.receipt.update(raw_entry_packets=raw, raw_entry_events=events, login_sync=sync,
        login_packets=sync['login_packets'], current_snapshot=now, saved=baseline['2']['saved'],
        resources=resources, public=public, active_spec=active, state=state, frame=frame,
        native_original=original, native_state=native, finished_at=until,
        phase=PHASE, completed=True)
    if housekeeping_path is not None:
        from . import bag_swap_idle
        house = closed(housekeeping_path)
        t.receipt['idle_housekeeping_source'] = bound(housekeeping_path)
        t.receipt['idle_housekeeping'] = bag_swap_idle.validate_receipt(local_store(), house, ready, failed, t.receipt)
        require(house['finished_at'] < t.receipt['started_at'], 'excluded housekeeping must finish before renewal capture')
    kwargs = {'login_sync': sync}
    if 'idle_housekeeping' in t.receipt:
        kwargs['idle_housekeeping'] = t.receipt['idle_housekeeping']
    owner_proof = contract.native_replay(raw, owner, since, until, **kwargs)
    t.receipt.update(native_owner_proof=owner_proof, owner_packets=owner_proof['packets'],
        checks=dict.fromkeys(('ordinary_login', 'native_owner', 'saved_baseline', 'protected_actors', 'public_level1', 'empty_cursor'), True))
    t.persist()
    validate_entry(local_store(), ready, t.receipt, exact, ready_ref, bound(t.out / 'episode.json'), precision_ref)
    require(bound(preparation) == ready_ref and bound(failed_path) == failed_ref and bound(precision_path) == precision_ref and
        continuation.runtime() == t.receipt['runtime'] and continuation.session(t.fixture) == owner,
        'original sources/runtime/session changed during read-only renewal')
    game_identity(continuation.focus(), frame)
    t.receipt['validation_finished_at'] = time.time()
    t.persist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'preparation', 'failure', 'precision'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--housekeeping', type=Path)
    parser.add_argument('--excluded-capture', type=Path, action='append', default=[])
    args = parser.parse_args()
    from .interaction_bag_swap_continuation import scout, SCRIPT_BOUNDARY, execute_trial
    with scout():
        from .interaction_trial import Trial
        from .bag_swap_projection import source_identities
        t = Trial(args.output, controller='code')
        t.receipt.update(controller='code', committed_sources=source_identities(lab.REPO),
            custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY,
            qualification_added=False, input_sent=False, mutation_sent=False)
        execute_trial(t, lambda: renewal(t, args.preparation, args.failure, args.precision, args.housekeeping, args.excluded_capture))
        print(json.dumps({k: t.receipt.get(k) for k in ('completed', 'phase', 'failure')}))


if __name__ == '__main__':
    main()
