"""Use an ordinary interact binding or a rechecked named game tooltip."""
import time
from . import runtime, inputs, native_control, action_queue,native_approach
from .observe import observe
from .farm_actions import stationary
from tools.client_compatibility.archaeology_inputs import FIND_NAMES


def native_approach_available(row,names):
    """A named mouseover can use the client's click-to-move interaction."""
    ui=row.get('farm_ui') or {};camera=ui.get('camera_input') or {};a=row['archaeology']
    cursor=ui.get('cursor') or {}
    return (ui.get('tooltip') in names and (ui.get('combat') or {}).get('click_to_move')=='1'
        and all(isinstance(cursor.get(k),(int,float)) and 0<=cursor[k]<1 for k in ('x','y'))
        and not any(a.get(k) for k in ('flying','falling','casting','swimming'))
        and not row['movement'].get('in_combat')
        and not native_approach.recent_refusal(row,ui.get('tooltip'))
        and not camera.get('right_down') and not camera.get('mouselooking'))


def search_points(maximum,*,portal=False):
    if portal:
        # Upright portals can be above the ground-object search band. This is
        # a cursor scan, never a claim that a portal is at a fixed screen point.
        center=[(640,y) for y in range(80,741,24)]
        broad=[(x,y) for x in range(400,921,40) for y in range(100,701,40)]
        broad.sort(key=lambda p:(p[0]-640)**2+(p[1]-380)**2)
        return list(dict.fromkeys(center+broad))[:maximum]
    # Small finds near the character's feet can lie between 40-pixel rows.
    # Interleave a denser local scan with the broader ground search.
    center=[(640,y) for y in range(260,621,24)]
    fine=[(x,y) for x in range(480,781,20) for y in range(400,801,20)]
    broad=[(x,y) for x in range(380,781,40) for y in range(220,661,40)]
    fine.sort(key=lambda p:(p[0]-640)**2+(p[1]-500)**2)
    broad.sort(key=lambda p:(p[0]-640)**2+(p[1]-430)**2)
    interleaved=[point for pair in zip(fine,broad) for point in pair]
    return list(dict.fromkeys(center+interleaved))[:maximum]


def hover(sender,point,before,folder,expected=None,allow_found=False):
    fps=max(1,before['farm_ui'].get('frame_rate') or 1)
    sender.move(*point);sequence=before['farm_ui']['sequence'];deadline=time.monotonic()+max(1.5,2/fps)
    matched=None
    while True:
        if (runtime.ROOT/'run/stop_dig').exists():raise RuntimeError('supervisor stop requested')
        row=observe(folder/'hover.png');stationary(before,row)
        ui=row['farm_ui'];cursor=ui.get('cursor') or {}
        if allow_found and ui['sequence']!=sequence and ui.get('tooltip') in FIND_NAMES:
            return row
        if (ui['sequence']!=sequence and
                abs(cursor.get('x',-1)*runtime.WIDTH-point[0])<2 and
                abs(cursor.get('y',-1)*runtime.HEIGHT-point[1])<2):
            matched=row
            if expected is None or ui.get('tooltip')==expected:return row
        if time.monotonic()>=deadline:
            if matched:return matched
            raise RuntimeError('artifact tooltip observation did not follow the cursor')
        time.sleep(.02)


def mouseover(folder,before,names,*,sender=None,identity=None):
    """Press the user's Mouse Button 5 binding on a fresh named mouseover."""
    folder.mkdir(parents=True,exist_ok=False)
    ui=before['farm_ui'];name=ui.get('tooltip');cursor=ui.get('cursor') or {}
    if name not in names or not cursor:raise RuntimeError('named artifact mouseover is unavailable')
    deadline=time.monotonic()+1.5
    while True:
        if (runtime.ROOT/'run/stop_dig').exists():raise RuntimeError('supervisor stop requested')
        fresh=observe(folder/'mouseover_precheck.png');stationary(before,fresh)
        if fresh['farm_ui']['sequence']!=ui['sequence']:break
        if time.monotonic()>=deadline:raise RuntimeError('named artifact mouseover is unavailable')
        time.sleep(.02)
    now=fresh['farm_ui'];point=now.get('cursor') or {}
    if (now.get('tooltip')!=name or not point or
            abs(point['x']-cursor['x'])*runtime.WIDTH>2 or
            abs(point['y']-cursor['y'])*runtime.HEIGHT>2):
        raise RuntimeError('named artifact mouseover changed before interaction')
    if sender is None:
        receipt=inputs.execute('World of Warcraft','button',{'button':9})
    else:
        # The tooltip search already owns input.lock and this sender. Keep the
        # actual mouseover in place and reuse that ownership for the click.
        from .resources import append_action
        receipt={'started_at':time.time(),'identity':identity,'action':'button',
            'arguments':{'button':9},'input':sender.initialization,'completed':False}
        try:
            sender._send(sender.X.ButtonPress,9)
            try:time.sleep(.15)
            finally:sender._send(sender.X.ButtonRelease,9)
            receipt['completed']=True
        finally:
            receipt['finished_at']=time.time();append_action(receipt)
    result={'source':'fresh public named mouseover','name':name,'cursor':point,
        'binding':'Mouse Button 5','input':receipt}
    runtime.write(folder/'interaction.json',result);return result


def use(folder,before,names,*,maximum=100,search_seconds=2,preferred_points=(),native_right_click=False):
    folder.mkdir(parents=True,exist_ok=False)
    before=action_queue.wait_ready(folder,before,observe)
    ui=before['farm_ui'];soft=ui['soft_interact'];keys=ui['bindings']['INTERACTTARGET']
    native_right_click=native_right_click or native_approach_available(before,names)
    # Game objects have a valid public softinteract name but UnitExists is false.
    if not native_right_click and soft.get('name') in names and soft.get('enabled')=='3' and keys:
        fresh=observe(folder/'key_precheck.png');stationary(before,fresh)
        if fresh['farm_ui']['soft_interact'].get('name')!=soft['name']:
            raise RuntimeError('soft interact target changed before selected interaction')
        result={'source':'confirmed public soft interact name','name':soft['name'],
                'input':inputs.execute('World of Warcraft','key',
                    {'key':keys[0],'hold':inputs.key_hold(fresh)})}
        runtime.write(folder/'interaction.json',result);return result
    from tools.second_client import ctl
    from tools.client_compatibility import native_input_adapter
    import fcntl
    ctl._launcher_env=runtime.client_environment
    native_input_adapter.lab=runtime;native_input_adapter.control=native_control
    points=search_points(maximum,portal=any(name.startswith('Portal to ') for name in names))
    for point in reversed(preferred_points):
        if (len(point)!=2 or any(not isinstance(v,int) for v in point)
                or not 0<=point[0]<runtime.WIDTH or not 0<=point[1]<runtime.HEIGHT):
            raise ValueError('preferred tooltip probe is outside the owned viewport')
        points=([tuple(point)]+[p for p in points if p!=tuple(point)])[:maximum]
    cursor=ui.get('cursor') or {}
    if ui.get('tooltip') in names and 'x' in cursor and 'y' in cursor:
        point=(round(cursor['x']*runtime.WIDTH),round(cursor['y']*runtime.HEIGHT))
        if 0<=point[0]<runtime.WIDTH and 0<=point[1]<runtime.HEIGHT:
            points=([point]+[p for p in points if p!=point])[:maximum]
    from . import interaction_search
    search=interaction_search.resume(before,names,points)
    search_deadline=time.monotonic()+search_seconds
    with (runtime.ROOT/'run/input.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        identity=inputs.focus('World of Warcraft');sender=native_input_adapter.Input()
        probes=[];observed=before
        try:
            for index in range(search['index'],len(points)):
                x,y=points[index]
                if (runtime.ROOT/'run/stop_dig').exists():raise RuntimeError('supervisor stop requested')
                if probes and time.monotonic()>=search_deadline:
                    interaction_search.save(search,index)
                    raise RuntimeError('named interaction search yielded for fresh facts')
                row=hover(sender,(x,y),observed,folder,allow_found=True);observed=row
                name=row['farm_ui'].get('tooltip');probes.append({'x':x,'y':y,'tooltip':name,
                    'cursor':row['farm_ui']['cursor'],'sequence':row['farm_ui']['sequence']})
                if name not in names:continue
                # The actual mouseover is useful even when it differs from a
                # requested search point. Laya chooses its newly legal action
                # using the observed name and cursor, without moving away.
                from . import laya_ui
                artifact=name in FIND_NAMES
                state={'object_name':name,'object_kind':'archaeology find' if artifact else 'named route interaction',
                    'cursor':row['farm_ui']['cursor'],
                    'combat':row['movement']['in_combat'],'casting':row['archaeology']['casting']}
                if artifact:state.update(artifact_name=name,mouseover_interact_binding='Mouse Button 5')
                else:state['interaction_binding']='Right mouse button after camera release'
                options=({'mouseover_interact':'Press Mouse Button 5 on the named artifact under the cursor',
                    'recheck':'Move away and recheck the tooltip before a right click'} if artifact else
                    {'right_click':'Right-click the freshly named route object with camera mouse-look released',
                     'recheck':'Move away and recheck the tooltip before a right click'})
                if native_approach_available(row,names):
                    state['client_click_to_move']=True
                    options['right_click']='Right-click the named object; the client moves into range and interacts'
                    if native_right_click:options.pop('mouseover_interact',None)
                action,request,response=laya_ui.choose(state,
                    ('Right-click the freshly named object so the client approaches and interacts. Release the right button after clicking.'
                        if native_right_click else 'Interact with the currently named '+('archaeology find using the user mouseover binding.'
                        if artifact else 'route object using a right click after camera release.')),options)
                runtime.write(folder/'mouseover_choice.json',{'state':state,'choice':action,'request':request,'response':response})
                if action=='mouseover_interact':
                    result=mouseover(folder/'mouse5',row,names,sender=sender,identity=identity)
                    interaction_search.save(search,0,completed=True)
                    runtime.write(folder/'interaction.json',result);return result
                if action=='right_click':
                    point=row['farm_ui']['cursor']
                    actual=(round(point['x']*runtime.WIDTH),round(point['y']*runtime.HEIGHT))
                    confirmed=hover(sender,actual,row,folder,expected=name)
                    if confirmed['farm_ui'].get('tooltip')!=name:continue
                    camera=confirmed['farm_ui'].get('camera_input') or {}
                    if camera.get('right_down') or camera.get('mouselooking'):
                        raise RuntimeError('selected client action invalidated: camera mouse-look active before portal click')
                    if native_right_click and not native_approach_available(confirmed,names):
                        raise RuntimeError('selected client action invalidated: named native approach changed before click')
                    sender._send(sender.X.ButtonPress,3)
                    try:time.sleep(inputs.key_hold(confirmed,minimum=.2))
                    finally:sender._send(sender.X.ButtonRelease,3)
                    time.sleep(1/max(1,confirmed['farm_ui'].get('frame_rate') or 30))
                    result={'source':'fresh named route object right click after camera release',
                        'name':name,'point':list(actual),'identity':identity,
                        'client_uptime_at_click':confirmed['farm_ui'].get('uptime',0)}
                    if native_approach_available(confirmed,names):
                        result['native_approach']=True
                        result['source']='fresh named object right click; client owns approach and interaction'
                    interaction_search.save(search,0,completed=True)
                    runtime.write(folder/'interaction.json',result);return result
                cleared=hover(sender,(1000,750),row,folder)
                # Native tooltip fading can outlive a cursor move. Wait for
                # its disappearance before confirming the object again.
                deadline=time.monotonic()+1.5
                while cleared['farm_ui'].get('tooltip') in names and time.monotonic()<deadline:
                    time.sleep(.02);cleared=observe(folder/'cleared.png');stationary(before,cleared)
                observed=cleared
                if cleared['farm_ui'].get('tooltip') in names:continue
                confirmed=hover(sender,(x,y),cleared,folder,expected=name)
                observed=confirmed
                if confirmed['farm_ui'].get('tooltip')!=name:continue
                camera=confirmed['farm_ui'].get('camera_input') or {}
                if camera.get('right_down') or camera.get('mouselooking'):
                    raise RuntimeError('selected client action invalidated: camera mouse-look active before object click')
                if native_right_click and not native_approach_available(confirmed,names):
                    raise RuntimeError('selected client action invalidated: named native approach changed before click')
                sender._send(sender.X.ButtonPress,3)
                try:time.sleep(.2)
                finally:sender._send(sender.X.ButtonRelease,3)
                result={'source':'rechecked public game tooltip','name':name,'point':[x,y],'identity':identity}
                result['client_uptime_at_click']=confirmed['farm_ui'].get('uptime',0)
                if native_approach_available(confirmed,names):
                    result['native_approach']=True
                    result['source']='rechecked named object right click; client owns approach and interaction'
                interaction_search.save(search,0,completed=True)
                runtime.write(folder/'interaction.json',result);return result
            interaction_search.save(search,0)
            raise RuntimeError('no matching public tooltip in bounded interaction search')
        finally:
            sender.close();runtime.write(folder/'probes.json',probes)
