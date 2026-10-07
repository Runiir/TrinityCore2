"""Publication preserves native-learning diagnostics without fabricated Trials."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import stat
import struct
import subprocess
import sys

import pytest

from tools.client_compatibility import checkpoint_hunter_learn as publication
from tools.client_compatibility import checkpoint_interactions as original
from tools.client_compatibility import hunter_learn_contract as contract
from tools.client_compatibility import hunter_learn_evidence as evidence
from tools.client_compatibility import hunter_learn_preservation as preservation
from tools.client_compatibility.interaction_metrics import choice_counts
from tools.client_compatibility.world.tests.test_interaction_checkpoint_diagnostic import diagnostic_batch
from tools.client_compatibility.world.tests.test_hunter_learn_trainer import trainer_fixture, SPAWN_BYTES
from tools.client_compatibility.world.buffer import Writer


def offline():
    result = {str(g): {'native': {'guid': g, 'online': 0}, 'saved': {}, 'pets': [], 'inventory': []}
        for g in range(1, 7)}
    result['6'] = {'native': {'guid': 6, 'account': 2, 'name': 'Harnesshunt', 'race': 1,
        'class': 3, 'level': 10, 'online': 0, 'money': contract.MONEY, 'xp': 45,
        'rest_bonus': 100.0, 'logout_time': 1000, 'is_logout_resting': 0},
        'saved': {'spells': deepcopy(contract.BASE_SPELLS)}, 'inventory': [], 'pets': [
            {'id': 4, 'owner': 6, 'entry': 42717, 'name': 'Harnesswolf', 'renamed': 1,
                'slot': 5, 'active': 0, 'curhealth': 278, 'savetime': 100, 'CreatedBySpell': 883, 'PetType': 1, 'level': 10},
            {'id': 16, 'owner': 6, 'entry': 299, 'name': 'Wolf', 'renamed': 0,
                'slot': 0, 'active': 1, 'curhealth': 278, 'savetime': 200, 'CreatedBySpell': 13481, 'PetType': 1, 'level': 10}]}
    return result


def trial(phase, start=10, finish=11):
    return {'schema': 'client442_laya_interactions_v1', 'phase': phase,
        'completed': True, 'failure': None, 'started_at': start, 'finished_at': finish,
        'controller': 'code', 'model': None, 'revision': None, 'cases': [],
        'runtime': {'worldserver': {'pid': 1}, 'modern_world': {'pid': 2}, 'client': {'pid': 3}}, 'actor': {'guid': 6}}


def prerequisites():
    value = {'dbc_hashes': contract.DBC_HASHES, 'spell': [[1462, 65536, 132096] + [0] * 45],
        'effects': [contract.EFFECT], 'abilities': [contract.ABILITY],
        'matching_criteria': [], 'trainer': [contract.TRAINER_ROW],
        'lesson': [[40, 1462, 680, 0, 0, 0, 0, 0, 10]],
        'relations': {k: [] for k in ('learn', 'required', 'pet', 'linked')}}
    return {**value, 'sha256': contract.fingerprint(value)}


@pytest.fixture
def batch(tmp_path, monkeypatch):
    root = tmp_path / 'lab'
    directory = root / 'evidence' / 'learn'
    directory.mkdir(parents=True, mode=0o700)
    monkeypatch.setattr(publication.lab, 'ROOT', root)
    monkeypatch.setattr(publication.lab, 'REPO', tmp_path / 'repo')
    def put(name, value, external=False, filename='episode.json'):
        path = (root / 'evidence' / 'previous' if external else directory) / name / filename
        publication.lab.private_write(path, json.dumps(value, indent=2) + '\n')
        return {'path': str(path), 'sha256': publication.lab.sha256(path)}
    return directory, put


@pytest.fixture
def diagnostic(batch):
    directory, put = batch
    before = offline()
    source = put('preparation', {**trial('await_owned_class_lobby_review'), 'learn_offline_baseline': before})
    run = {'schema': publication.LIFECYCLE_SCHEMA, 'phase': 'hunter_learn_prerequisites_reviewed',
        'started_at': 12, 'finished_at': 13, 'completed': True, 'failure': None,
        'input_sent': False, 'mutation_sent': False, 'qualification_added': False, 'sources': [source],
        'source': source, 'before': before, 'after': deepcopy(before), 'actor': {'guid': 6},
        'runtime': {'worldserver': {'pid': 1}, 'modern_world': {'pid': 2}},
        'prerequisite_fingerprint': prerequisites(), 'checks': dict.fromkeys(publication.PREFLIGHT_CHECKS, True)}
    path = Path(put('preflight', run)['path'])
    return directory, put, path, run


def rewrite(path, value):
    publication.lab.private_write(path, json.dumps(value, indent=2) + '\n')


def test_closed_preflight_is_zero_choices_without_trial_identity(diagnostic):
    directory, _, path, run = diagnostic
    raw = path.read_bytes()
    cases, metadata, trials = publication.checkpoint_runs([(path, run)], directory)
    assert cases == trials == [] and all(v == 0 for v in choice_counts(trials).values())
    assert metadata[0]['source_schema'] == publication.LIFECYCLE_SCHEMA
    assert metadata[0]['record_kind'] == 'offline_lifecycle_diagnostic'
    assert metadata[0]['operations_admitted'] == 0 and metadata[0]['mutation_sent'] is False
    assert not {'controller', 'model', 'revision', 'failure'} & set(metadata[0])
    assert not {'controller', 'model', 'revision', 'cases'} & set(run)
    assert path.read_bytes() == raw


def revive_parked_diagnostic(diagnostic):
    directory, put, path, run = diagnostic
    parked = {**trial('owned_revive_parked_boundary'), 'actor': {'guid': 2},
        'input_sent': False, 'qualification_added': False,
        'all_offline_snapshot': deepcopy(run['before']),
        'checks': dict.fromkeys(publication.REVIVE_PARKED_CHECKS, True)}
    source = put('accepted_revive_closure', parked)
    run.update(source=source, sources=[source], actor=deepcopy(parked['actor']))
    rewrite(path, run)
    return directory, path, run, Path(source['path']), parked


def test_revive_parked_preflight_projects_only_its_complete_offline_closure(diagnostic):
    directory, path, run, source_path, source = revive_parked_diagnostic(diagnostic)
    raw = path.read_bytes(), source_path.read_bytes()
    cases, metadata, trials = publication.checkpoint_runs([(path, run)], directory)
    assert cases == trials == []
    assert metadata[0]['record_kind'] == 'offline_lifecycle_diagnostic'
    assert metadata[0]['operations_admitted'] == 0
    assert 'mutation_sent' not in source
    assert publication.snapshot_source(source) == run['before'] == run['after']
    assert (path.read_bytes(), source_path.read_bytes()) == raw


@pytest.mark.parametrize('fault', ['schema', 'phase', 'incomplete', 'failed', 'input', 'qualification',
    'actor', 'missing_check', 'extra_check', 'false_check', 'truthy_check', 'after_only',
    'partial_snapshot', 'online_snapshot', 'actor_snapshot', 'borrowed_after', 'runtime', 'chronology', 'digest'])
def test_revive_parked_preflight_refuses_other_authority_or_arbitrary_after(diagnostic, fault):
    directory, path, run, source_path, source = revive_parked_diagnostic(diagnostic)
    if fault == 'schema': source['schema'] = 'unknown_parked_source'
    elif fault == 'phase': source['phase'] = 'unknown_parked_boundary'
    elif fault == 'incomplete': source['completed'] = False
    elif fault == 'failed': source['failure'] = 'RuntimeError: retained failure'
    elif fault == 'input': source['input_sent'] = True
    elif fault == 'qualification': source['qualification_added'] = True
    elif fault == 'actor': source['actor']['guid'] = run['actor']['guid'] = 6
    elif fault == 'missing_check': source['checks'].pop('both_pets_restored')
    elif fault == 'extra_check': source['checks']['unrelated_success'] = True
    elif fault == 'false_check': source['checks']['all_six_offline'] = False
    elif fault == 'truthy_check': source['checks']['all_six_offline'] = 1
    elif fault == 'after_only': source['after'] = source.pop('all_offline_snapshot')
    elif fault == 'partial_snapshot': source['all_offline_snapshot'].pop('1')
    elif fault == 'online_snapshot': source['all_offline_snapshot']['6']['native']['online'] = 1
    elif fault == 'actor_snapshot': source['all_offline_snapshot']['1']['native']['guid'] = 2
    elif fault == 'borrowed_after':
        source['after'] = deepcopy(run['before'])
        source['all_offline_snapshot']['1']['saved']['unrelated'] = [1]
    elif fault == 'runtime': source['runtime']['worldserver']['pid'] = 99
    elif fault == 'chronology': source['finished_at'] = run['started_at'] + 1
    rewrite(source_path, source)
    if fault != 'digest':
        run['source']['sha256'] = publication.lab.sha256(source_path)
    else:
        run['source']['sha256'] = '0' * 64
    rewrite(path, run)
    with pytest.raises((RuntimeError, KeyError)):
        publication.checkpoint_runs([(path, run)], directory)


@pytest.mark.parametrize('fault', ['unknown_schema', 'unknown_phase', 'missing_checks', 'false_check', 'truthy_check',
    'cases', 'controller', 'revision', 'input', 'mutation', 'qualification', 'open',
    'nonfinite', 'backward', 'source_hash', 'outside_source', 'changed_state', 'partial_snapshot', 'wrong_prerequisite'])
def test_invalid_diagnostic_never_gets_missing_trial_field_exemption(diagnostic, fault):
    directory, _, path, run = diagnostic
    if fault == 'unknown_schema': run['schema'] = 'unknown_diagnostic'
    elif fault == 'unknown_phase': run['phase'] = 'hunter_learn_unknown'
    elif fault == 'missing_checks': run['checks'].pop(next(iter(run['checks'])))
    elif fault == 'false_check': run['checks']['source_bound'] = False
    elif fault == 'truthy_check': run['checks']['source_bound'] = 1
    elif fault in ('cases', 'controller', 'revision'): run[fault] = [] if fault == 'cases' else 'fake'
    elif fault == 'input': run['input_sent'] = True
    elif fault == 'mutation': run['mutation_sent'] = True
    elif fault == 'qualification': run['qualification_added'] = True
    elif fault == 'open': run.pop('finished_at')
    elif fault == 'nonfinite': run['finished_at'] = float('inf')
    elif fault == 'backward': run['finished_at'] = run['started_at'] - 1
    elif fault == 'source_hash': run['source']['sha256'] = '0' * 64
    elif fault == 'outside_source': run['source']['path'] = str(directory.parent.parent / 'foreign.json')
    elif fault == 'changed_state': run['after']['6']['native']['money'] += 1
    elif fault == 'partial_snapshot': run['before'].pop('1'); run['after'].pop('1')
    else: run['prerequisite_fingerprint']['relations']['learn'] = [[1462, 999]]
    rewrite(path, run)
    with pytest.raises((RuntimeError, KeyError)):
        publication.checkpoint_runs([(path, run)], directory)


@pytest.mark.parametrize('phase,mutation', [
    ('hunter_learn_rest_precision_started', False),
    ('hunter_learn_prerequisites_started', False),
    ('hunter_learn_offline_cleanup_started', True),
    ('hunter_learn_creator_normalization_started', True),
])
def test_failed_offline_attempt_is_retained_only_as_excluded_diagnostic(diagnostic, phase, mutation):
    directory, _, path, original_run = diagnostic
    run = {key: deepcopy(original_run[key]) for key in ('schema', 'started_at', 'finished_at', 'input_sent',
        'qualification_added', 'sources', 'before', 'actor', 'runtime')}
    run.update(phase=phase, completed=False, failure='RuntimeError: source guard failed; transaction rolled back',
        mutation_sent=mutation)
    rewrite(path, run); raw = path.read_bytes()
    cases, metadata, trials = publication.checkpoint_runs([(path, run)], directory)
    assert cases == trials == [] and all(v == 0 for v in choice_counts(trials).values())
    row = metadata[0]
    assert row['record_kind'] == 'excluded_diagnostic_failure' and row['completed'] is False
    assert row['failure'] == run['failure'] and row['mutation_sent'] is mutation
    assert row['operations_admitted'] == 0 and row['qualification_added'] is False
    assert not {'controller', 'model', 'revision', 'cases', 'checks'} & set(row)
    assert row['receipt_sha256'] == publication.lab.sha256(path) and path.read_bytes() == raw


def test_failed_diagnostic_retains_actual_partial_checks_without_fabrication(diagnostic):
    directory, _, path, run = diagnostic
    run.update(completed=False, failure='RuntimeError: one check failed', checks={'source_bound': False})
    rewrite(path, run)
    metadata = publication.checkpoint_runs([(path, run)], directory)[1][0]
    assert metadata['checks'] == {'source_bound': False} and metadata['operations_admitted'] == 0


@pytest.mark.parametrize('fault', ['unknown_schema', 'unknown_phase', 'missing_failure', 'empty_failure',
    'missing_finish', 'nonfinite', 'backward', 'input', 'qualification', 'source_hash', 'foreign_source', 'fake_model'])
def test_failed_diagnostic_exclusion_requires_owned_closed_attributable_attempt(diagnostic, fault):
    directory, _, path, run = diagnostic
    run.update(phase='hunter_learn_prerequisites_started', completed=False, failure='RuntimeError: failed')
    run.pop('after'); run.pop('checks'); run.pop('prerequisite_fingerprint')
    if fault == 'unknown_schema': run['schema'] = 'unknown_failed_diagnostic'
    elif fault == 'unknown_phase': run['phase'] = 'hunter_learn_unknown_started'
    elif fault == 'missing_failure': run.pop('failure')
    elif fault == 'empty_failure': run['failure'] = ' '
    elif fault == 'missing_finish': run.pop('finished_at')
    elif fault == 'nonfinite': run['finished_at'] = float('inf')
    elif fault == 'backward': run['finished_at'] = run['started_at'] - 1
    elif fault == 'input': run['input_sent'] = True
    elif fault == 'qualification': run['qualification_added'] = True
    elif fault == 'source_hash': run['source']['sha256'] = '0' * 64
    elif fault == 'foreign_source': run['source']['path'] = str(directory.parent.parent / 'foreign.json')
    else: run['model'] = 'invented'
    rewrite(path, run)
    with pytest.raises((RuntimeError, KeyError)):
        publication.checkpoint_runs([(path, run)], directory)


def test_precision_validates_pinned_formula_and_exact_float_bits(diagnostic):
    directory, _, path, run = diagnostic
    run.pop('prerequisite_fingerprint')
    run.update(phase='hunter_learn_rest_precision_complete', query=preservation.PRECISION_QUERY,
        row={**{k: run['before']['6']['native'][k] for k in ('guid', 'account', 'name', 'class', 'level',
            'xp', 'online', 'rest_bonus', 'logout_time', 'is_logout_resting')},
            'exact_rest_bonus': 100.0, 'exact_rest_bonus_float32_bits': struct.pack('<f', 100.0).hex()},
        checks=dict.fromkeys(publication.PRECISION_CHECKS, True), rest_sources={
            'rate': 1, 'config_source': {'path': str(publication.lab.ROOT / 'config/worldserver.conf'),
                'sha256': evidence.REST_CONFIG_SHA256},
            'native_formula_source': {'path': str(publication.lab.REPO / evidence.FORMULA_SOURCE),
                'sha256': evidence.REST_FORMULA_SHA256}, 'formula_snippets': evidence.FORMULA_SNIPPETS,
            'native_float_storage_sources': [{'path': str(publication.lab.REPO / p), 'sha256': digest}
                for p, digest in evidence.FLOAT_SOURCES.items()]})
    rewrite(path, run)
    assert publication.checkpoint_runs([(path, run)], directory)[2] == []
    run['row']['exact_rest_bonus_float32_bits'] = '00000000'
    rewrite(path, run)
    with pytest.raises(RuntimeError): publication.checkpoint_runs([(path, run)], directory)


def test_creator_diagnostic_preserves_exact_source_proven_noop(batch):
    directory, put = batch
    before = offline()
    preparation = put('preparation', {**trial('await_owned_class_lobby_review'), 'learn_offline_baseline': before})
    entry = put('entry', trial('owned_class_entered', 12, 13))
    park = put('park', {**trial('await_original_selection_review', 14, 15), 'all_offline_snapshot': before,
        'entry_source': entry, 'rest_baseline_source': preparation, 'native_pet_reload': {
            'owner': 6, 'pet_number': 16, 'created_by_spell': 13481, 'health': 278,
            'native_reload_source_verified': True}})
    exact = put('exact', {**trial('hunter_learn_rest_precision_complete', 16, 17), 'source': park, 'after': before})
    run = {'schema': publication.LIFECYCLE_SCHEMA, 'phase': 'hunter_learn_creator_normalized',
        'started_at': 18, 'finished_at': 19, 'completed': True, 'failure': None,
        'input_sent': False, 'mutation_sent': False, 'qualification_added': False,
        'sources': [preparation, park, exact], 'source': park, 'fixture_source': preparation, 'precision_source': exact,
        'entry_source': entry, 'rest_baseline_source': preparation, 'before': before, 'after': deepcopy(before),
        'expected_after': deepcopy(before), 'actor': {'guid': 6}, 'runtime': trial('unused')['runtime'],
        'native_rest_accrual_preserved': {}, 'normalized_columns': [],
        'checks': dict.fromkeys(publication.NORMALIZE_CHECKS, True)}
    path = Path(put('normalize', run)['path'])
    assert publication.checkpoint_runs([(path, run)], directory)[0] == []
    run['mutation_sent'] = True; rewrite(path, run)
    with pytest.raises(RuntimeError): publication.checkpoint_runs([(path, run)], directory)


@pytest.mark.parametrize('fault', [None, 'wrong_refund', 'extra_spell', 'protected_actor', 'mutation_flag'])
def test_cleanup_only_admits_exact_offline_row_removal_and_refund(batch, fault):
    directory, put = batch
    baseline = offline(); before = deepcopy(baseline)
    before['6']['native']['money'] -= contract.PRICE
    before['6']['saved']['spells'] = sorted(contract.BASE_SPELLS + [[1462, 1, 0]])
    preparation = put('preparation', {**trial('await_owned_class_lobby_review'), 'learn_offline_baseline': baseline})
    purchase = put('purchase', trial('hunter_learn_transition_complete', 12, 13))
    restoration = put('restoration', {**trial('hunter_learn_online_restored', 14, 15), 'purchase_source': purchase})
    park = put('park', {**trial('await_original_selection_review', 16, 17), 'source': restoration, 'all_offline_snapshot': before})
    exact = put('exact', {**trial('hunter_learn_rest_precision_complete', 18, 19), 'source': park, 'after': before})
    run = {'schema': publication.LIFECYCLE_SCHEMA, 'phase': 'hunter_learn_offline_cleaned',
        'started_at': 20, 'finished_at': 21, 'completed': True, 'failure': None,
        'input_sent': False, 'mutation_sent': True, 'qualification_added': False,
        'sources': [preparation, purchase, restoration, park, exact], 'preparation_source': preparation,
        'purchase_source': purchase, 'restoration_source': restoration, 'park_source': park,
        'precision_source': exact, 'creator_normalization_source': None, 'before': before, 'after': deepcopy(baseline),
        'expected_after': deepcopy(baseline), 'actor': {'guid': 6}, 'runtime': trial('unused')['runtime'],
        'native_rest_accrual_preserved': {}, 'refunded_copper': contract.PRICE, 'removed_spell': 1462,
        'checks': dict.fromkeys(publication.CLEAN_CHECKS, True)}
    if fault == 'wrong_refund': run['after']['6']['native']['money'] += 1
    elif fault == 'extra_spell': run['after']['6']['saved']['spells'].append([999, 1, 0])
    elif fault == 'protected_actor': run['after']['1']['native']['online'] = 1
    elif fault == 'mutation_flag': run['mutation_sent'] = False
    path = Path(put('cleaned', run)['path'])
    if fault:
        with pytest.raises(RuntimeError): publication.checkpoint_runs([(path, run)], directory)
    else:
        metadata = publication.checkpoint_runs([(path, run)], directory)[1][0]
        assert metadata['mutation_sent'] is True and metadata['operations_admitted'] == 0


def cleanup_case(batch, recovery):
    directory, put = batch
    baseline = offline(); before = deepcopy(baseline)
    before['6']['native']['money'] -= contract.PRICE
    before['6']['saved']['spells'] = sorted(contract.BASE_SPELLS + [[1462, 1, 0]])
    preparation = put('preparation', {**trial('await_owned_class_lobby_review'), 'learn_offline_baseline': baseline})
    purchase_value = trial('failed_train' if recovery else 'hunter_learn_transition_complete', 12, 13)
    if recovery: purchase_value.update(completed=False, failure='RuntimeError: paid Train capture failed')
    purchase = put('failed_train' if recovery else 'purchase', purchase_value)
    restore_value = {**trial('hunter_learn_recovery_restored' if recovery else 'hunter_learn_online_restored', 14, 15),
        'purchase_source': purchase}
    if recovery: restore_value.update(failed_source=purchase, **publication.RECOVERY_FLAGS)
    restoration = put('restoration', restore_value)
    park_value = {**trial('await_original_selection_review', 16, 17), 'source': restoration, 'all_offline_snapshot': before}
    if recovery: park_value.update(failed_source=purchase, **publication.RECOVERY_FLAGS)
    park = put('park', park_value)
    exact = put('exact', {**trial('hunter_learn_rest_precision_complete', 18, 19), 'source': park, 'after': before})
    roles = [preparation, restoration, park, exact, purchase] if recovery else [preparation, purchase, restoration, park, exact]
    run = {'schema': publication.LIFECYCLE_SCHEMA,
        'phase': publication.RECOVERY_PHASE if recovery else 'hunter_learn_offline_cleaned',
        'started_at': 20, 'finished_at': 21, 'completed': True, 'failure': None,
        'input_sent': False, 'mutation_sent': True, 'qualification_added': False, 'sources': roles,
        'preparation_source': preparation, 'restoration_source': restoration, 'park_source': park,
        'precision_source': exact, 'before': before, 'after': deepcopy(baseline), 'expected_after': deepcopy(baseline),
        'actor': {'guid': 6}, 'runtime': trial('unused')['runtime'], 'native_rest_accrual_preserved': {},
        'removed_spell': 1462, 'refunded_copper': contract.PRICE, 'checks': dict.fromkeys(publication.CLEAN_CHECKS, True),
        'commit_attempted': True, 'transaction_committed': True}
    if recovery: run.update(failed_source=purchase, **publication.RECOVERY_FLAGS)
    else: run.update(purchase_source=purchase, creator_normalization_source=None)
    return directory, put, run


def settlement_case(batch, recovery, acknowledged):
    directory, put, original_run = cleanup_case(batch, recovery)
    original_run.pop('after'); original_run.pop('checks')
    original_run.update(phase='hunter_learn_recovery_cleanup_started' if recovery else 'hunter_learn_offline_cleanup_started',
        completed=False, failure='RuntimeError: postcommit verification failed', transaction_committed=acknowledged)
    failed = put('failed_cleanup', original_run)
    run = deepcopy(original_run)
    run.update(phase=publication.RECOVERY_PHASE if recovery else 'hunter_learn_offline_cleaned',
        started_at=22, finished_at=23, completed=True, failure=None, after=deepcopy(original_run['expected_after']),
        checks=dict.fromkeys(publication.CLEAN_CHECKS, True), mutation_sent=False, commit_attempted=False,
        transaction_committed=True, settled_commit_only=True, original_mutation_sent=True, cleanup_failed_source=failed,
        sources=original_run['sources'] + [failed])
    return directory, put, run, original_run, Path(failed['path'])


@pytest.mark.parametrize('recovery', [False, True])
@pytest.mark.parametrize('acknowledged', [False, True])
def test_readonly_settlement_proves_prior_commit_without_replaying_mutation(batch, recovery, acknowledged):
    directory, put, run, original_run, failed_path = settlement_case(batch, recovery, acknowledged)
    path = Path(put('settlement', run)['path']); raw = failed_path.read_bytes()
    cases, metadata, trials = publication.checkpoint_runs([(failed_path, original_run), (path, run)], directory)
    assert cases == trials == [] and len(metadata) == 2
    assert metadata[0]['record_kind'] == 'excluded_diagnostic_failure'
    assert metadata[0]['transaction_committed'] is acknowledged and metadata[0]['mutation_sent'] is True
    assert metadata[1]['record_kind'] == ('excluded_diagnostic_recovery' if recovery else 'offline_lifecycle_diagnostic')
    assert metadata[1]['mutation_sent'] is False and metadata[1]['transaction_committed'] is True
    assert metadata[1]['commit_attempted'] is False and metadata[1]['settled_commit_only'] is True
    assert all(row['operations_admitted'] == 0 for row in metadata) and failed_path.read_bytes() == raw


@pytest.mark.parametrize('fault', ['new_mutation', 'new_commit_attempt', 'wrong_original_hash',
    'original_never_attempted', 'changed_declaration', 'lost_exclusion'])
def test_settlement_cannot_replay_or_change_failed_cleanup_declaration(batch, fault):
    directory, put, run, original_run, failed_path = settlement_case(batch, True, False)
    if fault == 'new_mutation': run['mutation_sent'] = True
    elif fault == 'new_commit_attempt': run['commit_attempted'] = True
    elif fault == 'wrong_original_hash': run['cleanup_failed_source']['sha256'] = '0' * 64
    elif fault == 'original_never_attempted':
        original_run['commit_attempted'] = False; rewrite(failed_path, original_run)
        run['cleanup_failed_source']['sha256'] = publication.lab.sha256(failed_path)
    elif fault == 'changed_declaration': run['native_rest_accrual_preserved'] = {'changed': True}
    else: run['purchase_qualified'] = True
    path = Path(put('settlement', run)['path'])
    with pytest.raises(RuntimeError): publication.checkpoint_runs([(path, run)], directory)


def test_successful_recovery_remains_excluded_without_trial_identity(batch):
    directory, put, run = cleanup_case(batch, True)
    path = Path(put('recovery', run)['path'])
    cases, metadata, trials = publication.checkpoint_runs([(path, run)], directory)
    assert cases == trials == [] and metadata[0]['record_kind'] == 'excluded_diagnostic_recovery'
    assert metadata[0]['failed_whole_excluded'] is True and metadata[0]['purchase_qualified'] is False
    assert metadata[0]['operations_admitted'] == 0
    assert not {'controller', 'model', 'revision', 'cases'} & set(metadata[0])


@pytest.mark.parametrize('phase', ['hunter_learn_recovery_cleanup_started',
    'hunter_learn_recovery_offline_cleaned', 'hunter_learn_offline_cleanup_settlement_started',
    'hunter_learn_recovery_cleanup_settlement_started'])
def test_recovery_and_settlement_failures_archive_only_as_excluded(batch, phase):
    recovery = 'recovery' in phase
    directory, put, run, _, _ = settlement_case(batch, recovery, False)
    run.update(phase=phase, completed=False, failure='RuntimeError: read-only settlement guard failed')
    run.pop('after'); run.pop('checks')
    path = Path(put('failed_settlement', run)['path'])
    row = publication.checkpoint_runs([(path, run)], directory)[1][0]
    assert row['record_kind'] == 'excluded_diagnostic_failure' and row['operations_admitted'] == 0
    assert row['mutation_sent'] is False and row['transaction_committed'] is True
    assert row['settled_commit_only'] is True and not {'controller', 'model', 'revision', 'cases'} & set(row)


@pytest.mark.parametrize('fault', [None, 'missing_check', 'source_hash', 'fake_revision'])
def test_distinct_closure_requires_28_checks_without_trial_choices(batch, fault):
    directory, put = batch
    source = put('source', trial('closed_source'))
    run = {'schema': evidence.SCHEMA, 'phase': evidence.PHASE, 'started_at': 20, 'finished_at': 21,
        'completed': True, 'failure': None, 'runtime': trial('unused')['runtime'], 'actor': {'guid': 2},
        'sources': {role: source for role in evidence.ROLES}, 'primary_stop_source': source,
        'all_offline_snapshot': offline(), 'checks': dict.fromkeys(evidence.CLOSURE_NAMES, True),
        'input_sent': False, 'mutation_sent': False, 'qualification_added': False, 'controller': 'code', 'model': None,
        'proof': {'operation': 'spellbook.learn_spell', 'owner': 6, 'spell': 1462,
            'native_purchases': 1, 'native_learn_events': 1, 'modern_learn_events': 1,
            'cleanup_removed_spell': 1462, 'cleanup_refund': contract.PRICE, 'restored_untrained_reentry': True,
            'all_six_offline': True, 'primary_stopped': True, 'qualification_added': False,
            'closure_checks': 28}}
    if fault == 'missing_check': run['checks'].pop(next(iter(run['checks'])))
    elif fault == 'source_hash': source['sha256'] = '0' * 64
    elif fault == 'fake_revision': run['revision'] = 'fake'
    path = Path(put('closure', run)['path'])
    if fault:
        with pytest.raises(RuntimeError): publication.checkpoint_runs([(path, run)], directory)
    else:
        cases, metadata, trials = publication.checkpoint_runs([(path, run)], directory)
        assert cases == trials == [] and metadata[0]['record_kind'] == 'semantic_closure'
        assert len(metadata[0]['checks']) == 28 and metadata[0]['operations_admitted'] == 0
        assert not {'controller', 'model', 'revision'} & set(metadata[0])


def authority(batch):
    directory, put = batch
    previous = [put('old_' + str(n), trial('accepted_' + str(n)), True) for n in range(4)]
    remote = put('remote', {'schema': 'client442_native_feedback_remote_review_v1'}, True, 'remote.json')
    primary = put('primary', trial('user_requested_primary_client_stopped'), True)
    checkpoint = put('checkpoint', {'cloud_verified': True}, True, 'checkpoint_receipt.json')
    restoration = put('original_restoration', trial('hunter_learn_scout_original_restored', 12, 13), True)
    resume = put('resume', {'schema': 'client442_hunter_learn_scout_resume_v1', 'sources': previous,
        'remote_source': remote, 'primary_stop_source': primary, 'checkpoint_source': checkpoint,
        'restoration_source': restoration}, True, 'resume.json')
    preparation = {**trial('await_owned_class_lobby_review', 14, 15), 'accepted_previous_sources': previous,
        'remote_source': remote, 'primary_stop_source': primary, 'sources': [resume, restoration]}
    return directory, put, preparation


def test_carry_preserves_exact_bytes_refs_and_private_digest_files(batch):
    directory, _, preparation = authority(batch)
    frozen = deepcopy(preparation)
    manifest = publication.carry(directory, preparation)
    assert len(manifest['sources']) == 9 and preparation == frozen
    for row in manifest['sources']:
        original_path, copy = Path(row['original_path']), Path(row['copy_path'])
        assert copy.name == row['sha256'] + '.json' and copy.read_bytes() == original_path.read_bytes()
        assert hashlib.sha256(copy.read_bytes()).hexdigest() == row['sha256']
        assert stat.S_IMODE(copy.stat().st_mode) == 0o600
    assert stat.S_IMODE((directory / 'ancestry').stat().st_mode) == 0o700
    assert list(directory.rglob('episode.json')) == []
    assert len(publication.carried(directory)) == 9
    with pytest.raises(RuntimeError, match='overwrite'): publication.carry(directory, preparation)


@pytest.mark.parametrize('fault', ['source_hash', 'outside_private', 'source_symlink', 'parent_symlink', 'resume_binding'])
def test_carry_refuses_unbound_or_nonprivate_authority(batch, fault):
    directory, _, preparation = authority(batch)
    ref = preparation['accepted_previous_sources'][0]
    path = Path(ref['path'])
    if fault == 'source_hash': ref['sha256'] = '0' * 64
    elif fault == 'outside_private': ref['path'] = str(directory.parent.parent / 'foreign.json')
    elif fault == 'source_symlink':
        raw = path.read_bytes(); path.unlink(); target = path.parent / 'other.json'; target.write_bytes(raw); path.symlink_to(target)
    elif fault == 'parent_symlink':
        new = path.parent.with_name('old_real'); path.parent.rename(new); path.parent.symlink_to(new, target_is_directory=True)
    else:
        path = Path(preparation['sources'][0]['path']); value = json.loads(path.read_text())
        value['sources'] = []; rewrite(path, value); preparation['sources'][0]['sha256'] = publication.lab.sha256(path)
    with pytest.raises(RuntimeError): publication.carry(directory, preparation)
    assert not (directory / 'ancestry').exists()


def test_carried_authority_verifies_without_live_original_sources(batch):
    directory, _, preparation = authority(batch)
    manifest = publication.carry(directory, preparation)
    for row in manifest['sources']: Path(row['original_path']).unlink()
    ancestry = publication.carried(directory)
    assert len(ancestry) == 9
    ref = preparation['sources'][0]
    assert publication.source_value(ref, directory, ancestry)['schema'] == 'client442_hunter_learn_scout_resume_v1'
    copy = Path(manifest['sources'][0]['copy_path']); copy.write_bytes(copy.read_bytes() + b' ')
    with pytest.raises(RuntimeError, match='digest'): publication.carried(directory)


@pytest.mark.parametrize('field', ['cases', 'controller', 'model', 'revision', 'failure'])
def test_ordinary_required_identity_and_cases_remain_required(batch, field):
    directory, put = batch
    run = trial('ordinary'); run.pop(field)
    path = Path(put('trial', run)['path'])
    with pytest.raises(KeyError): publication.checkpoint_runs([(path, run)], directory)


def test_generic_closed_failed_trial_keeps_actual_identity_failure_and_choices(batch):
    directory, put = batch
    run = trial('hunter_learn_transition_started')
    run.update(completed=False, failure='RuntimeError: actual ordinary Train failed',
        controller='code_diagnostic_ordinary_inputs', revision='actual-source-revision', cases=[
            {'status': 'failed', 'selected': 'Train', 'input_transport': {'actual': True}}])
    path = Path(put('failed_trial', run)['path']); raw = path.read_bytes()
    cases, metadata, trials = publication.checkpoint_runs([(path, run)], directory)
    assert cases == run['cases'] and trials == [run]
    assert metadata == [{'path': str(path.relative_to(publication.lab.ROOT)), 'completed': False,
        'failure': run['failure'], 'controller': run['controller'], 'model': None, 'revision': run['revision']}]
    assert choice_counts(trials)['code_choices_selected'] == choice_counts(trials)['code_choices_executed'] == 1
    assert path.read_bytes() == raw


def test_failed_fresh_observation_trial_keeps_failure_without_claiming_native_settlement(batch):
    directory, put = batch
    failed_train = trial('hunter_learn_transition_started')
    failed_train.update(completed=False, failure='RuntimeError: original Train failed')
    source = put('failed_train', failed_train)
    run = trial('hunter_learn_observation_settlement_started', 20, 21)
    run.update(completed=False, failure='KeyboardInterrupt: observation interrupted',
        observation_settlement_source=source, cases=[{'status': 'observed', 'selected': 'Open Spellbook',
            'after_frame': {'file': 'book.png'}}])
    path = Path(put('failed_observation', run)['path'])
    cases, metadata, trials = publication.checkpoint_runs([(path, run)], directory)
    assert cases == run['cases'] and trials == [run]
    assert metadata[0]['completed'] is False and metadata[0]['failure'] == run['failure']
    assert 'record_kind' not in metadata[0] and 'operations_admitted' not in metadata[0]
    assert choice_counts(trials)['code_choices_selected'] == 1


def observation_case(batch, monkeypatch):
    from tools.client_compatibility import hunter_learn_reconciliation as reconciliation
    from tools.client_compatibility import hunter_learn_trainer as trainer
    from tools.client_compatibility.world.tests.test_hunter_learn_reconciliation import navigation_case
    directory, put = batch
    runtime = {'worldserver': deepcopy(trainer.NATIVE), 'modern_world': {'pid': 2}, 'client': {'pid': 3}}
    preparation = put('preparation', trial('await_owned_class_lobby_review', 900, 901))
    entry = put('entry', trial('owned_class_entered', 1009, 1010))
    spawn_path = directory / 'trainer_spawn.json'
    publication.write_exclusive(spawn_path, SPAWN_BYTES)
    monkeypatch.setattr(trainer, 'SPAWN_SOURCE', {'path': str(spawn_path), 'sha256': publication.lab.sha256(spawn_path)})
    identity, trainer_packets = trainer_fixture(runtime=runtime, entry_ref=entry, with_facing=True)
    baseline = {'active_spec': 0, 'saved': {'spells': deepcopy(contract.BASE_SPELLS),
        'actions': deepcopy(reconciliation.ACTIONS)}, 'resources': {'money': contract.MONEY, 'health': 500}}
    public = {'active_spec': 1, 'power': 100, 'power_type': 2, 'frames': {'MainMenuBar': True}, 'actions': [
        {'button': 'ActionButton' + str(n), 'slot': n, 'visible': True, 'kind': None, 'id': None}
        for n in range(1, 13)]}
    for _, slot, action, kind in reconciliation.ACTIONS:
        public['actions'][slot].update(kind='flyout' if kind == 48 else 'spell', id=action)
    selected = {**trial('hunter_learn_lesson_selected', 1011.35, 1011.7), 'actor': {'guid': 6}, 'runtime': runtime,
        'controller': 'code_diagnostic_ordinary_inputs',
        'native_session': identity['native_session'], 'fixture_source': preparation, 'entry_source': entry,
        'baseline': baseline, 'login_known_spell_ids': [1515, 79682], 'book_layout_baseline': {}, 'pose_fixture': {},
        'trainer_identity': identity, 'native_catalog': identity['native_catalog'], 'frame': {'file': 'selected.png'},
        'custom_script_permission': 'blocked_by_user', 'softTargetInteract': {
            'original': '0', 'current_stock_disabled': '1', 'original_restored': False}}
    selected_ref = put('selected', selected)
    review_ref = put('review', {'reviewed': True, 'source': selected_ref}, filename='review.json')
    high = (8 << 58) | (1 << 42) | (((contract.TRAINER_GUID >> 32) & 0xfffff) << 6)
    modern = Writer().guid(contract.TRAINER_GUID & 0xffffffff, high).pack('ii', contract.TRAINER, contract.SPELL).finish()
    def packet(direction, name, body, at):
        return {'session': identity['native_session'], 'direction': direction, 'name': name, 'body': body.hex(), 'time': at}
    packets = [packet('from_client', 'CMSG_TRAINER_BUY_SPELL', modern, 1011.9),
        packet('to_native', 'CMSG_TRAINER_BUY_SPELL', struct.pack('<QII', contract.TRAINER_GUID, 40, 1462), 1012),
        packet('from_native', 'SMSG_LEARNED_SPELL', struct.pack('<II', 1462, 0), 1012.1),
        packet('to_client', 'SMSG_LEARNED_SPELLS', struct.pack('<IIBIB', 1, 0, 0, 1462, 0), 1012.2),
        packet('from_native', 'SMSG_TRAINER_BUY_SUCCEEDED', struct.pack('<QI', contract.TRAINER_GUID, 1462), 1012.3)]
    before = {'player': 'Harnesshunt', 'guid': 'Player-1-00000006', 'level': 10,
        'world_position': [-9460, 114, 58], 'player_stats': {'health': 209},
        'money': contract.MONEY, 'lua_errors': {}, 'blocked_actions': {},
        'trainer': {'service': {'name': contract.NAME, 'state': 'available', 'cost': contract.PRICE}}}
    original_case = {'id': 'spellbook.learn_spell.train1462', 'status': 'infrastructure_failure',
        'error': reconciliation.CASE_ERROR, 'selected': 'button_0', 'selection_source': 'code',
        'request': None, 'response': None, 'input_transport': [], 'time': 1011.85,
        'input': {'kind': 'click', 'value': [210, 491], 'hold': .15,
            'description': 'Click visible Button Train. Row: Benjamin Foxworthy.'},
        'before': before, 'after': {**before, 'money': contract.MONEY - contract.PRICE},
        'after_frame': {'movement': {'health_percent': 100, 'dead': False, 'in_combat': False, 'speed': 0}}}
    saved = {**baseline['saved'], 'spells': sorted(contract.BASE_SPELLS + [[1462, 1, 0]])}
    resources = {**baseline['resources'], 'money': contract.MONEY - contract.PRICE}
    failed = {**deepcopy(selected), 'phase': 'hunter_learn_purchase_started', 'started_at': 1011.75,
        'finished_at': 1013.1, 'completed': False, 'failure': reconciliation.FAILURE, 'source': selected_ref,
        'purchase_source': selected_ref, 'screen_review': {**review_ref, 'frame': selected['frame']},
        'purchase_started_at': 1011.8, 'purchase_finished_at': 1013, 'trainer_identity_checked_at': 1011.8,
        'purchase_packets': packets, 'purchase_input_sent': True, 'input_sent': True, 'purchase_checks': None,
        'qualification_added': False, 'cases': [original_case], 'after_saved': saved, 'after_resources': resources,
        'protected_checks': reconciliation.PROTECTED, 'public_actionbar_after': public}
    failed_ref = put('failed_train', failed)
    monkeypatch.setattr(reconciliation, 'FAILED_SOURCE', failed_ref)
    state = {**deepcopy(original_case['after']), 'target': identity['target']}
    frame = {'file': 'fresh_observation.png', 'movement': {
        'health_percent': 100, 'dead': False, 'in_combat': False, 'speed': 0}}
    proof = reconciliation.observation_reconciliation(failed, failed_ref, selected, selected_ref, saved=saved,
        resources=resources, protected_checks=reconciliation.PROTECTED, public=public, state=state,
        frame=frame, rows=[*trainer_packets, *packets], observed_until=1021)
    navigation = navigation_case(time=1020.5)
    navigation.update(selected='Beast Mastery', selection_source='code', request=None, response=None,
        input_transport=[], after_frame={'file': 'learned.png'})
    run = {**trial('hunter_learn_transition_complete', 1020, 1022),
        'controller': 'code_diagnostic_ordinary_inputs',
        'custom_script_permission': failed['custom_script_permission'], 'softTargetInteract': failed['softTargetInteract'],
        **{key: deepcopy(failed[key]) for key in reconciliation.FACT_FIELDS},
        'observation_settlement_source': failed_ref, 'original_purchase_interval': [1011.8, 1013],
        'original_case': deepcopy(original_case), 'original_purchase_input_sent': True, 'input_sent': True,
        'gameplay_input_sent': False,
        'observation_only': True, 'mutation_sent': False,
        'purchase_input_sent': False, 'train_input_replayed': False, 'book_navigation_input_sent': True,
        'qualification_added': False, 'purchase_started_at': 1011.8, 'purchase_finished_at': 1013,
        'purchase_packets': packets, 'after_saved': saved, 'after_resources': resources,
        'protected_checks': reconciliation.PROTECTED, 'public_actionbar_after': public, 'state': state, 'frame': frame,
        'observation_reconciliation': proof, 'purchase_checks': proof['purchase_checks'],
        'auto_action_placement': None, 'actionbar_restoration_required': False,
        'cases': [navigation]}
    return directory, put, run, failed, Path(failed_ref['path'])


def test_native_outcome_observation_settlement_preserves_original_train_and_new_navigation_metrics(batch, monkeypatch):
    directory, put, run, failed, failed_path = observation_case(batch, monkeypatch)
    path = Path(put('observation', run)['path']); raw_failed = failed_path.read_bytes(); raw_new = path.read_bytes()
    cases, metadata, trials = publication.checkpoint_runs([(failed_path, failed), (path, run)], directory)
    assert cases == failed['cases'] + run['cases'] and trials == [failed, run]
    assert metadata[0] == {'path': str(failed_path.relative_to(publication.lab.ROOT)), 'completed': False,
        'failure': failed['failure'], 'controller': failed['controller'], 'model': None, 'revision': None}
    new = metadata[1]
    assert new['record_kind'] == 'native_outcome_observation_settlement' and new['operations_admitted'] == 0
    assert new['observation_settlement_source'] == run['observation_settlement_source']
    assert new['original_purchase_interval'] == [1011.8, 1013] and new['started_at'] == 1020
    assert new['input_sent'] is True and new['gameplay_input_sent'] is False
    assert new['purchase_input_sent'] is False and new['train_input_replayed'] is False
    assert new['observation_only'] is True and new['mutation_sent'] is False and new['book_navigation_input_sent'] is True
    assert new['controller'] == run['controller'] and new['model'] is run['model'] and new['revision'] is None
    assert choice_counts(trials)['code_choices_selected'] == choice_counts(trials)['code_choices_executed'] == 2
    assert sum(case['id'] == 'spellbook.learn_spell.train1462' for case in cases) == 1
    assert failed_path.read_bytes() == raw_failed and path.read_bytes() == raw_new


@pytest.mark.parametrize('fault', ['source_hash', 'foreign_source', 'new_train_case', 'replayed_train',
    'old_collection_clock', 'altered_original_case', 'altered_proof', 'wrong_schema', 'missing_marker',
    'missing_cases', 'missing_controller', 'missing_model', 'missing_revision', 'mutation', 'not_observation',
    'gameplay_input', 'missing_gameplay_flag', 'wrong_observer_actor', 'wrong_navigation', 'navigation_clock'])
def test_observation_settlement_requires_pinned_paid_proof_and_actual_trial_identity(batch, monkeypatch, fault):
    directory, put, run, _, _ = observation_case(batch, monkeypatch)
    if fault == 'source_hash': run['observation_settlement_source']['sha256'] = '0' * 64
    elif fault == 'foreign_source': run['observation_settlement_source']['path'] = str(directory.parent / 'foreign/episode.json')
    elif fault == 'new_train_case': run['cases'].append(deepcopy(run['original_case']))
    elif fault == 'replayed_train': run['purchase_input_sent'] = True
    elif fault == 'old_collection_clock': run['started_at'] = 1011.75
    elif fault == 'altered_original_case': run['original_case']['status'] = 'spellbook_learning_pass'
    elif fault == 'altered_proof': run['observation_reconciliation']['purchase_checks']['ordinary_train'] = False
    elif fault == 'wrong_schema': run['schema'] = 'unknown_observation_settlement'
    elif fault == 'missing_marker': run.pop('original_purchase_interval')
    elif fault == 'mutation': run['mutation_sent'] = True
    elif fault == 'not_observation': run['observation_only'] = False
    elif fault == 'gameplay_input': run['gameplay_input_sent'] = True
    elif fault == 'missing_gameplay_flag': run.pop('gameplay_input_sent')
    elif fault == 'wrong_observer_actor': run['state']['player'] = 'Harnesstwo'
    elif fault == 'wrong_navigation': run['cases'][0]['id'] = 'unrecognized.caption'
    elif fault == 'navigation_clock': run['cases'][0]['time'] = 1012
    else: run.pop(fault.removeprefix('missing_'))
    path = Path(put('observation', run)['path'])
    with pytest.raises((RuntimeError, KeyError)):
        publication.checkpoint_runs([(path, run)], directory)


def test_checkpoint_wrapper_restores_original_on_success_and_failure(diagnostic, monkeypatch):
    directory, put, path, run = diagnostic
    ordinary = trial('ordinary', 15, 16)
    ordinary['cases'] = [{'status': 'observed', 'selected': 'one', 'after_frame': {'file': 'screen.png'}}]
    ordinary_path = Path(put('ordinary', ordinary)['path'])
    classifier = original.checkpoint_runs
    order = []
    def fake_checkpoint(batch, name):
        order.append((batch, name))
        cases, metadata, trials = original.checkpoint_runs([(path, run), (ordinary_path, ordinary)], batch)
        assert len(cases) == 1 and trials == [ordinary]
        assert choice_counts(trials)['code_choices_selected'] == 1
        assert metadata[0]['operations_admitted'] == 0
        assert metadata[1] == {'path': str(ordinary_path.relative_to(publication.lab.ROOT)),
            'completed': True, 'failure': None, 'controller': 'code', 'model': None, 'revision': None}
        return 'published fixture'
    monkeypatch.setattr(original, 'checkpoint', fake_checkpoint)
    assert publication.checkpoint(directory, 'closed_learning') == 'published fixture'
    assert original.checkpoint_runs is classifier and order == [(directory, 'closed_learning')]
    def fail(*args):
        assert original.checkpoint_runs is not classifier
        raise RuntimeError('fixture publisher failed')
    monkeypatch.setattr(original, 'checkpoint', fail)
    with pytest.raises(RuntimeError, match='publisher failed'): publication.checkpoint(directory, 'failed')
    assert original.checkpoint_runs is classifier


@pytest.mark.parametrize('outcome', ['success', 'exception', 'interrupt'])
def test_learning_publisher_retains_trainer_movement_only_in_scoped_call(batch, monkeypatch, outcome):
    directory, _ = batch
    previous_names = original.SAFE_BODY_NAMES
    previous_values = frozenset(previous_names)
    previous_classifier = original.checkpoint_runs
    trainer_names = {'SMSG_ON_MONSTER_MOVE_TRANSPORT', 'SMSG_MOVE_UPDATE_TELEPORT',
        'MSG_MOVE_TELEPORT', 'SMSG_MOVE_TELEPORT', 'CMSG_MOVE_TELEPORT_ACK', 'MSG_MOVE_TELEPORT_ACK',
        'SMSG_TRANSFER_PENDING', 'SMSG_NEW_WORLD', 'CMSG_WORLD_PORT_RESPONSE', 'MSG_MOVE_WORLDPORT_ACK'}
    calls = []
    def fake_checkpoint(selected, name):
        calls.append((selected, name))
        assert original.checkpoint_runs is not previous_classifier
        assert original.SAFE_BODY_NAMES == previous_values | trainer_names
        assert trainer_names <= original.SAFE_BODY_NAMES
        assert 'SMSG_ON_MONSTER_MOVE' in original.SAFE_BODY_NAMES
        assert frozenset(previous_names) == previous_values
        if outcome == 'exception': raise RuntimeError('fixture publication failed')
        if outcome == 'interrupt': raise KeyboardInterrupt('fixture publication interrupted')
        return 'fixture publication complete'
    monkeypatch.setattr(original, 'checkpoint', fake_checkpoint)
    if outcome == 'success':
        assert publication.checkpoint(directory, 'trainer_identity') == 'fixture publication complete'
    else:
        error = RuntimeError if outcome == 'exception' else KeyboardInterrupt
        with pytest.raises(error): publication.checkpoint(directory, 'trainer_identity')
    assert calls == [(directory, 'trainer_identity')]
    assert original.SAFE_BODY_NAMES is previous_names
    assert frozenset(original.SAFE_BODY_NAMES) == previous_values
    assert original.checkpoint_runs is previous_classifier


def test_publication_import_has_no_ui_protobuf_or_publishing_dependency():
    code = ('import sys; from tools.client_compatibility import checkpoint_hunter_learn; '
        'assert not any(n.startswith(("PIL", "google.protobuf", "dvclive")) or '
        'n.endswith(("interaction_trial", "interaction_hunter_learn_cleanup")) for n in sys.modules)')
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_carried_legacy_precision_keeps_original_validator_and_episode_count(diagnostic_batch, monkeypatch):
    root, _, previous, precision_path, precision = diagnostic_batch
    directory = root / 'evidence' / 'new_learning'; directory.mkdir(mode=0o700)
    def put(name, value, filename='episode.json'):
        path = previous / name / filename
        publication.lab.private_write(path, json.dumps(value, indent=2) + '\n')
        return {'path': str(path), 'sha256': publication.lab.sha256(path)}
    old = [{'path': str(precision_path), 'sha256': publication.lab.sha256(precision_path)}, *precision['sources'][:3]]
    remote = put('carry_remote', {}, 'remote.json')
    primary = put('carry_primary', trial('user_requested_primary_client_stopped'))
    checkpoint = put('carry_checkpoint', {}, 'checkpoint_receipt.json')
    restoration = put('carry_restoration', trial('hunter_learn_scout_original_restored'))
    resume = put('carry_resume', {'schema': 'client442_hunter_learn_scout_resume_v1', 'sources': old,
        'remote_source': remote, 'primary_stop_source': primary, 'checkpoint_source': checkpoint,
        'restoration_source': restoration}, 'resume.json')
    preparation = {**trial('await_owned_class_lobby_review'), 'accepted_previous_sources': old,
        'remote_source': remote, 'primary_stop_source': primary, 'sources': [resume, restoration]}
    manifest = publication.carry(directory, preparation)
    copy = next(Path(row['copy_path']) for row in manifest['sources'] if row['original_path'] == str(precision_path))
    assert copy.name != 'episode.json' and copy.read_bytes() == precision_path.read_bytes()
    current = trial('new_ordinary')
    current_path = directory / 'current' / 'episode.json'; rewrite(current_path, current)
    previous_classifier = original.checkpoint_runs
    def fake_checkpoint(batch, name):
        episodes = [(p, json.loads(p.read_text())) for p in batch.rglob('episode.json')]
        assert len(episodes) == 1
        assert original.checkpoint_runs(episodes, batch)[2] == [current]
    monkeypatch.setattr(original, 'checkpoint', fake_checkpoint)
    publication.checkpoint(directory, 'fixture')
    assert original.checkpoint_runs is previous_classifier
    precision['checks']['exact_float32'] = False; rewrite(precision_path, precision)
    with pytest.raises(RuntimeError): publication.carried(directory)
