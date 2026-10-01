"""Bounded physical walk/swim transit to a public, dry survey waypoint."""
import json
import math
import time
from . import lab_runtime as lab,site_boundaries
from .observation.archaeology import angle_error


class CombatInterrupted(RuntimeError):
    """A healthy, in-bounds character needs the normal combat recovery."""


def available(movement,extra,position,polygon):
    if not movement['in_world'] or any(movement[k] for k in ['dead','on_taxi']):
        raise RuntimeError('walk/swim transit interrupted by unavailable character')
    if movement['health_percent']<50:raise RuntimeError('walk/swim transit health guard')
    if extra['mounted'] or extra['flying']:raise RuntimeError('walk/swim transit must remain unmounted')
    if not site_boundaries.contains(polygon,position):raise RuntimeError('walk/swim transit left the public digsite')
    if movement['in_combat']:raise CombatInterrupted('physical approach interrupted by combat')


def dry_arrival(position,goal,extra):
    return math.dist(position[:2],goal[:2])<=1.25 and not any(extra[k] for k in ['swimming','falling','mounted','flying'])


def cross(inputs,observer,planned,path):
    from .archaeology_inputs import screenshot
    if path is None:raise RuntimeError('walk/swim transit requires addon observations')
    polygon=site_boundaries.sites()[planned['boundary_guard']['site_id']]['polygon']
    goal=planned['points'][-1];points=[p[:] for p in planned['points']]
    transit={'schema':'public_walk_swim_transit_v1','started_at':time.time(),
        'route':planned.copy(),'observations':[],'physical_inputs':[],
        'decision_origin':'physical_navigation_adapter','completed':False,'failure':None}
    receipt_path=path.parent/f'water_transit_{time.time_ns()}.json'
    total_hold=0;blocked=0;failure=None
    try:
        for _ in range(45):
            if time.time()-transit['started_at']>90:raise RuntimeError('walk/swim transit exceeded local movement budget')
            movement,extra=screenshot(path);position=observer.poll(0)['player']['position']
            available(movement,extra,position,polygon)
            transit['observations'].append({'time':time.time(),'position':position,
                'movement':movement,'travel':extra})
            lab.private_write(receipt_path,json.dumps(transit,indent=2)+'\n')
            if dry_arrival(position,goal,extra):transit['completed']=True;break
            while len(points)>1 and math.dist(position[:2],points[0][:2])<=1.25:points.pop(0)
            target=points[0]
            # Once the shoreline waypoint is reached, move toward the dry
            # endpoint rather than repeatedly surveying while swimming.
            heading=math.atan2(target[1]-position[1],target[0]-position[0])
            error=angle_error(heading,position[3])
            if abs(error)>.12:
                key='a' if error>0 else 'd';hold=min(.55,max(.04,abs(error)/math.pi))
                inputs.key(key,hold=hold);time.sleep(.25)
                transit['physical_inputs'].append({'key':key,'hold':hold});continue
            speed=4.72 if extra['swimming'] else 7.
            hold=min(1.5,max(.12,math.dist(position[:2],target[:2])/speed))
            if blocked>=2:
                from .ground_navigation import low_step_hop
                hop=low_step_hop(position,target,{'attempt':1},grounded=not extra['swimming'] and not extra['falling'])
                if hop:
                    inputs.key('space',hold=.15)
                    transit['physical_inputs'].append({'key':'space','hold':.15,'low_step_hop':hop})
            inputs.key('w',hold=hold);time.sleep(.35);total_hold+=hold
            after=observer.poll(0)['player']['position']
            transit['physical_inputs'].append({'key':'w','hold':hold,'swimming_before':extra['swimming'],
                'before':position,'after':after})
            if math.dist(position[:2],after[:2])<max(.08,hold*speed*.15):blocked+=1
            else:blocked=0
            if blocked>=3:raise RuntimeError('three blocked walk/swim advances failed to reach dry ground')
        else:raise RuntimeError('walk/swim input budget ended before dry arrival')
    except BaseException as error:
        failure=f'{type(error).__name__}: {error}';raise
    finally:
        transit.update(finished_at=time.time(),failure=failure)
        lab.private_write(receipt_path,json.dumps(transit,indent=2)+'\n')
    planned.update(after=position,remaining_ground_points=[],physical_inputs=transit['physical_inputs'],
        dry_arrival_confirmed=True,water_transit_receipt=receipt_path.name,
        swimming_observed=any(o['travel']['swimming'] for o in transit['observations']),
        steering_source='public ground/water navigation mesh and normal addon swimming state')
    planned['boundary_guard']['observed_after_inside']=True
    return total_hold,planned
