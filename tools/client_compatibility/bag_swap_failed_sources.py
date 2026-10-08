"""Portable source authority for an excluded failed entry and offline closure.

Historical failed receipts keep their actual shape. Git reads happen only while
carrying code epochs; the final validator uses archived bytes and journals.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess

from . import bag_swap_contract as contract
from . import bag_swap_preservation as preservation
from .bag_swap_projection import SOURCE_FILES as CURRENT_DEPENDENCIES
from .item_actionbar_sources import (reference, FORMULA, FORMULA_HASH, CONFIG_HASH,
    FORMULA_SNIPPETS, FLOAT_SOURCES)
from .item_actionbar_contract import require, finite, strict_equal

SCHEMA = 'client442_bag_swap_failed_entry_closure_v1'
PHASE = 'bags_swap_failed_entry_closed_paused'
CAPTURE_PHASE = 'bags_swap_failed_entry_captured'
EPOCH_SCHEMA = 'client442_bag_swap_failed_code_epochs_v1'
CODE_SCHEMA = 'client442_bag_swap_code_source_v1'
C1 = 'e9a37f0666b911e47596443fa7850b48aa9797c5'
H06 = 'b3e115403c450c4fdb7552baf6464c45bb283d70'
H07 = '76386db97bb0c20826c30513d5126b2929fe0bf6'
ROLES = ('original', 'h06', 'h07', 'current')
ROOT = Path.home() / '.local/share/trinity-client442-lab'
REPO = Path(__file__).resolve().parents[2]
_BATCH = 'evidence/client_interactions_20261008_ui172/'
# Actual immutable source bytes admitted before this excluded closure. These
# anchors are independent of caller receipts, archived vectors and Git labels.
_HISTORICAL_SOURCES = {role: {'path': str(ROOT / (_BATCH + member)), 'sha256': sha}
    for role, member, sha in (
        ('preparation', 'scout_ready01/episode.json', 'ffbc2f9482ab1c029c3764411d517468d142880434071ca1f59b2b06487a5194'),
        ('precision', 'rest_before01/episode.json', '5e2ec4c27e8d4f9e3b5dcfb317404da0cb82aa04c9a6365aa2cda714e619f0d7'),
        ('failed_entry', 'entry01/episode.json', 'cb64cec0472f9a23d176fbf1e98710aee72b0c195f03ca62b60355f7d994213f'),
        ('h06', 'idle_capture01/episode.json', '50a1e8db99fad07b0c49b6c4f71bf564663435c4d2934d0575211df05640bfcd'),
        ('h07', 'idle_capture02/episode.json', '990a1a9ad57d4d9e919c55abeabf52574cf319ebd871433c03f1993b2ec26ffb'),
        ('lobby', 'entry_expired_lobby_readonly01.json', '322e063802fb87578da2f49b56a9adfcf37c68b1aefef9743f3b02d4ab6230f5'),
        ('attestation', 'root_failed_entry_no_input_attestation01.json', '96b1425746c9287675ae309e6622702a7ef422f8363bb7e3d4596f6a3e0296f6'),
        ('offline', 'idle_capture02_preservation_readonly01.json', 'eaf7b8dff49223b145ee9cc25ed9bf4bc95d8fe3581a7c9b532b39cfdb8a42d0'),
        ('failed_image', 'entry01/bags_swap_entered.png', '322ad4584ddaffe7cf6c43ba54bebaa9c39b8fef20bd10b8e01553e1dfe7c76f'),
        ('resources', 'entry_failure_readonly01/facts.json', '707b10512dbdb0fd1645ef4ad90f5c7ff6e3ca4a1357dee3c9b30b487b2caa62'))}
CONFIG = 'experiments/configs/client_harness/442_bag_swap_roundtrip_v1.json'
FIXED = (
    'tools/client_compatibility/item_actionbar_contract.py', 'tools/client_compatibility/item_actionbar_preservation.py',
    'tools/client_compatibility/world/buffer.py', 'tools/client_compatibility/world/native_objects.py',
    'tools/client_compatibility/world/native_transport.py', 'tools/client_compatibility/native_bridge/protocol.cpp',
    'tools/client_compatibility/native_bridge/buffer.cpp', 'tools/client_compatibility/native_bridge/buffer.hpp',
    'tools/client_compatibility/native_bridge/inventory_requests.cpp',
    'tools/client_compatibility/native_bridge/inventory_updates.cpp', 'tools/client_compatibility/native_bridge/native_objects.cpp',
    'tools/client_compatibility/world/native_fields.json', 'tools/client_compatibility/world/fields.json',
    'tools/client_compatibility/interaction_item_actionbar_parked_selection_capture.py', FORMULA,
    'src/server/game/Handlers/ItemHandler.cpp')
OLD_MODULES = ('bag_swap_contract', 'bag_swap_evidence', 'bag_swap_preservation', 'bag_swap_projection',
    'bag_swap_sources', 'checkpoint_bag_swap', 'interaction_bag_swap', 'interaction_bag_swap_continuation',
    'review_bag_swap_checkpoint')
OLD_TESTS = ('continuation', 'contract', 'evidence', 'full_unit', 'operation', 'preservation',
    'projection', 'publication', 'sources')
OLD_MEMBERS = tuple(sorted((CONFIG, *FIXED,
    *('tools/client_compatibility/' + n + '.py' for n in OLD_MODULES),
    *('tools/client_compatibility/world/tests/test_bag_swap_' + n + '.py' for n in OLD_TESTS))))
H_MEMBERS = (
    'tools/client_compatibility/interaction_bag_swap_idle_housekeeping.py',
    'tools/client_compatibility/world/tests/test_bag_swap_idle_housekeeping.py',
    'tools/client_compatibility/interaction_item_actionbar.py', 'tools/client_compatibility/interaction_trial.py',
    'tools/client_compatibility/interaction_item_actionbar_parked_selection_capture.py',
    'tools/client_compatibility/item_actionbar_contract.py', 'tools/client_compatibility/world/buffer.py',
    'tools/client_compatibility/world/native_objects.py', 'tools/client_compatibility/world/native_fields.json',
    'tools/client_compatibility/native_bridge/chat.cpp', 'tools/client_compatibility/native_bridge/client_requests.cpp',
    'tools/client_compatibility/observation/interactions.py')
# H06 failed before retaining a vector. Pin its twelve actual Git objects here;
# the failed receipt stays honestly unchanged and gains no invented field.
_H06_SOURCE_HASHES = (
    'dcbaa8cce90307b89085fe3b9407ae841c63f2b544cbbc07c2419de96c1f88f5',
    'c8d2046fd1f195241a47408180a96bc5123ddcc1a9c25a1cb14abaa8c834e34d',
    'c8d1d02229417f585d36fb742b96396c7ac4729d053e9f9ebcaef46e3e6f4086',
    'e23bb74b41945e7a80febfd815d82797264bb2e40af04a0ee21f6998ee3b01a9',
    '928432b9df8510cf5344cbc4edc045309651cde78260505b3978c1102d8197a3',
    'f82eae605a835dd2b1aa8deb76bc43a4f37dc720128a3441ed83a0a1f3c5594d',
    'ab253b94c854ecd6db839cb7d514ad6eb1631286fd4c6041211023a12402eff1',
    'cd03b82b6c945cd9b38102ac58929b6ec38707e4891ae7169f179308eeb71941',
    '15b87e3f3142d8292cce49c138e46bab167bd86606f9cda1f6c345994ef16b9a',
    '96ccde43f3470585eff48df9f114a48178259ab48f12a605ff4253ce3363cfe5',
    '3873aaa55bc6dd26de35a683e6c2b599752e3b8faddc7e5705761c5da4084c8c',
    'd59239773c99cce04d2dee00860a28c88c07b51aa656d046fb47901fd2dee429')
CURRENT_REQUIRED = frozenset((*H_MEMBERS, *CURRENT_DEPENDENCIES, 'tools/client_compatibility/bag_swap_failed_sources.py',
    'tools/client_compatibility/world/tests/test_bag_swap_failed_sources.py',
    'tools/client_compatibility/bag_swap_failed_contract.py',
    'tools/client_compatibility/world/tests/test_bag_swap_failed_contract.py',
    'tools/client_compatibility/bag_swap_login_sync.py',
    'tools/client_compatibility/world/tests/test_bag_swap_login_sync.py',
    'tools/client_compatibility/interaction_bag_swap_failed_entry_pause.py',
    'tools/client_compatibility/world/tests/test_bag_swap_failed_entry_pause.py',
    'tools/client_compatibility/world/movement.py',
    'tools/client_compatibility/world/native_movement.json',
    'tools/client_compatibility/native_bridge/movement.cpp',
    'tools/client_compatibility/native_bridge/client_requests.cpp',
    'tools/client_compatibility/interaction_trial.py'))
MAX_SOURCES, MAX_SOURCE_BYTES, MAX_TOTAL_BYTES = 128, 4 * 1024 * 1024, 24 * 1024 * 1024
CODE_FIELDS = {'schema', 'code_commit', 'original_path', 'sha256', 'bytes', 'raw_hex'}
EPOCH_FIELDS = {'role', 'code_commit', 'source_ref', 'committed_sources', 'carried_sources'}
PRECISION_CHECKS = frozenset(('all_six_offline', 'all_saved_state_unchanged', 'original_identity',
    'snapshot_rest_matches', 'exact_float32'))
STOP_CHECKS = frozenset(('scout_launcher_absent', 'owned_game_absent', 'all_retained_saved_state',
    'all_characters_offline', 'primary_still_stopped', 'native_lifetime', 'bridge_lifetime', 'origin_registration'))
SCRIPT = {'original': '0', 'current_stock_disabled': '1', 'original_restored': False}


def _pinned(role, ref):
    reference(ref)
    require(strict_equal(ref, _HISTORICAL_SOURCES[role]), 'immutable actual historical ' + role + ' source changed')


def _commit(value):
    require(type(value) is str and re.fullmatch('[0-9a-f]{40}', value), 'actual full code epoch commit required')
    return value


def _vector(refs, repo, members=None):
    require(type(refs) is list and 1 <= len(refs) <= MAX_SOURCES, 'bounded complete code vector required')
    for ref in refs:
        reference(ref)
        require(Path(ref['path']).is_relative_to(repo), 'code member must belong to its actual repository')
    paths = [str(Path(r['path']).relative_to(repo)) for r in refs]
    require(len(set(paths)) == len(paths) and (members is None or tuple(paths) == tuple(members)),
        'exact distinct code member list required')
    return paths


def _repo(ready):
    refs = ready.get('committed_sources')
    require(type(refs) is list, 'original ready code vector required')
    configs = [Path(r['path']) for r in refs if type(r) is dict and type(r.get('path')) is str and
        r['path'].endswith('/' + CONFIG)]
    require(len(configs) == 1, 'one original occupied-swap configuration required')
    repo = configs[0].parents[3]
    _vector(refs, repo, OLD_MEMBERS)
    require(ready.get('code_commit') == C1, 'original ready must retain all 35 actual C1 sources')
    return repo


def _raw(value, sha, size):
    require(type(size) is int and 0 <= size <= MAX_SOURCE_BYTES and type(value) is str and
        len(value) == size * 2 and re.fullmatch('[0-9a-f]*', value), 'bounded canonical complete raw source bytes required')
    raw = bytes.fromhex(value)
    require(type(sha) is str and re.fullmatch('[0-9a-f]{64}', sha) and hashlib.sha256(raw).hexdigest() == sha,
        'full raw source bytes differ from their exact SHA256')
    return raw


def _private(path, root):
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(root / 'evidence') and
        not any(p.is_symlink() for p in (path, *path.parents)), 'ordinary source-owned private evidence path required')
    return path


def _bound_json(ref, root):
    reference(ref)
    path = _private(ref['path'], root)
    require(path.is_file() and path.stat().st_size <= 4 * 1024 * 1024, 'bounded actual failed source receipt required')
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'actual immutable failed source changed')
    return json.loads(raw)


def _git_vector(commit, members, repo):
    _commit(commit)
    result, total = [], 0
    for member in members:
        raw = subprocess.check_output(['git', 'show', commit + ':' + member], cwd=repo)
        total += len(raw)
        require(len(raw) <= MAX_SOURCE_BYTES and total <= MAX_TOTAL_BYTES, 'bounded committed code epoch exceeded')
        result.append(({'path': str(repo / member), 'sha256': hashlib.sha256(raw).hexdigest()}, raw))
    return result


def carry_epochs(ready, failed_h_refs, out, *, preparation_ref=None, current=None, repo=None, root=None):
    """Carry actual C1, both failed helper commits, and the current closure package."""
    original_repo = _repo(ready)
    repo, root = Path(repo or original_repo), Path(root or ROOT)
    require(repo == original_repo and repo.is_absolute() and root.is_absolute() and
        '..' not in repo.parts and '..' not in root.parts, 'one actual ordinary code repository required')
    out = _private(out, root)
    require(out.parent.is_dir() and not out.exists(), 'new immutable private code epoch directory required')
    require(type(failed_h_refs) is list and len(failed_h_refs) == 2, 'both actual failed housekeeping references required')
    _pinned('preparation', preparation_ref)
    for role, ref in zip(('h06', 'h07'), failed_h_refs):
        _pinned(role, ref)
    require(strict_equal(_bound_json(preparation_ref, root), ready), 'ready differs from immutable actual C1 source bytes')
    failed_h = [_bound_json(ref, root) for ref in failed_h_refs]
    require([v.get('code_commit') for v in failed_h] == [H06, H07], 'actual H06/H07 failed commit labels required')
    if current is None:
        from .bag_swap_projection import source_identities
        current = {'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip(),
            'committed_sources': source_identities(repo)}
    _commit(current.get('code_commit'))
    current_members = _vector(current.get('committed_sources'), repo)
    require(set(OLD_MEMBERS) | CURRENT_REQUIRED <= set(current_members) and
        current_members == sorted(current_members) and current['code_commit'] not in (C1, H06, H07),
        'complete actual current failed-closure package required')
    identities = ((C1, OLD_MEMBERS, preparation_ref), (H06, H_MEMBERS, failed_h_refs[0]),
        (H07, H_MEMBERS, failed_h_refs[1]), (current['code_commit'], current_members, None))
    prepared = [_git_vector(commit, members, repo) for commit, members, _ in identities]
    require([ref for ref, _ in prepared[0]] == ready['committed_sources'] and
        [ref for ref, _ in prepared[3]] == current['committed_sources'], 'actual Git bytes differ from frozen C1/current vectors')
    require(tuple(ref['sha256'] for ref, _ in prepared[1]) == _H06_SOURCE_HASHES,
        'actual H06 Git bytes differ from immutable historical object hashes')
    h07 = failed_h[1].get('committed_source_bytes')
    require(type(h07) is list and len(h07) == len(H_MEMBERS) and
        h07 == [{**ref, 'bytes': len(raw), 'raw_hex': raw.hex()} for ref, raw in prepared[2]],
        'actual H07 retained raw code vector differs from its Git commit')
    require('committed_source_bytes' not in failed_h[0], 'H06 missing code vector must remain honestly absent')
    out.mkdir(mode=0o700)
    epochs = []
    for role, (commit, _, source_ref), rows in zip(ROLES, identities, prepared):
        directory = out / role
        directory.mkdir(mode=0o700)
        copies = []
        for index, (ref, raw) in enumerate(rows):
            value = {'schema': CODE_SCHEMA, 'code_commit': commit, 'original_path': ref['path'],
                'sha256': ref['sha256'], 'bytes': len(raw), 'raw_hex': raw.hex()}
            encoded = (json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False) + '\n').encode()
            path = directory / (f'{index:03d}_' + ref['sha256'] + '.json')
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            require(path.read_bytes() == encoded, 'carried code source changed while writing')
            copies.append({'path': str(path), 'sha256': hashlib.sha256(encoded).hexdigest()})
        epochs.append({'role': role, 'code_commit': commit, 'source_ref': source_ref,
            'committed_sources': [ref for ref, _ in rows], 'carried_sources': copies})
    return {'schema': EPOCH_SCHEMA, 'epochs': epochs}


def validate_epochs(store, ready, failed_h, receipt):
    """Re-derive all four full byte epochs without old checkout or Git reads."""
    repo = _repo(ready)
    value = receipt.get('code_epochs')
    require(type(value) is dict and set(value) == {'schema', 'epochs'} and value['schema'] == EPOCH_SCHEMA and
        type(value['epochs']) is list and len(value['epochs']) == 4 and
        [v.get('role') for v in value['epochs']] == list(ROLES), 'four exact ordered original/failed/current code epochs required')
    require(type(failed_h) is list and len(failed_h) == 2, 'both unchanged failed helper receipts required')
    h_refs = receipt.get('failed_housekeeping_sources')
    require(type(h_refs) is list and len(h_refs) == 2, 'both actual failed helper sources required')
    _pinned('preparation', receipt.get('original_preparation_source'))
    require(strict_equal(store.get(receipt['original_preparation_source'], False), ready),
        'original 35-member vector must come from actual pinned ready bytes')
    for role, ref, failed in zip(('h06', 'h07'), h_refs, failed_h):
        _pinned(role, ref)
        require(strict_equal(store.get(ref, False), failed), 'failed helper vector differs from actual pinned source bytes')
    expected_commits = (C1, H06, H07, _commit(receipt.get('code_commit')))
    require(expected_commits[-1] not in expected_commits[:3], 'fresh closed helper package must retain its own actual commit')
    expected_refs = (receipt.get('original_preparation_source'), *h_refs, None)
    all_copies, counts = set(), []
    for epoch, commit, source in zip(value['epochs'], expected_commits, expected_refs):
        require(type(epoch) is dict and set(epoch) == EPOCH_FIELDS and epoch['code_commit'] == commit and
            epoch['source_ref'] == source, 'code epoch commit or original source reference changed')
        if source is not None:
            reference(source)
        members = OLD_MEMBERS if epoch['role'] == 'original' else H_MEMBERS if epoch['role'] in ('h06', 'h07') else None
        paths = _vector(epoch['committed_sources'], repo, members)
        if epoch['role'] == 'original':
            require(epoch['committed_sources'] == ready['committed_sources'], 'original 35 code hashes changed')
        elif epoch['role'] == 'h06':
            require(tuple(ref['sha256'] for ref in epoch['committed_sources']) == _H06_SOURCE_HASHES,
                'H06 carried bytes differ from immutable actual historical Git object hashes')
        elif epoch['role'] == 'current':
            require(epoch['committed_sources'] == receipt.get('committed_sources') and paths == sorted(paths) and
                set(OLD_MEMBERS) | CURRENT_REQUIRED <= set(paths), 'complete current closed helper byte vector changed')
        copies = epoch['carried_sources']
        require(type(copies) is list and len(copies) == len(paths), 'each code member requires one full raw copy')
        raw_vector, total = [], 0
        for ref, copy in zip(epoch['committed_sources'], copies):
            reference(copy)
            require(copy['path'] not in all_copies, 'carried code epoch members may not alias')
            all_copies.add(copy['path'])
            envelope = store.get(copy, False)
            require(type(envelope) is dict and set(envelope) == CODE_FIELDS and envelope['schema'] == CODE_SCHEMA and
                envelope['code_commit'] == commit and envelope['original_path'] == ref['path'] and
                envelope['sha256'] == ref['sha256'], 'raw carried member differs from its epoch/ref')
            raw = _raw(envelope['raw_hex'], envelope['sha256'], envelope['bytes'])
            total += len(raw)
            require(total <= MAX_TOTAL_BYTES, 'bounded complete raw code epoch exceeded')
            raw_vector.append({**ref, 'bytes': len(raw), 'raw_hex': raw.hex()})
        if epoch['role'] == 'h07':
            require(strict_equal(failed_h[1].get('committed_source_bytes'), raw_vector), 'H07 actual retained raw vector changed')
        counts.append(len(paths))
    require([v.get('code_commit') for v in failed_h] == [H06, H07] and
        'committed_source_bytes' not in failed_h[0], 'missing H06 vector may not be invented or relabelled')
    formula = {'path': str(repo / FORMULA), 'sha256': FORMULA_HASH}
    require(formula in ready['committed_sources'] and formula in receipt['committed_sources'],
        'original/current carried native rest formula bytes must match the admitted formula')
    return {'commits': list(expected_commits), 'member_counts': counts, 'all_raw_code_bytes_verified': True}


def _closed(value, phase):
    require(type(value) is dict and value.get('schema') == SCHEMA and value.get('phase') == phase and
        value.get('completed') is True and value.get('failure') is None and finite(value.get('started_at')) and
        finite(value.get('finished_at')) and 0 < value['started_at'] < value['finished_at'], 'actual successful closed failed-entry source required')


def _root(ref):
    reference(ref)
    path = Path(ref['path'])
    require('evidence' in path.parts, 'private original evidence source required')
    return Path(*path.parts[:path.parts.index('evidence')])


def _identity(value, ready):
    require(strict_equal(value.get('actor'), ready.get('actor')) and strict_equal(value.get('runtime'), ready.get('runtime')) and
        value.get('controller') == 'code' and value.get('model') is None and value.get('revision') is None and
        value.get('qualification_added') is False and value.get('custom_script_permission') == 'blocked_by_user' and
        strict_equal(value.get('softTargetInteract'), SCRIPT), 'original actor/runtime/controller/script identity changed')


def _rest_sources(value, repo, root):
    require(type(value) is dict and type(value.get('rate')) in (int, float) and value['rate'] == 1 and
        type(value.get('xp_cap')) is int and value['xp_cap'] == 400 and
        type(value.get('rest_cap')) is int and value['rest_cap'] == 300 and
        type(value.get('wilderness_bubble')) is float and value['wilderness_bubble'] == .031 and
        value.get('formula_snippets') == list(FORMULA_SNIPPETS) and
        value.get('config_source') == {'path': str(root / 'config/worldserver.conf'), 'sha256': CONFIG_HASH} and
        value.get('native_formula_source') == {'path': str(repo / FORMULA), 'sha256': FORMULA_HASH} and
        value.get('native_float_storage_sources') == [{'path': str(repo / p), 'sha256': sha}
            for p, sha in FLOAT_SOURCES.items()], 'actual configured native FLOAT formula source binding required')


def _frame(store, image, source, ready, root):
    reference(source)
    require(type(image) is dict and type(image.get('file')) is str and Path(image['file']).name == image['file'] and
        type(image.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', image['sha256']), 'source-owned exact PNG identity required')
    monitor, original = image.get('monitor', {}), ready.get('frame', {}).get('monitor', {})
    isolation, old = monitor.get('input_isolation', {}), original.get('input_isolation', {})
    require(monitor.get('second_monitor_verified') is True and monitor.get('monitor', {}).get('name') == 'HDMI-1' and
        monitor.get('pid') == ready['runtime']['client']['pid'] and isolation.get('actor') == 'scout' and
        isolation.get('host_activation_sent') is False and
        all(isolation.get(k) == old.get(k) and isolation.get(k) is not None for k in ('game_pid', 'display', 'window_id', 'actor_lock')),
        'same owned private HDMI-1 physical child required')
    path = Path(source['path']).parent / image['file']
    require(path.is_relative_to(root / 'evidence'), 'source-owned PNG must remain private evidence')
    member = str(path.relative_to(root))
    require(getattr(store, 'digests', {}).get(member) == image['sha256'], 'actual source-owned PNG bytes absent or changed')


def _failed_resources(store, failed_h, ready, failed_ref, root):
    image_ref, resources_ref = failed_h.get('original_failed_image'), failed_h.get('original_resources_source')
    _pinned('failed_image', image_ref)
    _pinned('resources', resources_ref)
    require(getattr(store, 'digests', {}).get(str(Path(image_ref['path']).relative_to(root))) == image_ref['sha256'],
        'actual failed-entry PNG bytes absent or changed')
    facts = store.get(resources_ref, False)
    baseline = ready['all_offline_snapshot']
    require(type(facts) is dict and facts.get('entry_source') == failed_ref and
        strict_equal(facts.get('actor'), ready['actor']) and strict_equal(facts.get('runtime'), ready['runtime']) and
        facts.get('session') == ready['native_session'] and facts.get('input_sent') is False and facts.get('mutation_sent') is False and
        finite(facts.get('observed_at')) and facts['observed_at'] < failed_h['started_at'] and
        strict_equal(facts.get('before'), baseline), 'actual failed-entry read-only resources must bind their original entry owner and baseline')
    resources = contract.item_resources(facts.get('resources'))
    require(resources.get('money') == baseline['2']['native']['money'] and
        {(i['guid'] & ((1 << 48) - 1), i['id'], i['count']) for i in
            resources['equipment'] + resources['backpack'] + [i for bag in resources['bags'] for i in bag] if i['guid']} ==
        {(row[3], row[5], row[9]) for row in baseline['2']['inventory']},
        'read-only original native resources must retain every original item and money')
    _frame(store, facts.get('frame'), resources_ref, ready, root)


def failed_contract():
    from . import bag_swap_failed_contract
    return bag_swap_failed_contract


def _source_ref(store, value, root):
    members = [member for member, found in store.data.items() if found is value or strict_equal(found, value)]
    require(len(members) == 1, 'one exact immutable current failed-entry receipt source required')
    member = members[0]
    path = Path(member) if Path(member).is_absolute() else root / member
    ref = {'path': str(path), 'sha256': store.digests.get(member)}
    reference(ref)
    return ref


def _validate_failed(store, value, closing):
    """Common source/facts gate; capture runs this before any owned stop."""
    _closed(value, PHASE if closing else CAPTURE_PHASE)
    refs = [value.get(k) for k in ('original_preparation_source', 'original_entry_source', 'before_precision_source',
        'capture_source', 'review_source', 'lobby_source')]
    for ref in (refs if closing else refs[:3] + refs[5:]):
        reference(ref)
    for role, ref in zip(('preparation', 'failed_entry', 'precision'), refs[:3]):
        _pinned(role, ref)
    _pinned('lobby', refs[5])
    ready, failed, before_precision = [store.get(ref, False) for ref in refs[:3]]
    require(ready.get('phase') == 'bags_swap_scout_ready' and ready.get('completed') is True and ready.get('failure') is None and
        before_precision.get('phase') == 'bags_swap_rest_precision_complete' and before_precision.get('completed') is True and
        before_precision.get('failure') is None and failed.get('phase') == 'bags_swap_entry_started' and
        failed.get('completed') is False and type(failed.get('failure')) is str and failed['failure'] and
        [v.get('code_commit') for v in (ready, before_precision, failed)] == [C1, C1, C1] and
        all(strict_equal(v.get('committed_sources'), ready.get('committed_sources')) for v in (before_precision, failed)),
        'unchanged original C1 ready/preprecision/failed entry sources required')
    for original in (ready, before_precision, failed, value):
        _identity(original, ready)
    h_refs = value.get('failed_housekeeping_sources')
    require(type(h_refs) is list and len(h_refs) == 2, 'both exact failed no-input helper sources required')
    failed_h = [store.get(ref, False) for ref in h_refs]
    for original in failed_h:
        _identity(original, ready)
        require(original.get('completed') is False and type(original.get('failure')) is str and original['failure'] and
            original.get('cases') == original.get('cleanup') == [] and finite(original.get('started_at')) and
            finite(original.get('finished_at')) and 0 < original['started_at'] < original['finished_at'] and
            not any('attempt_source' in key for key in original), 'failed housekeeping must retain no attempted inputs')
    require('phase' not in failed_h[0] and 'input_sent' not in failed_h[0] and 'mutation_sent' not in failed_h[0] and
        failed_h[1].get('phase') == 'bags_swap_idle_housekeeping_started' and failed_h[1].get('input_sent') is False and
        failed_h[1].get('mutation_sent') is False and failed_h[1].get('ordinary_inputs') == [] and
        failed_h[1].get('preparation_source') == refs[0] and failed_h[1].get('original_entry_source') == refs[1],
        'H06 missing fields and H07 no-input failure must remain truthful')
    epochs = validate_epochs(store, ready, failed_h, value)
    root = _root(refs[0])
    _failed_resources(store, failed_h[1], ready, refs[1], root)
    _rest_sources(before_precision.get('rest_sources'), _repo(ready), root)
    baseline = ready.get('all_offline_snapshot')
    contract.owned_snapshot(baseline)
    require(before_precision.get('source') == refs[0] and before_precision.get('before') == before_precision.get('after') == baseline and
        before_precision.get('query') == preservation.PRECISION_QUERY and before_precision.get('input_sent') is False and
        before_precision.get('mutation_sent') is False and strict_equal(before_precision.get('checks'), dict.fromkeys(PRECISION_CHECKS, True)) and
        failed.get('input_sent') is True and failed.get('mutation_sent') is False and failed.get('cases') == failed.get('cleanup') == [] and
        strict_equal(failed.get('native_before_entry'), baseline['2']['native']) and
        strict_equal(failed.get('all_offline_snapshot'), baseline) and 'entered_native' not in failed and
        failed.get('preparation_source') == refs[0] and failed.get('precision_source') == refs[2] and
        all(finite(v.get(k)) for v in (ready, before_precision, failed) for k in ('started_at', 'finished_at')) and
        0 < ready['started_at'] < ready['finished_at'] < before_precision['started_at'] < before_precision['finished_at'] <
            failed['started_at'] < failed['entry_input_finished_at'] <= failed['finished_at'],
        'original exact offline preprecision and one failed login must remain immutable')
    old_exact = preservation.exact_precision(before_precision['row'], baseline)
    now = value.get('before')
    require(strict_equal(value.get('after'), now) and strict_equal(value.get('all_offline_snapshot'), now),
        'fresh failed-entry closure must preserve its complete offline before/after boundary')
    old, current = contract.owned_snapshot(baseline), contract.owned_snapshot(now)
    require(all(strict_equal(now[g], baseline[g]) for g in ('1', '3', '4', '5', '6')) and
        set(current['native']) == set(old['native']) and
        {k for k in old['native'] if not strict_equal(old['native'][k], current['native'][k])} <= preservation.ACCOUNTING | {'rest_bonus'} and
        all(type(v['native'].get(k)) is int and v['native'][k] >= 0 for v in (old, current) for k in preservation.ACCOUNTING) and
        all(current['native'][k] >= old['native'][k] for k in ('totaltime', 'leveltime', 'logout_time')) and
        strict_equal(current['saved'], old['saved']) and current['pets'] == old['pets'] == [],
        'failed-entry closure changed protected/saved native state beyond accounting/rest')
    contract.inventory_rows(old['inventory'], current['inventory'])
    exact = value.get('exact_precision')
    require(type(exact) is dict and set(exact) == {'query', 'row', 'before', 'after', 'source', 'input_sent', 'mutation_sent'} and
        exact.get('query') == preservation.PRECISION_QUERY and
        strict_equal(exact.get('before'), now) and strict_equal(exact.get('after'), now) and
        exact.get('input_sent') is False and exact.get('mutation_sent') is False and
        exact.get('source') == (value['capture_source'] if closing else None),
        'fresh source-bound read-only exact FLOAT boundary required')
    new_exact = preservation.exact_precision(exact.get('row'), now)
    journals = value.get('journal_sources')
    require(type(journals) is dict and set(journals) == {'packets', 'events'}, 'both actual private complete failed-history journals required')
    rows = {}
    root = _root(refs[0])
    for key, ref in journals.items():
        reference(ref)
        require(Path(ref['path']).is_relative_to(root / 'evidence'), 'full failed journal must remain source-owned private evidence')
        member = str(Path(ref['path']).relative_to(root))
        require(getattr(store, 'digests', {}).get(member) == ref['sha256'] and
            type(getattr(store, 'raw_journals', {}).get(member)) is list, 'actual full failed-history journal bytes absent')
        rows[key] = store.raw_journals[member]
    supplied = value.get('failed_history')
    require(type(supplied) is dict and finite(supplied.get('until')) and finite(supplied.get('audit_until')) and
        value['started_at'] <= supplied['audit_until'] <= value['finished_at'] and
        all(type(row) is dict and finite(row.get('time')) and failed['started_at'] <= row['time'] <= supplied['audit_until']
            for values in rows.values() for row in values), 'complete failed journals must cover the actual current receipt audit boundary')
    history = failed_contract().failed_history(rows['packets'], rows['events'], ready, failed,
        supplied.get('audit_until', supplied['until']))
    require(strict_equal(history, supplied), 'failed history differs from complete actual archived journals')
    login_rows = history['login_sync']['login_packets']
    login = contract.login_packets(login_rows, ready['native_session'], failed['started_at'], failed['entry_input_finished_at'])
    matches = []
    for second in range(math.floor(login['request']['time']), math.floor(login['verify']['time']) + 1):
        elapsed = second - old['native']['logout_time']
        if elapsed < 0:
            continue
        gained, text = preservation.native_rest(old_exact['exact_rest_bonus'], elapsed)
        if (gained == new_exact['exact_rest_bonus'] and text == current['native']['rest_bonus'] and
                history['native_original']['rest_threshold'] == int(gained)):
            matches.append({'native_login_second': second, 'offline_seconds': elapsed,
                'before_float32_bits': old_exact['exact_rest_bonus_float32_bits'],
                'after_float32_bits': new_exact['exact_rest_bonus_float32_bits'], 'exact_after': gained})
    require(len(matches) == 1 and current['native']['logout_time'] == math.floor(history['logout']['complete']['time']),
        'excluded saved rest requires one original native login and the actual automatic logout boundary')
    own_ref = _source_ref(store, value, root)
    capture = store.get(refs[3], False) if closing else value
    review = store.get(refs[4], False) if closing else None
    lobby = store.get(refs[5], False)
    _closed(capture, CAPTURE_PHASE)
    _identity(capture, ready)
    require(capture.get('code_commit') == value['code_commit'] and capture.get('committed_sources') == value['committed_sources'] and
        strict_equal(capture.get('before'), now) and strict_equal(capture.get('after'), now) and
        strict_equal(capture.get('exact_precision', {}).get('row'), exact['row']) and
        lobby.get('input_sent') is False and lobby.get('mutation_sent') is False and finite(lobby.get('observed_at')) and
        history['until'] < lobby['observed_at'] <= capture['started_at'], 'source-owned successful capture/review and truthful expired lobby required')
    for image, source in ((ready.get('frame'), refs[0]), (lobby.get('frame'), refs[5]),
            (capture.get('frame'), refs[3] if closing else own_ref), (value.get('frame'), own_ref)):
        _frame(store, image, source, ready, root)
    if closing:
        validate_failed_capture(store, capture)
        require(supplied['audit_until'] >= capture['finished_at'] and
            all(strict_equal(rows[key][:len(store.raw_journals[str(Path(ref['path']).relative_to(root))])],
                store.raw_journals[str(Path(ref['path']).relative_to(root))])
                for key, ref in capture['journal_sources'].items()),
            'closure current journals must retain every original capture row and extend its actual audit boundary')
        frame_ref = value.get('closing_frame_source')
        reference(frame_ref)
        require(frame_ref == {'path': str(Path(own_ref['path']).parent / value['frame']['file']), 'sha256': value['frame']['sha256']} and
            capture['finished_at'] < value['started_at'] and review.get('reviewed') is True and review.get('control') == 'Harnesstwo' and
            review.get('source') == refs[3] and review.get('frame') == capture.get('frame') and
            (review.get('selected_character'), review.get('selected_level')) == ('Harnesstwo', 1),
            'own closing PNG and reviewed exact capture source required')
    attestation_ref = value.get('no_input_attestation_source')
    _pinned('attestation', attestation_ref)
    attestation = store.get(attestation_ref, False)
    require(attestation.get('schema') == 'client442_root_failed_entry_no_input_attestation_v1' and
        finite(attestation.get('attested_at')) and failed_h[1]['finished_at'] <= attestation['attested_at'] <= capture['started_at'] and
        attestation.get('sources', {}).get('preparation') == refs[0] and
        attestation['sources'].get('original_failed_entry') == refs[1] and
        attestation['sources'].get('failed_idle_capture06') == h_refs[0] and
        attestation['sources'].get('failed_idle_capture07') == h_refs[1] and
        attestation['sources'].get('owned_selection') == refs[5] and
        attestation.get('ordinary_enter_world_was_sent') is True and
        attestation.get('original_failed_entry_finished_at') == failed['finished_at'] and
        all(attestation.get(k) is False for k in ('root_gameplay_input_after_original_failed_entry',
            'root_idle_cleanup_input_sent', 'root_swap_input_sent', 'root_logout_input_sent', 'qualification_added')) and
        attestation.get('bag_attempt_markers_found') == [] and
        attestation.get('original_failed_entry_and_failed_idle_captures_excluded') is True and
        attestation.get('custom_script_permission') == 'blocked_by_user' and strict_equal(attestation.get('softTargetInteract'), SCRIPT),
        'actual root no-input attestation must bind every immutable excluded source')
    offline_ref = attestation['sources'].get('current_offline_preservation')
    _pinned('offline', offline_ref)
    offline = store.get(offline_ref, False)
    require(type(offline) is dict and offline.get('input_sent') is False and offline.get('mutation_sent') is False and
        finite(offline.get('observed_at')) and failed_h[1]['finished_at'] <= offline['observed_at'] <= capture['started_at'] and
        offline.get('failed_capture_source') == h_refs[1] and strict_equal(offline.get('baseline'), baseline) and
        strict_equal(offline.get('current'), now), 'actual read-only H07 offline diagnostic must bind original and current complete snapshots')
    require(value.get('input_sent') is False and value.get('mutation_sent') is False and
        value.get('excluded_failed_entry') is True and type(value.get('operations_admitted')) is int and value['operations_admitted'] == 0 and
        all(value.get(k) == ready.get(k) for k in ('predecessor', 'authority_source', 'runtime_authority_source', 'native_session')) and
        strict_equal(value.get('primary_stop_source'), ready.get('predecessor', {}).get('primary_stop')) and
        not any(v.get('schema') == 'client442_bag_swap_consumed_attempt_v1' for v in store.data.values() if type(v) is dict),
        'excluded failed capture requires no bag attempts, qualifications or gameplay inputs')
    if closing:
        require(strict_equal(value.get('shutdown_checks'), dict.fromkeys(STOP_CHECKS, True)) and
            value.get('stop_attempted') is True and value.get('game_before', {}).get('pid') ==
                capture['frame']['monitor']['input_isolation']['game_pid'] and
            type(value.get('game_before', {}).get('start_ticks')) is str and re.fullmatch('[1-9][0-9]*', value['game_before']['start_ticks']),
            'all eight actual owned stops and original private physical lifetime required')
    return {'excluded_failed_entry': True, 'operations_admitted': 0, 'all_six_offline': True,
        'all_six_preserved': True, 'source_code_epochs': epochs, 'native_rest': {'matches': matches},
        'both_owned_clients_stopped': closing, 'shutdown_checks': len(STOP_CHECKS) if closing else 0}


def validate_failed_capture(store, value):
    return _validate_failed(store, value, False)


def validate_failed_pause(store, value):
    return _validate_failed(store, value, True)
