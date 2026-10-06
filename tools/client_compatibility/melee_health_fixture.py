"""Pose staging beside one existing SmartAI target with ordinary health damage."""
import json,time
from . import lab_runtime as lab
from .pet_attack_fixture import PetAttackFixture
from .interaction_bridge_deploy import identity

NAMES=('TC442MeleeHealthRestore','TC442MeleeHealthTarget')
POSE=(1818.73,1596.82,96.1702,6.10865)


def target():
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation,'
            'c.phaseMask,t.minlevel,t.maxlevel,t.faction,t.ScriptName,c.MovementType,t.flags_extra,t.AIName '
            'FROM client442_world.creature c JOIN client442_world.creature_template t ON t.entry=c.id WHERE c.guid=325163')
        row=q.fetchone()
        if (not row or row[:4]!=(325163,44794,'Training Dummy',0) or
            row[8:]!=(1,3,3,7,'',0,270336,'SmartAI') or
            any(abs(a-b)>.01 for a,b in zip(row[4:8],POSE))):
            raise RuntimeError('existing damageable SmartAI target contract differs')
        q.execute('SELECT event_type,action_type FROM client442_world.smart_scripts WHERE entryorguid=44794 ORDER BY id')
        if q.fetchall()!=((8,33),)*5:raise RuntimeError('target must have only the five existing spell-credit events')
        # The chosen western point is over 30m from the hostile level-30 NPCs.
        q.execute('SELECT c.guid FROM client442_world.creature c JOIN client442_world.creature_template t ON t.entry=c.id '
            'WHERE c.map=0 AND POW(c.position_x-%s,2)+POW(c.position_y-%s,2)<900 '
            'AND t.faction NOT IN (7,31,35)',(POSE[0]-3,POSE[1]))
        if q.fetchone():raise RuntimeError('unexpected non-neutral creature inside the reviewed 30m staging area')
    return list(row)


def native_target(row):
    return bool(row and row.get('kind')==3 and row.get('map')==0 and
        row.get('guid',0)>>52==0xf13 and row['guid']>>32&0xfffff==44794 and
        len(row.get('movement',{}).get('position',[]))==4 and
        all(abs(a-b)<.01 for a,b in zip(row['movement']['position'],POSE)))


class MeleeHealthFixture(PetAttackFixture):
    def __init__(self,out,actor):
        if tuple(actor.get(k) for k in ('guid','account_id','character_name','race','class','level'))!=(5,2,'Harnessctrl',1,9,10):
            raise ValueError('requires the unchanged trained owned warlock')
        self.out,self.actor=out,actor;self.before=None;self.rows=[];self.native=identity('worldserver')
        self.dummy=target();self.restoration=None

    def persist(self):
        lab.private_write(self.out/'melee_health_fixture.json',json.dumps({
            'schema':'client442_owned_melee_health_fixture_v1','actor':self.actor,'native':self.native,
            'before':self.before,'rows':self.rows,'dummy':self.dummy,
            'source':'Owned native-console pose staging only; the existing target is not modified, spawned or reset.'},indent=2)+'\n')

    def verify_rows(self):
        if identity('worldserver')!=self.native or target()!=self.dummy:raise RuntimeError('health fixture contract changed')
        with lab.connection() as c,c.cursor() as q:
            for row in self.rows:
                q.execute('SELECT id,position_x,position_y,position_z,orientation,map,name '
                    'FROM client442_world.game_tele WHERE id=%s',(row[0],))
                if list(q.fetchone() or ())!=row:raise RuntimeError('temporary health teleport changed')

    def prepare(self):
        from .interaction_ground_movement import position
        self.before=position(5);self.persist()
        if self.before[4]!=0:raise RuntimeError('requires the original map0')
        ground=(POSE[0]-3,POSE[1],POSE[2],0.,0)
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',NAMES)
            if q.fetchone():raise RuntimeError('an earlier melee health fixture needs cleanup')
            q.execute('SELECT MAX(id) FROM client442_world.game_tele');first=q.fetchone()[0]+1
            for i,(name,pose) in enumerate(zip(NAMES,[self.before,ground])):
                q.execute('INSERT INTO client442_world.game_tele '
                    '(id,position_x,position_y,position_z,orientation,map,name) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                    (first+i,*pose,name))
                q.execute('SELECT id,position_x,position_y,position_z,orientation,map,name '
                    'FROM client442_world.game_tele WHERE id=%s',(first+i,))
                self.rows.append(list(q.fetchone()));self.persist()
        self.verify_rows();lab.server_command('reload game_tele');time.sleep(.5)
        lab.server_command('tele name Harnessctrl '+NAMES[1]);time.sleep(4)
        actual=position(5)
        if (actual[4]!=0 or any(abs(actual[i]-ground[i])>.01 for i in (0,1,3)) or abs(actual[2]-ground[2])>2):
            raise RuntimeError('health target landing differs; restore teleport retained')
        return actual

    def restore(self):
        from .interaction_ground_movement import position
        if self.restoration is not None:return self.restoration
        if not self.rows:return None
        self.verify_rows();lab.server_command('tele name Harnessctrl '+NAMES[0]);time.sleep(4)
        actual=position(5)
        if any(abs(a-b)>.01 for a,b in zip(actual,self.before)):raise RuntimeError('health pose restoration differs')
        with lab.connection() as c,c.cursor() as q:
            for row in self.rows:
                q.execute('DELETE FROM client442_world.game_tele WHERE id=%s AND name=%s',(row[0],row[-1]))
                if q.rowcount!=1:raise RuntimeError('temporary health teleport removal rejected')
        lab.server_command('reload game_tele')
        self.restoration={'position':actual,'original_position':self.before,
            'temporary_teleports_removed':[r[0] for r in self.rows],'target_database_unchanged':target()==self.dummy,
            'target_runtime_health':'Ordinary earned damage retained; no spawn, reset or health command.'}
        lab.private_write(self.out/'melee_health_restoration.json',json.dumps(self.restoration,indent=2)+'\n')
        return self.restoration

    @classmethod
    def resume(cls,out,actor,path):
        path=path.resolve()
        if path.name!='melee_health_fixture.json' or not path.is_relative_to(lab.ROOT/'evidence') or path.is_symlink():
            raise ValueError('requires the private owned melee health fixture')
        row=json.loads(path.read_text());self=cls(out,actor)
        if (row['actor']!=actor or row['native']!=self.native or row['dummy']!=self.dummy or
            len(row['rows'])!=2 or [r[-1] for r in row['rows']]!=list(NAMES)):
            raise RuntimeError('closed health fixture differs')
        self.before=row['before'];self.rows=row['rows'];self.verify_rows();return self
