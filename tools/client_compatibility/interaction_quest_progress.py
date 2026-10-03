"""Ordinary melee credit on an existing Prowler; fixture warps are not travel proof."""
import argparse,json,math,time
from pathlib import Path
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_quest_accept import suite as accept_suite,QUEST
from .interaction_quest_fixture import quest_state
from .interaction_macros import require
from .observation.transport import Observer
from .observation.journal import entries
from .world.buffer import Reader
from .world.gameobjects import modern_guid
from .travel_inputs import face

SPAWN=280953
NAME='TC442QuestCombat'


def native_counts():
    rows=[r for r in quest_state(1)['active'] if r['quest']==QUEST]
    if len(rows)!=1:raise RuntimeError('trial quest no longer has one active native row')
    return {k:v for k,v in rows[0].items() if k.startswith('mobcount') or k in ['quest','status']}


def progress(t,giver,spawn_id=SPAWN,entry=118,name='Prowler',counter='mobcount1',required=8,prefix='quests.progress'):
    if (entry,name,counter,required) not in [(118,'Prowler','mobcount1',8),(822,'Young Forest Bear','mobcount2',5)]:
        raise ValueError('combat trial requires a registered quest 52 objective')
    t.clean_panels();row=None
    with lab.connection() as c,c.cursor() as q:
        q.execute('SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation '
            'FROM client442_world.creature c JOIN client442_world.creature_template t ON c.id=t.entry WHERE c.guid=%s',(spawn_id,))
        spawn=q.fetchone()
        if not spawn or spawn[:4]!=(spawn_id,entry,name,0):raise RuntimeError('registered quest combat spawn changed')
        q.execute('SELECT id FROM client442_world.game_tele WHERE name=%s',(NAME,))
        if q.fetchone():raise RuntimeError('earlier combat fixture requires restoration')
        q.execute('SELECT MAX(id) FROM client442_world.game_tele');tele_id=q.fetchone()[0]+1
        x,y,z,o=spawn[4:]
        # This registered bear spawn overlaps a large client tree. The farther
        # initial observation point passed the ordinary exact-name probe.
        dx,dy=(8,0) if entry==822 else (2*math.cos(o),2*math.sin(o))
        # A spawn's ground Z is not the height at an offset point. Start above
        # that floor so normal client gravity can settle on nearby terrain;
        # otherwise a slightly uphill offset can put the actor under the map.
        row=(tele_id,x+dx,y+dy,z+8,math.atan2(-dy,-dx)%(2*math.pi),0,NAME)
        q.execute('INSERT INTO client442_world.game_tele '
            '(id,position_x,position_y,position_z,orientation,map,name) VALUES (%s,%s,%s,%s,%s,%s,%s)',row)
        q.execute('SELECT id,CAST(position_x AS DOUBLE),CAST(position_y AS DOUBLE),CAST(position_z AS DOUBLE),'
            'CAST(orientation AS DOUBLE),map,name FROM client442_world.game_tele WHERE id=%s',(tele_id,));row=q.fetchone()
    t.receipt['combat_fixture']={'source':'native_console_staging_only','spawn':spawn,'teleport':row,
        'scope':'No spawn/reset/kill/quest-credit command; staging does not qualify navigation.'};t.persist()
    record=t.receipt['combat_fixture'];t.receipt.setdefault('combat_fixtures',[]).append(record);t.persist()
    before=native_counts()
    try:
        lab.server_command('reload game_tele');time.sleep(.5)
        with t.bounded_combat_observation(60):
            lab.server_command('tele name Harnessone '+NAME);time.sleep(3)
            require(t.step(prefix+'_target','Target the nearby ordinary '+name+'.',
                {'target':{'kind':'chat','value':'/targetexact '+name,'description':'Target the nearby '+name+' by its visible name.'}},
                lambda b,a,s:{'status':'quest_target_pass' if s=='target' and a.get('target',{}).get('name')==name and
                    a['target'].get('visible') and a['target'].get('health',0)>0 else 'client_or_protocol_failure',
                    'oracle':{'target':a.get('target'),'native_counts_before':before}},diagnostic_action='target'),'quest_target_pass')
            target=t.receipt['cases'][-1]['after']['target'];t.receipt['combat_target']=target;t.persist()
            # Random-movement creatures may be far from their stored spawn.
            # Stage beside the actual visible target, never assume its DB pose
            # is its current pose. This remains fixture setup, not movement proof.
            facts=Observer(guid=1).poll();unit=facts.get('selected_unit')
            record['observed_target_before_staging']=facts;t.persist()
            if not unit or unit['guid']>>32&0xFFFFF!=entry or unit['health']!=unit['max_health']:
                raise RuntimeError('requires an undamaged observed '+name)
            distance=math.dist(facts['position'][:3],unit['position'][:3])
            if distance>100:raise RuntimeError(f'observed combat staging target is {distance:.1f} yards away')
            x,y,z,o=unit['position'];dx,dy=2*math.cos(o),2*math.sin(o)
            with lab.connection() as c,c.cursor() as q:
                q.execute('UPDATE client442_world.game_tele SET position_x=%s,position_y=%s,position_z=%s,orientation=%s '
                    'WHERE id=%s AND name=%s',(x+dx,y+dy,z+3,math.atan2(-dy,-dx)%(2*math.pi),row[0],NAME))
                q.execute('SELECT id,CAST(position_x AS DOUBLE),CAST(position_y AS DOUBLE),CAST(position_z AS DOUBLE),'
                    'CAST(orientation AS DOUBLE),map,name FROM client442_world.game_tele WHERE id=%s',(row[0],));row=q.fetchone()
            t.receipt['combat_fixture']['observed_target_staging']={'facts':facts,'teleport':row};t.persist()
            lab.server_command('reload game_tele');time.sleep(.5)
            lab.server_command('tele name Harnessone '+NAME);time.sleep(1)
            observer=Observer(guid=1);approaches=[]
            def approach():
                current=observer.poll();near=current.get('selected_unit')
                if not near or near['guid']!=unit['guid']:raise RuntimeError('combat approach target changed')
                distance=math.dist(current['position'][:3],near['position'][:3])
                if distance>15 or abs(current['position'][2]-near['position'][2])>3:
                    raise RuntimeError('moving target escaped the bounded ground approach')
                keys=face(t.io,observer,near['position'])
                if distance>3:
                    hold=min(1.5,(distance-2.5)/7);t.io.key('w',hold=hold);keys.append({'key':'w','hold':hold})
                approaches.append({'time':time.time(),'facts':current,'physical_keys':keys})
                record['ordinary_approaches']=approaches;t.persist()
            approach()
            started=time.time()
            def killed(b,a,s):
                samples=[];deadline=time.monotonic()+15
                while time.monotonic()<deadline:
                    native=native_counts();probe=a.get('manual_quest_probe',{})
                    samples.append({'native':native,'public':probe,'target':a.get('target')})
                    if native.get(counter)==before.get(counter,0)+1:break
                    if len(approaches)<4:approach()
                    time.sleep(.5);a,frame=t.observe('combat_progress_'+str(len(samples)))
                matched=any(o.get('required')==required and o.get('fulfilled')==before.get(counter,0)+1
                    for o in probe.get('objectives',[]))
                packets=[p for p in entries(lab.ROOT/'evidence/world_packets.jsonl') if p.get('time',0)>=started and
                    p.get('session')==facts['session'] and p.get('name')=='SMSG_QUEST_UPDATE_ADD_CREDIT']
                credit=False
                for p in packets:
                    if p['direction']!='to_client':continue
                    r=Reader(bytes.fromhex(p['body']));victim=r.guid();values=r.unpack('IIHHB');r.end()
                    credit|=victim==modern_guid(unit['guid'],0) and values==(QUEST,entry,before.get(counter,0)+1,required,0)
                passed=s=='attack' and native.get(counter)==before.get(counter,0)+1 and matched and credit
                return {'status':'quest_progress_pass' if passed else 'client_or_protocol_failure',
                    'oracle':{'samples':samples,'native_credit':native,'public_credit_agrees':matched,
                        'target_before_attack':target,'ordinary_attack_only':True,'credit_packets':packets,'modern_credit_agrees':credit}}
            require(t.step(prefix+'_kill','Attack the '+name+' and verify one objective credit.',
                {'attack':{'kind':'chat','value':'/startattack','description':'Start ordinary melee attacks on the targeted '+name+'.'}},
                killed,diagnostic_action='attack'),'quest_progress_pass')
            t.execute({'kind':'chat','value':'/stopattack'})
    finally:
        # Returning to the existing giver restores staging and ends any failed
        # out-of-range engagement. It is cleanup, never a gameplay pass.
        lab.server_command('tele name Harnessone '+giver.rows[1][-1]);time.sleep(4)
        t.execute({'kind':'chat','value':'/stopattack'});t.execute({'kind':'chat','value':'/cleartarget'})
        # Nearby wolves can assist their killed pack member. Fixture departure
        # ends that surrounding combat; do not demand peace while still there.
        state,frame=t.observe(prefix+'_settled_at_giver')
        record['settled_at_giver']=frame;t.persist()
        with lab.connection() as c,c.cursor() as q:
            q.execute('SELECT id,CAST(position_x AS DOUBLE),CAST(position_y AS DOUBLE),CAST(position_z AS DOUBLE),'
                'CAST(orientation AS DOUBLE),map,name FROM client442_world.game_tele WHERE id=%s',(row[0],))
            if q.fetchone()!=row:raise RuntimeError('combat teleport changed; refusing deletion')
            q.execute('DELETE FROM client442_world.game_tele WHERE id=%s AND name=%s',(row[0],NAME))
        lab.server_command('reload game_tele');record['teleport_removed']=True;t.persist()


def complete(t,giver):
    # Validate the newly exercised bear targets before repeating the qualified
    # wolf objective. Credits still come from one uninterrupted ordinary run.
    for i,spawn in enumerate([280196,280203,280228,280233,280276],1):
        progress(t,giver,spawn_id=spawn,entry=822,name='Young Forest Bear',counter='mobcount2',required=5,
            prefix='quests.complete_bear_'+str(i))
    for i,spawn in enumerate([280953,280958,280966,281013,281017,281018,281019,281020],1):
        progress(t,giver,spawn_id=spawn,prefix='quests.complete_wolf_'+str(i))
    state,frame=t.observe('quest_objectives_complete');native=native_counts()
    objectives=state.get('manual_quest_probe',{}).get('objectives',[])
    passed=native.get('status')==1 and native.get('mobcount1')==8 and native.get('mobcount2')==5 and len(objectives)==2 and all(
        o.get('finished') and o.get('fulfilled')==o.get('required') for o in objectives)
    t.receipt['completion_oracle']={'native':native,'public':objectives,'frame':frame,'passed':passed};t.persist()
    if not passed:raise RuntimeError('all ordinary kills did not complete the native/public quest')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--review-point-file',type=Path,required=True);p.add_argument('--complete',action='store_true');a=p.parse_args()
    if a.review_point_file.exists():p.error('point review must be fresh for the staged frame')
    t=Trial(a.output,controller='code')
    try:accept_suite(t,a.review_point_file,False,after_read=complete if a.complete else progress);t.receipt['completed']=True
    except Exception as e:t.receipt['failure']=f'{type(e).__name__}: {e}'
    finally:
        t.receipt['finished_at']=time.time();t.persist()
        print(json.dumps({'completed':t.receipt['completed'],'failure':t.receipt['failure']}),flush=True)
