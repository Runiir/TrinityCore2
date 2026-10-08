"""Fresh authority from the published, excluded UI176 normal-logout boundary.

The complete predecessor is carried as raw flat members. Its original UI176
keyspace restores the existing indexed UI173 and UI174 crash maps unchanged.
Only a small derived closure and the stopped snapshot enter the live core.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import os

from . import bag_swap_indexed_sources as indexed
from . import bag_swap_indexed_archive as archive
from . import bag_swap_offline_sources as crash
from . import bag_swap_preservation as preservation
from .bag_swap_contract import require, finite, strict_equal, owned_snapshot

CACHE_SCHEMA = 'client442_bag_swap_closed_logout_authority_v1'
RUNTIME_SCHEMA = 'client442_bag_swap_closed_logout_runtime_v1'
EPOCH_SCHEMA = 'client442_bag_swap_closed_logout_code_epoch_v1'
CARRY_SCHEMA = 'client442_bag_swap_closed_logout_ancestry_v1'
CLOSURE_SCHEMA = 'client442_bag_swap_closed_logout_boundary_v1'
PHASE = 'bags_swap_excluded_normal_logout_closed'
LOGIN_SYNC_SCHEMA = crash.LOGIN_SYNC_SCHEMA
CORE_FIELDS = indexed.CORE_FIELDS
MAX_DESCRIPTOR_BYTES = MAX_RUNTIME_BYTES = 1024 * 1024
MAX_CARRY_BYTES = indexed.MAX_CARRY_BYTES
CARRY_NAME, RAW_DIRECTORY = 'predecessor_ui176.json', 'predecessor_ui176_raw'
NEW_FILES = tuple(sorted((
    'tools/client_compatibility/world/tests/test_bag_swap_login_sync_v2_loading.py',
    'tools/client_compatibility/bag_swap_closed_logout_sources.py',
    'tools/client_compatibility/bag_swap_closed_logout_contract.py',
    'tools/client_compatibility/world/tests/test_bag_swap_closed_logout_sources.py',
    'tools/client_compatibility/world/tests/test_bag_swap_closed_logout_contract.py',
    'tools/client_compatibility/world/tests/test_bag_swap_closed_logout_dispatch.py')))
CHANGED_OLD = frozenset((
    'tools/client_compatibility/interaction_bag_swap_continuation.py',
    'tools/client_compatibility/bag_swap_evidence.py',
    'tools/client_compatibility/checkpoint_bag_swap.py',
    'tools/client_compatibility/bag_swap_indexed_archive.py',
    'tools/client_compatibility/review_bag_swap_checkpoint.py',
    'tools/client_compatibility/bag_swap_login_sync_v2.py',
    'tools/client_compatibility/world/tests/test_bag_swap_login_sync_v2.py'))
BATCH = 'evidence/client_interactions_20261008_ui176/'
POINTER = 'artifacts/client_harness/442_interactions_20261008_176.tar.gz.dvc'
bound, reference = indexed.bound, indexed.reference
ROW_FIELDS = {'original_path', 'original_member', 'copy_member', 'sha256', 'bytes', 'kinds'}
REMOTE_CHECKS = frozenset(('actor_runtime_epoch', 'all_eight_shutdown_checks',
    'all_six_full_snapshot_unchanged_through_stop', 'closed_interval_covers_entry_through_stop',
    'entry_events_multiset_contained', 'entry_packets_multiset_contained', 'events_owned_path',
    'events_sha_row_count_interval', 'exact_float_preserved', 'exact_seven_packet_stock_timed_logout',
    'failed_entry_truthfully_retained', 'logout_events_multiset_contained', 'logout_packets_multiset_contained',
    'logout_stop_completed_whole_failure_excluded', 'no_gameplay_input_replayed', 'no_item_bag_operation_closed_window',
    'one_bit_modern_logout_request_physical_metadata', 'one_exact_closed_journal_logout_trio',
    'online_preservation_rederived', 'ordinary_logout_input', 'packets_owned_path', 'packets_sha_row_count_interval',
    'post_intentional_stop_xlib_diagnostic_retained', 'protected_five_full_saved_inventory_pose_health_power',
    'reference_chain', 'second_monitor_retained', 'supplied_entry_hash_and_size', 'supplied_logout_hash',
    'trio_order_and_receipt_exact', 'zero_added_qualification_whole_unit_excluded'))


def _encode(value): return indexed._encode(value)
def _root(root=None): return indexed._root(root)
def _json(path, limit=2 * 1024 * 1024, *, root=None, ref=None):
    return indexed._json_file(path, limit, root=root, expected_ref=ref)


def _write(path, value, root=None):
    from .bag_swap_fresh_sources import _write as write
    return write(Path(path), _encode(value), _root(root))


def admission_pins(value, *, root=None):
    root = _root(root)
    require(type(value) is dict and set(value) == {'closure', 'checkpoint', 'remote'},
        'actual excluded stop, checkpoint and remote pins are mandatory')
    for ref in value.values(): indexed._member(ref, root)
    require(Path(value['closure']['path']) == root / BATCH / 'failed_entry_stop01/episode.json' and
        Path(value['checkpoint']['path']) == root / BATCH / 'checkpoint_receipt.json' and
        not Path(value['remote']['path']).is_relative_to(root / BATCH),
        'only the actual published excluded UI176 boundary may supply this baseline')
    return deepcopy(value)


def read_admission_pins(path, *, root=None):
    return admission_pins(_json(path, MAX_DESCRIPTOR_BYTES, root=root)[0], root=root)


def _sources(stop, root):
    batch = root / BATCH
    return {'stop': bound(batch / 'failed_entry_stop01/episode.json'),
        'logout': stop['source'], 'ready': stop['preparation_source'], 'entry': stop['first_failure_source'],
        'precision': bound(batch / 'rest_before01/episode.json'),
        'journals': bound(batch / 'full_closed_journals01/journal_receipt.json')}


def _stop_summary(stop, refs):
    require(stop.get('completed') is True and stop.get('failure') is None and
        stop.get('phase') == 'bags_swap_failed_entry_closed_paused' and
        stop.get('recovery_only') is True and stop.get('failed_whole_excluded') is True and
        all(stop.get(k) is False for k in ('qualification_added', 'input_sent', 'mutation_sent', 'bag_input_sent')) and
        stop.get('cases') == stop.get('cleanup') == [] and stop.get('controller') == 'code_diagnostic_ordinary_inputs' and
        stop.get('model') is stop.get('revision') is None and
        stop.get('shutdown_checks') == dict.fromkeys(
            ('scout_launcher_absent', 'owned_game_absent', 'all_retained_saved_state', 'all_characters_offline',
             'primary_still_stopped', 'native_lifetime', 'bridge_lifetime', 'origin_registration'), True) and
        strict_equal(stop.get('before'), stop.get('after')) and strict_equal(stop.get('after'), stop.get('all_offline_snapshot')),
        'actual successful excluded owned stop and all eight checks required')
    owned_snapshot(stop['after'])
    before = preservation.exact_precision(stop.get('exact_precision_before'), stop['before'])
    after = preservation.exact_precision(stop.get('exact_precision_after'), stop['after'])
    require(strict_equal(before, after) and all(finite(stop.get(k)) for k in
        ('started_at', 'stop_started_at', 'stop_finished_at', 'finished_at')) and
        stop['started_at'] <= stop['stop_started_at'] < stop['stop_finished_at'] <= stop['finished_at'],
        'actual bounded stop must preserve its exact FLOAT row')
    return {'schema': CLOSURE_SCHEMA, 'phase': PHASE, 'completed': True, 'failure': None,
        'code_commit': stop['code_commit'], 'actor': deepcopy(stop['actor']), 'runtime': deepcopy(stop['runtime']),
        'started_at': stop['started_at'], 'finished_at': stop['finished_at'], 'sources': deepcopy(refs),
        'game_before': deepcopy(stop['game_before']),
        'shutdown_checks': deepcopy(stop['shutdown_checks']), 'exact_precision': after,
        'normal_logout_input_sent': True, 'entry_input_sent': True, 'stop_input_sent': False,
        'input_sent': True, 'mutation_sent': False, 'bag_input_sent': False, 'qualification_added': False,
        'excluded_failed_entry': True, 'operations_admitted': 0}


def _core(stop, refs, pins, pointer, parent_runtime):
    summary = _stop_summary(stop, refs)
    summary.update(prior_crash_authority_source=parent_runtime['authority_source'],
        prior_crash_boundary_source=parent_runtime['_descriptor']['boundary_source'])
    result = {'closure': summary, 'snapshot': deepcopy(stop['after']),
        'predecessor': {**pins, 'primary_stop': parent_runtime['core']['primary_stop_source']},
        'primary_stop_source': parent_runtime['core']['primary_stop_source'], 'dvc_pointer': pointer,
        'runtime': deepcopy(stop['runtime']), 'origin_actor': deepcopy(stop['actor'])}
    _runtime_core(result)
    return result


def _runtime_core(core):
    require(type(core) is dict and set(core) == set(CORE_FIELDS) and all(type(v) is dict for v in core.values()),
        'small complete excluded normal-logout core required')
    c = core['closure']
    require(c.get('schema') == CLOSURE_SCHEMA and c.get('phase') == PHASE and c.get('completed') is True and
        c.get('failure') is None and c.get('normal_logout_input_sent') is True and c.get('entry_input_sent') is True and
        c.get('input_sent') is True and c.get('excluded_failed_entry') is True and
        type(c.get('operations_admitted')) is int and c['operations_admitted'] == 0 and
        all(c.get(k) is False for k in ('qualification_added', 'mutation_sent', 'bag_input_sent', 'stop_input_sent')) and
        c.get('runtime') == core['runtime'] and c.get('actor') == core['origin_actor'] and
        core['primary_stop_source'] == core['predecessor'].get('primary_stop'),
        'normal-logout input and excluded zero-bag provenance must remain explicit')
    require(c.get('shutdown_checks') == dict.fromkeys(('scout_launcher_absent', 'owned_game_absent',
        'all_retained_saved_state', 'all_characters_offline', 'primary_still_stopped', 'native_lifetime',
        'bridge_lifetime', 'origin_registration'), True) and finite(c.get('started_at')) and finite(c.get('finished_at')) and
        0 < c['started_at'] < c['finished_at'] and type(c.get('code_commit')) is str and
        re.fullmatch('[0-9a-f]{40}', c['code_commit']) and type(c.get('sources')) is dict and
        set(c['sources']) == {'stop', 'logout', 'ready', 'entry', 'precision', 'journals'} and
        set(core['predecessor']) == set(indexed.ROLES) and core['origin_actor'].get('guid') == 2 and
        core['origin_actor'].get('account_id') == 2 and core['origin_actor'].get('actor') == 'scout',
        'exact excluded owned stop and original scout identities required')
    for ref in [*c['sources'].values(), *core['predecessor'].values(),
                c['prior_crash_authority_source'], c['prior_crash_boundary_source']]: reference(ref)
    for identity in [*core['runtime'].values(), c['game_before']]:
        require(type(identity) is dict and type(identity.get('pid')) is int and identity['pid'] > 0 and
            type(identity.get('start_ticks')) is str and re.fullmatch('[1-9][0-9]*', identity['start_ticks']),
            'retained native, bridge, launcher and game lifetimes must be exact')
    owned_snapshot(core['snapshot'])
    preservation.exact_precision(c['exact_precision'], core['snapshot'])
    return core


def _pointer(cp, remote, root, repo):
    path = Path(repo) / POINTER
    ref = bound(path); raw = path.read_bytes()
    require(0 < len(raw) <= 4096 and cp.get('cloud_verified') is True and
        cp.get('file') == POINTER.removesuffix('.dvc') and type(cp.get('bytes')) is int and cp['bytes'] > 0 and
        type(cp.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', cp['sha256']),
        'actual published UI176 checkpoint and bounded pointer required')
    text = raw.decode('utf-8'); oid = re.findall(r'^\s*-?\s*md5:\s*([0-9a-f]{32})\s*$', text, re.MULTILINE)
    require(len(oid) == 1 and re.findall(r'^\s*size:\s*([0-9]+)\s*$', text, re.MULTILINE) == [str(cp['bytes'])] and
        re.findall(r'^\s*path:\s*(\S+)\s*$', text, re.MULTILINE) == [Path(cp['file']).name] and
        re.search(r'^\s*hash:\s*md5\s*$', text, re.MULTILINE), 'actual UI176 pointer bytes differ')
    if remote is not None:
        require(remote.get('pointer') == POINTER and remote.get('pointer_sha256') == ref['sha256'] and
            remote.get('object_md5') == oid[0] and remote.get('bytes') == cp['bytes'] and
            remote.get('archive_sha256') == cp['sha256'] and remote.get('actual_remote_verified') is True and
            remote.get('complete_manifest_verified') is True,
            'mandatory actual complete remote UI176 verification differs')
        require(remote.get('schema') == 'client442_ui176_closed_excluded_failed_batch_remote_review_v1' and
            all(remote.get(k) is True for k in ('approval', 'scope_closed', 'source123_envelopes_match_retained_git_commit',
                'source_index_classes_and_raw_bindings_verified', 'whole_failed_unit_excluded')) and
            remote.get('outcome') == 'approved' and remote.get('result') == 'pass' and
            remote.get('qualification_added') is False and type(remote.get('operations_admitted')) is int and
            remote['operations_admitted'] == 0 and
            type(remote.get('lifecycle_verified_checks')) is dict and len(remote['lifecycle_verified_checks']) == 30 and
            all(v is True for v in remote['lifecycle_verified_checks'].values()),
            'actual sealed complete excluded normal-logout review required')
    pointer = {'source': ref, 'pointer': POINTER, 'oid': oid[0], 'bytes': cp['bytes']}
    if remote is not None: _portable_pointer(pointer, raw.hex(), cp, remote)
    return pointer, raw.hex()


def _local_preflight(pins, root, repo):
    stop = _json(pins['closure']['path'], root=root, ref=pins['closure'])[0]
    refs = _sources(stop, root)
    ready = _json(refs['ready']['path'], root=root, ref=refs['ready'])[0]
    compact = _json(ready['runtime_authority_source']['path'], MAX_RUNTIME_BYTES,
        root=root, ref=ready['runtime_authority_source'])[0]
    require(compact.get('schema') == crash.RUNTIME_SCHEMA and ready.get('all_offline_snapshot') == compact['core']['snapshot'] and
        ready.get('runtime') == stop.get('runtime') and compact.get('authority_source') == ready['authority_source'],
        'actual UI176 ready must retain its admitted UI174 crash authority')
    crash._runtime_core(compact['core'])
    compact['_descriptor'] = _json(ready['authority_source']['path'], MAX_DESCRIPTOR_BYTES,
        root=root, ref=ready['authority_source'])[0]
    crash._descriptor(compact['_descriptor'], root)
    cp = _json(pins['checkpoint']['path'], MAX_CARRY_BYTES, root=root, ref=pins['checkpoint'])[0]
    pointer, raw_hex = _pointer(cp, None, root, repo)
    return _core(stop, refs, pins, pointer, compact), raw_hex


def preflight_bundle(closure, remote, checkpoint, *, pins, root=None, repo=None):
    root = _root(root); pins = admission_pins(pins, root=root)
    require(all(str(path) == pins[k]['path'] for k, path in
        (('closure', closure), ('remote', remote), ('checkpoint', checkpoint))), 'actual role paths differ from supplied pins')
    return _local_preflight(pins, root, repo or indexed.REPO)[0]


def replay(store, refs):
    from . import bag_swap_closed_logout_contract as history
    ready, precision, failed, logout, stop, receipt = [store.get(refs[k], False) for k in
        ('ready', 'precision', 'entry', 'logout', 'stop', 'journals')]
    require(all(v.get('runtime') == ready.get('runtime') and v.get('actor') == ready.get('actor') and
        v.get('code_commit') == ready.get('code_commit') for v in (precision, failed, logout, stop)) and
        all(v.get('committed_sources') == ready.get('committed_sources') for v in (precision, failed)) and
        failed.get('completed') is False and failed.get('qualification_added') is False and failed.get('input_sent') is True and
        failed.get('preparation_source') == refs['ready'] and failed.get('precision_source') == refs['precision'] and
        logout.get('first_failure_source') == stop.get('first_failure_source') == refs['entry'] and
        logout.get('preparation_source') == stop.get('preparation_source') == refs['ready'] and stop.get('source') == refs['logout'],
        'normal closure must bind the exact immutable original source chain')
    baseline, final = ready['all_offline_snapshot'], stop['after']
    require(precision.get('before') == precision.get('after') == baseline and
        precision.get('source') == refs['ready'] and precision.get('query') == preservation.PRECISION_QUERY and
        precision.get('completed') is True and precision.get('failure') is None and
        all(precision.get(k) is False for k in ('input_sent', 'mutation_sent', 'qualification_added')) and
        failed.get('all_offline_snapshot') == baseline and failed.get('native_before_entry') == baseline['2']['native'] and
        logout.get('completed') is True and logout.get('failure') is None and
        logout.get('phase') == 'bags_swap_failed_entry_logged_out' and logout.get('input_sent') is True and
        logout.get('failed_whole_excluded') is True and logout.get('recovery_only') is True and
        all(logout.get(k) is False for k in ('mutation_sent', 'qualification_added', 'bag_input_sent')) and
        logout.get('after') == logout.get('all_offline_snapshot') == stop.get('before') == final,
        'truthful precision, failed entry and successful normal logout are required')
    old, now, inventory = preservation._preserved(baseline, final)
    require(receipt.get('schema') == 'client442_ui176_failed_entry_complete_journals_v1' and
        receipt.get('closed_source') == refs['stop'] and receipt.get('failed_source') == refs['entry'] and
        receipt.get('qualification_added') is False and receipt.get('interval') ==
            {'from': store.get(ready['resume_source'], False)['started_at'], 'until': stop['finished_at']},
        'whole retained resume-through-stop interval must be source-owned')
    journals = {key: crash._journal(store, ref) for key, ref in receipt['journal_sources'].items()}
    require(set(journals) == {'packets', 'events'} and all(len(journals[k]) == receipt['row_counts'][k] for k in journals),
        'complete actual journal row counts differ')
    proof = history.closed_history(journals['packets'], journals['events'], ready, failed, stop)
    before = preservation.exact_precision(precision['row'], baseline)
    after = preservation.exact_precision(stop['exact_precision_after'], final)
    require(preservation.exact_precision(stop['exact_precision_before'], final) == after and
        preservation.exact_precision(logout['exact_precision']['row'], final) == after,
        'normal logout and stopped exact FLOAT observations differ')
    boot = proof['login_sync']; request, verify = boot['login_packets'][1:3]
    matches = []
    for second in range(math.floor(request['time']), math.floor(verify['time']) + 1):
        elapsed = second - old['native']['logout_time']
        if elapsed < 0: continue
        gained, text = preservation.native_rest(before['exact_rest_bonus'], elapsed)
        if gained == after['exact_rest_bonus'] and text == now['native']['rest_bonus'] and int(gained) == proof['native_original']['rest_threshold']:
            matches.append({'native_login_second': second, 'offline_seconds': elapsed,
                'before_float32_bits': before['exact_rest_bonus_float32_bits'],
                'after_float32_bits': after['exact_rest_bonus_float32_bits'], 'exact_after': gained})
    require(len(matches) == 1 and now['native']['logout_time'] == math.floor(proof['normal_logout']['complete']['time']),
        'ordinary logout accounting needs one exact native login accrual and completion second')
    _stop_summary(stop, refs)
    return {'history': proof, 'native_rest': matches[0], 'all_six_preserved': True,
        'inventory_unchanged': inventory, 'qualification_added': False, 'operations_admitted': 0}


def validate_manifest(value, root=None):
    root = _root(root)
    require(type(value) is dict and set(value) == {'schema', 'predecessor', 'archive', 'dvc_pointer',
        'pointer_raw_hex', 'members', 'authorities'} and value.get('schema') == CARRY_SCHEMA and
        type(value.get('predecessor')) is dict and set(value['predecessor']) == set(indexed.ROLES),
        'exact flat excluded predecessor carry required')
    admission_pins({k: value['predecessor'][k] for k in ('closure', 'checkpoint', 'remote')}, root=root)
    from .review_bag_swap_failed_checkpoint import manifest
    require(type(value.get('archive')) is dict and set(value['archive']) ==
        {'file', 'bytes', 'sha256', 'manifest', 'tracking_manifest'}, 'actual payload and remote tracking manifests required')
    selected = manifest({'bytes': value['archive']['bytes'], 'sha256': value['archive']['sha256'],
        'file_manifest': value['archive']['manifest'] + value['archive']['tracking_manifest']}, BATCH)
    require(value['archive']['file'] == POINTER.removesuffix('.dvc') and len(selected) <= 100000 and
        type(value.get('members')) is list and len(value['members']) == len(selected) and
        type(value.get('authorities')) is list and len(value['authorities']) == 2,
        'complete published UI176 manifest and two mandatory external roles required')
    copies, originals, batches = {}, set(), set()
    for external, row in [(False, row) for row in value['members']] + [(True, row) for row in value['authorities']]:
        require(type(row) is dict and set(row) == ROW_FIELDS | ({'role'} if external else set()) and
            type(row['bytes']) is int and row['bytes'] >= 0 and type(row['kinds']) is list and
            row['kinds'] and row['kinds'] == sorted(set(row['kinds'])) and
            set(row['kinds']) <= {'json', 'journal', 'png', 'binary', *archive.index._OPAQUE_SOURCES},
            'typed bounded flat original member required')
        reference({'path': row['original_path'], 'sha256': row['sha256']})
        original = archive._name(row['original_member']); copy = archive._name(row['copy_member'])
        require(row['original_path'] == str(root / original) and original not in originals,
            'each original flat member must retain its exact private key once')
        originals.add(original)
        if external:
            require(row['role'] in ('checkpoint', 'remote') and
                {'path': row['original_path'], 'sha256': row['sha256']} == value['predecessor'][row['role']] and
                row['kinds'] == ['json'] and original not in selected, 'actual external publication role differs')
        else:
            require(original in selected and all(row[k] == selected[original][k] for k in ('bytes', 'sha256')),
                'every complete predecessor manifest byte identity must occur once')
        target = Path(copy)
        require(target.parent.name == RAW_DIRECTORY and target.name == row['sha256'] + '.blob' and
            target.parent.parent.as_posix().startswith('evidence/') and
            not Path(row['original_path']).is_relative_to(root / target.parent.parent),
            'flat copies must remain in a separately owned successor keyspace')
        batches.add(target.parent.parent.as_posix())
        kinds = frozenset(row['kinds'])
        require('json' not in kinds or row['bytes'] <= archive.MAX_JSON, 'ordinary JSON keeps its unchanged cap')
        require('journal' not in kinds or row['bytes'] <= archive.MAX_JOURNAL, 'journals keep their unchanged cap')
        opaque = archive.index._opaque_kind(row['sha256'], row['bytes'])
        require(not set(kinds) & set(archive.index._OPAQUE_SOURCES) or kinds == {opaque},
            'only the two exact legacy opaque identities may have an opaque view')
        require(copy not in copies or copies[copy][:2] == (row['sha256'], row['bytes']),
            'flat physical source size or digest conflicts')
        previous = copies[copy][2] if copy in copies else frozenset()
        copies[copy] = (row['sha256'], row['bytes'], previous | kinds)
    require(len(batches) == 1 and set(r['original_member'] for r in value['members']) == set(selected) and
        {r['role'] for r in value['authorities']} == {'checkpoint', 'remote'},
        'one complete flat physical batch and distinct external roles required')
    return copies


def _restore(store, carry):
    """Restore the whole current predecessor before its old indexed/crash replay."""
    root = store.root; copies = validate_manifest(carry, root)
    paths, digests, sizes = {}, {}, {}
    for row in [*carry['members'], *carry['authorities']]:
        member = row['copy_member']
        require(store.digests.get(member) == row['sha256'] and member in store.paths and
            Path(store.paths[member]).stat().st_size == row['bytes'], 'flat retained physical source differs')
        paths[row['original_member']] = store.paths[member]
        digests[row['original_member']] = row['sha256']; sizes[row['original_member']] = row['bytes']
    old_member = BATCH + archive.CARRY_NAME
    require(old_member in paths, 'unchanged UI173 flat carry must remain in actual UI176 archive')
    old = archive._read(paths[old_member], 'json', sizes[old_member], indexed.MAX_CARRY_BYTES, digests[old_member])
    classes = _classes(paths, digests, sizes, old, root)
    require(all(frozenset(row['kinds']) == classes[row['original_member']] for row in carry['members']),
        'flat types must preserve the unchanged original indexed/crash classes')
    data, journals = archive._materialize(paths, digests, old, root, sizes=sizes)
    from .bag_swap_evidence import Sources
    view = Sources(data, digests, local=False, paths=paths)
    view.root, view.raw_journals = root, journals
    cp = view.get(carry['predecessor']['checkpoint'], False)
    remote = view.get(carry['predecessor']['remote'], False)
    require(carry['archive'] == {'file': cp['file'], 'bytes': cp['bytes'], 'sha256': cp['sha256'],
        'manifest': cp['file_manifest'], 'tracking_manifest': remote.get('tracking_files')},
        'flat predecessor differs from its actual checkpoint and complete remote tracking manifest')
    archive._metadata(data, cp)
    return view


def _descriptor(value, root=None):
    root = _root(root)
    require(type(value) is dict and set(value) == {'schema', 'core_sha256', 'refs', 'carry_source',
        'dvc_pointer', 'pointer_raw_hex'} and value.get('schema') == CACHE_SCHEMA and
        type(value.get('core_sha256')) is str and re.fullmatch('[0-9a-f]{64}', value['core_sha256']) and
        len(_encode(value)) <= MAX_DESCRIPTOR_BYTES, 'one-MiB excluded normal-logout descriptor required')
    admission_pins({k: value['refs'][k] for k in ('closure', 'checkpoint', 'remote')}, root=root)
    for ref in [*value['refs'].values(), value['carry_source']]: indexed._member(ref, root)
    return value


def validate_cache(value, *, store, root=None):
    root = _root(root or store.root); _descriptor(value, root)
    carry = store.get(value['carry_source'], False)
    require(carry['predecessor'] == value['refs'] and carry['dvc_pointer'] == value['dvc_pointer'] and
        carry['pointer_raw_hex'] == value['pointer_raw_hex'], 'descriptor differs from flat source-owned carry')
    old_store = _restore(store, carry)
    stop = old_store.get(value['refs']['closure'], False)
    refs = _sources_from_values(stop, old_store, value['refs']['closure'])
    ready = old_store.get(refs['ready'], False)
    compact = deepcopy(old_store.get(ready['runtime_authority_source'], False))
    compact['_descriptor'] = old_store.get(ready['authority_source'], False)
    previous = crash.validate_cache(compact['_descriptor'], store=old_store, root=root)
    require(previous == compact['core'] and previous['snapshot'] == ready['all_offline_snapshot'],
        'full retained UI174 crash and unchanged UI173 ancestry differs')
    crash.validate_current_code_epoch(old_store, old_store.get(ready['resume_source'], False), ready, previous['closure'])
    proof = replay(old_store, refs)
    core = _core(stop, refs, {k: value['refs'][k] for k in ('closure', 'checkpoint', 'remote')}, value['dvc_pointer'], compact)
    cp = old_store.get(value['refs']['checkpoint'], False)
    remote = old_store.get(value['refs']['remote'], False)
    _portable_pointer(value['dvc_pointer'], value['pointer_raw_hex'], cp, remote)
    require(remote.get('checkpoint_source') == value['refs']['checkpoint'] and
        remote.get('code_commit') == stop['code_commit'] and remote.get('journal_receipt_source') == refs['journals'],
        'actual remote checkpoint, closure epoch or journal source differs')
    require(hashlib.sha256(_encode(core)).hexdigest() == value['core_sha256'],
        'excluded normal-logout core differs from the complete actual predecessor replay')
    return core


def _sources_from_values(stop, store, stop_ref):
    batch = Path(stop_ref['path']).parent.parent
    def ref(name):
        path = batch / name; member = str(path.relative_to(store.root))
        result = {'path': str(path), 'sha256': store.digests.get(member)}; reference(result); return result
    return {'stop': stop_ref, 'logout': stop['source'], 'ready': stop['preparation_source'],
        'entry': stop['first_failure_source'], 'precision': ref('rest_before01/episode.json'),
        'journals': ref('full_closed_journals01/journal_receipt.json')}


def _portable_pointer(pointer, raw_hex, cp, remote):
    require(type(pointer) is dict and set(pointer) == {'source', 'pointer', 'oid', 'bytes'} and
        pointer.get('pointer') == POINTER and pointer.get('oid') == remote.get('object_md5') and
        pointer.get('bytes') == cp.get('bytes') and type(raw_hex) is str and
        0 < len(raw_hex) <= 8192 and re.fullmatch('[0-9a-f]+', raw_hex) and len(raw_hex) % 2 == 0,
        'bounded complete actual normal-logout pointer required')
    reference(pointer['source']); raw = bytes.fromhex(raw_hex)
    require(pointer['source']['path'].endswith('/' + POINTER) and
        hashlib.sha256(raw).hexdigest() == pointer['source']['sha256'] == remote.get('pointer_sha256') and
        re.findall(rb'^\s*-?\s*md5:\s*([0-9a-f]{32})\s*$', raw, re.MULTILINE) == [pointer['oid'].encode()] and
        re.findall(rb'^\s*size:\s*([0-9]+)\s*$', raw, re.MULTILINE) == [str(cp['bytes']).encode()] and
        re.findall(rb'^\s*path:\s*(\S+)\s*$', raw, re.MULTILINE) == [Path(cp['file']).name.encode()] and
        re.search(rb'^\s*hash:\s*md5\s*$', raw, re.MULTILINE), 'actual normal-logout pointer bytes differ')
    require(cp.get('cloud_verified') is True and cp.get('file') == POINTER.removesuffix('.dvc') and
        remote.get('schema') == 'client442_ui176_closed_excluded_failed_batch_remote_review_v1' and
        remote.get('pointer') == POINTER and remote.get('archive_sha256') == cp.get('sha256') and
        remote.get('bytes') == cp.get('bytes') and remote.get('outcome') == 'approved' and remote.get('result') == 'pass' and
        all(remote.get(k) is True for k in ('approval', 'scope_closed', 'actual_remote_verified',
            'complete_manifest_verified', 'source123_envelopes_match_retained_git_commit',
            'source_index_classes_and_raw_bindings_verified', 'whole_failed_unit_excluded')) and
        remote.get('qualification_added') is False and type(remote.get('operations_admitted')) is int and
        remote['operations_admitted'] == 0 and type(remote.get('lifecycle_verified_checks')) is dict and
        set(remote['lifecycle_verified_checks']) == REMOTE_CHECKS and
        all(v is True for v in remote['lifecycle_verified_checks'].values()) and
        remote.get('manifest_files') == len(cp['file_manifest']) and remote.get('all_files') == len(cp['file_manifest']) + 16 and
        remote.get('complete_raw_source_members') == 123,
        'mandatory actual sealed zero-admission complete remote review differs')
    reference(remote.get('lifecycle_review_source'))


def _classes(paths, digests, sizes, old, root):
    classes = archive.validate_carry_manifest(old, root)
    classes.update(archive._crash_copies(paths, digests, dict(classes), root, sizes))
    return {member: frozenset(classes[member][2]) if member in classes else frozenset((
        archive.index._opaque_kind(digests[member], sizes[member]) or archive.index._ordinary_kind(member),))
        for member in paths}


def _full_checkpoint(cp, seal):
    require(type(seal.get('tracking_files')) is list and len(seal['tracking_files']) == 16 and
        all(type(row) is dict and type(row.get('path')) is str and row['path'].startswith('tracking/')
            for row in seal['tracking_files']) and
        not any(row['path'].startswith('tracking/') for row in cp['file_manifest']),
        'generic UI176 checkpoint payload and sixteen actual remote tracking identities remain separate')
    result = {**cp, 'file_manifest': cp['file_manifest'] + seal['tracking_files']}
    from .review_bag_swap_failed_checkpoint import manifest
    manifest(result, BATCH)
    return result


def _admit(data, digests, journals, paths, pins, pointer, raw_hex, root, cp):
    from .bag_swap_evidence import Sources
    store = Sources(data, digests, local=False, paths=paths)
    store.root, store.raw_journals = root, journals
    stop = store.get(pins['closure'], False); refs = _sources_from_values(stop, store, pins['closure'])
    ready = store.get(refs['ready'], False)
    compact = deepcopy(store.get(ready['runtime_authority_source'], False))
    compact['_descriptor'] = store.get(ready['authority_source'], False)
    previous = crash.validate_cache(compact['_descriptor'], store=store, root=root)
    require(previous == compact['core'] and previous['snapshot'] == ready['all_offline_snapshot'],
        'actual crash ancestry and ready baseline differ')
    crash.validate_current_code_epoch(store, store.get(ready['resume_source'], False), ready, previous['closure'])
    remote = store.get(pins['remote'], False)
    _portable_pointer(pointer, raw_hex, cp, remote)
    require(remote.get('checkpoint_source') == pins['checkpoint'] and remote.get('code_commit') == stop['code_commit'] and
        remote.get('journal_receipt_source') == refs['journals'], 'remote seal binds a different actual closure epoch')
    replay(store, refs)
    return _core(stop, refs, pins, pointer, compact)


def source_bundle(closure, remote, checkpoint, *, pins, root=None, repo=None):
    from urllib.request import urlopen
    from .review_hunter_learn_checkpoint import remote_options, remote_request
    root, repo = _root(root), Path(repo or indexed.REPO)
    pins = admission_pins(pins, root=root)
    require(all(str(path) == pins[k]['path'] for k, path in
        (('closure', closure), ('remote', remote), ('checkpoint', checkpoint))), 'actual normal-logout source paths differ')
    cp = _json(checkpoint, MAX_CARRY_BYTES, root=root, ref=pins['checkpoint'])[0]
    seal = _json(remote, MAX_DESCRIPTOR_BYTES, root=root, ref=pins['remote'])[0]
    pointer, raw_hex = _pointer(cp, seal, root, repo)
    with tempfile.TemporaryDirectory(prefix='client442-ui176-admission-') as temporary:
        with urlopen(remote_request(remote_options(repo), pointer['oid']), timeout=60) as stream:
            selected, paths, reader = archive._stream(stream, _full_checkpoint(cp, seal), BATCH, Path(temporary))
        require(reader.md5.hexdigest() == pointer['oid'], 'complete actual UI176 compressed MD5 differs')
        digests = {m: row['sha256'] for m, row in selected.items()}
        sizes = {m: row['bytes'] for m, row in selected.items()}
        old_member = BATCH + archive.CARRY_NAME
        old = archive._read(paths[old_member], 'json', sizes[old_member], MAX_CARRY_BYTES, digests[old_member])
        data, journals = archive._materialize(paths, digests, old, root, sizes=sizes)
        archive._metadata(data, cp)
        for key, value in (('checkpoint', cp), ('remote', seal)):
            member = indexed._member(pins[key], root)
            data[member], digests[member], paths[member] = value, pins[key]['sha256'], pins[key]['path']
        core = _admit(data, digests, journals, paths, pins, pointer, raw_hex, root, cp)
    require(all(bound(ref['path']) == ref for ref in pins.values()), 'actual publication changed during admission')
    return {**core, 'pointer_raw_hex': raw_hex}


def carry_authority(batch, *, admitted, root=None, repo=None):
    from urllib.request import urlopen
    from .review_hunter_learn_checkpoint import remote_options, remote_request
    root, batch = _root(root), Path(batch)
    require(batch.is_dir() and batch.is_relative_to(root / 'evidence') and str(batch.resolve()) == str(batch) and
        not any(p.is_symlink() for p in (batch, *batch.parents)) and
        not (batch / CARRY_NAME).exists() and not (batch / RAW_DIRECTORY).exists(),
        'exclusive canonical flat UI176 carry destination required')
    pins = {k: admitted['predecessor'][k] for k in ('closure', 'checkpoint', 'remote')}
    cp = _json(pins['checkpoint']['path'], MAX_CARRY_BYTES, root=root, ref=pins['checkpoint'])[0]
    seal = _json(pins['remote']['path'], MAX_DESCRIPTOR_BYTES, root=root, ref=pins['remote'])[0]
    _portable_pointer(admitted['dvc_pointer'], admitted['pointer_raw_hex'], cp, seal)
    destination = batch / RAW_DIRECTORY
    with tempfile.TemporaryDirectory(prefix='.ui176-carry-', dir=batch) as staged:
        raw_directory = Path(staged) / RAW_DIRECTORY; raw_directory.mkdir(mode=0o700)
        with urlopen(remote_request(remote_options(repo or indexed.REPO), admitted['dvc_pointer']['oid']), timeout=60) as stream:
            selected, paths, reader = archive._stream(stream, _full_checkpoint(cp, seal), BATCH, raw_directory)
        require(reader.md5.hexdigest() == admitted['dvc_pointer']['oid'], 'complete UI176 carry compressed MD5 differs')
        sizes = {m: row['bytes'] for m, row in selected.items()}; digests = {m: row['sha256'] for m, row in selected.items()}
        old_member = BATCH + archive.CARRY_NAME
        old = archive._read(paths[old_member], 'json', sizes[old_member], MAX_CARRY_BYTES, digests[old_member])
        classes = _classes(paths, digests, sizes, old, root)
        rows = [{'original_path': str(root / m), 'original_member': m, 'sha256': row['sha256'], 'bytes': row['bytes'],
            'copy_member': str((destination / Path(paths[m]).name).relative_to(root)), 'kinds': sorted(classes[m])}
            for m, row in selected.items()]
        authorities = []
        from .interaction_bag_swap_offline_boundary import copy_file
        for role in ('checkpoint', 'remote'):
            ref = pins[role]; target = raw_directory / (ref['sha256'] + '.blob')
            if not target.exists(): copy_file(ref['path'], target, MAX_CARRY_BYTES)
            require(bound(target)['sha256'] == ref['sha256'], 'actual external authority changed during carry')
            authorities.append({'role': role, 'original_path': ref['path'], 'original_member': indexed._member(ref, root),
                'sha256': ref['sha256'], 'bytes': target.stat().st_size,
                'copy_member': str((destination / target.name).relative_to(root)), 'kinds': ['json']})
        carry = {'schema': CARRY_SCHEMA, 'predecessor': deepcopy(admitted['predecessor']),
            'archive': {'file': cp['file'], 'sha256': cp['sha256'], 'bytes': cp['bytes'],
                'manifest': cp['file_manifest'], 'tracking_manifest': seal['tracking_files']},
            'dvc_pointer': deepcopy(admitted['dvc_pointer']), 'pointer_raw_hex': admitted['pointer_raw_hex'],
            'members': rows, 'authorities': authorities}
        validate_manifest(carry, root)
        staged_ref = _write(Path(staged) / CARRY_NAME, carry, root)
        destination.mkdir(mode=0o700)
        for path in raw_directory.iterdir(): os.link(path, destination / path.name)
        os.link(staged_ref['path'], batch / CARRY_NAME)
    return bound(batch / CARRY_NAME)


def materialize(paths, digests, sizes, carry, root, *, role_refs=None, local=False):
    """Keep current documents and raw predecessor mappings; replay it only once."""
    from .bag_swap_evidence import Sources
    copies = validate_manifest(carry, root)
    require(all(m in paths and digests.get(m) == sha and sizes[m] == size for m, (sha, size, _) in copies.items()),
        'complete flat physical copies differ')
    retained = {m for m in paths if Path(m).parent.name == RAW_DIRECTORY}
    require(retained == set(copies), 'flat raw directory must contain exactly its declared physical source set')
    limits = archive._role_limits(paths, digests, copies, root, role_refs, sizes, copies)
    original_paths, original_digests, original_sizes = {}, {}, {}
    for row in [*carry['members'], *carry['authorities']]:
        original_paths[row['original_member']] = paths[row['copy_member']]
        original_digests[row['original_member']] = row['sha256']
        original_sizes[row['original_member']] = row['bytes']
    old_member = BATCH + archive.CARRY_NAME
    require(old_member in original_paths, 'unchanged UI173 map must remain in the original UI176 keyspace')
    old = archive._read(original_paths[old_member], 'json', original_sizes[old_member],
        MAX_CARRY_BYTES, original_digests[old_member])
    classes = _classes(original_paths, original_digests, original_sizes, old, root)
    require(all(frozenset(row['kinds']) == classes[row['original_member']] for row in carry['members']),
        'flat types must preserve the unchanged original indexed/crash classes')
    data, journals = {}, {}
    for member, path in paths.items():
        if member in copies: continue
        kind = archive.index._opaque_kind(digests[member], sizes[member]) or archive.index._ordinary_kind(member)
        value = archive._read(path, kind, sizes[member], limits.get(member), digests[member])
        if kind == 'json': data[member] = value
        elif kind == 'journal': journals[member] = value
    carry_member = str(Path(next(iter(copies))).parent.parent / CARRY_NAME)
    require(strict_equal(data.get(carry_member), carry),
        'flat aliases must use the exact current physically retained carry map')
    active_carry = deepcopy(carry)
    class FlatSources(Sources):
        def _refresh_maps(self):
            # Diagnostic JSON and lazily decoded historical maps are retained
            # data. Only this physically validated outer map owns live aliases;
            # historical maps are interpreted later in their restored keyspace.
            self.maps = [active_carry]
            self.logical_kinds, self.copy_kinds = {}, {}
            for row in [*active_carry['members'], *active_carry['authorities']]:
                identity = (row['original_path'], row['sha256'])
                kinds = frozenset(row['kinds'])
                self.logical_kinds[identity] = self.logical_kinds.get(identity, frozenset()) | kinds
                copy = (str(root / row['copy_member']), row['sha256'])
                self.copy_kinds[copy] = self.copy_kinds.get(copy, frozenset()) | kinds

        def get(self, ref, successful=True):
            self._refresh_maps(); self._json_view(ref)
            member = self.member(ref)
            if member not in self.data:
                require(member in copies and 'json' in copies[member][2], 'typed raw ordinary JSON view required')
                self.data[member] = archive._read(self.paths[member], 'json', sizes[member],
                    limits.get(member), self.digests[member])
            return super().get(ref, successful)

        def journal(self, ref):
            member = self.member(ref)
            identity = (ref['path'], ref['sha256'])
            kinds = self.logical_kinds.get(identity, self.copy_kinds.get(identity))
            require(kinds is not None and 'journal' in kinds, 'typed raw journal view required')
            if member not in self.raw_journals:
                self.raw_journals[member] = archive._read(self.paths[member], 'journal', sizes[member],
                    expected_sha=self.digests[member])
            return self.raw_journals[member]
    store = FlatSources(data, digests, local=local, paths=paths)
    store.root, store.raw_journals = root, journals
    return store


def local_store(batch, root=None):
    root, batch = _root(root), Path(batch)
    require(batch.is_dir() and batch.is_relative_to(root / 'evidence') and str(batch.resolve()) == str(batch) and
        not any(p.is_symlink() for p in (batch, *batch.parents)), 'canonical ordinary successor batch required')
    carry, carry_ref = _json(batch / CARRY_NAME, MAX_CARRY_BYTES, root=root)
    paths, digests, sizes = {}, {}, {}
    for path in sorted(batch.rglob('*')):
        require(not path.is_symlink(), 'source links forbidden')
        if not path.is_file(): continue
        archive.index._file(path); member = str(path.relative_to(root)); ref = bound(path)
        paths[member], digests[member], sizes[member] = str(path), ref['sha256'], path.stat().st_size
    require(digests.get(str((batch / CARRY_NAME).relative_to(root))) == carry_ref['sha256'], 'flat carry changed while read')
    return materialize(paths, digests, sizes, carry, root, local=True)


def write_cache(directory, old, carry_source, *, root=None):
    descriptor = {'schema': CACHE_SCHEMA, 'core_sha256': hashlib.sha256(_encode({k: old[k] for k in CORE_FIELDS})).hexdigest(),
        'refs': old['predecessor'], 'carry_source': carry_source, 'dvc_pointer': old['dvc_pointer'],
        'pointer_raw_hex': old['pointer_raw_hex']}
    _descriptor(descriptor, root)
    actual = validate_cache(descriptor, store=local_store(Path(directory).parent, root), root=root)
    require(actual == {k: old[k] for k in CORE_FIELDS}, 'new flat carry differs from actual admitted stopped core')
    return _write(Path(directory) / 'authority.json', descriptor, root)


def compact_authority(old, full_ref, *, root=None):
    reference(full_ref); core = {k: deepcopy(old[k]) for k in CORE_FIELDS}; _runtime_core(core)
    result = {'schema': RUNTIME_SCHEMA, 'authority_source': full_ref, 'core': core}
    require(len(_encode(result)) <= MAX_RUNTIME_BYTES, 'excluded normal-logout runtime exceeds one MiB')
    return result


def write_runtime(directory, old, full_ref, *, root=None):
    return _write(Path(directory) / 'runtime_authority.json', compact_authority(old, full_ref, root=root), root)


def cached_runtime(path, full_ref, *, root=None, compact_ref=None):
    descriptor = _json(full_ref['path'], MAX_DESCRIPTOR_BYTES, root=root, ref=full_ref)[0]; _descriptor(descriptor, root)
    value = _json(path, MAX_RUNTIME_BYTES, root=root, ref=compact_ref)[0]
    require(value.get('schema') == RUNTIME_SCHEMA and value.get('authority_source') == full_ref and
        hashlib.sha256(_encode(value['core'])).hexdigest() == descriptor['core_sha256'], 'small normal-logout runtime differs')
    return _runtime_core(value['core'])


def cached_bundle(path, *, root=None):
    value = _json(path, MAX_DESCRIPTOR_BYTES, root=root)[0]
    return validate_cache(value, store=local_store(Path(path).parent.parent, root), root=root)


def validate_carry(store, ready):
    return validate_cache(store.get(ready['authority_source'], False), store=store)


def _epoch_paths(store, closure):
    """Derive the complete current member set from the immutable UI176 epoch."""
    require(type(closure) is dict and closure.get('schema') == CLOSURE_SCHEMA and
        closure.get('phase') == PHASE and closure.get('excluded_failed_entry') is True,
        'source-owned actual excluded normal-logout predecessor required')
    old_ready_ref = closure['sources']['ready']; reference(old_ready_ref)
    root = _root(store.root)
    require(old_ready_ref['path'] == str(root / BATCH / 'scout_ready01/episode.json'),
        'current epoch must derive from the actual UI176 ready source')
    old_ready = store.get(old_ready_ref, False)
    old_resume = store.get(old_ready['resume_source'], False)
    old_ref = old_ready['current_code_epoch_source']; reference(old_ref)
    old = store.get(old_ref, False)
    require(type(old) is dict and set(old) == {'schema', 'code_commit', 'committed_sources', 'carried_sources'} and
        old.get('schema') == crash.EPOCH_SCHEMA and old.get('code_commit') == closure.get('code_commit') ==
        old_ready.get('code_commit') == old_resume.get('code_commit') and
        old_resume.get('current_code_epoch_source') == old_ref and
        old_ready.get('committed_sources') == old_resume.get('committed_sources') == old.get('committed_sources'),
        'actual UI176 ready/resume raw source epoch differs from excluded publication')
    indexed.stopped._commit(old['code_commit'])
    require(type(old['committed_sources']) is list and old['committed_sources'], 'complete prior source vector required')
    repo = indexed.stopped._repo(old['committed_sources'])
    prior_paths = indexed.stopped._vector(old['committed_sources'], repo)
    require(not set(prior_paths) & set(NEW_FILES), 'successor-only members cannot relabel the old UI176 source epoch')
    indexed.stopped._envelopes(store, old, old['committed_sources'], old['code_commit'])
    return old, repo, sorted(set(prior_paths) | set(NEW_FILES))


def _source_transition(epoch, previous, repo, wanted):
    require(type(epoch) is dict and set(epoch) == {'schema', 'code_commit', 'committed_sources',
        'carried_sources', 'excluded_predecessor_code_commit'} and epoch.get('schema') == EPOCH_SCHEMA,
        'exact typed successor source epoch required')
    indexed.stopped._commit(epoch['code_commit'])
    require(epoch['code_commit'] != previous['code_commit'] and
        epoch['excluded_predecessor_code_commit'] == previous['code_commit'],
        'current code must be fresh against the actual excluded UI176 publication')
    rows = epoch['committed_sources']
    require(type(rows) is list and len(rows) == len(wanted) and wanted,
        'complete canonical current source membership required')
    for row in rows:
        reference(row)
        require(Path(row['path']).is_relative_to(repo), 'current raw source must remain in its original repository')
    members = [str(Path(row['path']).relative_to(repo)) for row in rows]
    require(members == wanted, 'current source vector must equal the exact prior-plus-successor canonical paths')
    hashes = {row['path']: row['sha256'] for row in previous['committed_sources']}
    require(all(row['sha256'] == hashes[row['path']] for row in rows if row['path'] in hashes and
        str(Path(row['path']).relative_to(repo)) not in CHANGED_OLD),
        'unrelated prior source must retain its actual UI176 bytes')


def current_code_epoch(directory, old):
    from .bag_swap_projection import source_identities
    from .bag_swap_failed_sources import CODE_SCHEMA, MAX_SOURCE_BYTES, MAX_TOTAL_BYTES
    directory = Path(directory)
    require(directory.is_dir() and directory.is_relative_to(_root() / 'evidence'),
        'new private normal-logout successor code epoch required')
    previous, repo, wanted = _epoch_paths(local_store(directory.parent), old['closure'])
    require(repo == indexed.REPO, 'current source writer must use the original source repository')
    refs = source_identities(repo)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=indexed.REPO, text=True).strip()
    epoch = {'schema': EPOCH_SCHEMA, 'code_commit': commit, 'committed_sources': refs,
        'carried_sources': [], 'excluded_predecessor_code_commit': previous['code_commit']}
    _source_transition(epoch, previous, repo, wanted)
    target = Path(directory) / 'code_sources'
    require(not target.exists(), 'current normal-logout successor epoch never overwrites source envelopes')
    target.mkdir(mode=0o700); copies, total = [], 0
    for i, ref in enumerate(refs):
        member = str(Path(ref['path']).relative_to(indexed.REPO))
        raw = subprocess.check_output(['git', 'show', commit + ':' + member], cwd=indexed.REPO)
        total += len(raw)
        require(len(raw) <= MAX_SOURCE_BYTES and total <= MAX_TOTAL_BYTES and
            hashlib.sha256(raw).hexdigest() == ref['sha256'], 'current successor bytes differ from actual committed code')
        copies.append(_write(target / (f'{i:03d}_' + ref['sha256'] + '.json'), {'schema': CODE_SCHEMA,
            'code_commit': commit, 'original_path': ref['path'], 'sha256': ref['sha256'], 'bytes': len(raw), 'raw_hex': raw.hex()}))
    epoch['carried_sources'] = copies
    indexed.stopped._envelopes(local_store(directory.parent), epoch, refs, commit)
    return _write(Path(directory) / 'current_code_epoch.json', epoch)


def validate_current_code_epoch(store, resume, ready, closure):
    ref = ready.get('current_code_epoch_source'); reference(ref); epoch = store.get(ref, False)
    require(resume.get('current_code_epoch_source') == ref and type(epoch) is dict and
        epoch.get('code_commit') == ready.get('code_commit') == resume.get('code_commit') and
        epoch.get('committed_sources') == ready.get('committed_sources') == resume.get('committed_sources'),
        'fresh current source epoch must retain the immutable excluded historical epoch separately')
    previous, repo, wanted = _epoch_paths(store, closure)
    _source_transition(epoch, previous, repo, wanted)
    indexed.stopped._envelopes(store, epoch, epoch['committed_sources'], epoch['code_commit'])
    return {'code_commit': epoch['code_commit'], 'complete_raw_source_members': len(wanted),
        'predecessor_publication_code_commit': previous['code_commit']}
