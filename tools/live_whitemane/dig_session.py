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
from .decisions import choose
from . import guide as routes
from .smooth_move import walk
from .motion import turn_duration
from .boundaries import constrain
from . import interact
from tools.client_compatibility.archaeology_inputs import FIND_NAMES
COLORS = {206590: 'red', 206589: 'yellow', 204272: 'green'}


def healthy(row):
    m, a = row['movement'], row['archaeology']
    return (m['in_world'] and m['position_available'] and m['health_percent'] >= 90
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
            and ((pending.get('after',{}).get('farm_ui') or {}).get('error') or {}).get('message')=='Out of range.'
            and not session.get('reapproach_find')):
            session.update(reapproach_find=True,pickup_retries=1,marker_fallback=True,
                walked_since_survey=True,marker_target=None)
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
            visible_find=(a['loot_open'] or ui.get('soft_interact',{}).get('name') in FIND_NAMES or
                          ui.get('route',{}).get('kind')=='pending_loot') if auto_loot else False
            if session.get('reapproach_find'):
                from .survey_find import in_range
                visible_find=a['loot_open'] or in_range(before)
            session.setdefault('site_id',a['site_id'])
            if not args.loot_at and not visible_find and (not a['can_survey'] or a['site_id'] != session['site_id']):
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
            guide,error=routes.select(before,session,tool) if not visible_find else (None,None)
            guide=constrain(before,guide) if guide else None
            if args.loot_at:
                inputs.execute('World of Warcraft','hover',dict(zip(('x','y'),args.loot_at)))
                hovered=observe(folder/'loot_hover.png')
                from tools.client_compatibility.observation.telemetry import checksum
                names=('Troll Archaeology Find','Fossil Archaeology Find','Night Elf Archaeology Find',"Tol'vir Archaeology Find")
                if hovered['archaeology']['tooltip_checksum'] not in {checksum(n.encode()) for n in names}:
                    raise RuntimeError('hovered object is not a confirmed archaeology find')
            state=routes.model_state(before,guide,bool(args.loot_at) or visible_find)
            action,model,request,result=choose(state)
            guidance=guide['source'] if guide else 'awaiting Survey'
            step={'index':index,'started_at':time.time(),'before':before,'state':state,
                'action':action,'model':model,'request':request,'response':result,
                'telescope':tool,'guidance_source':guidance,'guide':guide,
                'direction_slot_encoding':'selected addon guide in retained telescope schema',
                'completed':False,'Laya_received_screenshot_pixels':False}
            session['steps'].append(step)
            resources.trim_session(session,'dig')
            runtime.write(path,session)
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
                if session.get('reapproach_find') and not fresh.get('owned_pose'):
                    from .navigation import seed_height
                    step['pose_refresh']=seed_height(folder/'pose_refresh',fresh)
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
                if guide['color']=='red' or (guide['source']=='GatherMate marker' and guide['distance_yards']>20):
                    arrow={'endpoint':guide['world'],'source':guide['source'],'site_id':guide['boundary_site_id']}
                    step['travel_mode']='red_flight'
                    step['arrow']=arrow
                    step['inputs']=fly(folder,before,arrow,step)
                elif guide['source'] in ('GatherMate marker','visible owned archaeology find') or guide['color']=='yellow':
                    step['travel_mode']='held_waypoint_approach'
                    step['smooth_approach']=walk(folder,guide['world'],site_id=guide['boundary_site_id'])
                    step['inputs']=[]
                else:
                    hold=.4 if action=='forward_short' else 1.25
                    step['travel_mode']='green_small_steps' if action=='forward_short' else 'yellow_approach'
                    step['inputs']=[inputs.execute('World of Warcraft','key',{'key':'Up','hold':hold})]
                session['walked_since_survey']=True
                if guide['source']=='Survey telescope' and guide['color']=='green':
                    session.pop('telescope_target',None)
            elif action=='loot':
                if auto_loot:
                    if not fresh['archaeology']['loot_open']:
                        step['interaction']=interact.use(folder/'interaction',fresh,set(FIND_NAMES))
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
            else:
                step['inputs']=[]
                time.sleep(.5)
            time.sleep(.5)
            after=observe(folder/'after.png')
            walked=distance(a['world'],after['archaeology']['world'])
            found=after['archaeology']['looted_finds']>a['looted_finds']
            step.update(after=after,walked_yards=walked,confirmed_looted_find=found,
                        finished_at=time.time(),completed=True)
            if not healthy(after): raise RuntimeError('character became unavailable after input')
            if action=='survey' and after['archaeology']['successful_surveys']<=a['successful_surveys']:
                raise RuntimeError('Mouse Button 4 did not produce a successful Survey')
            if action=='survey':
                fresh_tool=telescope(after,session)
                if not fresh_tool and not auto_loot:session['stop_reason']='survey_without_telescope_review_visible_find'
                routes.marker_survey_outcome(session,guide,fresh_tool,not fresh_tool)
            if action=='loot':
                if not found:
                    error=(after.get('farm_ui') or {}).get('error') or {}
                    if error.get('message')!='Out of range.':
                        raise RuntimeError('artifact interaction did not confirm fragment pickup')
                    retries=session.get('pickup_retries',0)+1
                    if retries>2:raise RuntimeError('artifact stayed out of range after two guided recoveries')
                    session.update(reapproach_find=True,pickup_retries=retries,marker_fallback=True,
                        walked_since_survey=True,marker_target=None)
                    session.pop('telescope_target',None)
                    step['outcome']='out_of_range_refresh_survey_guidance'
                else:
                    args.loot_at=None
                    routes.pickup(session)
                    session['observed_find_count']=after['archaeology']['looted_finds']
            if action.startswith('forward_') and (walked<.25 or walked>(750 if step.get('travel_mode') in ('red_flight','held_waypoint_approach') else 15)):
                raise RuntimeError('walking outcome was blocked or exceeded its bound')
            if action.startswith('turn_') and walked>.15:
                raise RuntimeError('turn unexpectedly moved the character')
            turned=abs((after['movement']['facing_radians']-m['facing_radians']+math.pi)%math.tau-math.pi)>.05
            progress.decision_outcome(action=action,position=(round(a['world']['north'],1),round(a['world']['west'],1)),
                                      progress=found or walked>.25 or turned)
            session['progress']=asdict(progress)
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
