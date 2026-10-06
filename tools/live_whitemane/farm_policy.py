"""Laya selects the farm activity from current public state and legal actions."""
import math
import json
from pathlib import Path
from . import laya_ui,pending_find,dig_decisions,world_facts
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
    if m['in_combat']:return actions
    if not a['mounted'] and not a['flying']:
        if (a['can_survey'] or row.get('pending_find') or row.get('visible_find') or a.get('loot_open')
                or (row.get('minimap_finds') or {}).get('confirmed')
                or (ui.get('soft_interact') or {}).get('name') in FIND_NAMES):
            actions['dig']=('Choose Survey, marker/telescope movement or artifact pickup',None)
        if pending_find.facts(row,row.get('pending_find'))['uncollected']:return actions
        for r in a['races']:
            required=max(0,r['cost']-12*min(r['sockets'],r['keystones_in_bags']))
            if r['cost']>0 and r['fragments']>=required and (r['fragments']>=150 or r['index'] in batches.active_races):
                actions[f"solve_{r['index']}"]=(f"Solve race {r['index']} using maximum accepted keystones",{'race':r['index']})
    if pending_find.facts(row,row.get('pending_find'))['uncollected']:return actions
    if m['map_id']!=245 and route.get('kind')=='shortcut' and teleport_button(ui):
        actions['teleport']=('Use the Tol Barad teleport button',None)
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
    if route.get('origin') and route.get('exit'):
        target=route['origin']['point']
        if distance(a['world'],target)<12:actions['taxi']=('Take the route taxi',(route['origin'],route['exit']))
        elif a['world'] and a['world']['instance']==target['instance']:
            actions['flight']=('Fly to the route flight master',target)
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
            {**dig_guide['world'],'arrival_tolerance_yards':tolerance})
    return actions


def choose(row,batches,session):
    a,m=row['archaeology'],row['movement'];ui=row.get('farm_ui') or {}
    if a['recipe_items_in_bags'] or ui.get('recipe_known'):return 'recipe',None,{'completion':'recipe observed'}
    if a['canopic_jars_in_bags']:return 'jar',None,{'completion':'jar observed'}
    dig_guide=None;guide_error=None;ground_blocked=False
    if session.get('dig_output'):
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
    if len(options)==1:return 'wait',None,{'only_legal_action':'wait'}
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
        'fragments':[{k:r[k] for k in ('index','fragments','cost','sockets','keystones_in_bags')} for r in a['races'] if r['cost']],
        'last_failure':[{ 'failure':r['failure'][:120],'choice':r['choice']} for r in session.get('recoveries',[])[-1:]]}
    action,request,response=laya_ui.choose(state,
        'Choose the next activity. A discovered uncollected artifact means the current activity is pickup. '
        'Remain in pickup until collection is confirmed, including after the digsite is replaced. '
        'Finish the current digsite by following its guide before traveling onward. '
        'Prefer saved GatherMate markers; use telescope fallback. Collect discovered finds before leaving. '
        'Start solve batches around 150 fragments and continue while affordable with maximum keystones. '
        'Follow the current route instruction through Tol Barad and Orgrimmar to the next digsite. '
        'Use a nearby portal; if its ground approach is blocked, fly to that entrance and land. Learn from the last failure.',
        {k:v[0] for k,v in options.items()})
    action=dig_decisions.explore(action,response,options,state)
    return ('solve' if action.startswith('solve_') else action),options[action][1],{'state':state,'request':request,'response':response,'choice':action}
