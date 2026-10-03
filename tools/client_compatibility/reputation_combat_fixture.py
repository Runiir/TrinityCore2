"""Stage beside one existing reward-bearing creature and restore only player pose."""
import json,math,time
from . import lab_runtime as lab


class CombatFixture:
    def __init__(self,t):self.t=t;self.rows=[];self.before=None;self.spawn=None

    def prepare(self):
        if (self.t.fixture['guid'],self.t.fixture['account_id'],self.t.fixture['character_name'])!=(1,1,'Harnessone'):
            raise ValueError('requires the registered primary actor')
        lab.server_command('saveall');time.sleep(1)
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT guid,account,name,position_x,position_y,position_z,orientation,map '
                'FROM client442_characters.characters WHERE guid=1');self.before=q.fetchone()
            if self.before[:3]!=(1,1,'Harnessone'):raise RuntimeError('owned character binding changed')
            q.execute('SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation,c.MovementType '
                'FROM client442_world.creature c JOIN client442_world.creature_template t ON c.id=t.entry WHERE c.guid=336057')
            self.spawn=q.fetchone()
            if not self.spawn or self.spawn[:4]!=(336057,1561,'Bloodsail Raider',0) or self.spawn[-1]!=0:
                raise RuntimeError('registered stationary Bloodsail Raider changed')
            names=['TC442ReputationRestore','TC442ReputationCombat']
            q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',names)
            if q.fetchone():raise RuntimeError('an earlier reputation combat fixture needs restoration')
            q.execute('SELECT MAX(id) FROM client442_world.game_tele');start=q.fetchone()[0]+1
            x,y,z,o=self.spawn[4:8];dx,dy=4*math.cos(o),4*math.sin(o)
            sources=[self.before[3:],(x+dx,y+dy,z+6,math.atan2(-dy,-dx)%(2*math.pi),0)]
            for i,(name,source) in enumerate(zip(names,sources)):
                row=(start+i,*source,name)
                q.execute('INSERT INTO client442_world.game_tele '
                    '(id,position_x,position_y,position_z,orientation,map,name) VALUES (%s,%s,%s,%s,%s,%s,%s)',row)
                q.execute('SELECT id,CAST(position_x AS DOUBLE),CAST(position_y AS DOUBLE),CAST(position_z AS DOUBLE),'
                    'CAST(orientation AS DOUBLE),map,name FROM client442_world.game_tele WHERE id=%s',(row[0],))
                self.rows.append(q.fetchone())
        self.t.receipt['combat_fixture']={'source':'native_console_pose_staging','before':self.before,'spawn':self.spawn,
            'teleports':self.rows,'scope':'No spawn/reset/kill/reputation command. Staging is not navigation proof.'};self.t.persist()
        lab.server_command('reload game_tele');time.sleep(.5)
        lab.server_command('tele name Harnessone TC442ReputationCombat');time.sleep(4)

    def restore(self):
        if not self.rows:return
        lab.server_command('tele name Harnessone TC442ReputationRestore');time.sleep(4)
        lab.server_command('saveall');time.sleep(1)
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT position_x,position_y,position_z,orientation,map '
                'FROM client442_characters.characters WHERE guid=1');position=q.fetchone()
            if any(abs(a-b)>.01 for a,b in zip(position,self.before[3:])):
                raise RuntimeError('combat pose restoration failed; preserving restore teleport')
            for row in self.rows:
                q.execute('SELECT id,CAST(position_x AS DOUBLE),CAST(position_y AS DOUBLE),CAST(position_z AS DOUBLE),'
                    'CAST(orientation AS DOUBLE),map,name FROM client442_world.game_tele WHERE id=%s',(row[0],))
                if q.fetchone()!=row:raise RuntimeError('combat teleport changed; refusing deletion')
            for row in self.rows:q.execute('DELETE FROM client442_world.game_tele WHERE id=%s AND name=%s',(row[0],row[-1]))
        lab.server_command('reload game_tele');self.t.receipt['combat_fixture']['restoration']={
            'pose':position,'teleports_removed':True,'earned_standings_retained':True};self.t.persist()
