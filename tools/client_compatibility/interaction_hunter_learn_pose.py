"""Reversible Hunter-only staging beside the existing Beast Lore trainer."""
import math
import time

from . import lab_runtime as lab
from .hunter_learn_contract import require, native_prerequisites, TRAINER_ROW, TRAINER_NAME
from .interaction_hunter_tame_stage import pose, teleport_row
from .interaction_owned_class_fixture import saved
from .interaction_hunter_fixture import protected
from .interaction_spellbook_recon import resources

NAMES = ('TC442HunterLearnRestore', 'TC442HunterLearnTrainer')


def stage(t, old, oracle, baseline):
    prerequisite = native_prerequisites()
    require(saved(6) == baseline['saved'] and resources(oracle) == baseline['resources'] and
        all(protected(old).values()), 'trainer staging owner resources or protected actors differ')
    state, frame = t.observe('hunter_learn_pose_before')
    require(not frame['movement']['dead'] and not frame['movement']['in_combat'] and not frame['movement']['speed'],
        'trainer staging requires an idle living Hunter')
    lab.server_command('saveall')
    time.sleep(.5)
    original = pose()
    x, y, z, orientation = TRAINER_ROW[4:8]
    landing = [x + 3 * math.cos(orientation), y + 3 * math.sin(orientation), z,
        (orientation + math.pi) % math.tau, 0]
    with lab.connection() as con, con.cursor() as q:
        con.begin()
        try:
            q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s) FOR UPDATE', NAMES)
            require(not q.fetchone(), 'previous learning pose fixture needs source-bound cleanup')
            q.execute('SELECT MAX(id) FROM client442_world.game_tele')
            number = q.fetchone()[0] + 1
            rows = []
            for i, (name, where) in enumerate(zip(NAMES, (original, landing))):
                q.execute('INSERT INTO client442_world.game_tele (id,position_x,position_y,position_z,orientation,map,name) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s)', (number + i, *where, name))
                rows.append(teleport_row(q, number + i))
            q.execute('SELECT position_x,position_y,position_z,orientation,map FROM client442_world.game_tele WHERE id=%s', (number,))
            projection = list(q.fetchone())
            require(projection == original, 'exact original saved pose must survive its native SQL FLOAT projection')
            fixture = {'owner': 6, 'native': t.receipt['runtime']['worldserver'], 'before': original,
                'native_restore_projection': projection, 'landing': rows[1][1:6], 'rows': rows,
                'prerequisite_fingerprint': prerequisite, 'source': 'Owned Hunter pose only; no spell/pet/health grant.'}
            t.receipt.update(pose_fixture=fixture, pose_rows_committed=False)
            t.persist()
            con.commit()
        except BaseException:
            con.rollback()
            raise
    t.receipt['pose_rows_committed'] = True
    t.persist()
    lab.server_command('reload game_tele')
    lab.server_command('tele name Harnesshunt ' + NAMES[1])
    time.sleep(4)
    t.execute({'kind': 'chat', 'value': '/targetexact ' + TRAINER_NAME})
    state, frame = t.observe('hunter_learn_trainer_staged')
    target = state.get('target', {})
    require(target.get('name') == TRAINER_NAME and target.get('visible') is True and
        math.dist(state['world_position'][:3], landing[:3]) < 1 and
        saved(6) == baseline['saved'] and resources(oracle) == baseline['resources'] and
        all(protected(old).values()) and not state.get('lua_errors') and not state.get('blocked_actions'),
        'existing trainer staging or owner preservation differs')
    return fixture, state, frame


def restore(t, fixture, old, expected_saved, settlement=None):
    require(fixture.get('owner') == 6 and fixture.get('native') == t.receipt['runtime']['worldserver'] and
        [r[-1] for r in fixture.get('rows', [])] == list(NAMES), 'learning pose fixture authority differs')
    with lab.connection() as con, con.cursor() as q:
        q.execute('SELECT id FROM client442_world.game_tele WHERE id IN (%s,%s) OR name IN (%s,%s)',
            (*[row[0] for row in fixture['rows']], *NAMES))
        present = q.fetchall()
        if not present:
            expected = fixture['before']
            require(settlement is not None and settlement.get('fixture') == fixture and
                settlement.get('restored') == expected == fixture['native_restore_projection'] and
                settlement.get('removed') == [row[0] for row in fixture['rows']] and
                settlement.get('expected_saved') == expected_saved and
                settlement.get('gameplay_input_sent') is False and
                pose() == expected and saved(6) == expected_saved and all(protected(old).values()),
                'already-removed pose rows require exact persisted deletion authority and unchanged home state')
            proof = {**settlement, 'native_teleport_replayed': False, 'settlement_only': True,
                'checks': {'original_pose': True, 'saved_rows': True, 'temporary_rows_removed': True, **protected(old)}}
            t.receipt['pose_restoration'] = proof
            t.persist()
            lab.server_command('reload game_tele')
            return proof
        require(len(present) == 2 and all(teleport_row(q, row[0]) == row for row in fixture['rows']), 'learning pose rows changed')
        q.execute('SELECT position_x,position_y,position_z,orientation,map FROM client442_world.game_tele WHERE id=%s',
            (fixture['rows'][0][0],))
        expected = list(q.fetchone())
    require(expected == fixture['before'] == fixture['native_restore_projection'], 'source-bound original pose projection differs')
    lab.server_command('saveall')
    time.sleep(.5)
    replayed = pose() != expected
    if replayed:
        lab.server_command('tele name Harnesshunt ' + NAMES[0])
        time.sleep(4)
    lab.server_command('saveall')
    time.sleep(.5)
    require(pose() == expected and saved(6) == expected_saved and all(protected(old).values()),
        'exact learning home pose or saved rows did not restore')
    authority = {'fixture': fixture, 'restored': expected, 'removed': [r[0] for r in fixture['rows']],
        'expected_saved': expected_saved, 'native_teleport_replayed': replayed, 'gameplay_input_sent': False}
    t.receipt['pose_delete_authority'] = authority
    t.persist()
    with lab.connection() as con, con.cursor() as q:
        con.begin()
        try:
            for row in fixture['rows']:
                require(teleport_row(q, row[0]) == row, 'learning pose row changed before deletion')
                q.execute('DELETE FROM client442_world.game_tele WHERE id=%s AND name=%s', (row[0], row[-1]))
                require(q.rowcount == 1, 'exact learning pose row was not removed once')
            con.commit()
        except BaseException:
            con.rollback()
            raise
    proof = {**authority,
        'checks': {'original_pose': pose() == expected, 'saved_rows': saved(6) == expected_saved,
            'temporary_rows_removed': True, **protected(old)}}
    t.receipt['pose_restoration'] = proof
    t.persist()
    lab.server_command('reload game_tele')
    require(all(proof['checks'].values()), 'learning pose restoration differs')
    return proof
