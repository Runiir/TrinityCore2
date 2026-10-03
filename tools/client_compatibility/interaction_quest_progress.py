"""Ordinary melee credit on an existing Prowler; fixture warps are not travel proof."""
import argparse,json,math,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_quest_accept import suite as accept_suite,QUEST
from .interaction_quest_fixture import quest_state
from .interaction_macros import require

SPAWN=281458
NAME='TC442QuestCombat'


def native_counts():
    rows=[r for r in quest_state(1)['active'] if r['quest']==QUEST]
    if len(rows)!=1:raise RuntimeError('trial quest no longer has one active native row')
    return {k:v for k,v in rows[0].items() if k.startswith('mobcount') or k in ['quest','status']}


def progress(t,giver):
    t.clean_panels();row=None
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation '
            'FROM client442_world.creature c JOIN client442_world.creature_template t ON c.id=t.entry WHERE c.guid=%s',(SPAWN,))
        spawn=q.fetchone()
        if not spawn or spawn[:4]!=(SPAWN,118,'Prowler',0):raise RuntimeError('registered quest combat spawn changed')
        q.execute('SELECT id FROM client442_world.game_tele WHERE name=%s',(NAME,))
        if q.fetchone():raise RuntimeError('earlier combat fixture requires restoration')
        q.execute('SELECT MAX(id) FROM client442_world.game_tele');tele_id=q.fetchone()[0]+1
        x,y,z,o=spawn[4:];dx,dy=2*math.cos(o),2*math.sin(o)
        row=(tele_id,x+dx,y+dy,z,math.atan2(-dy,-dx)%(2*math.pi),0,NAME)
        q.execute('INSERT INTO client442_world.game_tele '
            '(id,position_x,position_y,position_z,orientation,map,name) VALUES (%s,%s,%s,%s,%s,%s,%s)',row)
        q.execute('SELECT id,CAST(position_x AS DOUBLE),CAST(position_y AS DOUBLE),CAST(position_z AS DOUBLE),'
            'CAST(orientation AS DOUBLE),map,name FROM client442_world.game_tele WHERE id=%s',(tele_id,));row=q.fetchone()
    t.receipt['combat_fixture']={'source':'native_console_staging_only','spawn':spawn,'teleport':row,
        'scope':'No spawn/reset/kill/quest-credit command; staging does not qualify navigation.'};t.persist()
    before=native_counts()
    try:
        lab.server_command('reload game_tele');time.sleep(.5)
        with t.bounded_combat_observation(60):
            lab.server_command('tele name Harnessone '+NAME);time.sleep(3)
            require(t.step('quests.progress_target','Target the nearby ordinary Prowler.',
                {'target':{'kind':'chat','value':'/targetexact Prowler','description':'Target the nearby Prowler by its visible name.'}},
                lambda b,a,s:{'status':'quest_target_pass' if s=='target' and a.get('target',{}).get('name')=='Prowler' and
                    a['target'].get('visible') and a['target'].get('health',0)>0 else 'client_or_protocol_failure',
                    'oracle':{'target':a.get('target'),'native_counts_before':before}},diagnostic_action='target'),'quest_target_pass')
            target=t.receipt['cases'][-1]['after']['target'];t.receipt['combat_target']=target;t.persist()
            def killed(b,a,s):
                samples=[];deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    native=native_counts();probe=a.get('manual_quest_probe',{})
                    samples.append({'native':native,'public':probe,'target':a.get('target')})
                    if native.get('mobcount1')==before.get('mobcount1',0)+1:break
                    time.sleep(.5);a,frame=t.observe('combat_progress_'+str(len(samples)))
                matched=any(o.get('required')==8 and o.get('fulfilled')==before.get('mobcount1',0)+1
                    for o in probe.get('objectives',[]))
                passed=s=='attack' and native.get('mobcount1')==before.get('mobcount1',0)+1 and matched
                return {'status':'quest_progress_pass' if passed else 'client_or_protocol_failure',
                    'oracle':{'samples':samples,'native_credit':native,'public_credit_agrees':matched,
                        'target_before_attack':target,'ordinary_attack_only':True}}
            require(t.step('quests.progress_kill','Attack the Prowler and verify one wolf objective credit.',
                {'attack':{'kind':'chat','value':'/startattack','description':'Start ordinary melee attacks on the targeted Prowler.'}},
                killed,diagnostic_action='attack'),'quest_progress_pass')
            t.execute({'kind':'chat','value':'/stopattack'})
            deadline=time.monotonic()+8
            while True:
                state,frame=t.observe('combat_settled')
                if not frame['movement']['in_combat']:break
                if time.monotonic()>deadline:raise RuntimeError('combat did not settle after bounded ordinary attack')
                time.sleep(.5)
    finally:
        # Returning to the existing giver restores staging and ends any failed
        # out-of-range engagement. It is cleanup, never a gameplay pass.
        lab.server_command('tele name Harnessone '+giver.rows[1][-1]);time.sleep(4)
        t.execute({'kind':'chat','value':'/stopattack'});t.execute({'kind':'chat','value':'/cleartarget'})
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT id,CAST(position_x AS DOUBLE),CAST(position_y AS DOUBLE),CAST(position_z AS DOUBLE),'
                'CAST(orientation AS DOUBLE),map,name FROM client442_world.game_tele WHERE id=%s',(row[0],))
            if q.fetchone()!=row:raise RuntimeError('combat teleport changed; refusing deletion')
            q.execute('DELETE FROM client442_world.game_tele WHERE id=%s AND name=%s',(row[0],NAME))
        lab.server_command('reload game_tele');t.receipt['combat_fixture']['teleport_removed']=True;t.persist()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--review-point-file',type=Path,required=True);a=p.parse_args()
    if a.review_point_file.exists():p.error('point review must be fresh for the staged frame')
    t=Trial(a.output,controller='code')
    try:accept_suite(t,a.review_point_file,False,after_read=progress);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
