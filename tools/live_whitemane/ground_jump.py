"""A selected forward jump ends on observed landing, not an assumed jump height."""
import fcntl
import math
import time
from . import runtime,inputs,action_queue
from .observe import observe
from .sticky_input import StickyInput,observation_lease
from .camera_navigation import align
from .boundaries import check_point


def legal(row):
    a,m=row['archaeology'],row['movement']
    return bool(a.get('grounded') and not any(a.get(k) for k in
        ('mounted','flying','falling','swimming','casting')) and m['in_world']
        and not m['dead'] and not m['in_combat'] and m['health_percent']>0)


def move(folder,before,target):
    if not legal(before):raise RuntimeError('grounded jump invalidated by client state')
    world=before['archaeology']['world']
    if not world or target['instance']!=world['instance']:
        raise RuntimeError('grounded jump requires a local destination')
    distance=math.hypot(target['north']-world['north'],target['west']-world['west'])
    if distance>4.01:raise RuntimeError('grounded jump exceeds its local approach')
    result={'action':'jump_forward','target':target,'start_world':world,
        'started_at':time.time(),'observations':[],'completed':False,'assumed_jump_height':None}
    before=action_queue.wait_stopped(folder,before,observe)
    result['camera']=align(folder/'jump_view',before,target,reset_view=False)
    before=observe(folder/'jump_ready.png')
    if not legal(before):raise RuntimeError('grounded jump invalidated by client state')
    site=before['archaeology'].get('site_id') if before['archaeology'].get('can_survey') else None
    if site is not None:check_point(site,target)
    initial=(before.get('owned_pose') or {}).get('height_yards');peak=initial
    with (runtime.ROOT/'run/input.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from .camera_input import Input
        inputs.focus('World of Warcraft');sender=Input();sticky=StickyInput(sender)
        started=time.monotonic();airborne=False;last_sequence=None
        # A key-down only needs to span one rendered frame. Physical landing
        # and displacement determine the end of the selected movement.
        fps=max(1,(before.get('farm_ui') or {}).get('frame_rate') or 30)
        try:
            sticky.lease=observation_lease(before);sticky.renew()
            sticky.hold('Up',True);sticky.hold('space',True,2/fps)
            while time.monotonic()-started<5:
                row=observe(folder/'jump_feedback.png');action_queue.validate(row,before)
                a,m=row['archaeology'],row['movement']
                if m['in_combat'] or a['casting'] or a.get('mounted') or a.get('swimming') or a['flying']:
                    raise RuntimeError('grounded jump interrupted by client state')
                if sticky.interrupted:raise RuntimeError(sticky.interrupted)
                sticky.lease=observation_lease(row);sticky.renew()
                if m['sequence']==last_sequence:time.sleep(.02);continue
                last_sequence=m['sequence'];w=a['world']
                if site is not None:check_point(site,w)
                height=(row.get('owned_pose') or {}).get('height_yards')
                if height is not None:peak=max(height,peak) if peak is not None else height
                airborne=airborne or bool(a['falling'] or not a.get('grounded')
                    or initial is not None and height is not None and height-initial>.2)
                moved=math.hypot(w['north']-world['north'],w['west']-world['west'])
                remaining=math.hypot(target['north']-w['north'],target['west']-w['west'])
                result['observations']=(result['observations']+[{'at':row['observed_at'],
                    'height_yards':height,'grounded':a.get('grounded'),'falling':a['falling'],
                    'moved_yards':moved,'remaining_yards':remaining}])[-40:]
                if remaining<=.5 or moved>=distance:sticky.hold('Up',False)
                if airborne and a.get('grounded') and not a['falling']:
                    result.update(completed=True,outcome='landed',walked_yards=moved,
                        forward_progress_yards=distance-remaining,after=row);return result
                if not airborne and time.monotonic()-started>1:
                    result.update(outcome='no_observed_jump',walked_yards=moved);return result
                time.sleep(.05)
            result['outcome']='landing_not_confirmed';return result
        finally:
            sticky.close();result.update(finished_at=time.time(),
                measured_jump_height_yards=peak-initial if peak is not None and initial is not None else None)
            runtime.write(folder/'ground_jump.json',result)
