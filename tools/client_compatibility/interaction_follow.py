"""Two-client movement and follow with public native packets and reversible staging."""
import argparse,json,math,time
from pathlib import Path
from . import actors,lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .interaction_macros import require
from .nearby_fixture import NearbyFixture
from .observation.journal import entries
from .world.buffer import Reader


def distance(a,b):return math.dist(a[:2],b[:2])


def suite(out):
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    cohort={'started_at':time.time(),'completed':False,'failure':None};trials={};fixture=None;sessions={}
    flag=lab.ROOT/'run/capture_public_movement';started=time.time()
    try:
        if flag.exists():raise RuntimeError('another movement capture is active')
        lab.private_write(flag,str(out)+'\n')
        for name in ['primary','scout']:
            with actor(name):
                t=trials[name]=Trial(out/name);sessions[name]=actors.session_entry(t.fixture)['session'];t.clean_panels()
                s,_=t.observe('observer_fixture')
                if 'follow' not in s:raise RuntimeError('follow observer is not deployed')
        fixture=NearbyFixture(out,trials['primary'].fixture,trials['scout'].fixture,open_ground=True);fixture.prepare()
        with actor('scout'):
            trials['scout'].execute({'kind':'chat','value':'/targetexact Harnessone'})
            initial,_=trials['scout'].observe('peer_before')
            if initial['target'].get('guid')!='Player-1-00000001':raise RuntimeError('nearby player fixture target missing')
        with actor('primary'):
            t=trials['primary']
            def moved(b,a,s):
                d=distance(b['world_position'],a['world_position'])
                return {'status':'movement_pass' if s=='move' and d>3 else
                    ('controller_failure' if s!='move' else 'client_or_protocol_failure'),
                    'oracle':{'distance':d,'before':b['world_position'],'after':a['world_position']}}
            require(t.step('movement.strafe_public','Move right far enough for the other player to see the new position.',{
                'move':{'kind':'key','value':'e','hold':1.2,'description':'Hold E for 1.2 seconds to strafe right.'},
                'map':{'kind':'key','value':'m','description':'Open the world map.'},
                'jump':{'kind':'key','value':'space','description':'Jump in place.'}},moved),'movement_pass')
            own,_=t.observe('mover_after')
        with actor('scout'):
            peer,frame=trials['scout'].observe('peer_after')
            p=peer['target'].get('position',[])
            facts={'expected':own['world_position'],'peer':p,'frame':frame,
                'initial_peer':initial['target'].get('position')}
            facts['matches']=len(p)>=2 and distance(p,own['world_position'])<.2 and distance(p,initial['target']['position'])>3
            trials['scout'].receipt['peer_movement_oracle']=facts;trials['scout'].persist()
            if not facts['matches']:raise RuntimeError('other client did not observe the moved player position')
        with actor('primary'):
            t=trials['primary']
            def followed(b,a,s):
                d=distance(a['world_position'],initial['world_position'])
                return {'status':'follow_pass' if s=='follow' and a['follow'].get('active') and
                    a['follow'].get('name')=='Harnesstwo' and d<3 else
                    ('controller_failure' if s!='follow' else 'client_or_protocol_failure'),
                    'oracle':{'follow':a['follow'],'remaining_distance':d,'position':a['world_position']}}
            require(t.step('movement.follow_nearby','Follow the nearby owned player Harnesstwo.',{
                'follow':{'kind':'chat','value':'/follow Harnesstwo','description':'Type /follow Harnesstwo to follow the nearby player.'},
                'target':{'kind':'chat','value':'/targetexact Harnesstwo','description':'Target Harnesstwo without following.'},
                'map':{'kind':'key','value':'m','description':'Open the map.'}},followed),'follow_pass')
            require(t.step('movement.stop_follow','Stop following the nearby player.',{
                'stop':{'kind':'key','value':'s','hold':.15,'description':'Press S briefly to move backward and stop following.'},
                'map':{'kind':'key','value':'m','description':'Open the map.'},
                'target':{'kind':'chat','value':'/targetexact Harnesstwo','description':'Target the nearby player.'}},
                lambda b,a,s:{'status':'stop_follow_pass' if s=='stop' and not a['follow'].get('active') else
                    ('controller_failure' if s!='stop' else 'client_or_protocol_failure'),'oracle':{'follow':a['follow']}}),'stop_follow_pass')
        packets=[r for r in entries(lab.ROOT/'evidence/world_packets.jsonl') if r.get('time',0)>=started and
            r.get('name')=='SMSG_MOVE_UPDATE' and r.get('session')==sessions['scout']]
        native=[r for r in packets if r.get('direction')=='from_native']
        modern=[r for r in packets if r.get('direction')=='to_modern' and Reader(bytes.fromhex(r['body'])).guid()[0]==1]
        lab.private_write(out/'public_movement_packets.json',json.dumps(packets,indent=2)+'\n')
        cohort['public_movement_packets']={'native':len(native),'modern':len(modern)}
        if not native or not modern:raise RuntimeError('public movement has no attributable native/modern packet pair')
        cohort['completed']=True
    except Exception as e:cohort['failure']=f'{type(e).__name__}: {e}'
    finally:
        if flag.exists() and flag.read_text()==str(out)+'\n':flag.unlink()
        for name,t in trials.items():
            with actor(name):
                try:
                    t.clean_panels();s,_=t.observe('cleanup_follow')
                    if s.get('follow',{}).get('active'):t.execute({'kind':'key','value':'s','hold':.15})
                except Exception as e:cohort['completed']=False;cohort.setdefault('cleanup_failures',{})[name]=str(e)
        if fixture:
            try:fixture.restore()
            except Exception as e:cohort.update(completed=False,cleanup_failure=str(e))
        for name,t in trials.items():
            with actor(name):
                try:
                    s,_=t.observe('cleanup_target')
                    if s.get('target',{}).get('exists'):t.execute({'kind':'key','value':'Escape'})
                    s,f=t.observe('restored');t.receipt['restoration']={'frame':f,'world_position':s['world_position'],'follow':s.get('follow')}
                except Exception as e:cohort['completed']=False;cohort.setdefault('cleanup_failures',{})[name]=str(e)
            t.receipt.update(completed=cohort['completed'],failure=cohort['failure'],finished_at=time.time());t.persist()
        cohort['finished_at']=time.time();lab.private_write(out/'cohort.json',json.dumps(cohort,indent=2)+'\n');print(json.dumps(cohort),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);suite(p.parse_args().output)
