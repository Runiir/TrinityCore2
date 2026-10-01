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


def locate_find(inputs,path):
    # Search the ordinary 3D view with cursor hover, then verify the game's
    # tooltip against known find names. No teacher pixel or private coordinates.
    preferred=[(655,331),(640,360),(655,400),(620,400)]
    grid=[(x,y) for x in range(500,781,20) for y in range(240,541,20)]
    grid.sort(key=lambda p:(p[0]-655)**2+(p[1]-370)**2)
    deadline=time.monotonic()+25
    for x,y in [*preferred,*grid]:
        if time.monotonic()>deadline:break
        inputs.move(x,y);time.sleep(.2)
        _,extra=screenshot(path)
        if extra['tooltip_name_checksum'] in FIND_CHECKSUMS:
            time.sleep(.3)
            _,confirmed=screenshot(path)
            if confirmed['tooltip_name_checksum']!=extra['tooltip_name_checksum']:continue
            with Image.open(path) as image:image.save(path.parent/'localized_find.webp',lossless=True)
            return (x,y)
    raise RuntimeError('no archaeology find tooltip in the bounded screen search')


def execute(action,tcp,path,recovery=None,mounted_moves=False):
    ctl._launcher_env=lab.client_environment;inputs=ctl.Input();hold=None;pixel=None;ground_route=None;loot_approach=None
    if action=='survey':inputs.key('2')
    elif action.startswith('turn_'):
        if not tcp['tool']:raise ValueError('turn without a survey observation')
        hold=min(.55,max(.025,abs(tcp['tool']['turn_error_radians'])/math.pi))
        inputs.key('a' if action=='turn_left' else 'd',hold=hold)
    elif action.startswith('forward_'):
        if not tcp['tool']:raise ValueError('walk without a survey observation')
        short,long={'red':(2,6),'yellow':(1,3),'green':(.5,1)}[tcp['tool']['color']]
        hold=short if action=='forward_short' else long
        with Image.open(path) as image:digsite_ids=travel.decode_image(image)['digsite_ids']
        if mounted_moves and tcp['tool']['color']!='green':
            from . import travel_trial,travel_routes,site_boundaries
            planned=ground_navigation.survey_ray(tcp,hold*7,digsite_ids)
            start=tcp['player']['position'];site=site_boundaries.sites()[planned['boundary_guard']['site_id']]
            targets=[p for p in planned['points'][1:] if math.dist(p[:2],start[:2])>1.5 and
                     site_boundaries.inside_segment(site['polygon'],start,p)]
            if not targets:raise RuntimeError('no in-site mounted waypoint from public survey heading')
            target=None;attempts=[]
            # A short telescope move can end against a hill. Try farther
            # public-bearing waypoints so flight can cross its steep face.
            heading=planned['heading_radians']
            farther=[]
            for scale in [2,3]:
                distance=site_boundaries.clip_distance(site['polygon'],start,heading,min(84,hold*7*scale))
                farther.append([start[0]+math.cos(heading)*distance,start[1]+math.sin(heading)*distance,start[2]])
            for waypoint in [*reversed(targets),*farther]:
                try:candidate=ground_navigation.landing_point(site['map'],waypoint,start=start)
                except RuntimeError:continue
                attempts.append({'waypoint':waypoint,'landing':candidate})
                if math.dist(candidate[:2],start[:2])>=3 and site_boundaries.inside_segment(site['polygon'],start,candidate):
                    target=candidate;break
            if target is None:raise RuntimeError('no flatter in-site landing near the public survey waypoint')
            planned['mounted_landing']={'requested':targets[-1],'selected':target,'maximum_detail_slope_degrees':20,
                'attempts':attempts,'source':'public static ground detail triangles; no private find coordinates'}
            profile=travel_routes.clearance(site['map'],start,target)
            route={'schema':'public_survey_mounted_move_v1','legs':[{'id':'mounted_survey_step','mode':'flight',
                'map':site['map'],'position':target,'ceiling':profile['ceiling'],'height_profile':profile,'arrival_radius':3,
                'ground_connection_origin':start[:3]}]}
            directory=path.parent/f'mounted_move_{time.time_ns()}'
            result=travel_trial.run(route,directory,maximum_steps=45)
            if not result['completed']:raise RuntimeError('mounted dig movement failed: '+str(result['failure']))
            _,after=screenshot(path)
            inside=site_boundaries.contains(site['polygon'],after['world_position'])
            ground_route={**planned,'mounted_travel_episode':directory.name,
                'boundary_guard':{**planned['boundary_guard'],'observed_after_inside':inside}}
        else:hold,ground_route=ground_navigation.walk(inputs,tcp,hold*7,digsite_ids)
    elif action=='loot':
        if not tcp['finds']:raise ValueError('loot without a visible owned find')
        owned_input.focus()
        start=tcp['player']['position'];find=min(tcp['finds'],key=lambda f:math.dist(f['position'][:2],start[:2]))
        if math.dist(find['position'][:2],start[:2])<3:
            from . import site_boundaries
            _,extra=screenshot(path)
            site=site_boundaries.active_site(find['map'],start,extra['digsite_ids'])
            distance=3.5-math.dist(find['position'][:2],start[:2])
            goal=[start[0]-math.cos(start[3])*distance,start[1]-math.sin(start[3])*distance,start[2]]
            if not site_boundaries.inside_segment(site['polygon'],start,goal):
                raise RuntimeError('overlapping artifact has no in-site backward approach')
            # Ordinary player feet and the already visible artifact, not a
            # private target. Moving off the model makes its mouse hit visible.
            ground_navigation.route(find['map'],start,goal)
            # Backpedalling is 4.5 yards/second, slower than forward walking.
            inputs.key('s',hold=distance/4.5);time.sleep(.4)
            from .observation.archaeology import Observer
            after=Observer().poll(start[3])['player']['position']
            if not site_boundaries.contains(site['polygon'],after):raise RuntimeError('loot approach left the digsite')
            loot_approach={'source':'visible owned artifact overlaps player feet','before':start,'after':after,
                'physical_keys':[{'key':'s','hold':distance/4.5}],'observed_after_inside':True}
        pixel=locate_find(inputs,path)
        # The owned Classic client can render at 15 FPS. Keep the button down
        # for multiple frames so the physical use action is observed reliably.
        inputs.click(*pixel,button=3,hold=.2)
    elif action!='observe':raise ValueError('unknown physical action')
    time.sleep(2.5 if action in ['survey','loot'] else .5)
    return {'hold_seconds':hold,'mouse_pixel':pixel,'mouse_hold_seconds':.2 if pixel else None,
            'pixel_source':'ordinary_game_tooltip_hover' if pixel else None,
            'collision_recovery':recovery,'ground_route':ground_route,'loot_approach':loot_approach}
