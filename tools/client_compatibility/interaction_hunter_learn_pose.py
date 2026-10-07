"""Reversible Hunter-only staging beside the existing Beast Lore trainer."""
import math
import time
from types import SimpleNamespace

from . import lab_runtime as lab
from .hunter_learn_contract import require, native_prerequisites, TRAINER_ROW, TRAINER_NAME
from .interaction_hunter_tame_stage import pose, teleport_row
from .interaction_owned_class_fixture import saved
from .interaction_hunter_fixture import protected
from .interaction_spellbook_recon import resources
from .observation.journal import entries
from .pet_attack_landing import acknowledgement
from .world import transfers

NAMES = ('TC442HunterLearnRestore', 'TC442HunterLearnTrainer')


def landing_authority(packets, session, since, until, fixture):
    rows = [p for p in packets if p.get('session') == session and since <= p.get('time', 0) <= until]
    require(fixture['owner'] == 6 and fixture['before'][4] == fixture['landing'][4] == TRAINER_ROW[3] == 0 and
        not any(p.get('name') in ('SMSG_TRANSFER_PENDING', 'SMSG_NEW_WORLD', 'CMSG_WORLD_PORT_RESPONSE',
            'MSG_MOVE_WORLDPORT_ACK') for p in rows), 'learning landing lacks unchanged native map authority')
    proof = acknowledgement(rows, session, since, until, 6, fixture['landing'])
    native = [p for p in rows if p.get('direction') == 'from_native' and p.get('name') == 'MSG_MOVE_TELEPORT']
    modern = [p for p in rows if p.get('direction') == 'to_client' and p.get('name') == 'SMSG_MOVE_TELEPORT']
    require(len(native) == len(modern) == 1, 'learning landing requires exactly one native and delivered teleport')
    owner = SimpleNamespace(character={'guid': 6})
    translated = transfers.response(owner, native[0]['name'], bytes.fromhex(native[0]['body']))
    require(translated is not None and translated[0] == modern[0]['name'] and
        all(math.isfinite(value) for value in owner.pending_near['position']) and
        translated[1].hex() == modern[0]['body'] and modern[0] == proof['modern_teleport'] and
        0 <= modern[0]['time'] - native[0]['time'] < 2,
        'learning landing native XYZ differs from its delivered owned teleport')
    return {**proof, 'native_teleport': native[0], 'native_position': list(owner.pending_near['position']),
        'map': 0, 'native_before': fixture['before'], 'landing': fixture['landing'],
        'source_interval': [since, until], 'native_session': session}


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
    since = time.time()
    t.receipt['staging_started_at'] = since
    t.persist()
    lab.server_command('tele name Harnesshunt ' + NAMES[1])
    time.sleep(4)
    t.execute({'kind': 'chat', 'value': '/targetexact ' + TRAINER_NAME})
    state, frame = t.observe('hunter_learn_trainer_staged')
    until = time.time()
    t.receipt.update(state=state, frame=frame, staging_finished_at=until)
    t.persist()
    packets = [p for p in entries(lab.ROOT / 'evidence/world_packets.jsonl') if
        p.get('session') == t.receipt['native_session'] and since <= p.get('time', 0) <= until and
        p.get('name') in ('MSG_MOVE_TELEPORT', 'SMSG_MOVE_TELEPORT', 'CMSG_MOVE_TELEPORT_ACK',
            'MSG_MOVE_TELEPORT_ACK', 'SMSG_TRANSFER_PENDING', 'SMSG_NEW_WORLD',
            'CMSG_WORLD_PORT_RESPONSE', 'MSG_MOVE_WORLDPORT_ACK')]
    t.receipt['staging_packets'] = packets
    try:
        t.receipt['staging_teleport'] = landing_authority(packets, t.receipt['native_session'], since, until, fixture)
        native_landing = True
    except (RuntimeError, ValueError, KeyError, TypeError) as error:
        t.receipt['staging_teleport_failure'] = type(error).__name__ + ': ' + str(error)
        native_landing = False
    target = state.get('target', {})
    public = state.get('world_position', [])
    protected_checks = protected(old)
    checks = {'trainer_identity': target.get('name') == TRAINER_NAME, 'trainer_visible': target.get('visible') is True,
        # UnitPosition height is retained as telemetry; native XYZ comes from the owned teleport.
        'public_xy': len(public) >= 2 and all(type(v) in (int, float) and math.isfinite(v) for v in public[:2]) and
            math.dist(public[:2], fixture['landing'][:2]) < 1,
        'native_xyz_map_ack': native_landing, 'saved_rows': saved(6) == baseline['saved'],
        'resources': resources(oracle) == baseline['resources'], 'protected_actors': all(protected_checks.values()),
        'ui_clean': not state.get('lua_errors') and not state.get('blocked_actions')}
    t.receipt.update(staging_checks=checks, protected_checks=protected_checks)
    t.persist()
    require(all(checks.values()), 'existing trainer staging or owner preservation differs: ' +
        ', '.join(name for name, passed in checks.items() if not passed))
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
