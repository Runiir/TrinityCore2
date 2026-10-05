"""Laya selects waypoint orientation; timing follows measured owned turns."""
import math
import time
from . import laya_ui, runtime, inputs
from .observe import observe
from .farm_actions import stationary
from .motion import turn_duration


def orient(folder,row,target,history=()):
    folder.mkdir(parents=True,exist_ok=False)
    world=row['archaeology']['world']
    if world['instance']!=target['instance']:raise RuntimeError('waypoint is on another world instance')
    error=(math.atan2(target['west']-world['west'],target['north']-world['north'])-row['movement']['facing_radians']+math.pi)%math.tau-math.pi
    direction='aligned' if abs(error)<=.18 else 'left' if error>0 else 'right'
    action,request,response=laya_ui.choose({'waypoint_direction':direction,'heading_error_degrees':round(error*180/math.pi,1),'player':'stationary and healthy'},
        'Face the waypoint using its measured direction.',
        {'left':'Turn left to face a waypoint on the left','right':'Turn right to face a waypoint on the right',
         'aligned':'Continue when already aligned','wait':'Wait without input'})
    result={'before':row,'action':action,'request':request,'response':response,'completed':False}
    runtime.write(folder/'turn.json',result)
    if action!=direction:raise RuntimeError('Laya orientation disagrees with public heading')
    if action!='aligned':
        stationary(row,observe(folder/'precheck.png'))
        duration,result['calibration']=turn_duration(error,list(history))
        result['input']=inputs.execute('World of Warcraft','key',{'key':'Left' if action=='left' else 'Right','hold':duration})
        time.sleep(.5)
    result.update(completed=True,after=observe(folder/'after.png'));runtime.write(folder/'turn.json',result)
    return result


def seed_height(folder,row):
    """Laya can refresh a stationary owned pose with a measured reversible turn."""
    folder.mkdir(parents=True,exist_ok=False)
    action,request,response=laya_ui.choose({'player':'stationary, healthy, all movement inputs released',
        'height_measurement':'expired','needed':'fresh height before calculating flight'},
        'Choose whether to refresh the expired height measurement before flight.',
        {'refresh':'Turn slightly and return to obtain a fresh owned movement measurement','wait':'Wait without input'})
    result={'action':action,'request':request,'response':response,'before':row,'inputs':[]}
    runtime.write(folder/'height_refresh.json',result)
    if action=='refresh':
        stationary(row,observe(folder/'precheck.png'))
        duration,result['calibration']=turn_duration(.15,[])
        for key in ('Left','Right'):
            result['inputs'].append(inputs.execute('World of Warcraft','key',{'key':key,'hold':duration}))
        for i in range(8):
            time.sleep(.15);after=observe(folder/'after.png')
            if after.get('owned_pose'):result['after']=after;break
    runtime.write(folder/'height_refresh.json',result)
    if 'after' not in result:raise RuntimeError('Laya height refresh did not obtain a fresh pose')
    return result
