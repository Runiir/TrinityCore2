"""Bounded keyboard flight and mouse taxi input driven by public observations."""
import math
import time
from tools.second_client import ctl
from . import lab_runtime as lab,owned_input
from .observation.archaeology import angle_error
from .observation import taxi,telemetry,gossip


def face(inputs,observer,goal):
    keys=[]
    for _ in range(8):
        current=observer.poll()['position'];heading=math.atan2(goal[1]-current[1],goal[0]-current[0])
        error=angle_error(heading,current[3])
        # Recorded 15 FPS clients turn in roughly 0.2-radian steps. A tighter
        # threshold oscillates or misses sub-frame key taps indefinitely.
        if abs(error)<.12:return keys
        key='a' if error>0 else 'd';hold=min(.6,max(.04,abs(error)/math.pi))
        inputs.key(key,hold=hold);time.sleep(.15);keys.append({'key':key,'hold':hold})
    raise RuntimeError('unable to face public travel waypoint')


def execute(action,leg,facts,extra,observer,path):
    from PIL import Image
    from . import archaeology_inputs
    ctl._launcher_env=lab.client_environment;inputs=ctl.Input();keys=[];pixel=None;collision=None
    goal=leg.get('vendor_position') if action=='interact' else leg.get('position')
    position=facts['position']
    if action=='mount':inputs.key('3');keys.append({'key':'3'});time.sleep(2)
    elif action=='takeoff':
        hold=min(3,max(.15,(leg['ceiling']-position[2])/28.7))
        inputs.key('space',hold=hold);keys.append({'key':'space','hold':hold})
        time.sleep(.3);after=observer.poll()
        if after['map']==facts['map'] and not after['transferring'] and hold>=.5 and after['position'][2]-position[2]<max(.4,hold*2.87):
            from .flight_recovery import nudge
            if leg.get('blocked_climb_escapes',0)>=8:raise RuntimeError('blocked climb exceeded eight bounded escapes')
            _,fresh=archaeology_inputs.screenshot(path)
            collision=nudge(inputs,leg,observer,path,fresh)
            leg['blocked_climb_escapes']=leg.get('blocked_climb_escapes',0)+1
    elif action=='cruise':
        if not extra['mounted'] or not extra['flying']:raise RuntimeError('model attempted unmounted flight')
        keys=face(inputs,observer,goal)
        distance=math.dist(observer.poll()['position'][:2],goal[:2])
        hold=min(4,max(.03,(distance-min(2,leg.get('arrival_radius',5)*.4))/28.7))
        inputs.key('w',hold=hold);keys.append({'key':'w','hold':hold})
    elif action=='land':
        if not goal:raise RuntimeError('landing without a public ground waypoint')
        hold=min(3,max(.15,(position[2]-goal[2])/28.7))
        inputs.key('x',hold=hold);keys.append({'key':'x','hold':hold})
        time.sleep(.25);after=observer.poll()
        if not leg.get('trigger') and hold>=.2 and position[2]-after['position'][2]<.35:
            _,fresh=archaeology_inputs.screenshot(path)
            if fresh['flying']:
                from .landing_recovery import nudge
                collision=nudge(inputs,leg,observer,path,fresh)
    elif action=='dismount':
        if extra['flying'] or extra['falling']:raise RuntimeError('model attempted dismount in the air')
        inputs.key('3');keys.append({'key':'3'})
    elif action=='interact':
        if not goal or math.dist(position[:3],goal[:3])>8:raise RuntimeError('flight master is out of interaction range')
        with Image.open(path) as image:options=gossip.decode_image(image)
        flight=next((o for o in (facts.get('gossip_menu') or {}).get('options',[]) if o['icon']==2),None)
        caption=next((o for o in options['options'] if flight and o['id']==flight['id'] and
                      o['caption_checksum']==telemetry.checksum(flight['title'].encode())),None)
        if caption:
            pixel=caption['pixel'];inputs.click(*pixel);time.sleep(1)
            return {'physical_keys':[],'mouse_pixel':pixel,'mouse_source':'ordinary_visible_gossip_caption'}
        keys=face(inputs,observer,goal)
        expected=telemetry.checksum(leg['name'].encode())
        from .flightmaster_input import locate
        pixel=locate(inputs,path,expected)
        inputs.click(*pixel,button=3,hold=.2)
        time.sleep(1)
    elif action=='taxi':
        with Image.open(path) as image:menu=taxi.decode_image(image)
        node=next((n for n in menu['nodes'] if n['id']==leg['destination']),None)
        if not node:raise RuntimeError('destination has no observed visible taxi button')
        pixel=node['pixel'];inputs.click(*pixel);time.sleep(1)
    elif action=='portal':
        # Use only the reviewed public entrance and real client trigger.
        if math.dist(position[:2],goal[:2])>90:raise RuntimeError('portal is outside the bounded approach')
        keys=face(inputs,observer,goal)
        hold=min(2,math.dist(observer.poll()['position'][:2],goal[:2])/7)
        inputs.key('w',hold=hold);keys.append({'key':'w','hold':hold});time.sleep(1)
    elif action=='observe':time.sleep(.5)
    elif action!='arrived':raise ValueError('unknown travel action')
    if action in ['mount','dismount']:
        # Wait for the visible state transition before another toggle or route
        # leg. Aura removal can briefly mark a grounded character as falling.
        deadline=time.monotonic()+6
        while True:
            movement,after=archaeology_inputs.screenshot(path)
            if action=='mount' and movement['in_combat'] and not after['mounted']:
                return {'physical_keys':keys,'mouse_pixel':None,'collision_recovery':None,
                    'transition_confirmed':False,'interrupted_by_combat':True}
            confirmed=after['mounted']==(action=='mount') and not after['casting']
            if confirmed and not after['falling']:break
            if time.monotonic()>deadline:raise RuntimeError(f'{action} was not confirmed by addon state')
            time.sleep(.2)
    time.sleep(.25)
    return {'physical_keys':keys,'mouse_pixel':pixel,'mouse_source':'ordinary_addon_ui_or_tooltip' if pixel else None,
        'collision_recovery':collision}
