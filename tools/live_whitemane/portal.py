"""A retained Laya travel decision approaches and uses the addon's named portal."""
import math
import time
from . import runtime, inputs, interact
from .observe import observe
from .decisions import choose
from .fast_waypoint import walk
from .farm_actions import stationary
from tools.client_compatibility import travel_policy


def run(folder,portal):
    folder.mkdir(parents=True,exist_ok=False)
    before=observe(folder/'before.png');m,a=before['movement'],before['archaeology']
    world=a['world'];target=portal['from'];remaining=math.hypot(target['north']-world['north'],target['west']-world['west'])
    if world['instance']!=target['instance'] or remaining>30:
        raise RuntimeError('portal use requires arrival near the public entrance')
    flags={'mode':'portal','available':m['in_world'] and m['health_percent']>0 and not (m['dead'] or m['in_combat']),
           'casting':a['casting'],'on_taxi':m['on_taxi'],'mounted':a['mounted'],'flying':a['flying'],
           'falling':a['falling'],'at_route_height':False,'near_destination':True,
           'destination_reached':False,'taxi_map_open':False}
    action,model,request,response=choose(travel_policy.model_state(flags),'travel',physical_state=flags)
    result={'before':before,'portal':portal,'action':action,'model':model,'request':request,'response':response,'completed':False}
    runtime.write(folder/'portal.json',result)
    if action!='portal':raise RuntimeError('portal approach needs Laya portal action')
    fresh=observe(folder/'precheck.png');stationary(before,fresh)
    result['approach']=walk(folder/'approach',target,tolerance=2,
        guidance={'source':'public portal route'},approved_intent=(action,model,request,response))
    row=observe(folder/'approached.png')
    result['interaction']=interact.use(folder/'interaction',row,{'Portal to '+portal['destination']})
    for index in range(25):
        time.sleep(.4)
        try:after=observe(folder/'arrival.png')
        except RuntimeError as error:
            if str(error).startswith(('live public observer is unavailable','direct public addon feed unavailable',
                    'local public tiles unavailable')):continue
            raise
        w=after['archaeology']['world'];destination=portal['to']
        if w and w['instance']==destination['instance'] and math.hypot(w['north']-destination['north'],w['west']-destination['west'])<100:
            result.update(completed=True,after=after);break
    runtime.write(folder/'portal.json',result)
    if not result['completed']:raise RuntimeError('portal interaction did not confirm destination arrival')
    return result


if __name__=='__main__':
    import argparse,json
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--key',required=True);args=parser.parse_args()
    row=observe(args.output.parent/'portal_lookup.png')
    target=next(p for p in row['farm_ui']['route']['known_portals'] if p['key']==args.key)
    print(json.dumps({'completed':run(args.output,target)['completed']}))
