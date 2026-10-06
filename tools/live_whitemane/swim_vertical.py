"""Execute one selected depth adjustment with measured height and retained input."""
import fcntl
import time
from . import runtime,inputs,action_queue
from .observe import observe
from .sticky_input import StickyInput,observation_lease
from .boundaries import check_point


def move(folder,action,guide,before):
    if action not in ('swim_up','swim_down'):raise ValueError('not a swimming depth action')
    sign=1 if action=='swim_up' else -1
    pose=before.get('owned_pose') or {};start_height=pose.get('height_yards')
    if not before['archaeology'].get('swimming') or start_height is None:
        raise RuntimeError('swimming depth adjustment requires an owned height observation')
    target=(guide or {}).get('world',{}).get('height_yards')
    exact=target is not None and sign*(target-start_height)>.5
    target=target if exact else start_height+sign*3
    speed=(before.get('farm_ui') or {}).get('move_speeds',{}).get('swim') or 5
    deadline=time.monotonic()+10+3*abs(target-start_height)/speed
    result={'action':action,'started_at':time.time(),'start_height_yards':start_height,
        'target_height_yards':target,'target_source':'owned visible find' if exact else 'local depth probe',
        'observations':[],'completed':False,'fixed_hold_seconds':None}
    with (runtime.ROOT/'run/input.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from .camera_input import Input
        inputs.focus('World of Warcraft');sender=Input();sticky=StickyInput(sender)
        key='space' if sign>0 else 'x';previous=None;last_progress=time.monotonic()
        samples=[]
        try:
            while time.monotonic()<deadline:
                row=observe(folder/'swim_depth.png');action_queue.validate(row,before)
                a=row['archaeology'];pose=row.get('owned_pose') or {};height=pose.get('height_yards')
                if row['movement']['in_combat'] or a['casting']:
                    raise RuntimeError('swimming depth adjustment interrupted by client state')
                if not a.get('swimming'):
                    result.update(completed=True,outcome='left_swimming_mode');return result
                if height is None:raise RuntimeError('swimming depth adjustment lost owned height observation')
                if (guide or {}).get('boundary_site_id'):check_point(guide['boundary_site_id'],a['world'])
                sticky.lease=observation_lease(row);sticky.renew()
                remaining=sign*(target-height)
                result['observations']=(result['observations']+[{'at':row['observed_at'],
                    'height_yards':height,'remaining_yards':remaining}])[-40:]
                if remaining<=.4:
                    result.update(completed=True,outcome='target_depth_reached');return result
                if previous and pose.get('client_uptime_ms')!=previous.get('client_uptime_ms'):
                    delta=((pose['client_uptime_ms']-previous['client_uptime_ms'])%2**32)/1000
                    if delta>0:
                        rate=sign*(height-previous['height_yards'])/delta
                        if rate>.1:samples=(samples+[rate])[-6:]
                    if sign*(height-previous['height_yards'])>.05:last_progress=time.monotonic()
                previous=pose
                if time.monotonic()-last_progress>2:
                    result['outcome']='no_observed_depth_progress';return result
                rate=max(samples) if samples else speed
                age=pose.get('age_seconds',0)
                duration=max(1/max(1,(row.get('farm_ui') or {}).get('frame_rate') or 30),(remaining-.4)/rate-age)
                sticky.hold(key,True,duration if duration<.5 else None)
                time.sleep(.1)
            result['outcome']='calculated_depth_bound_reached';return result
        finally:
            sticky.close();result['finished_at']=time.time()
            runtime.write(folder/'swim_depth.json',result)
