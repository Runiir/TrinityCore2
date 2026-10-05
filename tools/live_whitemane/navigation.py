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
