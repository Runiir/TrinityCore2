"""Stage the owned primary beside an existing mailbox; reuse verified pose cleanup."""
import json
import math
import time
from . import lab_runtime as lab
from .npc_fixture import NpcFixture


class MailboxFixture(NpcFixture):
    def __init__(self, out, player):
        super().__init__(out, player, 197135, 0)

    def prepare(self):
        lab.server_command('saveall'); time.sleep(1)
        with lab.connection() as connection, connection.cursor() as cursor:
            cursor.execute('SELECT guid,account,name,position_x,position_y,position_z,orientation,map '
                           'FROM client442_characters.characters WHERE guid=1')
            self.before = cursor.fetchone()
            if self.before[:3] != (1, 1, 'Harnessone'):
                raise RuntimeError('owned primary identity changed')
            cursor.execute('SELECT g.guid,g.id,t.name,g.map,g.position_x,g.position_y,g.position_z,g.orientation,t.type '
                           'FROM client442_world.gameobject g JOIN client442_world.gameobject_template t ON t.entry=g.id '
                           'WHERE g.guid=220045 AND g.id=197135 AND g.map=0 AND t.type=19')
            self.npc = cursor.fetchone()
            if not self.npc or self.npc[2] != 'Mailbox':
                raise RuntimeError('existing mailbox fixture changed')
            names = ['TC442NpcRestore', 'TC442NpcService']
            cursor.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)', names)
            if cursor.fetchone(): raise RuntimeError('an earlier service fixture needs cleanup')
            cursor.execute('SELECT MAX(id) FROM client442_world.game_tele'); start = cursor.fetchone()[0] + 1
            x,y,z = self.npc[4:7]; dx,dy = 3*math.cos(self.npc[7]),3*math.sin(self.npc[7])
            poses = [self.before[3:], (x+dx, y+dy, z, math.atan2(-dy,-dx) % (2*math.pi), 0)]
            for offset,(name,pose) in enumerate(zip(names,poses)):
                row = (start+offset, *pose, name); self.rows.append(row)
                cursor.execute('INSERT INTO client442_world.game_tele '
                               '(id,position_x,position_y,position_z,orientation,map,name) VALUES (%s,%s,%s,%s,%s,%s,%s)', row)
                cursor.execute('SELECT id,CAST(position_x AS DOUBLE),CAST(position_y AS DOUBLE),CAST(position_z AS DOUBLE),'
                               'CAST(orientation AS DOUBLE),map,name FROM client442_world.game_tele WHERE id=%s', (row[0],))
                self.rows[-1] = cursor.fetchone()
        lab.private_write(self.out/'mailbox_fixture.json', json.dumps({'source':'code_fixture_native_console',
            'before':self.before, 'mailbox':self.npc, 'temporary_teleports':self.rows}, indent=2)+'\n')
        lab.server_command('reload game_tele'); time.sleep(.5)
        lab.server_command('tele name Harnessone TC442NpcService'); time.sleep(4)
