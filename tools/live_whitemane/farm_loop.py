"""Supervised repeating archaeology with Laya-owned inputs and public outcomes."""
import argparse
import fcntl
import json
import math
from pathlib import Path
from types import SimpleNamespace
import time
from . import runtime, dig_session, portal, taxi, solve_batch
from .observe import observe
from .farm_actions import click_choice, command_choice
from .navigation import orient
from .flight import fly
from .dig_policy import SolveBatches


def distance(world,target):
    return math.inf if not world or world['instance']!=target['instance'] else math.hypot(world['north']-target['north'],world['west']-target['west'])


def phase(row,batches,via_tolbarad=False):
    m,a,ui=row['movement'],row['archaeology'],row.get('farm_ui')
    if not ui or not m['in_world'] or m['dead'] or m['in_combat'] or m['health_percent']<90 or a['casting'] or m['on_taxi']:
        return 'wait',None
    if a['recipe_items_in_bags']>0 or ui['recipe_known']:return 'recipe',None
    if a['canopic_jars_in_bags']>0:return 'jar',None
    route=ui.get('route') or {}
    if route.get('kind')=='pending_loot':return 'dig',None
    if not a['mounted'] and not a['flying'] and any(batches.next_project(r) for r in a['races']):return 'solve',None
    if a['can_survey']:return 'dig',None
    if ui.get('taxi') and route.get('exit'):
        current=route.get('current_taxi')
        node=next((n for n in ui['taxi'] if n['id']==current),None)
        if node:return 'taxi',({'id':current,'name':node['label'],'point':a['world']},route['exit'])
    if m['map_id']==245:
        return 'portal',next(p for p in route['known_portals'] if p['key']=='tb-org')
    if via_tolbarad or route.get('kind')=='shortcut':return 'teleport',None
    if route.get('portal'):
        p=route['portal'];return ('portal',p) if distance(a['world'],p['from'])<20 else ('flight',p['from'])
    if route.get('origin') and route.get('exit'):
        target=route['origin']['point']
        return ('taxi',(route['origin'],route['exit'])) if distance(a['world'],target)<12 else ('flight',target)
    if route.get('site'):return 'flight',route['site']['point']
    return 'wait',None


def teleport(folder,row):
    opened=click_choice(folder/'open',row,['actionbars'],'Open Teleport',{'label':'Teleport'})
    if not opened['executed']:raise RuntimeError('Laya waited before opening Teleport')
    row=opened['after']
    for i in range(10):
        if row['farm_ui']['flyout']:break
        time.sleep(.3);row=observe(folder/'flyout.png')
    chosen=click_choice(folder/'destination',row,['flyout'],'Teleport to Tol Barad',{'label':'Tol Barad'})
    if not chosen['executed']:raise RuntimeError('Laya waited before Tol Barad teleport')
    for i in range(40):
        time.sleep(.3)
        try:row=observe(folder/'arrival.png')
        except RuntimeError as error:
            if str(error).startswith(('live public observer is unavailable','direct public addon feed unavailable')):continue
            raise
        if row['movement']['map_id']==245 and not row['archaeology']['casting']:
            return {'opened':opened,'chosen':chosen,'after':row,'completed':True}
    raise RuntimeError('Tol Barad teleport did not confirm destination')


def run(output):
    output.mkdir(parents=True,exist_ok=True)
    path=output/'loop.json'
    session=json.loads(path.read_text()) if path.exists() else {
        'schema':'whitemane_live_laya_farm_loop_v1','started_at':time.time(),'steps':[],
        'completed_sites':0,'looted_finds':0,'last_progress_at':time.time(),'active_races':[],
        'via_tolbarad':False,'dig_output':None,'dig_site':None}
    batches=SolveBatches(set(session['active_races']))
    session.update(status='running',failure=None)
    with (runtime.ROOT/'run/farm_loop.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            while True:
                if (runtime.ROOT/'run/stop_dig').exists():session['status']='supervisor_stopped';break
                if time.time()-session['last_progress_at']>=1800:session['status']='inactive_30_minutes';break
                index=len(session['steps'])
                folder=output/f'step_{index:05d}'
                while folder.exists():index+=1;folder=output/f'step_{index:05d}'
                folder.mkdir(exist_ok=False)
                row=observe(folder/'before.png')
                action,target=phase(row,batches,session['via_tolbarad'])
                step={'phase':action,'before':row,'started_at':time.time(),'completed':False}
                session['steps'].append(step);runtime.write(path,session)
                if action=='recipe':session['status']='recipe_found';step['completed']=True;break
                if action=='wait':time.sleep(2)
                elif action=='jar':
                    step['result']=command_choice(folder/'jar',row,'/use Canopic Jar','Open the collected Canopic Jar','Open a Canopic Jar from the bags')
                    if not step['result']['executed']:raise RuntimeError('Laya waited with an unopened jar')
                elif action=='solve':
                    step['result']=solve_batch.run(folder/'solve',batches)
                    if step['result'].get('failure'):raise RuntimeError(step['result']['failure'])
                elif action=='teleport':
                    step['result']=teleport(folder,row);session['via_tolbarad']=False
                elif action=='portal':step['result']=portal.run(folder/'portal',target)
                elif action=='taxi':step['result']=taxi.run(folder/'taxi',*target)
                elif action=='flight':
                    length=distance(row['archaeology']['world'],target)
                    if length>1500:raise RuntimeError('public route requires additional flight waypoints')
                    step['orientation']=orient(folder/'orient',row,target)
                    step['inputs']=fly(folder,step['orientation']['after'],{'endpoint':target,'source':'public Canopic travel route'},step)
                elif action=='dig':
                    site=row['archaeology']['site_id']
                    if session['dig_output'] is None or (site is not None and site!=session['dig_site']):
                        session.update(dig_output=str(folder/'dig'),dig_site=site)
                    args=SimpleNamespace(output=Path(session['dig_output']),steps=1,loot_at=None,auto_loot=True)
                    step['result']=dig_session.run(args)
                    if step['result'].get('failure'):raise RuntimeError(step['result']['failure'])
                    if step['result'].get('finished'):
                        session.update(via_tolbarad=True,dig_output=None,dig_site=None)
                after=observe(folder/'after.png');step.update(after=after,completed=True,finished_at=time.time())
                before_a,after_a=row['archaeology'],after['archaeology']
                finds=max(0,after_a['looted_finds']-before_a['looted_finds'])
                before_route=(row.get('farm_ui') or {}).get('route') or {}
                after_route=(after.get('farm_ui') or {}).get('route') or {}
                sites=max(0,after_route.get('session_sites',0)-before_route.get('session_sites',0))
                session['looted_finds']+=finds;session['completed_sites']+=sites
                if sites:session.update(via_tolbarad=True,dig_output=None,dig_site=None)
                moved=distance(before_a['world'],after_a['world']) if after_a['world'] else 0
                solved=any(new['fragments']<old['fragments'] for old,new in zip(before_a['races'],after_a['races']))
                if finds or sites or moved>.25 or solved or after_a['canopic_jars_in_bags']!=before_a['canopic_jars_in_bags']:
                    session['last_progress_at']=time.time()
                session['active_races']=sorted(batches.active_races);runtime.write(path,session)
                print(json.dumps({'phase':action,'finds':session['looted_finds'],'sites':session['completed_sites']}),flush=True)
        except Exception as error:
            session.update(status='repair_required',failure=f'{type(error).__name__}: {error}')
        finally:
            session['updated_at']=time.time();session['active_races']=sorted(batches.active_races);runtime.write(path,session)
    return {k:session[k] for k in ('status','failure','looted_finds','completed_sites')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    print(json.dumps(run(parser.parse_args().output)))
