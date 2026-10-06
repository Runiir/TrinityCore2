"""Stage the owned warlock beside one existing passive dummy, then restore its pose."""
import json,math,time
from . import lab_runtime as lab
from .interaction_ground_movement import position
from .interaction_owned_class_fixture import character
from .interaction_bridge_deploy import identity

NAMES=('TC442PetAttackRestore','TC442PetAttackDummy')


def dummy():
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation,'
            'c.phaseMask,t.minlevel,t.maxlevel,t.faction,t.ScriptName,c.MovementType '
            'FROM client442_world.creature c JOIN client442_world.creature_template t ON t.entry=c.id WHERE c.guid=279984')
        row=q.fetchone()
    if (not row or row[:4]!=(279984,44548,'Training Dummy',0) or
        row[8:]!=(1,3,3,7,'npc_training_dummy',0) or
        any(not math.isfinite(v) for v in row[4:8])):
        raise RuntimeError('existing passive training dummy contract differs')
    return list(row)


class PetAttackFixture:
    def __init__(self,out,actor):
        if tuple(actor.get(k) for k in ('guid','account_id','character_name','race','class','level'))!=(5,2,'Harnessctrl',1,9,10):
            raise ValueError('requires the unchanged trained owned warlock')
        self.out,self.actor=out,actor;self.before=None;self.rows=[];self.native=identity('worldserver');self.dummy=dummy()

    def persist(self):
        source=lab.REPO/'src/server/scripts/World/npcs_special_services.cpp'
        lab.private_write(self.out/'pet_attack_fixture.json',json.dumps({
            'schema':'client442_owned_pet_attack_fixture_v1','actor':self.actor,'native':self.native,
            'before':self.before,'rows':self.rows,'dummy':self.dummy,
            'source':'Owned native-console pose staging only; existing dummy is not spawned, modified or reset.',
            'script_source':str(source),'script_source_sha256':lab.sha256(source)},indent=2)+'\n')

    def verify_rows(self):
        if identity('worldserver')!=self.native or dummy()!=self.dummy:raise RuntimeError('native fixture or dummy changed')
        with lab.connection() as c,c.cursor() as q:
            for row in self.rows:
                q.execute('SELECT id,position_x,position_y,position_z,orientation,map,name '
                    'FROM client442_world.game_tele WHERE id=%s',(row[0],))
                if list(q.fetchone() or ())!=row:raise RuntimeError('temporary pet attack teleport changed')

    def prepare(self):
        current=character(5,2)
        if current['name']!='Harnessctrl' or current['level']!=10 or current['online']!=1:
            raise RuntimeError('pet attack fixture requires the owned online warlock')
        self.before=position(5);self.persist()
        if self.before[4]!=0:raise RuntimeError('requires original map0')
        x,y,z=self.dummy[4:7];ground=(x+3,y,z,math.pi,0)
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',NAMES)
            if q.fetchone():raise RuntimeError('an earlier pet attack fixture needs cleanup')
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
        if any(abs(a-b)>.01 for a,b in zip(actual,ground)):raise RuntimeError('pet attack pose staging differs')
        return actual

    def restore(self):
        if not self.rows:return None
        self.verify_rows();current=character(5,2)
        if current['name']!='Harnessctrl' or current['level']!=10 or current['online']!=1:
            raise RuntimeError('owned pet attack fixture identity differs')
        lab.server_command('tele name Harnessctrl '+NAMES[0]);time.sleep(4);actual=position(5)
        if any(abs(a-b)>.01 for a,b in zip(actual,self.before)):
            raise RuntimeError('pet attack restoration differs; restore teleport retained')
        self.verify_rows()
        with lab.connection() as c,c.cursor() as q:
            for row in self.rows:
                q.execute('DELETE FROM client442_world.game_tele WHERE id=%s AND name=%s',(row[0],row[-1]))
                if q.rowcount!=1:raise RuntimeError('temporary pet attack teleport removal rejected')
        lab.server_command('reload game_tele')
        result={'position':actual,'original_position':self.before,'temporary_teleports_removed':[r[0] for r in self.rows],
            'dummy_unchanged':dummy()==self.dummy,'source':'Native fixture cleanup only; ordinary pet outcomes scored separately.'}
        lab.private_write(self.out/'pet_attack_restoration.json',json.dumps(result,indent=2)+'\n');return result

    @classmethod
    def resume(cls,out,actor,path):
        path=path.resolve()
        if path.name!='pet_attack_fixture.json' or not path.is_relative_to(lab.ROOT/'evidence') or path.is_symlink():
            raise ValueError('requires a private owned pet attack fixture')
        row=json.loads(path.read_text());self=cls(out,actor)
        if (row['actor']!=actor or row['native']!=self.native or row['dummy']!=self.dummy or
            len(row['rows'])!=2 or [r[-1] for r in row['rows']]!=list(NAMES)):
            raise RuntimeError('closed pet attack fixture source differs')
        self.before=row['before'];self.rows=row['rows'];self.verify_rows();return self
