"""Laya selects the farm activity from current public state and legal actions."""
import math
import json
from pathlib import Path
from . import laya_ui
from tools.client_compatibility.archaeology_inputs import FIND_NAMES


def distance(a,b):
    return math.inf if not a or not b or a['instance']!=b['instance'] else math.hypot(a['north']-b['north'],a['west']-b['west'])


def legal_actions(row,batches,dig_guide=None):
    a,m=row['archaeology'],row['movement'];ui=row.get('farm_ui') or {};route=ui.get('route') or {}
    actions={'wait':('Wait and observe',None)}
    if not ui or not m['in_world'] or m['dead'] or m['on_taxi'] or a['casting']:return actions
    actions['minimap']=('Inspect visible minimap blips',None)
    if m['in_combat']:actions['combat']=('Use Sinister Strike on the current target, landing and facing as needed',None)
    if a['mounted'] or a['flying'] or a['falling']:
        actions['land']=('Land here and toggle Shift+Space to dismount',a['world'])
    if m['in_combat']:return actions
    if not a['mounted'] and not a['flying']:
        if (a['can_survey'] or row.get('pending_find') or a.get('loot_open')
                or (ui.get('soft_interact') or {}).get('name') in FIND_NAMES):
            actions['dig']=('Choose Survey, marker/telescope movement or artifact pickup',None)
        for r in a['races']:
            required=max(0,r['cost']-12*min(r['sockets'],r['keystones_in_bags']))
            if r['cost']>0 and r['fragments']>=required:
                actions[f"solve_{r['index']}"]=(f"Solve race {r['index']} using maximum accepted keystones",{'race':r['index']})
    if any(b.get('label')=='Teleport' and b.get('enabled',True) for b in ui.get('actionbars',[])):
        actions['teleport']=('Open Teleport and choose Tol Barad',None)
    if ui.get('taxi') and route.get('exit'):
        current=route.get('current_taxi');node=next((n for n in ui['taxi'] if n['id']==current),None)
        if node:actions['taxi']=('Take the route taxi',({'id':current,'name':node['label'],'point':a['world']},route['exit']))
    portals=list(route.get('known_portals') or [])
    if route.get('portal'):portals.append(route['portal'])
    for p in portals:
        if distance(a['world'],p.get('from'))<20:actions['portal']=('Use the nearby route portal',p)
        elif route.get('portal')==p:actions['flight']=('Fly to the route portal',p['from'])
    if route.get('origin') and route.get('exit'):
        target=route['origin']['point']
        if distance(a['world'],target)<12:actions['taxi']=('Take the route taxi',(route['origin'],route['exit']))
        else:actions['flight']=('Fly to the route flight master',target)
    if route.get('site') and 'flight' not in actions:actions['flight']=('Fly to the next addon digsite',route['site']['point'])
    if dig_guide and not dig_guide['arrived']:
        actions['flight']=('Fly toward the current dig guide',dig_guide['world'])
    return actions


def choose(row,batches,session):
    a,m=row['archaeology'],row['movement'];ui=row.get('farm_ui') or {}
    if a['recipe_items_in_bags'] or ui.get('recipe_known'):return 'recipe',None,{'completion':'recipe observed'}
    if a['canopic_jars_in_bags']:return 'jar',None,{'completion':'jar observed'}
    dig_guide=None;guide_error=None
    if session.get('dig_output'):
        from . import dig_session,guide
        path=Path(session['dig_output'])/'session.json'
        if path.exists():
            dig=json.loads(path.read_text())
            try:dig_guide,_=guide.select(row,dig,dig_session.telescope(row,dig))
            except RuntimeError as error:guide_error=str(error)
    options=legal_actions(row,batches,dig_guide)
    if len(options)==1:return 'wait',None,{'only_legal_action':'wait'}
    route=ui.get('route') or {};signal=row.get('minimap_finds') or {}
    state={'goal':'Find a Canopic Jar; leave it unopened',
        'health':m['health_percent'],'combat':m['in_combat'],'mounted':a['mounted'],'flying':a['flying'],
        'at_digsite':a['can_survey'],'Survey_ready':(ui.get('survey') or {}).get('ready'),
        'guide':{k:v for k,v in (dig_guide or a.get('arrow') or {}).items()
            if k in ('source','color','distance_yards','heading_relative_to_player','arrived')},
        'named_object':(ui.get('soft_interact') or {}).get('name'),
        'pending_pickup':bool(row.get('pending_find')),'minimap':signal.get('status'),
        'guide_error':guide_error,
        'route':route.get('kind'),'via_Tol_Barad_requested':session['via_tolbarad'],
        'fragments':[{k:r[k] for k in ('index','fragments','cost','sockets','keystones_in_bags')} for r in a['races'] if r['cost']],
        'last_failure':[{ 'failure':r['failure'][:120],'choice':r['choice']} for r in session.get('recoveries',[])[-1:]]}
    action,request,response=laya_ui.choose(state,
        'Choose the next activity. Finish the current digsite by following its guide before traveling onward. '
        'Prefer saved GatherMate markers; use telescope fallback. Collect discovered finds before leaving. '
        'Start solve batches around 150 fragments and continue while affordable with maximum keystones. '
        'Travel via Tol Barad and Orgrimmar to the next digsite. Learn from the last failure.',
        {k:v[0] for k,v in options.items()})
    return ('solve' if action.startswith('solve_') else action),options[action][1],{'state':state,'request':request,'response':response,'choice':action}
