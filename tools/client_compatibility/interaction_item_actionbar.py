"""One source-bound Hearthstone icon drag and ordinary action-bar restoration.

Runtime imports stay lazy so source review and mocked tests need no auth SDK.
An interrupted gameplay input is never repeated. Recovery is housekeeping only.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import time

from . import lab_runtime as lab
from .observation.journal import entries

ITEM = 6948
ITEM_GUID = 41
ACTION = 'CMSG_SET_ACTION_BUTTON'
POSE_KEYS = ('position_x', 'position_y', 'position_z', 'orientation', 'map')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def bound(path):
    path = Path(path)
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def private_json(path):
    path = Path(path)
    require(path.name == 'episode.json' and path.is_file() and not path.is_symlink() and
        path.resolve().is_relative_to(lab.ROOT / 'evidence') and
        all(not p.is_symlink() for p in path.parents), 'requires a private owned episode')
    return json.loads(path.read_text())


def closed(path, successful=True):
    value = private_json(path)
    require(finite(value.get('started_at')) and finite(value.get('finished_at')) and
        0 < value['started_at'] < value['finished_at'], 'requires a closed finite episode')
    if successful:
        require(value.get('completed') is True and value.get('failure') is None, 'source episode did not pass')
    else:
        require(value.get('completed') is False and type(value.get('failure')) is str and bool(value['failure']),
            'recovery requires an immutable closed failed episode')
    return value


def contract():
    from . import item_actionbar_contract
    return item_actionbar_contract


def prepared(t, path):
    from .interaction_item_actionbar_continuation import prepared as read
    return read(t, path, online=True)


def session_entry(fixture):
    from . import actors
    return actors.session_entry(fixture)


def saved():
    from .interaction_owned_class_fixture import saved as read
    return read(2)


def snapshot():
    from .interaction_parked_client_resource_pause import snapshot as read
    return read()


def inventory(session):
    from .observation.inventory import Inventory
    return Inventory(lab.ROOT, session, 2).poll()


def resources(session):
    from .interaction_spellbook_recon import resources as read
    return read(inventory(session))


def native_state(session):
    from .interaction_sit_stand import pose, afk
    from .world.objects import INDEX
    oracle = inventory(session)
    fields = oracle.objects[2]
    return {'pose': pose(oracle), 'afk': afk(oracle),
        'selection': oracle.pair(2, 'UNIT_FIELD_TARGET'),
        'health': fields.get(INDEX['UNIT_FIELD_HEALTH'], 0),
        'max_health': fields.get(INDEX['UNIT_FIELD_MAXHEALTH'], 0),
        'power': fields.get(INDEX['UNIT_FIELD_POWER1'], 0),
        'xp': fields.get(INDEX['PLAYER_XP'], 0), 'next_xp': fields.get(INDEX['PLAYER_NEXT_LEVEL_XP'], 0),
        'summon': oracle.pair(2, 'UNIT_FIELD_SUMMON')}


def detail(t, label):
    from .interaction_actionbar_pages import detail as read
    return read(t, label)


def controls(t):
    from .interaction_operations import controls as read
    return read(t)


def slot_control(t):
    from .interaction_inventory_moves import slot_control as read
    return read(t, 0, 1)


def point(control):
    from .interaction_operations import point as read
    return read(control)


def binding_key(value):
    from .interaction_trial import binding_key as read
    return read(value)


def reviewed(t, path, name):
    from .interaction_owned_class_fixture import reviewed as read
    return read(t, path, name)


def server_save():
    lab.server_command('saveall')
    time.sleep(.5)


def stock_sources():
    from .interaction_hunter_learn_autobar import stock_sources as read
    return read()


def stock_grid_sources():
    """Verify installed stock hidden-cell/show-grid behavior without extraction."""
    import ctypes as ct
    source = contract().GRID_SOURCE
    require('4.4.2.60895' in (lab.BASE.parent / '.build.info').read_text(), 'installed stock build differs')
    lib = ct.CDLL(str(lab.ROOT / 'tools/CascLib-build/libcasc.so.1.0.0'))
    handle = ct.c_void_p
    signatures = {
        'CascOpenStorage': ([ct.c_char_p, ct.c_uint32, ct.POINTER(handle)], ct.c_bool),
        'CascOpenFile': ([handle, ct.c_char_p, ct.c_uint32, ct.c_uint32, ct.POINTER(handle)], ct.c_bool),
        'CascGetFileSize': ([handle, ct.POINTER(ct.c_uint32)], ct.c_uint32),
        'CascReadFile': ([handle, ct.c_void_p, ct.c_uint32, ct.POINTER(ct.c_uint32)], ct.c_bool),
        'CascCloseFile': ([handle], ct.c_bool), 'CascCloseStorage': ([handle], ct.c_bool),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(lib, name)
        fn.argtypes, fn.restype = args, result
    storage, file = handle(), handle()
    require(lib.CascOpenStorage(str(lab.BASE.parent).encode(), 2, ct.byref(storage)), 'stock storage is unavailable')
    try:
        require(lib.CascOpenFile(storage, source['path'].encode(), 2, 16, ct.byref(file)), 'stock grid source is absent')
        try:
            size = lib.CascGetFileSize(file, None)
            require(0 < size < 2_000_000, 'stock grid source size differs')
            data, count = ct.create_string_buffer(size), ct.c_uint32()
            require(lib.CascReadFile(file, data, size, ct.byref(count)) and count.value == size and
                hashlib.sha256(data.raw).hexdigest() == source['sha256'], 'installed stock grid source digest differs')
            text = data.raw.decode('utf-8').replace('\r\n', '\n')
            require(all(v in text for v in source['snippets']), 'installed stock grid handler differs')
        finally:
            lib.CascCloseFile(file)
    finally:
        lib.CascCloseStorage(storage)
    return deepcopy([source])


def consume_attempt(t, baseline, session, kind, intent):
    """Durably consume one input per immutable entry, across every capture."""
    require(kind in ('drag', 'clear') and type(intent) is dict, 'one bounded input attempt is required')
    entry_ref = baseline['entry_source']
    entry = Path(entry_ref['path'])
    output = t.out / 'episode.json'
    root = lab.ROOT / 'evidence'
    require(entry.name == 'episode.json' and entry.is_absolute() and entry.is_file() and
        entry.is_relative_to(root) and output.is_absolute() and output.is_relative_to(root) and
        t.out.is_dir() and all(not p.is_symlink() for p in (entry, *entry.parents, t.out, *t.out.parents)) and
        bound(entry) == entry_ref, 'attempt consumption requires its unchanged private entry and current output')
    marker = entry.parent / ('item_actionbar_' + kind + '_attempt.json')
    value = {'schema': 'client442_item_actionbar_consumed_attempt_v1', 'operation': 'actionbars.drag_item',
        'kind': kind, 'consumed': True, 'input_replay_allowed': False, 'created_at': time.time(),
        'entry_source': deepcopy(entry_ref), 'preparation_source': deepcopy(t.receipt['preparation_source']),
        'actor': deepcopy(t.fixture), 'runtime': deepcopy(t.receipt['runtime']), 'native_session': session,
        'operation_output': str(output), 'input_intent': deepcopy(intent)}
    require(finite(value['created_at']) and value['created_at'] > 0 and type(session) is str and session and
        t.receipt.get('native_session') == session and t.receipt.get('actor') == t.fixture and
        type(intent.get('slot0')) is int and 0 <= intent['slot0'] < 144 and
        type(intent.get('item')) is int and intent['item'] == ITEM and
        type(intent.get('item_guid')) is int and intent['item_guid'] == ITEM_GUID,
        'attempt time, owner/session or sole item intent differs')
    payload = (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()
    directory = os.open(entry.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        try:
            descriptor = os.open(marker.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600, dir_fd=directory)
        except FileExistsError as error:
            t.receipt.update(attempt_consumption_refused={'kind': kind, 'entry_source': deepcopy(entry_ref),
                'path': str(marker), 'input_replayed': False})
            t.persist()
            raise RuntimeError('this ordinary ' + kind + ' attempt is already consumed for the immutable entry; '
                'a new entry is required') from error
        # Even a partial/interrupted write leaves the exclusive marker in place.
        # It cannot authorize another input and is never removed by recovery.
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)
    marker_ref = bound(marker)
    t.receipt[kind + '_attempt_source'] = marker_ref
    t.persist()
    return marker_ref


def packet_rows(session, since, until):
    require(finite(since) and finite(until) and since <= until, 'packet interval differs')
    owned = [r for r in entries(lab.ROOT / 'evidence/world_packets.jsonl') if r.get('session') == session]
    require(all(finite(r.get('time')) for r in owned), 'owned packet timestamp is invalid')
    return [r for r in owned if since <= r['time'] <= until]


def context(t, preparation):
    old = prepared(t, preparation)
    require(tuple(t.fixture.get(k) for k in ('guid', 'account_id', 'character_name', 'race', 'class', 'level')) ==
        (2, 2, 'Harnesstwo', 1, 1, 1) and old.get('phase') == 'item_actionbar_scout_ready',
        'item drag requires the admitted original scout continuation')
    session = session_entry(t.fixture)['session']
    require(session == old.get('native_session'), 'item drag must use its prepared realm owner')
    t.receipt.update(preparation_source=bound(preparation), fixture_source=bound(preparation), native_session=session,
        qualification_added=False, custom_script_permission='blocked_by_user')
    t.persist()
    return old, session


def entry_source(t, preparation, path, old, session):
    e = closed(path)
    require(e.get('phase') == 'item_actionbar_entered' and e.get('actor') == t.fixture and
        e.get('runtime') == t.receipt['runtime'] and e.get('preparation_source') == bound(preparation) and
        e.get('native_session') == session and e.get('all_offline_snapshot') == old['all_offline_snapshot'] and
        e.get('active_spec') == old['all_offline_snapshot']['2']['native']['activeTalentGroup'] and
        e['finished_at'] <= t.receipt['started_at'], 'item drag entry source differs')
    require(e.get('saved') == old['all_offline_snapshot']['2']['saved'], 'entry saved rows differ from admitted scout')
    require(e.get('native_before_entry') == old['all_offline_snapshot']['2']['native'] and
        e.get('entered_native') == {**e['native_before_entry'], 'online': 1}, 'entry native online-only state differs')
    rows = packet_rows(session, e['started_at'], e['finished_at'])
    c = contract()
    login = c.login_packets(rows, session, e['started_at'], e['finished_at'])
    require(e.get('login_packets') == [login[k] for k in ('modern', 'request', 'verify', 'delivered')],
        'entry retained login facts differ from the actual owned journal')
    replay = c.native_replay(rows, session, e['started_at'], e['finished_at'])
    require(e.get('native_owner_proof') == replay and e.get('owner_packets') == replay['packets'],
        'entry owner creation/replay differs from actual owned journal')
    t.receipt.update(entry_source=bound(path), precision_source=e['precision_source'])
    t.persist()
    return e


def baseline_authority(base, entered, old):
    require(base.get('snapshot') == old['all_offline_snapshot'] and
        base.get('saved') == entered['saved'] and base.get('resources') == entered['resources'] and
        type(base.get('active_spec')) is int and base['active_spec'] == entered['active_spec'] and
        base.get('native_original') == entered['native_original'] and
        base.get('precision_source') == entered['precision_source'] and
        base.get('stock_grid_sources') == [contract().GRID_SOURCE] and
        public_same(base.get('public', {}), entered['public']) and
        all(base.get('state', {}).get(k) == entered['state'].get(k) for k in ('world_position', 'target', 'bags', 'panels')),
        'full original item-drag baseline differs from its immutable entry')
    original = entered['native_original']
    require(base.get('native_state', {}).get('pose') == original['pose'] and
        base['native_state'].get('afk') is original['afk'] and
        base['native_state'].get('selection') == original['selection']['native_guid'],
        'original native pose, AFK or selection baseline differs')


def prior(t, preparation, path, phases):
    old, session = context(t, preparation)
    e = closed(path)
    require(e.get('phase') in phases and e.get('actor') == t.fixture and e.get('runtime') == t.receipt['runtime'] and
        e.get('native_session') == session and e.get('preparation_source') == bound(preparation) and
        e['finished_at'] <= t.receipt['started_at'], 'item action-bar stage source differs')
    ref = e['entry_source']
    require(bound(Path(ref['path'])) == ref, 'ordinary entry source digest differs')
    entered = entry_source(t, preparation, Path(ref['path']), old, session)
    require(e['baseline']['snapshot'] == old['all_offline_snapshot'] and e['baseline']['entry_source'] == ref,
        'item action-bar baseline differs from source authority')
    baseline_authority(e['baseline'], entered, old)
    if e.get('entry_screen_source') is not None:
        from .interaction_item_actionbar_entry_capture import stage_source
        stage_source(t, e, old, entered)
    else:
        require(e.get('code_commit') == t.receipt.get('code_commit') == entered.get('code_commit'),
            'changed item-stage code requires its explicit fresh entry-screen transition')
    t.receipt.update(source=bound(path), baseline=deepcopy(e['baseline']),
        recovery_only=e.get('recovery_only', False), failed_whole_excluded=e.get('failed_whole_excluded', False))
    for key in ('placement', 'drag_source', 'drag_started_at', 'drag_finished_at', 'drag_packets',
            'placement_saved', 'placement_resources', 'first_failure_source', 'drag_attempt_source', 'clear_attempt_source',
            'stock_grid_sources', 'entry_screen_source', 'pre_recon_recovery_source', 'observer_reload_source',
            'repair_code_transition', 'committed_sources', 'prior_restoration_source', 'failed_observer_source'):
        if key in e:
            t.receipt[key] = deepcopy(e[key])
    t.persist()
    return old, session, e


def public_same(left, right):
    keys = ('active_spec', 'page', 'effective_page', 'bonus_offset', 'viewport')
    rows = lambda p: [(r.get('button'), r.get('slot'), r.get('kind'), r.get('id'), r.get('visible'))
        for r in p.get('actions', [])]
    return all(left.get(k) == right.get(k) for k in keys) and rows(left) == rows(right)


def peers(baseline, current=None):
    current = snapshot() if current is None else current
    before = baseline['snapshot']
    require(set(current) == set(before) == {str(g) for g in range(1, 7)}, 'all six snapshots are required')
    checks = {f'protected_{g}': current[str(g)] == before[str(g)] for g in (1, 3, 4, 5, 6)}
    checks.update(owner_inventory=current['2']['inventory'] == before['2']['inventory'],
        owner_pets=current['2']['pets'] == before['2']['pets'] == [],
        owner_position=all(current['2']['native'][k] == before['2']['native'][k] for k in POSE_KEYS))
    require(all(checks.values()), 'protected peer, exact item inventory, pets or owner position changed')
    return checks


def expected_saved(baseline, slot0, placed):
    rows = deepcopy(baseline['saved']['actions'])
    contract().action_rows(rows)
    require(type(baseline['active_spec']) is int and baseline['active_spec'] in (0, 1), 'baseline active spec differs')
    if placed:
        require(type(slot0) is int and 0 <= slot0 < 144 and
            not any(r[:2] == [baseline['active_spec'], slot0] for r in rows), 'placement slot was not empty')
        rows = sorted(rows + [[baseline['active_spec'], slot0, ITEM, 128]], key=lambda r: (r[0], r[1]))
    return {**deepcopy(baseline['saved']), 'actions': rows}


def validate_placement(stage, session):
    """Reconstruct placement authority from exact journal bytes before cleanup."""
    base, placement = stage['baseline'], stage['placement']
    since, until = stage['drag_started_at'], stage['drag_finished_at']
    require(finite(since) and finite(until) and since <= until, 'placement source interval differs')
    rows = packet_rows(session, since, until)
    expected = expected_saved(base, placement['slot0'], True)
    require(stage.get('drag_packets') == rows and stage.get('placement_saved') == expected and
        stage.get('placement_resources') == base['resources'], 'retained placement rows or full resources differ')
    actual = contract().addition_guard(base['saved']['actions'], expected['actions'], rows, session,
        since, until, base['active_spec'], placement['public'])
    require(actual == placement, 'placement differs from the actual owned journal')
    return actual


def assert_live(baseline, session, expected, *, allow_cursor=False, label='item_current', t=None):
    current_saved, current_resources = saved(), resources(session)
    native = native_state(session)
    require(current_saved == expected and current_resources == baseline['resources'],
        'full saved rows, money or native inventory differ')
    require(all(native.get(k) == v for k, v in {'health': 60, 'max_health': 60, 'power': 0,
        'xp': 0, 'next_xp': 400, 'summon': 0}.items()), 'owner health, rage, XP or summon changed')
    protected = peers(baseline)
    if t is None:
        return current_saved, current_resources, native, protected
    state, frame = t.observe(label)
    require(state.get('player') == 'Harnesstwo' and state.get('level') == 1 and
        state.get('world_position') == baseline['state'].get('world_position') and
        not state.get('spell_targeting') and not state.get('lua_errors') and not state.get('blocked_actions') and
        (allow_cursor or not state.get('cursor_info')), 'owned rendered state, position or cursor differs')
    return current_saved, current_resources, native, protected, state, frame


def no_forbidden(baseline, session, until, t=None):
    require(bound(Path(baseline['entry_source']['path'])) == baseline['entry_source'], 'ordinary entry digest changed')
    entered = closed(Path(baseline['entry_source']['path']))
    rows = packet_rows(session, entered['started_at'], until)
    c = contract()
    proof = c.forbidden_packets(rows, session, entered['started_at'], until)
    replay = c.native_replay(rows, session, entered['started_at'], until,
        rest_threshold=entered['native_owner_proof']['rest_threshold'])
    if t is not None:
        t.receipt.update(forbidden_input_proof=proof, native_owner_proof=replay, owner_packets=replay['packets'])
        t.persist()
    return {**proof, 'native_owner_proof': replay}


def recon(t, preparation, entry, review_path=None, entry_screen_path=None):
    old, session = context(t, preparation)
    e = entry_source(t, preparation, entry, old, session)
    from .interaction_item_actionbar_entry_capture import unconsumed, screen_source
    unconsumed(bound(entry))
    screen, screen_path = e, entry
    if entry_screen_path is not None:
        screen = screen_source(t, preparation, entry, old, e, entry_screen_path)
        screen_path = entry_screen_path
    else:
        require(t.receipt.get('code_commit') == e.get('code_commit'),
            'changed recon code requires its exact fresh entry-screen repair authority')
    native = native_state(session)
    state, frame = t.observe('item_actionbar_original')
    require(not state.get('panels') and not state.get('bags') and not state.get('chat_edit_open') and not state.get('cursor_info') and
        not state.get('spell_targeting'), 'item drag requires the original ordinary closed-panel layout')
    public = detail(t, 'item_actionbar_original_bars')
    c = contract()
    c.public_assignments(public, e['saved']['actions'], e['active_spec'])
    require(public_same(public, e['public']) and saved() == e['saved'] and resources(session) == e['resources'],
        'entry action bar, saved rows or resources differ before reconnaissance')
    original = e['native_original']
    require(type(original) is dict and original.get('resources') == e['resources'] and
        original.get('actions') == e['saved']['actions'], 'entry original native restoration authority differs')
    if entry_screen_path is not None:
        require(native.get('pose') == original['pose'] and native.get('afk') is original['afk'] and
            native.get('selection') == original['selection']['native_guid'],
            'fresh recon refuses a late native pose, AFK or target transition')
    native = {**native, 'pose': original['pose'], 'afk': original['afk'],
        'selection': original['selection']['native_guid']}
    base = {'snapshot': old['all_offline_snapshot'], 'saved': e['saved'], 'resources': e['resources'],
        'public': public, 'state': state, 'frame': frame, 'active_spec': e['active_spec'],
        'entry_source': bound(entry), 'precision_source': e['precision_source'], 'native_state': native,
        'native_original': original, 'stock_grid_sources': stock_grid_sources()}
    require(base['resources']['backpack'][0] == {'guid': (0x4000 << 48) | ITEM_GUID, 'id': ITEM, 'count': 1},
        'requires the exact existing Hearthstone GUID41 in public bag0 slot1')
    require(native['pose']['stand'] in (0, 1), 'only standing or seated ordinary scout pose is supported')
    protected = peers(base)
    t.receipt.update(baseline=base, protected_checks=protected, input_sent=False, stock_grid_sources=base['stock_grid_sources'])
    t.persist()
    require(review_path is not None, 'backpack opening requires a fresh source-bound icon review')
    d = reviewed(t, review_path, 'MainMenuBarBackpackButton')
    start = d.get('point', [])
    require(d.get('source') == bound(screen_path) and d.get('frame') == screen['frame'] and
        d.get('pickup_point_inside_button') is True and type(start) is list and len(start) == 2 and
        all(type(v) is int for v in start) and 0 <= start[0] < 1280 and 0 <= start[1] < 720,
        'backpack review must bind the actual closed-entry icon')
    geometry = screen_geometry(t, screen_path, screen, state, frame, (start,))
    t.receipt.update(backpack_open_input={'kind': 'click', 'value': start},
        backpack_open_review=bound(review_path), backpack_geometry=geometry, input_sent=True)
    t.persist()
    unconsumed(bound(entry))
    t.execute(t.receipt['backpack_open_input'])
    state, frame = t.observe('item_actionbar_bag_open')
    require(0 in state.get('bags', []) and not state.get('cursor_info'), 'ordinary backpack did not open')
    source = slot_control(t)
    shown = [r for r in state.get('bag_items', []) if (r.get('bag'), r.get('slot')) == (0, 1)]
    require(source and len(shown) == 1 and shown[0].get('id') == ITEM and shown[0].get('count') == 1 and
        shown[0].get('locked') is False, 'actual unlocked Hearthstone icon is absent')
    public = detail(t, 'item_actionbar_empty_buttons')
    buttons = c.public_assignments(public, base['saved']['actions'], base['active_spec'])
    empty = [r for r in buttons if type(r.get('visible')) is bool and not r.get('kind') and r.get('id') in (0, None, False)]
    require(empty, 'no actual empty stock main action grid cell is available')
    target = empty[0]
    state, frame = t.observe('item_actionbar_reconciled')
    assert_live(base, session, base['saved'], t=t)
    no_forbidden(base, session, time.time(), t)
    t.receipt.update(public=public, source_control=source, button=target,
        slot0=target['slot'] - 1, state=state, frame=frame,
        completed=True, phase='item_actionbar_reconciled')


def capture(t, preparation, source):
    old, session, e = prior(t, preparation, source, ('item_actionbar_reconciled', 'item_actionbar_drag_ready',
        'item_actionbar_placed', 'item_actionbar_recovery_placed', 'item_actionbar_clear_ready'))
    placed = bool(e.get('placement'))
    if placed:
        validate_placement(e, session)
    slot0 = e['placement']['slot0'] if placed else e['slot0']
    expected = expected_saved(e['baseline'], slot0, placed)
    _, _, _, protected, state, frame = assert_live(e['baseline'], session, expected, t=t, label='item_actionbar_capture')
    public = detail(t, 'item_actionbar_capture_bars')
    buttons = contract().public_assignments(public, expected['actions'], e['baseline']['active_spec'])
    button = next(r for r in buttons if r['slot'] == slot0 + 1)
    require((button.get('visible') is True if placed else type(button.get('visible')) is bool) and
        0 in state.get('bags', []), 'captured placed item or backpack is hidden')
    bag = slot_control(t)
    require(bag, 'captured bag item control is absent')
    state, frame = t.observe('item_actionbar_review_frame')
    t.receipt.update(public=public, state=state, frame=frame, source_control=bag,
        button=button, slot0=slot0, protected_checks=protected, input_sent=False, completed=True,
        phase='item_actionbar_clear_ready' if placed else 'item_actionbar_drag_ready')
    if placed:
        t.receipt['drag_source'] = e.get('drag_source') or bound(source)
    no_forbidden(e['baseline'], session, time.time(), t)


def reviewed_points(t, review_path, source, stage, *, clear=False):
    name = stage['button']['button']
    d = reviewed(t, review_path, name)
    start = d.get('point') if clear else point(stage['source_control'])
    end = d.get('empty_point') if clear else d.get('destination_point')
    require(d.get('source') == bound(source) and d.get('frame') == stage['frame'] and
        type(d.get('slot0')) is int and d['slot0'] == stage['slot0'] and
        type(d.get('item')) is int and d['item'] == ITEM and
        type(d.get('item_guid')) is int and d['item_guid'] == ITEM_GUID and d.get('public_button') == stage['button'] and
        d.get('point') == start and d.get('pickup_point_inside_button') is True and
        type(start) is list and len(start) == 2 and all(type(v) is int for v in start) and
        0 <= start[0] < 1280 and 0 <= start[1] < 720 and
        type(end) is list and len(end) == 2 and all(type(v) is int for v in end) and
        0 <= end[0] < 1280 and 0 <= end[1] < 720 and start != end,
        'review must bind the exact item, actual action button and fresh physical points')
    if clear:
        require(d.get('empty_point_reviewed') is True and d.get('empty_point_world_space') is True,
            'clear requires a reviewed empty world destination')
    else:
        require(d.get('source_control') == stage['source_control'] and
            d.get('destination_point') == end and d.get('destination_point_inside_button') is True,
            'drag review must bind both observed physical controls')
        if stage['button'].get('visible') is False:
            require(d.get('stock_grid_cell_reviewed') is True and d.get('stock_grid_source') == contract().GRID_SOURCE,
                'hidden empty destination requires a reviewed physical stock grid cell and exact installed source')
    return start, end


def screen_geometry(t, source, stage, state, frame, points):
    require(state.get('panels', []) == stage['state'].get('panels', []) and
        state.get('bags', []) == stage['state'].get('bags', []), 'reviewed panels or bags moved')
    from PIL import Image
    old_path = Path(source).parent / stage['frame']['file']
    new_path = t.out / frame['file']
    require(bound(old_path)['sha256'] == stage['frame']['sha256'], 'reviewed frame digest differs')
    with Image.open(old_path) as old, Image.open(new_path) as current:
        require(old.size == current.size == (1280, 720), 'reviewed input viewport differs')
        old, current = old.convert('RGB'), current.convert('RGB')
        regions = []
        for x, y in points:
            box = (max(0, x - 8), max(0, y - 8), min(1280, x + 8), min(720, y + 8))
            require(old.crop(box).tobytes() == current.crop(box).tobytes(), 'reviewed input pixels changed')
            regions.append(list(box))
    return {'reviewed_frame': stage['frame'], 'current_frame': frame, 'regions': regions, 'exact_pixels': True}


def retain_raw(t, session, since, label):
    """Keep each available raw fact even when another diagnostic itself fails."""
    facts = {'observed_at': time.time(), 'input_replayed': False}
    for key, read in (('packets', lambda: packet_rows(session, since, time.time())), ('saved', saved),
            ('resources', lambda: resources(session)), ('native_state', lambda: native_state(session)),
            ('public', lambda: detail(t, label + '_bars')), ('rendered', lambda: t.observe(label + '_rendered'))):
        try:
            value = read()
            if key == 'rendered':
                facts['state'], facts['frame'] = value
                facts['cursor_info'] = value[0].get('cursor_info')
            else:
                facts[key] = value
        except BaseException as error:
            facts.setdefault('errors', {})[key] = type(error).__name__ + ': ' + str(error)
        t.receipt['raw_' + label] = deepcopy(facts)
        t.persist()
    return facts


def save_guarded(t, baseline, session, slot0, public, packets, since, until, *, placed):
    c = contract()
    expected = expected_saved(baseline, slot0, placed)
    pair = c.action_packets(packets, session, since, until, slot0, clear=not placed)
    c.public_assignments(public, expected['actions'], baseline['active_spec'])
    before = saved()
    allowed = (baseline['saved'], expected_saved(baseline, slot0, True))
    require(before in allowed and resources(session) == baseline['resources'],
        'guarded SaveAll refuses unrelated saved rows or inventory changes')
    no_forbidden(baseline, session, time.time())
    t.receipt.update(saveall_authority={'pair': pair, 'public': public, 'saved_before': before,
        'expected_saved': expected, 'placed': placed}, saveall_input_sent=True)
    t.persist()
    server_save()
    after = saved()
    require(after == expected and resources(session) == baseline['resources'],
        'guarded SaveAll did not persist the sole expected action transition')
    t.receipt['saved_after_guarded_saveall'] = after
    t.persist()
    return after


def drag(t, preparation, source, review_path):
    old, session, e = prior(t, preparation, source, ('item_actionbar_drag_ready',))
    base, slot0 = e['baseline'], e['slot0']
    _, _, observed_native, protected, state, frame = assert_live(base, session, base['saved'], t=t, label='item_drag_before')
    require(observed_native == base['native_state'], 'first item drag requires the actual original native layout')
    public = detail(t, 'item_drag_before_bars')
    require(public_same(public, e['public']), 'reviewed empty public action bar differs')
    require(slot_control(t) == e['source_control'], 'reviewed Hearthstone control moved')
    start, end = reviewed_points(t, review_path, source, e)
    geometry = screen_geometry(t, source, e, state, frame, (start, end))
    no_forbidden(base, session, time.time())
    grid_sources = stock_grid_sources()
    require(grid_sources == base['stock_grid_sources'], 'reviewed installed stock grid source differs')
    require(native_state(session) == base['native_state'], 'native layout changed before consuming the first item drag')
    since = time.time()
    intent = {'source': bound(source), 'review': bound(review_path), 'slot0': slot0, 'item': ITEM,
        'item_guid': ITEM_GUID, 'start': start, 'end': end}
    consume_attempt(t, base, session, 'drag', intent)
    case = {'id': 'actionbars.drag_item', 'time': since, 'status': 'started', 'selected': 'drag',
        'selection_source': 'code', 'request': None, 'response': None,
        'input': {'kind': 'drag', 'start': start, 'end': end}, 'before': state, 'before_frame': frame}
    t.receipt.setdefault('cases', []).append(case)
    t.receipt.update(drag_started_at=since, phase='item_actionbar_drag_started', input_sent=True,
        drag_input_sent=True, drag_intent=intent,
        geometry_proof=geometry, protected_checks=protected, stock_grid_sources=grid_sources)
    t.persist()
    try:
        t.execute(case['input'])
        deadline = time.monotonic() + 16
        while True:
            shown = detail(t, 'item_drag_after_bars')
            after, after_frame = t.observe('item_drag_after')
            until = time.time()
            rows = packet_rows(session, since, until)
            t.receipt.update(drag_packets=rows, drag_finished_at=until, public_after_placement=shown,
                placement_state=after, placement_frame=after_frame, cursor_after_placement=after.get('cursor_info'))
            t.persist()
            if len([r for r in rows if r.get('name') == ACTION]) >= 2:
                break
            require(time.monotonic() < deadline, 'item placement did not settle; refusing drag replay')
            time.sleep(.2)
        require(not after.get('cursor_info') and not after.get('spell_targeting'), 'item placement left a carried cursor')
        expected = expected_saved(base, slot0, True)
        c = contract()
        native = c.action_packets(rows, session, since, until, slot0)
        c.public_assignments(shown, expected['actions'], base['active_spec'])
        no_forbidden(base, session, until)
        t.receipt['placement_native_authority'] = native
        t.persist()
        after_saved = save_guarded(t, base, session, slot0, shown, rows, since, until, placed=True)
        proof = c.addition_guard(base['saved']['actions'], after_saved['actions'], rows, session,
            since, until, base['active_spec'], shown)
        assert_live(base, session, expected, t=t)
        case.update(status='item_actionbar_drag_pass', after=after, after_frame=after_frame,
            oracle={'placement': proof, 'saved': after_saved})
        t.receipt.update(placement=proof, placement_saved=after_saved, placement_resources=resources(session),
            drag_source=bound(t.out / 'episode.json'), completed=True, phase='item_actionbar_placed')
        # The enclosing close changes episode bytes; downstream uses its closed source path, not this provisional digest.
        t.receipt.pop('drag_source', None)
    except BaseException as error:
        case.update(status='interrupted' if not isinstance(error, Exception) else 'client_or_protocol_failure',
            error=type(error).__name__ + ': ' + str(error))
        t.receipt.update(completed=False, failure=case['error'], first_failure=case['error'], failed_whole_excluded=True)
        t.persist()
        retain_raw(t, session, since, 'placement_failure')
        raise


def cancel_cursor(t, session, base, end, source_ref):
    state, frame = t.observe('item_cursor_before_cancel')
    cursor = state.get('cursor_info')
    require(type(cursor) is list and len(cursor) in (2, 3) and cursor[0] == 'item' and
        type(cursor[1]) is int and cursor[1] == ITEM and
        not state.get('spell_targeting'), 'only the exact carried Hearthstone cursor can be cancelled')
    t.receipt.update(cursor_before_cancel=cursor, cursor_cancel_input={'kind': 'click', 'value': end, 'button': 3},
        cursor_cancel_source=source_ref, cursor_cancel_input_sent=True)
    t.persist()
    t.execute(t.receipt['cursor_cancel_input'])
    deadline = time.monotonic() + 16
    while True:
        state, frame = t.observe('item_cursor_cancel_wait')
        t.receipt.update(cursor_after_cancel=state.get('cursor_info'), cursor_cancel_frame=frame)
        t.persist()
        if not state.get('cursor_info'):
            break
        require(time.monotonic() < deadline, 'carried item cursor did not cancel; refusing click replay')
        time.sleep(.2)
    no_forbidden(base, session, time.time(), t)


def restore_layout(t, base, session):
    """Ordinary UI and pose cleanup; never use the placed item or move inventory."""
    current = detail(t, 'item_restore_layout_bars')
    wanted = base['public']
    if current['page'] != wanted['page']:
        keys = current['keys'].get('ACTIONPAGE' + str(wanted['page']))
        require(type(keys) is list and keys, 'original installed action page binding is absent')
        t.receipt['page_restore_input'] = {'kind': 'key', 'value': binding_key(keys[0])}
        t.persist()
        t.execute(t.receipt['page_restore_input'])
    t.clean_panels()
    state, frame = t.observe('item_restore_layout_closed')
    original_bags = sorted(base['state'].get('bags', []))
    for bag in original_bags:
        keys = state.get('keys', {}).get('TOGGLEBACKPACK' if bag == 0 else 'TOGGLEBAG' + str(bag))
        require(type(keys) is list and keys, 'original open bag has no observed stock binding')
        action = {'kind': 'key', 'value': binding_key(keys[0])}
        t.receipt.setdefault('bag_restore_inputs', []).append(action)
        t.persist()
        t.execute(action)
        state, frame = t.observe('item_restore_bag_' + str(bag))
    native = native_state(session)
    original = base['native_state']
    wanted_target = base['state'].get('target', {})
    if native['selection'] != original['selection']:
        require(original['selection'] == 0 and not wanted_target.get('exists'), 'original selected target cannot be borrowed')
        t.receipt['target_restore_input'] = {'kind': 'chat', 'value': '/cleartarget'}
        t.persist()
        t.execute(t.receipt['target_restore_input'])
    native = native_state(session)
    if native['pose'] != original['pose']:
        require(native['pose']['sheath'] == original['pose']['sheath'] and
            {native['pose']['stand'], original['pose']['stand']} == {0, 1}, 'unsupported pose difference')
        keys = current['keys'].get('SITORSTAND')
        require(type(keys) is list and keys, 'observed stock sit/stand binding is absent')
        t.receipt['pose_restore_input'] = {'kind': 'key', 'value': binding_key(keys[0]), 'hold': .4}
        t.persist()
        t.execute(t.receipt['pose_restore_input'])
        time.sleep(12)
    public = detail(t, 'item_restored_original_bars')
    # Fixed observer chat can clear AFK; restore it after the final observer command.
    if native_state(session)['afk'] != original['afk']:
        t.receipt['afk_restore_input'] = {'kind': 'chat', 'value': '/afk'}
        t.persist()
        t.execute(t.receipt['afk_restore_input'])
    state, frame = t.observe('item_restored_original_rendered')
    native = native_state(session)
    checks = {'public_bar': public_same(wanted, public), 'bags': sorted(state.get('bags', [])) == original_bags,
        'panels': state.get('panels', []) == base['state'].get('panels', []),
        'target': native['selection'] == original['selection'] and
            all(state.get('target', {}).get(k) == wanted_target.get(k) for k in ('exists', 'guid', 'name')),
        'pose': native['pose'] == original['pose'], 'afk': native['afk'] == original['afk'],
        'position': state.get('world_position') == base['state'].get('world_position'),
        'cursor_empty': not state.get('cursor_info'), 'ui_clean': not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(layout_restoration_checks=checks, restored_public=public, restored_state=state,
        restored_frame=frame, restored_native_state=native)
    t.persist()
    require(all(checks.values()), 'ordinary original bags, page, target, pose or AFK restoration differs')
    return checks


def finish_restoration(t, base, session, placement, since, rows, public):
    until = time.time()
    expected = expected_saved(base, placement['slot0'], False)
    proof = contract().clear_guard(placement, saved()['actions'], rows, session, since, until, public)
    checks = restore_layout(t, base, session)
    after_saved, after_resources, _, protected = assert_live(base, session, expected)
    no_forbidden(base, session, time.time(), t)
    t.receipt.update(clear_proof=proof, after_saved=after_saved, after_resources=after_resources,
        protected_checks=protected, restoration_checks={**proof.get('checks', {}), **checks,
            'full_saved_baseline': after_saved == base['saved'], 'full_resources_baseline': after_resources == base['resources'],
            'protected_actors': all(protected.values())}, completed=True, phase='item_actionbar_restored',
        actionbar_restored=True)
    t.persist()


def cursor_settlement(t, preparation, source, review_path):
    """Cancel only the observed cursor after a proved and saved native clear."""
    old, session, stage = prior(t, preparation, source, ('item_actionbar_cursor_ready',))
    require(stage.get('recovery_only') is True and stage.get('failed_whole_excluded') is True and
        stage.get('first_failure_source'), 'cursor settlement must remain excluded')
    failed_ref = stage['first_failure_source']
    require(bound(Path(failed_ref['path'])) == failed_ref, 'immutable first clear failure digest differs')
    failed = closed(Path(failed_ref['path']), successful=False)
    base, placement, since = stage['baseline'], stage['placement'], stage['clear_started_at']
    validate_placement(stage, session)
    slot0 = placement['slot0']
    expected = expected_saved(base, slot0, False)
    _, _, _, _, state, frame = assert_live(base, session, expected, allow_cursor=True, t=t,
        label='item_cursor_settle_before')
    public = detail(t, 'item_cursor_settle_before_bars')
    require(public_same(public, base['public']), 'cursor settlement requires the exact original bar')
    end = stage['cursor_cancel_point']
    require(review_path is not None, 'carried cursor settlement requires a fresh screen review')
    d = reviewed(t, review_path, 'Hearthstone cursor cancellation')
    require(d.get('source') == bound(source) and d.get('frame') == stage['frame'] and
        d.get('point') == end and d.get('empty_point_reviewed') is True and
        d.get('empty_point_world_space') is True, 'cursor settlement review differs')
    geometry = screen_geometry(t, source, stage, state, frame, (end,))
    until = time.time()
    rows = packet_rows(session, since, until)
    pair = contract().action_packets(rows, session, since, until, slot0, clear=True)
    original = contract().action_packets(packet_rows(session, since, failed['finished_at']), session,
        since, failed['finished_at'], slot0, clear=True)
    require(pair == original == stage['clear_request_proof'], 'settlement native clear authority changed')
    t.receipt.update(phase='item_actionbar_cursor_settle_started', cursor_authority_source=bound(source),
        first_failure_source=failed_ref, clear_started_at=since, clear_request_proof=pair,
        clear_packets=rows, clear_finished_at=until, cursor_cancel_point=end, geometry_proof=geometry,
        clear_input_sent=False, drag_input_sent=False, gameplay_input_replayed=False)
    t.persist()
    if state.get('cursor_info'):
        cancel_cursor(t, session, base, end, bound(review_path))
    else:
        t.receipt['cursor_cancel_input_sent'] = False
        t.persist()
    finish_restoration(t, base, session, placement, since, rows, public)


def clear(t, preparation, source, review_path):
    old, session, e = prior(t, preparation, source, ('item_actionbar_clear_ready',))
    base, placement = e['baseline'], e['placement']
    validate_placement(e, session)
    slot0 = placement['slot0']
    expected = expected_saved(base, slot0, True)
    _, _, _, protected, state, frame = assert_live(base, session, expected, t=t, label='item_clear_before')
    public = detail(t, 'item_clear_before_bars')
    require(public_same(public, e['public']), 'reviewed placed public action bar differs')
    start, end = reviewed_points(t, review_path, source, e, clear=True)
    geometry = screen_geometry(t, source, e, state, frame, (start, end))
    no_forbidden(base, session, time.time())
    since = time.time()
    sources = stock_sources()
    intent = {'source': bound(source), 'review': bound(review_path), 'slot0': slot0, 'item': ITEM,
        'item_guid': ITEM_GUID, 'start': start, 'end': end}
    consume_attempt(t, base, session, 'clear', intent)
    t.receipt.update(drag_source=e.get('drag_source') or e['source'], clear_started_at=since,
        phase='item_actionbar_clear_started', clear_input_sent=True, input_sent=True,
        clear_intent=intent,
        geometry_proof=geometry, protected_checks=protected, stock_pickup_sources=sources)
    t.persist()
    try:
        with t.io.hold_modifier('shift'):
            t.io.drag(start, end)
        deadline = time.monotonic() + 16
        while True:
            public = detail(t, 'item_clear_after_bars')
            state, frame = t.observe('item_clear_carried_cursor')
            until = time.time()
            rows = packet_rows(session, since, until)
            t.receipt.update(clear_packets=rows, clear_finished_at=until, public_after_clear=public,
                clear_state=state, clear_frame=frame, cursor_after_clear=state.get('cursor_info'))
            t.persist()
            if len([r for r in rows if r.get('name') == ACTION]) >= 2:
                break
            require(time.monotonic() < deadline, 'action clear did not settle; refusing Shift drag replay')
            time.sleep(.2)
        pair = contract().action_packets(rows, session, since, until, slot0, clear=True)
        contract().public_assignments(public, base['saved']['actions'], base['active_spec'])
        # Retain the clear authority before any cursor requirement can fail.
        t.receipt['clear_request_proof'] = pair
        t.persist()
        no_forbidden(base, session, until)
        cancel_cursor(t, session, base, end, bound(review_path))
        after_saved = save_guarded(t, base, session, slot0, public, rows, since, until, placed=False)
        t.receipt['after_saved'] = after_saved
        finish_restoration(t, base, session, placement, since, rows, public)
    except BaseException as error:
        t.receipt.update(completed=False, failure=type(error).__name__ + ': ' + str(error),
            first_failure=type(error).__name__ + ': ' + str(error), failed_whole_excluded=True)
        t.persist()
        retain_raw(t, session, since, 'clear_failure')
        raise


def recover(t, preparation, failed_source, review_path=None):
    """Settle observed native outcomes; preserve the immutable first failure."""
    candidate = private_json(failed_source)
    if candidate.get('completed') is True and candidate.get('phase') == 'item_actionbar_cursor_ready':
        return cursor_settlement(t, preparation, failed_source, review_path)
    old, session = context(t, preparation)
    failed = closed(failed_source, successful=False)
    settlement_failure = failed.get('phase') == 'item_actionbar_cursor_settle_started'
    if settlement_failure:
        authority_ref = failed['cursor_authority_source']
        require(bound(Path(authority_ref['path'])) == authority_ref, 'failed cursor authority digest differs')
        authority = closed(Path(authority_ref['path']))
        first_ref = authority['first_failure_source']
        require(bound(Path(first_ref['path'])) == first_ref, 'failed cursor first failure digest differs')
        first = closed(Path(first_ref['path']), successful=False)
        require(failed.get('actor') == t.fixture and failed.get('runtime') == t.receipt['runtime'] and
            failed.get('preparation_source') == bound(preparation) and failed.get('native_session') == session and
            failed.get('baseline') == authority.get('baseline') == first.get('baseline') and
            failed.get('placement') == authority.get('placement') == first.get('placement') and
            failed.get('clear_request_proof') == authority.get('clear_request_proof') and
            failed.get('recovery_only') is True and failed.get('failed_whole_excluded') is True and
            failed['finished_at'] <= t.receipt['started_at'], 'failed cursor settlement differs from original authority')
        failed = first
    else:
        first_ref = bound(failed_source)
    require(failed.get('actor') == t.fixture and failed.get('runtime') == t.receipt['runtime'] and
        failed.get('preparation_source') == bound(preparation) and failed.get('native_session') == session and
        failed.get('qualification_added') is False and failed['finished_at'] <= t.receipt['started_at'] and
        failed.get('phase') in ('item_actionbar_drag_started', 'item_actionbar_clear_started') and
        failed.get('baseline', {}).get('snapshot') == old['all_offline_snapshot'], 'failed recovery authority differs')
    base = failed['baseline']
    ref = base['entry_source']
    require(bound(Path(ref['path'])) == ref, 'failed recovery ordinary entry digest differs')
    entered = entry_source(t, preparation, Path(ref['path']), old, session)
    baseline_authority(base, entered, old)
    t.receipt.update(source=bound(failed_source), first_failure_source=first_ref, first_failure=failed['failure'], baseline=deepcopy(base),
        recovery_only=True, failed_whole_excluded=True, drag_input_sent=False, clear_input_sent=False,
        input_sent=False, train_replayed=False, gameplay_input_replayed=False)
    for key in ('drag_attempt_source', 'clear_attempt_source'):
        if key in failed:
            t.receipt[key] = deepcopy(failed[key])
    t.persist()
    since = failed.get('clear_started_at') if failed.get('clear_input_sent') is True else failed.get('drag_started_at')
    require(finite(since) and failed['started_at'] <= since <= failed['finished_at'], 'failed input interval differs')
    raw = retain_raw(t, session, since, 'recovery_before')
    require(not raw.get('errors'), 'recovery requires complete current native/public/cursor facts')
    until, rows = time.time(), packet_rows(session, since, time.time())
    no_forbidden(base, session, until)
    clear_attempt = failed.get('clear_input_sent') is True
    slot0 = failed['clear_intent' if clear_attempt else 'drag_intent']['slot0']
    require(type(slot0) is int and 0 <= slot0 < 144, 'failed operation slot differs')
    action_rows = [r for r in rows if r.get('name') == ACTION]
    if not clear_attempt and not action_rows:
        require(raw['saved'] == base['saved'] and raw['resources'] == base['resources'] and
            public_same(raw['public'], base['public']) and not raw['state'].get('cursor_info'),
            'no-outcome recovery requires exact native/public baseline and an empty cursor')
        checks = restore_layout(t, base, session)
        after_saved, after_resources, _, protected = assert_live(base, session, base['saved'])
        no_forbidden(base, session, time.time(), t)
        t.receipt.update(after_saved=after_saved, after_resources=after_resources, protected_checks=protected,
            restoration_checks={**checks, 'full_saved_baseline': True, 'full_resources_baseline': True,
                'protected_actors': all(protected.values())}, placement_absent=True,
            completed=True, phase='item_actionbar_restored', actionbar_restored=True)
        return
    pair = contract().action_packets(rows, session, since, until, slot0, clear=clear_attempt)
    expected = expected_saved(base, slot0, not clear_attempt)
    contract().public_assignments(raw['public'], expected['actions'], base['active_spec'])
    require(raw['saved'] in (base['saved'], expected_saved(base, slot0, True)) and
        raw['resources'] == base['resources'], 'recovery refuses unrelated saved or inventory changes')
    t.receipt.update(recovery_native_authority=pair, recovery_public=raw['public'], recovery_saved_before=raw['saved'])
    t.persist()
    if clear_attempt:
        placement = failed['placement']
        validate_placement(failed, session)
        require(placement['slot0'] == slot0, 'failed clear slot differs from its placement')
        # The clear must already exist inside the immutable failed interval.
        original_pair = contract().action_packets(packet_rows(session, since, failed['finished_at']),
            session, since, failed['finished_at'], slot0, clear=True)
        require(original_pair == pair and (not failed.get('clear_request_proof') or failed['clear_request_proof'] == pair),
            'clear recovery authority differs from the failed native journal')
        save_guarded(t, base, session, slot0, raw['public'], rows, since, until, placed=False)
        t.receipt.update(placement=placement, clear_packets=rows, clear_started_at=since, clear_finished_at=until,
            clear_request_proof=pair, drag_source=failed.get('drag_source'), drag_started_at=failed.get('drag_started_at'),
            drag_finished_at=failed.get('drag_finished_at'), drag_packets=failed.get('drag_packets'),
            placement_saved=failed['placement_saved'], placement_resources=failed['placement_resources'])
        if raw['state'].get('cursor_info'):
            cursor = raw['state']['cursor_info']
            require(type(cursor) is list and len(cursor) in (2, 3) and cursor[0] == 'item' and
                type(cursor[1]) is int and cursor[1] == ITEM and not raw['state'].get('spell_targeting'),
                'proved clear recovery refuses another carried cursor')
            state, frame = t.observe('item_recovery_cursor_review')
            require(state.get('cursor_info') == cursor and state.get('bags') == raw['state'].get('bags') and
                state.get('panels') == raw['state'].get('panels'), 'carried cursor changed while capturing recovery')
            t.receipt.update(public=raw['public'], state=state, frame=frame,
                cursor_cancel_point=failed['clear_intent']['end'], completed=True, phase='item_actionbar_cursor_ready')
            no_forbidden(base, session, time.time(), t)
            return
        finish_restoration(t, base, session, placement, since, rows, raw['public'])
    else:
        require(not raw['state'].get('cursor_info'), 'placed recovery refuses an outstanding carried cursor')
        original_pair = contract().action_packets(packet_rows(session, since, failed['finished_at']),
            session, since, failed['finished_at'], slot0)
        require(original_pair == pair, 'placement recovery authority differs from the failed native journal')
        after_saved = save_guarded(t, base, session, slot0, raw['public'], rows, since, until, placed=True)
        proof = contract().addition_guard(base['saved']['actions'], after_saved['actions'], rows, session,
            since, until, base['active_spec'], raw['public'])
        peers(base)
        t.receipt.update(placement=proof, placement_saved=after_saved, placement_resources=raw['resources'],
            drag_source=bound(failed_source), drag_started_at=since, drag_finished_at=until, drag_packets=rows,
            completed=True, phase='item_actionbar_recovery_placed')


def run(t, action, preparation, source, review_path=None, entry_screen_path=None):
    try:
        require(action in ('recon', 'capture', 'drag', 'clear', 'recover'), 'unknown item action-bar stage')
        require(entry_screen_path is None or action == 'recon', 'fresh entry-screen source applies only to recon')
        if action == 'recon': recon(t, preparation, source, review_path, entry_screen_path)
        elif action == 'capture': capture(t, preparation, source)
        elif action == 'drag': drag(t, preparation, source, review_path)
        elif action == 'clear': clear(t, preparation, source, review_path)
        else: recover(t, preparation, source, review_path)
    except BaseException as error:
        t.receipt.update(completed=False, failure=t.receipt.get('failure') or type(error).__name__ + ': ' + str(error))
        if t.receipt.get('native_session') and t.receipt.get('baseline'):
            source_start = t.receipt.get('clear_started_at', t.receipt.get('drag_started_at', t.receipt['started_at']))
            retain_raw(t, t.receipt['native_session'], source_start, 'stage_failure')
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
    parser.add_argument('action', choices=['recon', 'capture', 'drag', 'clear', 'recover'])
    for name in ('preparation', 'source', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--review', type=Path)
    parser.add_argument('--entry-screen-source', type=Path,
        help='Fresh source-bound passive screen after excluded pre-recon observer recovery')
    args = parser.parse_args()
    with actor('scout'):
        trial = Trial(args.output, controller='code')
        trial.receipt.update(controller='code', custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY,
            input_sent=False, mutation_sent=False, qualification_added=False)
        run(trial, args.action, args.preparation, args.source, args.review, args.entry_screen_source)
        print(json.dumps({k: trial.receipt.get(k) for k in ('completed', 'phase', 'failure')}), flush=True)


if __name__ == '__main__':
    main()
