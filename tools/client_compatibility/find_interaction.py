"""Expose an already visible artifact using bounded camera and stance changes."""
import json
import time
from . import lab_runtime as lab,loot_pose,site_boundaries


def zoom(inputs,path):
    from .archaeology_inputs import screenshot
    _,extra=screenshot(path);before=extra['camera_zoom'];keys=[]
    for _ in range(10):
        if extra['camera_zoom']<=9:break
        inputs.click(1000,360,button=4,hold=.08);time.sleep(.2)
        keys.append({'button':4,'hold':.08})
        _,after=screenshot(path)
        if after['camera_zoom']<5:
            inputs.click(1000,360,button=5,hold=.08);time.sleep(.2)
            keys.append({'button':5,'hold':.08});_,after=screenshot(path)
            extra=after;break
        if after['camera_zoom']>=extra['camera_zoom']-.1:extra=after;break
        extra=after
    return {'before':before,'after':extra['camera_zoom'],'physical_mouse_wheel':keys}


def locate(inputs,observer,find,path):
    from PIL import Image
    from .archaeology_inputs import screenshot,locate_find
    trace={'schema':'client442_find_localization_v1','started_at':time.time(),
        'source':'ordinary visible artifact, public dry corridors and tooltip hover',
        'teacher_mouse_annotations':0,'views':[],'completed':False,'failure':None}
    token=time.time_ns();trace_path=path.parent/f'find_localization_{token}.json';stances=[]
    try:
        trace['camera']=zoom(inputs,path)
        for attempt in range(3):
            _,extra=screenshot(path);position=observer.poll()['position'];stances.append(position[:3])
            frame=path.parent/f'find_view_{token}_{attempt}.webp'
            with Image.open(path) as image:image.save(frame,lossless=True)
            view={'position':position,'frame':frame.name,'sha256':lab.sha256(frame)}
            trace['views'].append(view);lab.private_write(trace_path,json.dumps(trace,indent=2)+'\n')
            try:pixel=locate_find(inputs,path,timeout=12)
            except RuntimeError as error:
                view['failure']=str(error)
                if attempt==2:raise
                site=site_boundaries.active_site(find['map'],position,extra['digsite_ids'])
                view['next_stance']=loot_pose.approach(inputs,observer,find,site,path,excluded_stances=stances)
            else:
                view['pixel']=list(pixel);trace['completed']=True
                return pixel,trace
    except BaseException as error:trace['failure']=f'{type(error).__name__}: {error}';raise
    finally:
        trace['finished_at']=time.time();lab.private_write(trace_path,json.dumps(trace,indent=2)+'\n')
