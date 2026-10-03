"""Inspect ordinary targeting beside an existing bear; no quest or combat edits."""
import argparse,json,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .observation.transport import Observer

NAME='TC442BearTargetProbe'


def suite(t):
    t.clean_panels();lab.server_command('saveall');time.sleep(1)
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT position_x,position_y,position_z,orientation,map FROM client442_characters.characters WHERE guid=1')
        before=q.fetchone()
        q.execute('SELECT guid,id,position_x,position_y,position_z,map FROM client442_world.creature WHERE guid=280196')
        spawn=q.fetchone()
        if not spawn or spawn[:2]!=(280196,822) or spawn[-1]!=0:raise RuntimeError('registered bear spawn changed')
        q.execute('SELECT id FROM client442_world.game_tele WHERE name IN (%s,%s)',(NAME,NAME+'Restore'))
        if q.fetchone():raise RuntimeError('previous bear probe requires restoration')
        q.execute('SELECT MAX(id) FROM client442_world.game_tele');start=q.fetchone()[0]+1
        rows=[]
        for i,(name,pose) in enumerate([(NAME+'Restore',before),(NAME,(spawn[2]+8,spawn[3],spawn[4],3.14159,0))]):
            q.execute('INSERT INTO client442_world.game_tele '
                '(id,position_x,position_y,position_z,orientation,map,name) VALUES (%s,%s,%s,%s,%s,%s,%s)',(start+i,*pose,name))
            q.execute('SELECT id,CAST(position_x AS DOUBLE),CAST(position_y AS DOUBLE),CAST(position_z AS DOUBLE),'
                'CAST(orientation AS DOUBLE),map,name FROM client442_world.game_tele WHERE id=%s',(start+i,));rows.append(q.fetchone())
    t.receipt['fixture']={'source':'native_console_staging_only','spawn':spawn,'before':before,'teleports':rows};t.persist()
    try:
        with t.bounded_combat_observation(60):
            lab.server_command('reload game_tele');time.sleep(.5);lab.server_command('tele name Harnessone '+NAME);time.sleep(4)
            t.observe('bear_probe_staged');observer=Observer(guid=1);facts=observer.poll()
            t.receipt['native_bears']=[{'guid':g,'position':u.get('movement',{}).get('position'),'fields':u['fields']}
                for g,u in observer.units.items() if g>>32&0xfffff==822];t.persist()
            actions=[{'kind':'chat','value':'/targetexact Young Forest Bear'}]+[{'kind':'key','value':'Tab'}]*6
            t.receipt['target_observations']=[]
            for i,action in enumerate(actions):
                t.execute(action);state,frame=t.observe('target_probe_'+str(i));facts=observer.poll()
                t.receipt['target_observations'].append({'input':action,'public':state.get('target'),'frame':frame,'native':facts});t.persist()
                unit=facts.get('selected_unit')
                if unit and unit['guid']>>32&0xfffff==822:
                    t.receipt['bear_targeted']={'public':state.get('target'),'native':unit};t.persist();return
        raise RuntimeError('neither exact-name targeting nor six ordinary Tab selections reached the visible native bear')
    finally:
        lab.server_command('tele name Harnessone '+rows[0][-1]);time.sleep(4);lab.server_command('saveall');time.sleep(1)
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT position_x,position_y,position_z,orientation,map FROM client442_characters.characters WHERE guid=1')
            after=q.fetchone()
            if any(abs(a-b)>.01 for a,b in zip(before,after)):raise RuntimeError('bear probe pose restoration failed')
            for row in rows:
                q.execute('SELECT id,CAST(position_x AS DOUBLE),CAST(position_y AS DOUBLE),CAST(position_z AS DOUBLE),'
                    'CAST(orientation AS DOUBLE),map,name FROM client442_world.game_tele WHERE id=%s',(row[0],))
                if q.fetchone()!=row:raise RuntimeError('bear probe teleport changed; refusing deletion')
                q.execute('DELETE FROM client442_world.game_tele WHERE id=%s AND name=%s',(row[0],row[-1]))
        lab.server_command('reload game_tele');t.receipt['restoration']={'position':after,'teleports_removed':True};t.persist()
        t.execute({'kind':'chat','value':'/cleartarget'})


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    t=Trial(a.output,controller='code')
    try:suite(t);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
