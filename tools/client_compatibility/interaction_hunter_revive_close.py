"""Close a successful ordinary Revive, normal logout and original selection."""
import argparse
import json
import time
from pathlib import Path
from . import actors, lab_runtime as lab
from .hunter_revive_fixture import restored_pets
from .hunter_rest_accrual import preservation as rest_preservation
from .interaction_bridge_deploy import shot
from .interaction_hunter_stable_slots import bound
from .interaction_owned_class_fixture import prepared, SCRIPT_BOUNDARY
from .interaction_parked_client_resource_pause import snapshot
from .interaction_retained_class_fixture import closed
from .interaction_social import actor
from .interaction_trial import Trial


def close(t, preparation, fixture_path, cast_path, park_path, finish_path, cleanup_path, rest_precision=None):
    old = prepared(t, preparation, True)
    fixture, cast, park, finish = [closed(p) for p in (fixture_path, cast_path, park_path, finish_path)]
    cleanup = closed(cleanup_path)
    expected = bound(preparation)
    if (cast.get('phase') != 'owned_revive_cast_complete' or cast.get('dead_fixture_source') != bound(fixture_path) or
        cast.get('fixture_source') != expected or not all(cast.get('capture_checks', {}).values()) or
        not all(cast.get('restoration_checks', {}).values()) or cast.get('input_sent') is not True or
        any(e.get('runtime') != t.receipt['runtime'] for e in (cast, park, finish)) or
        park.get('actor') != old['class_actor'] or park.get('phase') != 'await_original_selection_review' or
        len(park.get('checks', {})) != 4 or not all(park['checks'].values()) or
        finish.get('actor') != old['origin_actor'] or len(finish.get('checks', {})) != 5 or not all(finish['checks'].values()) or
        any(e.get('fixture_source') != expected for e in (park, finish)) or
        not cast['finished_at'] <= park['started_at'] < park['finished_at'] <= finish['started_at'] < finish['finished_at'] or
        cleanup.get('phase') != 'owned_revive_fixture_normalized' or
        cleanup.get('sources') != [bound(p) for p in (fixture_path, cast_path, park_path)] or
        cleanup.get('before', {}).get('6', {}).get('pets') != park['retained_class_pets']):
        raise RuntimeError('successful Revive and normal parked restoration sources differ')
    before = fixture['before']
    after = snapshot()
    hunter = after['6']
    allowed = {'totaltime', 'leveltime', 'logout_time', 'latency'}
    rest = None
    if hunter['native'].get('rest_bonus') != before['6']['native'].get('rest_bonus'):
        if rest_precision is None:
            rest = rest_preservation(before['6']['native'], hunter['native'], cast['entry_source'])
        else:
            rest = rest_preservation(before['6']['native'], hunter['native'], cast['entry_source'], rest_precision)
        allowed.add('rest_bonus')
    elif rest_precision is not None:
        raise RuntimeError('rest precision source requires an observed offline rest change')
    changed = {k for k, v in before['6']['native'].items() if hunter['native'].get(k) != v}
    primary_path = Path(fixture['primary_stop_source']['path'])
    stop = closed(primary_path)
    with actor('primary'): primary_absent = lab.owned_process('client') is None
    checks = {**{f'actor_{g}_unchanged': after[g] == before[g] for g in ('1', '2', '3', '4', '5')},
        'hunter_saved_rows': hunter['saved'] == before['6']['saved'] == park['retained_class_saved'],
        'hunter_inventory': hunter['inventory'] == before['6']['inventory'],
        'hunter_native_columns': changed <= allowed and hunter['native'] == park['retained_class_fixture'],
        'both_pets_restored': restored_pets(before['6']['pets'], hunter['pets']) and after == cleanup.get('after'),
        'hunter_home_pose': all(hunter['native'][k] == before['6']['native'][k] for k in
            ('position_x', 'position_y', 'position_z', 'orientation', 'map')),
        'hunter_full_health': hunter['native']['health'] == before['6']['native']['health'] == 209,
        'all_six_offline': all(v['native']['online'] == 0 for v in after.values()),
        'primary_stopped': primary_absent and after['1'] == stop['after'],
        'original_registration': actors.load() == old['origin_actor'],
        'native_lifetime': fixture['runtime']['worldserver'] == t.receipt['runtime']['worldserver'],
        'bridge_lifetime': fixture['runtime']['modern_world'] == t.receipt['runtime']['modern_world'],
        'one_successful_revive': len(cast['native_cast_requests']) == 1 and cast['native_cast_requests'][0]['spell'] == 982,
        'no_failure_packets': not cast['failure_packets'],
        'ordinary_park_and_selection': True,
        'no_probe': not any((lab.ROOT / 'run' / name).exists() for name in
            ('owned_pet_abandon_probe.json', 'owned_tame_request_probe.json', 'owned_stable_request_probe.json', 'owned_entry_request_probe.json')),
        'fixture_health_restored': next(p for p in hunter['pets'] if p['id'] == 16)['curhealth'] == 278}
    t.receipt.update(sources=[bound(p) for p in (preparation, fixture_path, cast_path, park_path, finish_path, cleanup_path)],
        primary_stop_source=fixture['primary_stop_source'], all_offline_snapshot=after,
        hunter_changed_native_columns=sorted(changed), checks=checks, input_sent=False, qualification_added=False,
        native_rest_accrual_preserved=rest,
        frame=shot(t.out / 'original_offline.png'), completed=all(checks.values()), phase='owned_revive_parked_boundary')
    if len(checks) != 21 or not all(checks.values()):
        raise RuntimeError('Revive offline preservation or disposable health restoration differs')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('preparation', 'fixture', 'cast', 'park', 'finish', 'cleanup', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--rest-precision', type=Path)
    args = parser.parse_args()
    with actor('scout'):
        trial = Trial(args.output, controller='code')
        trial.receipt.update(custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY)
        try: close(trial, args.preparation, args.fixture, args.cast, args.park, args.finish, args.cleanup, args.rest_precision)
        except Exception as error: trial.receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
        finally:
            trial.receipt['finished_at'] = time.time()
            trial.persist()
        print(json.dumps({k: trial.receipt.get(k) for k in ('completed', 'phase', 'failure', 'checks')}), flush=True)
