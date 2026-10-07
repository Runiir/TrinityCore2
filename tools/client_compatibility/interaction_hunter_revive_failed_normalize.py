"""Restore only the offline disposable fixture after the recorded failed Revive."""
import argparse
import json
import time
from pathlib import Path
from . import lab_runtime as lab
from .hunter_revive_failed_fixture import sources, offline_restore
from .hunter_revive_fixture import restored_pets
from .hunter_rest_accrual import preservation as rest_preservation
from . import hunter_revive_restoration_failure as restoration
from .interaction_bridge_deploy import identity
from .interaction_hunter_stable_slots import bound
from .interaction_parked_client_resource_pause import snapshot
from .interaction_social import actor


PET_COLUMNS = ('id', 'entry', 'owner', 'modelid', 'CreatedBySpell', 'PetType', 'level', 'exp',
    'Reactstate', 'name', 'renamed', 'active', 'slot', 'curhealth', 'curmana', 'savetime', 'abdata')


def restore_sql(cursor, before, expected):
    """Compare both full pet rows and every owned online flag in the update itself."""
    pets = {p['id']: p for p in before['6']['pets']}
    restored = next(p for p in expected['6']['pets'] if p['id'] == 16)
    if any(set(p) != set(PET_COLUMNS) for p in pets.values()):
        raise RuntimeError('offline cleanup pet column contract differs')
    where = ' AND '.join('p.`' + k + '`=%s' for k in PET_COLUMNS)
    named = ' AND '.join('n.`' + k + '`=%s' for k in PET_COLUMNS)
    changed = tuple(k for k in ('curhealth', 'CreatedBySpell', 'active') if restored[k] != pets[16][k])
    if changed not in (('curhealth', 'CreatedBySpell', 'active'), ('CreatedBySpell',)):
        raise RuntimeError('failed-Revive cleanup requires its exact three-field or creator-only difference')
    cursor.execute('UPDATE client442_characters.character_pet AS p '
        'JOIN client442_characters.character_pet AS n ON n.id=4 AND n.owner=6 SET ' +
        ','.join('p.' + k + '=%s' for k in changed) + ' WHERE ' + where +
        ' AND ' + named +
        ' AND NOT EXISTS (SELECT 1 FROM client442_characters.characters WHERE guid IN (1,2,3,4,5,6) AND online<>0)',
        tuple(restored[k] for k in changed) +
        tuple(pets[16][k] for k in PET_COLUMNS) + tuple(pets[4][k] for k in PET_COLUMNS))
    if cursor.rowcount != 1:
        raise RuntimeError('exact failed-Revive offline disposable restoration did not match once')


def normalize(output, preparation_path, fixture_path, cast_path, park_path):
    started = time.time()
    _, fixture, cast, park = sources(preparation_path, fixture_path, cast_path, park_path)
    post_proof = restoration.from_journal(cast) if cast.get('failure') == restoration.FAILURE else None
    before = snapshot()
    rest = None
    if before['6']['native'].get('rest_bonus') != fixture['before']['6']['native'].get('rest_bonus'):
        rest = rest_preservation(fixture['before']['6']['native'], before['6']['native'], cast['entry_source'])
    expected = offline_restore(before, fixture, park, rest, cast)
    refs = [bound(p) for p in (preparation_path, fixture_path, cast_path, park_path)]
    runtime = {k: identity(k) for k in ('worldserver', 'modern_world', 'client')}
    if runtime != cast['runtime']:
        raise RuntimeError('failed Revive cleanup runtime lifetime differs')
    output = output.resolve()
    if output.exists() or not output.is_relative_to(lab.ROOT / 'evidence'):
        raise ValueError('requires a new private failed-Revive cleanup episode')
    output.mkdir(parents=True, mode=0o700)
    receipt = {'schema': 'client442_failed_revive_offline_cleanup_v1', 'started_at': started,
        'actor': park['actor'], 'runtime': runtime, 'controller': 'code', 'model': None, 'revision': None,
        'cases': [], 'completed': False, 'failure': None, 'sources': refs,
        'before': before, 'expected_after': expected, 'input_sent': False, 'qualification_added': False,
        'failed_cast_excluded': True, 'failed_cast_source': bound(cast_path), 'native_rest_accrual_preserved': rest,
        'scope': 'Failed Revive remains excluded. Offline fixture cleanup restores only Wolf16 saved '
            'health278, tame creator13481 and active1; named Harnesswolf4 and all other saved state stay exact.'}
    if post_proof:
        receipt.update(failed_cast_variant=restoration.VARIANT, post_revive_restoration_failure_proof=post_proof,
            normalized_columns=['CreatedBySpell'],
            scope='Failed post-Revive restoration remains excluded. Restore only Wolf16 creator883 to13481; '
                'actual health278, active1, native rest accrual, named Harnesswolf4 and all other saved fields remain exact.')
    def persist(): lab.private_write(output / 'episode.json', json.dumps(receipt, indent=2) + '\n')
    persist()
    try:
        if (snapshot() != before or refs != [bound(p) for p in (preparation_path, fixture_path, cast_path, park_path)] or
            {k: identity(k) for k in runtime} != runtime or
            (rest and rest != rest_preservation(fixture['before']['6']['native'], before['6']['native'], cast['entry_source']))):
            raise RuntimeError('failed Revive source, runtime or offline state changed before cleanup')
        with lab.connection() as connection, connection.cursor() as cursor:
            restore_sql(cursor, before, expected)
        after = snapshot()
        if (after != expected or not restored_pets(fixture['before']['6']['pets'], after['6']['pets']) or
            {k: identity(k) for k in runtime} != runtime or
            refs != [bound(p) for p in (preparation_path, fixture_path, cast_path, park_path)] or
            (rest and rest != rest_preservation(fixture['before']['6']['native'], after['6']['native'], cast['entry_source']))):
            raise RuntimeError('failed Revive cleanup changed more than the exact offline fixture')
        receipt.update(after=after, completed=True, phase='owned_revive_restoration_failure_fixture_normalized' if post_proof else
            'owned_failed_revive_fixture_normalized')
    except Exception as error:
        receipt['failure'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        receipt['finished_at'] = time.time()
        persist()
    print(json.dumps({'completed': True, 'normalized_pet': 16, 'failed_cast_excluded': True,
        'qualification_added': False}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('output', 'preparation', 'fixture', 'cast', 'park'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    with actor('scout'):
        normalize(args.output, args.preparation, args.fixture, args.cast, args.park)
