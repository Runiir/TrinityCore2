"""Local minimap candidates, confirmed through normal public tooltip names."""
import json
import math
import time
from . import runtime,telemetry_tiles,laya_ui,inputs
from tools.client_compatibility.archaeology_inputs import FIND_NAMES

_cache=None


def candidates(image,geometry,origin):
    """Filled yellow tracking blips. Hollow saved GatherMate rings are separate.

    Color detection supplies hover candidates only; it never identifies an
    artifact. A filled blip overlapping a saved ring must remain a candidate.
    """
    width,height=image.size;cx,cy=width/2,height/2
    mask=set()
    for y in range(height):
        for x in range(width):
            if ((x-cx)/(cx-7))**2+((y-cy)/(cy-7))**2>1:continue
            r,g,b=image.getpixel((x,y))
            if r>=170 and g>=140 and b<150 and min(r,g)>b+55:mask.add((x,y))
    all_pixels=set(mask);groups=[]
    while mask:
        point=mask.pop();group=[point];todo=[point]
        while todo:
            x,y=todo.pop()
            for dx in (-1,0,1):
                for dy in (-1,0,1):
                    q=(x+dx,y+dy)
                    if q in mask:mask.remove(q);group.append(q);todo.append(q)
        if not 4<=len(group)<=120:continue
        xs,ys=zip(*group);left,right,top,bottom=min(xs),max(xs),min(ys),max(ys)
        if max(right-left,bottom-top)>15:continue
        x,y=(left+right)/2,(top+bottom)/2
        core=sum((a-x)**2+(b-y)**2<=2.5**2 for a,b in group)
        saved_points=[(p['x']*runtime.WIDTH-origin[0],p['y']*runtime.HEIGHT-origin[1])
            for p in geometry.get('saved_pins',[]) if math.hypot(p['x']*runtime.WIDTH-origin[0]-x,p['y']*runtime.HEIGHT-origin[1]-y)<7]
        saved=bool(saved_points)
        if saved and not any(sum((a-px)**2+(b-py)**2<=2.3**2 for a,b in all_pixels)>=8 for px,py in saved_points):continue
        groups.append({'x':round(origin[0]+x),'y':round(origin[1]+y),'pixels':len(group),
            'overlaps_saved_marker':saved,'source':'unconfirmed_filled_yellow_minimap_blip'})
    return sorted(groups,key=lambda p:(p['x']-origin[0]-cx)**2+(p['y']-origin[1]-cy)**2)[:24]


def near(a,b,tolerance=2):
    return bool(a and b and a['instance']==b['instance'] and
        math.hypot(a['north']-b['north'],a['west']-b['west'])<=tolerance)


def signal(row,force=False):
    global _cache
    geometry=(row.get('farm_ui') or {}).get('minimap') or {}
    world=row['archaeology'].get('world')
    named=(row.get('farm_ui') or {}).get('soft_interact',{}).get('name')
    if not geometry.get('visible') or not world:
        return {'status':'unavailable','confirmed':[],'clear':False}
    now=time.monotonic()
    if not force and _cache and now-_cache['at']<.2 and _cache['runtime']==row['runtime'] and _cache.get('name')==named and near(_cache['world'],world):
        return _cache['signal']
    x=round((geometry['x']-geometry['width']/2)*runtime.WIDTH)
    y=round((geometry['y']-geometry['height']/2)*runtime.HEIGHT)
    width=round(geometry['width']*runtime.WIDTH);height=round(geometry['height']*runtime.HEIGHT)
    points=candidates(telemetry_tiles.image_region(x,y,width,height),geometry,(x,y))
    result={'status':'uninspected_candidates' if points else 'no_visible_candidates',
        'observed_at':time.time(),'runtime':row['runtime'],'world':world,'candidates':points,'confirmed':[],
        'saved_marker_count':len(geometry.get('saved_pins',[])),'tracking_enabled':geometry.get('artifact_tracking'),
        'clear':not points and geometry.get('artifact_tracking') is not False,
        'coverage':'visible yellow blip candidates; persistent pickup latch remains authoritative',
        'source':'local_minimap_pixels_and_public_addon_geometry'}
    if named in FIND_NAMES:
        result.update(known_live_find_name=named,clear=False)
        if not points:result['status']='public_named_find'
    path=runtime.ROOT/'run/minimap_finds.json'
    if points and path.exists():
        old=json.loads(path.read_text())
        if (old['runtime']==row['runtime'] and near(old['world'],world) and time.time()-old['observed_at']<5
            and old.get('zoom')==geometry['zoom'] and old.get('rotating')==geometry['rotating']):
            if old.get('candidates')==points:
                result['confirmed']=old['confirmed']
                if old['confirmed']:result['status']='confirmed_finds'
                elif old.get('all_candidates_inspected'):result.update(status='no_confirmed_finds',clear=geometry.get('artifact_tracking') is not False)
    if named in FIND_NAMES:result['clear']=False
    _cache={'at':now,'runtime':row['runtime'],'world':world,'name':named,'signal':result}
    return result


def world_from_blip(row,point):
    geometry=row['farm_ui']['minimap'];world=row['archaeology']['world']
    north=(geometry['y']*runtime.HEIGHT-point['y'])/(geometry['height']*runtime.HEIGHT/2)*geometry['radius_yards']
    west=-(point['x']-geometry['x']*runtime.WIDTH)/(geometry['width']*runtime.WIDTH/2)*geometry['radius_yards']
    if geometry['rotating']:
        angle=geometry['facing'];north,west=north*math.cos(angle)-west*math.sin(angle),north*math.sin(angle)+west*math.cos(angle)
    return {'instance':world['instance'],'north':world['north']+north,'west':world['west']+west}


def inspect(folder,row):
    """Laya chooses one bounded inspection; hover never clicks or pings."""
    from .observe import observe
    from .farm_actions import stationary
    folder.mkdir(parents=True,exist_ok=False)
    scan=signal(row,force=True)
    request_state={'goal':'Check live archaeology finds before continuing the dig or leaving',
        'unconfirmed_minimap_blips':len(scan.get('candidates',[])),
        'saved_GatherMate_markers':scan.get('saved_marker_count',0)}
    action,request,response=laya_ui.choose(request_state,'Inspect unknown minimap blips using their normal tooltips.',
        {'inspect':'Inspect the visible minimap blips','wait':'Wait without input'})
    result={**scan,'choice':action,'request':request,'response':response,'probes':[],'confirmed':[],
        'all_candidates_inspected':False,'zoom':row['farm_ui']['minimap']['zoom'],
        'rotating':row['farm_ui']['minimap']['rotating']}
    runtime.write(folder/'scan.json',result)
    if action!='inspect':return result
    for point in scan.get('candidates',[]):
        fresh=observe(folder/'precheck.png');stationary(row,fresh)
        inputs.execute('World of Warcraft','hover',{'x':point['x'],'y':point['y']})
        # A normal UI generation must reflect this cursor, not a fading tooltip.
        deadline=time.monotonic()+.7
        while True:
            hovered=observe(folder/'hover.png');stationary(row,hovered)
            cursor=hovered['farm_ui'].get('cursor') or {}
            if (hovered['farm_ui']['sequence']!=fresh['farm_ui']['sequence']
                and abs(cursor.get('x',-1)*runtime.WIDTH-point['x'])<2
                and abs(cursor.get('y',-1)*runtime.HEIGHT-point['y'])<2):break
            if time.monotonic()>deadline:raise RuntimeError('minimap tooltip observation did not follow the cursor')
            time.sleep(.02)
        lines=hovered['farm_ui']['minimap'].get('tooltip_lines') or []
        names=[name for name in FIND_NAMES if name in lines]
        result['probes'].append({'point':point,'tooltip_lines':lines})
        if names:
            result['confirmed'].append({'name':names[0],'world':world_from_blip(hovered,point),
                'point':point,'source':'normal_native_minimap_tooltip','estimated_position':True})
    result.update(observed_at=time.time(),all_candidates_inspected=True)
    result['status']='confirmed_finds' if result['confirmed'] else 'no_confirmed_finds'
    result['clear']=not result['confirmed'] and scan.get('tracking_enabled') is not False
    runtime.write(runtime.ROOT/'run/minimap_finds.json',result);runtime.write(folder/'scan.json',result)
    global _cache
    _cache=None
    return result
