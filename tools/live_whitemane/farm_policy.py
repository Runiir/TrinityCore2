"""Laya selects the farm activity from current public state and legal actions."""
import math
import json
from pathlib import Path
from . import laya_ui,pending_find,dig_decisions,world_facts
from .intent_queue import IntentQueue
from tools.client_compatibility.archaeology_inputs import FIND_NAMES


def distance(a,b):
    return math.inf if not a or not b or a['instance']!=b['instance'] else math.hypot(a['north']-b['north'],a['west']-b['west'])


def teleport_button(ui):
    return next((b for b in ui.get('actionbars',[]) if b.get('enabled',True) and
        (b.get('kind')=='spell' and b.get('id')==5000028 or b.get('label')=='Teleport')),None)


def legal_actions(row,batches,dig_guide=None,*,ground_approach_blocked=False):
    a,m=row['archaeology'],row['movement'];ui=row.get('farm_ui') or {};route=ui.get('route') or {}
    actions={'wait':('Wait and observe',None)}
    if not ui or not m['in_world'] or m['dead'] or m['on_taxi'] or a['casting']:return actions
    signal=row.get('minimap_finds') or {}
    if signal.get('clear') is not True and signal.get('status')!='unavailable':
        actions['minimap']=('Inspect visible minimap blips',None)
    if m['in_combat']:actions['combat']=('Use Sinister Strike on the current target, landing and facing as needed',None)
    if a['mounted'] or a['flying'] or a['falling']:
        actions['land']=('Land here and toggle Shift+Space to dismount',a['world'])
        if route.get('kind')=='shortcut':
            actions['land']=('Land and dismount here to prepare the teleport shortcut',a['world'])
    if m['in_combat']:return actions
    if not a['flying'] and not a.get('falling'):
        if (a['can_survey'] or row.get('pending_find') or row.get('visible_find') or a.get('loot_open')
                or (row.get('minimap_finds') or {}).get('confirmed')
                or (ui.get('soft_interact') or {}).get('name') in FIND_NAMES) and (
                not a['mounted'] or a['can_survey'] and not row.get('pending_find')):
            actions['dig']=('Choose Survey, marker/telescope movement or artifact pickup',None)
    if not a['mounted'] and not a['flying']:
        if pending_find.facts(row,row.get('pending_find'))['uncollected']:return actions
        for r in a['races']:
            required=max(0,r['cost']-12*min(r['sockets'],r['keystones_in_bags']))
            if r['cost']>0 and r['fragments']>=required and (r['fragments']>=150 or r['index'] in batches.active_races):
                actions[f"solve_{r['index']}"]=(f"Solve race {r['index']} using maximum accepted keystones",{'race':r['index']})
    if pending_find.facts(row,row.get('pending_find'))['uncollected']:return actions
    if (m['map_id']!=245 and route.get('kind')=='shortcut' and teleport_button(ui)
            and not any(a.get(k) for k in ('mounted','flying','falling'))):
        actions['teleport']=('Teleport to Tol Barad to begin the shortcut to Orgrimmar',None)
    if ui.get('taxi') and route.get('exit'):
        current=route.get('current_taxi');node=next((n for n in ui['taxi'] if n['id']==current),None)
        if node:actions['taxi']=('Take the route taxi',({'id':current,'name':node['label'],'point':a['world']},route['exit']))
    portals=list(route.get('known_portals') or [])
    if route.get('portal'):portals.append(route['portal'])
    for p in portals:
        if distance(a['world'],p.get('from'))<30:
            if not a['flying'] and not a['falling']:
                actions['portal']=('Approach and use the nearby route portal',p)
            if ui.get('flyable'):
                actions['flight']=('Fly precisely to the nearby portal entrance, then land',
                    {**p['from'],'arrival_tolerance_yards':.4})
        elif route.get('portal')==p and a['world'] and a['world']['instance']==p['from']['instance']:
            actions['flight']=('Fly to the route portal',p['from'])
    # The addon includes later legs in its route description. Its flight
    # master becomes the active destination only after the shortcut arrives.
    if route.get('origin') and route.get('exit') and route.get('kind')!='shortcut':
        target=route['origin']['point']
        if distance(a['world'],target)<12:actions['taxi']=('Take the route taxi',(route['origin'],route['exit']))
        elif a['world'] and a['world']['instance']==target['instance']:
            remaining=distance(a['world'],target)
            label=f'Fly directly {remaining:.0f} yards to the flight master'
            if route.get('kind')=='shortcut':label+=' before taking the shortcut'
            actions['flight']=(label,target)
    site=(route.get('site') or {}).get('point')
    if (site and not route.get('portal') and not route.get('origin') and a['world']
            and a['world']['instance']==site['instance'] and 'flight' not in actions
            and not a['can_survey']):
        actions['flight']=('Fly to the next addon digsite',site)
    if (dig_guide and not dig_guide['arrived'] and (a['mounted'] or a['flying'] or ground_approach_blocked)
            and a['world'] and a['world']['instance']==dig_guide['world']['instance']):
        tolerance=dig_guide.get('arrival_tolerance_yards',
            6 if dig_guide['color']=='red' else 4 if dig_guide['color']=='yellow' else .5)
        actions['flight']=('Fly to the current dig guide if its ground approach is blocked',
            {**dig_guide['world'],'arrival_tolerance_yards':tolerance,'site_id':a.get('site_id')})
    return actions


def choose(row,batches,session):
    a,m=row['archaeology'],row['movement'];ui=row.get('farm_ui') or {}
    if a['recipe_items_in_bags'] or ui.get('recipe_known'):return 'recipe',None,{'completion':'recipe observed'}
    if a['canopic_jars_in_bags']:return 'jar',None,{'completion':'jar observed'}
    dig_guide=None;guide_error=None;ground_blocked=False
    active_dig=(a['can_survey'] and a.get('site_id')==session.get('dig_site')) or row.get('pending_find')
    if session.get('dig_output') and active_dig:
        from . import dig_session,guide
        path=Path(session['dig_output'])/'session.json'
        if path.exists():
            dig=json.loads(path.read_text())
            ground_blocked=any(any(reason in (s.get('failure') or '') for reason in
                ('terrain falling','movement is blocked','calculated emergency bound'))
                for s in dig.get('steps',[])[-4:])
            try:dig_guide,_=guide.select(row,dig,dig_session.telescope(row,dig))
            except RuntimeError as error:guide_error=str(error)
    options=legal_actions(row,batches,dig_guide,ground_approach_blocked=ground_blocked)
    queued=IntentQueue(session).retained(row,options)
    if queued:return queued
    if len(options)==1:return 'wait',None,{'only_legal_action':'wait'}
    if m['in_combat']:
        c=ui.get('combat') or {}
        state={'task':'End the current combat and resume archaeology','combat':True,
            'mounted':a['mounted'],'flying':a['flying'],'falling':a.get('falling'),
            'target_attacks_player':c.get('target_engaged',c.get('target_attacks_player')),
            'target_in_melee_range':c.get('attack_in_range'),
            'current_target':c.get('target_name'),'health':m['health_percent'],
            'consecutive_actions_without_progress':sum(step.get('started_at',0)>=
                session.get('last_progress_at',math.inf) for step in session.get('steps',[]))}
        action,request,response=laya_ui.choose(state,
            'Respond to the attacker now. Land if airborne, then approach and use Sinister Strike. Resume the interrupted dig afterwards.',
            {k:v[0] for k,v in options.items()})
        action=dig_decisions.explore(action,response,options,state)
        decision={'state':state,'request':request,'response':response,'choice':action}
        IntentQueue(session).offer(action,options[action][1],decision,row)
        return action,options[action][1],decision
    route=ui.get('route') or {};signal=row.get('minimap_finds') or {}
    previous=session.get('steps',[])
    stalled=sum(step.get('started_at',0)>=session.get('last_progress_at',math.inf)
        for step in previous)
    observed=world_facts.reduce(row,row.get('pending_find'))
    state={'goal':'Find the Vial of the Sands recipe' if session.get('stop_on')=='recipe' else 'Find a Canopic Jar; leave it unopened',
        'activity':observed['activity'],'map_id':m['map_id'],
        'portal_distance_yards':observed['facts']['portal_distance_yards'],
        'health':m['health_percent'],'combat':m['in_combat'],'mounted':a['mounted'],'flying':a['flying'],
        'casting':a['casting'],'falling':a['falling'],
        'Survey_dismounts_on_ground':bool(a['mounted'] and not a['flying'] and not a.get('falling')),
        'at_digsite':a['can_survey'],'Survey_ready':(ui.get('survey') or {}).get('ready'),
        'guide':{k:v for k,v in (dig_guide or a.get('arrow') or {}).items()
            if k in ('source','color','distance_yards','heading_relative_to_player','arrived')},
        'named_object':(ui.get('soft_interact') or {}).get('name'),
        'pending_pickup':bool(row.get('pending_find')),'minimap':signal.get('status'),
        'minimap_clear':signal.get('clear'),
        'recent_actions':[{'action':step['phase'],'completed':step.get('completed',False),
            'failure':step.get('local_failure')} for step in previous[-4:]],
        'consecutive_actions_without_progress':stalled,
        'pickup':pending_find.facts(row,row.get('pending_find')),
        'guide_error':guide_error,
        'ground_approach_blocked':ground_blocked,
        'route':route.get('kind'),'route_instruction':route.get('instruction'),
        'via_Tol_Barad_requested':session['via_tolbarad'],
        'route_distances_yards':{name:round(distance(a['world'],point)) for name,point in (
            ('flight_master',(route.get('origin') or {}).get('point')),
            ('digsite',(route.get('site') or {}).get('point')))
            if math.isfinite(distance(a['world'],point))},
        'teleport_shortcut_pending':route.get('kind')=='shortcut',
        'completed_site_pending_minimap_check':bool(session.get('pending_site_completions') and signal.get('clear') is not True),
        'fragments':[{k:r[k] for k in ('index','fragments','cost','sockets','keystones_in_bags')} for r in a['races'] if r['cost']],
        'last_failure':[{ 'failure':r['failure'][:120],'choice':r['choice']} for r in session.get('recoveries',[])[-1:]]}
    action,request,response=laya_ui.choose(state,
        'Choose the next activity. A discovered uncollected artifact means the current activity is pickup. '
        'Remain in pickup until collection is confirmed, including after the digsite is replaced. '
        'Finish the current digsite by following its guide before traveling onward. '
        'Prefer saved GatherMate markers; use telescope fallback. Collect discovered finds before leaving. '
        'Start solve batches around 150 fragments and continue while affordable with maximum keystones. '
        'Follow the current route instruction through Tol Barad and Orgrimmar to the next digsite. '
        'When the teleport shortcut is pending, use Tol Barad and its Orgrimmar portal before approaching the distant flight master. '
        'Land first for a stationary teleport. Check remaining minimap blips before leaving a completed site. '
        'Use a nearby portal; if its ground approach is blocked, fly to that entrance and land. Learn from the last failure.',
        {k:v[0] for k,v in options.items()})
    action=dig_decisions.explore(action,response,options,state)
    phase='solve' if action.startswith('solve_') else action
    decision={'state':state,'request':request,'response':response,'choice':action}
    IntentQueue(session).offer(phase,options[action][1],decision,row)
    return phase,options[action][1],decision
