"""Qualify nearby owned player visibility and ordinary name targeting."""
import argparse,json,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_macros import require
from .nearby_fixture import NearbyFixture
from .observation.journal import entries
from .world.native_objects import records


def suite(out):
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    cohort={'started_at':time.time(),'completed':False,'failure':None};trials={};sessions={};fixture=None
    try:
        for name in ['primary','scout']:
            with actor(name):
                t=trials[name]=Trial(out/name);sessions[name]=actors.session_entry(t.fixture)['session'];t.clean_panels()
        fixture=NearbyFixture(out,trials['primary'].fixture,trials['scout'].fixture);since=time.time();fixture.prepare()
        # Separate the overlapping characters through ordinary owned input.
        with actor('primary'):trials['primary'].io.key('s',hold=.6);time.sleep(1)
        creations=[]
        for row in entries(lab.ROOT/'evidence/world_packets.jsonl'):
            if row.get('time',0)<since or row.get('direction')!='from_native' or row.get('name')!='SMSG_UPDATE_OBJECT':continue
            actor_name=next((n for n,s in sessions.items() if row.get('session')==s),None)
            if not actor_name:continue
            other=2 if actor_name=='primary' else 1
            for record in records(bytes.fromhex(row['body'])):
                if record.get('guid')==other and record.get('kind')==4:
                    creations.append({'actor':actor_name,'time':row['time'],'record':record})
        lab.private_write(out/'native_peer_creates.json',json.dumps(creations,indent=2)+'\n')
        cohort['native_peer_creates']={name:sum(r['actor']==name for r in creations) for name in trials}
        failed=False
        for name,t in trials.items():
            other_name,other_guid=('Harnesstwo',2) if name=='primary' else ('Harnessone',1)
            with actor(name):
                def outcome(b,a,s):
                    target=a['target'];expected=f'Player-1-{other_guid:08X}'
                    passed=s=='peer' and target.get('guid')==expected and target['exists'] and target['visible'] and target['player']
                    return {'status':'nearby_target_pass' if passed else
                        ('controller_failure' if s!='peer' else 'client_or_protocol_failure'),
                        'oracle':{'target':target,'expected_guid':expected,'native_peer_create_count':cohort['native_peer_creates'][name]}}
                row=t.step('player.target_nearby','Target the nearby owned player '+other_name+'.',{
                    'peer':{'kind':'chat','value':'/targetexact '+other_name,'description':'Type /targetexact '+other_name+' to target the nearby player.'},
                    'self':{'kind':'chat','value':'/targetexact '+t.fixture['character_name'],'description':'Target your own character.'},
                    'map':{'kind':'key','value':'m','description':'Open the map.'}},outcome)
                failed|=row['status']!='nearby_target_pass'
        if failed:raise RuntimeError('nearby owned player targeting did not qualify on both clients')
        cohort['completed']=True
    except Exception as e:cohort['failure']=f'{type(e).__name__}: {e}'
    finally:
        if fixture:
            with actor('primary'):
                try:fixture.restore()
                except Exception as e:cohort.update(completed=False,cleanup_failure=str(e))
        for name,t in trials.items():
            with actor(name):
                try:
                    t.clean_panels();t.execute({'kind':'key','value':'Escape'});s,f=t.observe('restored')
                    t.receipt['restoration']={'frame':f,'world_position':s.get('world_position')}
                except Exception as e:cohort['completed']=False;cohort.setdefault('cleanup_failures',{})[name]=str(e)
            t.receipt.update(completed=cohort['completed'],failure=cohort['failure'],finished_at=time.time());t.persist()
        cohort['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(cohort,indent=2)+'\n')
        print(json.dumps(cohort),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);suite(p.parse_args().output)
