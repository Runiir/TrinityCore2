"""Return local action failures to Laya without discarding farm progress."""
import json
import time
from pathlib import Path
from . import runtime,laya_ui,pending_find,farm_graph
from .observe import observe


RETRYABLE=(
    'continuous waypoint exceeded its calculated emergency bound',
    'continuous waypoint movement is blocked',
    'calculated ascent made no height progress',
    'calculated ascent exceeded its emergency bound',
    'repeated terrain contact without route progress',
    'flight cruise was blocked',
    'walking outcome was blocked or exceeded its bound',
    'mount input did not produce mounted state',
    'dismount input did not produce unmounted state',
    'takeoff did not produce flying state',
    'descent did not confirm landing',
    'artifact interaction did not confirm fragment pickup',
    'key-1 combat has made no target-health progress',
    'current-target facing remained blocked',
    'Laya disagreed with declared policy',
    'movement decision lease expired',
    'waiting for a boundary-verified public addon arrow',
    'Laya waited during a ready solve batch',
    'Laya waited at flight master ride option',
    'Laya waited before Tol Barad teleport',
    'instant taxi did not confirm requested arrival',
    'portal interaction did not confirm destination arrival',
    'Tol Barad teleport did not confirm destination',
    'Laya height refresh did not obtain a fresh pose',
    'portal approach needs Laya portal action',
    'unexpected travel action for a flight route',
    'unexpected action at a grounded flight master',
    'Laya interrupted continuous waypoint movement',
    'character unavailable for this walking trial',
    'Survey is still on cooldown',
    'new Survey replaced the active telescope route',
    'camera steering did not produce observed yaw',
    'camera view did not reach forward alignment',
    'minimap tooltip observation did not follow the cursor',
    'terrain falling interrupted the continuous approach',
    'no matching public tooltip in bounded interaction search',
)


def retryable(error):
    return any(reason in str(error) for reason in RETRYABLE)


def run(folder,row,step,session,graph):
    folder.mkdir(exist_ok=False)
    pending=pending_find.load(row)
    current=json.loads(graph.read_text())['current']
    if current=='gather':farm_graph.transition(graph,'verify_pickup',row,pending=pending,outcome='pickup_unconfirmed')
    farm_graph.transition(graph,'observe',row,pending=pending,outcome='recover_local_action_failure')
    a=row['archaeology'];m=row['movement']
    choices={'retry':'Reobserve and retry the interrupted activity with fresh facts',
             'wait':'Wait for conditions to change without gameplay input'}
    if a['mounted'] or a['flying'] or a['falling']:
        choices['land']='Land at the current position and dismount before trying again'
    if (step['phase']=='dig' and session.get('dig_output') and not pending and a['can_survey']
            and not a['mounted'] and not a['flying'] and not m['in_combat']):
        choices['resurvey']='Discard the failed route estimate and use a fresh Survey from this position'
    state={'goal':'Continue archaeology farming until a Canopic Jar is in the bags',
        'failed_activity':step['phase'],'failure':step['local_failure'],
        'combat':m['in_combat'],'mounted':a['mounted'],'flying':a['flying'],
        'pending_pickup':bool(pending),'world':a['world'],
        'recent_recoveries':session.get('recoveries',[])[-3:]}
    action,request,response=laya_ui.choose(state,
        'Choose the next recovery. Preserve an uncollected find. Change approach when repeated attempts do not progress.',choices)
    result={'at':time.time(),'choice':action,'state':state,'request':request,'response':response,'inputs':[]}
    runtime.write(folder/'recovery.json',result)
    if action=='land':
        from .flight import fly
        result['inputs']=fly(folder,row,{'endpoint':a['world']},result,combat_landing=m['in_combat'])
    elif action=='resurvey':
        path=Path(session['dig_output'])/'session.json'
        dig=json.loads(path.read_text())
        dig.update(marker_fallback=True,marker_target=None,walked_since_survey=True)
        dig.pop('telescope_target',None);dig.pop('last_green_endpoint',None)
        runtime.write(path,dig)
    else:time.sleep(1 if action=='wait' else .2)
    result['after']=observe(folder/'after.png');result['completed']=True
    runtime.write(folder/'recovery.json',result)
    session['recoveries']=(session.get('recoveries',[])+[{'at':result['at'],
        'failure':step['local_failure'],'choice':action,'world':a['world']}])[-8:]
    return result
