"""Plan public flights/taxis and the bidirectional Dark Portal connection."""
import json
import math
from . import lab_runtime as lab,ground_navigation,site_boundaries
from .observation.map_data import catalog
from .world.taxi import route as taxi_path

MASTERS=lab.REPO/'experiments/configs/client_harness/public_flightmasters_v1.json'
PORTALS={0:{'destination_map':530,'approach':[-11890,-3209,-14.56],
    'crossing':[-11924,-3209,-14.79],'trigger':4354,'arrival':[-248.113,922.9,84.3497]},
    530:{'destination_map':0,'approach':[-247.677,835,41.25],
    'crossing':[-247.677,895.675,144.362],'trigger':4352,'arrival':[-11896.8,-3206.77,-14.6724]}}


def flight(map_id,position,id):
    return {'id':id,'mode':'flight','map':map_id,'position':position,
            'ceiling':max(230,position[2]+100)}


def clearance(map_id,start,goal):
    distance=math.dist(start[:2],goal[:2]);count=min(160,max(2,math.ceil(distance/50)))
    heights=[start[2],goal[2]];missing=0
    for i in range(1,count):
        xy=[start[a]+(goal[a]-start[a])*i/count for a in range(2)]
        try:heights.append(ground_navigation.ground_point(map_id,xy)[2])
        except RuntimeError:missing+=1
    return {'ceiling':max(230,max(heights)+80),'sampled_ground_columns':len(heights)-2,
        'missing_ground_columns':missing,'ground_maximum':max(heights),
        'source':'public static NAV_GROUND height columns; 80-yard obstacle allowance'}


def prepare_clearance(plan,map_id,position):
    for leg in plan['legs']:
        if leg['mode']=='flight':
            if leg.get('trigger'):
                if map_id!=530 or leg['trigger']!=4352 or leg['position']!=PORTALS[530]['crossing']:
                    raise RuntimeError('unreviewed airborne portal route')
                leg['ceiling']=leg['position'][2]
                leg['height_profile']={'source':'reviewed public AreaTrigger 4352 box center; native teleport proximity remains authoritative'}
            else:
                original=leg['position']
                leg['position']=ground_navigation.ground_point(map_id,original,maximum_height=original[2]+8)
                if leg.get('site_id'):
                    leg['position']=ground_navigation.landing_point(map_id,leg['position'])
                    site=site_boundaries.sites()[leg['site_id']]
                    if not site_boundaries.contains(site['polygon'],leg['position']):
                        raise RuntimeError('flat landing is outside the destination digsite')
                leg['landing_height_source']={'source':'public static NAV_GROUND column',
                    'requested_position':original,'ground_position':leg['position']}
                profile=clearance(map_id,position,leg['position'])
                leg['ceiling']=max(leg['ceiling'],profile['ceiling']);leg['height_profile']=profile
        if leg['mode']=='portal' or leg.get('trigger'):
            position=PORTALS[map_id]['arrival'];map_id=leg['destination_map']
        else:position=leg['position']
    return plan


def same_map(map_id,start,goal):
    masters=json.loads(MASTERS.read_text())['nodes'];c=catalog();known={int(k) for k in masters}
    candidates=[m for m in masters.values() if m['map']==map_id]
    nearest=lambda p:sorted(candidates,key=lambda m:math.dist(m['position'][:2],p[:2]))[:4]
    best=math.dist(start[:2],goal[:2])/28.7;pair=None
    for source in nearest(start):
        for end in nearest(goal):
            if source['node']==end['node']:continue
            try:taxi_path(source['node'],end['node'],known,c['taxi_paths'])
            except ValueError:continue
            cost=(math.dist(start[:2],source['position'][:2])+math.dist(end['position'][:2],goal[:2]))/28.7+15
            if cost+5<best:best=cost;pair=(source,end)
    legs=[]
    if pair:
        source,end=pair
        # Land beside the vendor and face them for a tooltip-guided click.
        staging=[source['position'][0]+3,*source['position'][1:]]
        legs.append(flight(map_id,staging,'approach_flightmaster'))
        legs.append({'id':'instant_taxi','mode':'taxi','map':map_id,
            'position':c['taxi_nodes'][end['node']]['position'],'destination':end['node'],
            'vendor_position':source['position'],'name':source['name']})
    legs.append(flight(map_id,goal,'approach_destination'))
    if map_id==530 and goal==PORTALS[530]['approach']:
        # 60895's open stair approach is 20 yards above the legacy ground mesh,
        # verified by an ordinary grounded client movement packet (loop 20).
        legs[-1]['landing_height_tolerance']=25
        legs[-1]['landing_height_note']='60895 stair approach contact Z61.329; legacy column Z41.25'
    return legs


def to_site(map_id,start,site):
    if map_id not in PORTALS or site['map'] not in PORTALS:
        raise RuntimeError('this verified route catalog currently covers Eastern Kingdoms and Outland')
    legs=[]
    if map_id!=site['map']:
        portal=PORTALS[map_id]
        legs.extend(same_map(map_id,start,portal['approach']))
        legs.append({'id':'dark_portal','mode':'flight' if map_id==530 else 'portal','map':map_id,'position':portal['crossing'],
                     'destination_map':portal['destination_map'],'trigger':portal['trigger'],'arrival_radius':.5})
        map_id=portal['destination_map'];start=portal['arrival']
    goal=ground_navigation.ground_point(map_id,site['center'])
    if not site_boundaries.contains(site['polygon'],goal):raise RuntimeError('public landing point falls outside digsite')
    legs.extend(same_map(map_id,start,goal));legs[-1]['site_id']=site['id']
    return {'schema':'client442_public_site_route_v1','site':site['id'],'legs':legs,
            'source':'public digsite polygons, NPC spawns, taxi graph and static navigation mesh'}
