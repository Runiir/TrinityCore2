"""Bind ordinary1462 work to the accepted normalized UI169 remote boundary."""
from copy import deepcopy
import json
from pathlib import Path

from . import lab_runtime as lab
from .hunter_learn_contract import require, untrained_boundary
from .hunter_rest_accrual import bound

POINTER = 'artifacts/client_harness/442_interactions_20261007_169.tar.gz.dvc'
ARCHIVE_SHA256 = '779300493370b4c70724acf17168c15dc5f50ea756ff6a4f9203e8ba78b16dae'
ARCHIVE_BYTES = 182381021
REMOTE_SHA256 = 'fd0e683acc1a96b41e492437cc86b50c5d1c2bc14095c855e8abe3b96a9e9f32'
REMOTE_NAME = 'ui169_revive_remote_review01.json'
CHECKPOINT_SHA256 = 'dc8ba2683419e5a51599157dfaecce997d3e49f10a11e6237811370b596afe55'


def private_json(path, episode=True):
    path = Path(path)
    require(not path.is_symlink() and path.is_file() and path.resolve().is_relative_to(lab.ROOT / 'evidence'),
        'requires an unchanged private owned source')
    if episode:
        require(path.name == 'episode.json', 'requires a private closed episode')
    return json.loads(path.read_text())


def closed(path):
    value = private_json(path)
    require(value.get('completed') is True and value.get('failure') is None and
        type(value.get('started_at')) in (int, float) and type(value.get('finished_at')) in (int, float) and
        value['started_at'] < value['finished_at'], 'source episode is not closed and successful')
    return value


def linked(ref):
    require(set(ref) == {'path', 'sha256'}, 'source reference is incomplete')
    path = Path(ref['path'])
    value = closed(path)
    require(bound(path) == ref, 'source episode digest differs')
    return value


def whole(value, key, count):
    checks = value.get(key, {})
    require(len(checks) == count and all(v is True for v in checks.values()), 'complete ' + key + ' differ')


def remote_admission(path, checkpoint, paths):
    remote = private_json(path, False)
    require(Path(path).name == REMOTE_NAME and lab.sha256(path) == REMOTE_SHA256 and
        remote.get('schema') == 'client442_native_feedback_remote_review_v1' and
        remote.get('actual_remote_verified') is True and remote.get('complete_json_png_verified') is True and
        remote.get('pointer') == POINTER and remote.get('archive_sha256') == ARCHIVE_SHA256 and
        remote.get('bytes') == ARCHIVE_BYTES, 'actual UI169 remote semantic review is required')
    expected = {'operation': 'pets.revive', 'owner': 6, 'pet_number': 16, 'native_requests': 1,
        'modern_requests': 1, 'native_dead_to_alive': True, 'capture_checks': 18, 'restoration_checks': 17,
        'closure_checks': 21, 'shutdown_checks': 8, 'all_six_offline': True,
        'both_owned_clients_stopped': True, 'named_pet_preserved': 4, 'qualification_added': False}
    require(all(type(remote.get('proof', {}).get(k)) is type(v) and remote['proof'][k] == v
        for k, v in expected.items()), 'UI169 remote proof is incomplete or for another operation')
    require(checkpoint.get('file', '') + '.dvc' == POINTER and checkpoint.get('sha256') == ARCHIVE_SHA256 and
        checkpoint.get('bytes') == ARCHIVE_BYTES and checkpoint.get('cloud_verified') is True,
        'UI169 checkpoint differs from actual remote authority')
    for path in paths:
        member = str(Path(path).resolve().relative_to(lab.ROOT))
        rows = [r for r in checkpoint.get('file_manifest', []) if r.get('path') == member]
        require(len(rows) == 1 and rows[0].get('sha256') == lab.sha256(path),
            'normalized continuation source differs from verified remote manifest')
    return remote


def continuation(preparation, normalization, closure, pause, remote):
    paths = [Path(p) for p in (preparation, normalization, closure, pause)]
    old, normalized, parked, stopped = [closed(p) for p in paths]
    require(old.get('phase') == 'await_owned_class_lobby_review' and
        old.get('origin_actor', {}).get('guid') == 2 and old.get('actor') == old.get('origin_actor') and
        old.get('class_actor', {}).get('guid') == 6 and
        normalized.get('phase') == 'owned_revive_fixture_normalized' and
        parked.get('phase') == 'owned_revive_parked_boundary' and
        stopped.get('phase') == 'parked_scout_resource_paused', 'accepted normalized Hunter source phases differ')
    whole(old, 'checks', 8)
    whole(parked, 'checks', 21)
    whole(stopped, 'checks', 8)
    refs = parked.get('sources', [])
    require(len(refs) == 6 and refs[0] == bound(paths[0]) and refs[5] == bound(paths[1]) and
        normalized.get('sources') == [refs[n] for n in (1, 2, 3)] and
        stopped.get('source') == bound(paths[2]) and
        stopped.get('primary_stop_source') == parked.get('primary_stop_source'),
        'normalized-close-pause source roles or hashes differ')
    ancestors = [linked(ref) for ref in refs]
    fixture, cast, park, finish = [ancestors[n] for n in (1, 2, 3, 4)]
    whole(cast, 'capture_checks', 18)
    whole(cast, 'restoration_checks', 17)
    whole(park, 'checks', 4)
    whole(finish, 'checks', 5)
    require(cast.get('phase') == 'owned_revive_cast_complete' and
        park.get('phase') == 'await_original_selection_review' and
        normalized.get('before', {}).get('6', {}).get('pets') == park.get('retained_class_pets') and
        all(e.get('runtime') == old.get('runtime') for e in (normalized, parked, stopped, cast, park, finish)) and
        all(e.get('actor') == old['origin_actor'] for e in (parked, stopped, finish)) and
        all(e.get('actor') == old['class_actor'] for e in (normalized, cast, park)),
        'whole accepted Revive actor or runtime ancestry differs')
    expected = deepcopy(normalized['before'])
    pets = {p['id']: p for p in expected['6']['pets']}
    require(set(pets) == {4, 16}, 'exact normalized pet identities are required')
    pets[16]['curhealth'] = 278
    pets[16]['CreatedBySpell'] = 13481
    after = normalized.get('after')
    require(after == normalized.get('expected_after') == expected == parked.get('all_offline_snapshot') ==
        stopped.get('before') == stopped.get('after') and
        normalized.get('input_sent') is False and normalized.get('qualification_added') is False and
        parked.get('input_sent') is False and parked.get('qualification_added') is False and
        stopped.get('input_sent') is False and stopped.get('qualification_added') is False,
        'exact normalization delta and immutable offline pause differ')
    untrained_boundary(after)
    require(all(after[str(g)] == fixture['before'][str(g)] == old['protected_baseline'][str(g)] for g in range(1, 6)) and
        after['6']['saved'] == old['natural_saved'] and
        old['finished_at'] < cast['started_at'] < cast['finished_at'] <= park['started_at'] < park['finished_at'] <=
        normalized['started_at'] < normalized['finished_at'] < parked['started_at'] < parked['finished_at'] <
        stopped['started_at'] < stopped['finished_at'], 'continuation chronology or protected state differs')
    stop = linked(parked['primary_stop_source'])
    whole(stop, 'checks', 8)
    require(stop.get('phase') == 'user_requested_primary_client_stopped' and stop.get('before') == stop.get('after') == after['1'],
        'original primary stop source differs')
    checkpoint_path = paths[2].parent.parent / 'checkpoint_receipt.json'
    checkpoint = private_json(checkpoint_path, False)
    require(lab.sha256(checkpoint_path) == CHECKPOINT_SHA256, 'accepted UI169 checkpoint receipt digest differs')
    remote_admission(remote, checkpoint, [*paths, *[Path(ref['path']) for ref in refs]])
    return {'preparation': old, 'normalization': normalized, 'closure': parked, 'pause': stopped,
        'snapshot': after, 'sources': [bound(p) for p in paths], 'remote_source': bound(remote),
        'checkpoint_source': bound(checkpoint_path), 'primary_stop_source': parked['primary_stop_source']}
