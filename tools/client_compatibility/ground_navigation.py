"""Local walkable detours from static MMAP data and public survey headings."""
import json
import math
import subprocess
from . import lab_runtime as lab


def binary():
    source=lab.REPO/'tools/client_compatibility/navmesh_probe.cpp'
    target=lab.ROOT/'bin/navmesh_probe'
    if not target.exists() or target.stat().st_mtime<source.stat().st_mtime:
        subprocess.run(['c++','-std=c++20','-O2','-I'+str(lab.REPO/'dep/recastnavigation/Detour/Include'),
            str(source),str(lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a'),'-o',str(target)],check=True)
    return target


def route(map_id,start,goal):
    command=[str(binary()),str(lab.BASE/'data/mmaps'),str(map_id),*map(str,start[:3]),*map(str,goal[:3])]
    result=subprocess.run(command,capture_output=True,text=True,timeout=10)
    if result.returncode:raise RuntimeError('ground routing: '+result.stderr.strip())
    return json.loads(result.stdout)


def survey_detour(tcp,distance):
    start=tcp['player']['position'];heading=tcp['tool']['heading_radians']
    goal=[start[0]+math.cos(heading)*distance,start[1]+math.sin(heading)*distance,start[2]]
    # The waypoint is inferred from the ordinary telescope, never a hidden find.
    result=route(tcp['tool'].get('map',0),start,goal)
    result.update(start=start[:3],requested_goal=goal,goal_source='public_survey_heading_and_color')
    return result


def walk(inputs,tcp,distance):
    import time
    from .observation.archaeology import Observer,angle_error
    planned=survey_detour(tcp,distance);observer=Observer();executed=[]
    # Walk a bounded section of the ground corridor, then survey again. The
    # mesh defines walkable slopes and holes around static solid obstacles.
    target=next((p for p in planned['points'][1:] if math.dist(p[:2],planned['start'][:2])>1.5),None)
    if not target:
        planned=survey_detour(tcp,max(10,distance*2))
        target=next((p for p in planned['points'][1:] if math.dist(p[:2],planned['start'][:2])>1.5),None)
    if not target:raise RuntimeError('navigation mesh provides no useful ground displacement')
    for _ in range(3):
        current=observer.poll(0)['player']['position']
        heading=math.atan2(target[1]-current[1],target[0]-current[0])
        error=angle_error(heading,current[3])
        if abs(error)<=.12:break
        hold=min(.55,max(.025,abs(error)/math.pi))
        inputs.key('a' if error>0 else 'd',hold=hold);time.sleep(.25)
        executed.append({'key':'a' if error>0 else 'd','hold':hold})
    else:raise RuntimeError('could not face the walkable ground waypoint')
    hold=min(distance/7,math.dist(current[:2],target[:2])/7,2.)
    if hold<.1:raise RuntimeError('ground waypoint is too close for a useful walk')
    inputs.key('w',hold=hold);time.sleep(.3)
    executed.append({'key':'w','hold':hold})
    planned.update(physical_inputs=executed,after=observer.poll(0)['player']['position'],
                   steering_source='public_static_ground_navigation_mesh')
    return hold,planned
