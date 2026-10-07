"""Reversible native facing setup; gameplay remains ordinary owned client input."""
import json,math,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_bridge_deploy import identity
from .interaction_ground_movement import position

NAMES=('TC442PrimaryThrowRestore','TC442PrimaryThrowFacing')


class PrimaryFacingFixture:
    def __init__(self,out):
        self.out=out;self.before=None;self.rows=[];self.landing=None;self.native=identity('worldserver')

    def persist(self):
        lab.private_write(self.out/'primary_throw_facing_fixture.json',json.dumps({
            'schema':'client442_primary_facing_fixture_v1','native':self.native,'before':self.before,
            'rows':self.rows,'landing':self.landing,'actor_guid':1,
            'scope':'Owned reversible native facing setup only. No creature, spell, health, inventory or permission changes.'},indent=2)+'\n')

    def verify(self):
        if identity('worldserver')!=self.native:raise RuntimeError('native facing fixture lifetime changed')
        with lab.connection() as c,c.cursor() as q:
            for row in self.rows:
                q.execute('SELECT id,position_x,position_y,position_z,orientation,map,name FROM client442_world.game_tele WHERE id=%s',(row[0],))
                if list(q.fetchone() or ())!=row:raise RuntimeError('owned facing fixture row changed')

    def prepare(self,before,target):
        self.before=list(before)
        if position(1)!=self.before or before[4]!=0:raise RuntimeError('primary facing baseline differs')
        facing=math.atan2(target[1]-before[1],target[0]-before[0])%(2*math.pi)
        posed=[*before[:3],facing,before[4]];self.persist()
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',NAMES)
            if q.fetchone():raise RuntimeError('prior facing fixture needs exact cleanup')
            q.execute('SELECT MAX(id) FROM client442_world.game_tele');first=q.fetchone()[0]+1
            for i,(name,pose) in enumerate(zip(NAMES,(before,posed))):
                q.execute('INSERT INTO client442_world.game_tele (id,position_x,position_y,position_z,orientation,map,name) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s)',(first+i,*pose,name))
                q.execute('SELECT id,position_x,position_y,position_z,orientation,map,name FROM client442_world.game_tele WHERE id=%s',(first+i,))
                self.rows.append(list(q.fetchone()));self.persist()
        self.verify();lab.server_command('reload game_tele');time.sleep(.5)
        lab.server_command('tele name Harnessone '+NAMES[1]);time.sleep(4)
        self.landing=position(1);self.persist()
        if any(abs(a-b)>.01 for a,b in zip(self.landing,posed)):
            raise RuntimeError('native facing setup differs')
        return self.landing

    def restore(self):
        self.verify()
        if len(self.rows)!=2:raise RuntimeError('partial native facing fixture retained for exact cleanup')
        current=position(1)
        if self.landing and any(abs(a-b)>.01 for a,b in zip(current,self.landing)):
            raise RuntimeError('primary moved during facing fixture; preserve current pose for user attribution')
        lab.server_command('tele name Harnessone '+NAMES[0]);time.sleep(4)
        actual=position(1)
        if actual!=self.before:raise RuntimeError('exact user-facing restoration differs')
        with lab.connection() as c,c.cursor() as q:
            for row in self.rows:
                q.execute('DELETE FROM client442_world.game_tele WHERE id=%s AND name=%s',(row[0],row[-1]))
                if q.rowcount!=1:raise RuntimeError('facing fixture removal differs')
        lab.server_command('reload game_tele')
        result={'original':self.before,'restored':actual,'removed':[r[0] for r in self.rows],'native_unchanged':True}
        lab.private_write(self.out/'primary_facing_restoration.json',json.dumps(result,indent=2)+'\n');self.rows=[]
        return result

    @classmethod
    def resume(cls,out,path):
        if path.is_symlink():raise RuntimeError('facing fixture cannot be a symlink')
        path=path.resolve()
        if path.is_symlink() or path.name!='primary_throw_facing_fixture.json' or not path.is_relative_to(lab.ROOT/'evidence'):
            raise RuntimeError('requires an owned native facing fixture')
        d=json.loads(path.read_text());s=cls(out)
        if d.get('native')!=s.native or d.get('actor_guid')!=1 or len(d.get('rows',[]))!=2 or [r[-1] for r in d['rows']]!=list(NAMES):
            raise RuntimeError('native facing fixture identity differs')
        s.before=d['before'];s.landing=d['landing'];s.rows=d['rows'];s.verify();return s
