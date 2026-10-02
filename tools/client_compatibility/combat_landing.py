"""Land and dismount for bounded melee against ordinary low-level attackers."""
import json
import math
import time
from . import archaeology_inputs, ground_navigation, hostile_avoidance, lab_runtime as lab
from . import model_collision, site_boundaries, site_landing


def permitted(movement,extra,facts,player_level):
    attackers=[h for h in facts['visible_hostiles'] if h['guid'] in facts['attacking_units']]
    return bool(movement['in_world'] and movement['in_combat'] and not movement['dead'] and
        not movement['on_taxi'] and extra['mounted'] and not any(extra.get(k) for k in
        ['falling','swimming','indoors']) and hostile_avoidance.low_threat(
        attackers,player_level,movement['health_percent']>=80))


def flight_plan(facts,extra):
    start=facts['position'];site=site_boundaries.active_site(facts['map'],start,extra['digsite_ids'])
    goal,selection=site_landing.select(site,start)
    distance=math.dist(start[:2],goal[:2])
    if distance>100:raise RuntimeError('combat landing exceeds the short in-site corridor')
    columns=[]
    for index in range(math.ceil(distance/5)+1):
        fraction=min(1,index*5/max(distance,.01))
        point=[start[i]+(goal[i]-start[i])*fraction for i in range(3)]
        surface=model_collision.supporting_surface(facts['map'],point)
        if surface['highest_surface'] is None:raise RuntimeError('combat landing has an unknown public collision column')
        columns.append(surface)
    ceiling=max(start[2],goal[2]+20,*[c['highest_surface']+10 for c in columns])
    if ceiling>start[2]+80:raise RuntimeError('combat landing needs excessive additional ascent')
    a=[*start[:2],ceiling];b=[*goal[:2],ceiling]
    if not model_collision.clear_body_segment(facts['map'],a,b):raise RuntimeError('combat landing cruise is obstructed')
    return site,goal,{'source':'public site soil patch and static model collision; no private find coordinates',
        'selected':goal,'selection':selection,'ceiling':ceiling,'columns':columns}


def run(movement,extra,facts,observer,path):
    from .travel_inputs import face
    from .combat_clear import run as clear
    from tools.second_client import ctl
    if not permitted(movement,extra,facts,observer.player_level):raise RuntimeError('combat landing requires verified low-threat attackers')
    ctl._launcher_env=lab.client_environment;inputs=ctl.Input()
    site=site_boundaries.active_site(facts['map'],facts['position'],extra['digsite_ids'])
    trace={'schema':'public_combat_landing_v1','site_id':site['id'],'started_at':time.time(),
        'before':facts,'observations':[],'physical_keys':[],'completed':False,'failure':None}
    evidence=path.parent/f'combat_landing_{time.time_ns()}.json'
    try:
        goal=facts['position'][:3]
        if extra['flying']:
            site,goal,plan=flight_plan(facts,extra);trace['plan']=plan
            deadline=time.monotonic()+60;stalled=0;previous=None
            for _ in range(30):
                movement,extra=archaeology_inputs.screenshot(path);now=observer.poll();p=now['position']
                trace['observations'].append({'facts':now,'movement':movement,'travel':extra})
                if time.monotonic()>deadline or now['map']!=facts['map'] or not movement['in_world'] or movement['dead'] or (
                    movement['health_percent']<50 or movement['on_taxi'] or extra['falling'] or extra['swimming'] or
                    not extra['mounted'] or not site_boundaries.contains(site['polygon'],p)):
                    raise RuntimeError('combat landing lost a bounded safe state')
                horizontal=math.dist(p[:2],goal[:2]);vertical=max(0,p[2]-goal[2])
                if not extra['flying']:
                    if horizontal>1.5 or abs(p[2]-goal[2])>2:raise RuntimeError('combat landing settled on the wrong floor')
                    ground_navigation.site_ground_patch(facts['map'],p)
                    break
                if horizontal>1.2 and p[2]<plan['ceiling']-1:
                    key='space';hold=min(1.5,max(.05,(plan['ceiling']-p[2])/28.7));metric=('ascent',plan['ceiling']-p[2])
                elif horizontal>1.2:
                    trace['physical_keys'].extend(face(inputs,observer,goal))
                    key='w';hold=min(1.2,horizontal/28.7);metric=('cruise',horizontal)
                else:
                    key='x';hold=min(1.5,max(.08,vertical/28.7));metric=('descent',vertical)
                stalled=stalled+1 if previous and metric[0]==previous[0] and metric[1]>=previous[1]-.3 else 0
                if stalled>=3:raise RuntimeError('combat landing made no physical progress')
                previous=metric;inputs.key(key,hold=hold);trace['physical_keys'].append({'key':key,'hold':hold})
                time.sleep(.4)
            else:raise RuntimeError('combat landing exhausted its input budget')
        # Never dismount while the normal addon still reports flying/falling.
        movement,extra=archaeology_inputs.screenshot(path);now=observer.poll()
        if extra['flying'] or extra['falling'] or extra['swimming'] or movement['dead'] or movement['health_percent']<50:
            raise RuntimeError('combat dismount requires settled healthy ground')
        inputs.key('3');trace['physical_keys'].append({'key':'3','reason':'normal grounded dismount'})
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            movement,extra=archaeology_inputs.screenshot(path)
            if not extra['mounted']:break
            time.sleep(.2)
        if extra['mounted']:raise RuntimeError('combat dismount was not observed')
        result=clear(movement,extra,observer.poll(),observer,path)
        trace['completed']=True;trace['after']=observer.poll()
        result['combat_landing_receipt']=evidence.name
        return result
    except BaseException as error:trace['failure']=f'{type(error).__name__}: {error}';raise
    finally:
        trace['finished_at']=time.time();lab.private_write(evidence,json.dumps(trace,indent=2)+'\n')
