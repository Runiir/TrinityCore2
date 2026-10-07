"""Reversible native pose staging for the original primary's melee diagnosis."""
import json,time
from . import lab_runtime as lab
from .interaction_bridge_deploy import identity
from .interaction_ground_movement import position
from .melee_health_fixture import target,POSE

NAMES=('TC442PrimaryMeleeRestore','TC442PrimaryMeleeTarget')


class PrimaryMeleeFixture:
    def __init__(self,out):
        self.out=out;self.before=None;self.rows=[];self.native=identity('worldserver');self.target=target()

    def persist(self):
        lab.private_write(self.out/'primary_melee_fixture.json',json.dumps({'schema':'client442_primary_melee_fixture_v1',
            'native':self.native,'before':self.before,'rows':self.rows,'target':self.target,
            'source':'Owned pose staging only; existing target is never spawned, reset or modified.'},indent=2)+'\n')

    def verify(self):
        if identity('worldserver')!=self.native or target()!=self.target:raise RuntimeError('primary target contract changed')
        with lab.connection() as c,c.cursor() as q:
            for row in self.rows:
                q.execute('SELECT id,position_x,position_y,position_z,orientation,map,name '
                    'FROM client442_world.game_tele WHERE id=%s',(row[0],))
                if list(q.fetchone() or ())!=row:raise RuntimeError('primary pose fixture row differs')

    def prepare(self):
        self.before=position(1);self.persist()
        if self.before[4]!=0:raise RuntimeError('requires original primary on map0')
        ground=(POSE[0]-3,POSE[1],POSE[2],0.,0)
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',NAMES)
            if q.fetchone():raise RuntimeError('prior primary fixture needs cleanup')
            q.execute('SELECT MAX(id) FROM client442_world.game_tele');first=q.fetchone()[0]+1
            for i,(name,pose) in enumerate(zip(NAMES,(self.before,ground))):
                q.execute('INSERT INTO client442_world.game_tele '
                    '(id,position_x,position_y,position_z,orientation,map,name) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                    (first+i,*pose,name))
                q.execute('SELECT id,position_x,position_y,position_z,orientation,map,name '
                    'FROM client442_world.game_tele WHERE id=%s',(first+i,))
                self.rows.append(list(q.fetchone()));self.persist()
        self.verify();lab.server_command('reload game_tele');time.sleep(.5)
        lab.server_command('tele name Harnessone '+NAMES[1]);time.sleep(4)
        actual=position(1)
        if actual[4]!=0 or any(abs(actual[i]-ground[i])>.01 for i in (0,1,3)) or abs(actual[2]-ground[2])>=3:
            raise RuntimeError('primary target landing differs; restore fixture retained')
        return actual

    def restore(self):
        if not self.rows:return None
        if len(self.rows)!=2:raise RuntimeError('partial primary fixture needs exact row recovery')
        self.verify();lab.server_command('tele name Harnessone '+NAMES[0]);time.sleep(4)
        actual=position(1)
        if any(abs(a-b)>.01 for a,b in zip(actual,self.before)):raise RuntimeError('primary user pose restoration differs')
        with lab.connection() as c,c.cursor() as q:
            for row in self.rows:
                q.execute('DELETE FROM client442_world.game_tele WHERE id=%s AND name=%s',(row[0],row[-1]))
                if q.rowcount!=1:raise RuntimeError('primary fixture removal rejected')
        lab.server_command('reload game_tele')
        result={'position':actual,'original':self.before,'removed':[r[0] for r in self.rows],
            'target_database_unchanged':target()==self.target,'target_runtime_damage':'Ordinary earned outcome retained.'}
        lab.private_write(self.out/'primary_melee_restoration.json',json.dumps(result,indent=2)+'\n')
        self.rows=[];return result

    @classmethod
    def resume(cls,out,path):
        path=path.resolve()
        if path.name!='primary_melee_fixture.json' or path.is_symlink() or not path.is_relative_to(lab.ROOT/'evidence'):
            raise ValueError('requires owned primary fixture receipt')
        d=json.loads(path.read_text());self=cls(out)
        if d['native']!=self.native or d['target']!=self.target or len(d['rows'])!=2 or [r[-1] for r in d['rows']]!=list(NAMES):
            raise RuntimeError('closed primary fixture identity differs')
        self.before=d['before'];self.rows=d['rows'];self.verify();return self
