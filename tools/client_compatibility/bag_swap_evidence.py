"""Pure attributable archive proof for one occupied backpack swap and inverse."""
import argparse
from copy import deepcopy
import hashlib
import json
import re
from pathlib import Path

from . import lab_runtime as lab
from . import bag_swap_contract as contract
from .bag_swap_sources import bound, reference, validate_bundle, compact_authority
from .bag_swap_preservation import preserve_six, online_preservation, exact_precision, PRECISION_QUERY
from .bag_swap_projection import delivered_slots
from .item_actionbar_contract import require, finite, strict_equal, public_assignments
from . import item_actionbar_evidence as shared

PHASE = 'bags_swap_closed_paused'
ANCESTRY_SCHEMA = 'client442_bag_swap_ancestry_v1'
ROLES = ('preparation', 'entry', 'operation', 'park', 'before_precision', 'after_precision')
TRACKING_MEMBERS = ('tracking/packets.jsonl', 'tracking/events.jsonl')
MAX_ROWS, MAX_BYTES = 250000, 128 * 1024 * 1024


class Sources:
    def __init__(self, data, digests, local=False):
        self.data, self.digests, self.local = data, digests, local
        self.maps = [v for v in data.values() if type(v) is dict and v.get('schema') in
            (ANCESTRY_SCHEMA, 'client442_bag_swap_fresh_ancestry_v1')]

    def member(self, ref, seen=None):
        reference(ref)
        path = Path(ref['path'])
        require(path.is_relative_to(lab.ROOT / 'evidence'), 'swap source must be original private evidence')
        member = str(path.relative_to(lab.ROOT))
        if self.digests.get(member) == ref['sha256']:
            return member
        seen = set() if seen is None else seen
        identity = (ref['path'], ref['sha256'])
        require(identity not in seen and len(seen) < 8, 'carried source ancestry cycles or exceeds its exact bound')
        seen.add(identity)
        rows = [row for value in self.maps for row in [*value.get('members', []), *value.get('authorities', [])] if type(row) is dict and
            row.get('original_path') == ref['path'] and row.get('sha256') == ref['sha256']]
        require(len(rows) == 1 and type(rows[0].get('copy_member')) is str,
            'immutable swap source absent or ambiguous in carried graph')
        copy = rows[0]['copy_member']
        require(not Path(copy).is_absolute() and '..' not in Path(copy).parts, 'ordinary carried source member required')
        return self.member({'path': str(lab.ROOT / copy), 'sha256': ref['sha256']}, seen)

    def get(self, ref, successful=True):
        reference(ref)
        path = Path(ref['path'])
        require(path.is_relative_to(lab.ROOT / 'evidence'), 'swap source must be original private evidence')
        member = str(path.relative_to(lab.ROOT))
        if member not in self.data and self.local:
            require(bound(path) == ref, 'local immutable swap source changed')
            self.data[member] = json.loads(path.read_text())
            self.digests[member] = ref['sha256']
        key = self.member(ref)
        require(key in self.data and self.digests.get(key) == ref['sha256'], 'exact carried swap source bytes differ')
        value = self.data[key]
        return shared.accepted(value) if successful else value


def local_store(directory=None):
    data, digests = {}, {}
    if directory is not None:
        for path in Path(directory).rglob('*.json'):
            require(not any(p.is_symlink() for p in (path, *path.parents)), 'ordinary local evidence files required')
            member = str(path.relative_to(lab.ROOT))
            data[member], digests[member] = json.loads(path.read_text()), bound(path)['sha256']
        for path in Path(directory).rglob('*.png'):
            digests[str(path.relative_to(lab.ROOT))] = bound(path)['sha256']
    return Sources(data, digests, local=True)


def exact_checks(value, key, names):
    shared.checks(value, key, names)


def precision(value, source, snapshot):
    shared.accepted(value, 'bags_swap_rest_precision_complete')
    exact_checks(value, 'checks', shared.PRECISION_CHECKS)
    require(value.get('source') == source and value.get('before') == value.get('after') == snapshot and
        value.get('query') == PRECISION_QUERY and value.get('input_sent') is False and
        value.get('mutation_sent') is False and value.get('qualification_added') is False,
        'fresh exact read-only actor2 FLOAT boundary required')
    shared.rest_sources(value.get('rest_sources'))
    return exact_precision(value['row'], snapshot)


def frame(store, value, image, source):
    return shared.frame(store, value, image, source)


def predecessor(store, ready, *, live=False):
    ref = ready.get('authority_source')
    compact_ref = ready.get('runtime_authority_source')
    compact = store.get(compact_ref, False)
    from .interaction_bag_swap_continuation import authority_sources
    provider = authority_sources(compact.get('schema'))
    fresh = compact.get('schema') == 'client442_bag_swap_fresh_runtime_authority_v1'
    if live:
        require(store.local and bound(compact_ref['path']) == compact_ref,
            'live compact authority must retain its exact source-owned bytes')
        old = provider.cached_runtime(compact_ref['path'], ref)
        require(compact.get('core') == old, 'live compact source differs from its exact admitted core')
    else:
        cache = store.get(ref, False)
        if fresh:
            old = provider.validate_cache(cache)
        else:
            require(type(cache) is dict and set(cache) == {'schema', 'values', 'refs', 'graph'} and
                cache['schema'] == 'client442_bag_swap_predecessor_authority_v1', 'exact actual UI171 cache required')
            old = validate_bundle(cache['values'], cache['refs'], cache['graph'])
        require(compact == provider.compact_authority(old, ref), 'compact live authority differs from the full admitted source graph')
    require(ready.get('predecessor') == old['predecessor'] and
        ready.get('predecessor_dvc_pointer') == old['dvc_pointer'] and
        ready.get('all_offline_snapshot') == old['snapshot'], 'fresh swap authority differs from its latest actual offline pause')
    resume = store.get(ready['resume_source'], False)
    require(resume.get('schema') == 'client442_bag_swap_scout_resume_v1' and
        resume.get('phase') == 'bags_swap_scout_launched' and resume.get('completed') is True and
        resume.get('failure') is None and resume.get('installed') is True and
        resume.get('authority_source') == ref and resume.get('runtime_authority_source') == compact_ref and
        resume.get('predecessor') == old['predecessor'] and
        resume.get('all_offline_snapshot') == old['snapshot'] and resume.get('origin_actor') == ready['actor'] and
        resume.get('runtime') == ready['runtime'] and resume.get('previous_runtime') == old['runtime'] and
        resume['runtime']['worldserver'] == old['runtime']['worldserver'] and
        resume['runtime']['modern_world'] == old['runtime']['modern_world'] and
        resume['runtime']['client'] != old['runtime']['client'] and
        type(resume.get('available_memory_kib_before')) is int and resume['available_memory_kib_before'] >= 6 * 1024 * 1024 and
        old['closure']['finished_at'] < resume['started_at'] < resume['launch_finished_at'] < ready['started_at'],
        'one fresh owned scout and unchanged native/bridge lifetime required')
    if fresh:
        current_code_epoch(store, resume, ready, old['closure'])
    exact_checks(resume, 'checks', ('native_unchanged', 'bridge_unchanged', 'fresh_scout',
        'all_six_saved_snapshots', 'primary_stopped', 'HDMI_1', 'private_input'))
    auth = ready.get('realm_authentication', {})
    require(auth.get('event') == 'world_authenticated' and type(auth.get('account_id')) is int and auth['account_id'] == 2 and
        auth.get('session') == ready['native_session'] and finite(auth.get('time')) and
        resume['started_at'] <= auth['time'] <= ready['started_at'], 'one fresh retained scout authentication required')
    selected = shared.screen_review(store, ready, ready['selection_source'], 'Harnesstwo')
    require((selected.get('selected_character'), selected.get('selected_level')) == ('Harnesstwo', 1),
        'fresh original scout selection differs')
    return old


def current_code_epoch(store, resume, ready, closure):
    """Prove current raw code bytes while retaining all immutable parent epochs."""
    from .checkpoint_bag_swap import CURRENT_CODE_SCHEMA, FRESH_CODE_FILES
    from .bag_swap_failed_evidence import PUBLICATION_FILES, PUBLICATION_DEPENDENCIES
    from .bag_swap_failed_sources import CODE_FIELDS, CODE_SCHEMA, CONFIG, MAX_TOTAL_BYTES, _raw, _commit, _vector
    ref = ready.get('current_code_epoch_source')
    reference(ref)
    require(resume.get('current_code_epoch_source') == ref, 'fresh resume and ready must bind one current raw code epoch')
    epoch = store.get(ref, False)
    require(type(epoch) is dict and set(epoch) == {'schema', 'code_commit', 'committed_sources', 'carried_sources'} and
        epoch.get('schema') == CURRENT_CODE_SCHEMA and epoch.get('code_commit') == ready.get('code_commit') and
        epoch.get('committed_sources') == ready.get('committed_sources'), 'current raw code epoch differs from frozen gameplay identity')
    _commit(epoch['code_commit'])
    remote = store.get(ready['predecessor']['remote'], False)
    publication = remote.get('proof', {}).get('publication_code', {})
    _commit(publication.get('code_commit'))
    configs = [Path(row['path']) for row in closure['committed_sources'] if row['path'].endswith('/' + CONFIG)]
    require(len(configs) == 1, 'one original occupied-swap repository source required')
    repo = configs[0].parents[3]
    wanted = sorted({row['path'] for row in closure['committed_sources']} | {
        str(repo / member) for member in (*PUBLICATION_FILES, *PUBLICATION_DEPENDENCIES, *FRESH_CODE_FILES)})
    require(_vector(epoch['committed_sources'], repo) == [str(Path(member).relative_to(repo)) for member in wanted] and
        epoch['code_commit'] != publication['code_commit'], 'exact complete fresh current source membership and distinct publication epoch required')
    copies = epoch['carried_sources']
    require(type(copies) is list and len(copies) == len(wanted) and
        len({row.get('path') for row in copies if type(row) is dict}) == len(copies), 'one raw current source envelope per member required')
    total = 0
    for original, copy in zip(epoch['committed_sources'], copies):
        value = store.get(copy, False)
        require(type(value) is dict and set(value) == CODE_FIELDS and value.get('schema') == CODE_SCHEMA and
            value.get('code_commit') == epoch['code_commit'] and value.get('original_path') == original['path'] and
            value.get('sha256') == original['sha256'], 'current source envelope differs from exact frozen epoch')
        total += len(_raw(value['raw_hex'], value['sha256'], value['bytes']))
        require(total <= MAX_TOTAL_BYTES, 'bounded current raw source epoch exceeded')
    return {'code_commit': epoch['code_commit'], 'complete_raw_source_members': len(wanted)}


def stage_chain(store, operation):
    current, result, seen = operation, [], set()
    for _ in range(12):
        result.append(current)
        if current.get('phase') == 'bags_swap_forward_ready' and current.get('backpack_open_review'):
            return list(reversed(result))
        ref = current.get('source')
        reference(ref)
        require(ref['path'] not in seen, 'occupied swap source chain cycles')
        seen.add(ref['path'])
        current = store.get(ref)
    raise RuntimeError('occupied swap source chain exceeds bounded stages')


def attempt(store, stage, kind, entry_ref, ready_ref):
    value = store.get(stage[kind + '_attempt_source'], False)
    intent = stage[kind + '_intent']
    require(value.get('schema') == 'client442_bag_swap_consumed_attempt_v1' and
        value.get('operation') == 'bags.swap_item' and value.get('kind') == kind and
        value.get('consumed') is True and value.get('input_replay_allowed') is False and
        value.get('entry_source') == entry_ref and value.get('preparation_source') == ready_ref and
        value.get('actor') == stage['actor'] and value.get('runtime') == stage['runtime'] and
        value.get('native_session') == stage['native_session'] and value.get('input_intent') == intent and
        finite(value.get('created_at')) and value['created_at'] <= stage[kind + '_started_at'],
        'durably consumed exact once-only occupied drag required')
    source = stage[kind + '_review_source']
    review = store.get(stage[kind + '_review'], False)
    reviewed = store.get(source)
    require(review.get('reviewed') is True and review.get('control') == 'bags.swap_item' and
        review.get('source') == source and review.get('frame') == reviewed['frame'] and
        review.get('point') == intent['start'] and review.get('destination_point') == intent['end'] and
        type(review.get('item')) is int and review['item'] == 6948 and type(review.get('item_guid')) is int and
        review['item_guid'] == 41 and type(review.get('occupied_item')) is int and review['occupied_item'] == 58231 and
        type(review.get('occupied_item_guid')) is int and review['occupied_item_guid'] == 33 and
        review.get('pickup_point_inside_button') is True and review.get('destination_point_inside_button') is True and
        review.get('source_slot') == intent['source_slot'] and review.get('destination_slot') == intent['destination_slot'],
        'exact source-owned reviewed occupied drag required')
    frame(store, reviewed, reviewed['frame'], source)


def opening_review(store, stage, entry_ref, entry):
    review = store.get(stage['backpack_open_review'], False)
    intent = stage.get('backpack_open_input')
    point = review.get('point')
    require(review.get('reviewed') is True and review.get('control') == 'MainMenuBarBackpackButton' and
        review.get('source') == entry_ref and review.get('frame') == entry['frame'] and
        review.get('pickup_point_inside_button') is True and type(point) is list and len(point) == 2 and
        all(type(v) is int for v in point) and 0 <= point[0] < 1280 and 0 <= point[1] < 720 and
        intent == {'kind': 'click', 'value': point}, 'original source-owned ordinary backpack opening differs')
    frame(store, entry, entry['frame'], entry_ref)


def restored_layout(operation, base):
    state, native = operation.get('state', {}), operation.get('native_state')
    original = base['state']
    require(shared.same_public(operation.get('public', {}), base['public']) and
        strict_equal(native, base['native_state']) and
        all(strict_equal(state.get(k), original.get(k)) for k in ('bags', 'panels', 'target', 'world_position')) and
        'cursor_info' in state and shared.empty_cursor(state['cursor_info']) and
        not any(state.get(k) for k in ('spell_targeting', 'lua_errors', 'blocked_actions', 'chat_edit_open')),
        'actual public/native original layout facts did not restore')


def stage_snapshots(baseline, chain):
    for stage in chain:
        if 'snapshot' in stage:
            swapped = stage['snapshot']['2']['inventory'] != baseline['2']['inventory']
            online_preservation(baseline, stage['snapshot'], swapped=swapped)
        for kind in ('forward', 'reverse'):
            if kind + '_snapshot' in stage:
                saved = stage[kind + '_snapshot']
                swapped = True if kind == 'forward' else saved['2']['inventory'] != baseline['2']['inventory']
                online_preservation(baseline, saved, swapped=swapped)


def lifecycle(store, refs, *, live=False):
    require(type(refs) is dict and set(refs) == set(ROLES), 'all six occupied swap lifecycle roles required')
    current = [store.get(refs[k]) for k in ROLES]
    ready, entry, operation, park, before, after = current
    for value, phase in zip(current, ('bags_swap_scout_ready', 'bags_swap_entered', 'bags_swap_restored',
            'bags_swap_parked', 'bags_swap_rest_precision_complete', 'bags_swap_rest_precision_complete')):
        shared.accepted(value, phase)
    require(type(live) is bool, 'local lifecycle mode must be an actual boolean')
    predecessor(store, ready, live=live)
    baseline = ready['all_offline_snapshot']
    contract.owned_snapshot(baseline)
    fresh = store.get(ready['runtime_authority_source'], False).get('schema') == 'client442_bag_swap_fresh_runtime_authority_v1'
    from .interaction_bag_swap_continuation import entry_settlement
    if fresh:
        require(entry.get('native_before_entry') == baseline['2']['native'] and
            type(entry.get('raw_entry_packets')) is list and type(entry.get('raw_entry_events')) is list,
            'fresh entry must retain actual prelogin native state and complete wire/metadata sources')
    boot = entry_settlement(entry, entry.get('raw_entry_packets', []), entry.get('raw_entry_events', []), required=fresh)
    if boot is not None:
        owner = contract.native_replay(entry['raw_entry_packets'], ready['native_session'],
            entry['started_at'], entry['finished_at'], login_sync=boot)
        require(strict_equal(entry.get('native_owner_proof'), owner), 'fresh entry owner proof differs from complete actual source packets')
    require(all(value.get('actor') == ready['actor'] and value.get('runtime') == ready['runtime'] and
        value.get('code_commit') == ready['code_commit'] and value.get('committed_sources') == ready['committed_sources'] and
        value.get('controller') == 'code' and value.get('model') is None and value.get('revision') is None and
        value.get('qualification_added') is False and value.get('custom_script_permission') == 'blocked_by_user' and
        value.get('softTargetInteract') == shared.SCRIPT_BOUNDARY for value in current),
        'frozen ordinary controller/source/script identities differ')
    require(type(ready.get('committed_sources')) is list and len(ready['committed_sources']) >= 16 and
        len({v.get('path') for v in ready['committed_sources']}) == len(ready['committed_sources']),
        'complete distinct frozen swap source hashes required')
    for ref in ready['committed_sources']:
        reference(ref)
    require(ready['finished_at'] <= before['started_at'] < before['finished_at'] <= entry['started_at'] and
        entry['finished_at'] <= operation['started_at'] < operation['finished_at'] <= park['started_at'] and
        park['finished_at'] <= after['started_at'], 'ordinary occupied swap/rest chronology differs')
    exact_before = precision(before, refs['preparation'], baseline)
    final = park['all_offline_snapshot']
    exact_after = precision(after, refs['park'], final)
    preserved = preserve_six(baseline, final, entry, exact_before, exact_after)
    chain = stage_chain(store, operation)
    require(all(s.get('entry_source') == refs['entry'] and s.get('preparation_source') == refs['preparation'] and
        s.get('actor') == ready['actor'] and s.get('runtime') == ready['runtime'] and
        s.get('code_commit') == ready['code_commit'] and s.get('committed_sources') == ready['committed_sources'] and
        s.get('native_session') == ready['native_session'] and s.get('controller') == 'code' and
        s.get('model') is None and s.get('revision') is None and s.get('qualification_added') is False and
        s.get('custom_script_permission') == 'blocked_by_user' and s.get('softTargetInteract') == shared.SCRIPT_BOUNDARY and
        s.get('baseline') == operation['baseline'] for s in chain), 'exact occupied swap source chain differs')
    forward = [s for s in chain if s.get('phase') == 'bags_swap_forward']
    reverse = [s for s in chain if s.get('phase') == 'bags_swap_reverse']
    require(len(forward) == len(reverse) == 1, 'one successful occupied forward and inverse episode required')
    forward, reverse = forward[0], reverse[0]
    opening_review(store, chain[0], refs['entry'], entry)
    stage_snapshots(baseline, chain)
    base = operation['baseline']
    require(base.get('snapshot') == baseline and base.get('resources') == entry['resources'] and
        base.get('saved') == entry['saved'] == baseline['2']['saved'] and base.get('public') == entry['public'] and
        base.get('entry_source') == refs['entry'] and operation.get('after_resources') == entry['resources'] and
        operation.get('after_saved') == baseline['2']['saved'] and operation.get('inventory_restored') is True and
        operation.get('actionbar_restored') is True, 'whole exact original inventory/actions restoration required')
    exact_checks(operation, 'layout_restoration_checks', shared.LAYOUT_CHECKS)
    restored_layout(operation, base)
    for stage, kind, inverse in ((forward, 'forward', False), (reverse, 'reverse', True)):
        raw = stage[kind + '_packets']
        pair = contract.swap_packets(raw, ready['native_session'], stage[kind + '_started_at'],
            stage[kind + '_finished_at'], reverse=inverse)
        transition = stage[kind + '_native_transition']
        require(stage[kind] == pair and stage[kind + '_projection'] == delivered_slots(raw, ready['native_session'],
            transition['time'], stage[kind + '_finished_at'], swapped=not inverse) and
            stage[kind + '_projection']['delivery']['time'] > transition['time'], 'retained exact swap wire/effect delivery proof differs')
        contract.native_resources(entry['resources'], stage[kind + '_resources'], swapped=not inverse)
        contract.public_items(stage['state'], stage[kind + '_resources'], swapped=not inverse)
        attempt(store, stage, kind, refs['entry'], refs['preparation'])
        cursor = stage[kind + '_cursor']
        if not shared.empty_cursor(cursor):
            expected = ['item', 6948 if inverse else 58231]
            require(type(cursor) is list and cursor[:2] == expected, 'displaced occupied-item cursor is not attributable')
            cancellations = [c for c in operation.get('cursor_cancellations', []) if c.get('before_cursor') == cursor and
                stage[kind + '_finished_at'] <= c.get('started_at', 0)]
            require(len(cancellations) == 1 and 'after_cursor' in cancellations[0] and
                shared.empty_cursor(cancellations[0]['after_cursor']) and
                cancellations[0].get('input_replayed') is False, 'one attributable ordinary cursor cancellation required')
            cancellation = cancellations[0]
            review = store.get(cancellation['review'], False)
            reviewed = store.get(cancellation['source'])
            require(review.get('reviewed') is True and review.get('control') == 'bags.swap_item.cancel_cursor' and
                review.get('source') == cancellation['source'] and review.get('frame') == reviewed['frame'] and
                review.get('cursor') == cursor and review.get('empty_point_world_space') is True and
                review.get('empty_point_reviewed') is True and review.get('empty_point') == cancellation['input']['value'] and
                cancellation['input'].get('button') == 3 and not any(p.get('name') == contract.ACTION
                    for p in cancellation['packets']), 'ordinary cancellation source/input or packet proof differs')
            frame(store, reviewed, reviewed['frame'], cancellation['source'])
    autosave = forward.get('autosave', {})
    require(autosave.get('mechanism') == 'native_PlayerSaveInterval' and autosave.get('bound_seconds') == 150 and
        autosave.get('heartbeat_seconds') == 2 and autosave.get('persisted') is True and
        autosave.get('saveall_sent') is False and autosave.get('sql_write_sent') is False and
        finite(autosave.get('elapsed_seconds')) and 0 <= autosave['elapsed_seconds'] <= 150,
        'forward persistence must be attributable to the bounded native autosave')
    require(type(autosave.get('configured_interval_ms')) is int and autosave['configured_interval_ms'] == 90000 and
        autosave.get('first_timer_ms') == [45000, 135000] and autosave.get('config_source') == before['rest_sources']['config_source'] and
        autosave.get('native_timer_source') == before['rest_sources']['native_formula_source'],
        'native autosave interval/configuration must match the exact source-bound rest runtime')
    contract.inventory_rows(baseline['2']['inventory'], forward['forward_snapshot']['2']['inventory'], swapped=True)
    require(forward['forward_finished_at'] <= reverse['reverse_started_at'], 'inverse drag must follow proved forward swap')
    exact_checks(park, 'checks', shared.PARK_CHECKS)
    require(park.get('source') == refs['operation'] and park.get('entry_source') == refs['entry'],
        'ordinary logout must follow full occupied-swap restoration')
    require(strict_equal(park.get('pre_logout_native_state'), base['native_state']),
        'ordinary logout must retain the actual original native pose, target and AFK')
    closed = contract.native_replay(park['raw_native_logout_history'], ready['native_session'],
        entry['started_at'], park['logout_packets'][1]['time'],
        rest_threshold=entry['native_owner_proof']['rest_threshold'], login_sync=boot)
    require(park.get('native_logout_proof') == closed and len(closed['native_inventory_transitions']) == 3,
        'whole owner/item history through actual native logout completion differs')
    frame(store, entry, entry['frame'], refs['entry'])
    frame(store, park, park['frame'], refs['park'])
    from .interaction_item_actionbar_parked_selection_capture import frame_identity
    frame_identity(entry['frame'], ready['runtime'], ready['frame'])
    frame_identity(park['frame'], ready['runtime'], entry['frame'])
    result = {'operation': 'bags.swap_item', 'owner': 2, 'items': [6948, 58231], 'item_guids': [41, 33],
        'modern_swap_pairs': 2, 'native_swap_pairs': 2, 'occupied_slots_exchanged': True,
        'all_item_instance_fields_unchanged': True, 'native_item_fields_unchanged': True,
        'delivered_public_guid_slots': True, 'rendered_item_identities': True, 'inventory_restored': True,
        'saved_actions_preserved': True, 'ordinary_login': 1, 'ordinary_logout': 1,
        'exact_rest_accounting': True, 'all_six_offline': True, 'protected_actors_unchanged': True,
        'primary_stopped': True, 'qualification_added': False, 'preservation': preserved}
    return result, final, current


def local_lifecycle(refs):
    return lifecycle(local_store(), refs, live=True)


def tracking_state():
    return {'members': set(), 'packets': [], 'events': [], 'journal_counts':
        {member: {'rows': 0, 'serialized_bytes': 0} for member in TRACKING_MEMBERS}}


def collect(member, lines, data, tracking):
    require(member in TRACKING_MEMBERS and member not in tracking['members'], 'two distinct actual current journals required')
    closures = [v for v in data.values() if type(v) is dict and v.get('phase') == PHASE]
    require(len(closures) == 1, 'one closed swap pause must precede current journals')
    store = Sources(data, tracking['digests'])
    ready = store.get(closures[0]['sources']['preparation'])
    destination = tracking['packets' if member == TRACKING_MEMBERS[0] else 'events']
    tracking['members'].add(member)
    for row in lines:
        require(type(row) is dict, 'actual journal must contain objects')
        if row.get('session') == ready['native_session'] or row.get('account_id') == 2 or row.get('guid') == 2:
            require(finite(row.get('time')), 'attributable journal time must be finite and typed')
        if not finite(row.get('time')) or not ready['started_at'] <= row['time'] <= closures[0]['finished_at']:
            continue
        destination.append(row)
        count = tracking['journal_counts'][member]
        count['rows'] += 1
        count['serialized_bytes'] += shared.serialized_row_bytes(row)
        require(count['rows'] <= MAX_ROWS and count['serialized_bytes'] <= MAX_BYTES, 'bounded complete swap journal exceeded')


def actual_journals(store, closure, tracking, current):
    require(tracking.get('members') == set(TRACKING_MEMBERS), 'both actual archived journals required')
    ready, entry, operation, park, _, _ = current
    owner = ready['native_session']
    # The source-owned current copies preserve every gameplay body, including names
    # outside the generic publisher's safe-body allowlist.
    receipts = [v for v in store.data.values() if type(v) is dict and v.get('schema') == 'client442_bag_swap_journals_v1']
    require(len(receipts) == 1 and set(receipts[0]) == {'schema', 'closure_source', 'journal_sources'},
        'one distinct source-owned current journal receipt required')
    closure_members = [member for member, value in store.data.items() if value is closure]
    require(len(closure_members) == 1 and receipts[0]['closure_source'] ==
        {'path': str(lab.ROOT / closure_members[0]), 'sha256': store.digests[closure_members[0]]},
        'current journals must bind the exact immutable closed pause')
    raw_ref = receipts[0]['journal_sources']
    require(set(raw_ref) == {'packets', 'events'}, 'both source-owned complete current journals required')
    raw = {}
    for kind, ref in raw_ref.items():
        reference(ref)
        member = str(Path(ref['path']).relative_to(lab.ROOT))
        rows = tracking.get('raw_journals', {}).get(member)
        if rows is None and store.local:
            require(bound(ref['path']) == ref, 'current raw journal bytes differ')
            rows = [json.loads(line) for line in Path(ref['path']).read_text().splitlines()]
        require(type(rows) is list and store.digests.get(member) == ref['sha256'], 'exact raw current journal absent')
        raw[kind] = rows
    require(strict_equal(raw['events'], tracking['events']), 'current raw event journal differs from actual generic archived events')
    instances = [r for r in raw['events'] if r.get('event') == 'instance_authenticated' and r.get('account_id') == 2]
    require(len(instances) == 1 and finite(instances[0].get('time')) and
        entry['started_at'] <= instances[0]['time'] <= entry['finished_at'], 'one fresh actor2 physical instance required')
    sessions = {owner, instances[0]['session']}
    for row in raw['packets'] + raw['events']:
        require(type(row) is dict, 'actual whole gameplay journals require objects')
        if row.get('session') in sessions or row.get('account_id') == 2 or row.get('guid') == 2:
            require(finite(row.get('time')), 'malformed attributable gameplay time cannot be filtered out')
    wire = [r for r in raw['packets'] if r.get('session') == owner]
    from .interaction_bag_swap_continuation import entry_settlement
    compact = store.get(ready['runtime_authority_source'], False) if ready.get('runtime_authority_source') else {}
    boot = entry_settlement(entry, wire, raw['events'], required=compact.get('schema') ==
        'client442_bag_swap_fresh_runtime_authority_v1')
    if boot is not None:
        require(strict_equal(entry.get('raw_entry_packets'), contract.packet_rows(wire, owner, entry['started_at'], entry['finished_at'])) and
            strict_equal(entry.get('raw_entry_events'), [row for row in raw['events'] if
                finite(row.get('time')) and entry['started_at'] <= row['time'] <= entry['finished_at']]),
            'actual full journals must contain the exact retained complete fresh entry sources')
    contract.forbidden_packets(wire, owner, entry['started_at'], closure['finished_at'], login_sync=boot)
    contract.roundtrip_packets(wire, owner, entry['started_at'], closure['finished_at'], login_sync=boot)
    login = contract.login_packets(wire, owner, entry['started_at'], entry['finished_at'])
    require(entry['login_packets'] == [login[k] for k in ('modern', 'request', 'verify', 'delivered')] and
        len([r for r in wire if r.get('name') in ('CMSG_PLAYER_LOGIN', 'SMSG_LOGIN_VERIFY_WORLD')]) == 4,
        'actual current journal requires exactly one retained ordinary login')
    from .interaction_bag_swap_continuation import logout_packets
    logout = logout_packets(wire, owner, park['logout_started_at'], park['logout_finished_at'])
    require(logout == park['logout_packets'] and len([r for r in wire if r.get('name') in
        ('CMSG_LOGOUT_REQUEST', 'SMSG_LOGOUT_COMPLETE')]) == 4, 'actual current journal requires one ordinary logout')
    replay = contract.native_replay(wire, owner, entry['started_at'], logout[1]['time'],
        rest_threshold=entry['native_owner_proof']['rest_threshold'], login_sync=boot)
    require(park.get('raw_native_logout_history') == contract.packet_rows(wire, owner, entry['started_at'], logout[1]['time']) and
        park.get('native_logout_proof') == replay, 'retained pre-stop history differs from actual complete native logout journal')
    require(replay['native_inventory_states'] == [[contract.SOURCE['guid'], contract.DESTINATION['guid']],
        [contract.DESTINATION['guid'], contract.SOURCE['guid']], [contract.SOURCE['guid'], contract.DESTINATION['guid']]],
        'actual native inventory must exchange and exactly restore both GUIDs')
    events = [r for r in raw['events'] if r.get('session') in sessions]
    chain = stage_chain(store, operation)
    forward = next(stage for stage in chain if stage.get('phase') == 'bags_swap_forward')
    reverse = next(stage for stage in chain if stage.get('phase') == 'bags_swap_reverse')
    claimed = list(entry['login_packets']) + list(logout)
    for stage, kind, inverse, index in ((forward, 'forward', False, 1), (reverse, 'reverse', True, 2)):
        actual_window = contract.packet_rows(wire, owner, stage[kind + '_started_at'], stage[kind + '_finished_at'])
        require(actual_window == stage[kind + '_packets'], 'retained occupied-swap window differs from actual complete journal')
        pair = contract.swap_packets(actual_window, owner, stage[kind + '_started_at'], stage[kind + '_finished_at'], reverse=inverse)
        transition = replay['native_inventory_transitions'][index]
        projection = delivered_slots(actual_window, owner, transition['time'], stage[kind + '_finished_at'], swapped=not inverse)
        require(stage[kind] == pair and stage[kind + '_native_transition'] == transition and
            stage[kind + '_projection'] == projection and projection['delivery']['time'] > transition['time'],
            'actual request/effect/public GUID projection differs from retained attributable swap proof')
        claimed += [pair['modern'], pair['native'], transition['packet'], projection['delivery']]
    modern_logout = [row for row in wire if row.get('name') == 'CMSG_LOGOUT_REQUEST' and row.get('direction') == 'from_client']
    require(len(modern_logout) == 1 and modern_logout[0].get('body') == '00', 'exact modern ordinary logout required')
    claimed += modern_logout
    physical = instances[0]['session']
    for packet in claimed:
        event_session = owner if packet['direction'] in ('to_native', 'from_native') or packet['name'] in (
            'CMSG_PLAYER_LOGIN', 'SMSG_LOGOUT_COMPLETE') else physical
        matched = [row for row in events if row.get('session') == event_session and row.get('name') == packet['name'] and
            row.get('direction') == packet['direction'] and type(row.get('bytes')) is int and
            row['bytes'] == len(bytes.fromhex(packet['body'])) and finite(row.get('time')) and
            0 <= packet['time'] - row['time'] < .1]
        require(len(matched) == 1 and matched[0].get('event') == ('native_packet' if packet['direction'] in
            ('to_native', 'from_native') else 'modern_packet'), 'unique actual physical/native packet metadata attribution differs')
    require(len([row for row in events if row.get('name') == contract.ACTION and row.get('direction') in
        ('from_client', 'to_native')]) == 4, 'actual packet metadata contains another occupied inventory request')
    contract.forbidden_packets(events, owner, entry['started_at'], closure['finished_at'], login_sync=boot)
    for physical in sessions:
        contract.forbidden_packets(events, physical, entry['started_at'], closure['finished_at'], login_sync=boot)
    return {'actual_packet_journals_verified': True, 'native_item_fields_unchanged': replay['native_item_fields_preserved']}


def proof(data, digests, tracking):
    store = Sources(data, digests)
    store.raw_journals = tracking.get('raw_journals', {})
    closures = [(m, v) for m, v in data.items() if type(v) is dict and v.get('phase') == PHASE]
    require(len(closures) == 1, 'one distinct successful occupied-swap closed pause required')
    member, closure = closures[0]
    closure_ref = {'path': str(lab.ROOT / member), 'sha256': digests.get(member)}
    shared.accepted(closure, PHASE)
    result, final, current = lifecycle(store, closure['sources'])
    ready, _, _, park, _, _ = current
    exact_checks(closure, 'shutdown_checks', shared.SHUTDOWN_CHECKS)
    require(closure.get('proof') == result and closure.get('before') == closure.get('after') ==
        closure.get('all_offline_snapshot') == final and closure.get('actor') == ready['actor'] and
        closure.get('runtime') == ready['runtime'] and closure.get('primary_stop_source') == ready['predecessor']['primary_stop'] and
        closure.get('authority_source') == ready['authority_source'] and closure.get('input_sent') is False and
        closure.get('mutation_sent') is False and closure.get('qualification_added') is False and
        closure.get('action') == 'stop_parked_scout_after_bag_swap_roundtrip' and closure.get('stop_attempted') is True and
        closure.get('controller') == 'code' and closure.get('model') is None and closure.get('revision') is None and
        closure.get('code_commit') == ready['code_commit'] and closure.get('custom_script_permission') == 'blocked_by_user' and
        closure.get('softTargetInteract') == shared.SCRIPT_BOUNDARY and closure.get('committed_sources') == ready['committed_sources'] and
        current[-1]['finished_at'] <= closure['started_at'], 'whole closed occupied-swap resource pause differs')
    selected = shared.screen_review(store, closure, closure['sources']['park'], 'Harnesstwo')
    require((selected.get('selected_character'), selected.get('selected_level')) == ('Harnesstwo', 1), 'original final selection differs')
    frame(store, closure, closure['frame'], closure_ref)
    from .interaction_item_actionbar_parked_selection_capture import frame_identity
    frame_identity(closure['frame'], closure['runtime'], park['frame'])
    child = park['frame']['monitor']['input_isolation']['game_pid']
    require(type(closure.get('game_before', {}).get('pid')) is int and closure['game_before']['pid'] == child and
        type(closure['game_before'].get('start_ticks')) is str and
        re.fullmatch('[1-9][0-9]*', closure['game_before']['start_ticks']),
        'closed pause must stop the exact previously parked physical child')
    markers = [v for v in data.values() if type(v) is dict and v.get('schema') == 'client442_bag_swap_consumed_attempt_v1']
    require(len(markers) == 2 and {v.get('kind') for v in markers} == {'forward', 'reverse'}, 'one durable marker per drag required')
    from .checkpoint_bag_swap import validate_carry
    validate_carry(store, ready)
    actual = actual_journals(store, closure, tracking, current)
    return {**result, **actual, 'shutdown_checks': 8, 'both_owned_clients_stopped': True,
        'actual_journal_counts': tracking['journal_counts'], 'runtime_code_commit': ready['code_commit']}


def local(directory):
    store = local_store(directory)
    tracking = tracking_state()
    tracking.update(digests=store.digests, raw_journals={})
    from .observation.journal import entries
    for member, path in zip(TRACKING_MEMBERS, (lab.ROOT / 'evidence/world_packets.jsonl', lab.ROOT / 'logs/modern_world.jsonl')):
        collect(member, entries(path), store.data, tracking)
    for path in Path(directory).rglob('*.jsonl'):
        member = str(path.relative_to(lab.ROOT))
        store.digests[member] = bound(path)['sha256']
        tracking['raw_journals'][member] = [json.loads(line) for line in path.read_text().splitlines()]
    return proof(store.data, store.digests, tracking)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    a = parser.parse_args()
    print(json.dumps(local(a.directory)), flush=True)


if __name__ == '__main__':
    main()
