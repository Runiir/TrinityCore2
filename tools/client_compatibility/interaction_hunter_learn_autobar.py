"""Review, then ordinarily clear only an attributed client-added Beast Lore."""
import argparse
from copy import deepcopy
import ctypes as ct
import hashlib
import json
from pathlib import Path
import struct
import time

from . import lab_runtime as lab
from .hunter_learn_autobar import (SPELL, ACTION, PICKUP_SOURCE, BINDING_SOURCE, require, finite,
    addition_guard, clear_guard, public_slot, request_pair)
from .hunter_learn_contract import reconciled_known, learned_checks, BASE_SPELLS
from .hunter_learn_sources import closed, private_json
from .hunter_rest_accrual import bound
from .observation.inventory import Inventory
from .observation.journal import entries


def detail(*args):
    from .interaction_actionbar_pages import detail as read
    return read(*args)


def protected(*args):
    from .interaction_hunter_fixture import protected as read
    return read(*args)


def baseline(*args):
    from .interaction_spellbook_learn_spell import baseline as read
    return read(*args)


def saved(*args):
    from .interaction_owned_class_fixture import saved as read
    return read(*args)


def reviewed(*args):
    from .interaction_owned_class_fixture import reviewed as read
    return read(*args)


def resources(*args):
    from .interaction_spellbook_recon import resources as read
    return read(*args)


def purchase_episode(path):
    e = private_json(path)
    require(finite(e.get('started_at')) and finite(e.get('finished_at')) and
        e['started_at'] < e['finished_at'], 'auto-placement source is not closed')
    recovery = (e.get('completed') is False and type(e.get('failure')) is str and bool(e['failure']) and
        e.get('purchase_input_sent') is True)
    require((e.get('completed') is True and e.get('failure') is None and
        e.get('phase') == 'hunter_learn_transition_complete') or recovery,
        'requires a completed transition or a closed failed paid purchase for housekeeping only')
    return e, recovery


def purchase_packets(session, since, until):
    names = {ACTION, 'CMSG_TRAINER_BUY_SPELL', 'SMSG_TRAINER_BUY_SUCCEEDED', 'SMSG_TRAINER_BUY_FAILED',
        'SMSG_LEARNED_SPELL', 'SMSG_LEARNED_SPELLS', 'CMSG_CAST_SPELL', 'CMSG_PET_ACTION'}
    return [p for p in entries(lab.ROOT / 'evidence/world_packets.jsonl')
        if p.get('session') == session and since <= p.get('time', 0) <= until and p.get('name') in names]


def no_cast_pet(e, session, until):
    ref = e['entry_source']
    entry = private_json(Path(ref['path']))
    require(bound(Path(ref['path'])) == ref and entry.get('native_session') == session and
        entry.get('actor') == e.get('actor') and entry.get('runtime') == e.get('runtime') and
        finite(entry.get('started_at')) and entry['started_at'] <= until,
        'paid recovery requires its exact owned ordinary entry interval')
    require(not any(p.get('session') == session and entry['started_at'] <= p.get('time', 0) <= until and
        p.get('name') in ('CMSG_CAST_SPELL', 'CMSG_PET_ACTION')
        for p in entries(lab.ROOT / 'evidence/world_packets.jsonl')),
        'owned cast or pet-action input occurred before paid action cleanup')


def observed_failed_purchase(e, session, observation=None, t=None):
    """Recover lost outcome observations without changing the failed receipt."""
    if observation is None:
        require(t is not None, 'paid purchase recovery requires fresh read-only observations')
        after_saved = saved(6)
        after_resources = resources(Inventory(lab.ROOT, session, 6).poll())
        shown = detail(t, 'hunter_learn_failed_purchase_public')
        until = time.time()
        rows = purchase_packets(session, e['purchase_started_at'], until)
        no_cast_pet(e, session, until)
        modern = [p for p in rows if p.get('name') == ACTION and p.get('direction') == 'from_client']
        require(len(modern) == 1 and len(bytes.fromhex(modern[0]['body'])) == 5,
            'paid persistence requires one attributable modern auto-placement request')
        value, slot0 = struct.unpack('<IB', bytes.fromhex(modern[0]['body']))
        require(value == SPELL, 'paid persistence refuses another placed action')
        spec = e['baseline']['snapshot']['6']['native']['activeTalentGroup']
        expected_actions = sorted(e['baseline']['saved']['actions'] + [[spec, slot0, SPELL, 0]])
        inserted = addition_guard(e['baseline']['saved']['actions'], expected_actions, rows, session,
            e['purchase_started_at'], until, spec, shown)
        expected_saved = {**e['baseline']['saved'], 'actions': inserted['after_actions'],
            'spells': sorted(BASE_SPELLS + [[SPELL, 1, 0]])}
        checks = learned_checks(rows, e['baseline']['saved']['spells'], expected_saved['spells'],
            e['baseline']['resources'], after_resources, session, e['purchase_started_at'], until)
        require(all(checks.values()) and after_saved in (e['baseline']['saved'], expected_saved),
            'native paid persistence refuses a charge, learned event or full saved-state mismatch')
        authority = {'purchase_packets': rows, 'native_checks': checks, 'auto_action_placement': inserted,
            'saved_before_persistence': after_saved, 'resources_before_persistence': after_resources,
            'observed_at': until}
        t.receipt.update(recovery_native_authority=authority, recovery_only=True, failed_whole_excluded=True,
            qualification_added=False)
        t.persist()
        if after_saved == e['baseline']['saved']:
            t.receipt['recovery_saveall_sent'] = True
            t.persist()
            lab.server_command('saveall')
            time.sleep(.5)
            after_saved = saved(6)
            after_persist_resources = resources(Inventory(lab.ROOT, session, 6).poll())
            after_persist_public = detail(t, 'hunter_learn_failed_purchase_persisted_public')
            require(after_saved == expected_saved and after_persist_resources == after_resources and
                same_public(shown, after_persist_public), 'guarded SaveAll did not preserve exact paid acquisition')
            shown = after_persist_public
            until = time.time()
            no_cast_pet(e, session, until)
        observation = {'after_saved': after_saved, 'after_resources': after_resources,
            'public_actionbar_after': shown, 'purchase_finished_at': until,
            'purchase_packets': purchase_packets(session, e['purchase_started_at'], until)}
    require(set(observation) == {'after_saved', 'after_resources', 'public_actionbar_after',
        'purchase_finished_at', 'purchase_packets'} and finite(observation['purchase_finished_at']) and
        e['purchase_started_at'] <= observation['purchase_finished_at'] <= time.time() and
        observation['purchase_packets'] == purchase_packets(session, e['purchase_started_at'],
            observation['purchase_finished_at']), 'recovered paid observations differ from the immutable owned journal')
    reconstructed = deepcopy(e)
    reconstructed.update(deepcopy(observation))
    return reconstructed, deepcopy(observation)


def stock_sources():
    """Verify stock pickup handlers in memory; do not extract installed files."""
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
    storage = handle()
    require(lib.CascOpenStorage(str(lab.BASE.parent).encode(), 2, ct.byref(storage)), 'local stock storage is unavailable')
    try:
        for source in (PICKUP_SOURCE, BINDING_SOURCE):
            file = handle()
            require(lib.CascOpenFile(storage, source['path'].encode(), 2, 16, ct.byref(file)), 'stock pickup source is absent')
            try:
                size = lib.CascGetFileSize(file, None)
                require(0 < size < 2_000_000, 'stock pickup source size differs')
                data, count = ct.create_string_buffer(size), ct.c_uint32()
                require(lib.CascReadFile(file, data, size, ct.byref(count)) and count.value == size and
                    hashlib.sha256(data.raw).hexdigest() == source['sha256'], 'installed stock pickup source digest differs')
            finally:
                lib.CascCloseFile(file)
    finally:
        lib.CascCloseStorage(storage)
    return deepcopy([PICKUP_SOURCE, BINDING_SOURCE])


def purchase(t, preparation, source):
    old, session = baseline(t, preparation)
    stage, recovery = purchase_episode(source) if private_json(source).get('phase') != 'hunter_learn_auto_action_restore_ready' else (closed(source), False)
    capture_source = None
    if stage.get('phase') == 'hunter_learn_auto_action_restore_ready':
        capture_source = bound(source)
        e, recovery = purchase_episode(Path(stage['purchase_source']['path']))
        require(bound(Path(stage['purchase_source']['path'])) == stage['purchase_source'], 'original purchase source digest differs')
    else:
        e = stage
    require(all(v.get('actor') == t.fixture and v.get('runtime') == t.receipt['runtime'] and
            v.get('native_session') == session and v.get('fixture_source') == bound(preparation) for v in (e, stage)),
        'one source-bound owned paid purchase with a pending action placement is required')
    purchase_source = stage['purchase_source'] if capture_source else bound(source)
    t.receipt.update(source=purchase_source, purchase_source=purchase_source, native_session=session)
    t.persist()
    no_cast_pet(e, session, time.time())
    recovered = stage.get('recovery_observation') if capture_source else None
    if recovery and (recovered or not e.get('purchase_packets') or not e.get('after_saved') or
            not e.get('after_resources') or not ((e.get('auto_action_placement') or {}).get('public') or
                e.get('public_actionbar_after'))):
        e, recovered = observed_failed_purchase(e, session, recovered, t)
        if not capture_source:
            stage = e
        t.receipt['recovery_observation'] = recovered
        if capture_source:
            require(stage['started_at'] <= recovered['purchase_finished_at'] <= stage['finished_at'],
                'failed paid recovery observation is outside its fresh capture')
    native_checks = learned_checks(e['purchase_packets'], e['baseline']['saved']['spells'], e['after_saved']['spells'],
        e['baseline']['resources'], e['after_resources'], session, e['purchase_started_at'], e['purchase_finished_at'])
    require(all(native_checks.values()) and e['baseline']['saved']['spells'] == BASE_SPELLS,
        'closed purchase lacks exact new native learning and charge')
    if not recovery:
        require(e.get('actionbar_restoration_required') is True and e.get('auto_action_placement'),
            'completed purchase lacks its pending placement condition')
        reconciled_known(e['login_known_spell_ids'], e['purchase_packets'], e['purchase_checks'])
    spec = e['baseline']['snapshot']['6']['native']['activeTalentGroup']
    shown = (e.get('auto_action_placement') or {}).get('public') or e.get('public_actionbar_after')
    require(shown, 'closed failed purchase lacks actual public placement evidence; capture independent diagnostics first')
    proof = addition_guard(e['baseline']['saved']['actions'], e['after_saved']['actions'], e['purchase_packets'],
        session, e['purchase_started_at'], e['purchase_finished_at'], spec, shown)
    require(proof and (not e.get('auto_action_placement') or proof == e['auto_action_placement']) and
        e['after_saved'] == {**e['baseline']['saved'], 'actions': proof['after_actions'],
            'spells': sorted(BASE_SPELLS + [[SPELL, 1, 0]])},
        'pending placement differs from actual purchase packets or full saved rows')
    purchase_source = stage['purchase_source'] if capture_source else bound(source)
    if capture_source:
        require(stage.get('source') == purchase_source and stage.get('after_saved') == e['after_saved'] and
            stage.get('after_resources') == e['after_resources'] and stage.get('auto_action_placement') == proof and
            stage.get('recovery_only') is recovery and stage.get('failed_whole_excluded') is recovery and
            stage['finished_at'] >= e['finished_at'], 'fresh restore capture differs from its purchase')
    t.receipt.update(source=purchase_source, purchase_source=purchase_source, capture_source=capture_source,
        fixture_source=bound(preparation), native_session=session, auto_action_placement=proof,
        actionbar_restoration_required=True, qualification_added=False, recovery_only=recovery,
        failed_whole_excluded=recovery)
    t.persist()
    return old, session, e, stage, proof


def same_public(left, right):
    keys = ('active_spec', 'page', 'effective_page', 'bonus_offset', 'viewport')
    rows = lambda p: [(r.get('button'), r.get('slot'), r.get('kind'), r.get('id'), r.get('visible'))
        for r in p.get('actions', [])]
    return all(left.get(k) == right.get(k) for k in keys) and rows(left) == rows(right)


def current(t, e, proof, session, label):
    before_saved = saved(6)
    before_resources = resources(Inventory(lab.ROOT, session, 6).poll())
    public = detail(t, label + '_public')
    button = public_slot(public, before_saved['actions'], proof['active_spec'], proof['slot0'], SPELL)
    state, frame = t.observe(label + '_rendered')
    require(before_saved == e['after_saved'] and before_resources == e['after_resources'] and
        same_public(public, proof['public']) and not state.get('cursor_info') and not state.get('spell_targeting') and
        not state.get('lua_errors') and not state.get('blocked_actions'),
        'current full saved actions, resources, public slot or cursor differ before cleanup')
    return before_saved, before_resources, public, button, state, frame


def capture(t, preparation, source):
    old, session, e, stage, proof = purchase(t, preparation, source)
    require(t.receipt.get('capture_source') is None, 'fresh restore capture must bind the original purchase')
    after_saved, after_resources, public, button, state, frame = current(t, e, proof, session, 'hunter_learn_auto_action_before')
    require(all(protected(old).values()), 'protected actors differ before action cleanup')
    t.receipt.update(after_saved=after_saved, after_resources=after_resources, public=public, button=button,
        state=state, frame=frame, stock_pickup_sources=stock_sources(), protected_checks=protected(old),
        input_sent=False, completed=True, phase='hunter_learn_auto_action_restore_ready')


def reviewed_points(t, review_path, source, stage, proof, public, button):
    d = reviewed(t, review_path, button['button'])
    end = d.get('empty_point', [])
    require(d.get('source') == bound(source) and d.get('frame') == stage.get('frame') and
        d.get('purchase_source', t.receipt['purchase_source']) == t.receipt['purchase_source'] and
        type(d.get('slot0')) is int and d['slot0'] == proof['slot0'] and d.get('spell') == SPELL and
        d.get('public_button') == button and d.get('empty_point_reviewed') is True and
        d.get('pickup_point_inside_button') is True and d.get('empty_point_world_space') is True and
        len(end) == 2 and all(type(v) is int for v in end) and 0 <= end[0] < 1280 and 0 <= end[1] < 720 and
        d['point'] != end and same_public(stage.get('public', proof['public']), public),
        'review must bind the actual inserted button and a fresh empty world drop point')
    return d['point'], end


def screen_geometry(t, review_path, stage, state, frame, start, end):
    """Prevent input after panel, viewport or reviewed point pixels move."""
    previous = stage.get('state', {})
    require(state.get('panels', []) == previous.get('panels', []) and
        state.get('bags', []) == previous.get('bags', []), 'reviewed panels or bags changed before action cleanup')
    from PIL import Image
    reviewed_image = Path(review_path).parent / stage['frame']['file']
    current_image = t.out / frame['file']
    with Image.open(reviewed_image) as old, Image.open(current_image) as fresh:
        require(old.size == fresh.size == (1280, 720), 'reviewed cleanup viewport differs')
        old, fresh = old.convert('RGB'), fresh.convert('RGB')
        regions = []
        for point, radius in ((start, 16), (end, 8)):
            x, y = point
            box = (max(0, x - radius), max(0, y - radius), min(1280, x + radius), min(720, y + radius))
            require(old.crop(box).tobytes() == fresh.crop(box).tobytes(),
                'reviewed pickup or empty-world point pixels changed; capture and review again before input')
            regions.append(list(box))
    return {'reviewed_frame': stage['frame'], 'current_frame': frame, 'regions': regions, 'exact_pixels': True}


def action_packets(session, since, until):
    return [p for p in entries(lab.ROOT / 'evidence/world_packets.jsonl')
        if p.get('session') == session and since <= p.get('time', 0) <= until and p.get('name') == ACTION]


def repair(t, preparation, purchase_source, review_path):
    old, session, e, stage, proof = purchase(t, preparation, purchase_source)
    before_saved, before_resources, public, button, state, frame = current(t, e, proof, session, 'hunter_learn_auto_action_restore')
    start, end = reviewed_points(t, review_path, purchase_source, stage, proof, public, button)
    geometry = screen_geometry(t, review_path, stage, state, frame, start, end)
    require(all(protected(old).values()), 'protected actors differ before action cleanup')
    sources = stock_sources()
    since = time.time()
    t.receipt.update(before_saved=before_saved, before_resources=before_resources, public_before=public, before_state=state,
        before_frame=frame, cursor_before_clear=state.get('cursor_info'), stock_pickup_sources=sources,
        geometry_proof=geometry,
        clear_started_at=since, input_sent=True, clear_input_sent=True,
        bar_restore_input={'kind': 'shift_drag', 'start': start, 'end': end, 'slot0': proof['slot0'],
            'spell': SPELL, 'reviewed_frame': stage['frame'], 'source': bound(review_path)})
    t.persist()
    with t.io.hold_modifier('shift'):
        t.io.drag(start, end)
    deadline = time.monotonic() + 16
    while True:
        public_after = detail(t, 'hunter_learn_auto_action_clear_wait')
        state, frame = t.observe('hunter_learn_auto_action_cursor')
        until = time.time()
        packets = action_packets(session, since, until)
        t.receipt.update(clear_packets=packets, clear_finished_at=until, public_after_clear=public_after,
            clear_frame=frame, clear_state=state,
            cursor_cancel_input={'kind': 'click', 'value': end, 'button': 3, 'source': bound(review_path)})
        t.persist()
        target = next((r for r in public_after['actions'] if r['slot'] == proof['slot0'] + 1), {})
        if not target.get('kind') and len(packets) >= 2:
            break
        require(time.monotonic() < deadline, 'action-slot clear did not settle; refusing input replay')
        time.sleep(.2)
    cursor = state.get('cursor_info')
    no_cast_pet(e, session, until)
    require(type(cursor) is list and cursor and cursor[0] == 'spell' and SPELL in cursor[1:] and not state.get('spell_targeting'),
        'ordinary pickup did not produce the carried spell cursor')
    # Verify the actual clear pair before cancelling the carried cursor or saving.
    modern, native = request_pair(packets, proof['slot0'], 0)
    empty_button = public_slot(public_after, proof['before_actions'], proof['active_spec'], proof['slot0'], 0)
    t.receipt.update(clear_packets=packets, clear_finished_at=until, public_after_clear=public_after,
        clear_frame=frame, clear_state=state,
        clear_request_proof={'modern': modern, 'native': native, 'button': empty_button}, cursor_before_cancel=cursor,
        cursor_cancel_input={'kind': 'click', 'value': end, 'button': 3, 'source': bound(review_path)})
    t.persist()
    t.execute({'kind': 'click', 'value': end, 'button': 3})
    deadline = time.monotonic() + 16
    while True:
        state, frame = t.observe('hunter_learn_auto_action_cursor_cancel_wait')
        if not state.get('cursor_info'):
            break
        require(time.monotonic() < deadline, 'carried spell cursor did not cancel; refusing input replay')
        time.sleep(.2)
    lab.server_command('saveall')
    time.sleep(.5)
    after_saved = saved(6)
    after_resources = resources(Inventory(lab.ROOT, session, 6).poll())
    public_after = detail(t, 'hunter_learn_auto_action_restored_public')
    until = time.time()
    packets = action_packets(session, since, until)
    final_proof = clear_guard(proof, after_saved['actions'], packets, session, since, until, public_after)
    checks = {**final_proof['checks'], 'full_saved_rows_restored':
        after_saved == {**before_saved, 'actions': proof['before_actions']},
        'original_resources_preserved': before_resources == after_resources == e['after_resources'],
        'ordinary_shift_drag': t.receipt['clear_input_sent'] is True,
        'carried_cursor_cancelled': not state.get('cursor_info'), 'protected_originals': all(protected(old).values()),
        'ui_clean': not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(after_saved=after_saved, after_resources=after_resources, public_after=public_after,
        clear_packets=packets, clear_finished_at=until, clear_proof=final_proof,
        cursor_after_cancel=state.get('cursor_info'), cursor_cancel_frame=frame,
        restoration_checks=checks, protected_checks=protected(old))
    t.persist()
    require(all(checks.values()), 'ordinary action cleanup changed owner resources, saved rows or protected actors')
    t.receipt.update(completed=True, phase='hunter_learn_auto_action_restored', actionbar_restored=True)


def settle(t, preparation, failed_source):
    """Finish a failed clear's cursor housekeeping; never pick up a slot twice."""
    failed = private_json(failed_source)
    require(failed.get('completed') is False and type(failed.get('failure')) is str and bool(failed['failure']) and
        finite(failed.get('started_at')) and finite(failed.get('finished_at')) and
        failed['started_at'] < failed['finished_at'] and failed.get('clear_input_sent') is True and
        failed.get('qualification_added') is False and failed.get('source') == failed.get('purchase_source'),
        'settle requires a closed failed ordinary repair')
    original = Path(failed['purchase_source']['path'])
    require(bound(original) == failed['purchase_source'], 'failed repair original purchase digest differs')
    origin_stage = original
    if failed.get('capture_source'):
        origin_stage = Path(failed['capture_source']['path'])
        require(bound(origin_stage) == failed['capture_source'], 'failed repair capture digest differs')
    old, session, e, _, proof = purchase(t, preparation, origin_stage)
    require(failed.get('actor') == t.fixture and failed.get('runtime') == t.receipt['runtime'] and
        failed.get('native_session') == session and failed.get('fixture_source') == bound(preparation) and
        failed.get('auto_action_placement') == proof and failed.get('before_saved') == e['after_saved'] and
        failed.get('before_resources') == e['after_resources'] and
        finite(failed.get('clear_started_at')) and
        e['finished_at'] <= failed['started_at'] <= failed['clear_started_at'] <=
            failed['finished_at'] and (failed.get('clear_finished_at') is None or
                (finite(failed['clear_finished_at']) and failed['clear_started_at'] <=
                    failed['clear_finished_at'] <= failed['finished_at'])),
        'failed clear actor, full baseline or chronology differs')
    expected = {**e['after_saved'], 'actions': proof['before_actions']}
    before_saved = saved(6)
    before_resources = resources(Inventory(lab.ROOT, session, 6).poll())
    public_before = detail(t, 'hunter_learn_auto_action_settle_public')
    state, frame = t.observe('hunter_learn_auto_action_settle_cursor')
    until = time.time()
    rows = action_packets(session, failed['clear_started_at'], until)
    modern, native = request_pair(rows, proof['slot0'], 0)
    empty_button = public_slot(public_before, proof['before_actions'], proof['active_spec'], proof['slot0'], 0)
    recorded = failed.get('clear_request_proof')
    source_rows = action_packets(session, failed['clear_started_at'], failed['finished_at'])
    source_modern, source_native = request_pair(source_rows, proof['slot0'], 0)
    if not recorded:
        require(all(p in source_rows for p in failed.get('clear_packets', [])),
            'retained partial clear records differ from the bounded failed journal')
        recorded = {'modern': source_modern, 'native': source_native, 'button': empty_button}
    require(before_saved in (expected, e['after_saved']) and before_resources == e['after_resources'] and
        modern == recorded['modern'] and native == recorded['native'] and
        source_modern == modern and source_native == native and
        all(protected(old).values()) and not state.get('spell_targeting') and not state.get('lua_errors') and
        not state.get('blocked_actions'), 'failed clear has not retained exact saved baseline, public slot and resources')
    cursor = state.get('cursor_info')
    expected_cursor = failed.get('cursor_before_cancel') or (failed.get('clear_state') or {}).get('cursor_info')
    require(not cursor or (type(cursor) is list and cursor[0] == 'spell' and SPELL in cursor[1:] and
        expected_cursor and cursor == expected_cursor),
        'settle refuses a different or unattributed carried cursor')
    if cursor:
        intent = failed.get('cursor_cancel_input', {})
        point = intent.get('value')
        require(intent.get('kind') == 'click' and intent.get('button') == 3 and
            type(point) is list and len(point) == 2 and all(type(v) is int for v in point) and
            0 <= point[0] < 1280 and 0 <= point[1] < 720,
            'failed repair lacks its retained valid cursor-cancel intent; no settlement input is permitted')
    no_cast_pet(e, session, until)
    # A failed cancellation may precede SaveAll. The actual native/public clear
    # is verified first, then SaveAll must project exactly the original rows.
    lab.server_command('saveall')
    time.sleep(.5)
    saved_after_clear_save = saved(6)
    require(saved_after_clear_save == expected, 'native clear did not save the complete original action baseline')
    current_clear = clear_guard(proof, saved_after_clear_save['actions'], rows, session,
        failed['clear_started_at'], until, public_before)
    t.receipt.update(failed_repair_source=bound(failed_source), settlement_only=True, failed_repair_excluded=True,
        before_saved=before_saved, before_resources=before_resources, public_before=public_before,
        saved_after_clear_save=saved_after_clear_save,
        cursor_before_clear=failed.get('cursor_before_clear'), cursor_before_cancel=cursor,
        clear_started_at=failed['clear_started_at'], clear_finished_at=until, clear_packets=rows,
        clear_proof=current_clear, clear_request_proof=recorded,
        source_clear_packets=source_rows, source_clear_finished_at=failed['finished_at'],
        journal_reconstructed_clear=not failed.get('clear_request_proof'),
        bar_restore_input=failed['bar_restore_input'], screen_review=failed['screen_review'],
        geometry_proof=failed.get('geometry_proof'), stock_pickup_sources=stock_sources(),
        input_sent=False, clear_input_sent=False, cursor_settlement_before_frame=frame)
    t.persist()
    if cursor:
        clear_frame = failed.get('clear_frame', {})
        image = Path(failed_source).parent / clear_frame.get('file', '')
        require(image.is_file() and not image.is_symlink() and
            image.resolve().is_relative_to(lab.ROOT / 'evidence') and
            lab.sha256(image) == clear_frame.get('sha256') and type(failed.get('clear_state')) is dict,
            'carried cursor settlement requires its authenticated original clear frame and state')
        geometry = screen_geometry(t, failed_source, {'frame': clear_frame, 'state': failed['clear_state']},
            state, frame, point, point)
        t.receipt['cursor_settlement_geometry'] = geometry
        t.receipt.update(input_sent=True, cursor_cancel_input=failed['cursor_cancel_input'])
        t.persist()
        t.execute({'kind': 'click', 'value': point, 'button': 3})
        deadline = time.monotonic() + 16
        while True:
            state, frame = t.observe('hunter_learn_auto_action_settle_cancel_wait')
            if not state.get('cursor_info'):
                break
            require(time.monotonic() < deadline, 'carried spell cursor settlement did not finish; refusing input replay')
            time.sleep(.2)
    after_saved = saved(6)
    after_resources = resources(Inventory(lab.ROOT, session, 6).poll())
    public_after = detail(t, 'hunter_learn_auto_action_settle_restored')
    until = time.time()
    rows = action_packets(session, failed['clear_started_at'], until)
    final_clear = clear_guard(proof, after_saved['actions'], rows, session,
        failed['clear_started_at'], until, public_after)
    checks = {**final_clear['checks'], 'full_saved_rows_restored': after_saved == saved_after_clear_save == expected,
        'original_resources_preserved': after_resources == before_resources == e['after_resources'],
        'no_shift_drag_replay': t.receipt['clear_input_sent'] is False,
        'carried_cursor_cancelled': not state.get('cursor_info'), 'protected_originals': all(protected(old).values()),
        'ui_clean': not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(after_saved=after_saved, after_resources=after_resources, public_after=public_after,
        clear_packets=rows, clear_finished_at=until, clear_proof=final_clear, restoration_checks=checks,
        cursor_after_cancel=state.get('cursor_info'), cursor_cancel_frame=frame, protected_checks=protected(old))
    t.persist()
    require(all(checks.values()), 'failed clear settlement changed saved rows or original resources')
    t.receipt.update(completed=True, phase='hunter_learn_auto_action_restored', actionbar_restored=True)


def main():
    from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
    from .interaction_social import actor
    from .interaction_trial import Trial
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['capture', 'repair', 'settle'])
    for name in ('preparation', 'source', 'output'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--review', type=Path)
    a = p.parse_args()
    with actor('scout'):
        t = Trial(a.output, controller='code')
        t.receipt.update(custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY)
        try:
            if a.action == 'capture': capture(t, a.preparation, a.source)
            elif a.action == 'repair': repair(t, a.preparation, a.source, a.review)
            else: settle(t, a.preparation, a.source)
        except BaseException as error:
            t.receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
            if not isinstance(error, Exception):
                raise
        finally:
            t.receipt['finished_at'] = time.time()
            t.persist()
        print(json.dumps({k: t.receipt.get(k) for k in ('completed', 'phase', 'failure')}), flush=True)


if __name__ == '__main__':
    main()
