"""A failed original login can be observed under a fully carried new code epoch."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from tools.client_compatibility import bag_swap_renewal as r
from tools.client_compatibility import bag_swap_contract as contract
from tools.client_compatibility import bag_swap_preservation as preservation
from tools.client_compatibility.bag_swap_login_sync import login_sync
from tools.client_compatibility.item_actionbar_sources import FORMULA, FORMULA_HASH, CONFIG_HASH, FORMULA_SNIPPETS, FLOAT_SOURCES
from tools.client_compatibility.world.tests.test_bag_swap_contract import inventory
from tools.client_compatibility.world.tests.test_bag_swap_login_sync import recorded
from tools.client_compatibility.world.tests.test_item_actionbar_preservation import snapshot, precision as precise


class Store:
    def __init__(self, root):
        self.root, self.data, self.digests = root, {}, {}

    def put(self, name, value):
        path = self.root / 'evidence' / name
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        ref = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
        self.data[ref['path']], self.digests[ref['path']] = deepcopy(value), ref['sha256']
        return ref

    def get(self, ref, successful=True):
        r.reference(ref)
        assert self.digests[ref['path']] == ref['sha256']
        value = self.data[ref['path']]
        if successful:
            assert value.get('completed') is True and value.get('failure') is None
        return value


def epoch(store, repo, commit, *, current=False):
    members = list(r.OLD_MEMBERS)
    if current:
        members = sorted(set(members) | set(r.SOURCE_FILES) | set(r.CURRENT_REQUIRED))
    refs, copies, raws = [], [], {}
    for index, member in enumerate(sorted(members)):
        raw = ((Path(__file__).resolve().parents[4] / member).read_bytes() if member == FORMULA else
            (commit + '\n' + member + '\n').encode())
        ref = {'path': str(repo / member), 'sha256': hashlib.sha256(raw).hexdigest()}
        refs.append(ref)
        copies.append(store.put(f'code/{commit}/{index:03d}.json', {'schema': r.CODE_SCHEMA,
            'code_commit': commit, 'original_path': ref['path'], 'sha256': ref['sha256'],
            'bytes': len(raw), 'raw_hex': raw.hex()}))
        raws[member] = raw
    return refs, copies, raws


def fixture(tmp_path):
    store, repo = Store(tmp_path / 'lab'), tmp_path / 'repo'
    old_refs, old_copies, old_raws = epoch(store, repo, r.C1_COMMIT)
    new_refs, new_copies, new_raws = epoch(store, repo, 'f' * 40, current=True)
    recorded_value = recorded()
    since, failed_until = recorded_value['since'], recorded_value['until']
    interval = {'since': since, 'until': failed_until - .5}
    sync = login_sync(recorded_value['rows'], recorded_value['events'], recorded_value['session'],
        interval['since'], interval['until'], recorded_value['baseline_pose'])
    baseline = snapshot()
    baseline['2']['inventory'] = inventory()
    native = baseline['2']['native']
    native.update(rest_bonus=52.7233, logout_time=1791416981)
    native.update(dict(zip(('position_x', 'position_y', 'position_z', 'orientation'), recorded_value['baseline_pose'])))
    actor = {'schema': 'client442_actor_v1', 'actor': 'scout', 'guid': 2, 'account_id': 2,
        'character_name': 'Harnesstwo', 'race': 1, 'class': 1, 'level': 1}
    runtime = {k: {'pid': i + 1, 'start_ticks': str(i + 10)}
        for i, k in enumerate(('worldserver', 'modern_world', 'client'))}
    authority = {k: store.put(k + '.json', {'completed': True, 'failure': None})
        for k in ('authority_source', 'runtime_authority_source')}
    predecessor = {k: store.put('old/' + k + '.json', {'completed': True, 'failure': None})
        for k in ('closure', 'remote', 'checkpoint', 'primary_stop')}
    def trial(phase, start, finish, **kwargs):
        return {'schema': 'client442_laya_interactions_v1', 'phase': phase, 'completed': True,
            'failure': None, 'started_at': start, 'finished_at': finish, 'actor': deepcopy(actor),
            'runtime': deepcopy(runtime), 'code_commit': r.C1_COMMIT, 'committed_sources': deepcopy(old_refs),
            'controller': 'code', 'model': None, 'revision': None, 'qualification_added': False,
            'custom_script_permission': 'blocked_by_user', 'softTargetInteract': deepcopy(r.SCRIPT_BOUNDARY),
            'observer_file_sha256': 'a' * 64, 'compatibility_addon_sha256': 'b' * 64,
            'input_sent': False, 'mutation_sent': False, 'cases': [], 'cleanup': [], **kwargs}
    resume_ref = store.put('resume.json', {**trial('bags_swap_scout_launched', since - 20, since - 19),
        'schema': 'client442_bag_swap_scout_resume_v1'})
    ready = trial('bags_swap_scout_ready', since - 18, since - 12, **authority, predecessor=predecessor,
        predecessor_dvc_pointer={'source': predecessor['checkpoint']}, all_offline_snapshot=baseline,
        native_session=recorded_value['session'], resume_source=resume_ref)
    ready_ref = store.put('ready/episode.json', ready)
    binding = {'rate': 1, 'xp_cap': 400, 'rest_cap': 300, 'wilderness_bubble': .031,
        'config_source': {'path': str(store.root / 'config/worldserver.conf'), 'sha256': CONFIG_HASH},
        'native_formula_source': {'path': str(repo / FORMULA), 'sha256': FORMULA_HASH},
        'formula_snippets': list(FORMULA_SNIPPETS), 'native_float_storage_sources':
            [{'path': str(repo / p), 'sha256': sha} for p, sha in FLOAT_SOURCES.items()]}
    precision = trial('bags_swap_rest_precision_complete', since - 11, since - 9, source=ready_ref,
        before=baseline, after=baseline, query=preservation.PRECISION_QUERY,
        row=precise(native, 52.72333526611328), rest_sources=binding,
        checks=dict.fromkeys(('all_six_offline', 'all_saved_state_unchanged', 'original_identity',
            'snapshot_rest_matches', 'exact_float32'), True))
    precision_ref = store.put('precision/episode.json', precision)
    failed = trial('bags_swap_entry_started', since, failed_until, completed=False, failure=r.FAILURE,
        input_sent=True, entry_input_started_at=since + .1, entry_input_finished_at=interval['until'],
        preparation_source=ready_ref, precision_source=precision_ref, predecessor=predecessor,
        native_session=recorded_value['session'], native_before_entry=native,
        all_offline_snapshot=baseline, raw_entry_packets=recorded_value['rows'])
    failed_ref = store.put('failed/episode.json', failed)
    current = deepcopy(baseline)
    second = int(sync['login_packets'][1]['time'])
    exact_after, text = preservation.native_rest(52.72333526611328, second - native['logout_time'])
    current['2']['native'].update(online=1, rest_bonus=text, totaltime=native['totaltime'] + 5,
        leveltime=native['leveltime'] + 5)
    owner = contract.native_replay(recorded_value['rows'], recorded_value['session'], since, failed_until + 10,
        login_sync=sync)
    entry = trial(r.PHASE, failed_until + 1, failed_until + 10, **authority,
        code_commit='f' * 40, committed_sources=new_refs, predecessor=predecessor,
        predecessor_dvc_pointer=ready['predecessor_dvc_pointer'], all_offline_snapshot=baseline,
        native_session=recorded_value['session'], native_before_entry=native,
        original_entry_source=failed_ref, original_preparation_source=ready_ref,
        preparation_source=ready_ref, precision_source=precision_ref, original_login_interval=interval,
        login_sync=sync, raw_entry_packets=recorded_value['rows'], raw_entry_events=recorded_value['events'],
        login_packets=sync['login_packets'],
        owner_packets=owner['packets'], native_owner_proof=owner, current_snapshot=current,
        state={'player': 'Harnesstwo', 'level': 1, 'xp': 0, 'xp_max': 400, 'xp_exhaustion': 2 * int(exact_after)},
        native_original={'pose': {'stand': 0, 'sheath': 0}, 'afk': False},
        repair_code_transition={'schema': r.TRANSITION_SCHEMA, 'from_code_commit': r.C1_COMMIT,
            'to_code_commit': 'f' * 40, 'original_sources': old_refs, 'carried_sources': old_copies,
            'committed_sources': new_refs, 'current_carried_sources': new_copies})
    entry_ref = store.put('renewed/episode.json', entry)
    return {'store': store, 'repo': repo, 'ready': ready, 'entry': entry, 'precision': precision,
        'ready_ref': ready_ref, 'entry_ref': entry_ref, 'precision_ref': precision_ref,
        'failed_ref': failed_ref, 'old_raws': old_raws, 'new_raws': new_raws}


def validate(values):
    return r.validate_entry(*(values[k] for k in ('store', 'ready', 'entry', 'precision',
        'ready_ref', 'entry_ref', 'precision_ref')))


def test_complete_portable_renewal_keeps_original_timestamps_and_exact_both_code_epochs(tmp_path, monkeypatch):
    v = fixture(tmp_path)
    before = deepcopy(v['store'].data)
    def forbidden(*args, **kwargs):
        raise AssertionError('portable admission attempted current filesystem or Git access')
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    monkeypatch.setattr(subprocess, 'check_output', forbidden)
    result = validate(v)
    assert result['login_interval'] == v['entry']['original_login_interval']
    assert result['original_entry']['completed'] is False
    assert result['original_entry']['code_commit'] == r.C1_COMMIT
    assert result['native_rest']['matches'][0]['native_login_second'] == 1791421132
    assert result['current_preservation']['operations_admitted'] == 0
    assert v['entry']['started_at'] > result['original_entry']['finished_at']
    assert v['store'].data == before and 'entered_native' not in v['entry']
    assert len(result['code_transition']['original_sources']) == 35


@pytest.mark.parametrize('fault', ['old_raw', 'current_raw', 'old_path', 'current_path', 'old_commit',
    'current_commit', 'old_bytes_bool', 'current_bytes', 'old_missing', 'current_missing', 'old_duplicate',
    'current_duplicate', 'old_reorder', 'current_reorder', 'old_extra_field', 'transition_extra',
    'same_commit', 'current_member_removed', 'current_helper_removed'])
def test_code_transition_refuses_raw_byte_member_epoch_and_vector_drift(tmp_path, fault):
    v = fixture(tmp_path)
    t = v['entry']['repair_code_transition']
    if fault.startswith(('old_', 'current_')) and fault not in ('current_member_removed',):
        key = 'carried_sources' if fault.startswith('old_') else 'current_carried_sources'
        envelope = v['store'].data[t[key][0]['path']]
        kind = fault.split('_', 1)[1]
        if kind == 'raw': envelope['raw_hex'] = '00' * envelope['bytes']
        elif kind == 'path': envelope['original_path'] += '.other'
        elif kind == 'commit': envelope['code_commit'] = 'd' * 40
        elif kind == 'bytes_bool': envelope['bytes'] = True
        elif kind == 'bytes': envelope['bytes'] += 1
        elif kind == 'missing': t[key].pop()
        elif kind == 'duplicate': t[key][1] = t[key][0]
        elif kind == 'reorder': t[key].reverse()
        else: envelope['accepted'] = True
    elif fault == 'transition_extra': t['accepted'] = True
    elif fault == 'same_commit': v['entry']['code_commit'] = t['to_code_commit'] = r.C1_COMMIT
    elif fault == 'current_member_removed':
        t['committed_sources'].pop(1)
        t['current_carried_sources'].pop(1)
    else:
        index = next(i for i, ref in enumerate(t['committed_sources']) if ref['path'].endswith('/bag_swap_renewal.py'))
        t['committed_sources'].pop(index)
        t['current_carried_sources'].pop(index)
    with pytest.raises(RuntimeError):
        validate(v)


@pytest.mark.parametrize('fault', ['formula_bytes', 'repository_path'])
def test_rehashed_current_epoch_cannot_replace_native_formula_or_repository(tmp_path, fault):
    v = fixture(tmp_path)
    transition = v['entry']['repair_code_transition']
    for ref, copy in zip(transition['committed_sources'], transition['current_carried_sources']):
        envelope = v['store'].data[copy['path']]
        if fault == 'repository_path':
            ref['path'] = str(tmp_path / 'different_repo' / Path(ref['path']).relative_to(v['repo']))
            envelope['original_path'] = ref['path']
        elif ref['path'].endswith('/' + FORMULA):
            raw = bytes.fromhex(envelope['raw_hex']) + b'\n// changed formula epoch\n'
            ref['sha256'] = envelope['sha256'] = hashlib.sha256(raw).hexdigest()
            envelope.update(bytes=len(raw), raw_hex=raw.hex())
    with pytest.raises(RuntimeError, match='same actual repository and pinned native rest formula'):
        r.validate_code_transition(v['store'], v['ready'], v['entry'])


@pytest.mark.parametrize('fault', ['failed_success', 'failed_other_reason', 'failed_mutation', 'failed_attempt',
    'failed_entered_sql', 'failed_code', 'ready_code', 'precision_code', 'resume_code', 'resume_sources',
    'original_source', 'original_ready', 'precision_source', 'original_interval', 'rewritten_started',
    'actor', 'runtime', 'session', 'authority', 'script', 'input', 'entered_sql', 'raw_original_loss',
    'extra_swap', 'extra_login', 'extra_movement', 'owner_proof', 'current_health', 'current_protected',
    'current_inventory', 'current_rest', 'current_offline', 'current_afk', 'current_sit', 'preprecision',
    'early_attempt', 'missing_events', 'extra_metadata', 'mutated_metadata', 'sync_window', 'sync_allowance'])
def test_renewal_refuses_provenance_input_original_history_and_current_state_drift(tmp_path, fault):
    v = fixture(tmp_path)
    e, ready, p = v['entry'], v['ready'], v['precision']
    f = v['store'].data[v['failed_ref']['path']]
    if fault == 'failed_success': f['completed'] = True
    elif fault == 'failed_other_reason': f['failure'] = 'RuntimeError: different failure'
    elif fault == 'failed_mutation': f['mutation_sent'] = True
    elif fault == 'failed_attempt': f['forward_attempt_source'] = v['entry_ref']
    elif fault == 'failed_entered_sql': f['entered_native'] = f['native_before_entry']
    elif fault == 'failed_code': f['code_commit'] = 'd' * 40
    elif fault == 'ready_code': ready['code_commit'] = 'd' * 40
    elif fault == 'precision_code': p['code_commit'] = 'd' * 40
    elif fault in ('resume_code', 'resume_sources'):
        resume = v['store'].data[ready['resume_source']['path']]
        if fault == 'resume_code': resume['code_commit'] = 'd' * 40
        else: resume['committed_sources'].pop()
    elif fault == 'original_source': e['original_entry_source'] = v['ready_ref']
    elif fault == 'original_ready': e['original_preparation_source'] = v['precision_ref']
    elif fault == 'precision_source': e['precision_source'] = v['ready_ref']
    elif fault == 'original_interval': e['original_login_interval']['until'] += .1
    elif fault == 'rewritten_started': e['started_at'] = f['started_at']
    elif fault == 'actor': e['actor']['guid'] = 3
    elif fault == 'runtime': e['runtime']['client']['start_ticks'] += '1'
    elif fault == 'session': e['native_session'] = 'other'
    elif fault == 'authority': e['authority_source'] = v['ready_ref']
    elif fault == 'script': e['softTargetInteract']['current_stock_disabled'] = '0'
    elif fault == 'input': e['input_sent'] = True
    elif fault == 'entered_sql': e['entered_native'] = f['native_before_entry']
    elif fault == 'raw_original_loss': e['raw_entry_packets'].pop()
    elif fault in ('extra_swap', 'extra_login', 'extra_movement'):
        row = deepcopy(e['raw_entry_packets'][0])
        row.update(time=e['started_at'] + .1, session=e['native_session'], direction='from_client',
            name={'extra_swap': contract.ACTION, 'extra_login': 'CMSG_PLAYER_LOGIN',
                'extra_movement': 'CMSG_MOVE_HEARTBEAT'}[fault])
        e['raw_entry_packets'].append(row)
    elif fault == 'owner_proof': e['native_owner_proof']['health'] = 59
    elif fault == 'current_health': e['current_snapshot']['2']['native']['health'] -= 1
    elif fault == 'current_protected': e['current_snapshot']['6']['pets'][0]['curhealth'] -= 1
    elif fault == 'current_inventory': e['current_snapshot']['2']['inventory'][0][2] += 1
    elif fault == 'current_rest': e['current_snapshot']['2']['native']['rest_bonus'] += .001
    elif fault == 'current_offline': e['current_snapshot']['2']['native']['online'] = 0
    elif fault == 'current_afk': e['native_original']['afk'] = True
    elif fault == 'current_sit': e['native_original']['pose']['stand'] = 1
    elif fault == 'preprecision': p['row']['exact_rest_bonus_float32_bits'] = '00000000'
    elif fault == 'missing_events': e.pop('raw_entry_events')
    elif fault == 'extra_metadata':
        e['raw_entry_events'].append({'event': 'unmapped_client_packet', 'session': e['login_sync']['instance_session'],
            'time': e['original_login_interval']['until'] - .1, 'name': 'CMSG_MOVE_TIME_SKIPPED', 'bytes': 4})
    elif fault == 'mutated_metadata': e['raw_entry_events'][0]['time'] -= 1
    elif fault == 'sync_window': e['login_sync']['until'] += .1
    elif fault == 'sync_allowance': e['login_sync']['allowed_packet_keys'].append('{}')
    else: v['store'].put('attempt.json', {'schema': 'client442_bag_swap_consumed_attempt_v1',
        'entry_source': v['entry_ref'], 'preparation_source': v['ready_ref'], 'created_at': e['started_at']})
    # Bind mutations of ready/P into the supplied immutable synthetic store too.
    v['store'].data[v['ready_ref']['path']] = ready
    v['store'].data[v['precision_ref']['path']] = p
    with pytest.raises(RuntimeError):
        validate(v)


def test_login_interval_keeps_ordinary_timestamps_and_refuses_implicit_relabeling(tmp_path):
    assert r.login_interval({'phase': contract.ENTRY_PHASE, 'started_at': 100., 'finished_at': 101.}) == {
        'since': 100., 'until': 101.}
    e = fixture(tmp_path)['entry']
    e['phase'] = contract.ENTRY_PHASE
    with pytest.raises(RuntimeError): r.login_interval(e)


@pytest.mark.parametrize('preparation', ['missing', 'other'])
def test_attempt_explicitly_owned_by_renewed_entry_cannot_hide_early_consumption(tmp_path, preparation):
    v = fixture(tmp_path)
    attempt = {'schema': 'client442_bag_swap_consumed_attempt_v1', 'entry_source': v['entry_ref'],
        'created_at': v['entry']['started_at']}
    if preparation == 'other':
        attempt['preparation_source'] = v['precision_ref']
    v['store'].put('attempt.json', attempt)
    with pytest.raises(RuntimeError, match='consumed before renewed'):
        validate(v)


@pytest.mark.parametrize('name', ['CMSG_CHAT_MESSAGE_AFK', 'CMSG_MESSAGECHAT_AFK'])
@pytest.mark.parametrize('direction', ['from_client', 'to_native'])
def test_afk_housekeeping_requires_its_exact_excluded_source_proof(tmp_path, name, direction):
    v = fixture(tmp_path)
    e = v['entry']
    e['raw_entry_packets'].append({'session': e['native_session'], 'time': e['started_at'] + .1,
        'name': name, 'direction': direction, 'body': '0000'})
    with pytest.raises(RuntimeError): validate(v)


def test_carry_reads_exact_commit_bytes_and_never_uses_changed_checkout(tmp_path, monkeypatch):
    v = fixture(tmp_path)
    root, repo = v['store'].root, v['repo']
    (root / 'evidence').mkdir(parents=True)
    calls = []
    def git(args, *, cwd):
        calls.append((args, cwd))
        commit, member = args[2].split(':', 1)
        assert args[:2] == ['git', 'show'] and commit == r.C1_COMMIT
        return v['old_raws'][member]
    monkeypatch.setattr(subprocess, 'check_output', git)
    carried = r.carry_code_sources(v['ready'], root / 'evidence/old_code', repo=repo, root=root)
    assert len(carried) == len(calls) == 35
    assert all(cwd == repo for _, cwd in calls)
    for ref in carried:
        path = Path(ref['path'])
        assert path.stat().st_mode & 0o777 == 0o600
        assert hashlib.sha256(path.read_bytes()).hexdigest() == ref['sha256']
        envelope = json.loads(path.read_bytes())
        assert bytes.fromhex(envelope['raw_hex']) == v['old_raws'][str(Path(envelope['original_path']).relative_to(repo))]
    with pytest.raises(RuntimeError): r.carry_code_sources(v['ready'], root / 'evidence/old_code', root=root)


@pytest.mark.parametrize('fault', ['wrong_git_bytes', 'escape', 'parent_escape', 'existing', 'symlink', 'vector_reorder'])
def test_carry_refuses_unbound_git_or_nonprivate_destination_before_writing(tmp_path, monkeypatch, fault):
    v = fixture(tmp_path)
    root = v['store'].root
    (root / 'evidence').mkdir(parents=True)
    out = root / 'evidence/code'
    if fault == 'escape': out = tmp_path / 'outside'
    elif fault == 'parent_escape': out = root / 'evidence/../escaped_code'
    elif fault == 'existing': out.mkdir()
    elif fault == 'symlink': out.symlink_to(root / 'evidence', target_is_directory=True)
    elif fault == 'vector_reorder': v['ready']['committed_sources'].reverse()
    monkeypatch.setattr(subprocess, 'check_output', lambda *args, **kwargs: b'wrong')
    with pytest.raises(RuntimeError): r.carry_code_sources(v['ready'], out, root=root)
    if fault == 'wrong_git_bytes': assert not out.exists()


def test_renewal_import_has_no_live_ui_sql_runtime_network_dependency():
    script = '''
import importlib,sys
class Block:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.startswith(('Crypto','google','PIL','pymysql','requests','urllib.request',
            'tools.client_compatibility.interaction_','tools.client_compatibility.lab_runtime')):
            raise AssertionError('live dependency imported: '+fullname)
sys.meta_path.insert(0,Block())
importlib.import_module('tools.client_compatibility.bag_swap_renewal')
'''
    subprocess.run([sys.executable, '-B', '-c', script], cwd=Path(__file__).resolve().parents[4],
        check=True, capture_output=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
