"""Physical inputs and tooltip-guided find localization for the owned client."""
import contextlib
import io
import math
import time
from PIL import Image
from tools.second_client import ctl
from . import lab_runtime as lab
from . import owned_input,ground_navigation
from .observation import telemetry,travel

FIND_NAMES=['Night Elf Archaeology Find','Nerubian Archaeology Find','Dwarf Archaeology Find',
    'Fossil Archaeology Find','Troll Archaeology Find','Orc Archaeology Find','Draenei Archaeology Find',
    'Vrykul Archaeology Find',"Tol'vir Archaeology Find"]
FIND_CHECKSUMS={telemetry.checksum(name.encode()) for name in FIND_NAMES}


def screenshot(path):
    ctl._launcher_env=lab.client_environment
    with contextlib.redirect_stdout(io.StringIO()):ctl.shot(str(path))
    with Image.open(path) as image:
        movement=telemetry.decode_image(image,x=15,y=15,cell_size=3.75)
        extra=travel.decode_image(image)
    return movement,extra


def find_hover_points():
    # Sloping ground puts a nearby, faced artifact well above the character's
    # feet. Cover the full central vertical strip before the wider radial scan.
    preferred=[(640,275),(640,285)]
    vertical=[(640+dx,y) for dx in [0,-8,8,-16,16] for y in range(160,513,8)]
    grid=[(x,y) for x in range(320,961,24) for y in range(160,575,24)]
    grid.sort(key=lambda p:(p[0]-640)**2+(p[1]-340)**2)
    return list(dict.fromkeys([*preferred,*vertical,*grid]))


def locate_find(inputs,path,timeout=40,require_visible=None):
    # Search the ordinary 3D view with cursor hover, then verify the game's
    # tooltip against known find names. No teacher pixel or private coordinates.
    deadline=time.monotonic()+timeout
    for x,y in find_hover_points():
        if require_visible:require_visible()
        if time.monotonic()>deadline:break
        inputs.move(x,y);time.sleep(.2)
        _,extra=screenshot(path)
        if extra['tooltip_name_checksum'] in FIND_CHECKSUMS:
            # GameTooltip can remain shown while fading after the cursor
            # leaves an object. Verify this exact point from a cleared tip.
            inputs.move(400,100)
            for _ in range(6):
                time.sleep(.25);_,cleared=screenshot(path)
                if cleared['tooltip_name_checksum'] not in FIND_CHECKSUMS:break
            if cleared['tooltip_name_checksum'] in FIND_CHECKSUMS:continue
            inputs.move(x,y);time.sleep(.3)
            _,confirmed=screenshot(path)
            if confirmed['tooltip_name_checksum']!=extra['tooltip_name_checksum']:continue
            with Image.open(path) as image:image.save(path.parent/'localized_find.webp',lossless=True)
            return (x,y)
    raise RuntimeError('no archaeology find tooltip in the bounded screen search')


def execute(action,tcp,path,recovery=None,mounted_moves=False,object_observer=None):
    ctl._launcher_env=lab.client_environment;inputs=ctl.Input();hold=None;pixel=None;ground_route=None;loot_approach=None
    if action=='survey':
        _,extra=screenshot(path)
        planned=ground_navigation.dry_cast_plan(tcp,extra)
        if planned:
            from .observation.archaeology import Observer
            from .swim_navigation import cross
            hold,ground_route=cross(inputs,Observer(),planned,path)
            ground_route['reason']='reach dry shore before the selected Survey cast'
        inputs.key('2')
    elif action.startswith('turn_'):
        if not tcp['tool']:raise ValueError('turn without a survey observation')
        hold=min(.55,max(.025,abs(tcp['tool']['turn_error_radians'])/math.pi))
        inputs.key('a' if action=='turn_left' else 'd',hold=hold)
    elif action.startswith('forward_'):
        if not tcp['tool']:raise ValueError('walk without a survey observation')
        short,long={'red':(2,6),'yellow':(1,3),'green':(.5,1)}[tcp['tool']['color']]
        hold=short if action=='forward_short' else long
        with Image.open(path) as image:extra=travel.decode_image(image)
        digsite_ids=extra['digsite_ids']
        if mounted_moves and tcp['tool']['color']!='green':
            from . import travel_trial,travel_routes,site_boundaries
            planned=ground_navigation.survey_ray(tcp,hold*7,digsite_ids)
            start=tcp['player']['position'];site=site_boundaries.sites()[planned['boundary_guard']['site_id']]
            targets=[p for p in planned['points'][1:] if math.dist(p[:2],start[:2])>1.5 and
                     site_boundaries.inside_segment(site['polygon'],start,p)]
            if not targets:raise RuntimeError('no in-site mounted waypoint from public survey heading')
            from .survey_landing import select
            target,planned['mounted_landing']=select(site,start,planned['heading_radians'],hold*7)
            planned['mounted_landing']['requested']=targets[-1]
            profile=travel_routes.clearance(site['map'],start,target)
            heading=planned['heading_radians']
            bearing_progress=(target[0]-start[0])*math.cos(heading)+(target[1]-start[1])*math.sin(heading)
            route={'schema':'public_survey_mounted_move_v1','legs':[{'id':'mounted_survey_step','mode':'flight',
                'map':site['map'],'position':target,'ceiling':profile['ceiling'],'height_profile':profile,'arrival_radius':1.5,
                'landing_height_tolerance':2,
                'survey_progress':{'start':start[:3],'heading_radians':heading,
                    'minimum_bearing_progress':max(1.5,bearing_progress*.5)},
                'ground_connection_origin':start[:3]}]}
            directory=path.parent/f'mounted_move_{time.time_ns()}'
            result=travel_trial.run(route,directory,maximum_steps=45)
            if not result['completed']:raise RuntimeError('mounted dig movement failed: '+str(result['failure']))
            _,after=screenshot(path)
            inside=site_boundaries.contains(site['polygon'],after['world_position'])
            ground_route={**planned,'mounted_travel_episode':directory.name,
                'boundary_guard':{**planned['boundary_guard'],'observed_after_inside':inside}}
        else:
            from .ground_escape import TerrainBlocked
            from . import green_flight
            repeated=mounted_moves and tcp['tool']['color']=='green' and (recovery or {}).get('attempt',0)>=2
            if repeated:
                hold,ground_route=green_flight.execute(tcp,path,recovery,'repeated_blocked_ground_advances')
            else:
                try:
                    hold,ground_route=ground_navigation.walk(inputs,tcp,hold*7,digsite_ids,recovery,
                        grounded=not any(extra[k] for k in ['mounted','flying','falling','swimming']),path=path)
                except TerrainBlocked:
                    if not mounted_moves or tcp['tool']['color']!='green':raise
                    hold,ground_route=green_flight.execute(tcp,path,recovery,'ground_routes_exhausted')
    elif action=='loot':
        if not tcp['finds']:raise ValueError('loot without a visible owned find')
        owned_input.focus()
        start=tcp['player']['position'];find=min(tcp['finds'],key=lambda f:math.dist(f['position'][:2],start[:2]))
        from .travel_inputs import face
        from .observation.transport import Observer as TransportObserver
        observer=TransportObserver()
        facing_keys=face(inputs,observer,find['position'])
        time.sleep(.4);start=observer.poll()['position']
        loot_approach={'source':'ordinary visible artifact bearing','physical_keys':facing_keys}
        if math.dist(find['position'][:2],start[:2])<3:
            from . import site_boundaries
            _,extra=screenshot(path)
            site=site_boundaries.active_site(find['map'],start,extra['digsite_ids'])
            from . import loot_pose
            loot_approach=loot_pose.approach(inputs,observer,find,site,path)
            loot_approach['physical_keys']=[*facing_keys,*loot_approach['physical_keys']]
        from .find_interaction import locate,FindExpired
        def require_visible():
            if object_observer is not None and not any(f['guid']==find['guid'] for f in object_observer.poll(0)['finds']):
                raise FindExpired('artifact disappeared in ordinary owned object packets')
        pixel,localization=locate(inputs,observer,find,path,require_visible=require_visible)
        loot_approach['localization']=localization
        # The owned Classic client can render at 15 FPS. Keep the button down
        # for multiple frames so the physical use action is observed reliably.
        inputs.click(*pixel,button=3,hold=.2)
    elif action!='observe':raise ValueError('unknown physical action')
    time.sleep(2.5 if action in ['survey','loot'] else .5)
    return {'hold_seconds':hold,'mouse_pixel':pixel,'mouse_hold_seconds':.2 if pixel else None,
            'pixel_source':'ordinary_game_tooltip_hover' if pixel else None,
            'collision_recovery':recovery,'ground_route':ground_route,'loot_approach':loot_approach}
