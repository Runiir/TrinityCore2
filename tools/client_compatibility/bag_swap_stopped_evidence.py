"""Portable proof of UI173's failed entry and observed system-stop boundary.

The original trial stays failed. This new receipt proves only the subsequently
observed offline state, its complete journals and the immutable source epochs.
"""
import ast
import hashlib
import json
from pathlib import Path
import re

from . import lab_runtime as lab
from .bag_swap_sources import reference
from .bag_swap_contract import owned_snapshot
from .bag_swap_preservation import exact_precision, PRECISION_QUERY
from .item_actionbar_contract import require, finite, strict_equal
from .bag_swap_failed_sources import CODE_SCHEMA, CODE_FIELDS, MAX_TOTAL_BYTES, _raw, _commit

SCHEMA = 'client442_bag_swap_stopped_entry_closure_v1'
PHASE = 'bags_swap_stopped_entry_closed_excluded'
PROOF_SCHEMA = 'client442_bag_swap_stopped_checkpoint_proof_v1'
EPOCH_SCHEMA = 'client442_bag_swap_stopped_code_epoch_v1'
TRACKING_MEMBERS = ('tracking/packets.jsonl', 'tracking/events.jsonl')
SCRIPT = {'original': '0', 'current_stock_disabled': '1', 'original_restored': False}
OLD_COMMIT = '1a702eec0ed6bd55f6202ad8a574a1e365b7948c'
BATCH = 'evidence/client_interactions_20261008_ui173/'
SOURCES = {role: {'path': str(lab.ROOT / (BATCH + name)), 'sha256': sha}
    for role, name, sha in (
        ('preparation', 'scout_ready01/episode.json', '966306ac6349e6634975f6658f1c2d95632fc4d06b89b7fe7324096d579df598'),
        ('precision', 'rest_before01/episode.json', '5bee7458b77e541800558151800e3302e906d48f31966e6fc0fcc150c51c79f1'),
        ('failed_entry', 'entry01/episode.json', '63e2bd045a162b7cb125f76dd3532ca0f43a3e77137ca9e02a7e8cfbf009329a'),
        ('observation', 'failed_stop_observation01.json', '81083e598e9b542f715e1ae69e32242d2008ed296f03fe1c9f9c74b2bc45a68d'))}
STOP_CHECKS = frozenset(('scout_launcher_absent', 'observed_owned_game_pid_absent',
    'all_characters_offline', 'primary_still_stopped', 'native_lifetime', 'bridge_lifetime',
    'origin_registration', 'protected_five_snapshots_unchanged', 'all_saved_inventory_pets_unchanged',
    'actor2_native_changes_confined_to_accounting_rest'))
STOP_LOG_SHA = '821e6ce553a2ec6c1026a9e87d6b64d767a86f16f84e4985b7be43920597860c'
NEW_FILES = tuple(sorted((
    'tools/client_compatibility/bag_swap_source_index.py',
    'tools/client_compatibility/world/tests/test_bag_swap_source_index.py',
    'tools/client_compatibility/bag_swap_stopped_contract.py',
    'tools/client_compatibility/world/tests/test_bag_swap_stopped_contract.py',
    'tools/client_compatibility/bag_swap_stopped_evidence.py',
    'tools/client_compatibility/world/tests/test_bag_swap_stopped_evidence.py',
    'tools/client_compatibility/checkpoint_bag_swap_stopped.py',
    'tools/client_compatibility/review_bag_swap_stopped_checkpoint.py',
    'tools/client_compatibility/world/tests/test_bag_swap_stopped_publication.py')))
CHANGED_OLD = frozenset(('tools/client_compatibility/bag_swap_login_sync.py',
    'tools/client_compatibility/world/tests/test_bag_swap_login_sync.py',
    'tools/client_compatibility/bag_swap_projection.py'))


def historical(store, refs):
    require(type(refs) is dict and strict_equal(refs, SOURCES),
        'the actual immutable UI173 ready/precision/failure/stop observation are required')
    values = {role: store.get(ref, False) for role, ref in refs.items()}
    ready, precision, failed, observation = (values[k] for k in
        ('preparation', 'precision', 'failed_entry', 'observation'))
    require(ready.get('code_commit') == precision.get('code_commit') == failed.get('code_commit') ==
        observation.get('code_commit') == OLD_COMMIT and ready.get('completed') is True and
        ready.get('phase') == 'bags_swap_scout_ready' and precision.get('completed') is True and
        precision.get('phase') == 'bags_swap_rest_precision_complete' and
        failed.get('completed') is False and type(failed.get('failure')) is str and failed['failure'] and
        failed.get('phase') == 'bags_swap_entry_started' and
        failed.get('preparation_source') == refs['preparation'] and
        failed.get('precision_source') == refs['precision'] and precision.get('source') == refs['preparation'] and
        strict_equal(failed.get('all_offline_snapshot'), ready.get('all_offline_snapshot')) and
        strict_equal(failed.get('actor'), ready.get('actor')) and
        strict_equal(failed.get('runtime'), ready.get('runtime')) and
        failed.get('native_session') == ready.get('native_session') and failed.get('input_sent') is True and
        failed.get('mutation_sent') is False and failed.get('qualification_added') is False,
        'original failed trial must keep its truthful old code and failure labels')
    require(observation.get('schema') == 'client442_failed_entry_stop_observation_v1' and
        observation.get('phase') == 'bags_swap_failed_entry_stopped_observed' and
        observation.get('ready_source') == observation.get('game_identity_source') == refs['preparation'] and
        observation.get('failed_entry_source') == refs['failed_entry'] and
        strict_equal(observation.get('ready_baseline'), ready.get('all_offline_snapshot')) and
        strict_equal(observation.get('runtime'), ready.get('runtime')) and
        strict_equal(observation.get('checks'), dict.fromkeys(STOP_CHECKS, True)) and
        observation.get('normal_logout_input_sent') is False and observation.get('bag_input_sent') is False and
        observation.get('entry_input_sent') is True and observation.get('qualification_added') is False and
        observation.get('client_input_sent_by_this_observation') is False and
        observation.get('mutation_sent_by_this_observation') is False and
        observation.get('excluded_failed_entry') is True and type(observation.get('operations_admitted')) is int and
        observation['operations_admitted'] == 0 and finite(observation.get('observed_at')),
        'actual observed system stop, input exclusion and ten typed checks differ')
    original = observation.get('exact_after_precision')
    require(type(original) is dict and original.get('query') == PRECISION_QUERY and
        original.get('input_sent') is False and original.get('mutation_sent') is False and
        strict_equal(original.get('before'), observation.get('after')) and
        strict_equal(original.get('after'), observation.get('after')),
        'observed exact FLOAT query must retain its actual read-only snapshots')
    exact_precision(original['row'], observation['after'])
    owned_snapshot(ready['all_offline_snapshot'])
    owned_snapshot(observation['after'])
    return values


def _repo(refs):
    config = 'experiments/configs/client_harness/442_bag_swap_roundtrip_v1.json'
    matches = [Path(row['path']) for row in refs if row['path'].endswith('/' + config)]
    require(len(matches) == 1, 'one actual occupied-swap source repository required')
    return matches[0].parents[3]


def _vector(rows, repo):
    require(type(rows) is list and len(rows) <= 128, 'bounded complete code vector required')
    paths = []
    for row in rows:
        reference(row)
        require(Path(row['path']).is_relative_to(repo), 'raw code source must stay in its original repository')
        paths.append(str(Path(row['path']).relative_to(repo)))
    require(paths == sorted(set(paths)), 'canonical unique raw source vector required')
    return paths


def _envelopes(store, epoch, rows, commit):
    copies = epoch.get('carried_sources')
    require(type(copies) is list and len(copies) == len(rows) and
        len({row.get('path') for row in copies if type(row) is dict}) == len(copies),
        'one raw source envelope per original vector member required')
    total, raw_members = 0, {}
    for row, ref in zip(rows, copies):
        source = store.get(ref, False)
        require(type(source) is dict and set(source) == CODE_FIELDS and source.get('schema') == CODE_SCHEMA and
            source.get('code_commit') == commit and source.get('original_path') == row['path'] and
            source.get('sha256') == row['sha256'], 'raw source envelope differs from its exact code epoch')
        raw = _raw(source['raw_hex'], source['sha256'], source['bytes'])
        total += len(raw)
        require(total <= MAX_TOTAL_BYTES, 'complete raw source package exceeds its bound')
        raw_members[row['path']] = raw
    return raw_members


def code_epochs(store, closure, ready):
    from .bag_swap_projection import STOPPED_SOURCE_FILES
    old_ref = ready['current_code_epoch_source']
    require(closure.get('prior_code_epoch_source') == old_ref, 'original 89-source epoch reference changed')
    old = store.get(old_ref, False)
    require(old.get('schema') == 'client442_bag_swap_current_code_epoch_v1' and
        old.get('code_commit') == OLD_COMMIT and old.get('committed_sources') == ready.get('committed_sources') and
        len(old['committed_sources']) == 89, 'actual immutable original 89-source package required')
    repo = _repo(old['committed_sources'])
    old_paths = _vector(old['committed_sources'], repo)
    _envelopes(store, old, old['committed_sources'], OLD_COMMIT)
    epoch = closure.get('code_source_epoch')
    require(type(epoch) is dict and set(epoch) == {'schema', 'code_commit', 'committed_sources', 'carried_sources'} and
        epoch.get('schema') == EPOCH_SCHEMA and epoch.get('code_commit') == closure.get('code_commit') and
        epoch.get('committed_sources') == closure.get('committed_sources'), 'new stopped-entry raw code epoch differs')
    commit = _commit(epoch['code_commit'])
    require(commit != OLD_COMMIT, 'causal repair and stopped-entry proof require their own actual committed epoch')
    paths = _vector(epoch['committed_sources'], repo)
    require(paths == sorted(set(old_paths) | set(NEW_FILES) | set(STOPPED_SOURCE_FILES)),
        'complete stopped-entry helper/test/queue/expiry package required')
    old_hashes = {r['path']: r['sha256'] for r in old['committed_sources']}
    require(all(row['sha256'] == old_hashes[row['path']] for row in epoch['committed_sources']
        if row['path'] in old_hashes and str(Path(row['path']).relative_to(repo)) not in CHANGED_OLD),
        'unrelated original source bytes cannot change in the bounded stopped-entry epoch')
    raw_members = _envelopes(store, epoch, epoch['committed_sources'], commit)
    return {'code_commit': commit, 'original_code_commit': OLD_COMMIT,
        'original_raw_source_members': 89, 'current_raw_source_members': len(paths)}, raw_members


def _boundary(closure, old):
    """Check the completed observations without replaying the large sources."""
    require(type(closure) is dict and closure.get('schema') == SCHEMA and closure.get('phase') == PHASE and
        closure.get('completed') is True and closure.get('failure') is None and
        closure.get('controller') == 'code' and closure.get('model') is None and closure.get('revision') is None and
        closure.get('input_sent') is False and closure.get('mutation_sent') is False and
        closure.get('qualification_added') is False and closure.get('excluded_failed_entry') is True and
        type(closure.get('operations_admitted')) is int and closure['operations_admitted'] == 0 and
        closure.get('custom_script_permission') == 'blocked_by_user' and
        strict_equal(closure.get('softTargetInteract'), SCRIPT) and closure.get('cases') == closure.get('cleanup') == [],
        'a new completed, read-only, excluded stopped-entry boundary is required')
    require(all(finite(closure.get(k)) for k in ('started_at', 'audit_until', 'finished_at')) and
        0 < closure['started_at'] <= closure['audit_until'] < closure['finished_at'],
        'honest new closure capture/audit/completion times required')
    ready, observation = old['preparation'], old['observation']
    require(observation['observed_at'] < closure['started_at'] and
        strict_equal(closure.get('before'), observation['after']) and
        strict_equal(closure.get('after'), observation['after']) and
        strict_equal(closure.get('all_offline_snapshot'), observation['after']) and
        strict_equal(closure.get('actor'), ready.get('actor')) and
        strict_equal(closure.get('runtime'), ready.get('runtime')) and
        closure.get('predecessor') == ready.get('predecessor') and
        closure.get('authority_source') == ready.get('authority_source') and
        closure.get('runtime_authority_source') == ready.get('runtime_authority_source') and
        strict_equal(closure.get('stop_checks'), dict.fromkeys(STOP_CHECKS, True)) and
        closure.get('entry_input_sent') is True and closure.get('bag_input_sent') is False and
        closure.get('normal_logout_input_sent') is False and
        closure.get('stop_action') == observation.get('stop_action'),
        'actual stopped state/ownership/preservation cannot be relabeled as ordinary logout or restoration')
    require('game_before' not in closure and 'game_start_ticks' not in closure and
        'sigterm_at' not in closure and 'stop_finished_at' not in closure,
        'unobserved game ticks or exact system-stop times cannot be invented')
    precision = closure.get('exact_precision')
    precision_fields = {'query', 'before_row', 'after_row', 'before', 'after', 'input_sent', 'mutation_sent',
        'before_query_started_at', 'before_query_finished_at', 'after_query_started_at', 'after_query_finished_at'}
    require(type(precision) is dict and set(precision) == precision_fields and
        precision.get('query') == PRECISION_QUERY and precision.get('input_sent') is False and
        precision.get('mutation_sent') is False and strict_equal(precision.get('before'), closure['before']) and
        strict_equal(precision.get('after'), closure['after']) and
        strict_equal(precision.get('before_row'), observation['exact_after_precision']['row']) and
        strict_equal(precision.get('after_row'), precision['before_row']),
        'both actual exact offline FLOAT observations must match the retained one-login source')
    times = ('before_query_started_at', 'before_query_finished_at', 'after_query_started_at', 'after_query_finished_at')
    require(all(finite(precision.get(k)) for k in times) and finite(closure.get('source_validation_finished_at')) and
        closure['started_at'] <= precision['before_query_started_at'] <= precision['before_query_finished_at'] <=
        closure['audit_until'] < closure['source_validation_finished_at'] <= precision['after_query_started_at'] <=
        precision['after_query_finished_at'] < closure['finished_at'],
        'final exact query must follow the completed source replay and precede actual closure completion')
    exact_precision(precision['before_row'], closure['before'])
    exact_precision(precision['after_row'], closure['after'])
    return precision


def _source_proof(store, closure, old):
    """Replay immutable sources before the collector's final exact query."""
    from .bag_swap_stopped_contract import stopped_history
    ready, failed, observation, before_precision = (old[k] for k in
        ('preparation', 'failed_entry', 'observation', 'precision'))
    reference(closure.get('source_index_source'))
    index = store.get(closure['source_index_source'], False)
    require(index.get('schema') == 'client442_bag_swap_source_index_v1',
        'the actual source-owned flat index must accompany the stopped closure')
    log_ref = closure.get('stop_log_source')
    reference(log_ref)
    require(log_ref['sha256'] == STOP_LOG_SHA and store.digests.get(store.member(log_ref)) == STOP_LOG_SHA,
        'actual committed owned stop-client output bytes required')
    frame = ready.get('frame', {})
    monitor = frame.get('monitor', {})
    isolation = monitor.get('input_isolation', {})
    require(monitor.get('second_monitor_verified') is True and monitor.get('monitor', {}).get('name') == 'HDMI-1' and
        isolation.get('actor') == isolation.get('actor_lock') == 'scout' and isolation.get('display') == ':2' and
        isolation.get('host_activation_sent') is False and type(isolation.get('game_pid')) is int and
        isolation['game_pid'] == observation.get('observed_owned_game_pid') and
        closure.get('owned_game_identity') == {'pid': isolation['game_pid'], 'source': SOURCES['preparation'], 'frame': frame},
        'the absent physical child must be the original source-owned HDMI-1 scout')
    image = str(Path(store.member(SOURCES['preparation'])).parent / frame['file'])
    require(store.digests.get(image) == frame.get('sha256'), 'original source-owned selected PNG bytes required')
    interval = closure.get('journal_interval')
    refs = closure.get('journal_sources')
    require(interval == {'from': ready['started_at'], 'until': closure['audit_until']} and
        type(refs) is dict and set(refs) == {'packets', 'events'}, 'complete ready-to-new-cutoff journals required')
    rows = {role: store.journal(ref) for role, ref in refs.items()}
    history = stopped_history(rows['packets'], rows['events'], ready, failed, observation,
        before_precision, audit_until=closure['audit_until'])
    require(strict_equal(closure.get('history'), history), 'actual complete stopped history differs from its retained proof')
    epoch, raw_members = code_epochs(store, closure, ready)
    return history, epoch, raw_members


def validate_closure(store, closure):
    require(type(closure) is dict, 'a typed completed stopped-entry boundary is required')
    old = historical(store, closure.get('sources'))
    precision = _boundary(closure, old)
    history, epoch, raw_members = _source_proof(store, closure, old)
    return {'schema': PROOF_SCHEMA, 'qualified_fixture_operations': 453, 'interaction_plan_operations': 916,
        'qualification_added': False, 'operations_admitted': 0, 'excluded_failed_entry': True,
        'original_entry_remains_failed': True, 'system_stop_only': True, 'ten_stop_checks': True,
        'exact_precision': precision['after_row'],
        'exact_precision_samples': {'before_row': precision['before_row'], 'after_row': precision['after_row'],
            **{k: precision[k] for k in ('before_query_started_at', 'before_query_finished_at',
                'after_query_started_at', 'after_query_finished_at')}},
        'history': history, 'code_epochs': epoch}, raw_members


def proof(data, digests, tracking):
    from .bag_swap_source_index import Sources, prove_ancestors
    store = Sources(data, digests, tracking.get('raw_journals', {}), paths=tracking.get('paths', {}))
    prefix = tracking.get('batch_prefix')
    require(prefix == BATCH, 'one actual excluded UI173 archive scope required')
    candidates = [value for name, value in data.items() if name.startswith(prefix) and
        type(value) is dict and value.get('schema') == SCHEMA and value.get('phase') == PHASE]
    require(len(candidates) == 1, 'one completed excluded system-stop closure required')
    closure = candidates[0]
    result, raw = validate_closure(store, closure)
    ready = store.get(SOURCES['preparation'], False)
    ancestors = prove_ancestors(store, ready)
    from .bag_swap_failed_evidence import _metadata
    metadata_projection = _metadata(store, closure, tracking)
    metadata = tracking.get('archived_metadata')
    require(type(metadata) is dict and metadata.get('code_commit') == closure['code_commit'] and
        metadata.get('counts') == {} and type(metadata.get('qualified_fixture_operations')) is int and
        metadata['qualified_fixture_operations'] == 453 and type(metadata.get('interaction_plan_operations')) is int and
        metadata['interaction_plan_operations'] == 916, 'actual excluded publisher code and unchanged qualification totals required')
    runs = []
    for name in sorted(name for name in tracking['manifest'] if name.startswith(prefix) and name.endswith('/episode.json')):
        value = data.get(name)
        require(type(value) is dict and value.get('cases') == value.get('cleanup') == [] and
            value.get('qualification_added') is False and type(value.get('completed')) is bool and
            (value.get('failure') is None if value['completed'] else type(value.get('failure')) is str and value['failure']) and
            value.get('controller') == 'code' and value.get('model') is None and value.get('revision') is None,
            'every original current-batch Trial must retain empty cases and truthful success/failure')
        runs.append({'path': name, **{k: value[k] for k in ('completed', 'failure', 'controller', 'model', 'revision')}})
    require(runs and strict_equal(metadata.get('runs'), runs), 'generic run projection must match all actual Trial source bytes')
    publisher = str(_repo(closure['committed_sources']) / 'tools/client_compatibility/checkpoint_interactions.py')
    nodes = [node.value for node in ast.parse(raw[publisher]).body if isinstance(node, ast.Assign) and
        any(isinstance(target, ast.Name) and target.id == 'SAFE_BODY_NAMES' for target in node.targets)]
    require(len(nodes) == 1, 'one source-bound publisher safe-body declaration required')
    safe = ast.literal_eval(nodes[0])
    require(type(safe) is set and all(type(name) is str for name in safe), 'typed actual publisher body projection required')
    rows = {key: store.journal(ref) for key, ref in closure['journal_sources'].items()}
    for key in ('packets', 'events'):
        generic = tracking.get(key)
        require(type(generic) is list and all(type(row) is dict and finite(row.get('time')) for row in generic),
            'full generic tracking rows require finite time before filtering')
        scoped = [row for row in generic if closure['journal_interval']['from'] <= row['time'] <= closure['audit_until']]
        expected = rows[key] if key == 'events' else [row for row in rows[key] if 'body' not in row or row.get('name') in safe]
        require(strict_equal(scoped, expected), 'ordered generic journal projection differs from complete closure copies')
    require(tracking.get('members') == set(TRACKING_MEMBERS), 'both complete source-owned tracking journals required')
    return {**result, **metadata_projection, 'ancestors': ancestors, 'current_batch_episode_count': len(runs),
        'current_batch_cases': 0, 'both_tracking_journals_verified': True}
