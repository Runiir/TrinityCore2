"""One occupied Hearthstone backpack swap and its exact ordinary restoration.

Each immutable entry permits one forward and one reverse drag. An interrupted
input remains consumed, and diagnostics preserve its intent and raw facts.
"""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import time

from . import lab_runtime as lab
from .item_actionbar_contract import require, finite, strict_equal, public_assignments
from .bag_swap_sources import bound, closed, linked, reference
from . import bag_swap_contract as contract
from .bag_swap_projection import delivered_slots, source_identities
from .bag_swap_renewal import PHASE as RENEWED_PHASE, login_interval

AUTOSAVE_BOUND_SECONDS = 150
AUTOSAVE_HEARTBEAT_SECONDS = 2
POSE_KEYS = ('position_x', 'position_y', 'position_z', 'orientation', 'map')


def runtime_helpers():
    from . import interaction_item_actionbar
    return interaction_item_actionbar


def snapshot():
    return runtime_helpers().snapshot()


def resources(session):
    return runtime_helpers().resources(session)


def native_state(session):
    return runtime_helpers().native_state(session)


def detail(t, label):
    return runtime_helpers().detail(t, label)


def packets(session, since, until):
    return runtime_helpers().packet_rows(session, since, until)


def context(t, preparation, entry_path=None):
    from .interaction_bag_swap_continuation import prepared, session
    ready = prepared(t, preparation, online=True)
    owner = session(t.fixture)
    require(owner == ready['native_session'], 'occupied swap must use its fresh prepared owner session')
    current_sources = source_identities(lab.REPO)
    require(current_sources == t.receipt.get('committed_sources'),
        'occupied swap requires its exact frozen controller/source identities')
    if ready.get('committed_sources') != current_sources or ready.get('code_commit') != t.receipt.get('code_commit'):
        require(entry_path is not None, 'changed code requires its explicit source-bound renewed entry')
        renewed = closed(entry_path)
        require(renewed.get('phase') == RENEWED_PHASE and renewed.get('code_commit') == t.receipt.get('code_commit') and
            renewed.get('committed_sources') == current_sources, 'current controller differs from the reviewed renewal epoch')
        validate_renewal(ready, renewed, bound(preparation), bound(entry_path))
    t.receipt.update(preparation_source=bound(preparation), native_session=owner,
        authority_source=ready['authority_source'], predecessor=ready['predecessor'])
    t.persist()
    return ready, owner


def validate_renewal(ready, entry, ready_ref, entry_ref):
    from .bag_swap_evidence import local_store
    from .bag_swap_renewal import validate_entry
    precision_ref = entry['precision_source']
    return validate_entry(local_store(), ready, entry, linked(precision_ref), ready_ref, entry_ref, precision_ref)


def history(entry):
    interval = login_interval(entry)
    kwargs = {}
    if entry.get('phase') == RENEWED_PHASE:
        kwargs['login_sync'] = entry['login_sync']
        if 'idle_housekeeping' in entry:
            kwargs['idle_housekeeping'] = entry['idle_housekeeping']
    return interval, kwargs


def entry_authority(t, preparation, path, ready, owner):
    entry = closed(path)
    require(entry.get('phase') in ('bags_swap_entered', RENEWED_PHASE) and entry.get('actor') == t.fixture and
        entry.get('runtime') == t.receipt['runtime'] and entry.get('native_session') == owner and
        entry.get('preparation_source') == bound(preparation) and
        entry.get('all_offline_snapshot') == ready['all_offline_snapshot'] and
        entry.get('committed_sources') == t.receipt.get('committed_sources') and
        entry.get('code_commit') == t.receipt.get('code_commit') and
        entry['finished_at'] <= t.receipt['started_at'], 'exact frozen ordinary swap entry differs')
    if entry.get('phase') == RENEWED_PHASE:
        validate_renewal(ready, entry, bound(preparation), bound(path))
    else:
        require(entry.get('committed_sources') == ready['committed_sources'] and
            entry.get('code_commit') == ready.get('code_commit'), 'original entry code epoch differs')
    interval, kwargs = history(entry)
    raw = packets(owner, interval['since'], entry['finished_at'])
    chain = contract.login_packets(raw, owner, interval['since'], interval['until'])
    replay = contract.native_replay(raw, owner, interval['since'], entry['finished_at'], **kwargs)
    require(entry.get('login_packets') == [chain[k] for k in ('modern', 'request', 'verify', 'delivered')] and
        entry.get('native_owner_proof') == replay, 'retained swap entry differs from actual raw journal')
    contract.item_resources(entry['resources'])
    t.receipt.update(entry_source=bound(path), precision_source=entry['precision_source'])
    t.persist()
    return entry


def current(t, base, owner, *, swapped, allow_cursor=False, closed_layout=False, label='swap_current'):
    now = snapshot()
    from .bag_swap_preservation import online_preservation
    # The SQL projection may lag the exact native move until native autosave/logout.
    persisted_swapped = now['2']['inventory'] != base['snapshot']['2']['inventory']
    preserved = online_preservation(base['snapshot'], now, swapped=persisted_swapped)
    native = resources(owner)
    contract.native_resources(base['resources'], native, swapped=swapped)
    pose = native_state(owner)
    original = base['native_state']
    require(all(pose.get(k) == v for k, v in {'health': 60, 'max_health': 60, 'power': 0,
        'xp': 0, 'next_xp': 400, 'summon': 0}.items()) and
        pose['selection'] == original['selection'] and pose['pose'] == original['pose'],
        'occupied swap changed health, power, XP, target, pose or summon')
    state, frame = t.observe(label)
    from .interaction_item_actionbar_parked_selection_capture import frame_identity
    frame_identity(frame, t.receipt['runtime'], base['frame'])
    require(state.get('player') == 'Harnesstwo' and state.get('level') == 1 and
        state.get('world_position') == base['state']['world_position'] and
        not state.get('spell_targeting') and not state.get('lua_errors') and not state.get('blocked_actions') and
        not frame.get('movement', {}).get('in_combat') and not frame.get('movement', {}).get('speed') and
        not frame.get('movement', {}).get('dead') and (allow_cursor or not state.get('cursor_info')),
        'occupied swap rendered owner, position, combat or cursor differs')
    if closed_layout:
        require(swapped is False and base['state'].get('bags') == state.get('bags') == [] and
            state.get('bag_items') in (None, []), 'restored closed backpack must match its original layout')
    else:
        contract.public_items(state, native, swapped=swapped)
    public = detail(t, label + '_bars')
    public_assignments(public, base['saved']['actions'], base['active_spec'])
    require(runtime_helpers().public_same(public, base['public']), 'occupied swap changed public action assignments')
    return {'snapshot': now, 'resources': native, 'native_state': pose, 'state': state,
        'frame': frame, 'public': public, 'preservation': preserved}


def guard(base, owner, until, t=None):
    entry = linked(base['entry_source'])
    interval, kwargs = history(entry)
    raw = packets(owner, interval['since'], until)
    safe = contract.forbidden_packets(raw, owner, interval['since'], until, **kwargs)
    native = contract.native_replay(raw, owner, interval['since'], until,
        rest_threshold=entry['native_owner_proof']['rest_threshold'], **kwargs)
    if t is not None:
        t.receipt.update(forbidden_input_proof=safe, native_owner_proof=native, owner_packets=native['packets'])
        t.persist()
    return safe


def native_effect(base, owner, until, *, swapped):
    entry = linked(base['entry_source'])
    interval, kwargs = history(entry)
    raw = packets(owner, interval['since'], until)
    replay = contract.native_replay(raw, owner, interval['since'], until,
        rest_threshold=entry['native_owner_proof']['rest_threshold'], **kwargs)
    transition = replay['native_inventory_transitions'][-1]
    expected = [contract.DESTINATION['guid'], contract.SOURCE['guid']] if swapped else [
        contract.SOURCE['guid'], contract.DESTINATION['guid']]
    require(transition['guids'] == expected and len(replay['native_inventory_transitions']) == (2 if swapped else 3),
        'one attributable native occupied-swap effect required before public delivery')
    return transition


def recon(t, preparation, entry_path, review_path):
    ready, owner = context(t, preparation, entry_path)
    entry = entry_authority(t, preparation, entry_path, ready, owner)
    state, frame = t.observe('swap_original')
    from .interaction_item_actionbar_parked_selection_capture import frame_identity
    frame_identity(frame, t.receipt['runtime'], entry['frame'])
    require(not any(state.get(k) for k in ('bags', 'panels', 'cursor_info', 'spell_targeting', 'chat_edit_open')),
        'occupied swap requires its exact original closed-panel entry')
    native = native_state(owner)
    original = entry['native_original']
    require(native['pose'] == original['pose'] and native['selection'] == original['selection']['native_guid'] and
        native['afk'] == original['afk'], 'occupied swap entry pose, target or AFK changed')
    base = {'snapshot': ready['all_offline_snapshot'], 'saved': entry['saved'], 'resources': entry['resources'],
        'public': entry['public'], 'state': state, 'frame': frame, 'active_spec': entry['active_spec'],
        'entry_source': bound(entry_path), 'precision_source': entry['precision_source'],
        'native_state': native, 'native_original': original}
    t.receipt['baseline'] = base
    t.persist()
    checked = runtime_helpers().reviewed(t, review_path, 'MainMenuBarBackpackButton')
    point = checked.get('point')
    require(checked.get('source') == bound(entry_path) and checked.get('frame') == entry['frame'] and
        checked.get('pickup_point_inside_button') is True and valid_point(point),
        'ordinary bag opening requires the source-owned closed-entry icon review')
    geometry = runtime_helpers().screen_geometry(t, entry_path, entry, state, frame, (point,))
    t.receipt.update(backpack_open_review=bound(review_path), backpack_open_input={'kind': 'click', 'value': point},
        backpack_geometry=geometry, input_sent=True)
    t.persist()
    from .interaction_item_actionbar_parked_selection_capture import game_identity
    from .owned_input import focus
    game_identity(focus(), entry['frame'])
    t.execute(t.receipt['backpack_open_input'])
    found = current(t, base, owner, swapped=False, label='swap_opened')
    require(found['state'].get('bags') == [0], 'ordinary source-owned backpack did not open alone')
    source_control, destination_control = occupied_controls(t, reverse=False)
    t.receipt.update(**found, source_control=source_control, destination_control=destination_control,
        completed=True, phase='bags_swap_forward_ready')
    guard(base, owner, time.time(), t)


def valid_point(point):
    return type(point) is list and len(point) == 2 and all(type(v) is int for v in point) and \
        0 <= point[0] < 1280 and 0 <= point[1] < 720


def prior(t, preparation, source, phases, *, failed=False):
    value = linked(bound(source), not failed)
    entry_ref = value.get('entry_source') or value.get('baseline', {}).get('entry_source')
    reference(entry_ref)
    ready, owner = context(t, preparation, Path(entry_ref['path']))
    require(value.get('phase') in phases and value.get('preparation_source') == bound(preparation) and
        value.get('actor') == t.fixture and value.get('runtime') == t.receipt['runtime'] and
        value.get('native_session') == owner and value.get('code_commit') == t.receipt.get('code_commit') and
        value.get('committed_sources') == t.receipt.get('committed_sources') and
        value['finished_at'] <= t.receipt['started_at'], 'exact source-bound occupied swap stage differs')
    require(bound(entry_ref['path']) == entry_ref, 'occupied swap original entry bytes changed')
    entry = entry_authority(t, preparation, Path(entry_ref['path']), ready, owner)
    base = value['baseline']
    require(base['snapshot'] == ready['all_offline_snapshot'] and base['saved'] == entry['saved'] and
        base['resources'] == entry['resources'] and base['public'] == entry['public'] and
        base['entry_source'] == entry_ref, 'occupied swap whole baseline differs')
    t.receipt.update(source=bound(source), baseline=deepcopy(base))
    for key in ('forward_source', 'forward', 'forward_attempt_source', 'reverse_attempt_source',
            'forward_started_at', 'forward_finished_at', 'forward_packets', 'forward_projection',
            'forward_snapshot', 'forward_resources', 'autosave', 'forward_cursor', 'cursor_cancellations',
            'reverse', 'reverse_started_at', 'reverse_finished_at', 'reverse_packets', 'reverse_projection',
            'reverse_resources', 'reverse_snapshot', 'reverse_cursor', 'first_failure_source',
            'recovery_only', 'failed_whole_excluded', 'gameplay_input_replayed'):
        if key in value:
            t.receipt[key] = deepcopy(value[key])
    if value.get('phase') == 'bags_swap_forward':
        t.receipt['forward_source'] = bound(source)
    t.persist()
    return ready, owner, value


def capture(t, preparation, source):
    _, owner, old = prior(t, preparation, source, ('bags_swap_forward_ready', 'bags_swap_forward',
        'bags_swap_reverse_ready', 'bags_swap_cursor_cancelled', 'bags_swap_reverse'))
    swapped = bool(old.get('forward')) and old.get('reverse') is None
    found = current(t, old['baseline'], owner, swapped=swapped, allow_cursor=True, label='swap_review')
    phase = 'bags_swap_restore_ready' if old.get('reverse') is not None else (
        'bags_swap_reverse_ready' if swapped else 'bags_swap_forward_ready')
    source_control, destination_control = occupied_controls(t, reverse=swapped)
    t.receipt.update(**found, source_control=source_control, destination_control=destination_control,
        swapped=swapped, input_sent=False, completed=True, phase=phase)
    guard(old['baseline'], owner, time.time(), t)


def consumed_attempt(t, base, owner, kind, intent):
    require(kind in ('forward', 'reverse') and type(intent) is dict, 'one typed occupied-swap attempt required')
    entry = Path(base['entry_source']['path'])
    require(entry.is_absolute() and entry.is_relative_to(lab.ROOT / 'evidence') and entry.name == 'episode.json' and
        bound(entry) == base['entry_source'] and t.out.is_relative_to(lab.ROOT / 'evidence') and
        all(not p.is_symlink() for p in (entry, *entry.parents, t.out, *t.out.parents)),
        'attempt requires the immutable original private entry')
    marker = entry.parent / ('bag_swap_' + kind + '_attempt.json')
    value = {'schema': 'client442_bag_swap_consumed_attempt_v1', 'operation': 'bags.swap_item',
        'kind': kind, 'consumed': True, 'input_replay_allowed': False, 'created_at': time.time(),
        'entry_source': base['entry_source'], 'preparation_source': t.receipt['preparation_source'],
        'actor': t.fixture, 'runtime': t.receipt['runtime'], 'native_session': owner,
        'operation_output': str(t.out / 'episode.json'), 'input_intent': intent}
    directory = os.open(entry.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            descriptor = os.open(marker.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=directory)
        except FileExistsError as error:
            t.receipt.update(attempt_consumption_refused={'kind': kind, 'path': str(marker), 'input_replayed': False})
            t.persist()
            raise RuntimeError('this occupied ' + kind + ' drag is already consumed; input replay refused') from error
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write((json.dumps(value, indent=2, sort_keys=True) + '\n').encode())
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)
    t.receipt[kind + '_attempt_source'] = bound(marker)
    t.persist()


def occupied_controls(t, *, reverse):
    source_slot, destination_slot = (2, 1) if reverse else (1, 2)
    from .interaction_inventory_moves import slot_control
    source_control, destination_control = slot_control(t, 0, source_slot), slot_control(t, 0, destination_slot)
    require(source_control is not None and destination_control is not None, 'two occupied observed controls required')
    return source_control, destination_control


def reviewed_points(t, source, old, review_path, *, reverse):
    source_slot, destination_slot = (2, 1) if reverse else (1, 2)
    source_control, destination_control = occupied_controls(t, reverse=reverse)
    checked = runtime_helpers().reviewed(t, review_path, 'bags.swap_item')
    start, end = checked.get('point'), checked.get('destination_point')
    require(checked.get('source') == bound(source) and checked.get('frame') == old['frame'] and
        checked.get('source_control') == source_control == old.get('source_control') and
        checked.get('destination_control') == destination_control == old.get('destination_control') and
        type(checked.get('source_slot')) is int and checked['source_slot'] == source_slot and
        type(checked.get('destination_slot')) is int and checked['destination_slot'] == destination_slot and
        checked.get('item') == 6948 and checked.get('item_guid') == 41 and checked.get('occupied_item') == 58231 and
        checked.get('occupied_item_guid') == 33 and checked.get('pickup_point_inside_button') is True and
        checked.get('destination_point_inside_button') is True and valid_point(start) and valid_point(end) and start != end,
        'drag requires exact source-owned occupied controls, item identities and physical points')
    require(start == runtime_helpers().point(source_control) and end == runtime_helpers().point(destination_control),
        'drag review points differ from both freshly observed controls')
    return start, end


def autosave(t, base, owner):
    """Poll read-only state; the native timer alone persists the forward layout."""
    from .bag_swap_preservation import online_preservation
    config = lab.ROOT / 'config/worldserver.conf'
    native_source = lab.REPO / 'src/server/game/Entities/Player/Player.cpp'
    require(re.findall(r'^\s*PlayerSaveInterval\s*=\s*([0-9]+)\s*(?:#.*)?$', config.read_text(), re.MULTILINE) == ['90000'] and
        'm_nextSave = urand(m_nextSave / 2, m_nextSave * 3 / 2);' in native_source.read_text() and
        'm_nextSave = sWorld->getIntConfig(CONFIG_INTERVAL_SAVE);' in native_source.read_text(),
        'native forward autosave requires its actual 90000ms interval and randomized 45–135s first timer')
    started, samples = time.monotonic(), []
    deadline = started + AUTOSAVE_BOUND_SECONDS
    while True:
        now = snapshot()
        saved_swapped = now['2']['inventory'] != base['snapshot']['2']['inventory']
        online_preservation(base['snapshot'], now, swapped=saved_swapped)
        contract.native_resources(base['resources'], resources(owner), swapped=True)
        guard(base, owner, time.time(), t)
        samples.append({'observed_at': time.time(), 'saved_swapped': saved_swapped})
        observed = time.monotonic()
        t.receipt['autosave'] = {'mechanism': 'native_PlayerSaveInterval', 'bound_seconds': AUTOSAVE_BOUND_SECONDS,
            'heartbeat_seconds': AUTOSAVE_HEARTBEAT_SECONDS, 'samples': samples, 'elapsed_seconds': observed - started,
            'saveall_sent': False, 'sql_write_sent': False, 'persisted': saved_swapped,
            'configured_interval_ms': 90000, 'first_timer_ms': [45000, 135000],
            'config_source': bound(config), 'native_timer_source': bound(native_source)}
        t.persist()
        require(observed <= deadline, 'native forward autosave did not persist within its bounded timer')
        if saved_swapped:
            return now
        require(time.monotonic() < deadline, 'native forward autosave did not persist within its bounded timer')
        time.sleep(min(AUTOSAVE_HEARTBEAT_SECONDS, max(0, deadline - time.monotonic())))


def retain_raw(t, owner, since, label):
    facts = {'observed_at': time.time(), 'input_replayed': False}
    for key, read in (('packets', lambda: packets(owner, since, time.time())), ('snapshot', snapshot),
            ('resources', lambda: resources(owner)), ('native_state', lambda: native_state(owner)),
            ('rendered', lambda: t.observe(label))):
        try:
            facts[key] = read()
        except BaseException as error:
            facts[key + '_failure'] = f'{type(error).__name__}: {error}'
    t.receipt['raw_' + label] = facts
    t.persist()


def drag(t, preparation, source, review_path, *, reverse=False, recovery=False):
    phases = ('bags_swap_recovery_reverse_ready',) if recovery else (
        ('bags_swap_reverse_ready', 'bags_swap_forward', 'bags_swap_cursor_cancelled') if reverse else ('bags_swap_forward_ready',))
    _, owner, old = prior(t, preparation, source, phases)
    base = old['baseline']
    before = current(t, base, owner, swapped=reverse, label='swap_before_drag')
    require(before['state'].get('bags') == [0], 'occupied swap requires the source-owned open backpack')
    start, end = reviewed_points(t, source, old, review_path, reverse=reverse)
    geometry = runtime_helpers().screen_geometry(t, source, old, before['state'], before['frame'], (start, end))
    kind = 'reverse' if reverse else 'forward'
    intent = {'kind': 'drag', 'start': start, 'end': end, 'item': 6948, 'item_guid': 41,
        'occupied_item': 58231, 'occupied_item_guid': 33, 'source_slot': 2 if reverse else 1,
        'destination_slot': 1 if reverse else 2}
    consumed_attempt(t, base, owner, kind, intent)
    t.receipt.update(**{kind + '_intent': intent, kind + '_review': bound(review_path),
        kind + '_review_source': bound(source), kind + '_geometry': geometry,
        kind + '_started_at': time.time(), kind + '_input_sent': True}, input_sent=True,
        phase='bags_swap_' + kind + '_attempted')
    if recovery:
        t.receipt.update(first_failure_source=old['first_failure_source'], recovery_only=True, failed_whole_excluded=True,
            gameplay_input_replayed=False)
    t.persist()
    try:
        from .interaction_item_actionbar_parked_selection_capture import game_identity
        from .owned_input import focus
        game_identity(focus(), base['frame'])
        t.execute(intent)
        found = current(t, base, owner, swapped=not reverse, allow_cursor=True, label='swap_after_' + kind)
        until = time.time()
        raw = packets(owner, t.receipt[kind + '_started_at'], until)
        pair = contract.swap_packets(raw, owner, t.receipt[kind + '_started_at'], until, reverse=reverse)
        transition = native_effect(base, owner, until, swapped=not reverse)
        projection = delivered_slots(raw, owner, transition['time'], until, swapped=not reverse)
        require(projection['delivery']['time'] > transition['time'], 'public GUID delivery must follow its actual native inventory effect')
        t.receipt.update(**{kind: pair, kind + '_finished_at': until, kind + '_packets': raw,
            kind + '_projection': projection, kind + '_resources': found['resources'],
            kind + '_native_transition': transition,
            kind + '_snapshot': found['snapshot'], kind + '_cursor': found['state'].get('cursor_info')}, **found)
        t.persist()
        guard(base, owner, until, t)
        if not reverse:
            persisted = autosave(t, base, owner)
            t.receipt.update(forward_snapshot=persisted)
        t.receipt.setdefault('cases', []).append({'id': 'bags.swap_item_restore' if reverse else 'bags.swap_item',
            'status': 'bags_swap_reverse_pass' if reverse else 'bags_swap_forward_pass',
            'selected': 'drag', 'selection_source': 'code', 'request': None, 'response': None,
            'input': intent, 'after': found['state'], 'after_frame': found['frame'],
            'oracle': {'exact_request_pair': pair, 'delivered_guids': projection,
                'native_occupied_swap': True, 'rendered_identities': True}})
        t.receipt.update(completed=True, phase='bags_swap_reverse' if reverse else 'bags_swap_forward')
    except BaseException:
        retain_raw(t, owner, t.receipt[kind + '_started_at'], kind + '_failure')
        raise


def cancel_cursor(t, preparation, source, review_path):
    _, owner, old = prior(t, preparation, source, ('bags_swap_forward', 'bags_swap_reverse', 'bags_swap_reverse_ready',
        'bags_swap_recovery_reverse_ready', 'bags_swap_recovery_restore_ready'))
    swapped = old.get('swapped', old.get('reverse') is None)
    found = current(t, old['baseline'], owner, swapped=swapped, allow_cursor=True, label='swap_cursor_before')
    cursor = found['state'].get('cursor_info')
    expected_id = 58231 if swapped else 6948
    require(type(cursor) is list and len(cursor) >= 2 and cursor[:2] == ['item', expected_id],
        'ordinary cancellation requires the actual attributable displaced-item cursor')
    checked = runtime_helpers().reviewed(t, review_path, 'bags.swap_item.cancel_cursor')
    end = checked.get('empty_point')
    require(checked.get('source') == bound(source) and checked.get('frame') == old['frame'] and
        checked.get('cursor') == cursor and checked.get('empty_point_reviewed') is True and
        checked.get('empty_point_world_space') is True and valid_point(end), 'fresh reviewed cursor cancellation required')
    runtime_helpers().screen_geometry(t, source, old, found['state'], found['frame'], (end,))
    intent = {'kind': 'click', 'value': end, 'button': 3}
    cancellation = {'source': bound(source), 'review': bound(review_path), 'before_cursor': cursor,
        'input': intent, 'started_at': time.time(), 'input_replayed': False}
    t.receipt.setdefault('cursor_cancellations', []).append(cancellation)
    t.persist()
    from .interaction_item_actionbar_parked_selection_capture import game_identity
    from .owned_input import focus
    game_identity(focus(), old['baseline']['frame'])
    t.execute(intent)
    final = current(t, old['baseline'], owner, swapped=swapped, label='swap_cursor_cancelled')
    until = time.time()
    raw = packets(owner, cancellation['started_at'], until)
    require(not any(r.get('name') == 'CMSG_SWAP_INV_ITEM' for r in raw), 'cursor cancellation must not issue another swap')
    cancellation.update(finished_at=until, after_cursor=final['state'].get('cursor_info'), packets=raw)
    phase = ('bags_swap_recovery_reverse_ready' if swapped else 'bags_swap_recovery_restore_ready') if \
        old.get('recovery_only') else 'bags_swap_cursor_cancelled'
    t.receipt.update(**final, completed=True, phase=phase, input_sent=True, swapped=swapped)
    if old.get('reverse') is not None:
        t.receipt['reverse'] = old['reverse']
    guard(old['baseline'], owner, until, t)


def restore(t, preparation, source):
    _, owner, old = prior(t, preparation, source, ('bags_swap_reverse', 'bags_swap_cursor_cancelled',
        'bags_swap_restore_ready', 'bags_swap_recovery_restore_ready'))
    require(old.get('reverse') is not None or old.get('swapped') is False, 'ordinary restoration requires the exact reverse swap')
    base = old['baseline']
    current(t, base, owner, swapped=False, label='swap_restoration_before')
    # All panels are originally closed. Target and pose remain exact, so no target/movement input is authorized.
    t.clean_panels()
    public = detail(t, 'swap_restored_bars')
    if native_state(owner)['afk'] != base['native_state']['afk']:
        t.receipt['afk_restore_input'] = {'kind': 'chat', 'value': '/afk'}
        t.persist()
        t.execute(t.receipt['afk_restore_input'])
    found = current(t, base, owner, swapped=False, closed_layout=True, label='swap_restored')
    state, native = found['state'], found['native_state']
    checks = {'public_bar': runtime_helpers().public_same(public, base['public']),
        'bags': state.get('bags') == base['state'].get('bags'), 'panels': state.get('panels') == base['state'].get('panels'),
        'target': native['selection'] == base['native_state']['selection'] and state.get('target') == base['state'].get('target'),
        'pose': native['pose'] == base['native_state']['pose'], 'afk': native['afk'] == base['native_state']['afk'],
        'position': state.get('world_position') == base['state'].get('world_position'),
        'cursor_empty': not state.get('cursor_info'), 'ui_clean': not state.get('lua_errors') and not state.get('blocked_actions')}
    require(all(v is True for v in checks.values()), 'full original occupied-swap layout did not restore')
    guard(base, owner, time.time(), t)
    raw = packets(owner, linked(base['entry_source'])['started_at'], time.time())
    whole = contract.roundtrip_packets(raw, owner, linked(base['entry_source'])['started_at'], time.time()) if old.get('forward') else None
    require(whole is not None or old.get('recovery_only') is True, 'successful restore requires both exact swap pairs')
    t.receipt.update(**found, reverse=old.get('reverse'), roundtrip=whole, layout_restoration_checks=checks,
        after_saved=found['snapshot']['2']['saved'], after_resources=found['resources'],
        inventory_restored=True, actionbar_restored=True, completed=True, phase='bags_swap_restored', input_sent=False)


def recover_capture(t, preparation, source):
    """Diagnose one immutable failed input; authorize only unconsumed restoration."""
    _, owner, old = prior(t, preparation, source, ('bags_swap_forward_attempted', 'bags_swap_reverse_attempted'), failed=True)
    base = old['baseline']
    native = resources(owner)
    swapped = native != base['resources']
    contract.native_resources(base['resources'], native, swapped=swapped)
    guard(base, owner, time.time(), t)
    found = current(t, base, owner, swapped=swapped, allow_cursor=True, label='swap_failed_capture')
    failed_ref = old.get('first_failure_source') or bound(source)
    entry_directory = Path(base['entry_source']['path']).parent
    require(not swapped or not (entry_directory / 'bag_swap_reverse_attempt.json').exists(),
        'failed reverse drag is consumed; ordinary inventory input replay is forbidden')
    raw = packets(owner, linked(base['entry_source'])['started_at'], time.time())
    if swapped:
        forward = contract.swap_packets(raw, owner, old['forward_started_at'], time.time())
        t.receipt.update(forward=forward, forward_started_at=old['forward_started_at'],
            forward_finished_at=old['finished_at'], forward_packets=old.get('forward_packets', raw))
    source_control, destination_control = occupied_controls(t, reverse=swapped)
    t.receipt.update(**found, source_control=source_control, destination_control=destination_control,
        first_failure_source=failed_ref, recovery_only=True, failed_whole_excluded=True,
        gameplay_input_replayed=False, swapped=swapped, input_sent=False, completed=True,
        phase='bags_swap_recovery_reverse_ready' if swapped else 'bags_swap_recovery_restore_ready')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['recon', 'capture', 'forward', 'reverse', 'cancel-cursor', 'restore',
        'recover-capture', 'recover-reverse'])
    for name in ('output', 'preparation', 'source', 'review', 'entry'):
        parser.add_argument('--' + name, type=Path, required=name in ('output', 'preparation'))
    a = parser.parse_args()
    from .interaction_bag_swap_continuation import scout, execute_trial, SCRIPT_BOUNDARY
    from .interaction_trial import Trial
    with scout():
        t = Trial(a.output, controller='code', chat_key_hold=1.2, chat_open_retry=True)
        t.receipt.update(controller='code', model=None, revision=None, qualification_added=False,
            custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY,
            committed_sources=source_identities(lab.REPO), input_sent=False, mutation_sent=False)
        def run():
            if a.action == 'recon':
                require(a.entry and a.review, 'recon requires ordinary entry and backpack review')
                recon(t, a.preparation, a.entry, a.review)
            else:
                require(a.source, 'occupied swap stage requires its immutable source')
                if a.action in ('forward', 'reverse', 'recover-reverse'):
                    require(a.review, 'occupied drag requires its exact reviewed source-owned physical controls')
                    drag(t, a.preparation, a.source, a.review, reverse=a.action != 'forward', recovery=a.action == 'recover-reverse')
                elif a.action == 'capture':
                    capture(t, a.preparation, a.source)
                elif a.action == 'cancel-cursor':
                    require(a.review, 'cursor cancellation requires its exact ordinary review')
                    cancel_cursor(t, a.preparation, a.source, a.review)
                elif a.action == 'recover-capture':
                    recover_capture(t, a.preparation, a.source)
                else:
                    restore(t, a.preparation, a.source)
        execute_trial(t, run)
        print(json.dumps({k: t.receipt.get(k) for k in ('completed', 'phase', 'failure')}), flush=True)


if __name__ == '__main__':
    main()
