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
from .boundaries import constrain
from . import interact,pending_find,minimap_finds,farm_graph,dig_context,dig_feedback,pickup_intent
from tools.client_compatibility.archaeology_inputs import FIND_NAMES
# Upgrade the catalog once when an older running controller loads this module
# at an action boundary. Its SourceUpdates instance resolves the new globals.
from . import controller_updates
if 'swim_vertical' not in controller_updates.COMPONENTS:
    import importlib
    from . import world_facts
    importlib.reload(controller_updates)
    importlib.reload(world_facts)
    importlib.reload(farm_graph)
COLORS = {206590: 'red', 206589: 'yellow', 204272: 'green'}


def write_decision(folder, step, session):
    keys=('index','started_at','action','state','model','request','response','guide',
          'completed','finished_at','outcome','failure','walked_yards','confirmed_looted_find','gathering_cast_started')
    receipt={key:step[key] for key in keys if key in step}
    receipt['code_commit']=session['runs'][-1]['code_commit']
    runtime.write(folder/'decision.json',receipt)


def healthy(row):
    m, a = row['movement'], row['archaeology']
    return (m['in_world'] and m['position_available'] and m['health_percent'] > 0
            and not any(m[k] for k in ('dead','in_combat','on_taxi'))
            and a['world'] is not None and not a['flying'] and not a.get('falling'))


def distance(a, b):
    if a['instance'] != b['instance']:
        raise RuntimeError('world instance changed')
    return math.hypot(a['north']-b['north'], a['west']-b['west'])


def telescope(row, session):
    path = runtime.ROOT / 'run/telescope.json'
    if session.get('walked_since_survey'):
        return None
    arrow=row['archaeology'].get('arrow') or {}
    public=(row.get('farm_ui') or {}).get('survey_guidance') or {}
    at=public.get('at',0)
    if (arrow.get('boundary_verified') and public.get('color') in COLORS.values()
            and public.get('site_id')==row['archaeology']['site_id']
            and arrow.get('observed_at')==at and 0<=time.time()-at<=20
            and at>=session.get('last_survey_at',time.time())
            and distance(arrow['origin'],row['archaeology']['world'])<=25):
        return {**arrow['origin'],'runtime':row['runtime'],'observed_at':at,
            'facing_radians':arrow['heading_radians'],
            'entry':next(entry for entry,color in COLORS.items() if color==public['color']),
            'source':'fresh_public_addon_survey_bearing'}
    if not path.exists():return None
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
    previous_pickup=next((s.get('after') for s in reversed(session['steps'])
        if s.get('confirmed_looted_find') and s.get('after')),None)
    if previous_pickup:pending_find.confirm_pickup(previous_pickup)
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
    step=None
    try:
        pending=session['steps'][-1] if session['steps'] else None
        if (pending and pending.get('action') in ('loot','mouseover_interact') and not pending.get('confirmed_looted_find')
            and pending_find.range_error((pending.get('after',{}).get('farm_ui') or {}).get('error') or {})
            and not session.get('reapproach_find')):
            current=observe(output/'range_resume.png')
            pending_find.out_of_range(current,session)
            session.update(marker_fallback=True,marker_target=None)
            session.pop('telescope_target',None)
        if pending and pending.get('travel_mode')=='red_flight' and not pending['completed']:
            current=observe(output/'resume_precheck.png')
            a=current['archaeology']
            grounded_here=(a['can_survey'] and a['site_id']==session.get('site_id')
                and not a['mounted'] and not a['flying'] and not a['falling']
                and not pending_find.load(current))
            if grounded_here:
                pending.update(completed=True,finished_at=time.time(),after=current,
                    outcome='grounded_digsite_discard_interrupted_flight_estimate')
                routes.reobserve(session)
                runtime.write(path,session)
            if current['archaeology']['mounted'] or current['archaeology']['flying']:
                folder=output/f"step_{pending['index']:04d}"
                pending['arrow']['resume_to_survey_on_ground']=True
                pending['inputs']=fly(folder,current,pending['arrow'],pending)
                pending['after']=observe(folder/'after.png')
                pending['walked_yards']=distance(pending['before']['archaeology']['world'],pending['after']['archaeology']['world'])
                pending.update(completed=True,finished_at=time.time())
                session['walked_since_survey']=True
                if pending.get('grounded_digsite_reobserve'):
                    routes.reobserve(session)
                runtime.write(path,session)
                print('Laya resumed the observed flight to the addon endpoint',flush=True)
        for _ in range(args.steps):
            step=None
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
            value=pending_find.update(before,session)
            before['pending_find']=value
            visible_find=(a['loot_open'] or pending_find.named_uncollected(before) or
                          ui.get('route',{}).get('kind')=='pending_loot') if auto_loot else False
            if session.get('reapproach_find'):
                from .survey_find import in_range
                visible_find=(a['loot_open'] or in_range(before)
                    or ui.get('soft_interact',{}).get('name') in FIND_NAMES or ui.get('tooltip') in FIND_NAMES)
                approach=session.get('pickup_approach')
                tolerance=.1 if approach and approach.get('source')=='named find forward range approach' else .5
            session.setdefault('site_id',a['site_id'])
            if not args.loot_at and not visible_find and not value and (not a['can_survey'] or a['site_id'] != session['site_id']):
                session.update(finished=True,stop_reason='digsite_changed_check_final_loot')
                break
            tool=telescope(before,session)
            if session.get('observed_find_count',a['looted_finds']) < a['looted_finds']:
                routes.pickup(session,before)
            session['observed_find_count']=a['looted_finds']
            if tool and not visible_find and not routes.fresh_guidance(before,tool):
                for attempt in range(60):
                    if routes.fresh_guidance(before,tool):break
                    time.sleep(.05)
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
            retained=pickup_intent.retained(session,before,value)
            action,model,request,result=retained or choose(state)
            pickup_intent.offer(session,before,value,action,model,request,result)
            guidance=guide['source'] if guide else 'awaiting Survey'
            step={'index':index,'started_at':time.time(),'before':before,'state':state,
                'action':action,'model':model,'request':request,'response':result,
                'telescope':tool,'guidance_source':guidance,'guide':guide,
                'direction_slot_encoding':'selected addon guide in retained telescope schema',
                'completed':False,'Laya_received_screenshot_pixels':False}
            session['steps'].append(step)
            resources.trim_session(session,'dig')
            runtime.write(path,session)
            write_decision(folder,step,session)
            graph=getattr(args,'graph',None)
            if action=='survey' and (ui.get('survey') or {}).get('ready') is False:
                step.update(completed=True,inputs=[],outcome='Survey_deferred_until_cooldown_ready',finished_at=time.time())
                runtime.write(path,session);time.sleep(.2);continue
            if graph and action!='observe':step['graph_transition']=farm_graph.transition(graph,action,before,pending=value)
            fresh=observe(folder/'precheck.png')
            if (not healthy(fresh) or fresh['runtime']!=before['runtime']
                    or distance(a['world'],fresh['archaeology']['world'])>.15
                    or abs((fresh['movement']['facing_radians']-m['facing_radians']+math.pi)%math.tau-math.pi)>.03
                    or fresh['archaeology']['casting']):
                raise RuntimeError('client changed, casting started, or supervisor moved before input')
            tool_lifetime=20 if tool and tool.get('source')=='fresh_public_addon_survey_bearing' else 10
            if tool and guide and guide['source']=='Survey telescope' and time.time()-tool['observed_at']>tool_lifetime:
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
                step['command_queue']=dig_feedback.survey(folder/'survey_command',fresh,
                    lambda row:inputs.execute('World of Warcraft','button',{'button':8,
                        'x':runtime.WIDTH//2,'y':int(runtime.HEIGHT*.3),
                        'frame_period_seconds':1/max(1,(row.get('farm_ui') or {}).get('frame_rate') or 1)}),
                    observe,lambda row:telescope(row,session))
                step['inputs']=step['command_queue']['inputs']
            elif action in ('turn_left','turn_right'):
                from .camera_navigation import align
                step['camera_alignment']=align(folder/'camera',before,guide['world'])
                step['inputs']=[]
            elif action in ('camera_forward','camera_ground'):
                from .camera_navigation import align
                step['camera_alignment']=align(folder/'camera',before,ground_view=action=='camera_ground')
                step['inputs']=[]
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
                    from .camera_navigation import align
                    step['camera_alignment']=align(folder/'camera',fresh,guide['world'])
                    step['inputs']=[inputs.execute('World of Warcraft','key',{'key':'Up','hold':hold})]
                    # This endpoint represents a measured probe distance. On
                    # completion, interact again even if the map overshot it.
                    session['pickup_approach']=None
                    if value:
                        value['approach']=None;value['out_of_range']=False
                        runtime.write(runtime.ROOT/'run/pending_find.json',value)
                elif not a.get('swimming') and (guide['color']=='red' or (guide['distance_yards']>20 and
                        (guide['color']=='yellow' or guide['source']=='GatherMate marker'))):
                    arrow={'endpoint':guide['world'],'source':guide['source'],'site_id':guide['boundary_site_id']}
                    step['travel_mode']='red_flight'
                    step['arrow']=arrow
                    if graph:step['graph_path']=str(graph)
                    step['inputs']=fly(folder,before,arrow,step)
                    if step.get('grounded_digsite_reobserve'):
                        routes.reobserve(session)
                elif value or guide['source'] in ('GatherMate marker','visible owned archaeology find','last green Survey endpoint') or guide['color']=='yellow':
                    step['travel_mode']='held_waypoint_approach'
                    finding=bool(value) or guide['source'] in ('visible owned archaeology find','last green Survey endpoint')
                    step['smooth_approach']=walk(folder,guide['world'],site_id=guide['boundary_site_id'],
                        approaching_find=finding,tolerance=guide.get('arrival_tolerance_yards',.5) if finding else guide.get('arrival_tolerance_yards'),
                        guidance=guide,approved_intent=(action,model,request,result))
                    step['inputs']=[]
                else:
                    step['travel_mode']='green_telescope_approach'
                    step['smooth_approach']=walk(folder,guide['world'],site_id=guide['boundary_site_id'],
                        tolerance=guide.get('arrival_tolerance_yards',.5),guidance=guide,
                        approved_intent=(action,model,request,result))
                    step['inputs']=[]
                session['walked_since_survey']=True
                if guide['source']=='Survey telescope' and guide['color']=='green':
                    session['last_green_endpoint']={'world':guide['world']}
                    session.pop('telescope_target',None)
            elif action in ('swim_up','swim_down'):
                from .swim_vertical import move
                step['water_depth_adjustment']=move(folder,action,guide,before)
                step['outcome']=step['water_depth_adjustment']['outcome']
                step['inputs']=[]
                session['walked_since_survey']=True
            elif action in ('loot','mouseover_interact'):
                if auto_loot:
                    if not fresh['archaeology']['loot_open']:
                        step['interaction']=(interact.mouseover if action=='mouseover_interact' else interact.use)(
                            folder/'interaction',fresh,set(FIND_NAMES))
                    step['pickup_feedback']=dig_feedback.pickup(folder,fresh,observe)
                    step['gathering_cast_started']=step['pickup_feedback']['cast_observed']
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
                    if step['pickup_feedback']['outcome']=='loot_open':
                        step['pickup_feedback']=dig_feedback.pickup(folder,fresh,observe)
                    step['inputs']=[]
                else:
                    x,y=args.loot_at
                    step['inputs']=[inputs.execute('World of Warcraft','click',{'x':x,'y':y,'button':3})]
                    step['pickup_feedback']=dig_feedback.pickup(folder,fresh,observe)
                session['walked_since_survey']=True
            elif action=='inspect':
                step['minimap_scan']=minimap_finds.inspect(folder/'pending_minimap',fresh)
                step['inputs']=[]
            else:
                step['inputs']=[]
                time.sleep(.5)
            after=observe(folder/'after.png')
            walked=distance(a['world'],after['archaeology']['world'])
            found=pending_find.gained(pending_find.fragments(before),after)
            step.update(after=after,walked_yards=walked,confirmed_looted_find=found,
                        finished_at=time.time(),completed=True)
            old_height=(before.get('owned_pose') or {}).get('height_yards')
            new_height=(after.get('owned_pose') or {}).get('height_yards')
            step['vertical_yards']=abs(new_height-old_height) if old_height is not None and new_height is not None else 0
            if not healthy(after): raise RuntimeError('character became unavailable after input')
            if action=='survey' and after['archaeology']['successful_surveys']<=a['successful_surveys']:
                raise RuntimeError('Mouse Button 4 did not produce a successful Survey')
            if action=='survey':
                fresh_tool=telescope(after,session)
                if fresh_tool and COLORS[fresh_tool['entry']]!='green':session.pop('last_green_endpoint',None)
                if fresh_tool and value and not pending_find.facts(after,value)['discovery_confirmed']:
                    # Absence of a decoded telescope was only a provisional
                    # discovery. A fresh telescope at the same search position
                    # corrects that inference; it never counts as a pickup.
                    step['outcome']='fresh_telescope_replaced_unconfirmed_discovery'
                    pending_find.clear();value=None
                    for key in ('pending_find','reapproach_find','pickup_approach','last_green_endpoint'):
                        session.pop(key,None)
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
            if action in ('loot','mouseover_interact'):
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
                    routes.pickup(session,after)
                    pending_find.confirm_pickup(after,name=(value or {}).get('name'))
                    pending_find.clear();session.pop('pending_find',None)
                    session.pop('accepted_pickup_intent',None)
                    session['observed_find_count']=after['archaeology']['looted_finds']
            if action.startswith('forward_'):
                if walked<.25 and guide['arrived']:
                    step['outcome']='waypoint_already_arrived_no_movement'
                elif walked<.25 or walked>(750 if step.get('travel_mode') in
                        ('red_flight','held_waypoint_approach','green_telescope_approach') else 15):
                    raise RuntimeError('walking outcome was blocked or exceeded its bound')
            if action.startswith('turn_') and walked>.15:
                raise RuntimeError('turn unexpectedly moved the character')
            turned=abs((after['movement']['facing_radians']-m['facing_radians']+math.pi)%math.tau-math.pi)>.05
            progress.decision_outcome(action=action,position=(round(a['world']['north'],1),round(a['world']['west'],1)),
                                      progress=found or walked>.25 or step['vertical_yards']>.25 or turned)
            session['progress']=asdict(progress)
            if graph:farm_graph.transition(graph,'observe',after,pending=pending_find.load(after))
            runtime.write(path,session)
            write_decision(folder,step,session)
            print(json.dumps({'step':index,'action':action,'walked_yards':round(walked,2),
                              'looted_find':found,'guidance':guidance}),flush=True)
            if session.get('stop_reason')=='survey_without_telescope_review_visible_find': break
        session['failure']=None
    except Exception as error:
        if 'no matching public tooltip' in str(error):
            pending_find.search_missed(observe(output/'search_missed.png'))
        session['failure']=f'{type(error).__name__}: {error}'
        session['stop_reason']='guard_stopped_input'
        if step is not None:
            step['failure']=session['failure']
            write_decision(folder,step,session)
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
