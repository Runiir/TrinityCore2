"""Pure admission of one source-preserving C1 to C2 occupied-swap entry repair.

The failed entry retains its original bytes and login interval. The renewed
receipt describes a later observation; it never manufactures an old SQL read.
Only ``carry_code_sources`` reads Git, to retain both actual committed epochs.
"""
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess

from . import bag_swap_contract as contract
from . import bag_swap_preservation as preservation
from .bag_swap_login_sync import login_sync, validate_login_sync, packet_key
from .bag_swap_projection import SOURCE_FILES
from .item_actionbar_contract import require, finite, strict_equal
from .item_actionbar_sources import (reference, FORMULA, FORMULA_HASH, CONFIG_HASH,
    FORMULA_SNIPPETS, FLOAT_SOURCES)

PHASE = 'bags_swap_entry_renewed'
C1_COMMIT = 'e9a37f0666b911e47596443fa7850b48aa9797c5'
CODE_SCHEMA = 'client442_bag_swap_code_source_v1'
TRANSITION_SCHEMA = 'client442_bag_swap_entry_code_transition_v1'
ROOT = Path.home() / '.local/share/trinity-client442-lab'
REPO = Path(__file__).resolve().parents[2]
CONFIG = 'experiments/configs/client_harness/442_bag_swap_roundtrip_v1.json'
OLD_SOURCE_FILES = (
    'tools/client_compatibility/item_actionbar_contract.py',
    'tools/client_compatibility/item_actionbar_preservation.py',
    'tools/client_compatibility/world/buffer.py',
    'tools/client_compatibility/world/native_objects.py',
    'tools/client_compatibility/world/native_transport.py',
    'tools/client_compatibility/native_bridge/protocol.cpp',
    'tools/client_compatibility/native_bridge/buffer.cpp',
    'tools/client_compatibility/native_bridge/buffer.hpp',
    'tools/client_compatibility/native_bridge/inventory_requests.cpp',
    'tools/client_compatibility/native_bridge/inventory_updates.cpp',
    'tools/client_compatibility/native_bridge/native_objects.cpp',
    'tools/client_compatibility/world/native_fields.json',
    'tools/client_compatibility/world/fields.json',
    'tools/client_compatibility/interaction_item_actionbar_parked_selection_capture.py',
    'src/server/game/Entities/Player/Player.cpp',
    'src/server/game/Handlers/ItemHandler.cpp',
)
OLD_MODULES = ('bag_swap_contract', 'bag_swap_evidence', 'bag_swap_preservation',
    'bag_swap_projection', 'bag_swap_sources', 'checkpoint_bag_swap',
    'interaction_bag_swap', 'interaction_bag_swap_continuation', 'review_bag_swap_checkpoint')
OLD_TESTS = ('continuation', 'contract', 'evidence', 'full_unit', 'operation',
    'preservation', 'projection', 'publication', 'sources')
OLD_MEMBERS = tuple(sorted((CONFIG, *OLD_SOURCE_FILES,
    *('tools/client_compatibility/' + n + '.py' for n in OLD_MODULES),
    *('tools/client_compatibility/world/tests/test_bag_swap_' + n + '.py' for n in OLD_TESTS))))
MAX_SOURCES, MAX_SOURCE_BYTES, MAX_TOTAL_BYTES = 96, 4 * 1024 * 1024, 16 * 1024 * 1024
TRANSITION_FIELDS = {'schema', 'from_code_commit', 'to_code_commit', 'original_sources',
    'carried_sources', 'committed_sources', 'current_carried_sources'}
CODE_FIELDS = {'schema', 'code_commit', 'original_path', 'sha256', 'bytes', 'raw_hex'}
CURRENT_REQUIRED = frozenset(('tools/client_compatibility/bag_swap_renewal.py',
    'tools/client_compatibility/bag_swap_login_sync.py',
    'tools/client_compatibility/world/tests/test_bag_swap_renewal.py',
    'tools/client_compatibility/world/tests/test_bag_swap_login_sync.py'))
SCRIPT_BOUNDARY = {'original': '0', 'current_stock_disabled': '1', 'original_restored': False}
FAILURE = ('RuntimeError: bag swap refuses other gameplay mutation, item use/cast/action assignment, '
    'combat, target, movement, pet input or inventory failure')


def _commit(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{40}', value), 'actual full code commit is required')
    return value


def _closed(value, phase):
    require(type(value) is dict and value.get('phase') == phase and value.get('completed') is True and
        value.get('failure') is None and finite(value.get('started_at')) and finite(value.get('finished_at')) and
        0 < value['started_at'] < value['finished_at'] and
        all(value.get(k) is not True for k in ('recovery_only', 'failed_whole_excluded',
            'settlement_only', 'failed_repair_excluded')), 'one actual closed renewal source is required')
    return value


def _vector(identity):
    _commit(identity.get('code_commit'))
    refs = identity.get('committed_sources')
    require(type(refs) is list and 16 <= len(refs) <= MAX_SOURCES, 'bounded complete committed source vector required')
    for ref in refs:
        reference(ref)
        require(str(Path(ref['path'])) == ref['path'], 'canonical committed source path required')
    paths = [r['path'] for r in refs]
    require(paths == sorted(set(paths)), 'committed sources must be ordered and distinct')
    configs = [Path(p) for p in paths if p.endswith('/' + CONFIG)]
    require(len(configs) == 1, 'one actual occupied-swap configuration source required')
    repo = configs[0].parents[3]
    require(all(Path(p).is_relative_to(repo) for p in paths), 'all code sources must belong to one repository')
    members = [str(Path(p).relative_to(repo)) for p in paths]
    fixed = {CONFIG, *(OLD_SOURCE_FILES if identity['code_commit'] == C1_COMMIT else SOURCE_FILES)}
    require(fixed <= set(members) and all(m in fixed or (
        Path(m).parent == Path('tools/client_compatibility') and 'bag_swap' in Path(m).name and m.endswith('.py')) or (
        Path(m).parent == Path('tools/client_compatibility/world/tests') and
        Path(m).name.startswith('test_bag_swap') and m.endswith('.py')) for m in members),
        'complete narrow occupied-swap code member list required')
    if identity['code_commit'] == C1_COMMIT:
        require(tuple(members) == OLD_MEMBERS and len(members) == 35, 'the actual original 35 C1 sources are required')
    return refs, repo, members


def carry_code_sources(identity, out, *, repo=None, root=None):
    """Retain actual Git bytes for a frozen epoch without reading checkout bytes."""
    refs, original_repo, members = _vector(identity)
    repo, root, out = Path(repo or original_repo), Path(root or ROOT), Path(out)
    require(repo.is_absolute() and root.is_absolute() and out.is_absolute() and
        all('..' not in p.parts for p in (repo, root, out)) and out.is_relative_to(root / 'evidence') and
        out.parent.is_dir() and not out.exists() and
        not any(p.is_symlink() for p in (out, *out.parents)), 'new private source-owned code carry directory required')
    values, total = [], 0
    for ref, member in zip(refs, members):
        raw = subprocess.check_output(['git', 'show', identity['code_commit'] + ':' + member], cwd=repo)
        total += len(raw)
        require(len(raw) <= MAX_SOURCE_BYTES and total <= MAX_TOTAL_BYTES and
            hashlib.sha256(raw).hexdigest() == ref['sha256'], 'actual committed source bytes differ from the frozen epoch')
        values.append({'schema': CODE_SCHEMA, 'code_commit': identity['code_commit'],
            'original_path': ref['path'], 'sha256': ref['sha256'], 'bytes': len(raw), 'raw_hex': raw.hex()})
    out.mkdir(mode=0o700)
    result = []
    for index, value in enumerate(values):
        raw = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
        path = out / (f'{index:03d}_' + value['sha256'] + '.json')
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        require(path.read_bytes() == raw, 'carried committed source changed while writing')
        result.append({'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()})
    return result


def _epoch(store, identity, carried):
    refs, _, members = _vector(identity)
    require(type(carried) is list and len(carried) == len(refs), 'one carried raw source per committed member required')
    for ref in carried:
        reference(ref)
    require(len({r['path'] for r in carried}) == len(carried), 'carried code source references must be distinct')
    total = 0
    for original, copy in zip(refs, carried):
        value = store.get(copy, False)
        require(type(value) is dict and set(value) == CODE_FIELDS and value['schema'] == CODE_SCHEMA and
            value['code_commit'] == identity['code_commit'] and value['original_path'] == original['path'] and
            value['sha256'] == original['sha256'] and type(value['bytes']) is int and
            0 <= value['bytes'] <= MAX_SOURCE_BYTES and type(value['raw_hex']) is str and
            len(value['raw_hex']) == value['bytes'] * 2 and
            re.fullmatch('[0-9a-f]*', value['raw_hex']), 'carried source envelope differs from its actual epoch member')
        raw = bytes.fromhex(value['raw_hex'])
        total += len(raw)
        require(total <= MAX_TOTAL_BYTES and hashlib.sha256(raw).hexdigest() == original['sha256'],
            'portable committed source raw bytes differ from their original SHA')
    return members


def validate_code_transition(store, ready, entry):
    """Verify the complete raw C1 and C2 vectors using only carried sources."""
    transition = entry.get('repair_code_transition')
    require(type(transition) is dict and set(transition) == TRANSITION_FIELDS and
        transition['schema'] == TRANSITION_SCHEMA and ready.get('code_commit') == C1_COMMIT and
        transition['from_code_commit'] == C1_COMMIT and
        transition['to_code_commit'] == entry.get('code_commit') != C1_COMMIT and
        strict_equal(transition['original_sources'], ready.get('committed_sources')) and
        strict_equal(transition['committed_sources'], entry.get('committed_sources')),
        'exact explicit original-to-current code transition required')
    old = _epoch(store, ready, transition['carried_sources'])
    current = _epoch(store, entry, transition['current_carried_sources'])
    old_refs, old_repo, _ = _vector(ready)
    current_refs, current_repo, _ = _vector(entry)
    formula = {'path': str(old_repo / FORMULA), 'sha256': FORMULA_HASH}
    require(old_repo == current_repo and formula in old_refs and formula in current_refs,
        'both code epochs must carry the same actual repository and pinned native rest formula bytes')
    require(set(old) | CURRENT_REQUIRED <= set(current) and
        not ({r['path'] for r in transition['carried_sources']} &
             {r['path'] for r in transition['current_carried_sources']}), 'both distinct complete code epochs must be carried')
    return deepcopy(transition)


def login_interval(entry):
    """Return the semantic login window while retaining actual receipt times."""
    require(type(entry) is dict, 'actual entry receipt required')
    if entry.get('phase') == PHASE:
        _closed(entry, PHASE)
        interval = entry.get('original_login_interval')
        require(type(interval) is dict and set(interval) == {'since', 'until'} and
            finite(interval['since']) and finite(interval['until']) and
            0 < interval['since'] < interval['until'] < entry['started_at'], 'exact original login interval required')
        for key in ('original_entry_source', 'original_preparation_source', 'precision_source'):
            reference(entry.get(key))
        return deepcopy(interval)
    require(entry.get('phase') == contract.ENTRY_PHASE and
        not any(k in entry for k in ('original_login_interval', 'original_entry_source', 'repair_code_transition')) and
        finite(entry.get('started_at')) and finite(entry.get('finished_at')) and
        0 < entry['started_at'] < entry['finished_at'], 'ordinary or explicitly renewed login window required')
    return {'since': entry['started_at'], 'until': entry['finished_at']}


def _identity(value, ready, *, session=False):
    require(strict_equal(value.get('actor'), ready.get('actor')) and strict_equal(value.get('runtime'), ready.get('runtime')) and
        value.get('controller') == 'code' and value.get('model') is None and value.get('revision') is None and
        value.get('qualification_added') is False and value.get('custom_script_permission') == 'blocked_by_user' and
        strict_equal(value.get('softTargetInteract'), SCRIPT_BOUNDARY) and
        all(value.get(k) == ready.get(k) for k in ('observer_file_sha256', 'compatibility_addon_sha256')) and
        (not session or value.get('native_session') == ready.get('native_session')),
        'original actor/runtime/controller/script/source identity changed')


def _rest_sources(value, ready, ready_ref):
    _, repo, _ = _vector(ready)
    path = Path(ready_ref['path'])
    parts = path.parts
    require('evidence' in parts, 'original preparation must be private evidence')
    root = Path(*parts[:parts.index('evidence')])
    require(type(value) is dict and type(value.get('rate')) in (int, float) and value['rate'] == 1 and
        type(value.get('xp_cap')) is int and value['xp_cap'] == 400 and
        type(value.get('rest_cap')) is int and value['rest_cap'] == 300 and
        type(value.get('wilderness_bubble')) is float and value['wilderness_bubble'] == .031 and
        value.get('formula_snippets') == list(FORMULA_SNIPPETS) and
        value.get('config_source') == {'path': str(root / 'config/worldserver.conf'), 'sha256': CONFIG_HASH} and
        value.get('native_formula_source') == {'path': str(repo / FORMULA), 'sha256': FORMULA_HASH} and
        value.get('native_float_storage_sources') == [{'path': str(repo / p), 'sha256': sha}
            for p, sha in FLOAT_SOURCES.items()], 'exact original configured native FLOAT formula sources required')


def validate_entry(store, ready, entry, precision, ready_ref, entry_ref, precision_ref):
    """Admit one failed original login followed only by honest C2 observation."""
    for ref in (ready_ref, entry_ref, precision_ref):
        reference(ref)
    _closed(ready, 'bags_swap_scout_ready')
    _closed(precision, 'bags_swap_rest_precision_complete')
    _closed(entry, PHASE)
    require(strict_equal(store.get(ready_ref), ready) and strict_equal(store.get(precision_ref), precision),
        'exact immutable original ready and preprecision sources required')
    original_ref = entry.get('original_entry_source')
    reference(original_ref)
    require(len({r['path'] for r in (ready_ref, entry_ref, precision_ref, original_ref)}) == 4,
        'original and renewed lifecycle roles must retain distinct source-owned paths')
    original = store.get(original_ref, False)
    require(type(original) is dict and original.get('phase') == 'bags_swap_entry_started' and
        original.get('completed') is False and original.get('failure') == FAILURE and
        finite(original.get('started_at')) and finite(original.get('finished_at')) and
        finite(original.get('entry_input_started_at')) and finite(original.get('entry_input_finished_at')) and
        0 < original['started_at'] <= original['entry_input_started_at'] < original['entry_input_finished_at'] <=
        original['finished_at'] < entry['started_at'] and original.get('input_sent') is True and
        original.get('mutation_sent') is False and original.get('cases') == [] and original.get('cleanup') == [] and
        not any(k in original for k in ('entered_native', 'native_owner_proof', 'forward', 'reverse',
            'forward_attempt_source', 'reverse_attempt_source')),
        'one unchanged failed C1 login without any bag attempt is required')
    require(ready['code_commit'] == precision.get('code_commit') == original.get('code_commit') == C1_COMMIT and
        strict_equal(ready.get('committed_sources'), precision.get('committed_sources')) and
        strict_equal(ready.get('committed_sources'), original.get('committed_sources')),
        'original ready/preprecision/failed source epoch must remain C1')
    for value in (ready, precision, original, entry):
        _identity(value, ready, session=value is original or value is entry)
    resume = store.get(ready.get('resume_source'), False)
    require(type(resume) is dict and resume.get('schema') == 'client442_bag_swap_scout_resume_v1' and
        resume.get('phase') == 'bags_swap_scout_launched' and resume.get('completed') is True and
        resume.get('failure') is None and resume.get('code_commit') == C1_COMMIT and
        strict_equal(resume.get('committed_sources'), ready['committed_sources']), 'original resume source must retain its C1 epoch')
    require(entry.get('original_preparation_source') == entry.get('preparation_source') == original.get('preparation_source') == ready_ref and
        entry.get('precision_source') == original.get('precision_source') == precision_ref and
        entry.get('predecessor') == original.get('predecessor') == ready.get('predecessor') and
        all(entry.get(k) == ready.get(k) for k in ('authority_source', 'runtime_authority_source', 'predecessor_dvc_pointer')) and
        ready['finished_at'] <= precision['started_at'] < precision['finished_at'] <= original['started_at'] and
        ready.get('input_sent') is False and ready.get('mutation_sent') is False and
        precision.get('input_sent') is False and precision.get('mutation_sent') is False and
        entry.get('input_sent') is False and entry.get('mutation_sent') is False and entry.get('cases') == [] and
        entry.get('cleanup') == [] and 'entered_native' not in entry,
        'renewal must retain original preparation/authority and send no new gameplay input')
    baseline = ready.get('all_offline_snapshot')
    contract.owned_snapshot(baseline)
    native = baseline['2']['native']
    require(strict_equal(precision.get('before'), baseline) and strict_equal(precision.get('after'), baseline) and
        precision.get('source') == ready_ref and precision.get('query') == preservation.PRECISION_QUERY and
        strict_equal(precision.get('checks'), dict.fromkeys(('all_six_offline', 'all_saved_state_unchanged',
            'original_identity', 'snapshot_rest_matches', 'exact_float32'), True)),
        'original source-bound exact preprecision required')
    _rest_sources(precision.get('rest_sources'), ready, ready_ref)
    exact_before = preservation.exact_precision(precision['row'], baseline)
    require(all(strict_equal(v.get('all_offline_snapshot'), baseline) and
        strict_equal(v.get('native_before_entry'), native) for v in (original, entry)),
        'renewal may not replace the original offline native baseline')
    interval = login_interval(entry)
    require(interval == {'since': original['started_at'], 'until': original['entry_input_finished_at']},
        'renewal original login timestamps differ from the failed source')
    transition = validate_code_transition(store, ready, entry)
    sync = validate_login_sync(entry.get('login_sync'))
    pose = [native[k] for k in ('position_x', 'position_y', 'position_z', 'orientation')]
    require(sync['session'] == ready['native_session'] and sync['since'] == interval['since'] and
        sync['until'] == interval['until'] and
        strict_equal(sync['baseline_pose'], [preservation.float32(v) for v in pose]), 'login settlement window or original native pose changed')
    old_raw, raw = original.get('raw_entry_packets'), entry.get('raw_entry_packets')
    require(type(old_raw) is list and type(raw) is list and old_raw == contract.packet_rows(raw, ready['native_session'],
        original['started_at'], original['finished_at']), 'new packet history must retain every exact original failed packet')
    require(all(packet_key(row) in {packet_key(p) for p in old_raw} for row in sync['source_packets']),
        'login settlement sources must belong to the original failed journal')
    require(strict_equal(sync, login_sync(raw, entry.get('raw_entry_events'), ready['native_session'],
        interval['since'], interval['until'], pose)), 'login settlement must replay the complete original event window')
    for row in contract.packet_rows(raw, ready['native_session'], interval['since'], entry['finished_at']):
        require(row.get('name') != contract.ACTION, 'no occupied swap input may precede renewed entry admission')
    idle = None
    if 'idle_housekeeping_source' in entry or 'idle_housekeeping' in entry:
        from . import bag_swap_idle
        receipt = store.get(entry.get('idle_housekeeping_source'))
        idle = bag_swap_idle.validate_receipt(store, receipt, ready, original, entry)
        require(strict_equal(entry.get('idle_housekeeping'), idle), 'source-bound idle housekeeping proof differs')
    replay_kwargs = {'login_sync': sync}
    if idle is not None:
        replay_kwargs['idle_housekeeping'] = idle
    contract.forbidden_packets(raw, ready['native_session'], interval['since'], entry['finished_at'], **replay_kwargs)
    for session in (ready['native_session'], sync['instance_session']):
        contract.forbidden_packets(entry['raw_entry_events'], session, interval['since'], entry['finished_at'], **replay_kwargs)
    chain = contract.login_packets(raw, ready['native_session'], interval['since'], entry['finished_at'])
    require(strict_equal(entry.get('login_packets'), sync['login_packets']) and
        strict_equal(sync['login_packets'], [chain[k] for k in ('modern', 'request', 'verify', 'delivered')]),
        'renewal must retain the one original modern/native login chain')
    owner = contract.native_replay(raw, ready['native_session'], interval['since'], entry['finished_at'], **replay_kwargs)
    require(strict_equal(entry.get('native_owner_proof'), owner) and strict_equal(entry.get('owner_packets'), owner['packets']),
        'whole original creation through current observation native history required')
    current = entry.get('current_snapshot')
    current_preservation = preservation.online_preservation(baseline, current)
    original_native = entry.get('native_original', {})
    require(type(original_native) is dict and strict_equal(original_native.get('pose'), {'stand': 0, 'sheath': 0}) and
        original_native.get('afk') is False, 'fresh renewed native pose must restore standing/unsheathed/non-AFK state')
    state = entry.get('state', {})
    require(all(type(state.get(k)) is type(v) and state[k] == v for k, v in
        {'player': 'Harnesstwo', 'level': 1, 'xp': 0, 'xp_max': contract.XP_CAP}.items()) and
        type(state.get('xp_exhaustion')) is int, 'honest renewed level1 XP observation required')
    matches = []
    for second in range(math.floor(chain['request']['time']), math.floor(chain['verify']['time']) + 1):
        elapsed = second - native['logout_time']
        if elapsed < 0:
            continue
        exact, text = preservation.native_rest(exact_before['exact_rest_bonus'], elapsed)
        if (text == current['2']['native']['rest_bonus'] and owner['rest_threshold'] == int(exact) and
                state['xp_exhaustion'] == 2 * int(exact)):
            matches.append({'native_login_second': second, 'offline_seconds': elapsed, 'exact_after': exact,
                'before_float32_bits': exact_before['exact_rest_bonus_float32_bits'],
                'after_float32_bits': preservation.float32_bits(exact)})
    require(len(matches) == 1, 'current accounting/rest must match one original native login second')
    for value in getattr(store, 'data', {}).values():
        if type(value) is dict and value.get('schema') == 'client442_bag_swap_consumed_attempt_v1':
            require(value.get('entry_source') != original_ref and
                (value.get('preparation_source') != ready_ref and value.get('entry_source') != entry_ref or
                 finite(value.get('created_at')) and value['created_at'] > entry['finished_at']),
                'an occupied bag attempt was consumed before renewed admission')
    return {'original_entry': deepcopy(original), 'original_preparation': deepcopy(ready),
        'precision': deepcopy(precision), 'login_interval': interval, 'code_transition': transition,
        'native_owner_proof': owner, 'login_sync': sync, 'current_preservation': current_preservation,
        'native_rest': {'matches': matches}}
