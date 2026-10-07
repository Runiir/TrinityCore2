"""Restore only original offline disposable-pet health/creator after live Revive."""
import argparse
from copy import deepcopy
import json
import time
from pathlib import Path
from . import lab_runtime as lab
from .hunter_revive_fixture import restored_pets
from .interaction_bridge_deploy import identity
from .interaction_hunter_stable_slots import bound
from .interaction_parked_client_resource_pause import snapshot
from .interaction_retained_class_fixture import closed
from .interaction_social import actor


def normalize(output, fixture_path, cast_path, park_path):
    started = time.time()
    fixture, cast, park = [closed(p) for p in (fixture_path, cast_path, park_path)]
    if (cast.get('phase') != 'owned_revive_cast_complete' or cast.get('dead_fixture_source') != bound(fixture_path) or
        not cast.get('capture_checks') or not all(cast['capture_checks'].values()) or
        not cast.get('restoration_checks') or not all(cast['restoration_checks'].values()) or
        park.get('phase') != 'await_original_selection_review' or len(park.get('checks', {})) != 4 or
        not all(park['checks'].values()) or park.get('fixture_source') != cast.get('fixture_source') or
        park['runtime'] != cast['runtime'] or not cast['finished_at'] < park['started_at']):
        raise RuntimeError('successful ordinary Revive and normal offline park differ')
    before = snapshot()
    old = fixture['before']['6']['pets']
    current = before['6']['pets']
    if (any(v['native']['online'] for v in before.values()) or before['6']['native'] != park['retained_class_fixture'] or
        len(current) != 2 or current[0] != old[0] or current != park['retained_class_pets'] or
        current[1]['id'] != 16 or current[1]['curhealth'] != cast['native_pet_max_health'] or
        current[1]['CreatedBySpell'] not in (13481, 883) or current[1]['savetime'] < old[1]['savetime'] or
        {k: v for k, v in current[1].items() if k not in ('curhealth', 'CreatedBySpell', 'savetime')} !=
        {k: v for k, v in old[1].items() if k not in ('curhealth', 'CreatedBySpell', 'savetime')} or
        any(before[g] != fixture['before'][g] for g in ('1', '2', '3', '4', '5'))):
        raise RuntimeError('offline pet differs beyond source-backed reload/call metadata')
    native, bridge = identity('worldserver'), identity('modern_world')
    if native != park['runtime']['worldserver'] or bridge != park['runtime']['modern_world']:
        raise RuntimeError('native or bridge lifetime changed')
    if output.exists() or not output.resolve().is_relative_to(lab.ROOT / 'evidence'):
        raise ValueError('requires a new private normalization episode')
    output.mkdir(parents=True, mode=0o700)
    expected = deepcopy(before)
    expected['6']['pets'][1]['curhealth'] = old[1]['curhealth']
    expected['6']['pets'][1]['CreatedBySpell'] = old[1]['CreatedBySpell']
    receipt = {'schema': 'client442_revive_offline_fixture_normalization_v1', 'started_at': started,
        'actor': park['actor'], 'runtime': park['runtime'], 'controller': 'code', 'model': None, 'revision': None,
        'cases': [], 'completed': False, 'failure': None, 'sources': [bound(p) for p in (fixture_path, cast_path, park_path)],
        'before': before, 'expected_after': expected, 'input_sent': False, 'qualification_added': False,
        'scope': 'Offline fixture cleanup only. Restore original Wolf16 saved health278 and tame creator13481; '
            'the recorded live Revive outcome is untouched. Stored Harnesswolf4 remains exact.'}
    def persist(): lab.private_write(output / 'episode.json', json.dumps(receipt, indent=2) + '\n')
    persist()
    try:
        if snapshot() != before: raise RuntimeError('offline snapshot changed before normalization')
        with lab.connection() as connection, connection.cursor() as cursor:
            cursor.execute('UPDATE client442_characters.character_pet SET curhealth=%s,CreatedBySpell=%s '
                'WHERE id=16 AND owner=6 AND slot=0 AND active=1 AND curhealth=%s AND CreatedBySpell=%s AND savetime=%s '
                'AND NOT EXISTS (SELECT 1 FROM client442_characters.characters WHERE guid=6 AND online<>0)',
                (old[1]['curhealth'], old[1]['CreatedBySpell'], current[1]['curhealth'], current[1]['CreatedBySpell'], current[1]['savetime']))
            if cursor.rowcount != 1: raise RuntimeError('exact disposable offline pet normalization did not match once')
        after = snapshot()
        if after != expected or not restored_pets(old, after['6']['pets']):
            raise RuntimeError('offline normalization changed more than declared disposable metadata')
        receipt.update(after=after, completed=True, phase='owned_revive_fixture_normalized')
    except Exception as error:
        receipt['failure'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        receipt['finished_at'] = time.time()
        persist()
    print(json.dumps({'completed': True, 'normalized_pet': 16, 'qualification_added': False}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('output', 'fixture', 'cast', 'park'): parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    with actor('scout'): normalize(args.output, args.fixture, args.cast, args.park)
