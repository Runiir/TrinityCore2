"""Pure archive proof of one ordinary actor2 Hearthstone drag and full pause."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from . import lab_runtime as lab
from .item_actionbar_contract import (ITEM_ID, ITEM_SQL_GUID, ITEM_NATIVE_GUID, FORBIDDEN,
    require, finite, owned_snapshot, login_packets, action_packets, addition_guard,
    clear_guard, public_assignments, native_replay, forbidden_packets)
from .item_actionbar_preservation import PRECISION_QUERY, exact_precision, preserve_six
from .item_actionbar_sources import (reference, private_json, bound, validate_bundle,
    FORMULA, FORMULA_HASH, CONFIG_HASH, FORMULA_SNIPPETS, FLOAT_SOURCES)

PHASE = 'item_actionbar_closed_paused'
ANCESTRY_SCHEMA = 'client442_item_actionbar_ancestry_v1'
ROLES = ('preparation', 'entry', 'operation', 'park', 'before_precision', 'after_precision')
TRACKING_MEMBERS = ('tracking/packets.jsonl', 'tracking/events.jsonl')
PACKET_NAMES = frozenset(('CMSG_PLAYER_LOGIN', 'SMSG_LOGIN_VERIFY_WORLD',
    'CMSG_SET_ACTION_BUTTON', 'SMSG_UPDATE_ACTION_BUTTONS', 'SMSG_UPDATE_OBJECT',
    'SMSG_DESTROY_OBJECT', 'CMSG_LOGOUT_REQUEST', 'SMSG_LOGOUT_COMPLETE',
    'CMSG_STAND_STATE_CHANGE', 'CMSG_STANDSTATECHANGE', 'SMSG_STAND_STATE_UPDATE',
    'CMSG_CHAT_MESSAGE_AFK', 'CMSG_MESSAGECHAT_AFK')) | FORBIDDEN
LAYOUT_CHECKS = frozenset(('public_bar', 'bags', 'panels', 'target', 'pose', 'afk',
    'position', 'cursor_empty', 'ui_clean'))
SHUTDOWN_CHECKS = frozenset(('scout_launcher_absent', 'owned_game_absent', 'all_retained_saved_state',
    'all_characters_offline', 'primary_still_stopped', 'native_lifetime', 'bridge_lifetime', 'origin_registration'))
PRECISION_CHECKS = frozenset(('all_six_offline', 'all_saved_state_unchanged', 'original_identity',
    'snapshot_rest_matches', 'exact_float32'))
PARK_CHECKS = frozenset(('ordinary_logout', 'native_logout', 'delivered_logout', 'all_six_offline',
    'protected_actors', 'saved_inventory', 'saved_actions', 'native_health_power_pose', 'original_registration'))
SCRIPT_BOUNDARY = {'original': '0', 'current_stock_disabled': '1', 'original_restored': False}


def accepted(value, phase=None):
    require(type(value) is dict and value.get('completed') is True and value.get('failure') is None and
        finite(value.get('started_at')) and finite(value.get('finished_at')) and
        0 < value['started_at'] < value['finished_at'] and
        (phase is None or value.get('phase') == phase) and
        all(value.get(k) is not True for k in ('recovery_only', 'failed_whole_excluded',
            'settlement_only', 'failed_repair_excluded')), 'one successful ordinary closed episode is required')
    return value


def checks(value, key, names):
    found = value.get(key)
    require(type(found) is dict and set(found) == set(names) and all(v is True for v in found.values()),
        'complete exact typed ' + key + ' checks are required')


def packet_key(row):
    return tuple(row.get(k) for k in ('session', 'time', 'direction', 'name', 'body'))


class Sources:
    """Resolve exact original bytes; carried JSON retains its original reference."""
    def __init__(self, data, digests, local=False):
        self.data, self.digests, self.local = data, digests, local
        self.ancestry = [v for v in data.values() if type(v) is dict and v.get('schema') == ANCESTRY_SCHEMA]

    def get(self, ref, successful=True):
        reference(ref)
        path = Path(ref['path'])
        require(path.is_relative_to(lab.ROOT / 'evidence'), 'source lies outside private evidence')
        member = str(path.relative_to(lab.ROOT))
        if member not in self.data and self.local:
            value = private_json(path, False)
            require(bound(path) == ref, 'local source digest changed')
            self.data[member], self.digests[member] = value, ref['sha256']
        key = member if self.digests.get(member) == ref['sha256'] and member in self.data else None
        if key is None:
            require(len(self.ancestry) == 1, 'one carried ancestry manifest is required')
            rows = [r for r in self.ancestry[0].get('sources', []) if
                r.get('original_path') == ref['path'] and r.get('sha256') == ref['sha256']]
            require(len(rows) == 1, 'source is absent or ambiguous in the carried authority')
            copy = Path(rows[0]['copy_path'])
            require(copy.is_relative_to(lab.ROOT / 'evidence'), 'carried copy is outside private evidence')
            key = str(copy.relative_to(lab.ROOT))
            require(self.digests.get(key) == ref['sha256'] and key in self.data, 'carried source bytes differ')
        value = self.data[key]
        return accepted(value) if successful else value


def frame(store, episode, image, source):
    require(type(image) is dict and type(image.get('file')) is str and Path(image['file']).name == image['file'] and
        type(image.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', image['sha256']), 'complete frame digest is required')
    monitor = image.get('monitor', {})
    require(monitor.get('second_monitor_verified') is True and monitor.get('monitor', {}).get('name') == 'HDMI-1' and
        monitor.get('pid') == episode['runtime']['client']['pid'] and
        monitor.get('input_isolation', {}).get('actor') == 'scout' and
        monitor['input_isolation'].get('host_activation_sent') is False,
        'ordinary frame must belong to the owned private HDMI-1 scout')
    reference(source)
    image_path = Path(source['path']).parent / image['file']
    require(image_path.is_relative_to(lab.ROOT / 'evidence'), 'frame owner is outside private evidence')
    if store.local:
        require(bound(image_path)['sha256'] == image['sha256'], 'exact reviewed source PNG bytes differ')
    else:
        member = str(image_path.relative_to(lab.ROOT))
        require(store.digests.get(member) == image['sha256'],
            'exact reviewed source PNG is absent from actual complete archive bytes')
    return image


def screen_review(store, episode, source, control, *, fixture=None):
    screen = episode.get('screen_review', {})
    require(type(screen) is dict and set(screen) == {'path', 'sha256', 'frame'}, 'complete owned review reference is required')
    value = store.get({k: screen[k] for k in ('path', 'sha256')}, False)
    require(value.get('reviewed') is True and value.get('control') == control and
        value.get('source') == source and value.get('frame') == screen['frame'] and
        store.get(source).get('frame') == screen['frame'] and
        (fixture is None or value.get('fixture_source_sha256') == fixture['sha256']),
        'reviewed source, physical control or exact frame differs')
    frame(store, episode, screen['frame'], source)
    return value


def rest_sources(value):
    require(type(value) is dict and type(value.get('rate')) in (int, float) and finite(value['rate']) and value['rate'] == 1 and
        value.get('xp_cap') == 400 and type(value.get('xp_cap')) is int and value.get('rest_cap') == 300 and
        type(value.get('rest_cap')) is int and type(value.get('wilderness_bubble')) is float and value['wilderness_bubble'] == .031 and
        value.get('formula_snippets') == list(FORMULA_SNIPPETS) and
        value.get('config_source') == {'path': str(lab.ROOT / 'config/worldserver.conf'), 'sha256': CONFIG_HASH} and
        value.get('native_formula_source') == {'path': str(lab.REPO / FORMULA), 'sha256': FORMULA_HASH},
        'source-bound configured native level1 wilderness rest formula differs')
    refs = value.get('native_float_storage_sources')
    require(type(refs) is list and refs == [{'path': str(lab.REPO / p), 'sha256': sha} for p, sha in FLOAT_SOURCES.items()],
        'source-bound exact native FLOAT storage implementation differs')


def precision(value, source, snapshot):
    accepted(value, 'item_actionbar_rest_precision_complete')
    checks(value, 'checks', PRECISION_CHECKS)
    require(value.get('source') == source and value.get('query') == PRECISION_QUERY and
        value.get('before') == value.get('after') == snapshot and value.get('input_sent') is False and
        value.get('mutation_sent') is False and value.get('qualification_added') is False,
        'exact read-only actor2 precision source differs')
    rest_sources(value.get('rest_sources'))
    return exact_precision(value.get('row'), snapshot)


def predecessor(store, ready):
    refs = ready.get('predecessor')
    require(type(refs) is dict and set(refs) == {'closure', 'pause', 'remote', 'checkpoint', 'primary_stop'},
        'all actual UI170 predecessor roles are required')
    values = {k: store.get(ref, k in ('closure', 'pause', 'primary_stop')) for k, ref in refs.items()}
    values['dvc_pointer'] = ready.get('predecessor_dvc_pointer')
    bundle = validate_bundle(values, refs)
    require(bundle['snapshot'] == ready.get('all_offline_snapshot'), 'ready six-actor snapshot differs from actual UI170 pause')
    resume = store.get(ready['resume_source'], False)
    require(resume.get('schema') == 'client442_item_actionbar_scout_resume_v1' and
        resume.get('phase') == 'item_actionbar_scout_launched' and resume.get('completed') is True and
        resume.get('finished_at') == resume.get('launch_finished_at') and resume.get('installed') is True and
        resume.get('failure') is None and resume.get('predecessor') == refs and
        resume.get('predecessor_dvc_pointer') == ready.get('predecessor_dvc_pointer') and
        resume.get('all_offline_snapshot') == bundle['snapshot'] and resume.get('origin_actor') == ready['actor'] and
        resume.get('runtime') == ready['runtime'] and resume.get('previous_runtime') == bundle['runtime'] and
        resume['runtime']['worldserver'] == bundle['runtime']['worldserver'] and
        resume['runtime']['modern_world'] == bundle['runtime']['modern_world'] and
        resume['runtime']['client'] != bundle['runtime']['client'] and
        type(resume.get('available_memory_kib_before')) is int and resume['available_memory_kib_before'] >= 6 * 1024 * 1024 and
        finite(resume.get('started_at')) and finite(resume.get('launch_finished_at')) and
        bundle['pause']['finished_at'] < resume['started_at'] < resume['launch_finished_at'] < ready['started_at'],
        'fresh source-bound one-scout launch or unchanged native/bridge lifetime differs')
    checks(resume, 'checks', {'native_unchanged', 'bridge_unchanged', 'fresh_scout',
        'all_six_saved_snapshots', 'primary_stopped', 'HDMI_1', 'private_input'})
    authentication = ready.get('realm_authentication', {})
    require(authentication.get('event') == 'world_authenticated' and type(authentication.get('account_id')) is int and
        authentication['account_id'] == 2 and authentication.get('session') == ready.get('native_session') and
        finite(authentication.get('time')) and resume['started_at'] <= authentication['time'] <= ready['started_at'],
        'fresh source-retained realm authentication differs from the owned scout session')
    selection = screen_review(store, ready, ready['selection_source'], 'Harnesstwo')
    require((selection.get('selected_character'), selection.get('selected_level')) == ('Harnesstwo', 1),
        'ready original selection review differs')
    return bundle


def pointer_observation(store, ready):
    require(len(store.ancestry) == 1, 'one predecessor pointer observation manifest is required')
    value = store.get(store.ancestry[0].get('pointer_observation'), False)
    require(type(value) is dict and set(value) == {'schema', 'descriptor', 'raw_hex'} and
        value['schema'] == 'client442_item_actionbar_predecessor_pointer_v1' and
        value['descriptor'] == ready.get('predecessor_dvc_pointer') and type(value['raw_hex']) is str and
        len(value['raw_hex']) <= 8192 and re.fullmatch('[0-9a-f]+', value['raw_hex']),
        'exact raw original UI170 DVC pointer observation is required')
    raw = bytes.fromhex(value['raw_hex'])
    descriptor = value['descriptor']
    require(hashlib.sha256(raw).hexdigest() == descriptor['source']['sha256'], 'actual original DVC pointer bytes differ')
    text = raw.decode('utf-8')
    hashes = re.findall(r'^\s*-?\s*md5:\s*([0-9a-f]{32})\s*$', text, re.MULTILINE)
    sizes = re.findall(r'^\s*size:\s*([0-9]+)\s*$', text, re.MULTILINE)
    paths = re.findall(r'^\s*path:\s*(\S+)\s*$', text, re.MULTILINE)
    require(hashes == [descriptor['oid']] and sizes == [str(descriptor['bytes'])] and
        paths == [Path(descriptor['pointer']).name.removesuffix('.dvc')] and
        re.search(r'^\s*hash:\s*md5\s*$', text, re.MULTILINE), 'actual original DVC pointer object identity differs')


def same_public(left, right):
    keys = ('active_spec', 'page', 'effective_page', 'bonus_offset', 'viewport')
    rows = lambda p: [(r.get('button'), r.get('slot'), r.get('kind'), r.get('id'), r.get('visible'))
        for r in p.get('actions', [])]
    return all(left.get(k) == right.get(k) for k in keys) and rows(left) == rows(right)


def stage_chain(store, operation):
    restored = accepted(operation, 'item_actionbar_restored')
    clear_ready = store.get(restored['source'])
    captures, ref = [], restored['source']
    while clear_ready.get('phase') == 'item_actionbar_clear_ready':
        captures.append((ref, clear_ready))
        require(len(captures) <= 8, 'clear capture chain exceeds its bound')
        ref = clear_ready['source']
        clear_ready = store.get(ref)
    placed_ref, placed = ref, accepted(clear_ready, 'item_actionbar_placed')
    drag_ready = store.get(placed['source'])
    captures2, ref = [], placed['source']
    while drag_ready.get('phase') == 'item_actionbar_drag_ready':
        captures2.append((ref, drag_ready))
        require(len(captures2) <= 8, 'drag capture chain exceeds its bound')
        ref = drag_ready['source']
        drag_ready = store.get(ref)
    recon_ref, recon = ref, accepted(drag_ready, 'item_actionbar_reconciled')
    require(captures and captures2 and restored.get('drag_source') == placed_ref,
        'exact reconciled/captured/placed/captured/clear source chain is required')
    return recon_ref, recon, list(reversed(captures2)), placed_ref, placed, list(reversed(captures)), restored


def input_review(store, value, source, ready_ref, stage, clear=False):
    review = screen_review(store, value, source, stage['button']['button'], fixture=ready_ref)
    intent = value.get('clear_intent' if clear else 'drag_intent', {})
    start = review.get('point')
    end = review.get('empty_point' if clear else 'destination_point')
    require(type(start) is list and type(end) is list and len(start) == len(end) == 2 and start != end and
        all(type(p) is int and 0 <= p < (1280 if i % 2 == 0 else 720) for i, p in enumerate(start + end)) and
        review.get('public_button') == stage.get('button') and review.get('slot0') == stage.get('slot0') and
        type(review.get('slot0')) is int and review.get('item') == ITEM_ID and review.get('item_guid') == ITEM_SQL_GUID and
        review.get('pickup_point_inside_button') is True and intent == {'source': source,
            'review': {k: value['screen_review'][k] for k in ('path', 'sha256')}, 'slot0': stage['slot0'],
            'item': ITEM_ID, 'item_guid': ITEM_SQL_GUID, 'start': start, 'end': end} and
        value.get('geometry_proof', {}).get('exact_pixels') is True and
        value['geometry_proof'].get('reviewed_frame') == stage['frame'], 'exact reviewed physical item drag intent differs')
    if clear:
        require(review.get('empty_point_reviewed') is True and review.get('empty_point_world_space') is True and
            value.get('cursor_cancel_input_sent') is True and value.get('cursor_cancel_source') == intent['review'] and
            value.get('cursor_cancel_input') == {'kind': 'click', 'value': end, 'button': 3} and
            value.get('cursor_after_cancel') in (None, False, []), 'one reviewed ordinary carried-cursor cancellation is required')
        from .hunter_learn_autobar import PICKUP_SOURCE, BINDING_SOURCE
        require(value.get('stock_pickup_sources') == [PICKUP_SOURCE, BINDING_SOURCE],
            'installed source-bound stock Shift pickup handler differs')
    else:
        require(review.get('source_control') == stage.get('source_control') and
            review.get('destination_point_inside_button') is True and value.get('cursor_after_placement') in (None, False, []),
            'actual observed item icon and empty action destination review differs')
        from .item_actionbar_contract import GRID_SOURCE
        require(value.get('stock_grid_sources') == [GRID_SOURCE], 'installed source-bound stock grid behavior is required')
        if stage['button'].get('visible') is False:
            require(review.get('stock_grid_cell_reviewed') is True and review.get('stock_grid_source') == GRID_SOURCE,
                'a hidden empty destination needs its exact stock grid source and reviewed physical cell')
    return review


def consumed_attempt(store, value, value_ref, entry_ref, ready_ref, clear=False):
    key, kind = ('clear_attempt_source', 'clear') if clear else ('drag_attempt_source', 'drag')
    ref = value.get(key)
    marker = store.get(ref, False)
    input_key = 'clear_intent' if clear else 'drag_intent'
    since = value['clear_started_at' if clear else 'drag_started_at']
    pair = value['clear_proof' if clear else 'placement']
    require(Path(ref['path']) == Path(entry_ref['path']).parent / ('item_actionbar_' + kind + '_attempt.json') and
        marker.get('schema') == 'client442_item_actionbar_consumed_attempt_v1' and
        marker.get('operation') == 'actionbars.drag_item' and marker.get('kind') == kind and
        marker.get('consumed') is True and marker.get('input_replay_allowed') is False and
        marker.get('entry_source') == entry_ref and marker.get('preparation_source') == ready_ref and
        marker.get('actor') == value.get('actor') and marker.get('runtime') == value.get('runtime') and
        marker.get('native_session') == value.get('native_session') and marker.get('operation_output') == value_ref['path'] and
        marker.get('input_intent') == value.get(input_key) and finite(marker.get('created_at')) and
        value['started_at'] <= since <= marker['created_at'] <= pair['modern']['time'],
        'durable exact one-attempt marker, input intent or owned output differs')
    return marker


def fresh_entry_screen(store, ready, entry, recon, ready_ref, entry_ref):
    """Admit a later screen only through the exact excluded repair chain."""
    from . import interaction_item_actionbar_entry_capture as capture
    ref = recon.get('entry_screen_source')
    value = store.get(ref)
    refs = {'preparation': ready_ref, 'entry': entry_ref, 'failed': value.get('first_failure_source'),
        'recovery': value.get('pre_recon_recovery_source'), 'reload': value.get('observer_reload_source')}
    failed, recovery, reload = [store.get(refs[k], False) for k in ('failed', 'recovery', 'reload')]
    ancestors = capture.repair_ancestors(recovery, refs, lambda ref, success: store.get(ref, False))
    transition = capture.validate_capture(value, ready, entry, failed, recovery, reload, refs, ancestors)
    require(all(store.get(row['source'], False) == row['value'] for row in value['housekeeping_attempts']),
        'actual archived housekeeping attempt bytes differ from fresh capture')
    for source_ref, episode, image in ((entry_ref, entry, entry['frame']), (ref, value, value['frame']),
            (refs['reload'], reload, reload['after_frame'])):
        frame(store, episode, image, source_ref)
    original_review = store.get(failed.get('backpack_open_review'), False)
    point = original_review.get('point')
    require(original_review.get('reviewed') is True and original_review.get('control') == 'MainMenuBarBackpackButton' and
        original_review.get('source') == entry_ref and original_review.get('frame') == entry['frame'] and
        original_review.get('fixture_source_sha256') == ready_ref['sha256'] and
        original_review.get('pickup_point_inside_button') is True and type(point) is list and len(point) == 2 and
        all(type(v) is int for v in point) and 0 <= point[0] < 1280 and 0 <= point[1] < 720 and
        failed.get('backpack_open_input') == {'kind': 'click', 'value': point} and
        failed.get('backpack_geometry', {}).get('exact_pixels') is True and
        failed['backpack_geometry'].get('reviewed_frame') == entry['frame'],
        'original failed recon must retain its exact reviewed entry backpack click')
    frame(store, failed, failed['raw_stage_failure']['frame'], refs['failed'])
    restorations = [(refs['prior_restoration'], ancestors['prior_restoration']), (refs['recovery'], recovery)] if ancestors else [(refs['recovery'], recovery)]
    for restored_ref, restored_episode in restorations:
        frame(store, restored_episode, restored_episode['restored_frame'], restored_ref)
        idle_frame = restored_episode.get('pre_recon_idle_observation', {}).get('frame')
        frame(store, restored_episode, idle_frame, restored_ref)
        if restored_episode.get('idle_renewal') is True:
            for preflight in restored_episode['renewal_input_preflights']:
                frame(store, restored_episode, preflight['frame'], restored_ref)
        if restored_episode.get('idle_renewal') is not True:
            require(idle_frame == restored_episode.get('bag_close_before_frame'),
                'source-retained idle observation must own the actual bag-close-before frame')
            if restored_episode.get('bag_close_input_sent') is True:
                frame(store, restored_episode, restored_episode.get('bag_close_frame'), restored_ref)
            require(type(restored_episode.get('bag_close_input_sent')) is bool and
                (restored_episode.get('bag_close_input') == {'kind': 'key', 'value': 'Escape'} if restored_episode['bag_close_input_sent']
                    else restored_episode.get('input_sent') is False) and
                restored_episode.get('pre_recon_no_mutation_proof', {}).get('native_action_requests') == 0,
                'excluded pre-recon housekeeping must retain the sole ordinary bag-close input')
    if ancestors:
        frame(store, ancestors['failed_observer'], ancestors['failed_observer']['before_frame'], refs['failed_observer'])
    review = screen_review(store, recon, ref, 'MainMenuBarBackpackButton', fixture=ready_ref)
    start = review.get('point')
    require(review.get('pickup_point_inside_button') is True and type(start) is list and len(start) == 2 and
        all(type(v) is int for v in start) and 0 <= start[0] < 1280 and 0 <= start[1] < 720 and
        recon.get('backpack_open_input') == {'kind': 'click', 'value': start} and
        recon.get('backpack_open_review') == {k: recon['screen_review'][k] for k in ('path', 'sha256')} and
        recon.get('backpack_geometry', {}).get('reviewed_frame') == value['frame'] and
        recon['backpack_geometry'].get('exact_pixels') is True and
        value['finished_at'] <= recon['started_at'] and
        all(recon.get(k) == value.get(k) for k in ('first_failure_source', 'pre_recon_recovery_source',
            'observer_reload_source', 'repair_code_transition', 'committed_sources', 'prior_restoration_source', 'failed_observer_source')),
        'renewed recon must review the distinct fresh captured entry screen')
    return value, reload, transition


def lifecycle(store, refs):
    require(type(refs) is dict and set(refs) == set(ROLES), 'one complete item lifecycle source role set is required')
    rows = {k: store.get(v) for k, v in refs.items()}
    ready, entry, operation, park, before, after = [rows[k] for k in ROLES]
    accepted(ready, 'item_actionbar_scout_ready')
    checks(ready, 'checks', {'original_selection', 'fresh_enumeration', 'all_six_offline'})
    bundle = predecessor(store, ready)
    baseline = ready['all_offline_snapshot']
    own = owned_snapshot(baseline)
    exact_before = precision(before, refs['preparation'], baseline)
    accepted(entry, 'item_actionbar_entered')
    require(entry.get('preparation_source') == refs['preparation'] and entry.get('precision_source') == refs['before_precision'] and
        entry.get('all_offline_snapshot') == baseline and entry.get('native_before_entry') == own['native'] and
        entry.get('entered_native') == {**own['native'], 'online': 1} and entry.get('saved') == own['saved'] and
        type(entry.get('native_session')) is str and entry['native_session'] == ready.get('native_session') and
        entry.get('active_spec') == own['native']['activeTalentGroup'], 'exact source-bound ordinary original entry differs')
    owner_session = entry['native_session']
    login = login_packets(entry.get('login_packets'), owner_session, entry['started_at'], entry['finished_at'])
    replay = native_replay(entry.get('owner_packets'), owner_session, entry['started_at'], entry['finished_at'])
    require(replay == entry.get('native_owner_proof') and entry.get('state', {}).get('xp_exhaustion') == 2 * replay['rest_threshold'],
        'complete native creation and public level1 exhaustion differ')
    public_assignments(entry.get('public'), own['saved']['actions'], entry['active_spec'])
    item_rows = [r for r in own['inventory'] if type(r) is list and len(r) >= 19 and r[3] == ITEM_SQL_GUID]
    require(len(item_rows) == 1 and item_rows[0][:11] == [2, 0, 23, 41, 41, 6948, 2, 0, 0, 1, 0] and
        type(entry.get('resources')) is dict and entry['resources'].get('backpack', [None])[0] ==
        {'guid': ITEM_NATIVE_GUID, 'id': ITEM_ID, 'count': 1}, 'existing unchanged Hearthstone GUID41 bag0 slot1 is required')
    recon_ref, recon, drag_views, placed_ref, placed, clear_views, restored = stage_chain(store, operation)
    base = recon.get('baseline', {})
    require(base.get('snapshot') == baseline and base.get('saved') == entry['saved'] and
        base.get('resources') == entry['resources'] and base.get('entry_source') == refs['entry'] and
        base.get('precision_source') == refs['before_precision'] and base.get('active_spec') == entry['active_spec'] and
        same_public(base.get('public', {}), entry['public']) and base.get('native_original') == entry.get('native_original'),
        'complete initial item baseline differs from ordinary entry authority')
    fresh = None
    if recon.get('entry_screen_source') is not None:
        fresh, reload, transition = fresh_entry_screen(store, ready, entry, recon, refs['preparation'], refs['entry'])
    current = [ready, before, entry, *([fresh] if fresh is not None else []), recon, *[v for _, v in drag_views], placed,
        *[v for _, v in clear_views], restored, park, after]
    for value in current:
        expected_commit = reload['code_commit'] if fresh is not None and value not in (ready, before, entry) else ready['code_commit']
        require(value.get('actor') == ready['actor'] and value.get('runtime') == ready['runtime'] and
            type(ready.get('code_commit')) is str and re.fullmatch('[0-9a-f]{40}', ready['code_commit']) and
            value.get('code_commit') == expected_commit and
            value.get('controller') == 'code' and value.get('model') is None and value.get('revision') is None and
            value.get('custom_script_permission') == 'blocked_by_user' and value.get('softTargetInteract') == SCRIPT_BOUNDARY and
            value.get('qualification_added') is False, 'same owned actor/runtime, code controller or scripts boundary differs')
    stages = [recon, *[v for _, v in drag_views], placed, *[v for _, v in clear_views], restored]
    for value in stages:
        require(value.get('baseline') == base and value.get('native_session') == owner_session and
            value.get('preparation_source') == refs['preparation'] and value.get('entry_source') == refs['entry'],
            'item stages do not retain the complete original baseline and login authority')
        if fresh is not None:
            require(value.get('entry_screen_source') == recon['entry_screen_source'] and
                value.get('repair_code_transition') == transition and value.get('committed_sources') == transition['committed_sources'] and
                all(value.get(k) == fresh.get(k) for k in ('first_failure_source', 'pre_recon_recovery_source', 'observer_reload_source',
                    'prior_restoration_source', 'failed_observer_source')),
                'later item stage lost its explicit source-bound repair code transition')
    for left, right in zip(current, current[1:]):
        require(left['finished_at'] <= right['started_at'], 'ordinary item lifecycle chronology differs')
    drag_ref, drag_view = drag_views[-1]
    clear_ref, clear_view = clear_views[-1]
    input_review(store, placed, drag_ref, refs['preparation'], drag_view)
    input_review(store, restored, clear_ref, refs['preparation'], clear_view, clear=True)
    consumed_attempt(store, placed, placed_ref, refs['entry'], refs['preparation'])
    consumed_attempt(store, restored, refs['operation'], refs['entry'], refs['preparation'], clear=True)
    require(placed.get('drag_input_sent') is True and restored.get('clear_input_sent') is True and
        placed.get('input_sent') is True and restored.get('input_sent') is True, 'exact one ordinary drag and Shift clear input is required')
    placement = addition_guard(base['saved']['actions'], placed['placement_saved']['actions'], placed['drag_packets'],
        owner_session, placed['drag_started_at'], placed['drag_finished_at'], base['active_spec'], placed['public_after_placement'])
    require(placement == placed.get('placement') == restored.get('placement') and
        placed['placement_saved'] == {**base['saved'], 'actions': placement['after_actions']} and
        placed.get('placement_resources') == base['resources'], 'only the sole native item action may be added')
    cleared = clear_guard(placement, restored['after_saved']['actions'], restored['clear_packets'], owner_session,
        restored['clear_started_at'], restored['clear_finished_at'], restored['public_after_clear'])
    require(cleared == restored.get('clear_proof') and restored.get('after_saved') == base['saved'] and
        restored.get('after_resources') == base['resources'] and restored.get('actionbar_restored') is True and
        same_public(restored.get('restored_public', {}), base['public']) and
        restored.get('restored_native_state') == base.get('native_state'), 'ordinary item clear did not restore full saved/native baseline')
    checks(restored, 'layout_restoration_checks', LAYOUT_CHECKS)
    require(type(restored.get('restoration_checks')) is dict and all(v is True for v in restored['restoration_checks'].values()) and
        restored['restoration_checks'].get('full_saved_baseline') is True and
        restored['restoration_checks'].get('full_resources_baseline') is True,
        'complete successful original layout/resources restoration is required')
    cases = placed.get('cases')
    require(type(cases) is list and len(cases) == 1 and cases[0].get('id') == 'actionbars.drag_item' and
        cases[0].get('status') == 'item_actionbar_drag_pass' and cases[0].get('selected') == 'drag' and
        cases[0].get('selection_source') == 'code' and cases[0].get('request') is None and cases[0].get('response') is None and
        cases[0].get('oracle', {}).get('placement') == placement, 'one attributable code-selected item drag case is required')
    accepted(park, 'item_actionbar_parked')
    checks(park, 'checks', PARK_CHECKS)
    require(park.get('source') == refs['operation'] and park.get('preparation_source') == refs['preparation'] and
        park.get('entry_source') == refs['entry'] and park.get('native_session') == owner_session,
        'park does not consume the exact completed roundtrip')
    from .interaction_item_actionbar_continuation import logout_packets
    logout = logout_packets(park.get('logout_packets'), owner_session, park['logout_started_at'], park['logout_finished_at'])
    snapshot = park['all_offline_snapshot']
    exact_after = precision(after, refs['park'], snapshot)
    preservation = preserve_six(baseline, snapshot, entry, exact_before, exact_after)
    require(replay['rest_threshold'] == int(exact_after['exact_rest_bonus']), 'native entry rest threshold differs from exact saved FLOAT')
    result = {'operation': 'actionbars.drag_item', 'owner': 2, 'item': ITEM_ID, 'item_sql_guid': ITEM_SQL_GUID,
        'bag': 0, 'bag_slot': 1, 'active_spec': placement['active_spec'], 'slot0': placement['slot0'],
        'native_item_requests': 1, 'modern_item_requests': 1, 'native_clear_requests': 1,
        'modern_clear_requests': 1, 'ordinary_login_count': 1, 'ordinary_logout_count': 1,
        'cursor_cancel_count': 1, 'full_saved_actions_restored': True, 'full_inventory_preserved': True,
        'health_power_xp_preserved': True, 'pets_absent': True, 'no_item_use_or_cast': True,
        'all_six_offline': True, 'primary_stopped': True, 'qualification_added': False,
        'rest': preservation['native_rest']}
    return result, snapshot, current


def tracking_state():
    return {'packets': [], 'events': [], 'members': set()}


def collect(member, lines, data, tracking):
    closures = [e for e in data.values() if type(e) is dict and e.get('phase') == PHASE]
    require(len(closures) == 1 and member in TRACKING_MEMBERS, 'one item closed pause must precede both actual journals')
    store = Sources(data, tracking['digests'])
    ready = store.get(closures[0]['sources']['preparation'])
    since, until = ready['started_at'], closures[0]['finished_at']
    require(member not in tracking['members'], 'duplicate actual journal member')
    tracking['members'].add(member)
    destination = tracking['packets' if member == TRACKING_MEMBERS[0] else 'events']
    for row in lines:
        require(type(row) is dict, 'actual journal row must be an object')
        if row.get('session') == ready['native_session']:
            require(finite(row.get('time')), 'actual owned journal timestamp must be finite and typed')
        if not finite(row.get('time')) or not since <= row['time'] <= until:
            continue
        if member == TRACKING_MEMBERS[0] and (row.get('name') in PACKET_NAMES or
            str(row.get('name', '')).startswith(('CMSG_PET_', 'CMSG_STABLE_'))) or member == TRACKING_MEMBERS[1]:
            destination.append(row)
            require(len(destination) <= 30000, 'item journal exceeds its bounded one-scout semantic interval')


def actual_packets(store, closure, tracking):
    require(tracking.get('members') == set(TRACKING_MEMBERS), 'both actual archived journals are required')
    entry = store.get(closure['sources']['entry'])
    operation = store.get(closure['sources']['operation'])
    park = store.get(closure['sources']['park'])
    placed = store.get(operation['drag_source'])
    owner = entry['native_session']
    wire = [p for p in tracking['packets'] if p.get('session') == owner]
    events = tracking['events']
    instances = [e for e in events if e.get('event') == 'instance_authenticated' and e.get('account_id') == 2]
    require(len(instances) == 1 and type(instances[0].get('session')) is str and instances[0]['session'],
        'one actual fresh actor2 physical instance is required')
    require(entry['started_at'] <= instances[0].get('time', 0) <= entry['finished_at'],
        'actual physical instance is outside its ordinary entry interval')
    physical = instances[0]['session']
    relevant_events = [e for e in events if e.get('session') in (owner, physical)]
    require(not any(e.get('direction') in ('from_client', 'to_native') and
        (e.get('name') in FORBIDDEN or str(e.get('name', '')).startswith(('CMSG_PET_', 'CMSG_STABLE_')))
        for e in relevant_events), 'actual metadata contains item use, cast, trainer, inventory or pet input')
    forbidden_packets(wire, owner, entry['started_at'], closure['finished_at'])
    chain = login_packets(wire, owner, entry['started_at'], entry['finished_at'])
    require(len([p for p in wire if p.get('name') in ('CMSG_PLAYER_LOGIN', 'SMSG_LOGIN_VERIFY_WORLD')]) == 4,
        'actual item lifecycle contains another ordinary login or delivery')
    actual_logout = [p for p in wire if p.get('name') in ('CMSG_LOGOUT_REQUEST', 'SMSG_LOGOUT_COMPLETE')]
    require(len(actual_logout) == 4 and len([p for p in actual_logout if p.get('name') == 'CMSG_LOGOUT_REQUEST' and
        p.get('direction') == 'from_client' and p.get('body') == '']) == 1,
        'actual item lifecycle must contain one ordinary modern/native logout only')
    from .interaction_item_actionbar_continuation import logout_packets
    completed_logout = logout_packets(wire, owner, park['logout_started_at'], park['logout_finished_at'])
    require([packet_key(p) for p in completed_logout] == [packet_key(p) for p in park['logout_packets']],
        'actual completed logout differs from the saved native/client triple')
    actual_owner = native_replay(wire, owner, entry['started_at'], completed_logout[1]['time'],
        rest_threshold=entry['native_owner_proof']['rest_threshold'])
    require(actual_owner['health'] == 60 and actual_owner['rest_threshold'] == entry['native_owner_proof']['rest_threshold'],
        'actual native owner interval changed health, power, rest, XP or pets')
    _, recon, _, _, _, _, _ = stage_chain(store, operation)
    if recon.get('entry_screen_source') is not None:
        captured = store.get(recon['entry_screen_source'])
        captured_actual = [p for p in wire if entry['started_at'] <= p['time'] <= captured['finished_at']]
        captured_claimed = [p for p in captured['capture_packets'] if p.get('name') in PACKET_NAMES]
        require([packet_key(p) for p in captured_actual] == [packet_key(p) for p in captured_claimed] and
            not any(p.get('name') == 'CMSG_SET_ACTION_BUTTON' for p in captured_actual),
            'actual pre-drag journal differs from fresh capture or contains an earlier action input')
        recovery = store.get(captured['pre_recon_recovery_source'], False)
        restorations = [store.get(captured['prior_restoration_source'], False), recovery] if recovery.get('idle_renewal') is True else [recovery]
        for restored_episode in restorations:
            observed = restored_episode['pre_recon_idle_observation']
            retained = [*observed.get('observed_stand_packets', []), *restored_episode.get('stand_cleanup_packets', []),
                *observed.get('observed_owner_flags_packets', [])]
            if observed.get('observed_owner_flags_packet'):
                retained.append(observed['observed_owner_flags_packet'])
            require(all(any(packet_key(p) == packet_key(q) for q in captured_actual) for p in retained),
                'actual source-retained observed idle and restoration packets are absent from the archive')
            if restored_episode.get('idle_renewal') is True:
                from .interaction_item_actionbar_idle_renewal import idle_packets
                prior = restorations[0]
                observer = store.get(captured['failed_observer_source'], False)
                proof = idle_packets(captured_actual, owner, prior['finished_at'], observed['until'], observer['finished_at'])
                require(all(observed.get(k) == proof[k] for k in proof), 'actual fresh renewal sparse idle journal differs')
                metadata = [row for row in events if row.get('session') == owner and
                    prior['finished_at'] < row.get('time', 0) <= observed['until']]
                forbidden_events = [row for row in metadata if row.get('event') in
                    ('native_player_created', 'world_connection_closed', 'native_stream_closed')]
                require(not forbidden_events and observed.get('native_lifecycle_events') == forbidden_events and
                    observed.get('native_metadata_rows_checked') == len(metadata),
                    'actual post-A native lifetime must exclude every recreation or disconnect event')
            elif observed['mismatch_observed']:
                require(observed['since'] == store.get(captured['first_failure_source'], False)['finished_at'],
                    'unattributed idle observation must begin after the immutable first failure')
    claimed = [*entry['login_packets'], placed['placement']['modern'], placed['placement']['native'],
        operation['clear_proof']['modern'], operation['clear_proof']['native'], *park['logout_packets']]
    require(all(any(packet_key(p) == packet_key(c) for p in wire) for c in claimed),
        'one claimed login, action or logout is absent from the actual archive')
    actions = [p for p in wire if p.get('name') == 'CMSG_SET_ACTION_BUTTON']
    expected_actions = claimed[4:8]
    require(len(actions) == 4 and {packet_key(p) for p in actions} == {packet_key(p) for p in expected_actions},
        'actual complete action journal differs from the sole placement and sole clear')
    action_packets(wire, owner, placed['drag_started_at'], placed['drag_finished_at'], placed['placement']['slot0'])
    action_packets(wire, owner, operation['clear_started_at'], operation['clear_finished_at'], placed['placement']['slot0'], clear=True)
    for p in claimed:
        event_session = (owner if p['direction'] in ('to_native', 'from_native') or
            p['name'] == 'CMSG_PLAYER_LOGIN' or p['name'] == 'SMSG_LOGOUT_COMPLETE' else physical)
        found = [e for e in relevant_events if e.get('session') == event_session and e.get('name') == p['name'] and
            e.get('direction') == p['direction'] and type(e.get('bytes')) is int and e['bytes'] == len(bytes.fromhex(p['body'])) and
            finite(e.get('time')) and 0 <= p['time'] - e['time'] < .1]
        require(len(found) == 1 and found[0].get('event') ==
            ('native_packet' if p['direction'] in ('to_native', 'from_native') else 'modern_packet'),
            'actual unique physical/native packet metadata attribution differs')
    return actual_owner


def proof(data, digests, tracking):
    store = Sources(data, digests)
    require(len(store.ancestry) == 1, 'one complete actual carried UI170 ancestry manifest is required')
    ancestry = store.ancestry[0]
    mapped = ancestry.get('sources')
    from .checkpoint_item_actionbar import MAX_SOURCES, source_graph
    require(type(mapped) is list and 5 <= len(mapped) <= MAX_SOURCES and
        all(type(r) is dict for r in mapped) and len({r.get('original_path') for r in mapped}) == len(mapped),
        'bounded predecessor JSON authorities and required ancestors must be carried once')
    for row in mapped:
        require(type(row) is dict and set(row) == {'original_path', 'sha256', 'copy_path', 'bytes'} and
            type(row.get('bytes')) is int and row['bytes'] > 0 and
            type(row.get('original_path')) is str and Path(row['original_path']).is_absolute() and
            Path(row['original_path']).is_relative_to(lab.ROOT / 'evidence') and
            type(row.get('copy_path')) is str and Path(row['copy_path']).is_absolute() and
            Path(row['copy_path']).is_relative_to(lab.ROOT / 'evidence') and
            type(row.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', row['sha256']) and
            Path(row['copy_path']).name == row['sha256'] + '.json', 'exact carried source member schema differs')
        member = str(Path(row['copy_path']).relative_to(lab.ROOT))
        require(digests.get(member) == row['sha256'] and tracking.get('manifest', {}).get(member, {}).get('bytes') == row['bytes'],
            'carried authority differs from actual complete bytes and SHA256')
    closures = [e for e in data.values() if type(e) is dict and e.get('phase') == PHASE]
    require(len(closures) == 1, 'one distinct successful item closed pause is required')
    closure = accepted(closures[0], PHASE)
    markers = [v for v in data.values() if type(v) is dict and v.get('schema') == 'client442_item_actionbar_consumed_attempt_v1']
    require(len(markers) == 2 and {m.get('kind') for m in markers} == {'drag', 'clear'},
        'one durable drag marker and one durable clear marker are required')
    result, snapshot, current = lifecycle(store, closure.get('sources'))
    ready = current[0]
    expected = source_graph(ready['predecessor'], lambda ref: store.get(ref, False))
    require(sorted([{'path': row['original_path'], 'sha256': row['sha256']} for row in mapped],
        key=lambda row: row['path']) == expected,
        'carried predecessor graph omits or substitutes a required immutable ancestor')
    pointer_observation(store, ready)
    checks(closure, 'shutdown_checks', SHUTDOWN_CHECKS)
    require(closure.get('proof') == result and closure.get('before') == closure.get('after') ==
        closure.get('all_offline_snapshot') == snapshot and closure.get('actor') == ready['actor'] and
        closure.get('runtime') == ready['runtime'] and closure.get('predecessor') == ready['predecessor'] and
        closure.get('primary_stop_source') == ready['predecessor']['primary_stop'] and
        closure.get('code_commit') == current[-1]['code_commit'] and
        closure.get('controller') == 'code' and closure.get('model') is None and closure.get('revision') is None and
        closure.get('custom_script_permission') == 'blocked_by_user' and closure.get('softTargetInteract') == SCRIPT_BOUNDARY and
        closure.get('input_sent') is False and closure.get('mutation_sent') is False and closure.get('qualification_added') is False and
        closure.get('action') == 'stop_parked_scout_after_item_roundtrip' and closure.get('stop_attempted') is True and
        type(closure.get('game_before', {}).get('pid')) is int and closure['game_before']['pid'] > 0 and
        type(closure['game_before'].get('start_ticks')) is str and
        re.fullmatch('[1-9][0-9]*', closure['game_before']['start_ticks']) and
        current[-1]['finished_at'] <= closure['started_at'], 'complete exact original scout closed resource pause differs')
    review = screen_review(store, closure, closure['sources']['park'], 'Harnesstwo')
    require((review.get('selected_character'), review.get('selected_level')) == ('Harnesstwo', 1),
        'final original selection differs')
    actual_packets(store, closure, tracking)
    return {**result, 'shutdown_checks': 8, 'both_owned_clients_stopped': True, 'actual_packet_journals_verified': True}


def local(directory):
    directory = Path(directory)
    data, digests = {}, {}
    for path in sorted(directory.rglob('*.json')):
        require(not path.is_symlink(), 'local proof refuses symlink evidence')
        member = str(path.relative_to(lab.ROOT))
        data[member], digests[member] = json.loads(path.read_text()), bound(path)['sha256']
    tracking = tracking_state()
    tracking.update(digests=digests, manifest={str(p.relative_to(lab.ROOT)): {'bytes': p.stat().st_size}
        for p in directory.rglob('*') if p.is_file()})
    from .observation.journal import entries
    for member, path in zip(TRACKING_MEMBERS, (lab.ROOT / 'evidence/world_packets.jsonl', lab.ROOT / 'logs/modern_world.jsonl')):
        collect(member, entries(path), data, tracking)
    for path in directory.rglob('*.png'):
        digests[str(path.relative_to(lab.ROOT))] = bound(path)['sha256']
    return proof(data, digests, tracking)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    a = parser.parse_args()
    print(json.dumps(local(a.directory)), flush=True)


if __name__ == '__main__':
    main()
