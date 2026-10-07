"""Stage only disposable Wolf16's offline health for one ordinary Revive test."""
import argparse
import json
import subprocess
import time
from pathlib import Path
from . import lab_runtime as lab
from .hunter_revive_fixture import dead_snapshot
from .review_hunter_revive_prerequisites import absent_clients
from .interaction_bridge_deploy import identity
from .interaction_hunter_stable_slots import bound
from .interaction_parked_client_resource_pause import snapshot
from .interaction_retained_class_fixture import closed
from .interaction_social import actor


def stage(output, pause_path, prerequisite_path, preparation_path):
    started = time.time()
    output = output.resolve()
    if output.exists() or not output.is_relative_to(lab.ROOT / 'evidence'):
        raise ValueError('requires a new private evidence directory')
    absent_clients()
    pause, proof, preparation = [closed(p) for p in (pause_path, prerequisite_path, preparation_path)]
    native, bridge = identity('worldserver'), identity('modern_world')
    before = snapshot()
    if (pause.get('phase') != 'parked_scout_resource_paused' or len(pause.get('checks', {})) != 8 or
        not all(pause['checks'].values()) or before != pause.get('after') or pause.get('before') != before or
        pause['runtime']['worldserver'] != native or pause['runtime']['modern_world'] != bridge or
        proof.get('known_native_and_public') is not True or proof.get('input_sent') is not False or
        proof.get('sources', [None, None, None])[2] != bound(pause_path) or
        preparation.get('phase') != 'await_owned_class_lobby_review' or
        preparation.get('runtime') != pause.get('runtime') or preparation.get('class_actor', {}).get('guid') != 6):
        raise RuntimeError('verified Revive prerequisite or closed offline source differs')
    after = dead_snapshot(before)
    pet = next(p for p in before['6']['pets'] if p['id'] == 16)
    output.mkdir(parents=True, mode=0o700)
    receipt = {'schema': 'client442_owned_revive_dead_fixture_v1', 'started_at': started,
        'actor': preparation['class_actor'], 'runtime': {'worldserver': native, 'modern_world': bridge},
        'code_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip(),
        'controller': 'code', 'model': None, 'revision': None, 'cases': [], 'completed': False, 'failure': None,
        'sources': [bound(p) for p in (pause_path, prerequisite_path, preparation_path)],
        'primary_stop_source': pause['primary_stop_source'], 'before': before, 'expected_after': after,
        'input_sent': False, 'qualification_added': False, 'spell_grant_sent': False,
        'fixture_mutation': {'table': 'character_pet', 'owner': 6, 'id': 16, 'column': 'curhealth', 'before': 278, 'after': 0},
        'qualified_scope': 'Offline disposable pet health fixture only. No natural death, Revive cast or gameplay qualification.'}
    def persist(): lab.private_write(output / 'episode.json', json.dumps(receipt, indent=2) + '\n')
    persist()
    try:
        absent_clients()
        if snapshot() != before:
            raise RuntimeError('offline actors changed before the exact fixture update')
        with lab.connection() as connection, connection.cursor() as cursor:
            cursor.execute('UPDATE client442_characters.character_pet SET curhealth=0 '
                'WHERE id=16 AND owner=6 AND curhealth=278 AND savetime=%s AND slot=0 AND active=1 '
                'AND NOT EXISTS (SELECT 1 FROM client442_characters.characters WHERE guid=6 AND online<>0)',
                (pet['savetime'],))
            if cursor.rowcount != 1:
                raise RuntimeError('exact offline disposable pet update did not match once')
        current = snapshot()
        if current != after or identity('worldserver') != native or identity('modern_world') != bridge:
            raise RuntimeError('offline fixture changed more than disposable Wolf16 health')
        absent_clients()
        receipt.update(after=current, completed=True, phase='owned_revive_dead_fixture_staged',
            checks={'only_Wolf16_health': True, 'Harnesswolf4_unchanged': True,
                'all_six_offline': True, 'other_saved_state': True, 'both_clients_stopped': True,
                'native_unchanged': True, 'bridge_unchanged': True})
    except Exception as error:
        receipt['failure'] = f'{type(error).__name__}: {error}'
        raise
    finally:
        receipt['finished_at'] = time.time()
        persist()
    print(json.dumps({'completed': True, 'fixture_pet': 16, 'health': 0, 'qualification_added': False}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('output', 'pause', 'prerequisite', 'preparation'):
        parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    with actor('scout'):
        stage(args.output, args.pause, args.prerequisite, args.preparation)
