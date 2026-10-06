"""Supervised repeating archaeology with Laya-owned inputs and public outcomes."""
import argparse
import fcntl
import json
import math
from pathlib import Path
from types import SimpleNamespace
import time
from . import runtime, dig_session, portal, taxi, solve_batch, resources,pending_find,minimap_finds,combat,farm_graph,recovery,farm_policy
from .observe import observe
from .farm_actions import click_choice, command_choice
from .navigation import orient
from .flight import fly
from .dig_policy import SolveBatches
from . import observation_wait


def distance(world,target):
    return math.inf if not world or world['instance']!=target['instance'] else math.hypot(world['north']-target['north'],world['west']-target['west'])


def phase(row,batches,via_tolbarad=False,pending=None):
    """Historical selector for replay comparison; live selection uses Laya."""
    m,a,ui=row['movement'],row['archaeology'],row.get('farm_ui')
    if ui and m['in_world'] and m['in_combat'] and not m['dead']:return 'combat',None
    if not ui or not m['in_world'] or m['dead'] or m['in_combat'] or m['health_percent']<90 or a['casting'] or m['on_taxi'] or m.get('speed',0)>0:
        return 'wait',None
    if a['recipe_items_in_bags']>0 or ui['recipe_known']:return 'recipe',None
    if a['canopic_jars_in_bags']>0:return 'jar',None
    route=ui.get('route') or {}
    if pending or (row.get('minimap_finds') or {}).get('confirmed'):return 'dig',None
    if (row.get('minimap_finds') or {}).get('status')=='uninspected_candidates':return 'minimap',None
    if route.get('kind')=='pending_loot':return 'dig',None
    if not a['mounted'] and not a['flying'] and any(batches.next_project(r) for r in a['races']):return 'solve',None
    if a['can_survey']:
        if a['mounted'] or a['flying']:return 'flight',a['world']
        return 'dig',None
    if row.get('minimap_finds') and not row['minimap_finds']['clear']:return 'minimap',None
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
    def arrived(row):
        return row['movement']['map_id']==245 and not row['archaeology']['casting']
    if arrived(row):return {'after':row,'completed':True,'already_at_destination':True}
    button=farm_policy.teleport_button(row['farm_ui'])
    if not button:raise RuntimeError('public Tol Barad teleport button is unavailable')
    expected={k:button[k] for k in ('kind','id','label') if k in button}
    opened=click_choice(folder/'open',row,['actionbars'],'Teleport to Tol Barad',expected)
    if not opened['executed']:raise RuntimeError('Laya waited before Tol Barad teleport')
    row=opened['after'];direct=button.get('kind')=='spell' and button.get('id')==5000028
    chosen=None
    for i in range(40):
        if arrived(row):return {'opened':opened,'chosen':chosen,'after':row,'completed':True}
        if not direct and chosen is None and row['farm_ui'].get('flyout'):
            chosen=click_choice(folder/'destination',row,['flyout'],'Teleport to Tol Barad',{'label':'Tol Barad'})
            if not chosen['executed']:raise RuntimeError('Laya waited before Tol Barad teleport')
            row=chosen['after'];continue
        time.sleep(.3)
        try:row=observe(folder/'arrival.png')
        except RuntimeError as error:
            if str(error).startswith(('live public observer is unavailable','direct public addon feed unavailable',
                    'local public tiles unavailable')):continue
            raise
    raise RuntimeError('Tol Barad teleport did not confirm destination')


def run(output,stop_on='recipe'):
    resources.enable();resources.check(force=True)
    output.mkdir(parents=True,exist_ok=True)
    path=output/'loop.json'
    session=json.loads(path.read_text()) if path.exists() else {
        'schema':'whitemane_live_laya_farm_loop_v1','started_at':time.time(),'steps':[],
        'completed_sites':0,'looted_finds':0,'last_progress_at':time.time(),'active_races':[],
        'via_tolbarad':False,'dig_output':None,'dig_site':None}
    batches=SolveBatches(set(session['active_races']))
    resources.trim_session(session,'loop')
    if session.get('status') in ('inactive_30_minutes','repair_required','supervisor_stopped'):
        # An explicit new run resumes a stopped supervised session. Telemetry
        # and waiting inside a running farm never renew gameplay inactivity.
        session['resumed_at']=time.time();session['last_progress_at']=session['resumed_at']
    session.update(status='running',failure=None,stop_on=stop_on)
    session['selection_mode']='Laya current state and legal actions'
    graph=output/'graph.json'
    def sample(output):return observation_wait.sample(output,session,reader=observe)
    from .observed_state import ensure
    ensure(graph)
    with (runtime.ROOT/'run/farm_loop.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:
            while True:
                if (runtime.ROOT/'run/stop_dig').exists():session['status']='supervisor_stopped';break
                if time.time()-session['last_progress_at']>=1800:session['status']='inactive_30_minutes';break
                resources.check()
                index=session['next_step_index']
                folder=output/f'step_{index:05d}'
                while folder.exists():index+=1;folder=output/f'step_{index:05d}'
                folder.mkdir(exist_ok=False)
                row=sample(folder/'before.png')
                pending=pending_find.update(row,{})
                row['pending_find']=pending
                action,target,decision=farm_policy.choose(row,batches,session)
                session['next_step_index']=index+1
                step={'index':index,'phase':action,'target':target,'decision':decision,'before':row,'started_at':time.time(),'completed':False}
                session['steps'].append(step);resources.trim_session(session,'loop');runtime.write(path,session)
                node='jar_found' if action=='jar' and stop_on=='canopic_jar' else action
                step['graph_transition']=farm_graph.transition(graph,node,row,pending=pending,target=target)
                if action=='recipe':session['status']='recipe_found';step['completed']=True;break
                if action=='jar' and stop_on=='canopic_jar':session['status']='canopic_jar_found';step['completed']=True;break
                try:
                    if action=='wait':time.sleep(2)
                    elif action=='combat':
                        history=[]
                        if session['dig_output']:
                            dig_path=Path(session['dig_output'])/'session.json'
                            if dig_path.exists():
                                dig=json.loads(dig_path.read_text());history=dig.get('turn_history',[])+dig['steps']
                        step['result']=combat.run(folder/'combat',turn_history=history)
                    elif action=='minimap':
                        step['result']=minimap_finds.inspect(folder/'minimap',row)
                    elif action=='jar':
                        step['result']=command_choice(folder/'jar',row,'/use Canopic Jar','Open the collected Canopic Jar','Open a Canopic Jar from the bags')
                        if not step['result']['executed']:raise RuntimeError('Laya waited with an unopened jar')
                    elif action=='solve':
                        step['result']=solve_batch.run(folder/'solve',batches,race_id=target['race'])
                        if step['result'].get('failure'):raise RuntimeError(step['result']['failure'])
                    elif action=='teleport':
                        step['result']=teleport(folder,row);session['via_tolbarad']=False
                    elif action=='portal':
                        step['result']=portal.run(folder/'portal',target,approved_intent=(
                            action,decision['response'].get('model'),decision['request'],decision['response']))
                    elif action=='taxi':step['result']=taxi.run(folder/'taxi',*target)
                    elif action in ('flight','land'):
                        length=distance(row['archaeology']['world'],target)
                        if length>1500:
                            step['final_target']=target
                            origin=row['archaeology']['world'];fraction=1250/length
                            target={**target,**{k:origin[k]+(target[k]-origin[k])*fraction for k in ('north','west')}}
                        step['orientation']=orient(folder/'orient',row,target)
                        step['graph_path']=str(graph)
                        step['inputs']=fly(folder,step['orientation']['after'],{
                            'endpoint':target,'arrival_tolerance_yards':target.get('arrival_tolerance_yards',6),
                            'source':'public Canopic travel route'},step) if step['orientation']['completed'] else []
                    elif action=='dig':
                        site=pending['site_id'] if pending else row['archaeology']['site_id']
                        if session['dig_output'] is None or (site is not None and site!=session['dig_site']):
                            session.update(dig_output=str(folder/'dig'),dig_site=site)
                        args=SimpleNamespace(output=Path(session['dig_output']),steps=1,loot_at=None,auto_loot=True,graph=graph)
                        step['result']=dig_session.run(args)
                        if step['result'].get('failure'):
                            interrupted=sample(folder/'dig_interrupt.png')
                            if not interrupted['movement']['in_combat']:raise RuntimeError(step['result']['failure'])
                            step['combat_interruption']=True
                        if step['result'].get('finished'):
                            final=sample(folder/'final_pickup_check.png')
                            if pending_find.can_leave(final):session.update(via_tolbarad=True,dig_output=None,dig_site=None)
                except RuntimeError as error:
                    interrupted=sample(folder/'interrupted.png')
                    if action!='combat' and interrupted['movement']['in_combat']:
                        step.update(combat_interruption=True,interrupted_error=str(error))
                    elif recovery.retryable(error):
                        step.update(local_failure=str(error),outcome='returned_to_Laya_recovery')
                        try:
                            step['recovery']=recovery.run(folder/'recovery',interrupted,step,session,graph)
                        except RuntimeError as recovery_error:
                            if not recovery.retryable(recovery_error):raise
                            step['recovery']={'completed':False,'failure':str(recovery_error),
                                'outcome':'reobserve_with_Laya_on_next_loop'}
                            session['recoveries']=(session.get('recoveries',[])+[{
                                'at':time.time(),'failure':str(recovery_error),'choice':'reobserve',
                                'world':interrupted['archaeology']['world']}])[-8:]
                    else:raise
                after=sample(folder/'after.png');step.update(after=after,completed=True,finished_at=time.time())
                farm_graph.transition(graph,'observe',after,pending=pending_find.load(after))
                before_a,after_a=row['archaeology'],after['archaeology']
                finds=int(action=='dig' and pending_find.gained(pending_find.fragments(row),after))
                before_route=(row.get('farm_ui') or {}).get('route') or {}
                after_route=(after.get('farm_ui') or {}).get('route') or {}
                sites=max(0,after_route.get('session_sites',0)-before_route.get('session_sites',0))
                session['pending_site_completions']=session.get('pending_site_completions',0)+sites
                sites=0
                if session['pending_site_completions'] and pending_find.can_leave(after):
                    sites=session.pop('pending_site_completions')
                    session.update(via_tolbarad=True,dig_output=None,dig_site=None)
                session['looted_finds']+=finds;session['completed_sites']+=sites
                moved=distance(before_a['world'],after_a['world']) if after_a['world'] else 0
                solved=any(new['fragments']<old['fragments'] for old,new in zip(before_a['races'],after_a['races']))
                if finds or sites or moved>.25 or solved or after_a['canopic_jars_in_bags']!=before_a['canopic_jars_in_bags']:
                    session['last_progress_at']=time.time()
                session['active_races']=sorted(batches.active_races);runtime.write(path,session)
                resources.phase_boundary(output,session)
                print(json.dumps({'phase':action,'finds':session['looted_finds'],'sites':session['completed_sites']}),flush=True)
        except observation_wait.InactiveObservation:
            session.update(status='inactive_30_minutes',failure=None)
        except Exception as error:
            if (runtime.ROOT/'run/stop_dig').exists():session.update(status='supervisor_stopped',failure=None)
            else:session.update(status='repair_required',failure=f'{type(error).__name__}: {error}')
        finally:
            session['updated_at']=time.time();session['active_races']=sorted(batches.active_races);runtime.write(path,session)
    return {k:session[k] for k in ('status','failure','looted_finds','completed_sites')}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stop-on',choices=('canopic_jar','recipe'),default='canopic_jar')
    args=parser.parse_args();print(json.dumps(run(args.output,args.stop_on)))
