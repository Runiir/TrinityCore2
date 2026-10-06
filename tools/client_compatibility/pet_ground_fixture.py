"""Stage only the trained owned warlock on previously validated open ground."""
import json,time
from . import lab_runtime as lab
from .interaction_ground_movement import position
from .interaction_owned_class_fixture import character
from .interaction_bridge_deploy import identity

GROUND=(-8921.09,-119.135,82.195,0.,0)
NAMES=('TC442PetCommandRestore','TC442PetCommandGround')


class PetGroundFixture:
    def __init__(self,out,actor):
        if tuple(actor.get(k) for k in ('guid','account_id','character_name','race','class','level'))!=(5,2,'Harnessctrl',1,9,10):
            raise ValueError('requires the unchanged trained owned warlock')
        self.out,self.actor=out,actor;self.before=None;self.rows=[];self.native=identity('worldserver')

    def persist(self):
        lab.private_write(self.out/'pet_ground_fixture.json',json.dumps({
            'schema':'client442_owned_pet_ground_fixture_v1','actor':self.actor,'native':self.native,
            'before':self.before,'rows':self.rows,'source':'owned native-console setup only; no movement qualification',
            'ground_source':'tools/client_compatibility/nearby_fixture.py validated open-ground coordinates',
            'ground_source_sha256':lab.sha256(lab.REPO/'tools/client_compatibility/nearby_fixture.py')},indent=2)+'\n')

    def verify_rows(self):
        if identity('worldserver')!=self.native:raise RuntimeError('native fixture lifetime differs')
        with lab.connection() as c,c.cursor() as q:
            for row in self.rows:
                q.execute('SELECT id,position_x,position_y,position_z,orientation,map,name '
                    'FROM client442_world.game_tele WHERE id=%s',(row[0],))
                if list(q.fetchone() or ())!=row:raise RuntimeError('temporary pet teleport changed')

    def prepare(self):
        current=character(5,2)
        if current['name']!='Harnessctrl' or current['level']!=10 or current['online']!=1:
            raise RuntimeError('trained pet fixture is not the owned online warlock')
        self.before=position(5);self.persist()
        if self.before[4]!=0:raise RuntimeError('pet fixture requires its original map0')
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',NAMES)
            if q.fetchone():raise RuntimeError('an earlier pet ground fixture needs cleanup')
            q.execute('SELECT MAX(id) FROM client442_world.game_tele');first=q.fetchone()[0]+1
            for i,(name,pose) in enumerate(zip(NAMES,[self.before,GROUND])):
                row=(first+i,*pose,name)
                q.execute('INSERT INTO client442_world.game_tele '
                    '(id,position_x,position_y,position_z,orientation,map,name) VALUES (%s,%s,%s,%s,%s,%s,%s)',row)
                q.execute('SELECT id,position_x,position_y,position_z,orientation,map,name '
                    'FROM client442_world.game_tele WHERE id=%s',(row[0],));stored=list(q.fetchone())
                if (stored[0]!=row[0] or stored[5:]!=list(row[5:]) or
                    any(abs(a-b)>.001 for a,b in zip(stored[1:5],row[1:5]))):
                    raise RuntimeError('temporary pet teleport storage differs')
                self.rows.append(stored);self.persist()
        self.verify_rows();lab.server_command('reload game_tele');time.sleep(.5)
        lab.server_command('tele name Harnessctrl '+NAMES[1]);time.sleep(4)
        actual=position(5)
        if any(abs(a-b)>.01 for a,b in zip(actual,GROUND)):
            raise RuntimeError('native pet ground staging differs')
        return actual

    def restore(self):
        if not self.rows:return None
        self.verify_rows()
        current=character(5,2)
        if current['name']!='Harnessctrl' or current['level']!=10:raise RuntimeError('owned fixture identity differs')
        lab.server_command('tele name Harnessctrl '+NAMES[0]);time.sleep(4)
        actual=position(5)
        if any(abs(a-b)>.01 for a,b in zip(actual,self.before)):
            raise RuntimeError('pet fixture position restoration differs; restore teleport retained')
        with lab.connection() as c,c.cursor() as q:
            for row in self.rows:
                q.execute('SELECT id,position_x,position_y,position_z,orientation,map,name '
                    'FROM client442_world.game_tele WHERE id=%s',(row[0],))
                if list(q.fetchone() or ())!=row:raise RuntimeError('temporary pet teleport changed before removal')
                q.execute('DELETE FROM client442_world.game_tele WHERE id=%s AND name=%s',(row[0],row[-1]))
                if q.rowcount!=1:raise RuntimeError('temporary pet teleport removal rejected')
        lab.server_command('reload game_tele')
        result={'position':actual,'original_position':self.before,'temporary_teleports_removed':[r[0] for r in self.rows],
            'native':self.native,'source':'native fixture cleanup only; ordinary pet outcomes are scored separately'}
        lab.private_write(self.out/'pet_ground_restoration.json',json.dumps(result,indent=2)+'\n')
        return result

    @classmethod
    def resume(cls,out,actor,path):
        path=path.resolve()
        if path.name!='pet_ground_fixture.json' or not path.is_relative_to(lab.ROOT/'evidence'):
            raise ValueError('require the owned private pet ground fixture')
        row=json.loads(path.read_text());self=cls(out,actor)
        if row['actor']!=actor or row['native']!=self.native or len(row['rows'])!=2:
            raise RuntimeError('pet ground fixture source differs')
        self.before=row['before'];self.rows=row['rows'];self.verify_rows();return self
