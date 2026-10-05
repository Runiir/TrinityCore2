"""Supervised live archaeology in bounded Laya bursts, with observed outcomes."""
import argparse
from dataclasses import asdict
import json
import math
import subprocess
from pathlib import Path
import time
from . import runtime, inputs, resources
from .observe import observe
from .archaeology_probe import sha256
from .dig_policy import DigProgress
from .flight import fly
from .dig_decisions import choose
from . import guide as routes
from .smooth_move import walk
from .motion import turn_duration
from .boundaries import constrain
from . import interact,pending_find,minimap_finds,farm_graph,dig_context
from tools.client_compatibility.archaeology_inputs import FIND_NAMES
COLORS = {206590: 'red', 206589: 'yellow', 204272: 'green'}


def healthy(row):
    m, a = row['movement'], row['archaeology']
    return (m['in_world'] and m['position_available'] and m['health_percent'] > 0
            and not any(m[k] for k in ('dead','in_combat','on_taxi'))
            and a['world'] is not None and not a['flying'] and not a['mounted'])


def distance(a, b):
    if a['instance'] != b['instance']:
        raise RuntimeError('world instance changed')
    return math.hypot(a['north']-b['north'], a['west']-b['west'])


def telescope(row, session):
    path = runtime.ROOT / 'run/telescope.json'
    if session.get('walked_since_survey') or not path.exists():
        return None
    tool = json.loads(path.read_text())
    if (tool['runtime'] != row['runtime'] or time.time()-tool['observed_at'] > 6
            or tool['observed_at'] < session.get('last_survey_at', time.time())
            or tool['entry'] not in COLORS or distance(tool, row['archaeology']['world']) > 25):
        return None
    return tool


def run(args):
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=output/'session.json'
    session=json.loads(path.read_text()) if path.exists() else {
        'schema':'whitemane_live_laya_dig_session_v1','started_at':time.time(),
        'code_sha256':sha256(__file__),'steps':[],'progress':asdict(DigProgress()),
        'last_survey_at':0,'walked_since_survey':True,'finished':False}
    progress=DigProgress(**session['progress'])
    resources.trim_session(session,'dig')
    if not session.get('last_green_endpoint'):
        since_pickup=[]
        for s in reversed(session['steps']):
            if s.get('confirmed_looted_find'):break
            since_pickup.append(s)
        old=next((s['guide'] for s in since_pickup if s.get('guide')
            and s['guide']['source']=='Survey telescope' and s['guide']['color']=='green'),None)
        if old:session['last_green_endpoint']={'world':old['world']}
    session.setdefault('runs',[]).append({'started_at':time.time(),
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=runtime.REPO,text=True).strip(),
        'source_sha256':{str(p.relative_to(runtime.REPO)):sha256(p)
                         for p in Path(__file__).parent.glob('*.py')}})
    resources.trim_session(session,'dig')
    session.pop('stop_reason',None)
    if progress.last_decision: progress.last_decision=tuple(progress.last_decision)
    try:
        pending=session['steps'][-1] if session['steps'] else None
        if (pending and pending.get('action')=='loot' and not pending.get('confirmed_looted_find')
            and pending_find.range_error((pending.get('after',{}).get('farm_ui') or {}).get('error') or {})
            and not session.get('reapproach_find')):
            current=observe(output/'range_resume.png')
            pending_find.out_of_range(current,session)
            session.update(marker_fallback=True,marker_target=None)
            session.pop('telescope_target',None)
        if pending and pending.get('travel_mode')=='red_flight' and not pending['completed']:
            current=observe(output/'resume_precheck.png')
            if current['archaeology']['mounted'] or current['archaeology']['flying']:
                folder=output/f"step_{pending['index']:04d}"
                pending['inputs']=fly(folder,current,pending['arrow'],pending)
                pending['after']=observe(folder/'after.png')
                pending['walked_yards']=distance(pending['before']['archaeology']['world'],pending['after']['archaeology']['world'])
                pending.update(completed=True,finished_at=time.time())
                session['walked_since_survey']=True
                runtime.write(path,session)
                print('Laya resumed the observed flight to the addon endpoint',flush=True)
        for _ in range(args.steps):
            if (runtime.ROOT/'run/stop_dig').exists():
                raise RuntimeError('supervisor stop requested')
            resources.check()
            index=session['next_step_index'];session['next_step_index']=index+1
            folder=output/f'step_{index:04d}'
            folder.mkdir(mode=0o700)
            before=observe(folder/'before.png')
            if not healthy(before): raise RuntimeError('character unavailable for this walking trial')
            a,m=before['archaeology'],before['movement']
            auto_loot=getattr(args,'auto_loot',False)
            ui=before.get('farm_ui') or {}
            if ((before.get('minimap_finds') or {}).get('status')=='uninspected_candidates'
                and ui.get('soft_interact',{}).get('name') not in FIND_NAMES
                and not pending_find.load(before)):
                minimap_finds.inspect(folder/'minimap',before)
                before=observe(folder/'minimap_after.png');a,m=before['archaeology'],before['movement'];ui=before['farm_ui']
            value=pending_find.update(before,session)
            before['pending_find']=value
            pickup_priority=pending_find.priority(before,value) if value else None
            visible_find=(a['loot_open'] or ui.get('soft_interact',{}).get('name') in FIND_NAMES or
                          ui.get('route',{}).get('kind')=='pending_loot') if auto_loot else False
            if session.get('reapproach_find'):
                from .survey_find import in_range
                visible_find=(a['loot_open'] or in_range(before)
                    or ui.get('soft_interact',{}).get('name') in FIND_NAMES)
                approach=session.get('pickup_approach')
                tolerance=.1 if approach and approach.get('source')=='named find forward range approach' else .5
                if approach and distance(a['world'],approach['world'])<=tolerance:visible_find=True
            session.setdefault('site_id',a['site_id'])
            if not args.loot_at and not visible_find and not value and (not a['can_survey'] or a['site_id'] != session['site_id']):
                session.update(finished=True,stop_reason='digsite_changed_check_final_loot')
                break
            tool=telescope(before,session)
            if session.get('observed_find_count',a['looted_finds']) != a['looted_finds']:
                routes.pickup(session)
            session['observed_find_count']=a['looted_finds']
            if tool and session.get('marker_fallback') and not session.get('telescope_target'):
                for attempt in range(6):
                    arrow=before['archaeology'].get('arrow')
                    if arrow and arrow.get('boundary_verified'):break
                    time.sleep(.5)
                    before=observe(folder/f'arrow_wait_{attempt:02d}.png')
                a,m=before['archaeology'],before['movement']
            guide,error=routes.select(before,session,tool) if not visible_find or session.get('reapproach_find') else (None,None)
            guide=constrain(before,guide,site_id=value['site_id'] if value else None) if guide else None
            ui=before.get('farm_ui') or {}
            cooldown=ui.get('survey') or {}
            if (not args.loot_at and not visible_find and not value
                    and (not guide or guide['arrived']) and cooldown.get('ready') is False):
                # A local readiness wait sends neither a model request nor a
                # gameplay input. Keep character availability in its trained
                # meaning instead of turning a spell cooldown into absence.
                remaining=max(0,cooldown.get('cooldown_ends',0)-ui.get('uptime',0))
                session['survey_cooldown_wait']={'observed_at':before['observed_at'],
                    'remaining_seconds':remaining,'gameplay_inputs':0,'model_requests':0}
                runtime.write(path,session)
                time.sleep(min(.5,remaining) if remaining>0 else .2)
                continue
            if args.loot_at:
                inputs.execute('World of Warcraft','hover',dict(zip(('x','y'),args.loot_at)))
                hovered=observe(folder/'loot_hover.png')
                from tools.client_compatibility.observation.telemetry import checksum
                names=('Troll Archaeology Find','Fossil Archaeology Find','Night Elf Archaeology Find',"Tol'vir Archaeology Find")
                if hovered['archaeology']['tooltip_checksum'] not in {checksum(n.encode()) for n in names}:
                    raise RuntimeError('hovered object is not a confirmed archaeology find')
            state=dig_context.model_state(before,guide,bool(args.loot_at) or visible_find,value,session['steps'])
            if value and not visible_find and not guide:
                action,model,request,result,state=pending_find.choose_inspection(before)
            else:
                action,model,request,result=choose(state)
            guidance=guide['source'] if guide else 'awaiting Survey'
            step={'index':index,'started_at':time.time(),'before':before,'state':state,
                'action':action,'model':model,'request':request,'response':result,
                'telescope':tool,'guidance_source':guidance,'guide':guide,
                'direction_slot_encoding':'selected addon guide in retained telescope schema',
                'completed':False,'Laya_received_screenshot_pixels':False}
            if pickup_priority:step['pickup_priority']=pickup_priority
            session['steps'].append(step)
            resources.trim_session(session,'dig')
            runtime.write(path,session)
            graph=getattr(args,'graph',None)
            if action=='survey' and (ui.get('survey') or {}).get('ready') is False:
                step.update(completed=True,inputs=[],outcome='Survey_deferred_until_cooldown_ready',finished_at=time.time())
                runtime.write(path,session);time.sleep(.2);continue
            if graph and action!='observe':step['graph_transition']=farm_graph.transition(graph,action,before,pending=value)
            fresh=observe(folder/'precheck.png')
            if (not healthy(fresh) or fresh['runtime']!=before['runtime']
                    or (fresh['source']=='normal_public_addon_api_rendered_pixels' and fresh['movement']['sequence']==m['sequence'])
                    or distance(a['world'],fresh['archaeology']['world'])>.15
                    or abs((fresh['movement']['facing_radians']-m['facing_radians']+math.pi)%math.tau-math.pi)>.03
                    or fresh['archaeology']['casting']):
                raise RuntimeError('client changed, casting started, or supervisor moved before input')
            if tool and guide and guide['source']=='Survey telescope' and time.time()-tool['observed_at']>10:
                raise RuntimeError('telescope expired before input')
            if action=='survey':
                cooldown=(fresh.get('farm_ui') or {}).get('survey') or {}
                if cooldown.get('ready') is False:
                    step.update(completed=True,outcome='waiting_for_public_survey_cooldown',finished_at=time.time())
                    runtime.write(path,session);time.sleep(.2);continue
                session['last_survey_at']=time.time()
                session['walked_since_survey']=False
                session.pop('telescope_target',None)
                # WoW Mouse Button 4 is X button 8 / Linux BTN_SIDE (275).
                step['inputs']=[inputs.execute('World of Warcraft','click',
                    {'x':640,'y':350,'button':8})]
                time.sleep(2)
            elif action in ('turn_left','turn_right'):
                hold,step['turn_calibration']=turn_duration(error,session.get('turn_history',[])+session['steps'][:-1])
                step['inputs']=[inputs.execute('World of Warcraft','key',
                    {'key':'Left' if action=='turn_left' else 'Right','hold':hold})]
            elif action in ('forward_short','forward_long'):
                if not guide: raise RuntimeError('movement requires a selected addon guide')
                if guide['source']=='named find forward range approach':
                    # One distance-derived pulse, then let the public map
                    # settle. Its position cache updates more slowly than M.
                    speeds=(fresh.get('farm_ui') or {}).get('move_speeds') or {}
                    speed=speeds.get('run') or max(m['speed'],7)
                    hold=max(.05,min(1.25,guide['distance_yards']/speed))
                    step['travel_mode']='measured_pickup_range_step'
                    step['calculated_walk_seconds']=hold
                    step['inputs']=[inputs.execute('World of Warcraft','key',{'key':'Up','hold':hold})]
                    # This endpoint represents a measured probe distance. On
                    # completion, interact again even if the map overshot it.
                    session['pickup_approach']=None
                    if value:
                        value['approach']=None;value['out_of_range']=False
                        runtime.write(runtime.ROOT/'run/pending_find.json',value)
                elif guide['color']=='red' or (guide['source']=='GatherMate marker' and guide['distance_yards']>20):
                    arrow={'endpoint':guide['world'],'source':guide['source'],'site_id':guide['boundary_site_id']}
                    step['travel_mode']='red_flight'
                    step['arrow']=arrow
                    if graph:step['graph_path']=str(graph)
                    step['inputs']=fly(folder,before,arrow,step)
                elif value or guide['source'] in ('GatherMate marker','visible owned archaeology find','last green Survey endpoint') or guide['color']=='yellow':
                    step['travel_mode']='held_waypoint_approach'
                    finding=bool(value) or guide['source'] in ('visible owned archaeology find','last green Survey endpoint')
                    step['smooth_approach']=walk(folder,guide['world'],site_id=guide['boundary_site_id'],
                        approaching_find=finding,tolerance=guide.get('arrival_tolerance_yards',.5) if finding else None)
                    step['inputs']=[]
                else:
                    hold=.4 if action=='forward_short' else 1.25
                    step['travel_mode']='green_small_steps' if action=='forward_short' else 'yellow_approach'
                    step['inputs']=[inputs.execute('World of Warcraft','key',{'key':'Up','hold':hold})]
                session['walked_since_survey']=True
                if guide['source']=='Survey telescope' and guide['color']=='green':
                    session['last_green_endpoint']={'world':guide['world']}
                    session.pop('telescope_target',None)
            elif action=='loot':
                if auto_loot:
                    gathering=(fresh.get('farm_ui') or {}).get('gathering') or {}
                    if not fresh['archaeology']['loot_open']:
                        step['interaction']=interact.use(folder/'interaction',fresh,set(FIND_NAMES))
                    deadline=time.monotonic()+4
                    while time.monotonic()<deadline:
                        cast=observe(folder/'gather_cast.png')
                        now=(cast.get('farm_ui') or {}).get('gathering') or {}
                        if now.get('starts',0)>gathering.get('starts',0):
                            step['gathering_cast_started']=True;break
                        if pending_find.gained(pending_find.fragments(fresh),cast):
                            step['gathering_cast_started']=now.get('successes',0)>gathering.get('successes',0);break
                        error=(cast.get('farm_ui') or {}).get('error') or {}
                        if pending_find.range_error(error) and error.get('at',0)>=fresh['farm_ui'].get('uptime',0):break
                        time.sleep(.1)
                    # An interact can open the normal loot window while auto
                    # loot is disabled. Laya chooses each visible loot button.
                    from .farm_actions import click_choice
                    for slot in range(8):
                        loot=observe(folder/f'loot_{slot:02d}.png')
                        if not loot['archaeology']['loot_open']:break
                        if not (loot.get('farm_ui') or {}).get('loot'):
                            time.sleep(.2);continue
                        selected=click_choice(folder/f'loot_choice_{slot:02d}',loot,['loot'],
                            'Collect the archaeology fragments or items in the open loot window')
                        step.setdefault('loot_choices',[]).append(selected)
                        if not selected['executed']:break
                    step['inputs']=[]
                else:
                    x,y=args.loot_at
                    step['inputs']=[inputs.execute('World of Warcraft','click',{'x':x,'y':y,'button':3})]
                time.sleep(3)
                session['walked_since_survey']=True
            elif action=='inspect':
                step['minimap_scan']=minimap_finds.inspect(folder/'pending_minimap',fresh)
                step['inputs']=[]
            else:
                step['inputs']=[]
                time.sleep(.5)
            time.sleep(.5)
            after=observe(folder/'after.png')
            walked=distance(a['world'],after['archaeology']['world'])
            found=pending_find.gained(pending_find.fragments(before),after)
            step.update(after=after,walked_yards=walked,confirmed_looted_find=found,
                        finished_at=time.time(),completed=True)
            if not healthy(after): raise RuntimeError('character became unavailable after input')
            if action=='survey' and after['archaeology']['successful_surveys']<=a['successful_surveys']:
                raise RuntimeError('Mouse Button 4 did not produce a successful Survey')
            if action=='survey':
                fresh_tool=telescope(after,session)
                if not fresh_tool:
                    approach=after.get('visible_find') or session.get('last_green_endpoint')
                    if not approach and guide and guide['arrived']:approach={'world':guide['world'],'source':'arrival at saved GatherMate marker'}
                    value=pending_find.latch(after,site_id=session['site_id'],approach=approach)
                    pending_find.update(after,session)
                    step['pending_find']=value
                routes.marker_survey_outcome(session,guide,fresh_tool,not fresh_tool)
                named=((after.get('farm_ui') or {}).get('soft_interact') or {}).get('name') in FIND_NAMES
                if (session.get('reapproach_find') and not fresh_tool and named
                    and not after.get('visible_find') and session.get('last_green_endpoint')):
                    # Survey discovered a find instead of a telescope. Its
                    # last green endpoint is a local estimate, not a hidden
                    # artifact coordinate. Recheck range by interaction there.
                    session['pickup_approach']=dict(session['last_green_endpoint'])
            if action=='loot':
                if graph:farm_graph.transition(graph,'verify_pickup',after,pending=pending_find.load(after),outcome='fragments_increased' if found else 'pickup_unconfirmed')
                if not found:
                    error=(after.get('farm_ui') or {}).get('error') or {}
                    if not pending_find.range_error(error):
                        raise RuntimeError('artifact interaction did not confirm fragment pickup')
                    pending_find.out_of_range(after,session)
                    session.pop('telescope_target',None)
                    step['outcome']='out_of_range_approach_same_pending_find'
                else:
                    args.loot_at=None
                    routes.pickup(session)
                    pending_find.clear();session.pop('pending_find',None)
                    session['observed_find_count']=after['archaeology']['looted_finds']
            if action.startswith('forward_') and (walked<.25 or walked>(750 if step.get('travel_mode') in ('red_flight','held_waypoint_approach') else 15)):
                raise RuntimeError('walking outcome was blocked or exceeded its bound')
            if action.startswith('turn_') and walked>.15:
                raise RuntimeError('turn unexpectedly moved the character')
            turned=abs((after['movement']['facing_radians']-m['facing_radians']+math.pi)%math.tau-math.pi)>.05
            progress.decision_outcome(action=action,position=(round(a['world']['north'],1),round(a['world']['west'],1)),
                                      progress=found or walked>.25 or turned)
            session['progress']=asdict(progress)
            if graph:farm_graph.transition(graph,'observe',after,pending=pending_find.load(after))
            runtime.write(path,session)
            print(json.dumps({'step':index,'action':action,'walked_yards':round(walked,2),
                              'looted_find':found,'guidance':guidance}),flush=True)
            if session.get('stop_reason')=='survey_without_telescope_review_visible_find': break
        session['failure']=None
    except Exception as error:
        session['failure']=f'{type(error).__name__}: {error}'
        session['stop_reason']='guard_stopped_input'
    session.update(updated_at=time.time(),progress=asdict(progress))
    runtime.write(path,session)
    return {k:session.get(k) for k in ('finished','stop_reason','failure','site_id')}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--steps',type=int,default=8)
    parser.add_argument('--walk-hold',type=float,default=.35)
    parser.add_argument('--loot-at',type=int,nargs=2)
    parser.add_argument('--continuous',action='store_true')
    parser.add_argument('--auto-loot',action='store_true')
    args=parser.parse_args()
    if not 1<=args.steps<=15 or not .1<=args.walk_hold<=1.25:
        parser.error('bounded steps or walking duration exceeded')
    while True:
        result=run(args)
        print(json.dumps(result),flush=True)
        if not args.continuous or result['failure'] or result['stop_reason'] or result['finished']:
            break


if __name__=='__main__': main()
