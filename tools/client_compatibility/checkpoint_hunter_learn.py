"""Root-invoked publication adapter for the ordinary Beast Lore pipeline.

Carried authority keeps its original references and exact bytes, under digest
filenames which cannot become episodes or training choices. Only ``checkpoint``
invokes the existing publisher; classification and carrying perform no gameplay,
SQL, build, subprocess or network operations.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat

from . import lab_runtime as lab

LIFECYCLE_SCHEMA = 'client442_hunter_learn_offline_lifecycle_v1'
CLOSURE_SCHEMA = 'client442_owned_hunter_learn_closure_v1'
ANCESTRY_SCHEMA = 'client442_hunter_learn_ancestry_v1'
REST_PRECISION_SCHEMA = 'client442_owned_hunter_readonly_rest_precision_v1'
MANIFEST = 'ancestry_manifest.json'
MAX_SOURCES = 128
PRECISION_CHECKS = {'all_six_offline', 'all_saved_state_unchanged', 'hunter_identity',
    'snapshot_rest_matches', 'exact_float32'}
PREFLIGHT_CHECKS = {'source_bound', 'all_six_offline', 'snapshot_preserved',
    'untrained_hunter', 'native_prerequisites'}
NORMALIZE_CHECKS = {'exact_source', 'all_six_offline', 'creator_only', 'health_preserved', 'protected_actors'}
CLEAN_CHECKS = {'exact_source', 'all_six_offline', 'removed_new1462_only', 'exact_refund',
    'saved_inventory_preserved', 'protected_actors'}
COMMON_FIELDS = {'schema', 'phase', 'started_at', 'finished_at', 'completed', 'failure',
    'input_sent', 'mutation_sent', 'qualification_added', 'sources', 'before', 'after',
    'actor', 'runtime', 'checks'}
PHASE_FIELDS = {
    'hunter_learn_rest_precision_complete': ({'source', 'query', 'row', 'rest_sources'}, PRECISION_CHECKS),
    'hunter_learn_prerequisites_reviewed': ({'source', 'prerequisite_fingerprint'}, PREFLIGHT_CHECKS),
    'hunter_learn_creator_normalized': ({'source', 'fixture_source', 'precision_source', 'entry_source',
        'rest_baseline_source', 'expected_after', 'native_rest_accrual_preserved', 'normalized_columns'}, NORMALIZE_CHECKS),
    'hunter_learn_offline_cleaned': ({'preparation_source', 'purchase_source', 'restoration_source',
        'park_source', 'precision_source', 'creator_normalization_source', 'expected_after',
        'native_rest_accrual_preserved', 'refunded_copper', 'removed_spell'}, CLEAN_CHECKS),
}
RECOVERY_PHASE = 'hunter_learn_recovery_offline_cleaned'
RECOVERY_FIELDS = {'preparation_source', 'restoration_source', 'park_source', 'precision_source',
    'failed_source', 'expected_after', 'native_rest_accrual_preserved', 'recovery_only',
    'failed_whole_excluded', 'purchase_qualified', 'train_input_replayed', 'removed_spell', 'refunded_copper'}
TRANSACTION_FIELDS = {'commit_attempted', 'transaction_committed'}
SETTLEMENT_FIELDS = {'settled_commit_only', 'original_mutation_sent', 'cleanup_failed_source'}
RECOVERY_FLAGS = {'recovery_only': True, 'failed_whole_excluded': True,
    'purchase_qualified': False, 'train_input_replayed': False}
STARTED_PHASES = {
    'hunter_learn_rest_precision_started': 'hunter_learn_rest_precision_complete',
    'hunter_learn_prerequisites_started': 'hunter_learn_prerequisites_reviewed',
    'hunter_learn_creator_normalization_started': 'hunter_learn_creator_normalized',
    'hunter_learn_offline_cleanup_started': 'hunter_learn_offline_cleaned',
    'hunter_learn_recovery_cleanup_started': RECOVERY_PHASE,
    'hunter_learn_offline_cleanup_settlement_started': 'hunter_learn_offline_cleaned',
    'hunter_learn_recovery_cleanup_settlement_started': RECOVERY_PHASE,
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def private_path(path, directory=False):
    path = Path(path)
    boundary = (lab.ROOT / 'evidence').absolute()
    require(path.is_absolute() and path.is_relative_to(boundary) and '..' not in path.parts,
        'source is outside the private evidence boundary')
    require(not any(p.is_symlink() for p in (path, *path.parents)), 'symlink evidence is inadmissible')
    require(path.is_dir() if directory else path.is_file(), 'private evidence path is absent')
    return path


def batch_path(directory):
    path = private_path(directory, True)
    require(path.parent == lab.ROOT / 'evidence', 'requires a named private interaction batch')
    return path


def reference(ref):
    require(isinstance(ref, dict) and set(ref) == {'path', 'sha256'} and
        isinstance(ref['path'], str) and re.fullmatch('[0-9a-f]{64}', ref.get('sha256', '')),
        'complete immutable JSON source reference is required')
    return private_path(ref['path'])


def json_bytes(path, digest=None):
    path = private_path(path)
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    require(digest is None or actual == digest, 'source JSON digest changed')
    value = json.loads(raw)
    require(isinstance(value, dict), 'source JSON must be an object')
    return raw, actual, value


def write_exclusive(path, raw):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, 'wb') as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    require(stat.S_IMODE(path.stat().st_mode) == 0o600 and path.read_bytes() == raw,
        'private ancestry copy differs')


def successful(value):
    require(value.get('completed') is True and value.get('failure') is None and
        all(type(value.get(k)) in (int, float) and math.isfinite(value[k]) for k in ('started_at', 'finished_at')) and
        0 < value['started_at'] < value['finished_at'], 'diagnostic must be closed and successful')
    return value


def failed_lifecycle(run, directory, ancestry):
    """Retain a closed failed attempt without assigning choices or pass checks."""
    phase = run.get('phase')
    complete = STARTED_PHASES.get(phase, phase)
    require(run.get('schema') == LIFECYCLE_SCHEMA and (complete in PHASE_FIELDS or complete == RECOVERY_PHASE),
        'unknown failed offline learning diagnostic schema or phase')
    required = {'schema', 'phase', 'started_at', 'finished_at', 'completed', 'failure',
        'input_sent', 'mutation_sent', 'qualification_added', 'sources', 'before'}
    allowed = COMMON_FIELDS | (RECOVERY_FIELDS if complete == RECOVERY_PHASE else PHASE_FIELDS[complete][0])
    if complete in ('hunter_learn_offline_cleaned', RECOVERY_PHASE):
        allowed |= TRANSACTION_FIELDS | SETTLEMENT_FIELDS
    require(required <= set(run) <= allowed, 'exact failed offline learning diagnostic fields differ')
    require(run['completed'] is False and isinstance(run['failure'], str) and run['failure'].strip() and
        all(type(run.get(k)) in (int, float) and math.isfinite(run[k]) for k in ('started_at', 'finished_at')) and
        0 < run['started_at'] < run['finished_at'], 'failed diagnostic must have a closed finite interval and actual failure')
    require(run['input_sent'] is False and run['qualification_added'] is False and
        type(run['mutation_sent']) is bool, 'failed diagnostic input or qualification flags differ')
    for key in TRANSACTION_FIELDS & set(run):
        require(type(run[key]) is bool, 'failed diagnostic transaction flag differs')
    for key in (SETTLEMENT_FIELDS - {'cleanup_failed_source'}) & set(run):
        require(type(run[key]) is bool, 'failed diagnostic settlement flag differs')
    if complete == RECOVERY_PHASE:
        require(all(run.get(key) is value for key, value in RECOVERY_FLAGS.items()),
            'failed recovery must retain whole-trial exclusion')
    snapshot(run['before'])
    require(isinstance(run['sources'], list) and run['sources'], 'failed diagnostic source roles are absent')
    for ref in run['sources']:
        source_value(ref, directory, ancestry)
    if 'checks' in run:
        require(isinstance(run['checks'], dict), 'failed diagnostic checks must remain an object')


def legacy_precision(path, value, classifier=None):
    """Keep the original precision validator and its original episode identity."""
    if value.get('schema') != REST_PRECISION_SCHEMA:
        return
    if classifier is None:
        from .checkpoint_interactions import checkpoint_runs as classifier
    classifier([(path, value)], path.parent.parent)


def carry(directory, preparation):
    """Freeze only UI169's pinned authority and the current resume boundary.

    ``preparation`` is the new preparation episode path (or its already loaded
    object). Historical accepted episodes are opaque authority: their deeper
    trails were checked by the pinned actual remote review. The resume record's
    checkpoint and restoration references are the only extra graph edges needed
    by the new proof. No receipt reference is rewritten.
    """
    directory = batch_path(directory)
    if not isinstance(preparation, dict):
        _, _, preparation = json_bytes(preparation)
    successful(preparation)
    require(preparation.get('phase') == 'await_owned_class_lobby_review' and
        isinstance(preparation.get('accepted_previous_sources'), list) and
        len(preparation['accepted_previous_sources']) == 4 and
        isinstance(preparation.get('sources'), list) and len(preparation['sources']) == 2,
        'requires the whole new learning preparation authority')
    seeds = [*preparation['accepted_previous_sources'], preparation['remote_source'],
        preparation['primary_stop_source'], *preparation['sources']]
    queue = [(ref, False) for ref in seeds]
    # Resolve the resume record, rather than recursively importing UI history.
    queue[-2] = (preparation['sources'][0], True)
    seen, rows, copies = {}, [], {}
    pending = []
    while queue:
        ref, resume = queue.pop(0)
        path = reference(ref)
        require(path.suffix == '.json', 'carried authority must be private JSON')
        old = seen.get(str(path))
        require(old is None or old == ref['sha256'], 'one source path has conflicting digests')
        if old is not None:
            continue
        require(len(seen) < MAX_SOURCES, 'ancestry graph exceeds its bounded source count')
        seen[str(path)] = ref['sha256']
        raw, digest, value = json_bytes(path, ref['sha256'])
        legacy_precision(path, value)
        if resume:
            require(value.get('schema') == 'client442_hunter_learn_scout_resume_v1' and
                value.get('sources') == preparation['accepted_previous_sources'] and
                value.get('remote_source') == preparation['remote_source'] and
                value.get('primary_stop_source') == preparation['primary_stop_source'] and
                value.get('restoration_source') == preparation['sources'][1],
                'current resume authority differs from preparation')
            queue.extend((value[key], False) for key in ('checkpoint_source', 'restoration_source'))
        if path.is_relative_to(directory):
            continue
        copy = directory / 'ancestry' / (digest + '.json')
        rows.append({'original_path': str(path), 'sha256': digest, 'copy_path': str(copy), 'bytes': len(raw)})
        if digest not in copies:
            copies[digest] = raw
            pending.append((copy, raw))
    target = directory / 'ancestry'
    require(not target.exists() and not (directory / MANIFEST).exists(), 'ancestry must never overwrite an existing carry')
    target.mkdir(mode=0o700)
    require(stat.S_IMODE(target.stat().st_mode) == 0o700, 'ancestry directory is not private')
    for copy, raw in pending:
        write_exclusive(copy, raw)
        require(lab.sha256(copy) == copy.stem, 'carried source bytes differ from digest filename')
    manifest = {'schema': ANCESTRY_SCHEMA, 'sources': sorted(rows, key=lambda row: row['original_path'])}
    write_exclusive(directory / MANIFEST, (json.dumps(manifest, indent=2) + '\n').encode())
    return manifest


def carried(directory, ordinary=None):
    """Verify the manifest against all ancestry bytes, independent of originals."""
    directory = batch_path(directory)
    path = directory / MANIFEST
    if not path.exists():
        require(not (directory / 'ancestry').exists(), 'unmanifested ancestry is inadmissible')
        return {}
    _, _, manifest = json_bytes(path)
    require(set(manifest) == {'schema', 'sources'} and manifest['schema'] == ANCESTRY_SCHEMA and
        isinstance(manifest['sources'], list) and len(manifest['sources']) <= MAX_SOURCES,
        'exact ancestry manifest schema differs')
    ancestry = private_path(directory / 'ancestry', True)
    require(stat.S_IMODE(ancestry.stat().st_mode) == 0o700, 'ancestry directory is not private')
    result, files = {}, set()
    for row in manifest['sources']:
        require(set(row) == {'original_path', 'sha256', 'copy_path', 'bytes'} and
            isinstance(row['original_path'], str) and isinstance(row['sha256'], str) and
            re.fullmatch('[0-9a-f]{64}', row['sha256']) and type(row['bytes']) is int and row['bytes'] > 0,
            'complete carried source manifest row differs')
        original = Path(row['original_path'])
        require(original.is_absolute() and original.is_relative_to(lab.ROOT / 'evidence') and
            not original.is_relative_to(directory) and '..' not in original.parts,
            'carried source original is outside private ancestry')
        copy = Path(row['copy_path'])
        require(copy == ancestry / (row['sha256'] + '.json'), 'carried source copy path differs')
        raw, _, value = json_bytes(copy, row['sha256'])
        require(len(raw) == row['bytes'] and stat.S_IMODE(copy.stat().st_mode) == 0o600,
            'carried source size or private mode differs')
        require(str(original) not in result, 'carried source original path is duplicated')
        result[str(original)] = (row['sha256'], value)
        files.add(copy)
        if value.get('schema') == REST_PRECISION_SCHEMA:
            # The carried filename is intentionally not episode.json; validate
            # the original receipt unchanged through its established validator.
            legacy_precision(private_path(original), value, ordinary)
    require(set(ancestry.iterdir()) == files, 'ancestry contains unmanifested artifacts')
    return result


def source_value(ref, directory, ancestry):
    require(isinstance(ref, dict) and set(ref) == {'path', 'sha256'} and
        isinstance(ref['path'], str) and re.fullmatch('[0-9a-f]{64}', ref.get('sha256', '')),
        'complete immutable JSON source reference is required')
    path = Path(ref['path'])
    require(path.is_absolute() and path.is_relative_to(lab.ROOT / 'evidence') and '..' not in path.parts,
        'diagnostic source is outside private evidence')
    if path.is_relative_to(directory):
        return json_bytes(path, ref['sha256'])[2]
    require(ancestry.get(str(path), (None,))[0] == ref['sha256'], 'external diagnostic source is not carried by exact hash')
    return ancestry[str(path)][1]


def refs(value):
    if isinstance(value, dict):
        if set(value) == {'path', 'sha256'}:
            yield value
        else:
            for child in value.values():
                yield from refs(child)
    elif isinstance(value, list):
        for child in value:
            yield from refs(child)


def snapshot(value):
    from .hunter_learn_contract import owned_snapshot
    owned_snapshot(value)
    require(all(set(actor) == {'native', 'saved', 'pets', 'inventory'} and
        isinstance(actor['saved'], dict) and isinstance(actor['pets'], list) and isinstance(actor['inventory'], list)
        for actor in value.values()), 'whole offline snapshot shape differs')


def snapshot_source(value):
    phase = value.get('phase')
    key = {'await_owned_class_lobby_review': 'learn_offline_baseline',
        'await_original_selection_review': 'all_offline_snapshot',
        'hunter_learn_creator_normalized': 'after', 'hunter_learn_offline_cleaned': 'after'}.get(phase)
    require(key is not None, 'offline diagnostic source phase differs')
    return value[key]


def cleanup_settlement(run, directory, ancestry, ordinary_sources, phase):
    """A fresh read may prove an earlier commit; it cannot replay that mutation."""
    settled = run.get('settled_commit_only') is True
    if not settled:
        require(not SETTLEMENT_FIELDS & set(run) and run['mutation_sent'] is True and
            run['sources'] == ordinary_sources, 'ordinary cleanup mutation or source roles differ')
        if TRANSACTION_FIELDS & set(run):
            require(run.get('commit_attempted') is True and run.get('transaction_committed') is True,
                'successful cleanup transaction outcome differs')
        return
    require(SETTLEMENT_FIELDS <= set(run) and run['original_mutation_sent'] is True and
        run['mutation_sent'] is False and run.get('commit_attempted') is False and
        run.get('transaction_committed') is True and
        run['sources'] == ordinary_sources + [run['cleanup_failed_source']],
        'read-only committed cleanup settlement flags or roles differ')
    original = source_value(run['cleanup_failed_source'], directory, ancestry)
    failed_lifecycle(original, directory, ancestry)
    expected_phase = ('hunter_learn_recovery_cleanup_started' if phase == RECOVERY_PHASE else
        'hunter_learn_offline_cleanup_started')
    require(original.get('phase') == expected_phase and original.get('mutation_sent') is True and
        original.get('commit_attempted') is True and type(original.get('transaction_committed')) is bool and
        original['sources'] == ordinary_sources and
        original['finished_at'] <= run['started_at'] and original['before'] == run['before'] and
        original.get('expected_after') == run['expected_after'] and
        all(original.get(key) == run.get(key) for key in ((RECOVERY_FIELDS if phase == RECOVERY_PHASE else
            PHASE_FIELDS['hunter_learn_offline_cleaned'][0]) - {'expected_after'})),
        'settlement differs from the original immutable attempted cleanup')


def recovery_lifecycle(run, directory, ancestry):
    """Validate a completed repair, keeping the failed gameplay whole excluded."""
    from . import hunter_learn_contract as contract
    successful(run)
    required = COMMON_FIELDS | RECOVERY_FIELDS
    require(required <= set(run) <= required | TRANSACTION_FIELDS | SETTLEMENT_FIELDS and
        run.get('phase') == RECOVERY_PHASE and run['input_sent'] is False and
        run['qualification_added'] is False and all(run[key] is value for key, value in RECOVERY_FLAGS.items()),
        'exact whole-trial-excluded cleanup recovery differs')
    require(set(run['checks']) == CLEAN_CHECKS and all(value is True for value in run['checks'].values()),
        'complete cleanup recovery checks differ')
    snapshot(run['before']); snapshot(run['after'])
    roles = [run[key] for key in ('preparation_source', 'restoration_source', 'park_source', 'precision_source', 'failed_source')]
    cleanup_settlement(run, directory, ancestry, roles, RECOVERY_PHASE)
    preparation, restored, park, exact = [successful(source_value(ref, directory, ancestry)) for ref in roles[:4]]
    failed = source_value(run['failed_source'], directory, ancestry)
    require(failed.get('completed') is False and isinstance(failed.get('failure'), str) and failed['failure'].strip() and
        all(type(failed.get(key)) in (int, float) and math.isfinite(failed[key]) for key in ('started_at', 'finished_at')) and
        0 < failed['started_at'] < failed['finished_at'] <= restored['started_at'] and
        restored.get('phase') == 'hunter_learn_recovery_restored' and
        restored.get('failed_source') == run['failed_source'] and
        all(restored.get(key) is value for key, value in RECOVERY_FLAGS.items()) and
        park.get('phase') == 'await_original_selection_review' and park.get('source') == run['restoration_source'] and
        park.get('failed_source') == run['failed_source'] and
        all(park.get(key) is value for key, value in RECOVERY_FLAGS.items()) and
        exact.get('phase') == 'hunter_learn_rest_precision_complete' and exact.get('source') == run['park_source'] and
        run['before'] == park.get('all_offline_snapshot') and run['runtime'] == park.get('runtime') and
        run['actor'] == park.get('actor') and
        all(value['finished_at'] <= run['started_at'] for value in (preparation, restored, park, exact)),
        'attributable failed-whole recovery ancestry differs')
    require(run['after'] == run['expected_after'] == contract.cleanup_expected(
        preparation['learn_offline_baseline'], run['before']) and type(run['removed_spell']) is int and
        run['removed_spell'] == contract.SPELL and type(run['refunded_copper']) is int and
        run['refunded_copper'] == contract.PRICE, 'recovery cleanup exceeds the exact row removal and refund')


def lifecycle(run, directory, ancestry):
    from . import hunter_learn_contract as contract
    from . import hunter_learn_preservation as preservation
    from . import hunter_learn_evidence as evidence
    successful(run)
    phase = run.get('phase')
    require(phase in PHASE_FIELDS, 'unknown offline learning diagnostic phase')
    fields, names = PHASE_FIELDS[phase]
    required = COMMON_FIELDS | fields
    optional = TRANSACTION_FIELDS | SETTLEMENT_FIELDS if phase == 'hunter_learn_offline_cleaned' else set()
    require(required <= set(run) <= required | optional, 'exact offline learning diagnostic fields differ')
    for key in TRANSACTION_FIELDS & set(run):
        require(type(run[key]) is bool, 'diagnostic transaction flag differs')
    require(set(run['checks']) == names and all(v is True for v in run['checks'].values()),
        'complete offline learning diagnostic checks differ')
    require(run['input_sent'] is False and run['qualification_added'] is False and
        type(run['mutation_sent']) is bool, 'diagnostic input or qualification flags differ')
    snapshot(run['before']); snapshot(run['after'])
    require(isinstance(run['sources'], list) and run['sources'], 'diagnostic source roles are absent')
    sources = [source_value(ref, directory, ancestry) for ref in run['sources']]
    for ref, value in zip(run['sources'], sources):
        if ref != run.get('cleanup_failed_source'):
            successful(value)
    require(all(value['finished_at'] <= run['started_at'] for value in sources), 'diagnostic source chronology differs')
    if phase in ('hunter_learn_rest_precision_complete', 'hunter_learn_prerequisites_reviewed'):
        require(run['sources'] == [run['source']] and run['mutation_sent'] is False and
            run['before'] == run['after'] == snapshot_source(sources[0]), 'read-only learning source or state differs')
        require(run['actor'] == sources[0].get('actor') and set(run['runtime']) in (
            {'worldserver', 'modern_world'}, {'worldserver', 'modern_world', 'client'}) and
            all(value == sources[0].get('runtime', {}).get(key) for key, value in run['runtime'].items()),
            'read-only learning actor or native runtime differs')
        if phase == 'hunter_learn_rest_precision_complete':
            evidence.precision_proof(run, run['source'], run['before'])
        else:
            evidence.prerequisite(run['prerequisite_fingerprint'])
            h = contract.owned_snapshot(run['before'])
            require(h['saved']['spells'] == contract.BASE_SPELLS and h['native']['money'] == contract.MONEY,
                'prerequisite diagnostic is not untrained')
    elif phase == 'hunter_learn_creator_normalized':
        require(run['sources'] == [run['fixture_source'], run['source'], run['precision_source']],
            'creator diagnostic source roles differ')
        preparation, park, exact = sources
        require(park.get('phase') == 'await_original_selection_review' and
            exact.get('phase') == 'hunter_learn_rest_precision_complete' and exact.get('source') == run['source'] and
            run['before'] == park.get('all_offline_snapshot') == exact.get('after') and
            run['entry_source'] == park.get('entry_source') and run['rest_baseline_source'] == park.get('rest_baseline_source') and
            run['actor'] == park.get('actor') and
            run['runtime'] == park.get('runtime'), 'source-bound creator diagnostic differs')
        expected = preservation.creator_expected(preparation['learn_offline_baseline'],
            run['before'], park['native_pet_reload'])
        require(run['after'] == run['expected_after'] == expected and
            run['mutation_sent'] is (expected != run['before']) and
            run['normalized_columns'] == ([] if expected == run['before'] else ['CreatedBySpell']),
            'exact creator-only mutation differs')
    else:
        expected_refs = [run[k] for k in ('preparation_source', 'purchase_source', 'restoration_source', 'park_source', 'precision_source')]
        normalized = run['creator_normalization_source']
        cleanup_settlement(run, directory, ancestry, expected_refs + ([normalized] if normalized else []), phase)
        preparation, purchase, restoration, park, exact = sources[:5]
        require(purchase.get('phase') == 'hunter_learn_transition_complete' and
            restoration.get('phase') == 'hunter_learn_online_restored' and
            restoration.get('purchase_source') == run['purchase_source'] and park.get('source') == run['restoration_source'] and
            exact.get('phase') == 'hunter_learn_rest_precision_complete' and exact.get('source') == run['park_source'] and
            run['before'] == (sources[5]['after'] if normalized else park.get('all_offline_snapshot')) and
            run['actor'] == park.get('actor') and run['runtime'] == park.get('runtime'),
            'whole cleanup ancestry differs')
        require(run['after'] == run['expected_after'] == contract.cleanup_expected(
            preparation['learn_offline_baseline'], run['before']) and
            type(run['refunded_copper']) is int and run['refunded_copper'] == contract.PRICE and
            type(run['removed_spell']) is int and run['removed_spell'] == contract.SPELL,
            'offline cleanup exceeds the exact row removal and refund')


def checkpoint_runs(episodes, directory, ordinary=None):
    """Project only the two new schemas; delegate every ordinary Trial unchanged."""
    directory = batch_path(directory)
    if ordinary is None:
        from .checkpoint_interactions import checkpoint_runs as ordinary
    ancestry = carried(directory, ordinary)
    cases, runs, trials = [], [], []
    for path, run in episodes:
        path = private_path(path)
        require(path.is_relative_to(directory) and path.name == 'episode.json', 'episode is outside the current batch')
        require(json_bytes(path)[2] == run, 'episode changed during publication classification')
        schema = run.get('schema')
        if schema not in (LIFECYCLE_SCHEMA, CLOSURE_SCHEMA):
            selected, metadata, attributed = ordinary([(path, run)], directory)
            cases.extend(selected); runs.extend(metadata); trials.extend(attributed)
            continue
        if schema == LIFECYCLE_SCHEMA:
            if run.get('completed') is False:
                failed_lifecycle(run, directory, ancestry)
                for ref in refs(run):
                    if Path(ref['path']).is_relative_to(lab.ROOT / 'evidence'):
                        source_value(ref, directory, ancestry)
                metadata = {'path': str(path.relative_to(lab.ROOT)), 'record_kind': 'excluded_diagnostic_failure',
                    'source_schema': schema, 'phase': run['phase'], 'completed': False, 'failure': run['failure'],
                    'started_at': run['started_at'], 'finished_at': run['finished_at'], 'input_sent': False,
                    'mutation_sent': run['mutation_sent'], 'qualification_added': False, 'operations_admitted': 0,
                    'sources': run['sources'], 'receipt_sha256': lab.sha256(path)}
                for key in ({'checks'} | TRANSACTION_FIELDS | SETTLEMENT_FIELDS | set(RECOVERY_FLAGS)) & set(run):
                    metadata[key] = run[key]
                runs.append(metadata)
                continue
            if run.get('phase') == RECOVERY_PHASE:
                recovery_lifecycle(run, directory, ancestry)
                kind = 'excluded_diagnostic_recovery'
            else:
                lifecycle(run, directory, ancestry)
                kind = 'offline_lifecycle_diagnostic'
        else:
            from .hunter_learn_evidence import closure_checks
            successful(run)
            closure_checks(run)
            require(set(run) == {'schema', 'phase', 'started_at', 'finished_at', 'completed', 'failure',
                'runtime', 'actor', 'sources', 'primary_stop_source', 'all_offline_snapshot', 'proof',
                'checks', 'input_sent', 'mutation_sent', 'qualification_added', 'controller', 'model'} and
                run['controller'] == 'code' and run['model'] is None,
                'exact semantic closure fields differ')
            for ref in [*run['sources'].values(), run['primary_stop_source']]:
                source_value(ref, directory, ancestry)
            kind = 'semantic_closure'
        for ref in refs(run):
            if Path(ref['path']).is_relative_to(lab.ROOT / 'evidence'):
                source_value(ref, directory, ancestry)
        runs.append({'path': str(path.relative_to(lab.ROOT)), 'record_kind': kind, 'source_schema': schema,
            'phase': run['phase'], 'completed': True, 'started_at': run['started_at'], 'finished_at': run['finished_at'],
            'input_sent': run['input_sent'], 'mutation_sent': run['mutation_sent'],
            'qualification_added': False, 'operations_admitted': 0, 'cases': [],
            'checks': run['checks'], 'sources': run['sources'], 'receipt_sha256': lab.sha256(path)})
        for key in (TRANSACTION_FIELDS | SETTLEMENT_FIELDS | set(RECOVERY_FLAGS)) & set(run):
            runs[-1][key] = run[key]
        if kind == 'excluded_diagnostic_recovery':
            runs[-1].pop('cases')
    return cases, runs, trials


def checkpoint(directory, name):
    """Publish learning records and retain the frozen trainer's movement proof."""
    from . import checkpoint_interactions as original
    previous = original.checkpoint_runs
    previous_body_names = original.SAFE_BODY_NAMES
    def adapted(episodes, batch):
        return checkpoint_runs(episodes, batch, ordinary=previous)
    try:
        original.checkpoint_runs = adapted
        original.SAFE_BODY_NAMES = previous_body_names | {
            'SMSG_ON_MONSTER_MOVE_TRANSPORT', 'SMSG_MOVE_UPDATE_TELEPORT'}
        return original.checkpoint(directory, name)
    finally:
        original.checkpoint_runs = previous
        original.SAFE_BODY_NAMES = previous_body_names


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['carry', 'checkpoint'])
    parser.add_argument('--directory', required=True, type=Path)
    parser.add_argument('--preparation', type=Path)
    parser.add_argument('--name')
    args = parser.parse_args()
    if args.action == 'carry':
        if args.preparation is None: parser.error('carry requires --preparation')
        result = carry(args.directory, args.preparation)
        print(json.dumps({'schema': result['schema'], 'carried_sources': len(result['sources'])}))
    else:
        if not args.name: parser.error('checkpoint requires --name')
        checkpoint(args.directory, args.name)


if __name__ == '__main__':
    main()
