"""Return local action failures to Laya without discarding farm progress."""
import json
import math
import time
from pathlib import Path
from . import runtime,laya_ui,pending_find,farm_graph,escape_route
from .observe import observe


RETRYABLE=(
    'selected client action invalidated',
    'client changed, casting started, or supervisor moved before input',
    'selected client action readiness timed out',
    'character or owned client unavailable for UI input',
    'continuous waypoint exceeded its calculated emergency bound',
    'continuous waypoint movement is blocked',
    'calculated ascent made no height progress',
    'calculated ascent lost a healthy owned height observation',
    'calculated ascent exceeded its emergency bound',
    'repeated terrain contact without route progress',
    'flight cruise was blocked',
    'flight repeated phases without reaching the addon endpoint',
    'walking outcome was blocked or exceeded its bound',
    'mount input did not produce mounted state',
    'dismount input did not produce unmounted state',
    'takeoff did not produce flying state',
    'descent did not confirm landing',
    'character drifted away from landing destination',
    'Survey result did not receive fresh public facts',
    'Mouse Button 4 did not produce a successful Survey',
    'artifact interaction did not confirm fragment pickup',
    'key-1 combat has made no target-health progress',
    'combat target approach made no movement or range progress',
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
    'character or owned feed unavailable during continuous approach',
    'character became unavailable during flight',
    'character unavailable during descent',
    'character became unavailable after input',
    'local public tiles unavailable:',
    'Survey is still on cooldown',
    'new Survey replaced the active telescope route',
    'camera steering did not produce observed yaw',
    'camera view did not reach forward alignment',
    'camera view interrupted by player state',
    'minimap tooltip observation did not follow the cursor',
    'terrain falling interrupted the continuous approach',
    'unexpected movement mode during continuous approach',
    'swimming depth adjustment',
    'no matching public tooltip in bounded interaction search',
    'artifact tooltip observation did not follow the cursor',
    'named artifact mouseover is unavailable',
    'named artifact mouseover changed before interaction',
    'no named flight master candidate at the addon origin',
)


def retryable(error):
    return any(reason in str(error) for reason in RETRYABLE)


def run(folder,row,step,session,graph):
    folder.mkdir(exist_ok=False)
    pending=pending_find.load(row)
    state=json.loads(graph.read_text());current=state.get('last_action_node',state['current'])
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
    alternatives={}
    terrain={};route={}
    if (step['phase'] in ('flight','dig') and not m['in_combat'] and not a['casting']
            and m.get('facing_radians') is not None
            and not a['falling'] and (m.get('speed',0)==0 or any(reason in step['local_failure']
                for reason in ('blocked','no height progress','movement mode')))):
        target=step.get('target')
        if step['phase']=='dig' and session.get('dig_output'):
            dig=json.loads((Path(session['dig_output'])/'session.json').read_text())
            guide=(dig.get('steps') or [{}])[-1].get('guide') or {}
            target=guide.get('world') or target
        alternatives=escape_route.candidates(row,target)
        from . import terrain_context
        terrain=terrain_context.facts(row,target)
        route=terrain_context.detour(row,target)
        choices.update({key:'Move 4 yards '+key.removeprefix('step_')+
            ' relative to the route using forward movement and camera steering to clear the obstruction'
            for key in alternatives})
        if route.get('available'):choices['follow_detour']='Follow the connected reference ground route around the obstruction'
    state={'goal':'Find the Vial of the Sands recipe through archaeology',
        'failed_activity':step['phase'],'failure':step['local_failure'],
        'combat':m['in_combat'],'mounted':a['mounted'],'flying':a['flying'],
        'pending_pickup':bool(pending),'world':a['world'],'grounded':a.get('grounded'),
        'local_movement_alternatives':alternatives,
        'terrain':terrain,'reference_ground_detour':route,
        'recent_recoveries':session.get('recoveries',[])[-3:]}
    context=state
    instructions=('Choose the next recovery. Preserve an uncollected find. Change approach '
        'when repeated attempts do not progress.')
    if alternatives:
        start_pose=(step.get('before') or {}).get('owned_pose') or {}
        end_pose=row.get('owned_pose') or {}
        dz=(end_pose['height_yards']-start_pose['height_yards']
            if 'height_yards' in start_pose and 'height_yards' in end_pose else None)
        progressed=False
        for previous in session.get('recoveries',[])[-3:]:
            old,new=previous.get('world'),previous.get('after_world')
            if old and new and old['instance']==new['instance']:
                progressed=progressed or math.hypot(old['north']-new['north'],old['west']-new['west'])>.25
        context={'task':'Escape an obstruction to resume '+('digging' if step['phase']=='dig' else 'flying'),
            'ascent_blocked':bool('ascent' in step['local_failure'] and dz is not None and abs(dz)<.25),
            'position_changed_after_retries':progressed,'flying':a['flying'],'grounded':a.get('grounded'),
            'directions_clear_in_reference_geometry':{key:value['reference_collision_clear'] for key,value in alternatives.items()},
            'terrain':terrain,'reference_detour_available':route.get('available',False),
            'pending_pickup':bool(pending)}
        descriptions={'retry':'Repeat the blocked movement','wait':'Wait here','land':'Land and dismount',
            'resurvey':'Survey again from this position',
            'step_left':'Move left around the obstruction','step_right':'Move right around the obstruction',
            'step_back':'Move back away from the obstruction','step_forward':'Move forward toward the destination',
            'follow_detour':'Follow the connected ground route around the wall'}
        choices={key:descriptions[key] for key in choices}
        instructions=('Choose how to clear the obstacle. A blocked reference climb suggests a ceiling. '
            'Use a clear side or connected ground detour instead of repeating a failed ascent. '
            'Reference geometry can differ from the live client. Preserve a pending artifact.')
    action,request,response=laya_ui.choose(context,instructions,choices)
    result={'at':time.time(),'choice':action,'state':context,'observed_context':state,
        'request':request,'response':response,'inputs':[]}
    runtime.write(folder/'recovery.json',result)
    if action=='land':
        from .flight import fly
        result['inputs']=fly(folder,row,{'endpoint':a['world']},result,combat_landing=m['in_combat'])
    elif action in alternatives or action=='follow_detour':
        from . import terrain_context
        from .smooth_move import GroundContact
        result['target']=route['points'][-1] if action=='follow_detour' else alternatives[action]['target']
        try:
            result['movement']=terrain_context.move(folder,row,action,request,response,alternatives,route)
        except GroundContact as contact:
            result.update(outcome='short_recovery_reached_ground',ground_contact=contact.observation)
    elif action=='resurvey':
        path=Path(session['dig_output'])/'session.json'
        dig=json.loads(path.read_text())
        from .guide import reobserve
        reobserve(dig)
        runtime.write(path,dig)
    else:time.sleep(1 if action=='wait' else .2)
    result['after']=observe(folder/'after.png');result['completed']=True
    runtime.write(folder/'recovery.json',result)
    session['recoveries']=(session.get('recoveries',[])+[{'at':result['at'],
        'failure':step['local_failure'],'choice':action,'world':a['world'],
        'after_world':result['after']['archaeology']['world']}])[-8:]
    return result
