"""Survey, collect, finish sites and travel to replacements without GM actions.

The live watchdogs stop on semantic stalls. A site budget is an experiment
boundary, never evidence of an indefinitely reliable policy.
"""
import argparse
import json
from pathlib import Path
from types import SimpleNamespace
import time
import math
from . import lab_runtime as lab,archaeology_inputs,archaeology_trial,travel_trial,travel_routes,site_boundaries,ground_navigation
from .observation.transport import Observer


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--maximum-sites',type=int,default=0,help='0 continues until interrupted or a semantic stall')
    p.add_argument('--first-site',type=int);p.add_argument('--initial-route',type=Path)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    receipt={'schema':'client442_archaeology_loop_v1','started_at':time.time(),'steps':[],
        'finds':[],'sites_completed':[],'manual_gameplay_interventions':0,'teacher_mouse_annotations':0,
        'supported_world_maps':[0,530],'mounted_red_yellow_moves':True}
    latest=out/'latest.png';failure=None;count=0
    initial=json.loads(a.initial_route.read_text())['legs'] if a.initial_route else []
    try:
        while not a.maximum_sites or count<a.maximum_sites:
            movement,extra=archaeology_inputs.screenshot(latest);facts=Observer().poll()
            active=[site_boundaries.sites()[sid] for sid in extra['digsite_ids'] if
                    sid in site_boundaries.sites() and site_boundaries.sites()[sid]['map'] in [0,530]]
            if not active:raise RuntimeError('no assigned digsite in the supported travel maps')
            planned_initial=bool(initial)
            if initial:
                stop=next(i for i,leg in enumerate(initial) if leg.get('site_id'))
                legs,initial=initial[:stop+1],initial[stop+1:]
                site=next(s for s in active if s['id']==legs[-1]['site_id'])
                plan={'schema':'client442_public_site_route_v1','site':site['id'],'legs':legs}
            else:
                site=next((s for s in active if count==0 and s['id']==a.first_site),None)
                if not site:site=min(active,key=lambda s:(s['map']!=facts['map'],math.dist(s['center'],facts['position'][:2])))
                plan=travel_routes.to_site(facts['map'],facts['position'],site)
            already_there=not planned_initial and site['map']==facts['map'] and site_boundaries.contains(site['polygon'],facts['position']) and not any(extra[k] for k in ['mounted','flying','falling'])
            if already_there:
                try:floor=ground_navigation.ground_point(facts['map'],facts['position'],maximum_height=facts['position'][2]+1)
                except RuntimeError:already_there=False
                else:already_there=abs(floor[2]-facts['position'][2])<=2
            if already_there:
                receipt['steps'].append({'kind':'already_at_site','site':site['id'],'facts':facts,
                    'travel':extra,'source':'observed grounded player inside assigned public polygon'})
            else:
                travel_name=f'travel_{count:03d}_site_{site["id"]}'
                plan=travel_routes.prepare_clearance(plan,facts['map'],facts['position'])
                result=travel_trial.run(plan,out/travel_name)
                receipt['steps'].append({'kind':'travel','episode':travel_name,'site':site['id'],'completed':result['completed']})
                if not result['completed']:raise RuntimeError(result['failure'])
            for dig in range(4):
                _,extra=archaeology_inputs.screenshot(latest)
                if site['id'] not in extra['digsite_ids']:break
                name=f'dig_{count:03d}_{dig:02d}_site_{site["id"]}'
                result=archaeology_trial.run(SimpleNamespace(output=out/name,finds=1,maximum_steps=120,
                    final_find_site=None,mounted_moves=True))
                receipt['steps'].append({'kind':'dig','episode':name,'site':site['id'],'completed':result['completed']})
                receipt['finds'].extend(result['finds'])
                lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
                if not result['completed']:raise RuntimeError(result['failure'])
            _,extra=archaeology_inputs.screenshot(latest)
            if site['id'] in extra['digsite_ids']:raise RuntimeError('digsite did not finish within four collected finds')
            receipt['sites_completed'].append({'site':site['id'],'time':time.time(),'replacement_sites':extra['digsite_ids']})
            count+=1;lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
    except (Exception,KeyboardInterrupt) as e:failure=f'{type(e).__name__}: {e}'
    receipt.update(finished_at=time.time(),completed=bool(a.maximum_sites and count>=a.maximum_sites),failure=failure)
    lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'sites_completed':count,'finds':len(receipt['finds']),'completed':receipt['completed'],'failure':failure}),flush=True)


if __name__=='__main__':main()
