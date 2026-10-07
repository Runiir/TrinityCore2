"""Real caller references, remote manifests and shutdown semantics gate entry."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from tools.client_compatibility import item_actionbar_sources as s
from tools.client_compatibility.world.tests.test_item_actionbar_preservation import snapshot


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')
    return path


def fixture(tmp_path):
    root, repo = tmp_path / 'private', tmp_path / 'repo'
    evidence = root / 'evidence' / 'client_interactions_20990101_ui170'
    paths = {k: evidence / k / 'episode.json' for k in ('closure', 'pause', 'primary_stop')}
    paths.update(remote=evidence / 'actual_remote_review.json', checkpoint=evidence / 'checkpoint_receipt.json')
    native = snapshot()
    actor = {'guid': 2, 'name': 'Harnesstwo', 'account_id': 2, 'actor': 'scout'}
    runtime = {k: {'pid': i, 'start_ticks': str(100 + i)} for i, k in enumerate(('worldserver', 'modern_world', 'client'), 1)}
    stop = {'phase': 'user_requested_primary_client_stopped', 'started_at': 1, 'finished_at': 2,
        'completed': True, 'failure': None, 'checks': {str(i): True for i in range(8)},
        'before': native['1'], 'after': native['1']}
    write(paths['primary_stop'], stop)
    proof = {'operation': 'spellbook.learn_spell', 'owner': 6, 'spell': 1462, 'trainer': 40,
        'native_purchases': 1, 'native_learn_events': 1, 'modern_learn_events': 1, 'cleanup_removed_spell': 1462,
        'cleanup_refund': 646, 'restored_untrained_reentry': True, 'all_six_offline': True,
        'primary_stopped': True, 'qualification_added': False, 'closure_checks': 28}
    closure = {'schema': 'client442_owned_hunter_learn_closure_v1', 'phase': 'hunter_learn_parked_boundary',
        'completed': True, 'failure': None, 'started_at': 10, 'finished_at': 11, 'actor': actor, 'runtime': runtime,
        'input_sent': False, 'mutation_sent': False, 'qualification_added': False,
        'checks': dict.fromkeys(s.CLOSURE_NAMES, True), 'all_offline_snapshot': native,
        'proof': proof, 'sources': {k: {'path': str((evidence / k / 'episode.json').resolve()), 'sha256': 'a' * 64} for k in s.ROLES},
        'primary_stop_source': s.bound(paths['primary_stop'])}
    write(paths['closure'], closure)
    pause = {'phase': 'hunter_learn_scout_resource_paused', 'completed': True, 'failure': None,
        'started_at': 12, 'finished_at': 13, 'actor': actor, 'runtime': runtime, 'source': s.bound(paths['closure']),
        'primary_stop_source': s.bound(paths['primary_stop']), 'before': native, 'after': native,
        'input_sent': False, 'qualification_added': False, 'action': 'stop_parked_scout_after_learning_restoration',
        'controller': 'code', 'model': None, 'custom_script_permission': 'blocked_by_user',
        'checks': dict.fromkeys(s.PAUSE_NAMES, True), 'game_before': {'pid': 40, 'start_ticks': '1000'}}
    write(paths['pause'], pause)
    archive = 'artifacts/client_harness/442_interactions_20990101_170.tar.gz'
    cp = {'file': archive, 'bytes': 42, 'sha256': 'b' * 64, 'cloud_verified': True,
        'file_manifest': [{'path': str(paths[k].relative_to(root)), 'bytes': paths[k].stat().st_size,
            'sha256': s.bound(paths[k])['sha256']} for k in ('closure', 'pause')]}
    write(paths['checkpoint'], cp)
    remote = {'schema': 'client442_hunter_learn_remote_review_v1', 'reviewed_at': 14,
        'actual_remote_verified': True, 'complete_json_png_verified': True, 'qualification_added': False,
        'pointer': archive + '.dvc', 'bytes': 42, 'archive_sha256': 'b' * 64,
        'proof': {**proof, 'shutdown_checks': 8, 'both_owned_clients_stopped': True, 'actual_packet_journals_verified': True}}
    write(paths['remote'], remote)
    pointer = repo / (archive + '.dvc')
    pointer.parent.mkdir(parents=True)
    pointer.write_text('outs:\n- md5: ' + 'c' * 32 + '\n  size: 42\n  hash: md5\n  path: ' + Path(archive).name + '\n')
    values = {'closure': closure, 'pause': pause, 'remote': remote, 'checkpoint': cp, 'primary_stop': stop,
        'dvc_pointer': s.dvc_pointer(cp, remote, repo=repo)}
    return root, repo, paths, values


def call(root, repo, paths):
    return s.source_bundle(*(paths[k] for k in ('closure', 'pause', 'remote', 'checkpoint', 'primary_stop')), root=root, repo=repo)


def test_real_closed_caller_sources_and_portable_archive_values_bind_without_future_hash(tmp_path):
    root, repo, paths, values = fixture(tmp_path)
    result = call(root, repo, paths)
    refs = {k: s.bound(path) for k, path in paths.items()}
    assert result == s.validate_bundle(values, refs)
    assert result['predecessor'] == refs and result['origin_actor']['guid'] == 2
    assert result['runtime']['worldserver']['start_ticks'] == '101'
    assert result['pause']['game_before']['start_ticks'] == '1000'
    assert result['dvc_pointer']['source'] == s.bound(repo / values['remote']['pointer'])
    ready = {'phase': 'item_actionbar_scout_ready', 'completed': True, 'failure': None,
        'started_at': 15, 'finished_at': 16, 'actor': result['origin_actor'],
        'all_offline_snapshot': result['snapshot'], 'predecessor': result['predecessor']}
    assert s.prepared(ready) == ready


@pytest.mark.parametrize('fault', ['local_only', 'wrong_operation', 'wrong_spell', 'boolean_count',
    'missing_check', 'false_check', 'wrong_shutdown', 'boolean_shutdown', 'changed_snapshot',
    'wrong_runtime', 'wrong_primary', 'wrong_source', 'reverse_time', 'nan_time', 'bool_game_pid',
    'wrong_archive', 'wrong_dvc_index', 'duplicate_manifest', 'changed_source', 'wrong_size', 'changed_pointer'])
def test_dynamic_source_remote_manifest_and_shutdown_guards_refuse_drift(tmp_path, fault):
    root, repo, paths, values = fixture(tmp_path)
    if fault == 'local_only': values['remote']['actual_remote_verified'] = False
    elif fault == 'wrong_operation': values['remote']['proof']['operation'] = 'actionbars.page_next'
    elif fault == 'wrong_spell': values['remote']['proof']['spell'] = 1515
    elif fault == 'boolean_count': values['remote']['proof']['native_purchases'] = True
    elif fault == 'missing_check': values['closure']['checks'].pop(next(iter(s.CLOSURE_NAMES)))
    elif fault == 'false_check': values['pause']['checks']['origin_registration'] = False
    elif fault == 'wrong_shutdown': values['remote']['proof']['shutdown_checks'] = 7
    elif fault == 'boolean_shutdown': values['remote']['proof']['shutdown_checks'] = True
    elif fault == 'changed_snapshot': values['pause']['after'] = deepcopy(values['pause']['after']); values['pause']['after']['6']['pets'][0]['curhealth'] += 1
    elif fault == 'wrong_runtime': values['pause']['runtime'] = deepcopy(values['pause']['runtime']); values['pause']['runtime']['client']['pid'] += 1
    elif fault == 'wrong_primary': values['primary_stop']['after'] = {}
    elif fault == 'wrong_source': values['pause']['source']['sha256'] = 'd' * 64
    elif fault == 'reverse_time': values['pause']['started_at'] = 9
    elif fault == 'nan_time': values['closure']['finished_at'] = float('nan')
    elif fault == 'bool_game_pid': values['pause']['game_before']['pid'] = True
    elif fault == 'wrong_archive': values['checkpoint']['bytes'] += 1
    elif fault == 'wrong_dvc_index': values['remote']['pointer'] = values['remote']['pointer'].replace('_170.', '_169.')
    elif fault == 'duplicate_manifest': values['checkpoint']['file_manifest'].append(deepcopy(values['checkpoint']['file_manifest'][0]))
    elif fault == 'changed_source': values['closure']['new_field'] = True
    elif fault == 'wrong_size': values['checkpoint']['file_manifest'][0]['bytes'] += 1
    else: (repo / values['remote']['pointer']).write_text('outs: []\n')
    for role in paths:
        if role in values: write(paths[role], values[role])
    with pytest.raises(RuntimeError): call(root, repo, paths)


@pytest.mark.parametrize('fault', ['symlink', 'outside', 'completed_int', 'failure', 'unfinished', 'bool_time'])
def test_closed_private_sources_have_strict_success_and_no_symlink(tmp_path, fault):
    root = tmp_path / 'private'
    path = root / 'evidence' / 'unit' / 'episode.json'
    value = {'completed': True, 'failure': None, 'started_at': 1, 'finished_at': 2}
    if fault == 'completed_int': value['completed'] = 1
    elif fault == 'failure': value['failure'] = 'actual failure'
    elif fault == 'unfinished': value.pop('finished_at')
    elif fault == 'bool_time': value['started_at'] = True
    elif fault == 'outside': path = tmp_path / 'elsewhere' / 'episode.json'
    write(path, value)
    if fault == 'symlink':
        target = path.with_name('target.json'); path.rename(target); path.symlink_to(target)
    with pytest.raises(RuntimeError): s.closed(path, root=root)


def test_failed_source_authority_remains_immutable_and_never_successful(tmp_path):
    root = tmp_path / 'private'
    path = write(root / 'evidence' / 'failed' / 'episode.json', {'completed': False, 'failure': 'RuntimeError: failed drag',
        'started_at': 1, 'finished_at': 2, 'operations_admitted': 0})
    ref = s.bound(path)
    assert s.linked(ref, successful=False, root=root)['completed'] is False
    with pytest.raises(RuntimeError): s.linked(ref, root=root)
    write(path, {'completed': False, 'failure': 'changed', 'started_at': 1, 'finished_at': 2})
    with pytest.raises(RuntimeError): s.linked(ref, successful=False, root=root)


@pytest.mark.parametrize('location', ['game', 'worldserver', 'modern_world', 'client'])
@pytest.mark.parametrize('ticks', [101, True, '', '0101', '0'])
def test_process_start_ticks_require_preserved_canonical_positive_decimal_strings(tmp_path, location, ticks):
    _, _, paths, values = fixture(tmp_path)
    refs = {k: s.bound(path) for k, path in paths.items()}
    if location == 'game': values['pause']['game_before']['start_ticks'] = ticks
    else:
        values['closure']['runtime'][location]['start_ticks'] = ticks
        values['pause']['runtime'][location]['start_ticks'] = ticks
    with pytest.raises(RuntimeError): s.validate_bundle(values, refs)


@pytest.mark.parametrize('location', ['game', 'worldserver', 'modern_world', 'client'])
def test_process_pid_never_accepts_boolean_as_positive_integer(tmp_path, location):
    _, _, paths, values = fixture(tmp_path)
    refs = {k: s.bound(path) for k, path in paths.items()}
    if location == 'game': values['pause']['game_before']['pid'] = True
    else:
        values['closure']['runtime'][location]['pid'] = True
        values['pause']['runtime'][location]['pid'] = True
    with pytest.raises(RuntimeError): s.validate_bundle(values, refs)


def test_native_rest_sources_are_pinned_to_actual_config_formula_and_float_storage():
    result = s.rest_sources()
    assert result['xp_cap'] == 400 and result['rest_cap'] == 300 and result['rate'] == 1
    assert result['native_formula_source']['sha256'] == s.FORMULA_HASH
