"""Supervised live archaeology in bounded Laya bursts, with observed outcomes."""
import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import time
import urllib.request
from . import runtime, inputs
from .observe import observe
from .archaeology_probe import command, sha256
from .dig_policy import DigProgress
from .flight import fly
from .decisions import choose
from tools.client_compatibility import archaeology_policy as policy

ENDPOINT = 'http://127.0.0.1:8004'
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


def choose(state):
    with urllib.request.urlopen(ENDPOINT+'/health',timeout=5) as response:
        model=json.load(response)
    request={'model':model['model'],'state':state}
    req=urllib.request.Request(ENDPOINT+'/v1/systemone', data=json.dumps(request).encode(),
                               headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=10) as response:
        result=json.load(response)
    action=result['answers']['action']['choice']
    if (result['revision'] != model['revision'] or action not in policy.ACTIONS
            or any(v['truncated_fields'] for v in result['token_budget'].values())
            or action != policy.label(state)):
        raise RuntimeError('Laya identity, complete input or declared-policy check failed')
    return action, model, request, result


def run(args):
    output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=output/'session.json'
    session=json.loads(path.read_text()) if path.exists() else {
        'schema':'whitemane_live_laya_dig_session_v1','started_at':time.time(),
        'code_sha256':sha256(__file__),'steps':[],'progress':asdict(DigProgress()),
        'last_survey_at':0,'walked_since_survey':True,'finished':False}
    progress=DigProgress(**session['progress'])
    session.pop('stop_reason',None)
    if progress.last_decision: progress.last_decision=tuple(progress.last_decision)
    try:
        pending=session['steps'][-1] if session['steps'] else None
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
            index=len(session['steps'])
            folder=output/f'step_{index:04d}'
            folder.mkdir(mode=0o700)
            before=observe(folder/'before.png')
            if not healthy(before): raise RuntimeError('character unavailable for this walking trial')
            a,m=before['archaeology'],before['movement']
            session.setdefault('site_id',a['site_id'])
            if not a['can_survey'] or a['site_id'] != session['site_id']:
                session.update(finished=True,stop_reason='digsite_changed_check_final_loot')
                break
            tool=telescope(before,session)
            error=(tool['facing_radians']-m['facing_radians']+math.pi)%math.tau-math.pi if tool else None
            direction='aligned' if error is not None and abs(error)<=.18 else 'left' if error is not None and error>0 else 'right'
            state={'task':'recover an archaeology find','available':healthy(before),
                'casting':a['casting'],'artifact_visible':bool(args.loot_at),
                'instrument_current':bool(tool),'telescope':{'color':COLORS[tool['entry']],
                'heading_relative_to_player':direction} if tool else None}
            action,model,request,result=choose(state)
            marker=None
            if tool:
                for candidate in a['visible_markers']:
                    difference=abs((candidate['heading_radians']-tool['facing_radians']+math.pi)%math.tau-math.pi)
                    if difference<=math.radians(25) and candidate['distance_yards']>=3:
                        marker=candidate;break
            guidance=progress.guidance(site_id=a['site_id'],looted_finds=a['looted_finds'],
                                       visible_marker=marker and marker['marker_id'])
            step={'index':index,'started_at':time.time(),'before':before,'state':state,
                'action':action,'model':model,'request':request,'response':result,
                'telescope':tool,'guidance_source':guidance,'marker':marker,
                'completed':False,'Laya_received_screenshot_pixels':False}
            session['steps'].append(step)
            runtime.write(path,session)
            fresh=observe(folder/'precheck.png')
            if (not healthy(fresh) or fresh['runtime']!=before['runtime']
                    or fresh['movement']['sequence']==m['sequence']
                    or distance(a['world'],fresh['archaeology']['world'])>.15
                    or abs((fresh['movement']['facing_radians']-m['facing_radians']+math.pi)%math.tau-math.pi)>.03
                    or fresh['archaeology']['casting']):
                raise RuntimeError('client changed, casting started, or supervisor moved before input')
            if tool and time.time()-tool['observed_at']>10:
                raise RuntimeError('telescope expired before input')
            if action=='survey':
                session['last_survey_at']=time.time()
                session['walked_since_survey']=False
                # WoW Mouse Button 4 is X button 8 / Linux BTN_SIDE (275).
                step['inputs']=[inputs.execute('World of Warcraft','click',
                    {'x':640,'y':350,'button':8})]
                time.sleep(2)
                # A missing bearing can mean a discovered visible find. Pause for screenshot review.
                if not (runtime.ROOT/'run/telescope.json').exists():
                    session['stop_reason']='survey_without_telescope_review_visible_find'
                if marker and marker['distance_yards']<=5:
                    progress.failed_marker_survey(marker['marker_id'])
            elif action in ('turn_left','turn_right'):
                hold=max(.05,min(.30,abs(error)/2.618))
                step['inputs']=[inputs.execute('World of Warcraft','key',
                    {'key':'Left' if action=='turn_left' else 'Right','hold':hold})]
            elif action in ('forward_short','forward_long'):
                if tool['entry']==206590:
                    arrow=a.get('arrow')
                    if not arrow or abs(arrow['observed_at']-tool['observed_at'])>2:
                        raise RuntimeError('fresh public addon arrow endpoint is not available')
                    step['travel_mode']='red_flight'
                    step['arrow']=arrow
                    step['inputs']=fly(folder,before,arrow,step)
                else:
                    hold=.4 if action=='forward_short' else 1.25
                    if guidance=='gathermate_minimap_marker' and marker:
                        hold=min(hold,max(.10,marker['distance_yards']/7))
                    step['travel_mode']='green_small_steps' if action=='forward_short' else 'yellow_approach'
                    step['inputs']=[inputs.execute('World of Warcraft','key',{'key':'Up','hold':hold})]
                session['walked_since_survey']=True
            elif action=='loot':
                x,y=args.loot_at
                step['inputs']=[inputs.execute('World of Warcraft','click',{'x':x,'y':y,'button':3})]
                time.sleep(3)
                args.loot_at=None
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
            if action.startswith('forward_') and (walked<.25 or walked>(750 if step.get('travel_mode')=='red_flight' else 15)):
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
    args=parser.parse_args()
    if not 1<=args.steps<=15 or not .1<=args.walk_hold<=1.25:
        parser.error('bounded steps or walking duration exceeded')
    while True:
        result=run(args)
        print(json.dumps(result),flush=True)
        if not args.continuous or result['failure'] or result['stop_reason'] or result['finished']:
            break


if __name__=='__main__': main()
