"""Locate a nearby, faced flight master through a fresh ordinary tooltip."""
import math
import time


def approach(inputs,observer,map_id,goal,path):
    from . import ground_navigation
    from .archaeology_inputs import screenshot
    from .travel_inputs import face
    before=observer.poll()['position'];keys=[]
    if math.dist(before[:3],goal[:3])<=4:return None
    route=ground_navigation.route(map_id,before,goal)
    points=[p[:] for p in route['points']];corridor=[before,*points]
    if sum(math.dist(a[:2],b[:2]) for a,b in zip(corridor,corridor[1:]))>16:
        raise RuntimeError('flight-master ground approach exceeds short interaction corridor')
    if abs(points[0][2]-before[2])>2 or abs(points[-1][2]-goal[2])>2:
        raise RuntimeError('flight-master approach is on a different floor')
    for _ in range(12):
        movement,extra=screenshot(path);current=observer.poll()['position']
        if not movement['in_world'] or any(movement[k] for k in ['dead','in_combat','on_taxi']):
            raise RuntimeError('flight-master approach interrupted by unavailable character')
        if any(extra[k] for k in ['mounted','flying','falling','swimming']):
            raise RuntimeError('flight-master approach must stay on dry ground')
        if math.dist(current[:3],goal[:3])<=4:
            return {'source':'public flight-master position and ground corridor','before':before,
                'after':current,'public_ground_route':route,'physical_keys':keys}
        while len(points)>1 and math.dist(current[:2],points[0][:2])<=.75:points.pop(0)
        target=points[0];keys.extend(face(inputs,observer,target))
        remaining=math.dist(current[:2],target[:2])
        if len(points)==1 and math.dist(target[:3],goal[:3])<=1.25:remaining-=3.25
        hold=min(1,max(.12,remaining/7))
        inputs.key('w',hold=hold);time.sleep(.35);keys.append({'key':'w','hold':hold})
        after=observer.poll()['position']
        if math.dist(current[:2],after[:2])<.1:
            raise RuntimeError('flight-master ground approach is blocked')
    raise RuntimeError('flight-master approach did not reach observed interaction range')


def hover_points():
    # At close interaction range, a faced NPC can be above the old search's
    # y=220 limit. Cover the central vertical strip before a wider scene scan.
    central=[(640+dx,y) for dx in [0,-16,16,-32,32,-48,48]
             for y in range(160,513,16)]
    wide=[(x,y) for x in range(384,897,32) for y in range(160,577,32)]
    wide.sort(key=lambda p:(p[0]-640)**2+(p[1]-280)**2)
    return list(dict.fromkeys([*central,*wide]))


def locate(inputs,path,expected):
    from PIL import Image
    from .archaeology_inputs import screenshot
    deadline=time.monotonic()+45
    for x,y in hover_points():
        if time.monotonic()>deadline:break
        inputs.move(x,y);time.sleep(.2)
        _,hover=screenshot(path)
        if hover['tooltip_name_checksum']!=expected:continue
        # A tooltip persisting after leaving an NPC is not a localization.
        inputs.move(400,100)
        for _ in range(6):
            time.sleep(.25);_,cleared=screenshot(path)
            if cleared['tooltip_name_checksum']==0:break
        if cleared['tooltip_name_checksum']!=0:continue
        inputs.move(x,y);time.sleep(.3)
        _,confirmed=screenshot(path)
        if confirmed['tooltip_name_checksum']!=expected:continue
        with Image.open(path) as image:image.save(path.parent/'localized_flightmaster.webp',lossless=True)
        return [x,y]
    raise RuntimeError('no fresh matching flight-master tooltip in bounded mouse search')
