"""Read-only immutable authority for actor2 continuation after admitted UI170."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from .item_actionbar_contract import require, finite, owned_snapshot, strict_equal

ROOT = Path.home() / '.local/share/trinity-client442-lab'
REPO = Path(__file__).resolve().parents[2]
POINTER_PATTERN = r'artifacts/client_harness/442_interactions_[0-9]{8}_170\.tar\.gz\.dvc'
CLOSURE_NAMES = frozenset(('untrained_owned_baseline', 'accepted_previous_remote',
    'same_native_bridge_client', 'ordinary_untrained_entry', 'stock_future_caption',
    'existing_trainer', 'available_selected_lesson', 'one_exact_purchase',
    'ordered_native_modern_learn', 'saved_direct_spell_only', 'exact_resource_charge',
    'stock_learned_caption', 'original_stock_layout', 'original_exact_pose',
    'first_ordinary_logout', 'first_exact_rest_accounting', 'first_pet_preservation',
    'exact_offline_cleanup', 'restored_ordinary_reentry', 'restored_future_caption',
    'final_ordinary_logout', 'final_exact_rest_accounting', 'final_pet_preservation',
    'original_selection_restored', 'all_six_offline', 'protected_actors_unchanged',
    'primary_remains_stopped', 'no_qualification_added'))
PAUSE_NAMES = frozenset(('scout_launcher_absent', 'owned_game_absent', 'all_retained_saved_state',
    'all_characters_offline', 'primary_still_stopped', 'native_lifetime', 'bridge_lifetime', 'origin_registration'))
ROLES = frozenset(('preparation', 'purchase', 'restoration', 'first_park', 'first_precision',
    'cleaned', 'reentry', 'final_park', 'final_precision', 'finish'))
FLOAT_SOURCES = {
    'src/server/database/Database/Field.cpp': 'eed8ddfa345c74109afa258db9f72c1d7e828e069c4ca1caf7e4ea0275e7b662',
    'src/server/database/Database/QueryResult.cpp': '56ac195234501b795956949846de208c8e5ab2fdaeeee29a56291a404ce6bdc1',
    'src/server/database/Database/MySQLPreparedStatement.cpp': '11dcd2db84b932850149ce4bad4107ba717c07d96c495e58577a91eec5bd4553',
    'sql/base/characters_database.sql': '880d4c7a92c600dd1cbdb4f3a1f388a4631de0cc08a34e176e078a6d8ea03be9'}
FORMULA = 'src/server/game/Entities/Player/Player.cpp'
FORMULA_HASH = 'ca09174ed5c4c2afaa5aeaf188c52282a622da11e19fd0059cdd77b0748771f3'
CONFIG_HASH = 'c41c11b4c6f38113a0cbf355fa80f279d0c70b6469c1a6f8392e9123412e75f7'
FORMULA_SNIPPETS = ('float bubble0 = 0.031f;',
    'bubble0*sWorld->getRate(RATE_REST_OFFLINE_IN_WILDERNESS)',
    'SetRestBonus(GetRestBonus() + time_diff*((float)GetUInt32Value(PLAYER_NEXT_LEVEL_XP) / 72000)*bubble);')


def bound(path):
    path = Path(path)
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)), 'source must be an ordinary immutable file')
    return {'path': str(path.resolve()), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def reference(ref):
    require(type(ref) is dict and set(ref) == {'path', 'sha256'} and type(ref['path']) is str and
        Path(ref['path']).is_absolute() and '..' not in Path(ref['path']).parts and
        type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}', ref['sha256']), 'complete original source reference is required')
    return ref


def private_json(path, episode=True, *, root=None):
    path, root = Path(path), Path(root or ROOT)
    require(path.is_absolute() and '..' not in path.parts and path.is_relative_to(root / 'evidence') and
        path.suffix == '.json' and (not episode or path.name == 'episode.json'), 'source must be private evidence JSON')
    bound(path)
    try:
        value = json.loads(path.read_text())
    except (ValueError, UnicodeError) as error:
        raise RuntimeError('private source is not valid JSON') from error
    require(type(value) is dict, 'private source must be a JSON object')
    return value


def closed(path, *, root=None):
    value = private_json(path, root=root)
    require(Path(path).name == 'episode.json' and value.get('completed') is True and value.get('failure') is None and
        finite(value.get('started_at')) and finite(value.get('finished_at')) and
        0 < value['started_at'] < value['finished_at'], 'source episode must be closed and successful')
    return value


def linked(ref, successful=True, *, root=None):
    reference(ref)
    value = closed(ref['path'], root=root) if successful else private_json(ref['path'], root=root)
    require(type(successful) is bool and bound(ref['path']) == ref, 'source reference digest differs')
    if not successful:
        require(value.get('completed') is False and type(value.get('failure')) is str and value['failure'] and
            finite(value.get('started_at')) and finite(value.get('finished_at')) and
            value['started_at'] < value['finished_at'], 'actual immutable closed failed source is required')
    return value


def whole(value, names):
    require(type(value) is dict and set(value) == names and all(v is True for v in value.values()),
        'complete exact typed source checks are required')


def dvc_pointer(checkpoint, remote, *, repo=None):
    pointer = remote.get('pointer')
    require(type(pointer) is str and re.fullmatch(POINTER_PATTERN, pointer) and
        checkpoint.get('file', '') + '.dvc' == pointer and type(checkpoint.get('bytes')) is int and
        checkpoint['bytes'] > 0 and type(checkpoint.get('sha256')) is str and
        re.fullmatch('[0-9a-f]{64}', checkpoint['sha256']) and checkpoint.get('cloud_verified') is True and
        type(remote.get('bytes')) is int and remote['bytes'] == checkpoint['bytes'] and
        remote.get('archive_sha256') == checkpoint['sha256'], 'actual UI170 checkpoint archive identity differs')
    path = Path(repo or REPO) / pointer
    ref = bound(path)
    text = path.read_text()
    hashes = re.findall(r'^\s*-?\s*md5:\s*([0-9a-f]{32})\s*$', text, re.MULTILINE)
    sizes = re.findall(r'^\s*size:\s*([0-9]+)\s*$', text, re.MULTILINE)
    paths = re.findall(r'^\s*path:\s*(\S+)\s*$', text, re.MULTILINE)
    require(len(hashes) == len(sizes) == len(paths) == 1 and int(sizes[0]) == checkpoint['bytes'] and
        paths[0] == Path(checkpoint['file']).name and re.search(r'^\s*hash:\s*md5\s*$', text, re.MULTILINE),
        'published UI170 DVC pointer object identity differs')
    return {'source': ref, 'pointer': pointer, 'oid': hashes[0], 'bytes': checkpoint['bytes']}


def source_bundle(closure, pause, remote, checkpoint, primary_stop, *, root=None, repo=None):
    """Admit only supplied real closure bytes already reviewed on the actual remote."""
    root = Path(root or ROOT)
    c, p, stop = [closed(v, root=root) for v in (closure, pause, primary_stop)]
    r, cp = [private_json(v, False, root=root) for v in (remote, checkpoint)]
    refs = {k: bound(v) for k, v in {'closure': closure, 'pause': pause, 'remote': remote,
        'checkpoint': checkpoint, 'primary_stop': primary_stop}.items()}
    pointer = dvc_pointer(cp, r, repo=repo)
    result = validate_bundle({'closure': c, 'pause': p, 'remote': r, 'checkpoint': cp,
        'primary_stop': stop, 'dvc_pointer': pointer}, refs)
    for role, path in {'closure': closure, 'pause': pause}.items():
        rows = [v for v in cp['file_manifest'] if v['path'] == str(Path(path).relative_to(root))]
        require(len(rows) == 1 and rows[0]['bytes'] == Path(path).stat().st_size,
            'actual closure or shutdown size differs from the remote-reviewed manifest')
    require(all(bound(path) == refs[role] for role, path in {'closure': closure, 'pause': pause,
        'remote': remote, 'checkpoint': checkpoint, 'primary_stop': primary_stop}.items()), 'source bytes changed during admission')
    return result


def validate_bundle(values, refs):
    """Portable semantic validation over archive values and their actual original digests."""
    require(type(values) is dict and set(values) == {'closure', 'pause', 'remote', 'checkpoint', 'primary_stop', 'dvc_pointer'} and
        type(refs) is dict and set(refs) == {'closure', 'pause', 'remote', 'checkpoint', 'primary_stop'},
        'complete predecessor values and original reference roles are required')
    for ref in refs.values():
        reference(ref)
    c, p, r, cp, stop, pointer = [values[k] for k in ('closure', 'pause', 'remote', 'checkpoint', 'primary_stop', 'dvc_pointer')]
    require(all(type(v) is dict for v in (c, p, r, cp, stop, pointer)), 'predecessor values must be objects')
    for value in (c, p, stop):
        require(value.get('completed') is True and value.get('failure') is None and finite(value.get('started_at')) and
            finite(value.get('finished_at')) and 0 < value['started_at'] < value['finished_at'],
            'predecessor episode is not closed and successful')
    require(c.get('schema') == 'client442_owned_hunter_learn_closure_v1' and
        c.get('phase') == 'hunter_learn_parked_boundary' and c.get('actor', {}).get('guid') == 2 and
        c.get('input_sent') is False and c.get('mutation_sent') is False and c.get('qualification_added') is False,
        'actual successful ordinary-learning parked closure is required')
    whole(c.get('checks'), CLOSURE_NAMES)
    require(type(c.get('sources')) is dict and ROLES <= set(c['sources']) <= ROLES | {'first_normalization', 'final_normalization'},
        'complete learning closure source roles differ')
    for ref in c['sources'].values():
        reference(ref)
    snapshot = c.get('all_offline_snapshot')
    owned_snapshot(snapshot)
    require(p.get('phase') == 'hunter_learn_scout_resource_paused' and p.get('source') == refs['closure'] and
        strict_equal(p.get('runtime'), c.get('runtime')) and strict_equal(p.get('actor'), c.get('actor')) and
        p.get('primary_stop_source') == c.get('primary_stop_source') == refs['primary_stop'] and
        strict_equal(p.get('before'), snapshot) and strict_equal(p.get('after'), snapshot) and p.get('input_sent') is False and
        p.get('qualification_added') is False and p.get('action') == 'stop_parked_scout_after_learning_restoration' and
        p.get('controller') == 'code' and p.get('model') is None and
        p.get('custom_script_permission') == 'blocked_by_user' and c['finished_at'] < p['started_at'],
        'whole paused six-actor learning boundary or chronology differs')
    whole(p.get('checks'), PAUSE_NAMES)
    def lifetime(value):
        return (type(value) is dict and type(value.get('pid')) is int and value['pid'] > 0 and
            type(value.get('start_ticks')) is str and re.fullmatch('[1-9][0-9]*', value['start_ticks']) is not None)

    require(lifetime(p.get('game_before')), 'owned stopped game lifetime is required')
    require(type(c.get('runtime')) is dict and set(c['runtime']) >= {'worldserver', 'modern_world', 'client'} and
        all(lifetime(c['runtime'][k]) for k in ('worldserver', 'modern_world', 'client')),
        'same exact native, bridge and stopped launcher lifetimes are required')
    require(stop.get('phase') == 'user_requested_primary_client_stopped' and
        strict_equal(stop.get('before'), snapshot['1']) and strict_equal(stop.get('after'), snapshot['1']), 'original stopped primary snapshot differs')
    require(type(stop.get('checks')) is dict and len(stop['checks']) == 8 and all(v is True for v in stop['checks'].values()),
        'complete original primary shutdown checks are required')
    expected = {'operation': 'spellbook.learn_spell', 'owner': 6, 'spell': 1462, 'native_purchases': 1,
        'native_learn_events': 1, 'modern_learn_events': 1, 'cleanup_removed_spell': 1462,
        'cleanup_refund': 646, 'restored_untrained_reentry': True, 'all_six_offline': True,
        'primary_stopped': True, 'qualification_added': False, 'closure_checks': 28}
    proof = c.get('proof', {})
    require(type(proof) is dict and all(type(proof.get(k)) is type(v) and proof[k] == v for k, v in expected.items()),
        'complete1462 learning closure semantic proof differs')
    require(r.get('schema') == 'client442_hunter_learn_remote_review_v1' and r.get('actual_remote_verified') is True and
        r.get('complete_json_png_verified') is True and r.get('qualification_added') is False and
        finite(r.get('reviewed_at')) and r['reviewed_at'] >= p['finished_at'] and
        strict_equal(r.get('proof'), {**proof, 'shutdown_checks': 8, 'both_owned_clients_stopped': True,
            'actual_packet_journals_verified': True}), 'actual complete UI170 remote semantic review is required')
    require(type(r.get('pointer')) is str and re.fullmatch(POINTER_PATTERN, r['pointer']) and
        cp.get('file', '') + '.dvc' == r['pointer'] and cp.get('cloud_verified') is True and
        type(cp.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', cp['sha256']) and
        type(cp.get('bytes')) is int and cp['bytes'] > 0 and type(r.get('bytes')) is int and
        r['bytes'] == cp['bytes'] and r.get('archive_sha256') == cp['sha256'] and
        pointer.get('pointer') == r['pointer'] and type(pointer.get('oid')) is str and
        re.fullmatch('[0-9a-f]{32}', pointer['oid']) and type(pointer.get('bytes')) is int and
        pointer['bytes'] == cp['bytes'], 'actual UI170 remote/checkpoint/DVC pointer identity differs')
    reference(pointer.get('source'))
    require(Path(pointer['source']['path']).as_posix().endswith('/' + r['pointer']), 'DVC pointer original source path differs')
    manifest = cp.get('file_manifest')
    require(type(manifest) is list and bool(manifest) and all(type(v) is dict and type(v.get('path')) is str and
        not Path(v['path']).is_absolute() and '..' not in Path(v['path']).parts and
        type(v.get('bytes')) is int and v['bytes'] >= 0 and type(v.get('sha256')) is str and
        re.fullmatch('[0-9a-f]{64}', v['sha256']) for v in manifest) and
        len({v['path'] for v in manifest}) == len(manifest), 'complete unique checkpoint file manifest is required')
    for role in ('closure', 'pause'):
        path = Path(refs[role]['path'])
        require('evidence' in path.parts, 'source reference lacks its original private evidence boundary')
        member = str(Path(*path.parts[path.parts.index('evidence'):]))
        rows = [v for v in manifest if v['path'] == member]
        require(len(rows) == 1 and rows[0]['sha256'] == refs[role]['sha256'],
            'actual closure or shutdown bytes differ from the remote-reviewed manifest')
    return deepcopy({'closure': c, 'pause': p, 'snapshot': snapshot, 'sources': [refs['closure'], refs['pause']],
        'remote_source': refs['remote'], 'checkpoint_source': refs['checkpoint'], 'primary_stop_source': refs['primary_stop'],
        'predecessor': refs, 'dvc_pointer': pointer, 'runtime': c['runtime'], 'origin_actor': c['actor'], 'remote_proof': r['proof']})


def prepared(value):
    require(type(value) is dict and value.get('phase') == 'item_actionbar_scout_ready' and value.get('completed') is True and
        value.get('failure') is None and value.get('actor', {}).get('guid') == 2 and
        finite(value.get('started_at')) and finite(value.get('finished_at')) and value['started_at'] < value['finished_at'],
        'closed original-scout ready preparation is required')
    own = owned_snapshot(value.get('all_offline_snapshot'))
    require(type(own['native'].get('activeTalentGroup')) is int and own['native']['activeTalentGroup'] in (0, 1) and
        type(value.get('predecessor')) is dict and set(value['predecessor']) == {'closure', 'pause', 'remote', 'checkpoint', 'primary_stop'},
        'ready active spec or predecessor roles differ')
    for ref in value['predecessor'].values():
        reference(ref)
    return deepcopy(value)


def rest_sources(config=None, repo=None):
    repo, config = Path(repo or REPO), Path(config or ROOT / 'config/worldserver.conf')
    formula = repo / FORMULA
    rates = re.findall(r'^\s*Rate\.Rest\.Offline\.InWilderness\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(?:#.*)?$',
        config.read_text(), re.MULTILINE)
    require(rates == ['1'] and bound(config)['sha256'] == CONFIG_HASH and bound(formula)['sha256'] == FORMULA_HASH and
        all(v in formula.read_text() for v in FORMULA_SNIPPETS), 'exact configured rate1/native wilderness rest source differs')
    storage = [bound(repo / path) for path in FLOAT_SOURCES]
    require(all(ref['sha256'] == FLOAT_SOURCES[str(Path(ref['path']).relative_to(repo))] for ref in storage),
        'exact native FLOAT storage implementation differs')
    return {'rate': 1, 'xp_cap': 400, 'rest_cap': 300, 'wilderness_bubble': .031,
        'config_source': bound(config), 'native_formula_source': bound(formula),
        'formula_snippets': list(FORMULA_SNIPPETS), 'native_float_storage_sources': storage}
