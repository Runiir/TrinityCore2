"""Close failed Revive evidence after exact fixture cleanup and ordinary parking."""
import argparse
import json
import time
from pathlib import Path
from . import actors, lab_runtime as lab
from .hunter_revive_failed_fixture import sources, offline_restore, ORIGIN_CHECKS, ALLOWED_HUNTER_COLUMNS
from .hunter_revive_fixture import restored_pets
from .hunter_rest_accrual import preservation as rest_preservation
from . import hunter_revive_restoration_failure as restoration
from .interaction_bridge_deploy import shot
from .interaction_hunter_stable_slots import bound
from .interaction_owned_class_fixture import prepared, SCRIPT_BOUNDARY
from .interaction_parked_client_resource_pause import snapshot
from .interaction_retained_class_fixture import closed
from .interaction_social import actor
from .interaction_trial import Trial


def close(t, preparation, fixture_path, cast_path, park_path, finish_path, cleanup_path):
    finish, cleanup = [closed(p) for p in (finish_path, cleanup_path)]
    post_proof = cleanup.get('post_revive_restoration_failure_proof')
    old = prepared(t, preparation, True)
    checked_old, fixture, cast, park = sources(preparation, fixture_path, cast_path, park_path,
        post_proof.get('raw_packets') if post_proof else None)
    if cast.get('failure') == restoration.FAILURE:
        if (not post_proof or cleanup.get('failed_cast_variant') != restoration.VARIANT or
            cleanup.get('normalized_columns') != ['CreatedBySpell'] or
            post_proof != restoration.proof(cast, post_proof.get('raw_packets'))):
            raise RuntimeError('post-Revive restoration failure actual native proof differs')
    elif post_proof:
        raise RuntimeError('post-Revive native proof cannot reclassify the earlier dead-corpse failure')
    refs = [bound(p) for p in (preparation, fixture_path, cast_path, park_path)]
    rest = None
    if cleanup.get('before', {}).get('6', {}).get('native', {}).get('rest_bonus') != fixture['before']['6']['native'].get('rest_bonus'):
        rest = rest_preservation(fixture['before']['6']['native'], cleanup['before']['6']['native'], cast['entry_source'])
    if (old != checked_old or cast['runtime'] != t.receipt['runtime'] or finish.get('runtime') != cast['runtime'] or
        finish.get('actor') != old['origin_actor'] or finish.get('fixture_source') != bound(preparation) or
        set(finish.get('checks', {})) != ORIGIN_CHECKS | {'origin_registration', 'class_offline'} or
        not all(v is True for v in finish['checks'].values()) or
        not park['finished_at'] <= finish['started_at'] < finish['finished_at'] or
        cleanup.get('schema') != 'client442_failed_revive_offline_cleanup_v1' or
        cleanup.get('phase') != ('owned_revive_restoration_failure_fixture_normalized' if post_proof else
            'owned_failed_revive_fixture_normalized') or cleanup.get('sources') != refs or
        cleanup.get('failed_cast_source') != bound(cast_path) or cleanup.get('failed_cast_excluded') is not True or
        cleanup.get('qualification_added') is not False or cleanup.get('input_sent') is not False or
        cleanup.get('runtime') != cast['runtime'] or cleanup.get('actor') != cast['actor'] or
        not park['finished_at'] <= cleanup['started_at'] < cleanup['finished_at'] or
        cleanup.get('native_rest_accrual_preserved') != rest or
        cleanup.get('after') != cleanup.get('expected_after') or
        cleanup.get('after') != offline_restore(cleanup['before'], fixture, park, rest, cast)):
        raise RuntimeError('failed Revive normal parking, selection or offline cleanup sources differ')
    before = fixture['before']
    after = snapshot()
    hunter = after['6']
    changed = {k for k in set(before['6']['native']) | set(hunter['native'])
        if before['6']['native'].get(k) != hunter['native'].get(k)}
    primary_path = Path(fixture['primary_stop_source']['path'])
    stop = closed(primary_path)
    if bound(primary_path) != fixture['primary_stop_source']:
        raise RuntimeError('failed Revive primary-stop source hash differs')
    with actor('primary'): primary_absent = lab.owned_process('client') is None
    checks = {**{f'actor_{g}_unchanged': after[g] == before[g] for g in ('1', '2', '3', '4', '5')},
        'hunter_saved_rows': hunter['saved'] == before['6']['saved'] == park['retained_class_saved'],
        'hunter_inventory': hunter['inventory'] == before['6']['inventory'],
        'hunter_native_columns': changed <= ALLOWED_HUNTER_COLUMNS | ({'rest_bonus'} if rest else set()) and
            hunter['native'] == park['retained_class_fixture'],
        'both_pets_restored': restored_pets(before['6']['pets'], hunter['pets']) and after == cleanup['after'],
        'hunter_home_pose': all(hunter['native'][k] == before['6']['native'][k] for k in
            ('position_x', 'position_y', 'position_z', 'orientation', 'map')),
        'hunter_full_health': hunter['native']['health'] == before['6']['native']['health'] == 209,
        'all_six_offline': all(v['native']['online'] == 0 for v in after.values()),
        'primary_stopped': primary_absent and after['1'] == stop['before'] == stop['after'],
        'original_registration': actors.load() == old['origin_actor'],
        'native_lifetime': fixture['runtime']['worldserver'] == t.receipt['runtime']['worldserver'],
        'bridge_lifetime': fixture['runtime']['modern_world'] == t.receipt['runtime']['modern_world'],
        'failed_revive_preserved': bound(cast_path) == cleanup['failed_cast_source'] and cast['completed'] is False,
        'failed_revive_excluded': cleanup['qualification_added'] is False and cleanup['failed_cast_excluded'] is True,
        'ordinary_park_and_selection': True,
        'no_probe': not any((lab.ROOT / 'run' / name).exists() for name in
            ('owned_pet_abandon_probe.json', 'owned_tame_request_probe.json', 'owned_stable_request_probe.json', 'owned_entry_request_probe.json')),
        'fixture_health_restored': next(p for p in hunter['pets'] if p['id'] == 16)['curhealth'] == 278}
    t.receipt.update(sources=[bound(p) for p in (preparation, fixture_path, cast_path, park_path, finish_path, cleanup_path)],
        primary_stop_source=fixture['primary_stop_source'], all_offline_snapshot=after,
        failed_cast_source=bound(cast_path), failed_cast_excluded=True, hunter_changed_native_columns=sorted(changed),
        native_rest_accrual_preserved=rest,
        checks=checks, input_sent=False, qualification_added=False, frame=shot(t.out / 'original_offline.png'),
        completed=all(checks.values()), phase='owned_revive_restoration_failed_parked_boundary' if post_proof else
            'owned_failed_revive_parked_boundary',
        qualified_scope='Offline cleanup and ordinary parking only. Failed Revive remains failed and excluded; no gameplay qualification.')
    if post_proof:
        t.receipt.update(failed_cast_variant=restoration.VARIANT, post_revive_restoration_failure_proof=post_proof)
    if len(checks) != 21 or not all(checks.values()):
        raise RuntimeError('failed Revive offline fixture preservation differs')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('preparation', 'fixture', 'cast', 'park', 'finish', 'cleanup', 'output'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    with actor('scout'):
        trial = Trial(args.output, controller='code')
        trial.receipt.update(custom_script_permission='blocked_by_user', softTargetInteract=SCRIPT_BOUNDARY)
        try: close(trial, args.preparation, args.fixture, args.cast, args.park, args.finish, args.cleanup)
        except Exception as error: trial.receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
        finally:
            trial.receipt['finished_at'] = time.time()
            trial.persist()
        print(json.dumps({k: trial.receipt.get(k) for k in ('completed', 'phase', 'failure', 'checks')}), flush=True)
